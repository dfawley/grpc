> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 6.1 TLS

<!-- Sources: A29 (generic certificate provider, SAN matching, file_watcher), A69, A81 (secure naming), A87, A101 (generic SNI parts), A107, A120, L127, doc/grpc_xds_bootstrap_format.md (file_watcher config), doc/ssl-performance.md (informative), include/grpc/grpc_security_constants.h -->

This section specifies TLS channel and server credentials. The same TLS
machinery underlies xDS credentials. For how xDS configures it, see
[xDS Security](../09-xds/security.md). TLS handshake and private key
offload metrics are specified in
[Metric Catalog](../08-observability/metrics.md).

## 1. Protocol Requirements

- **TLS versions.** The default minimum is TLS 1.2 and the default maximum is
  TLS 1.3. Versions below TLS 1.2 MUST NOT be negotiated. The credentials API
  MUST let applications raise the minimum or lower the maximum within that
  range.
- **HTTP/2 over TLS.** Connections MUST meet the TLS requirements of HTTP/2
  (RFC 9113 §9.2). In particular, TLS compression and renegotiation MUST NOT be
  used. TLS 1.2 connections MUST use a cipher suite allowed by HTTP/2, with
  ephemeral key exchange (ECDHE).
- **ALPN.** The client MUST offer the ALPN protocol `h2`. The server MUST
  select `h2`. If the handshake does not end with `h2` negotiated, both client
  and server MUST fail the handshake. The connection is then not used.
- **Security level.** A TLS connection has security level
  `PRIVACY_AND_INTEGRITY` (see [Security](README.md)).

## 2. Server Name Indication (SNI)

The client sends SNI in the ClientHello as follows:

1. If the TLS credentials have an SNI override, the override is used. An empty
   override means no SNI is sent.
2. Otherwise, if the channel uses xDS credentials, the SNI is chosen from xDS
   configuration (see [xDS Security](../09-xds/security.md)).
