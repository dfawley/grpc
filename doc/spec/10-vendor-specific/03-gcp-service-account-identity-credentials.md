> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 10.3 GCP Service Account Identity Credentials

<!-- Sources: A83 (call credentials part), doc/http-grpc-status-mapping.md -->

> **Introduced by:** [gRFC A83: xDS GCP Authentication Filter](https://github.com/grpc/proposal/blob/master/A83-xds-gcp-authn-filter.md)

These call credentials get a service account identity JWT from the GCP metadata
server, so they work only on Google Cloud. They are token-fetching credentials:
caching, refresh, backoff, and the handling of RPCs waiting for a token follow
[Call Credentials: Token-Fetching Credentials](../06-security/03-call-credentials.md#3-token-fetching-credentials).
They are not specific to xDS. (The xDS GCP authentication HTTP filter uses
them; see [GCP Authentication Filter](04-gcp-authentication-filter.md).) The
other Google call credential types are listed in
[Google Call Credentials](05-google-call-credentials.md).

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
    mapping (see [gRPC over HTTP/2](../03-wire-protocol/01-http2.md)), meaning 429, 502, 503,
    or 504: `UNAVAILABLE`.
  - Any other non-200 HTTP status: `UNAUTHENTICATED`.
  - A 200 response whose body has no readable `exp`: `UNAUTHENTICATED`.
- **Metadata:** `authorization: Bearer <jwt>`.
- **Minimum security level:** `PRIVACY_AND_INTEGRITY`.

## API Requirements

- An implementation that provides these credentials MUST provide a way to
  create them from an audience.
