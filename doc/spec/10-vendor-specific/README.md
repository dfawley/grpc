> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 10. Vendor-Specific Features

This section specifies features that are tied to a specific vendor's
infrastructure, such as credentials and resolvers that depend on a cloud
provider's metadata server, identity system, or control plane.
Implementations MAY provide these features. An implementation that provides
one MUST implement it as specified here, under the names given here.

## Contents

- [10.1 Google Default Credentials](01-google-default-credentials.md): ALTS-or-TLS channel credentials with Application Default Credentials; ALTS-specific call credentials; compute engine channel credentials; the `google_default` xDS bootstrap type
- [10.2 Google Cloud-to-Prod (`google-c2p`) Resolver](02-google-c2p-resolver.md): the `google-c2p` target scheme: generated xDS bootstrap, DNS fallback
- [10.3 GCP Service Account Identity Credentials](03-gcp-service-account-identity-credentials.md): call credentials that fetch an identity JWT from the GCP metadata server
- [10.4 GCP Authentication Filter](04-gcp-authentication-filter.md): the xDS HTTP filter that attaches GCP service account identity credentials with a per-cluster audience
- [10.5 Google Call Credentials](05-google-call-credentials.md): Application Default Credentials, compute engine, service account, user refresh token, external account, IAM, and GDCH call credentials

## Related Sections

- [ALTS](../06-security/05-alts.md): the ALTS credentials that Google default credentials select for some connections
- [Bootstrap](../09-xds/02-bootstrap.md): the xDS bootstrap format used by the `google-c2p` resolver
- [Call Credentials](../06-security/03-call-credentials.md): the generic call credential behavior that the Google call credentials follow
- [xDS HTTP Filters](../09-xds/07-http-filters.md): the xDS HTTP filter framework that the GCP authentication filter plugs into
