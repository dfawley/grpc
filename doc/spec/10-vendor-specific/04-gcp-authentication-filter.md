> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 10.4 GCP Authentication Filter

<!-- Sources: A83 (xDS HTTP filter part) -->

> **Introduced by:** [gRFC A83: xDS GCP Authentication Filter](https://github.com/grpc/proposal/blob/master/A83-xds-gcp-authn-filter.md)

The GCP authentication filter is an xDS HTTP filter that attaches a GCP
service account identity JWT to RPCs, as call credentials, with a per-cluster
audience. The generic xDS HTTP filter framework (the filter registry,
top-level and override configuration, the effective configuration rules, how
filters are applied to RPCs, and filter state retention) is specified in
[xDS HTTP Filters](../09-xds/07-http-filters.md). This document specifies
only what is particular to this filter.

- **Config type:** `envoy.extensions.filters.http.gcp_authn.v3.GcpAuthnFilterConfig`.
- **Sides:** client only. **Terminal:** no. **Overrides:** not supported
  ([Configuration Validation](#1-configuration-validation)).

## 1. Configuration Validation

| Field | Handling |
|---|---|
| `cache_config` | May be unset. |
| `cache_config.cache_size` | `UInt64Value`. If set, MUST be > 0, else NACK. Default 10. Implementations MAY cap it at their maximum supported size. |
| `http_uri`, `token_header`, `retry_policy`, `cluster`, `timeout` | Ignored. |

Per-route overrides are not supported. If a `GcpAuthnFilterConfig` appears in a
`typed_per_filter_config` map, it is validated as part of normal resource
validation (as a top-level config), but it is never used.

<!-- REVIEW(divergence) [XDS_GCP_AUTHN-1]: A83 says an override is "validated ... but will not
actually be used". Java: override parsed/validated as top-level config, then
ignored (GcpAuthenticationFilter.java parseFilterConfigOverride). Go: same
(internal/xds/httpfilter/gcpauthn/gcp_authn_filter.go). C++: no override type
registered (OverrideConfigProtoName() == ""), so an override NACKs unless
is_optional (src/core/xds/grpc/xds_http_gcp_authn_filter.cc). Spec says: follow
A83 (validate, ignore). -->

## 2. Audience from Cluster Metadata

The audience comes from the CDS resource of the RPC's cluster. CDS
`Cluster.metadata` is parsed into a metadata map as described in
[Cluster](../09-xds/04-resources/04-cluster.md) and
[Common Types](../09-xds/04-resources/01-common-types.md); the registered metadata
type `envoy.extensions.filters.http.gcp_authn.v3.Audience` (whose `url` MUST be
non-empty, else the CDS resource is NACKed) parses to an audience string.

The metadata key looked up is the xDS HTTP filter **instance name**
(`HttpFilter.name`), not a fixed key.

## 3. Per-RPC Behavior

When the RPC's request headers are processed, using the RPC's finalized
cluster and the `XdsConfig` ([xDS HTTP Filters: Client](../09-xds/07-http-filters.md#51-client)):

1. If the matched route uses a cluster specifier plugin (so the RPC's target is
   `cluster_specifier_plugin:<name>` rather than a concrete cluster; see
   [Client Data Plane: Cluster selection](../09-xds/05-client.md#52-cluster-selection)), do nothing (the
   filter is a no-op for the RPC).
2. If the CDS resource for the cluster is not available in the current
   `XdsConfig` (e.g., an error was received with no previously valid resource,
   or the resource does not exist), fail the RPC with `UNAVAILABLE`. (The RPC
   is failed even if it is wait-for-ready, because it cannot be re-processed
   with a later configuration.)
3. Look up the instance name in the cluster's metadata map. If absent, do
   nothing.
4. If the entry is not of type `Audience`, fail the RPC with `UNAVAILABLE`.
5. Otherwise, obtain from the instance's cache ([Call Credentials Cache](#4-call-credentials-cache)) the GCP
   service-account identity call credentials for the audience `url`, creating
   and inserting them if absent, and attach them to the RPC.

<!-- REVIEW(divergence) [XDS_GCP_AUTHN-2]: Combining with or replacing application per-call credentials. C++ overwrites grpc_client_security_context::creds (gcp_authentication_filter.cc), dropping per-call credentials the application set. Go appends a grpc.PerRPCCredentials call option after the application's options, and callInfo holds only one per-call credential, so the application's is replaced (gcp_authn_filter.go, rpc_util.go). Java wraps both in CompositeCallCredentials (GcpAuthenticationFilter.java), so both are sent. Envoy overwrites only the target header (preserve_existing keeps it). A83 says only "attach". Spec says: "attach them to the RPC". -->
The token is not added by this step directly, because the connection is not
yet known. The attached call credentials add the token after a connection has
been chosen, and MUST NOT send it on connections whose security level does
not permit call credentials (e.g., insecure connections). The GCP
service-account identity call credentials (token fetch from the metadata
server, caching, refresh, backoff, error-to-status mapping, and the
`authorization: Bearer <token>` header) are specified in
[GCP Service Account Identity Credentials](03-gcp-service-account-identity-credentials.md).

## 4. Call Credentials Cache

Each filter instance maintains an LRU cache mapping audience → call
credentials object:

- Using an entry moves it to the most-recently-used position. Inserting into a
  full cache evicts the least-recently-used entry.
- The maximum size is `cache_config.cache_size`. The cache is channel-wide:
  shared by all routes.
- The cache is retained across LDS and RDS updates using the mechanism of
  [xDS HTTP Filters: Filter State Retention Across Updates](../09-xds/07-http-filters.md#6-filter-state-retention-across-updates), keyed by instance name, so two instances never share a cache and the
  same instance keeps its cache across updates.
- If an update changes `cache_size`, the new size is applied to the retained
  cache, evicting least-recently-used entries as needed.

## 5. API Requirements

The filter adds no API requirements. It is configured entirely by the control
plane. An implementation that provides it MUST also provide the call
credentials it uses
([GCP Service Account Identity Credentials](03-gcp-service-account-identity-credentials.md)),
but need not expose them to applications.
