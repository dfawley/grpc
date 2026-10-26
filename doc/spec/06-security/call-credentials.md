> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 6.2 Call Credentials

<!-- Sources: L62, A54, A83 (call credentials part), A97 (call credentials part), doc/server_side_auth.md, doc/http-grpc-status-mapping.md, doc/connection-backoff.md -->

Call credentials attach per-RPC authentication metadata, such as bearer
tokens, to RPCs. This section defines how call credentials behave in general,
and three built-in types. The security model, composition, and security
levels are in [Security](README.md).

## 1. General Behavior

### 1.1 Invocation Timing

- Call credentials are invoked once per RPC **attempt**: for the initial
  attempt, each retry or hedged attempt, and each transparent retry.
- Invocation happens **after the LB pick**, once the attempt has been assigned
  to a connection. This lets the client check the connection's security level
  against the credential's minimum security level before invoking the
  credential (see [Security](README.md), [Call Credential Minimum Security Level](README.md#51-call-credential-minimum-security-level)). If the check
  fails, the credential is not invoked.
- Interceptors and xDS HTTP filters that run before the LB pick MUST NOT add
  credential-derived secrets to the RPC directly. To attach credentials, they
  attach a call credentials object to the RPC. The object is then invoked after
  the pick.
- While the credential is computing metadata, the attempt waits. The RPC
  deadline still applies. If the RPC is cancelled or its deadline expires,
  gRPC abandons the pending invocation. The credential SHOULD be notified, if
  the API allows it, so it can stop work.
- Headers are not sent on the connection until all call credentials for the
  attempt have finished.

### 1.2 Inputs

When invoked, a call credential gets:

| Input | Definition |
|-------|------------|
| Service URL | `"https://" + host + "/" + service`. `host` is the RPC's authority, with the port removed if it is `443`. `service` is the full service name: the method's path without the leading `/` and without the final `/` and method name. Example: authority `example.com:443`, method `/pkg.Svc/Get` gives `https://example.com/pkg.Svc`. |
| Method name | The method name (the last path component, for example `Get`). Implementations MAY also give the full method path. |
| Authority | The RPC's authority. |
| Security level | The security level of the connection chosen for the attempt. |
| AuthContext | The AuthContext of that connection (see [Security](README.md), [Security: AuthContext and Peer Identity](README.md#6-authcontext-and-peer-identity)). |

### 1.3 Results

A call credential either returns metadata or fails with a status.

- **Metadata.** The entries are added to the attempt's request headers. Keys
  and values MUST be valid custom metadata (see
  [gRPC over HTTP/2](../03-wire-protocol/http2.md)). Metadata from
  several call credentials (channel-level, per-call, or composite components)
  is combined. Duplicate keys keep all values.
- **Failure.** The attempt fails with the returned status, after the status
  code rewrite below. The call credential is treated as part of the control
  plane. If the code is one of `OK`, `INVALID_ARGUMENT`, `NOT_FOUND`,
  `ALREADY_EXISTS`, `FAILED_PRECONDITION`, `ABORTED`, `OUT_OF_RANGE` or
  `DATA_LOSS`, gRPC MUST change it to `INTERNAL`. The new message MUST make
  clear that a bug happened and MUST include the original code and message.
  Retry-policy status matching (see
  [Retries](../04-client-channel/retries.md)) uses the rewritten status.
- A credential that cannot produce metadata for an expected, recoverable
  reason (for example, a token endpoint is temporarily unreachable) SHOULD
  fail with `UNAVAILABLE`. One that is rejected by its token issuer SHOULD
  fail with `UNAUTHENTICATED`.

### 1.4 Minimum Security Level

Every call credential has a minimum security level (see
[Security](README.md), [Call Credential Minimum Security Level](README.md#51-call-credential-minimum-security-level)). All built-in types in this section
require `PRIVACY_AND_INTEGRITY`. On a connection with a lower level, the
attempt fails with `UNAUTHENTICATED` and the credential is not invoked.

## 2. Access Token Credentials

Access token credentials are created with a fixed OAuth2 access token string.
On each invocation they return one metadata entry:

```
authorization: Bearer <token>
```

There is exactly one space after `Bearer`. Minimum security level:
`PRIVACY_AND_INTEGRITY`. The credentials never fail.

## 3. Token-Fetching Credentials

The GCP service account identity credentials ([GCP Service Account Identity Credentials](#4-gcp-service-account-identity-credentials)) and the JWT
token file credentials ([JWT Token File Credentials](#5-jwt-token-file-credentials)) both obtain a JWT from a source,
cache it, and attach it as a bearer token. They share the behavior in this
section. "Fetch" means an HTTP request or a file read, depending on the type.

### 3.1 Parameters

| Parameter | Value |
|-----------|-------|
| Expiration skew | 30 seconds |
| Refresh window | 1 minute |
| Backoff | The connection backoff parameters defined in [Subchannels](../04-client-channel/subchannels.md) |

### 3.2 Token Cache

- When a fetch succeeds, the credential reads the JWT's `exp` claim. It
  base64url-decodes the second dot-separated part of the token, parses it as
  a JSON object, and reads `exp` as a NumericDate (seconds since the epoch).
  The token is otherwise not validated. Full RFC 7519 validation is the
  server's job.
- The *effective expiration* is `exp − 30 s`. All logic below uses the
  effective expiration, never `exp` itself.
- A token is *valid* while now < effective expiration.
- If `exp` cannot be read (the token is malformed), the fetch counts as a
  failure with status `UNAUTHENTICATED`, and the cache is not updated.

### 3.3 Algorithm

State: `cached_token` (optional), `fetch_in_progress` (bool), `queued`
(the list of attempts waiting for a fetch), `backoff` (the backoff state),
`backoff_timer_active` (bool), `last_failure_status`.

```
on invocation for an attempt:
  if cached_token is valid:
    if (cached_token.effective_expiration - now) < refresh_window
        and not fetch_in_progress and not backoff_timer_active:
      start_fetch()                  # prefetch; attempt is not delayed
    return metadata("authorization", "Bearer " + cached_token)
  # no valid token
  if backoff_timer_active:
    fail attempt with last_failure_status
    return
  add attempt to queued
  if not fetch_in_progress:
    start_fetch()

on fetch completion(result):
  fetch_in_progress = false
  if result is success with readable exp:
    cached_token = result.token
    backoff.reset()
    complete every queued attempt with metadata("authorization", "Bearer " + token)
  else:
    last_failure_status = status_for(result)
    fail every queued attempt with last_failure_status
    start backoff timer for backoff.next_delay(); backoff_timer_active = true

on backoff timer expiry:
  backoff_timer_active = false       # no fetch started here
```

Rules from the algorithm:

- At most one fetch is in progress per credential instance. Every attempt
  that arrives while a fetch is in progress and has no valid token is queued.
  All of them get the result of that fetch.
- Prefetching starts a fetch when the cached token is still valid but will
  expire within the refresh window. Attempts keep using the cached token
  meanwhile, so refreshes do not cause periodic latency spikes.
- Fetches are started only by attempts. When the backoff timer expires, no
  fetch starts until another attempt needs one, so an idle channel does no
  work.
- During backoff, an attempt with no valid token fails at once with the
  status of the last failed fetch.
- A successful fetch resets the backoff state.
- If a prefetch fails while the cached token is still valid, attempts keep
  using the cached token until it expires. A new fetch can start once the
  backoff timer expires.

## 4. GCP Service Account Identity Credentials

These credentials get a service account identity JWT from the GCP metadata
server. They are not specific to xDS. (The xDS GCP authentication HTTP filter
uses them. See [xDS HTTP Filters](../09-xds/http-filters.md).)

- **Parameter:** `audience` (string). It is placed in the token request.
- **Fetch:** an HTTP GET request to
  ```
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=<audience>
  ```
  with the request header `Metadata-Flavor: Google`.
- **Success:** an HTTP 200 response. The body is the JWT.
- **Failure status:**
  - If the request fails with no HTTP status (connection error, I/O error,
    timeout): `UNAVAILABLE`.
  - If the HTTP status maps to `UNAVAILABLE` under the HTTP-to-gRPC status
    mapping (see [gRPC over HTTP/2](../03-wire-protocol/http2.md)), meaning 429, 502, 503,
    or 504: `UNAVAILABLE`.
  - Any other non-200 HTTP status: `UNAUTHENTICATED`.
  - A 200 response whose body has no readable `exp`: `UNAUTHENTICATED`.
- **Metadata:** `authorization: Bearer <jwt>`.
- **Minimum security level:** `PRIVACY_AND_INTEGRITY`.

## 5. JWT Token File Credentials

These credentials read a JWT from a local file. They are not specific to xDS.
The xDS bootstrap can configure them for connections to xDS servers, as call
credentials type `jwt_token_file` (see [Bootstrap](../09-xds/bootstrap.md)).

- **Parameter:** the path to the token file.
- **Fetch:** read the whole file. The content is the JWT.
- **Failure status:**
  - The file cannot be read: `UNAVAILABLE`.
  - The content has no readable `exp`: `UNAUTHENTICATED`.
- **Metadata:** `authorization: Bearer <jwt>`.
- **Minimum security level:** `PRIVACY_AND_INTEGRITY`.

Because fetches happen only on demand ([Token-Fetching Credentials](#3-token-fetching-credentials)), the file is re-read
when the cached token is about to expire or has expired. Replacing the file
takes effect at the next fetch.

## 6. API Requirements

- The credentials API MUST provide a way to create access token credentials
  from a token string.
- It MUST provide a way to create GCP service account identity credentials
  from an audience.
- It MUST provide a way to create JWT token file credentials from a file path.
- It MUST let applications implement their own call credentials. Such a
  credential gets the inputs in [Inputs](#12-inputs), returns metadata or a failure
  status, may finish asynchronously, and declares its minimum security level.
- The call credentials API MUST allow combining call credentials (composite
  call credentials) and attaching them per channel or per call (see
  [Security](README.md)).