3. Otherwise, the SNI is the host part of the channel's default authority,
   with any port removed (see [Security](README.md), [Security: Authority and Authority Override](README.md#7-authority-and-authority-override)).

In every case, if the chosen name is an IP address literal, SNI MUST NOT be
sent (RFC 6066 §3). An empty name means no SNI.

On the server, the SNI the client sent (if any) is recorded in the
`ssl_requested_server_name` AuthContext property. A TLS server MAY hold more
than one identity key/certificate pair. If it does, it SHOULD present a
certificate that matches the client's SNI. If no certificate matches, or the
client sent no SNI, it presents the first configured pair.

## 3. Server Certificate Verification

By default, a TLS client verifies the server in two steps. Both MUST succeed
for the handshake to succeed.

1. **Chain verification.** The server's certificate chain MUST chain to a
   trusted root. The roots come from the root certificate provider
   ([Certificate Providers](#6-certificate-providers)). If none is configured, the system's default trust store is
   used. Alternatively, when the root provider supplies a SPIFFE trust bundle
   map, SPIFFE verification ([SPIFFE Trust Bundle Map Verification](#10-spiffe-trust-bundle-map-verification)) is used. If a CRL provider is
   configured, revocation checking ([Certificate Revocation (CRL)](#9-certificate-revocation-crl)) is part of this step.
2. **Hostname verification.** The leaf certificate MUST match the *target
   name*. The target name is the channel's default authority with any port
   removed. If the TLS credentials have an SNI override, the target name is
   the override value. Matching follows RFC 6125:
   - If the target name is an IP address, it MUST equal an IP-address SAN.
     Addresses are compared in binary form.
   - Otherwise, it MUST match a DNS SAN. Comparison is case-insensitive. A
     wildcard is allowed only as the whole left-most label (`*.example.com`).
     It matches exactly one label and never matches IP addresses.
   - The subject CN MUST NOT be used for matching.
     <!-- REVIEW(divergence) [TLS-1]: Java: falls back to the most specific subject CN when the cert has no DNS SANs and the target is not an IP (netty uses JDK endpoint identification "HTTPS"; okhttp OkHostnameVerifier.verifyHostName); Go: no CN fallback (crypto/x509 VerifyHostname); C++: falls back to the CN only when the cert has no SANs of any type and the target is not an IP (tsi_ssl_peer_matches_name in tsi/ssl_transport_security.cc). Spec says no CN fallback. This is a minority behavior (Go only), but it was kept because CN matching is deprecated (RFC 9525 forbids it; CA/B Forum requires SANs) and Java and C++ also differ from each other on when they fall back. Owner to decide. -->

The TLS credentials API MUST let the application:

- turn off hostname verification, replacing it with a custom verifier
  ([Custom Verification](#8-custom-verification)), and
- turn off chain verification on the client, again for use with a custom
  verifier. This is dangerous. It MUST NOT be the default.

## 4. Per-RPC Authority Verification

An RPC's `:authority` can differ from the name its connection was verified
against: through a per-call authority override, or through xDS authority
rewriting (see [Security](README.md), [Security: Authority and Authority Override](README.md#7-authority-and-authority-override)). In that case TLS
credentials MUST, by default, check before the RPC is sent on the connection
that the server's leaf certificate is valid for the RPC's authority. The check
uses the same hostname matching rules as [Server Certificate Verification](#3-server-certificate-verification), applied to the
authority with any port removed.

- If the check fails, the RPC fails with status `UNAVAILABLE` and a message
  saying the authority does not match the server certificate. The RPC is not
  sent.
  <!-- REVIEW(divergence) [TLS-2]: Java: UNAVAILABLE (netty X509AuthorityVerifier / NettyClientHandler; okhttp OkHttpClientTransport.verifyAuthority); Go: UNAVAILABLE (internal/transport/http2_client.go, CallAuthority validation); C++: UNAUTHENTICATED (SslCheckCallHost in credentials/transport/tls/ssl_utils.cc, "call host does not match SSL server name"). statuscodes.md lists "Invalid host set in :authority metadata" under UNAUTHENTICATED, which matches C++. Spec says UNAVAILABLE (majority). -->
- If the RPC's authority equals the connection's target name, no extra check
  is needed.
- Implementations MAY cache results per (connection, authority).
- The TLS credentials API MUST provide an option to disable this check. When a
  custom verifier replaces hostname verification, the per-RPC check SHOULD be
  delegated to that verifier or disabled.

Credentials that do no hostname verification, such as insecure credentials or
xDS credentials using SAN matching, do not do this check.

## 5. Client Certificates and Mutual TLS

A TLS client sends a certificate only if an identity certificate provider is
configured and the server requests one. If the server requires a certificate
and the client has none, the handshake fails.

A TLS server has a *client certificate request type*:

| Request type | Requests a client cert | Requires one | Verifies it |
|--------------|------------------------|--------------|-------------|
| `DONT_REQUEST_CLIENT_CERTIFICATE` (default) | No | No | n/a |
| `REQUEST_CLIENT_CERTIFICATE_BUT_DONT_VERIFY` | Yes | No | No |
| `REQUEST_CLIENT_CERTIFICATE_AND_VERIFY` | Yes | No | Yes, if one is presented |
| `REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_BUT_DONT_VERIFY` | Yes | Yes | No |
| `REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY` | Yes | Yes | Yes |

"Verify" means chain verification against the server's root provider (or
SPIFFE verification), plus revocation checking if configured. Hostname
verification does not apply to client certificates. A server that verifies
client certificates MUST have roots configured: there is no default trust
store for client certificates. The verified client certificate fills the
server-side AuthContext (see [Security](README.md)).

A TLS server MUST have an identity (key and certificate chain). Server
credentials creation MUST fail if no identity provider is configured.

## 6. Certificate Providers

### 6.1 Model

TLS credentials get key material from *certificate providers*. There are two
independent roles:

- A **root certificate provider** supplies trust anchors for verifying the
  peer. A trust anchor is either a set of PEM root certificates or a SPIFFE
  trust bundle map ([SPIFFE Trust Bundle Map Verification](#10-spiffe-trust-bundle-map-verification)), never both.
- An **identity certificate provider** supplies one or more identity pairs.
  Each pair is a certificate chain plus either a private key or a private key
  signer ([Private Key Offloading](#11-private-key-offloading)).

TLS credentials are configured with a root provider, an identity provider,
both, or neither, independently. One provider object MAY fill both roles. A
provider MAY serve several named certificates. The credentials select which
root and identity names they watch. The default name is the empty string.

Provider semantics:

- A provider delivers key material to consumers. It does so either by pushing
  updates to registered watchers or by letting consumers fetch the current
  material. A provider caches the latest material it has. Each new watcher
  immediately gets the cached material, if there is any.
- Updates take effect for handshakes that start after the update. Existing
  connections are not affected.
- A provider can report an error for a name, for example when it has never
  loaded valid material. A handshake that needs material the provider cannot
  supply fails.
- Providers with identical configuration MAY be deduplicated and shared.

Defaults when a provider is absent:

| Side | No root provider | No identity provider |
|------|------------------|----------------------|
| Client | Use the system default trust store | Send no client certificate |
| Server | Do not verify client certificates. A request type that verifies is invalid. | Invalid configuration |

### 6.2 In-Memory Provider

The in-memory provider holds key material supplied directly by the
application.

- It is created with optional PEM root certificates and an optional list of
  identity pairs. Each pair is a PEM certificate chain plus either a PEM
  private key or a private key signer.
- It offers thread-safe operations to replace the roots and to replace the
  identity pairs. Each update takes effect for later handshakes and returns an
  error if the new material is invalid.
- It offers a validation operation. Validation checks that the roots are one
  or more valid PEM certificate blocks, that each certificate chain consists
  of valid PEM certificate blocks, and that each PEM private key is a valid PEM
  key block.

An in-memory provider that is created with material and never updated
behaves as a static provider.

### 6.3 File-Watcher Provider

The file-watcher provider reads key material from the local file system and
re-reads it periodically.

| Parameter | Meaning |
|-----------|---------|
| identity certificate file | Path to a PEM certificate chain (leaf first). |
| private key file | Path to the PEM private key for the leaf. |
| root certificate file | Path to PEM root certificates. |
| SPIFFE trust bundle map file | Path to a SPIFFE trust bundle map ([SPIFFE Trust Bundle Map Verification](#10-spiffe-trust-bundle-map-verification)). If set, the root certificate file is ignored, even if the map file fails to load. |
| refresh interval | Time between reads. Default 600 seconds. Values under 1 second are raised to 1 second. |

Validation (configuration errors make provider creation fail):

- The identity certificate file and the private key file MUST be both set or
  both unset.
- At least one of the identity certificate file, root certificate file, or
  SPIFFE trust bundle map file MUST be set.

Behavior:

- The provider reads all configured files when it is created, then once per
  refresh interval.
- When it reads the identity files, the provider MUST make sure the key and
  certificate belong together. It SHOULD detect a concurrent rewrite (for
  example, by checking that the files' modification times did not change
  during the read, and re-reading if they did). It MUST NOT publish a key that
  does not match the leaf certificate.
- Material is published to watchers only when it changes.
- **Initial load failure:** the affected material (roots or identity) is
  unavailable. The provider reports an error for it. Handshakes that need it
  fail until a later read succeeds.
- **Reload failure:** if a later read of a file fails, or its content is
  invalid, the provider logs the error and keeps serving the most recently
  loaded valid material. Roots and identity are handled independently. The
  provider MUST NOT clear previously loaded valid material because a reload
  failed. As an exception, the provider MAY stop serving an identity
  certificate that has expired, or will expire within one refresh interval.

In the xDS bootstrap, this provider is registered under the plugin name
`file_watcher`. Its JSON configuration is in
[xDS Security](../09-xds/security.md).

## 7. TLS Credentials Options Summary

TLS channel credentials:

| Option | Default |
|--------|---------|
| Root certificate provider and root name | System trust store |
| Identity certificate provider and identity name | None |
| Minimum / maximum TLS version | 1.2 / 1.3 |
| Key exchange groups ([Key Exchange Groups](#12-key-exchange-groups)) | Default preference list |
| SNI override ([Server Name Indication (SNI)](#2-server-name-indication-sni)) | None (use the target name) |
| Verify server certificate chain | Enabled |
| Hostname verification | Enabled (built-in verifier) |
| Custom verifier ([Custom Verification](#8-custom-verification)) | None |
| Per-RPC authority check ([Per-RPC Authority Verification](#4-per-rpc-authority-verification)) | Enabled |
| CRL provider and undetermined-status policy ([Certificate Revocation (CRL)](#9-certificate-revocation-crl)) | None |

TLS server credentials:

| Option | Default |
|--------|---------|
| Identity certificate provider and identity name | Required |
| Root certificate provider and root name | None |
| Client certificate request type | `DONT_REQUEST_CLIENT_CERTIFICATE` |
| Minimum / maximum TLS version | 1.2 / 1.3 |
| Key exchange groups | Default preference list |
| Custom verifier | None |
| CRL provider and undetermined-status policy | None |

Implementations MAY offer a TLS key-log option for debugging (writing session
secrets to a file). It MUST be off by default, and it MUST NOT be used in
production.

## 8. Custom Verification

TLS credentials MUST support an application-supplied **custom verifier** on
both client and server. The verifier runs after the built-in chain
verification, unless the application turned chain verification off. It runs
in addition to, or instead of, the built-in hostname verification.

The verifier gets a *verification request* with at least:

- the target name (client side), or the requested SNI (server side);
- the peer leaf certificate and the full peer certificate chain;
- the leaf's subject, common name, and SANs, grouped by type (DNS, URI, email,
  IP);
- the verified chain, if chain verification ran;
- the negotiated key exchange group ([Key Exchange Groups](#12-key-exchange-groups)).

The verifier returns success, or failure with an error message. It MAY finish
asynchronously. If it fails, the handshake fails. gRPC MUST be able to cancel
a pending asynchronous verification, for example on shutdown or when the
connection attempt is abandoned.

gRPC provides a built-in hostname verifier that implements [Server Certificate Verification](#3-server-certificate-verification). A
custom verifier can run alongside it or replace it.

## 9. Certificate Revocation (CRL)

TLS credentials MAY be configured with a **CRL provider**. Revocation checking
then covers every certificate in the peer's verified chain except the trust
anchor.

### 9.1 CRL Provider Interface

```
interface CrlProvider {
  // Returns the CRL issued by the issuer of `cert`, or null if the
  // provider has no CRL for that issuer. Returned CRLs are read-only.
  // null (no CRL) is different from an empty CRL (nothing revoked).
  Crl GetCrl(CertificateInfo cert)
}
```

`CertificateInfo` gives at least the certificate's issuer name. A provider
MUST be safe to use from many connections at once. The same provider is
expected to be shared by all handshakes of the credentials it is configured
on. Providers supply CRLs only. Verification is done by gRPC as described
below. CRL distribution points are not used to fetch CRLs. Application-defined
providers MAY implement any lookup policy.

### 9.2 Revocation Status

For each certificate checked, gRPC computes one of:

| Status | Meaning |
|--------|---------|
| `Unrevoked` | A valid CRL from the certificate's issuer exists and does not list the certificate. |
| `Revoked` | A valid CRL from the certificate's issuer lists the certificate's serial number. |
| `Undetermined` | No CRL was found for the issuer, or no CRL could be validated. |

The credentials have a policy for `Undetermined`: treat it as `Revoked` (fail
closed) or as `Unrevoked` (fail open). The application MUST be able to choose.
If any certificate in the chain ends up `Revoked`, the handshake fails.

```
RevocationStatus Check(cert, issuer, opts):
  crl = opts.crlProvider.GetCrl(cert)
  status = (crl == null) ? Undetermined : CheckAgainstCrl(crl, cert, issuer)
  if status == Undetermined:
    return opts.failOnUndetermined ? Revoked : Unrevoked
  return status
```

### 9.3 Supported Subset of RFC 5280 §6.3.3

gRPC supports only complete, direct CRLs (the CRL issuer is the certificate's
issuer):

| RFC 5280 §6.3.3 step | gRPC behavior |
|----------------------|---------------|
| (a) Update local CRL cache | Not done by gRPC. The CRL provider supplies CRLs. Only complete CRLs are supported. A CRL past its `nextUpdate` time is still used. |
| (b) Verify issuer and scope | The CRL issuer MUST equal the certificate's issuer, and the issuer certificate MUST have the `cRLSign` key usage bit set. Issuing distribution points are not supported. |
| (c) Delta CRLs | Not supported. |
| (d), (e) Reasons mask | Not supported. |
| (f) CRL issuer path | Not needed: only direct CRLs, so the CRL issuer is the certificate's issuer in the verified chain. |
| (g) Signature validation | The CRL signature MUST validate with the issuer's public key. |
| (h), (i) Delta CRL processing | Not supported. |
| (j) Revocation check | If the certificate's serial number is listed, the status is `Revoked`. |
| (k) `removeFromCRL` | Not supported. Un-revocation does not exist. A new certificate must be issued. |
| (l) Reason codes | Not reported. Only revoked, unrevoked, or undetermined matters. |

OCSP (including stapling) is not supported.

### 9.4 Static CRL Provider

The static provider is created from a list of CRLs (each given as the encoded
CRL content). It indexes them by issuer and never changes. Creation fails if
any CRL cannot be parsed.

### 9.5 Directory-Reloading CRL Provider

The directory-reloading provider reads every file in a directory and parses
each one as a CRL. It re-reads the directory periodically.

Parameters: directory path, refresh interval, and an optional error callback.

- CRLs are indexed by issuer. File names carry no meaning.
- The first read happens synchronously when the provider is created, so CRLs
  are loaded before any handshake uses the provider. Errors in the first read
  do not make creation fail. They are handled like errors in any later read.
- Later reads run asynchronously, off the RPC path.
- If every file in the directory was read and parsed, the directory is the
  exact truth: CRLs that are no longer present are removed.
- If any file fails to read or parse, the update is best-effort. CRLs that
  parsed are added or replaced. No CRL is removed, because the issuer of an
  unreadable file is unknown. Each bad file affects only itself, not the rest
  of the update.
- The error callback, if set, is called at most once per reload pass. It gets
  one error describing every file that failed and why. The callback only
  reports. It does not affect provider behavior. Decisions about missing or
  stale CRLs are made through the `Undetermined` policy.
- Applications MUST update the directory atomically, for example by writing
  to a temporary path and renaming. If they do not, the provider's view of a
  partly written directory is unspecified.

## 10. SPIFFE Trust Bundle Map Verification

A root provider MAY supply a **SPIFFE trust bundle map** instead of root
certificates. The map goes from SPIFFE trust domain to a set of X.509 root
certificates. When a map is supplied, peer certificates are verified like
this. Non-SPIFFE peer certificates are rejected.

1. The peer leaf certificate MUST be a well-formed SPIFFE leaf. It MUST have
   exactly one URI SAN, and that URI MUST be a valid SPIFFE ID:
   - the scheme is `spiffe://` (compared case-insensitively);
   - the URI is at most 2048 characters long, contains only ASCII, and has
     no query (`?`) or fragment (`#`);
   - the trust domain is non-empty, at most 255 characters, and contains
     only `a-z`, `0-9`, `.`, `-`, `_`;
   - the path is empty, or `/`-separated segments that are each non-empty,
     not `.` or `..`, and contain only `a-z`, `A-Z`, `0-9`, `.`, `-`, `_`;
     the URI does not end with `/`.
2. The trust domain of the peer's SPIFFE ID is looked up in the map. If it is
   not there, the certificate is rejected.
3. The peer chain is verified with the TLS library's standard verification,
   using that trust domain's certificates as the roots.

Any configured SAN matching (for example from xDS) and revocation checking
still apply.

### 10.1 Bundle Map Format

The map file is JSON. gRPC supports a subset of the SPIFFE bundle format:

```json
{
  "trust_domains": {
    "example.com": {
      "spiffe_sequence": 12035488,
      "keys": [
        { "kty": "RSA", "use": "x509-svid", "x5c": ["<base64 DER certificate>"] }
      ]
    }
  }
}
```

- `trust_domains` (required): an object mapping each trust domain name to a
  JWK set. Each key MUST be a valid trust domain (rules above).
- In each JWK set, only `keys` and `spiffe_sequence` are used. `keys` is
  required.
- In each key, only `kty`, `use`, and `x5c` are used:
  - `use` MUST be `x509-svid`;
  - `kty` MUST be `RSA` or `EC`;
  - `x5c` MUST have exactly one element: a base64 DER certificate that parses
    as exactly one X.509 certificate.
- If any entry of a trust domain's bundle is invalid, the whole map is
  invalid. gRPC does not skip individual bad JWK entries.
- An empty `trust_domains` object is a valid, empty map. Every peer is then
  rejected.

### 10.2 Loading Rules

- If the first load fails (file unreadable, invalid JSON, or invalid entries),
  there is no valid map, and handshakes that need it fail.
- If a later reload fails, the in-memory map does not change.

## 11. Private Key Offloading

An identity pair MAY hold a **private key signer** instead of a private key.
The TLS handshake then never needs the key material.

### 11.1 Constraints

- Only signing is offloaded. Offloading is supported only with TLS 1.3, and
  with TLS 1.2 cipher suites that use ECDHE key exchange. Private key
  decryption (static RSA key exchange) is not supported.
- The certificate chain configured with the signer MUST match the signer's
  key.
- Implementations whose TLS library cannot offload MUST reject the
  configuration when it is supplied (for example, when the provider is
  updated). They MUST NOT fail later during handshakes.

### 11.2 Signer Interface

```
interface PrivateKeySigner {
  // Signs `data` with `algorithm`. Either returns a result
  // synchronously (signature bytes or an error), or returns a handle
  // and later calls `onComplete` exactly once with the signature or an
  // error. `onComplete` MUST NOT be called before Sign returns.
  SyncResultOrHandle Sign(bytes data, SignatureAlgorithm algorithm,
                          Callback onComplete)

  // Cancels a pending asynchronous Sign. The signer must release any
  // resources for the operation. gRPC calls this when the handshake is
  // abandoned (for example on shutdown or deadline).
  void Cancel(Handle handle)
}
```

- `data` is the input to sign, as the implementation's TLS library defines
  it: either the unhashed message, which the signer hashes as `algorithm`
  requires, or the precomputed digest of the message. `algorithm` is always
  passed, so the signer knows the signature scheme, including the hash and
  padding.
- Signers MUST be thread-safe. One signer can be used by many concurrent
  handshakes.
- If signing fails, or the callback reports an error, the handshake fails.

Supported signature algorithms (TLS SignatureScheme names, RFC 8446):

| Algorithm |
|-----------|
| `rsa_pkcs1_sha256`, `rsa_pkcs1_sha384`, `rsa_pkcs1_sha512` |
| `ecdsa_secp256r1_sha256`, `ecdsa_secp384r1_sha384`, `ecdsa_secp521r1_sha512` |
| `rsa_pss_rsae_sha256`, `rsa_pss_rsae_sha384`, `rsa_pss_rsae_sha512` |

A signer is supplied through an identity certificate provider, typically the
in-memory provider ([In-Memory Provider](#62-in-memory-provider)). The roots can come from a separate root
provider.

## 12. Key Exchange Groups

The client offers an ordered list of key exchange groups (TLS "supported
groups", RFC 8446 §4.2.7), and the server picks one. gRPC TLS stacks MUST
*prefer* the post-quantum hybrid group `X25519MLKEM768` over groups that are
not post-quantum. They MUST still allow falling back to classical groups for
interoperability.

- If the TLS library's default list already puts a post-quantum group first,
  gRPC uses the library default.
- Otherwise, gRPC's default preference list is, in order:
  `X25519MLKEM768`, `X25519`, `P-256`, `P-384`, `P-521`. Groups the TLS
  library does not support are left out.
- The TLS credentials API (client and server) MUST let the application set
  the ordered list of key exchange groups, replacing the default. This lets
  applications opt out of post-quantum key exchange.
- The negotiated group is exposed in the AuthContext as
  `ssl_negotiated_key_exchange_group` (see [Security](README.md)) and in
  the custom verification request ([Custom Verification](#8-custom-verification)).

## 13. API Requirements

- The credentials API MUST provide TLS channel credentials and TLS server
  credentials with the options in [TLS Credentials Options Summary](#7-tls-credentials-options-summary).
- It MUST let applications configure root and identity certificate providers
  separately.
- It MUST provide the in-memory provider (with thread-safe updates and
  validation) and the file-watcher provider (with a refresh interval and an
  optional SPIFFE trust bundle map file).
- It MUST let applications set the minimum and maximum TLS version.
- It MUST let applications set the SNI override, including suppressing SNI.
- The server credentials API MUST let applications set the client
  certificate request type.
- It MUST let applications install a custom verifier that may finish
  asynchronously. It MUST let applications turn off hostname verification
  and, on the client, chain verification.
- It MUST provide an option to disable the per-RPC authority check.
- It MUST let applications configure a CRL provider and the `Undetermined`
  policy. It MUST provide the static and directory-reloading CRL providers,
  and it MUST let applications implement their own CRL provider.
- It MUST let applications supply a private key signer instead of a private
  key, where the TLS library supports it.
- It MUST let applications set the ordered list of key exchange groups.
- The AuthContext MUST expose the standard TLS properties in
  [Security](README.md), including the negotiated key exchange group.
