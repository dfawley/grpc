> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 9.3.4 Cluster

<!-- Sources: A27, A29, A32, A37, A42, A47, A48, A50, A52, A55, A61, A75, A81, A83, A85, A86, A101, A105, doc/grpc_xds_features.md -->

The `envoy.config.cluster.v3.Cluster` resource describes an upstream cluster:
how its endpoints are discovered, which LB policy to use for it, and
cluster-level settings such as circuit breaking, outlier detection, load
reporting, and transport security. Clusters are referenced by routes (see
[RouteConfiguration](route-configuration.md)) and by aggregate clusters.

This section specifies which fields are read, when the resource is rejected,
and what the parsed resource contains. How parsed clusters are turned into
the LB policy tree is specified in [Client Data Plane](../client.md) and
[xDS LB Policies](../lb-policies.md).

## 1. Discovery Type

The `cluster_discovery_type` oneof decides the cluster type. Exactly one of
the following is accepted. Anything else (`type` = `STATIC`, `STRICT_DNS`, or
`ORIGINAL_DST`, or the oneof being unset) rejects the resource.

| Field / value | Cluster type |
| --- | --- |
| `type` = `EDS` | EDS cluster ([EDS Clusters](#11-eds-clusters)) |
| `type` = `LOGICAL_DNS` | Logical DNS cluster ([Logical DNS Clusters](#12-logical-dns-clusters)) |
| `cluster_type` set | Custom cluster type; only the aggregate cluster is supported ([Aggregate Clusters](#13-aggregate-clusters)) |

### 1.1 EDS Clusters

| Field | Rule |
| --- | --- |
| `eds_cluster_config` | MUST be present. |
| `eds_cluster_config.eds_config` | MUST be present, with `ads` or `self` set (see `ConfigSource` in [Common Types](common-types.md)). |
| `eds_cluster_config.service_name` | Optional. If non-empty, it is the name of the `ClusterLoadAssignment` resource to fetch. If empty, the cluster's own name is used. If the Cluster's name starts with `xdstp:`, `service_name` MUST be non-empty; otherwise the resource is rejected. (An `xdstp:` name includes the resource type, so it cannot be reused as an EDS resource name.) |

### 1.2 Logical DNS Clusters

| Field | Rule |
| --- | --- |
| `load_assignment` | MUST be present. |
| `load_assignment.endpoints` | MUST have exactly one entry. |
| `load_assignment.endpoints[0].lb_endpoints` | MUST have exactly one entry. |
| `...lb_endpoints[0].endpoint` | MUST be present. |
| `...endpoint.address` | MUST be present, with `socket_address` set. |
| `...socket_address.address` | MUST be non-empty. It is a DNS name (or IP literal) to resolve. |
| `...socket_address.port_value` | MUST be set. |
| `...socket_address.resolver_name` | MUST be empty; custom resolvers are not supported. |

Violations reject the resource. All other fields of `load_assignment` are
ignored. The parsed cluster records the DNS name as `host:port`, with the
host in brackets if it is an IPv6 literal. The client resolves this name with
its DNS resolver. All addresses returned form a single endpoint in a single
priority and an unnamed locality. Each such endpoint gets a `hostname`
attribute equal to the `host:port` string, used for authority rewriting (see
[Client Data Plane](../client.md)).

### 1.3 Aggregate Clusters

| Field | Rule |
| --- | --- |
| `cluster_type.typed_config` | MUST be present. Its type name MUST be `envoy.extensions.clusters.aggregate.v3.ClusterConfig`; any other type is rejected. The value MUST parse as that message. |
| `ClusterConfig.clusters` | MUST have at least one entry. The ordered list of underlying cluster names (highest priority first). |

`cluster_type.name` is ignored. An aggregate cluster uses the LB policy of
each underlying cluster, not its own. Its LB policy fields
(`load_balancing_policy`, `lb_policy`, and `lb_config`) are still validated
exactly as for any other cluster, and the resource is rejected if they are
invalid (so, for example, `lb_policy` = `CLUSTER_PROVIDED` is rejected), but
the resulting policy is never used.

Resolving the aggregate cluster graph (recursion, depth limit, cycles,
de-duplication) is specified in [Client Data Plane](../client.md).

## 2. LB Policy

The cluster's LB policy is converted to a gRPC LB policy configuration (a
JSON `LoadBalancingConfig` list; see
[Service Config](../../04-client-channel/service-config.md)). This config
is used as the child config of each priority under the cluster's `priority`
policy (see [xDS LB Policies](../lb-policies.md)). This section does not apply to
aggregate clusters ([Aggregate Clusters](#13-aggregate-clusters)).

**Precedence:** if `load_balancing_policy` is set, it is used, and
`lb_policy` and the `lb_config` oneof (`ring_hash_lb_config`,
`least_request_lb_config`, and so on) are ignored. Otherwise the legacy
`lb_policy` field is used.

### 2.1 `load_balancing_policy`

The `envoy.config.cluster.v3.LoadBalancingPolicy` message is converted by the
xDS LB policy registry, as specified in [xDS LB Policies](../lb-policies.md).
In short: the `policies` list is scanned in order, and the first entry whose
`typed_extension_config.typed_config` type the registry supports is converted
(recursively, for policies with child policies, up to 16 levels deep).
Unsupported entries are skipped. The resource is rejected if:

- no entry in the list is supported,
- a supported entry fails to convert (for example a `RingHash` with a
  `hash_function` other than `XX_HASH` or `DEFAULT_HASH`, or more than 16
  levels of nesting), or
- the converted JSON config fails to parse with the gRPC LB policy registry.

### 2.2 Legacy `lb_policy`

| `lb_policy` | Config fields read | Converted gRPC config |
| --- | --- | --- |
| `ROUND_ROBIN` (default) | none | `[{"xds_wrr_locality_experimental": {"childPolicy": [{"round_robin": {}}]}}]` |
| `RING_HASH` | `ring_hash_lb_config` (optional) | `[{"ring_hash_experimental": {"minRingSize": <min>, "maxRingSize": <max>}}]` |
| `LEAST_REQUEST` | `least_request_lb_config` (optional) | `[{"xds_wrr_locality_experimental": {"childPolicy": [{"least_request_experimental": {"choiceCount": <n>}}]}}]` |
| any other value (`RANDOM`, `MAGLEV`, `CLUSTER_PROVIDED`, `LOAD_BALANCING_POLICY_CONFIG`, unknown) | | resource is rejected |

`ring_hash_lb_config` (`Cluster.RingHashLbConfig`):

| Field | Rule |
| --- | --- |
| `minimum_ring_size` | `UInt64Value`, default 1024. MUST be in [1, 8388608] and MUST NOT exceed the effective maximum ring size. |
| `maximum_ring_size` | `UInt64Value`, default 8388608. MUST be in [1, 8388608]. |
| `hash_function` | MUST be `XX_HASH` (the default). `MURMUR_HASH_2` or any other value rejects the resource. |

`minRingSize` and `maxRingSize` are always written into the converted config,
even when the xDS fields are unset (so the xDS default of 8388608 for the
maximum, rather than the `ring_hash` policy's own default, applies). The
client-side ring size cap then limits both (see
[ring_hash](../../04-client-channel/lb-policies/ring_hash.md)).

`least_request_lb_config` (`Cluster.LeastRequestLbConfig`):

| Field | Rule |
| --- | --- |
| `choice_count` | `UInt32Value`, default 2. Values below 2 are rejected (by the `least_request` config parser). Values above 10 are treated as 10 by the policy. |
| `active_request_bias`, `slow_start_config` | Ignored. |

As with `load_balancing_policy`, the converted config MUST parse with the
gRPC LB policy registry, or the resource is rejected.

> **Experimental:** The registered LB policy names `ring_hash_experimental`,
> `least_request_experimental`, and `xds_wrr_locality_experimental` still
> carry the `_experimental` suffix. See
> [xDS LB Policies](../lb-policies.md) for the current registered names.

## 3. Circuit Breakers

`circuit_breakers` (`envoy.config.cluster.v3.CircuitBreakers`):

| Field | Rule |
| --- | --- |
| `thresholds` | gRPC uses only the **first** entry whose `priority` is `DEFAULT`. Entries for other priorities are ignored. |
| `thresholds[DEFAULT].max_requests` | `UInt32Value`. The maximum number of concurrent requests to the cluster. Default 1024 (used if `circuit_breakers`, the `DEFAULT` entry, or `max_requests` is absent). Set it very high (for example 4294967295) to effectively disable the limit. |
| `per_host_thresholds` | gRPC uses only the **first** entry whose `priority` is `DEFAULT`. |
| `per_host_thresholds[DEFAULT].max_connections` | `UInt32Value`. If set, it is the maximum number of connections per subchannel for every endpoint in the cluster (connection scaling; see [Subchannels](../../04-client-channel/subchannels.md)). 0 is rejected. If unset, the cluster configures no value, and the subchannel's value comes from the service config, else defaults to 1 (see [Subchannels](../../04-client-channel/subchannels.md)). The channel's own cap (10 by default) limits the value. |

All other threshold fields (`max_pending_requests`, `max_retries`,
`retry_budget`, `max_connection_pools`, `max_connections` in `thresholds`,
`track_remaining`) are ignored. Enforcement of `max_requests` (per
cluster and EDS service name, shared across channels) is specified in
[xDS LB Policies](../lb-policies.md).

## 4. Outlier Detection

If `outlier_detection` is absent, outlier detection is disabled for the
cluster. If it is present, its fields are validated and mapped onto the
`outlier_detection` LB policy config (see
[outlier_detection](../../04-client-channel/lb-policies/outlier_detection.md)):

| `OutlierDetection` field | Validation | gRPC `outlier_detection` config field |
| --- | --- | --- |
| `interval` | `Duration` ([`google.protobuf.Duration`](common-types.md#4-googleprotobufduration)) | `interval` |
| `base_ejection_time` | `Duration` | `baseEjectionTime` |
| `max_ejection_time` | `Duration` | `maxEjectionTime` |
| `max_ejection_percent` | ≤ 100 | `maxEjectionPercent` |
| `enforcing_success_rate` | ≤ 100 | `successRateEjection.enforcementPercentage` |
| `success_rate_stdev_factor` | | `successRateEjection.stdevFactor` |
| `success_rate_minimum_hosts` | | `successRateEjection.minimumHosts` |
| `success_rate_request_volume` | | `successRateEjection.requestVolume` |
| `enforcing_failure_percentage` | ≤ 100 | `failurePercentageEjection.enforcementPercentage` |
| `failure_percentage_threshold` | ≤ 100 | `failurePercentageEjection.threshold` |
| `failure_percentage_minimum_hosts` | | `failurePercentageEjection.minimumHosts` |
| `failure_percentage_request_volume` | | `failurePercentageEjection.requestVolume` |

Validation failures reject the resource. Unset xDS fields leave the
corresponding config field unset, so the `outlier_detection` policy's
defaults apply.

Enabling each algorithm (the "`enforcing_*` null rules"):

- **Success rate:** if `enforcing_success_rate` is explicitly set to 0,
  `successRateEjection` is unset (the algorithm is disabled) and all
  `success_rate_*` fields are ignored. Otherwise (unset, or non-zero),
  `successRateEjection` is set. When `enforcing_success_rate` is unset, its
  enforcement percentage takes the default of 100.
- **Failure percentage:** if `enforcing_failure_percentage` is unset or 0,
  `failurePercentageEjection` is unset (the algorithm is disabled) and all
  `failure_percentage_*` fields are ignored. Otherwise
  `failurePercentageEjection` is set.

All other `OutlierDetection` fields are ignored, including the
`consecutive_5xx`, `consecutive_gateway_failure`, and
`consecutive_local_origin_failure` families,
`split_external_local_origin_errors`, `max_ejection_time_jitter`, and
`successful_active_health_check_uneject_host`. Unsupported algorithms are
treated as disabled.

## 5. Override Host Status

`common_lb_config.override_host_status` (`envoy.config.core.v3.HealthStatusSet`)
is the set of endpoint health statuses that stateful session affinity may
still route to (see [xDS HTTP Filters](../http-filters.md) and
[xDS LB Policies](../lb-policies.md)):

- If `common_lb_config` or `override_host_status` is absent, the set is
  {`UNKNOWN`, `HEALTHY`}.
- If present, the set has the listed statuses that gRPC supports (`UNKNOWN`,
  `HEALTHY`, `DRAINING`). Other values are ignored, not rejected. A present
  but empty list gives an empty set.

All other `common_lb_config` fields are ignored.

## 6. Transport Socket

`transport_socket.typed_config` (an `Any`; see [Extensions: `google.protobuf.Any` and `TypedStruct`](common-types.md#2-extensions-googleprotobufany-and-typedstruct) in
[Common Types](common-types.md)), if present, MUST be one of the following.
Any other type rejects the resource. `transport_socket.name` and
`transport_socket_matches` are ignored.

| Type | Handling |
| --- | --- |
| `envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext` | Validated and parsed as specified in [xDS Security](../security.md). The parsed TLS config is used only if the channel uses xDS credentials. |
| `envoy.extensions.transport_sockets.http_11_proxy.v3.Http11ProxyUpstreamTransport` | HTTP CONNECT wrapper (see below). |

### 6.1 `Http11ProxyUpstreamTransport`

- The parsed cluster's `use_http_connect` flag is set to true. This flag is
  honored whether or not the channel uses xDS credentials.
- The nested `transport_socket` field MAY be unset. If set, its
  `typed_config` MUST be an `UpstreamTlsContext`; any other type rejects the
  resource. The nested `UpstreamTlsContext` is validated, parsed, and used
  exactly as if it had appeared directly in `Cluster.transport_socket`.
- With `use_http_connect` set, each endpoint whose EDS metadata has a proxy
  address (key `envoy.http11_proxy_transport_socket.proxy_address`, endpoint
  level first, then locality level; see
  [ClusterLoadAssignment](endpoint.md)) is reached through that HTTP
  CONNECT proxy. The CONNECT request's target is the endpoint's IP address
  and port (see [HTTP CONNECT Proxy Support](../../04-client-channel/proxy.md)
  and [xDS LB Policies](../lb-policies.md)). Endpoints without a proxy
  address are connected to directly.

## 7. Load Reporting

| Field | Rule |
| --- | --- |
| `lrs_server` | If absent, load reporting is disabled for the cluster. If present, it MUST have `self` set (otherwise the resource is rejected), and load reports for this cluster are sent to the xDS server the Cluster resource came from (see [LRS](../load-reporting.md)). |
| `lrs_report_endpoint_metrics` | List of names of ORCA backend metrics to copy into load reports. Recognized entries: `cpu_utilization`, `mem_utilization`, `application_utilization`, `named_metrics.<key>` (one key of the ORCA `named_metrics` map), and `named_metrics.*` (all keys). Unrecognized entries are ignored. If the list is empty, no backend metrics are propagated. Propagated `named_metrics` keys appear in LRS with the `named_metrics.` prefix. See [LRS](../load-reporting.md). |

## 8. Upstream Connection Options

`upstream_config` (`TypedExtensionConfig`):

- If absent, `connection_idle_timeout` takes its default.
- If present, `typed_config` MUST be
  `envoy.extensions.upstreams.http.v3.HttpProtocolOptions` (serialized
  protobuf); any other type rejects the resource.
- Within it, `common_http_protocol_options.idle_timeout`, if set, is
  validated as a `Duration` ([`google.protobuf.Duration`](common-types.md#4-googleprotobufduration)) and becomes the cluster's
  `connection_idle_timeout`. If `common_http_protocol_options` or
  `idle_timeout` is unset, the default applies.
- The default is 1 hour.

All other `HttpProtocolOptions` fields are ignored. The idle timeout limits
how long the `xds_override_host` policy keeps connections to endpoints that
are used only for stateful session affinity (see
[xDS LB Policies](../lb-policies.md)).

## 9. Metadata

`metadata` is parsed with the metadata rules and the metadata type registry
in [Common Types](common-types.md) ([Metadata](common-types.md#9-metadata)). Errors reject the resource. The
parsed map is part of the parsed cluster. The GCP authentication xDS HTTP
filter uses it (see [xDS HTTP Filters](../http-filters.md)).

## 10. Ignored Fields

All `Cluster` fields not named above are ignored. This includes
`connect_timeout`, `per_connection_buffer_limit_bytes`, `health_checks`,
`max_requests_per_connection`, DNS settings (`dns_lookup_family`,
`dns_refresh_rate`, `respect_dns_ttl`, `typed_dns_resolver_config`),
`cleanup_interval`, `upstream_bind_config`, `lb_subset_config`, `filters`,
`load_assignment` (for non-`LOGICAL_DNS` clusters), and
`typed_extension_protocol_options`.

## 11. Parsed Resource

```
Cluster {
  type: one of
    Eds { eds_service_name: string }            // empty => use cluster name
    LogicalDns { hostname: string }             // "host:port"
    Aggregate { prioritized_cluster_names: list of string }

  lb_policy_config: JSON LoadBalancingConfig list   // not set for Aggregate

  lrs_load_reporting_server: optional xDS server    // set iff lrs_server present
  lrs_backend_metric_propagation: {
    cpu_utilization: bool
    mem_utilization: bool
    application_utilization: bool
    all_named_metrics: bool
    named_metric_keys: set of string
  }

  upstream_tls_context: optional UpstreamTlsContext  // see xDS Security
  use_http_connect: bool

  max_concurrent_requests: uint32                    // default 1024
  max_connections_per_subchannel: optional uint32    // per_host_thresholds

  outlier_detection: optional OutlierDetectionConfig // absent => disabled
  override_host_statuses: set of HealthStatus        // default {UNKNOWN, HEALTHY}
  connection_idle_timeout: Duration                  // default 1h
  metadata: map<string, metadata value>
}
```

## 12. API Requirements

Cluster parsing itself needs no public API. Related public APIs, specified
elsewhere:

- Registering custom LB policies that can be selected through
  `load_balancing_policy` with a `TypedStruct` (see
  [xDS LB Policies](../lb-policies.md) and
  [Load Balancing](../../04-client-channel/load-balancing.md)).
- Setting the client-side ring size cap for `ring_hash` (see
  [ring_hash](../../04-client-channel/lb-policies/ring_hash.md)).
- Setting the channel's limit on connections per subchannel (see
  [Subchannels](../../04-client-channel/subchannels.md)).
- Choosing xDS credentials, which decides whether `UpstreamTlsContext` is
  used (see [xDS Security](../security.md)).
