> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 10.1 Google Default Credentials

<!-- Sources: L72, L126, A27, A47, doc/grpc_xds_bootstrap_format.md, doc/interop-test-descriptions.md, Google AIP-4110 (Application Default Credentials) -->

Google default credentials are client channel credentials for connecting to
Google services, either directly or through Google's xDS control plane. Each
Google default credentials object combines:

- **Transport security** that is chosen per connection: ALTS channel
  credentials (see [ALTS](../06-security/05-alts.md)) for connections to
  backends that Google's load balancing infrastructure designates as ALTS
  backends, and TLS channel credentials (see [TLS](../06-security/02-tls.md))
  for all other connections ([Transport Selection](#2-transport-selection)).
- **Call credentials** that obtain Google tokens: by default,
  Application Default Credentials
  ([Call Credentials](#3-call-credentials)). The Google call credential
  types are specified in
  [Google Call Credentials](05-google-call-credentials.md).

They behave as composite channel credentials (see
[Security Model: Composite Credentials](../06-security/01-security-model.md#4-composite-credentials)):
the call credentials apply to every RPC on the channel. There are no Google
default server credentials.

Implementations MAY provide Google default credentials.

## 1. Components

| Component | Configuration |
| --- | --- |
| TLS channel credentials | Default TLS client credentials: system root certificates, no client certificate, hostname verification on. |
| ALTS channel credentials | ALTS client credentials with no target service accounts and the default handshaker service address. |
| Call credentials | Application Default Credentials ([Application Default Credentials](#31-application-default-credentials)), unless the application supplies call credentials ([Application-Supplied Call Credentials](#32-application-supplied-call-credentials)). |
| ALTS call credentials | None, unless the application supplies them ([ALTS-Specific Call Credentials](#33-alts-specific-call-credentials)). |

## 2. Transport Selection

The transport security for each connection is chosen when the connection is
established (see
[Subchannels and Connections](../04-client-channel/07-subchannels.md)), from
attributes of the subchannel's address:

```
use_alts(address):
  cluster = address's xDS cluster name attribute
  if cluster is absent: return false
  if cluster starts with "google_cfe_": return false
  if cluster does not start with "xdstp:": return true
  uri = parse cluster as a URI
  if parsing fails: return true
  return not (uri.authority == "traffic-director-c2p.xds.googleapis.com" and
              uri.path starts with "/envoy.config.cluster.v3.Cluster/google_cfe_")
```

- The xDS cluster name attribute is the cluster name that the
  [`xds_cluster_impl`](../09-xds/lb-policies/xds_cluster_impl.md) LB policy
  adds to the addresses below it. Clusters whose names have the
  `google_cfe_` prefix (directly, or as the cluster ID of an `xdstp:` name in
  the `traffic-director-c2p.xds.googleapis.com` authority) are Google Cloud
  front-end clusters and use TLS. Every other xDS cluster is a DirectPath
  cluster and uses ALTS.
- Transport selection for grpclb balancer addresses and for backend
  addresses provided by a grpclb balancer is implementation-defined. The
  `grpclb` LB policy is outside this specification (see
  [Appendix E](../appendices/e-historical.md)).
- If ALTS is selected but ALTS is not available (for example, because the
  process is not running on Google Cloud Platform; see
  [ALTS: Credentials](../06-security/05-alts.md#1-credentials)), the
  connection attempt fails. gRPC MUST NOT fall back to TLS for that
  connection.
- The connection's security level and AuthContext are those of the selected
  credentials.

## 3. Call Credentials

### 3.1 Application Default Credentials

By default, the call credentials are Google Application Default Credentials
(ADC), as specified in
[Google Call Credentials: Application Default Credentials](05-google-call-credentials.md#2-application-default-credentials).

ADC is looked up when the Google default credentials are created. If no
credentials are found, an implementation either fails creation of the Google
default credentials, or creates them and fails every RPC that uses them with
`UNAUTHENTICATED`. In either case, gRPC MUST NOT send RPCs without call
credentials.

### 3.2 Application-Supplied Call Credentials

> **Introduced by:** [gRFC L72: Allow Call Credentials to be Specified in `grpc_google_default_credentials_create`](https://github.com/grpc/proposal/blob/master/L72-core-google_default_credentials-extension.md)

The application MAY supply call credentials when it creates Google default
credentials. They are used instead of ADC, and ADC is not looked up.

### 3.3 ALTS-Specific Call Credentials

> **Introduced by:** [gRFC L126: C-core: Support ALTS Hard Bound Call Credentials in Google Default Credentials](https://github.com/grpc/proposal/blob/master/L126-core-add-alts-google-call-credentials.md)

The application MAY also supply a second set of call credentials for ALTS
connections. If it does, for each RPC gRPC checks the
`transport_security_type` of the connection the RPC uses (see
[Security Model: Standard Properties](../06-security/01-security-model.md#62-standard-properties)):

- If it is `alts`, only the ALTS-specific call credentials are used.
- Otherwise, only the call credentials of
  [Application Default Credentials](#31-application-default-credentials) or
  [Application-Supplied Call Credentials](#32-application-supplied-call-credentials)
  are used.

The minimum security level of the combination is the higher of the two
credentials' minimum security levels.

Instead of supplying ALTS-specific call credentials, the application MAY ask
gRPC to create them. If it does and ADC resolves to compute engine
credentials, the ALTS-specific call credentials are ALTS hard-bound compute
engine credentials
([Google Call Credentials: ALTS Hard-Bound Compute Engine Credentials](05-google-call-credentials.md#31-alts-hard-bound-compute-engine-credentials)).
Otherwise no ALTS-specific call credentials are used.

## 4. xDS Bootstrap Channel Credentials Type `google_default`

> **Introduced by:** [gRFC A27: xDS-Based Global Load Balancing](https://github.com/grpc/proposal/blob/master/A27-xds-global-load-balancing.md)

An implementation that provides Google default credentials and xDS support
SHOULD register the xDS bootstrap channel credentials type `google_default`
(see [Bootstrap: XdsServer Object](../09-xds/02-bootstrap.md#41-xdsserver-object)):

```json
{ "type": "google_default" }
```

- The type takes no configuration. A `config` field, if present, is
  ignored. All `google_default` entries are equal for XdsServer identity.
- The xDS channel uses Google default credentials with ADC
  ([Application Default Credentials](#31-application-default-credentials)).
  Because the xDS channel's addresses carry no grpclb or xDS cluster name
  attributes, its connections use TLS.

Because the call credentials carry OAuth tokens, gRPC sends load reports
only to LRS servers that are configured in the bootstrap, never to a server
named only by the control plane (see
[Load Reporting (LRS)](../09-xds/10-load-reporting.md)).

## 5. Compute Engine Channel Credentials

Compute engine channel credentials are Google default credentials whose call
credentials are compute engine call credentials
([Google Call Credentials: Compute Engine Credentials](05-google-call-credentials.md#3-compute-engine-credentials)),
supplied as in [Application-Supplied Call Credentials](#32-application-supplied-call-credentials).
They use the same transport selection and do not look up ADC. They are
intended for processes that run on Google Compute Engine; elsewhere every
RPC fails because the token cannot be fetched.

## 6. API Requirements

If the implementation provides Google default credentials:

- The credentials API MUST provide a way to create Google default channel
  credentials.
- It MUST let applications supply call credentials to use instead of ADC
  ([Application-Supplied Call Credentials](#32-application-supplied-call-credentials)).
- It MUST let applications supply ALTS-specific call credentials
  ([ALTS-Specific Call Credentials](#33-alts-specific-call-credentials)).
- It MAY provide a way to create compute engine channel credentials
  ([Compute Engine Channel Credentials](#5-compute-engine-channel-credentials)).
  Compute engine call credentials
  ([Google Call Credentials: Compute Engine Credentials](05-google-call-credentials.md#3-compute-engine-credentials))
  MUST be available, so that applications can build them as in that section.
