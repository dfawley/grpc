> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 9.9 xDS Security

<!-- Sources: A29, A65, A82, A86, A87, A101, A36, doc/grpc_xds_bootstrap_format.md -->

> **Introduced by:** [gRFC A29: xDS-Based Security for gRPC Clients and Servers](https://github.com/grpc/proposal/blob/master/A29-xds-tls-security.md)

This section specifies how gRPC clients and servers obtain transport security
(TLS and mTLS) configuration from xDS: client-side configuration from the CDS
`Cluster.transport_socket` (`UpstreamTlsContext`) and server-side configuration
from the Listener `FilterChain.transport_socket` (`DownstreamTlsContext`).
Certificates and keys are never sent by the control plane; the control plane
names *certificate provider instances* that are defined locally in the
bootstrap.

Generic TLS behavior (certificate providers, SPIFFE verification, handshake
and verification details) is specified in
[TLS](../06-security/02-tls.md) (in particular, its
certificate provider and SPIFFE subsections). Configuring TLS for the
connection to the xDS server itself (the `tls` bootstrap channel credential
type) is specified in [Bootstrap](02-bootstrap.md).

## 1. XdsChannelCredentials and XdsServerCredentials

Applications opt in to xDS-provided transport security by using
**XdsChannelCredentials** (for a channel) or **XdsServerCredentials** (for a
server). Each is constructed with **fallback credentials** (any channel or
server credentials, respectively).

| Situation | Credentials used |
|---|---|
| xDS not in use (e.g., the channel target does not use the `xds` scheme) | Fallback credentials. |
| xDS in use; the control plane provides no security configuration (client: the cluster has no `UpstreamTlsContext`; server: the selected filter chain has no `transport_socket`) | Fallback credentials. |
| xDS in use; the control plane provides security configuration | The xDS-provided TLS configuration. |
| Error while using the xDS-provided configuration (e.g., certificate unavailable, handshake or verification failure) | **No fallback.** The connection attempt or connection fails. |

To get plaintext communication when the control plane provides no security
configuration, the application MUST use insecure credentials as the fallback.

Applications are not required to use these credentials types with xDS
channels or servers; with any other credentials, xDS-provided TLS
configuration is ignored (though it is still validated).

**Validation is independent of credentials.** gRPC always validates the
security configuration in CDS and LDS resources, whether or not
XdsChannelCredentials or XdsServerCredentials are in use, and NACKs invalid
resources. As a general rule, unsupported fields are ignored, except that a
field whose being ignored would compromise security, or that changes the
interpretation of other fields, causes a NACK when present.

When XdsChannelCredentials use the xDS-provided TLS configuration, the
authority-based hostname verification normally performed by TLS is not
performed; server identity is instead checked as described in [Server Identity Verification](#3-server-identity-verification).

## 2. Client Side: `UpstreamTlsContext`

### 2.1 Locating the TLS Context

The CDS resource's `Cluster.transport_socket` ([Cluster](04-resources/04-cluster.md))
determines client transport security. In the table, `UpstreamTlsContext` is
`envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext`, and
`Http11ProxyUpstreamTransport` is
`envoy.extensions.transport_sockets.http_11_proxy.v3.Http11ProxyUpstreamTransport`.

| `transport_socket.typed_config` type (after `TypedStruct` unwrapping) | Result |
|---|---|
| absent (`transport_socket` unset) | No xDS security configuration (fallback credentials). |
| `UpstreamTlsContext` | Validated per [`UpstreamTlsContext` Validation](#22-upstreamtlscontext-validation) and used. |
| `Http11ProxyUpstreamTransport` | HTTP CONNECT wrapper ([HTTP CONNECT and TLS](#6-http-connect-and-tls)). Its nested `transport_socket` MUST be unset or contain an `UpstreamTlsContext`, which is validated and used exactly as if it had been in `Cluster.transport_socket`. Any other nested type → NACK. |
| any other type | NACK. |

`Cluster.transport_socket_matches` is ignored.

The `UpstreamTlsContext` and `DownstreamTlsContext` messages MUST be given in
serialized protobuf form. A `TypedStruct` whose inner type is one of them is
identified as that type but then rejected (see
[Common Types](04-resources/01-common-types.md)).

The parsed security configuration is part of the parsed cluster resource and
is applied to all connections to the cluster's endpoints
([`xds_cluster_impl`](lb-policies/xds_cluster_impl.md)).

### 2.2 `UpstreamTlsContext` Validation

| Field | Handling |
|---|---|
| `common_tls_context` | Validated per [`CommonTlsContext` Validation](#4-commontlscontext-validation). A CA source MUST result (see below). |
| `sni` | If longer than 255 characters → NACK. Used per [SNI Selection](#23-sni-selection). Empty means not specified. |
| `auto_host_sni` | Used per [SNI Selection](#23-sni-selection). |
| `auto_sni_san_validation` | Used per [Server Identity Verification](#3-server-identity-verification). |
| `allow_renegotiation`, `max_session_keys` | Ignored. |
| Other fields | Ignored. |

The client MUST have a source of trusted CA certificates. The
`CertificateValidationContext` is obtained from
`common_tls_context.validation_context` or from
`common_tls_context.combined_validation_context.default_validation_context`.
If neither is present → NACK. Within it, exactly one CA source is used:

- `ca_certificate_provider_instance` if set: the named certificate provider
  instance supplies CA certificates or a SPIFFE trust bundle map ([Certificate Provider Instances](#5-certificate-provider-instances)).
- otherwise `system_root_certs` if set: the platform's default root
  certificates are used.
- otherwise → NACK.

If `ca_certificate_provider_instance` is set, `system_root_certs` is ignored.
The parsed representation SHOULD make it impossible to represent both.

The client identity certificate, if any, comes from
`common_tls_context.tls_certificate_provider_instance`; it is sent if the
server requests or requires a client certificate. If it is unset, the client
has no certificate, and a server requiring one fails the handshake.

### 2.3 SNI Selection

> **Introduced by:** [gRFC A101: xDS-Based setting SNI and server certificate SAN validation](https://github.com/grpc/proposal/blob/master/A101-SNI-setting-and-SNI-SAN-validation.md)

When the xDS-provided TLS configuration is used, the Server Name Indication
for the handshake with an endpoint is determined as follows:

1. If `auto_host_sni` is true and the endpoint has a hostname, SNI is that
   hostname. The hostname is the endpoint hostname for EDS clusters
   (`Endpoint.hostname`; see [ClusterLoadAssignment and LbEndpointCollection](04-resources/05-endpoint.md)),
   or the DNS name for LOGICAL_DNS clusters
   ([Cluster](04-resources/04-cluster.md)). Any port is excluded. (This
   is the same hostname used for xDS authority rewriting.)
2. Otherwise, if `sni` is non-empty, SNI is `sni`.
3. Otherwise, no SNI is sent.

For example, if `auto_host_sni` is true but the endpoint has no hostname, and
`sni` is set, `sni` is used.

## 3. Server Identity Verification

After the server's certificate chain has been verified against the configured
trust source (CA certificates, system roots, or SPIFFE trust bundle; see
[Certificate Provider Instances](#5-certificate-provider-instances) and [TLS](../06-security/02-tls.md)), the client checks
the leaf certificate's Subject Alternative Names (SANs).

**Which check applies:**

- If `auto_sni_san_validation` is true **and** an SNI was sent (by whatever
  rule it was determined), the SANs are checked against the SNI, and
  `match_subject_alt_names` is not used. Only DNS-type SANs are considered,
  and a SAN matches if it matches the SNI as a DNS domain name per
  RFC 9525 §6.3 (case-insensitive, including wildcard SANs).
- Otherwise, the SANs are checked against `match_subject_alt_names` from the
  `CertificateValidationContext`, as follows.

**`match_subject_alt_names` check:**

1. If `match_subject_alt_names` is empty, the check succeeds.
2. If there is no leaf certificate, or it has no SAN entries, the check fails.
3. Each SAN entry of type DNS, URI, email, or IP address is considered. IP
   address SANs are converted to text before matching: IPv4 in dotted
   decimal, IPv6 in the canonical form of RFC 5952 §4. An empty SAN entry
   never matches.
4. A SAN entry matches if it matches any value in `match_subject_alt_names`.
   Each value is an `envoy.type.matcher.v3.StringMatcher` evaluated with its
   usual semantics (`exact`, `prefix`, `suffix`, `contains`, `safe_regex`, with
   `ignore_case`; see [Common Types](04-resources/01-common-types.md)).
   In addition, for DNS SANs, an `exact` value also matches a wildcard SAN
   (e.g., `*.example.com`) as described in RFC 9525 §6.3.
5. The check succeeds if any SAN entry matches.

If the check fails, the handshake fails with a certificate check failure.

## 4. `CommonTlsContext` Validation

`CommonTlsContext` appears in both `UpstreamTlsContext` and
`DownstreamTlsContext`. gRPC supports only certificate provider plugin
instances as a source of certificates.

| Field | Handling |
|---|---|
| `tls_certificate_provider_instance` (`CertificateProviderPluginInstance`) | Identity certificate and private key. `instance_name` MUST name an instance in the bootstrap `certificate_providers` map, else NACK. `certificate_name` is passed to the provider (ignored by `file_watcher`). |
| `tls_certificates`, `tls_certificate_sds_secret_configs` | If present while `tls_certificate_provider_instance` is unset → NACK. |
| `validation_context` | A `CertificateValidationContext` (below). |
| `combined_validation_context.default_validation_context` | A `CertificateValidationContext` (below). |
| `validation_context_sds_secret_config` | SDS is not supported → NACK. |
| `tls_params` | NACK. |
| `custom_handshaker` | NACK. |
| `alpn_protocols` | Ignored. |

`CertificateValidationContext`:

| Field | Handling |
|---|---|
| `ca_certificate_provider_instance` | CA certificates or SPIFFE trust bundle map. `instance_name` MUST name a bootstrap instance, else NACK. |
| `system_root_certs` | Client: used if `ca_certificate_provider_instance` is unset ([`UpstreamTlsContext` Validation](#22-upstreamtlscontext-validation)). Server: see [Server Side: `DownstreamTlsContext`](#7-server-side-downstreamtlscontext). |
| `match_subject_alt_names` | Client: used per [Server Identity Verification](#3-server-identity-verification). Server: see [Server Side: `DownstreamTlsContext`](#7-server-side-downstreamtlscontext). Each entry MUST be a valid `StringMatcher`, else NACK. |
| `verify_certificate_spki` | NACK if present. |
| `verify_certificate_hash` | NACK if present. |
| `require_signed_certificate_timestamp` | NACK if true. |
| `crl` | NACK if present. |
| `custom_validator_config` | NACK if present. |
| `trusted_ca` | Ignored. |
| `watched_directory` | Ignored. |
| `allow_expired_certificate` | Ignored. |
| `trust_chain_verification` | Ignored. |

## 5. Certificate Provider Instances

Certificate provider instances are defined in the bootstrap
`certificate_providers` map ([Bootstrap](02-bootstrap.md)):

```jsonc
"certificate_providers": {
  "<instance_name>": {
    "plugin_name": "<plugin implementation name>",
    "config": { /* plugin-specific; optional if the plugin needs none */ }
  }
}
```

The control plane refers to an instance by `instance_name` (and optionally a
`certificate_name`); gRPC maps the name to a locally configured plugin
implementation and configuration. This lets different clients use different
mechanisms for the same instance name. An `instance_name` not present in the
bootstrap NACKs the resource referencing it ([`CommonTlsContext` Validation](#4-commontlscontext-validation)).

A certificate provider delivers, for a given certificate name, an identity
certificate chain and private key, and/or trust roots. Trust roots are
**either** CA certificates **or** a SPIFFE trust bundle map, never both for the
same certificate name. If CA certificates are delivered, X.509 path
validation (RFC 5280 §6) is performed. If a SPIFFE trust bundle map is delivered, SPIFFE
verification is performed and non-SPIFFE peer certificates are rejected
([TLS](../06-security/02-tls.md)); SAN checks ([Server Identity Verification](#3-server-identity-verification)) still
apply. Providers cache the latest material and deliver it to all consumers,
and deliver updates as they occur. Instances with the same plugin and
configuration SHOULD be shared (instantiated once). Until a provider has
delivered the material needed for a handshake, handshakes requiring it fail.

The certificate provider plugin API is internal; applications cannot register
provider implementations.

### 5.1 `file_watcher` Plugin

The only provider plugin is `file_watcher`, which periodically reads PEM files
from the local file system. Configuration:

| Field | Type | Description |
|---|---|---|
| `certificate_file` | string | Path to the PEM identity certificate (chain). |
| `private_key_file` | string | Path to the PEM private key (PKCS). |
| `ca_certificate_file` | string | Path to the PEM CA certificates (trust bundle). |
| `spiffe_trust_bundle_map_file` | string | Path to a SPIFFE trust bundle map (JSON). |
| `refresh_interval` | string (JSON `google.protobuf.Duration`) | How often to re-read the files. Default `"600s"`. |

Validation (failure makes the bootstrap invalid):

- `certificate_file` and `private_key_file` MUST be both set or both unset.
- At least one of `certificate_file`, `ca_certificate_file`, and
  `spiffe_trust_bundle_map_file` MUST be set.

Trust roots:

- If `spiffe_trust_bundle_map_file` is unset, `ca_certificate_file` (if set)
  supplies CA certificates.
- If `spiffe_trust_bundle_map_file` is set, the provider supplies the SPIFFE
  trust bundle map from that file and ignores `ca_certificate_file`.

SPIFFE trust bundle map loading: the file is parsed and validated when read.
If the initial load fails (unreadable file or invalid content), there is no
valid map and handshakes that need it fail. A failed later reload leaves the
previously loaded map in use. An empty map is valid. The supported subset of
the SPIFFE bundle format, and SPIFFE verification, are specified in
[TLS](../06-security/02-tls.md).

## 6. HTTP CONNECT and TLS

> **Introduced by:** [gRFC A86: xDS-Based HTTP CONNECT](https://github.com/grpc/proposal/blob/master/A86-xds-http-connect.md)

The `Http11ProxyUpstreamTransport` transport socket wrapper ([Locating the TLS Context](#21-locating-the-tls-context)) enables
HTTP CONNECT proxying to endpoints that carry a proxy address in their EDS
metadata ([Cluster](04-resources/04-cluster.md),
[ClusterLoadAssignment and LbEndpointCollection](04-resources/05-endpoint.md),
[HTTP CONNECT Proxy Support](../04-client-channel/09-proxy.md)). Its
interaction with security:

- The wrapper is honored regardless of whether XdsChannelCredentials are used.
- The nested `UpstreamTlsContext`, if any, is parsed into the same
  representation as an unwrapped one, and the credential rules of [XdsChannelCredentials and XdsServerCredentials](#1-xdschannelcredentials-and-xdsservercredentials) apply
  unchanged: with XdsChannelCredentials, TLS configuration present → used;
  absent → fallback credentials; without XdsChannelCredentials the TLS
  configuration is ignored.
- TLS (if any) is negotiated end to end with the endpoint through the CONNECT
  tunnel; SNI and SAN checks ([SNI Selection](#23-sni-selection), [Server Identity Verification](#3-server-identity-verification)) refer to the endpoint, not the
  proxy.

## 7. Server Side: `DownstreamTlsContext`

For each accepted connection, the server selects a filter chain
([xDS-Enabled Servers](08-server.md)). That chain's `transport_socket` determines transport
security:

- If `transport_socket` is absent, there is no xDS security configuration and
  the fallback credentials of XdsServerCredentials are used (plaintext if the
  fallback is insecure).
- Otherwise its `typed_config` (after `TypedStruct` unwrapping) MUST be
  `envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext`; any other
  type → NACK. The context is used if the server uses XdsServerCredentials.

`DownstreamTlsContext` validation (failures NACK the Listener):

| Field | Handling |
|---|---|
| `common_tls_context` | Validated per [`CommonTlsContext` Validation](#4-commontlscontext-validation). |
| `common_tls_context.tls_certificate_provider_instance` | Required (the server identity). Absent (including when `common_tls_context` is absent) → NACK. |
| `CertificateValidationContext` | Optional; obtained from `validation_context` or `combined_validation_context.default_validation_context`. If absent, the server does not request a client certificate (TLS, not mTLS). If present, it MUST have `ca_certificate_provider_instance` (the client-certificate trust source), else NACK. |
| `system_root_certs` (in the validation context) | Not supported on servers: if set while `ca_certificate_provider_instance` is unset → NACK. |
| `match_subject_alt_names` (in the validation context) | Not supported on servers → NACK if non-empty. |
| `require_client_certificate` | If true, a CA source (`ca_certificate_provider_instance`) MUST be configured, else NACK. When true, connections without a client certificate that validates against the configured trust source are rejected. When false and a validation context is present, a client certificate is requested and, if presented, validated. |
| `require_sni` | NACK if true (SNI-based virtual hosting does not apply to gRPC, and ignoring it would weaken security). |
| `ocsp_staple_policy` | Any value other than `LENIENT_STAPLING` → NACK. |
| `session_ticket_keys`, `session_ticket_keys_sds_secret_config`, `disable_stateless_session_resumption`, `session_timeout` | Ignored. |
| Other fields | Ignored. |

## 8. API Requirements

- The channel credentials API MUST provide XdsChannelCredentials constructed
  from fallback channel credentials.
- The server credentials API MUST provide XdsServerCredentials constructed
  from fallback server credentials.
- Both MUST be usable with any fallback credentials, including insecure
  credentials.
