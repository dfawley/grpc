> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 10.5 Google Call Credentials

<!-- Sources: L72, L126, doc/interop-test-descriptions.md, Google AIP-4110 (Application Default Credentials), AIP-4111 (self-signed JWT), AIP-4112 (service account keys), AIP-4115 (credentials for Google Cloud virtual environments), AIP-4117 (external account credentials) -->

This document lists the call credentials that obtain Google-issued tokens for
calling Google services. Each type is described briefly: what it is, where
its token comes from, what metadata it attaches, and its minimum security
level. Channel credentials for Google services, which use these call
credentials, are specified in
[Google Default Credentials](01-google-default-credentials.md).

Implementations MAY provide any of these credentials. An implementation that
provides one MUST give it the behavior described here.

## 1. Common Behavior

The rules in this section apply to every type in this document unless its
section says otherwise.

- **General behavior.** These are call credentials as specified in
  [Call Credentials](../06-security/03-call-credentials.md): invocation
  timing, inputs, results, and the status code rewrite apply unchanged.
- **Tokens and token sources are defined by Google.** The credential file
  formats, OAuth 2.0 and JWT token formats, token endpoints, token exchange
  and refresh flows, and the lookup procedure of Application Default
  Credentials are defined by Google's public authentication documents (the
  AIP-4100 series, starting at
  [AIP-4110: Google Application Default Credentials](https://google.aip.dev/auth/4110)),
  not by gRPC. This specification does not restate them.
- **Metadata.** Unless stated otherwise, the credentials attach one entry,
  `authorization: Bearer <token>`, in the form of
  [Call Credentials: Access Token Credentials](../06-security/03-call-credentials.md#2-access-token-credentials).
  A Google authentication library MAY cause additional Google-defined request
  metadata to be attached; that metadata is outside this specification.
- **Minimum security level:** `PRIVACY_AND_INTEGRITY` for every type in this
  document (see
  [Security Model: Call Credential Minimum Security Level](../06-security/01-security-model.md#51-call-credential-minimum-security-level)).
- **Caching and refresh.** Credentials that fetch tokens over the network
  cache each token and reuse it until shortly before it expires. They have the
  same purpose as
  [Call Credentials: Token-Fetching Credentials](../06-security/03-call-credentials.md#3-token-fetching-credentials),
  but their tokens are generally not JWTs, so their expiration comes from the
  token source's response rather than from an `exp` claim. The exact caching,
  refresh, and backoff behavior is implementation-defined. An implementation
  MAY use the token-fetching algorithm
  ([Call Credentials: Algorithm](../06-security/03-call-credentials.md#33-algorithm))
  with the expiration taken from the token response.
- **Failures.** A failure to obtain a token fails the attempt as specified in
  [Call Credentials: Results](../06-security/03-call-credentials.md#13-results):
  `UNAVAILABLE` when the token source is temporarily unreachable,
  `UNAUTHENTICATED` when it rejects the request.
- **Scope.** When a token request needs an OAuth 2.0 scope and the
  application has not supplied one, the scope is
  `https://www.googleapis.com/auth/cloud-platform`.

<!-- REVIEW(divergence) [VENDOR-8]: Status when a Google token cannot be obtained because the token source is unreachable. C++ HttpTokenFetcherCredentials::HttpFetchRequest::OnHttpResponse (src/core/credentials/call/token_fetcher/token_fetcher_credentials.cc L333-L359), used by compute engine, refresh token, STS, GDCH, and GCP service account identity credentials, fails with UNAVAILABLE on an HTTP error and maps a non-200 status to UNAVAILABLE (429, 502, 503, 504) or UNAUTHENTICATED; external account credentials have their own ExternalAccountCredentials::HttpFetchBody::OnHttpResponse (src/core/credentials/call/external/external_account_credentials.cc L131-L153) with the same non-200 mapping, but pass an HTTP error through unchanged (UNKNOWN). Java GoogleAuthLibraryCallCredentials (auth/src/main/java/io/grpc/auth/GoogleAuthLibraryCallCredentials.java L145-L156) uses UNAVAILABLE when the google-auth exception is Retryable and isRetryable(), otherwise UNAUTHENTICATED; Java ComputeEngineChannelCredentials.create (alts/src/main/java/io/grpc/alts/ComputeEngineChannelCredentials.java L50-L56) fails every RPC with INTERNAL when not on GCP. Go's oauth.TokenSource, jwtAccess, and serviceAccount (credentials/oauth/oauth.go) return the golang.org/x/oauth2 error unchanged, which is not a status; http2Client.getTrAuthData (internal/transport/http2_client.go L709-L719) turns a non-status error from channel-level credentials into UNAUTHENTICATED, and getCallAuthData (L745-L754) turns one from per-call credentials into INTERNAL, so a network failure reaching the metadata server or token endpoint fails the RPC with UNAUTHENTICATED or INTERNAL. Spec says: UNAVAILABLE when the token source is temporarily unreachable, UNAUTHENTICATED when it rejects the request. -->

Token exchange credentials based on the OAuth 2.0 Token Exchange protocol
(RFC 8693, "STS") are not Google-specific and are not covered by this
document.

## 2. Application Default Credentials

Application Default Credentials (ADC) are call credentials found by Google's
standard lookup procedure, as specified in
[AIP-4110: Google Application Default Credentials](https://google.aip.dev/auth/4110):
a credentials file named by the `GOOGLE_APPLICATION_CREDENTIALS` environment
variable, otherwise the Google Cloud CLI's well-known credentials file,
otherwise the GCP metadata server. They are the default call credentials of
[Google Default Credentials](01-google-default-credentials.md).

The lookup happens when the credentials are created. The credentials found
behave as the type in this document that matches them:

| Credentials found | Behavior |
| --- | --- |
| Service account key | [Service Account JWT Access Credentials](#4-service-account-jwt-access-credentials), unless the application requested OAuth scopes |
| Authorized user (refresh token) | [User Refresh Token Credentials](#6-user-refresh-token-credentials) |
| External account | [External Account Credentials](#7-external-account-credentials) |
| GCP metadata server (no credentials file) | [Compute Engine Credentials](#3-compute-engine-credentials) |

Scopes that gRPC adds itself (for example, scopes that Google default
credentials pass to the ADC lookup) are not requested by the application, so
a service account key used by Google default credentials MUST produce a
self-signed JWT unless the application supplied scopes (see
[AIP-4111: Self-signed JWT](https://google.aip.dev/auth/4111)).

If no credentials are found, creating ADC call credentials fails. (Google
default credentials handle this case as specified in
[Google Default Credentials: Application Default Credentials](01-google-default-credentials.md#31-application-default-credentials).)

## 3. Compute Engine Credentials

Compute engine credentials get an OAuth 2.0 access token for the default
service account of the virtual machine (or other Google Cloud runtime) from
the GCP metadata server, as described in
[AIP-4115: Default Credentials For Google Cloud Virtual Environments](https://google.aip.dev/auth/4115).
They work only where the GCP metadata server is reachable. Elsewhere every
token fetch fails.

- **Parameters:** none.
- **Metadata:** `authorization: Bearer <access token>`.

### 3.1 ALTS Hard-Bound Compute Engine Credentials

> **Introduced by:** [gRFC L126: C-core: Support ALTS Hard Bound Call Credentials in Google Default Credentials](https://github.com/grpc/proposal/blob/master/L126-core-add-alts-google-call-credentials.md)

A variant of compute engine credentials requests an access token that is
bound to ALTS connections, by adding the query parameter `transport=alts` to
the metadata server token request. These credentials are intended to be used
only as the ALTS-specific call credentials of Google default credentials
([Google Default Credentials: ALTS-Specific Call Credentials](01-google-default-credentials.md#33-alts-specific-call-credentials)),
so that the token is sent only on ALTS connections.

## 4. Service Account JWT Access Credentials

Service account JWT access credentials sign a JWT locally with a service
account's private key, as described in
[AIP-4111: Self-signed JWT](https://google.aip.dev/auth/4111). No network
request is made.

- **Parameters:** the service account key (see
  [AIP-4112: Service Account Keys](https://google.aip.dev/auth/4112)).
  Implementations MAY also accept a token lifetime.
- **Audience:** derived from the RPC's service URL
  ([Call Credentials: Inputs](../06-security/03-call-credentials.md#12-inputs))
  by removing the service name, giving `https://<host>/`. For example, service
  URL `https://pubsub.googleapis.com/google.pubsub.v1.Publisher` gives the
  audience `https://pubsub.googleapis.com/`.
- **Metadata:** `authorization: Bearer <jwt>`.
- **Caching:** a JWT MAY be reused for RPCs with the same audience until
  shortly before it expires.

## 5. Service Account OAuth Credentials

Service account OAuth credentials use a service account key (see
[AIP-4112: Service Account Keys](https://google.aip.dev/auth/4112)) to obtain
an OAuth 2.0 access token for a set of scopes from Google's OAuth 2.0 token
endpoint.

- **Parameters:** the service account key and the OAuth scopes.
- **Metadata:** `authorization: Bearer <access token>`.

## 6. User Refresh Token Credentials

User refresh token credentials hold an end user's OAuth 2.0 refresh token
(an "authorized user" credential, typically written by the Google Cloud CLI;
see [AIP-4110: Google Application Default Credentials](https://google.aip.dev/auth/4110))
and exchange it for access tokens at Google's OAuth 2.0 token endpoint.

- **Parameters:** the authorized user credential (client ID, client secret,
  and refresh token).
- **Metadata:** `authorization: Bearer <access token>`.

## 7. External Account Credentials

External account credentials (workload identity federation) obtain a token
from an identity provider outside Google (such as a local file, a URL, or a
cloud provider's metadata service), exchange it for a Google access token at
Google's Security Token Service, and, if the configuration names a service
account to impersonate, exchange that token for the service account's access
token, as described in
[AIP-4117: External Account Credentials (Workload Identity Federation)](https://google.aip.dev/auth/4117).

- **Parameters:** the external account credential configuration and the
  OAuth scopes. If no scope is given, the scope in
  [Common Behavior](#1-common-behavior) is used.
- **Metadata:** `authorization: Bearer <access token>`.

## 8. IAM Credentials

IAM credentials attach a fixed Google IAM authorization token and authority
selector that the application supplies. They make no network request and
never fail.

- **Parameters:** an authorization token and an authority selector (both
  strings).
- **Metadata:** two entries:

  ```
  x-goog-iam-authorization-token: <authorization token>
  x-goog-iam-authority-selector: <authority selector>
  ```

## 9. GDCH Service Account Credentials

Google Distributed Cloud Hosted (GDCH) service account credentials use a GDCH
service account key to obtain an access token for a given audience from the
token endpoint named in the key, as described in
[Google Distributed Cloud: Service identities](https://docs.cloud.google.com/distributed-cloud/hosted/docs/latest/gdcag/platform/pa-user/service-identity).

- **Parameters:** the GDCH service account key and the audience.
- **Metadata:** `authorization: Bearer <access token>`.

## 10. GCP Service Account Identity Credentials

GCP service account identity credentials get an identity JWT for a given
audience from the GCP metadata server. Unlike the other types in this
document, their fetch and caching behavior is fully specified by gRPC, in
[GCP Service Account Identity Credentials](03-gcp-service-account-identity-credentials.md).

## 11. Authentication Library Adapters

An implementation MAY provide a way to create call credentials from a
credentials object of a Google authentication library, so that any
credential type that library supports can be used with gRPC. Such adapters:

- Pass the RPC's service URL
  ([Call Credentials: Inputs](../06-security/03-call-credentials.md#12-inputs))
  to the library when the library needs a URI (for example, to compute a
  self-signed JWT audience).
- Attach the metadata the library returns, unchanged.
- Have minimum security level `PRIVACY_AND_INTEGRITY` for every Google
  credential type.
- Map a library failure that the library reports as retryable to
  `UNAVAILABLE`, and any other failure to `UNAUTHENTICATED`.

## 12. API Requirements

If the implementation provides a type in this document:

- The credentials API MUST provide a way to create it from the parameters
  listed in its section.
- Every type MUST be usable wherever call credentials are accepted: per
  channel, per call, in composite call credentials, and as the call
  credentials of Google default credentials
  ([Google Default Credentials: Application-Supplied Call Credentials](01-google-default-credentials.md#32-application-supplied-call-credentials)).
- An implementation that provides Google default credentials MUST provide
  [Compute Engine Credentials](#3-compute-engine-credentials), so that
  applications can build compute engine channel credentials
  ([Google Default Credentials: Compute Engine Channel Credentials](01-google-default-credentials.md#5-compute-engine-channel-credentials)).
