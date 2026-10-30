> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 9.4.5 ClusterLoadAssignment and LbEndpointCollection

<!-- Sources: A27, A42, A52, A55, A61, A76, A81, A86, A95, doc/grpc_xds_features.md -->

> **Introduced by:** [gRFC A27: xDS-Based Global Load Balancing](https://github.com/grpc/proposal/blob/master/A27-xds-global-load-balancing.md)

The `envoy.config.endpoint.v3.ClusterLoadAssignment` (EDS) resource gives the
endpoints of an EDS cluster, grouped into localities and priorities, plus
drop configuration. The `envoy.config.endpoint.v3.LbEndpointCollection`
resource holds the endpoints of one locality when the EDS resource refers to
them instead of inlining them ([LbEndpointCollection (LEDS List Collections)](#7-lbendpointcollection-leds-list-collections)).

This section specifies which fields are read, when the resources are
rejected, and what the parsed resources contain. How priorities, localities,
endpoints, and drops are turned into the LB policy tree and used is specified
in [Client Data Plane](../05-client.md) and
[xDS LB Policies](../06-lb-policies.md).

## 1. ClusterLoadAssignment Fields

| Field | Rule |
| --- | --- |
| `cluster_name` | The resource name. |
| `endpoints` | List of `LocalityLbEndpoints` ([LocalityLbEndpoints](#2-localitylbendpoints)). May be empty, in which case the cluster has no endpoints. |
| `policy.drop_overloads` | Drop categories ([Drop Overloads](#5-drop-overloads)). |
| `policy.overprovisioning_factor` | Ignored. gRPC does not do overprovisioning-based graceful failover; it expects the control plane to move traffic. gRPC advertises the client feature `envoy.lb.does_not_support_overprovisioning` (see [Client Features](../01-architecture.md#3-client-features)). |
| `policy.endpoint_stale_after`, `policy.weighted_priority_health` | Ignored. |
| `named_endpoints` | Ignored. |

## 2. LocalityLbEndpoints

Each entry of `endpoints` is processed as follows:

| Field | Rule |
| --- | --- |
| `load_balancing_weight` | `UInt32Value`, the locality weight. If unset or 0, the **whole entry is ignored**: it is left out of the parsed resource and its other fields are not validated. |
| `locality` | MUST be present; otherwise the resource is rejected. `region`, `zone`, and `sub_zone` together identify the locality (empty strings are allowed). |
| `priority` | `uint32`, default 0. See the priority rules below. |
| `lb_endpoints` | The locality's endpoints ([LbEndpoint](#3-lbendpoint)), unless `leds_cluster_locality_config` is set. An empty list is allowed; the locality then has no endpoints and is unreachable. |
| `leds_cluster_locality_config` | If set, `lb_endpoints` is ignored, and the endpoints come from an `LbEndpointCollection` resource ([LbEndpointCollection (LEDS List Collections)](#7-lbendpointcollection-leds-list-collections)). |
| `metadata` | Parsed with the metadata rules in [Common Types](01-common-types.md) ([Metadata](01-common-types.md#9-metadata)). Errors reject the resource. Used for the locality-level HTTP CONNECT proxy address ([Endpoint Metadata](#4-endpoint-metadata)). |
| `proximity` | Ignored. |

<!-- REVIEW(divergence) [XDS_EDS-2]: Java: absent locality is treated as the empty locality
(region/zone/sub_zone all "") (xds/XdsEndpointResource.java parseLocality).
Go: rejects ("locality without ID"), checked before the zero-weight skip, so it
also rejects zero-weight entries without a locality
(internal/xds/xdsclient/xdsresource/unmarshal_eds.go). C++: rejects ("field not
present"), after the zero-weight skip (src/core/xds/grpc/xds_endpoint_parser.cc).
spec says: reject (C++/Go majority), zero-weight entries not validated (C++). -->

Rules across all entries that were not ignored:

- **Unique localities.** Within one priority, each locality (the
  `region`/`zone`/`sub_zone` triple) MUST appear at most once. A locality MAY
  appear in more than one priority.
- **No gaps in priorities.** If any locality has priority N > 0, then at
  least one locality has priority N-1. Equivalently, the set of priorities is
  exactly {0, 1, ..., P-1} for some P. (A validator MAY reject early any
  priority that is not less than the number of `endpoints` entries, since
  such a priority must leave a gap.)
- **Weight sum.** For each priority, the sum of the locality weights MUST NOT
  exceed 4,294,967,295 (the uint32 max).

Violations reject the resource.

## 3. LbEndpoint

Each entry of `lb_endpoints` (and each `LbEndpoint` in an
`LbEndpointCollection`) is processed as follows:

| Field | Rule |
| --- | --- |
| `health_status` | `UNKNOWN` and `HEALTHY`: the endpoint is used. `DRAINING`: the endpoint is kept in the parsed resource with its status (for stateful session affinity; see [xDS LB Policies](../06-lb-policies.md)). Any other value (`UNHEALTHY`, `TIMEOUT`, `DEGRADED`, unknown): the **endpoint is ignored** (left out and not validated). |
| `endpoint` | MUST be present. |
| `endpoint.address` | MUST be present and valid under the `Address` rules in [Common Types](01-common-types.md) ([Addresses](01-common-types.md#6-addresses)): a `socket_address` with an IPv4 or IPv6 literal and a `port_value` of at most 65535. |
| `endpoint.additional_addresses` | Optional extra addresses of the same endpoint (for example its IPv6 address alongside an IPv4 one). For each entry, `address` MUST be present and is validated exactly like `endpoint.address`. |
| `endpoint.hostname` | Optional. If non-empty, it becomes the endpoint's `hostname` attribute, used for authority rewriting when the route sets `auto_host_rewrite` (see [Client Data Plane](../05-client.md)). |
| `endpoint.health_check_config` | Ignored. |
| `load_balancing_weight` | `UInt32Value`, the endpoint weight. Default 1 if unset. 0 rejects the resource. |
| `metadata` | Parsed with the metadata rules in [Common Types](01-common-types.md) ([Metadata](01-common-types.md#9-metadata)). Errors reject the resource. See [Endpoint Metadata](#4-endpoint-metadata). |
| `endpoint_name` (in the `host_identifier` oneof) | Not supported; it does not give an `endpoint`, so the resource is rejected. |

The endpoint's addresses are `endpoint.address` followed by the
`additional_addresses` in order. The order matters: it is the order in which
the endpoint's addresses are tried (see
[pick_first](../../04-client-channel/lb-policies/pick_first.md)), and the
first address is the one hashed by ring_hash when there is no hash key.

### 3.1 Endpoint Weight

The parsed endpoint carries its weight. LB policies that use endpoint
weights (for example ring_hash) use the raw product of the locality weight
and the endpoint weight as the endpoint's effective weight (capped at the
uint32 maximum), as specified in [xDS LB Policies](../06-lb-policies.md).
Policies that do not use endpoint weights ignore it.

<!-- REVIEW(divergence) [XDS_EDS-1]: All three parse the endpoint weight (default 1) and pass
it through, despite doc/grpc_xds_features.md and early gRFCs saying it is
ignored (later gRFCs A42/A52 use it). Explicit 0: Java maps 0 to 1 with no NACK
(xds/Endpoints.java LbEndpoint.create); Go rejects
(internal/xds/xdsclient/xdsresource/unmarshal_eds.go); C++ rejects ("must be
greater than 0", src/core/xds/grpc/xds_endpoint_parser.cc). Go also rejects if
the endpoint weights in one locality sum above the uint32 max; Java/C++ do not.
spec says: default 1, 0 rejects (C++/Go majority), no per-locality endpoint sum
check (C++/Java majority). -->

### 3.2 Duplicate Addresses

Every address (from `address` and `additional_addresses`) of every endpoint
that was not ignored MUST be unique within the resource, across all
localities and priorities. A duplicate address rejects the resource.
Endpoints and localities that were ignored (by health status or zero locality
weight) are not counted.

<!-- REVIEW(divergence) [XDS_EDS-3]: Java: no duplicate-address check at all
(xds/XdsEndpointResource.java). Go: rejects duplicates across the whole
resource, including additional_addresses; endpoints of every health status are
kept and counted (internal/xds/xdsclient/xdsresource/unmarshal_eds.go). C++:
rejects duplicates across the resource, including additional addresses;
endpoints with health status other than UNKNOWN/HEALTHY/DRAINING are dropped
first and not counted (src/core/xds/grpc/xds_endpoint_parser.cc). spec says:
reject duplicates incl. additional addresses (C++/Go majority, original EDS
rule); ignored endpoints not counted (C++). LbEndpointCollection is not
implemented anywhere, so its per-resource uniqueness scope is unvalidated. -->

## 4. Endpoint Metadata

Two metadata entries are read from the parsed metadata maps:

- **Endpoint hash key.** In the endpoint's `LbEndpoint.metadata`, the entry
  with key `envoy.lb` of type `google.protobuf.Struct` (that is, from
  `filter_metadata`, or a `typed_filter_metadata` entry of an unregistered
  type with a `filter_metadata` fallback). If it has a string field
  `hash_key` with a non-empty value, that value becomes the endpoint's
  `hash_key` attribute. ring_hash then places the endpoint on the ring by
  hashing this key instead of the endpoint's first address (see
  [ring_hash](../../04-client-channel/lb-policies/ring_hash.md)). A missing
  entry, a value of another type, or a missing, non-string, or empty
  `hash_key` field means no hash key; none of these are errors.
- **HTTP CONNECT proxy address.** The entry with key
  `envoy.http11_proxy_transport_socket.proxy_address` and type
  `envoy.config.core.v3.Address`. It is looked up first in
  `LbEndpoint.metadata`, then in the enclosing `LocalityLbEndpoints.metadata`.
  An entry of another type is ignored, and lookup goes on. If found, the
  address becomes the endpoint's proxy address attribute. It is used only if
  the cluster's transport socket is `Http11ProxyUpstreamTransport` (see
  [Cluster](04-cluster.md)). If found in neither place, the endpoint is
  connected to directly.

## 5. Drop Overloads

Each entry of `policy.drop_overloads`:

| Field | Rule |
| --- | --- |
| `category` | MUST be non-empty. Used as the drop category name in load reports. |
| `drop_percentage` | MUST be present. A `FractionalPercent`, normalized to requests per million and capped at 1,000,000 (see [Common Types](01-common-types.md), [Fractional Percentages](01-common-types.md#5-fractional-percentages)). An unknown denominator rejects the resource. |

The categories are kept in list order. How drops are applied and reported is
specified in [xDS LB Policies](../06-lb-policies.md) and
[LRS](../10-load-reporting.md).

## 6. Parsed ClusterLoadAssignment

```
ClusterLoadAssignment {
  priorities: list of Priority {                  // index = priority, no gaps
    localities: map<Locality, LocalityEntry> {
      key Locality { region, zone, sub_zone }
      LocalityEntry {
        weight: uint32                            // > 0
        endpoints: one of
          inline: LbEndpointList                  // from lb_endpoints
          collection_name: string                 // LbEndpointCollection resource name
      }
    }
  }
  drop_categories: list of { category: string, requests_per_million: uint32 }
}

LbEndpointList: list of Endpoint {
  addresses: list of socket address               // address, then additional_addresses
  weight: uint32                                  // default 1
  health_status: UNKNOWN | HEALTHY | DRAINING
  hostname: optional string
  hash_key: optional string
  http_proxy_address: optional socket address     // endpoint, else locality metadata
}
```

## 7. LbEndpointCollection (LEDS List Collections)

> **Introduced by:** [gRFC A95: xDS Endpoint Fallback](https://github.com/grpc/proposal/blob/master/A95-xds-endpoint-fallback.md)

An EDS resource can keep a locality's endpoints in a separate resource. This
lets endpoint assignments come from a different authority than the locality
assignments, which helps xDS fallback (see [XdsClient](../03-xds-client.md)).
gRPC supports only *list collections*, which do not need the incremental xDS
protocol. Glob collections are not supported.

### 7.1 `leds_cluster_locality_config` in EDS

If `LocalityLbEndpoints.leds_cluster_locality_config` is set:

| Field | Rule |
| --- | --- |
| `leds_config` | MUST be present and have `self` set (see `ConfigSource` in [Common Types](01-common-types.md)). |
| `leds_collection_name` | The name of the `LbEndpointCollection` resource. MUST NOT end with `/*` (which would mean a glob collection). |

Violations reject the EDS resource. The parsed locality records the
collection name instead of an inline endpoint list. The rest of the
`LocalityLbEndpoints` entry (weight, locality, priority, metadata) is
processed as usual. Fetching the referenced collections is done by the
client's dependency handling (see [Client Data Plane](../05-client.md)).

### 7.2 `LbEndpointCollection` Resource

The resource type is `envoy.config.endpoint.v3.LbEndpointCollection`. It is
validated as follows:

- If `entries` is empty, the resource is valid and the locality has no
  endpoints (it is unreachable).
- Otherwise, each entry (an `xds.core.v3.CollectionEntry`):
  - MUST have `inline_entry` set. Entries that use `locator` are rejected.
  - `inline_entry.resource` MUST be an `Any` containing an
    `envoy.config.endpoint.v3.LbEndpoint`. Any other type rejects the
    resource.
  - The `LbEndpoint` is validated exactly as in [LbEndpoint](#3-lbendpoint), including the
    health-status, weight, metadata, and duplicate-address rules. Whether the
    locality-level proxy address fallback applies to these endpoints is not
    yet specified; it will be defined by a future specification for
    `LbEndpointCollection` (LEDS) resources.
  - `inline_entry.name` and `inline_entry.version` are ignored.

The parsed form is an `LbEndpointList` (as in [Parsed ClusterLoadAssignment](#6-parsed-clusterloadassignment)), the same structure
used for inline endpoints. When the client builds its configuration, a
locality whose endpoints are given by `collection_name` uses the parsed
collection resource with that name.

Clients that support `LbEndpointCollection` MUST advertise the client feature
`xds.endpoint.supports_lb_endpoint_collection`, so that control planes send
collection references only to clients that understand them (see
[Client Features](../01-architecture.md#3-client-features)).

## 8. API Requirements

No public API is needed for EDS or `LbEndpointCollection` handling.
Applications that use custom resolvers can set the endpoint `hash_key`
attribute directly, without xDS (see
[ring_hash](../../04-client-channel/lb-policies/ring_hash.md)).
