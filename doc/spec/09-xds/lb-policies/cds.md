> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `cds` LB Policy

<!-- Sources: A37, A50, A52, A55, A56, A61, A74, A75, A76, A81, A86, A89, A94, grpc-proto grpc/service_config/service_config.proto -->

> **Experimental:** This policy is registered as `cds_experimental`.

> **Introduced by:** [gRFC A27: xDS-Based Global Load Balancing](https://github.com/grpc/proposal/blob/master/A27-xds-global-load-balancing.md)

## 1. Overview

The `cds` policy builds the LB policy subtree for one xDS cluster from the
`XdsConfig` resolver attribute (see [XdsConfig](../05-client.md#3-xdsconfig)).
For an EDS or LOGICAL_DNS cluster, its child is an `outlier_detection` →
`xds_cluster_impl` → `xds_override_host` → `priority` chain, and it flattens
the cluster's endpoint data into the endpoint list passed to that child. For an
aggregate cluster, its child is a `priority` policy with one `cds` child per
leaf cluster.

The `cds` policy is a parent policy with a single child (see
[Policy Hierarchy](../../04-client-channel/06-load-balancing.md#9-policy-hierarchy)).

Registered name: `cds_experimental`.

### 1.1 Position in the xDS LB Policy Tree

<!-- XDS-LB-TREE: generated; identical in every xDS LB policy document except for the highlighted policy -->
<pre>
<a href="xds_cluster_manager.md">xds_cluster_manager</a>  (one child per cluster and per cluster specifier plugin)
├── <b><a href="cds.md">cds</a>  ◀ this policy</b>  (one per cluster)
│   ├── non-aggregate cluster (EDS or LOGICAL_DNS):
│   │   └── <a href="../../04-client-channel/lb-policies/outlier_detection.md">outlier_detection</a>
│   │       └── <a href="xds_cluster_impl.md">xds_cluster_impl</a>
│   │           └── <a href="xds_override_host.md">xds_override_host</a>
│   │               └── <a href="../../04-client-channel/lb-policies/priority.md">priority</a>  (one child per EDS priority)
│   │                   ├── <a href="xds_wrr_locality.md">xds_wrr_locality</a>  (default; see <a href="../06-lb-policies.md#2-xds-lb-policy-registry">xDS LB Policy Registry</a>)
│   │                   │   └── <a href="../../04-client-channel/lb-policies/weighted_target.md">weighted_target</a>  (one child per locality)
│   │                   │       └── endpoint-picking policy (e.g. <a href="../../04-client-channel/lb-policies/round_robin.md">round_robin</a>)
│   │                   │           └── <a href="../../04-client-channel/lb-policies/pick_first.md">pick_first</a>  (one per endpoint)
│   │                   └── or another converted policy: <a href="../../04-client-channel/lb-policies/ring_hash.md">ring_hash</a> | <a href="../../04-client-channel/lb-policies/random_subsetting.md">random_subsetting</a> | ...
│   └── aggregate cluster:
│       └── <a href="../../04-client-channel/lb-policies/priority.md">priority</a>  (one child per leaf cluster)
│           └── <b><a href="cds.md">cds</a>  ◀ this policy</b>  (one per leaf cluster; non-aggregate subtree above)
└── <a href="../../04-client-channel/lb-policies/rls.md">rls</a>  (one per RLS cluster specifier plugin)
    └── <b><a href="cds.md">cds</a>  ◀ this policy</b>  (one per target cluster returned by the lookup server)
</pre>
<!-- /XDS-LB-TREE -->

`cds` is a child of `xds_cluster_manager`; of `rls`, for a cluster returned by
an RLS lookup; or of an aggregate cluster's `priority` policy, for a leaf
cluster. For a non-aggregate cluster its child is `outlier_detection`. For an
aggregate cluster its child is a `priority` policy with one `cds` child per leaf
cluster.

## 2. Configuration

Proto: `CdsConfig` in `grpc/service_config/service_config.proto`.

```json
{
  "cds_experimental": {
    "cluster": "cluster_a",
    "isDynamic": false
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `cluster` | string | Yes | — | The cluster name. It MUST NOT change over the life of the policy instance. |
| `isDynamic` | bool | No | `false` | True for a cluster that is not named by the route configuration, such as a cluster returned by the lookup server of the RLS cluster specifier plugin (see [RLS Cluster Specifier Plugin](../04-resources/03-route-configuration.md#53-rls-cluster-specifier-plugin)). The policy then obtains a dynamic subscription. |

### 2.1 Validation

The config is invalid, and is rejected as described in
[LB Policy Registry and Configuration](../../04-client-channel/06-load-balancing.md#2-lb-policy-registry-and-configuration),
if:

- `cluster` is missing.

### 2.2 Other Inputs

| Input | Location | Default | Used for |
| --- | --- | --- | --- |
| Cluster entry | Top-level attribute `XdsConfig` (see [XdsConfig](../05-client.md#3-xdsconfig)): the `clusters` entry for `cluster`, which is either an error or a `ClusterConfig` | — | A missing or error entry makes the policy report TRANSIENT_FAILURE, or, for a missing dynamic cluster, keep its current state ([Update](#33-updates-from-the-parent)). |
| Cluster type | Top-level attribute `XdsConfig`: the `ClusterConfig` for `cluster`, cluster resource field `type` (EDS, LOGICAL_DNS, or aggregate) | — | Choosing between the non-aggregate and aggregate child configs ([Child Config for a Non-Aggregate Cluster](#child-config-for-a-non-aggregate-cluster), [Child Config for an Aggregate Cluster](#child-config-for-an-aggregate-cluster)). |
| Cluster resolution note | Top-level attribute `XdsConfig`: the `ClusterConfig` for `cluster`, `resolution_note` of its `EndpointConfig` or `AggregateConfig` | empty | Combined with the update's resolution note for an EDS or LOGICAL_DNS cluster; passed as the child's resolution note for an aggregate cluster ([Update](#33-updates-from-the-parent)). |
| Endpoint data | Top-level attribute `XdsConfig`: the `ClusterConfig` for `cluster`, `EndpointConfig` fields `endpoints` (the EDS resource or the DNS result) and `lb_endpoint_collections` (EDS or LOGICAL_DNS cluster only) | — | Building the endpoint list and its attributes, and the priority child names ([Endpoint List and Attributes](#endpoint-list-and-attributes), [Priority Child Names](#priority-child-names)). |
| LB policy config | Top-level attribute `XdsConfig`: the `ClusterConfig` for `cluster`, cluster resource field `lb_policy_config` (the converted LB policy config; EDS or LOGICAL_DNS cluster only) | — | The config of each `priority` child ([Child Config for a Non-Aggregate Cluster](#child-config-for-a-non-aggregate-cluster)). |
| `outlier_detection` | Top-level attribute `XdsConfig`: the `ClusterConfig` for `cluster`, cluster resource field `outlier_detection` (EDS or LOGICAL_DNS cluster only) | absent (outlier detection disabled) | The `outlier_detection` child's config ([Child Config for a Non-Aggregate Cluster](#child-config-for-a-non-aggregate-cluster)). |
| `use_http_connect` | Top-level attribute `XdsConfig`: the `ClusterConfig` for `cluster`, cluster resource field `use_http_connect` (EDS or LOGICAL_DNS cluster only) | false | Whether to set or remove the HTTP CONNECT proxy endpoint attributes ([Endpoint List and Attributes](#endpoint-list-and-attributes)). |
| Leaf clusters | Top-level attribute `XdsConfig`: the `ClusterConfig` for `cluster`, `AggregateConfig` field `leaf_clusters` (aggregate cluster only) | — | The `priority` child's children, in order ([Child Config for an Aggregate Cluster](#child-config-for-an-aggregate-cluster)). |
| Cluster subscription interface | Top-level attribute cluster subscription interface | — | Obtaining a cluster subscription when `isDynamic` is true (see [Dynamic cluster subscriptions](../05-client.md#26-dynamic-cluster-subscriptions); [Update](#33-updates-from-the-parent)). |
| Resolution note | Update resolution note | empty | Combined with the cluster's `resolution_note` ([Update](#33-updates-from-the-parent)). |
| Endpoint list | Update endpoints (always empty from the xds resolver) | — | Not used; endpoints come from the `XdsConfig`. |

## 3. LB Policy Implementation

### 3.1 Internal State

The `cds` policy keeps:

- its child policy, if any;
- the dynamic cluster subscription, if it holds one;
- the child number state used to name priority children
  (`priority_child_numbers` and `next_available_child_number`; see
  [Priority Child Names](#priority-child-names));
- the cluster's `ClusterConfig` from the previous update, used to decide
  whether it can skip updating the child ([Update](#33-updates-from-the-parent)).

### 3.2 Features

#### Priority Child Names

Each priority of an EDS or LOGICAL_DNS cluster becomes a child of the
`priority` policy, named `{cluster=<cluster>, child_number=<n>}`. To avoid
recreating child policies (and their connections) when localities move between
priorities, child numbers are reused across updates with this algorithm:

```
# State kept across updates:
#   priority_child_numbers: list, child number for each priority index
#   next_available_child_number: integer, initially 0
# If the endpoint resource is missing or has no priorities, it is treated as
# having exactly one priority with no localities.

def UpdateChildNumbers(old_priorities, new_priorities):
  locality_to_child = {}        # from the previous update
  child_to_localities = {}
  for p, priority in enumerate(old_priorities):
    n = priority_child_numbers[p]
    for locality in priority.localities:
      locality_to_child[locality] = n
      child_to_localities[n].add(locality)
  new_numbers = []
  for priority in new_priorities:
    n = None
    for locality in priority.localities:
      if n is None:
        if locality in locality_to_child:
          n = locality_to_child.pop(locality)
          # Don't reuse n for a later priority via its other old localities.
          for old_locality in child_to_localities[n]:
            locality_to_child.pop(old_locality, None)
      else:
        # Don't let a later priority claim this priority's child number.
        locality_to_child.pop(locality, None)
    if n is None:
      n = next_available_child_number
      while n in child_to_localities: n += 1
      next_available_child_number = n + 1
      child_to_localities[n] = {}     # mark as in use
    new_numbers.append(n)
  priority_child_numbers = new_numbers
```

When the cluster becomes an aggregate cluster, this state is reset.

#### Endpoint List and Attributes

For an EDS or LOGICAL_DNS cluster, the `cds` policy flattens the endpoint data
from the `XdsConfig` into the endpoint list passed to its child. Endpoints are
taken from the EDS resource, or from its `LbEndpointCollection` resources, or
from the DNS result. Priorities are processed in order; within each priority,
each locality; within each locality, each endpoint. Each endpoint's
addresses are passed unchanged. The `cds` policy sets these **per-endpoint
attributes**:

| Attribute | Value |
| --- | --- |
| Hierarchical path | `[<priority child name>, <locality name string>]`. The first element routes the endpoint to its `priority` child; the second routes it to its locality child under `xds_wrr_locality` / `weighted_target` (see [priority](../../04-client-channel/lb-policies/priority.md)). |
| Locality | The locality (region, zone, sub-zone). Used by `xds_cluster_impl` for load reporting and labels, and by `xds_wrr_locality`. |
| Locality name string | `{region="<region>", zone="<zone>", sub_zone="<sub_zone>"}`. Used as the `grpc.lb.locality` label value by subchannel metrics (see [Metric Catalog](../../08-observability/04-metrics.md)). |
| Locality weight | The locality's `load_balancing_weight`. Used by `xds_wrr_locality`. |
| Backend service | The cluster name. Used as the `grpc.lb.backend_service` label value by subchannel and TLS client metrics (see [Metric Catalog](../../08-observability/04-metrics.md)). |
| Endpoint weight | Locality weight × endpoint weight ([Endpoint Weight](#endpoint-weight)). Used by weighted policies such as `ring_hash`. |
| HTTP CONNECT proxy | If the parsed cluster has `use_http_connect` set (its transport socket is `Http11ProxyUpstreamTransport`, see [Cluster](../04-resources/04-cluster.md)) and the endpoint has a proxy address (the parsed endpoint's `http_proxy_address`, from endpoint metadata, else locality metadata, key `envoy.http11_proxy_transport_socket.proxy_address`; see [ClusterLoadAssignment and LbEndpointCollection](../04-resources/05-endpoint.md)), attributes that make the subchannel connect through that proxy, with the endpoint's address as the CONNECT argument (see [HTTP CONNECT Proxy](../../04-client-channel/09-proxy.md)). If `use_http_connect` is not set, any proxy attribute MUST be removed. |

These attributes come from resource parsing (see
[ClusterLoadAssignment and LbEndpointCollection](../04-resources/05-endpoint.md)) and are passed through
unchanged:

| Attribute | Value |
| --- | --- |
| Health status | The endpoint's EDS `health_status` (UNKNOWN, HEALTHY, or DRAINING). Used by `xds_override_host`. |
| `hostname` | The endpoint's `Endpoint.hostname`. For LOGICAL_DNS, the cluster's `host:port`. Used for authority rewriting. |
| `hash_key` | The `hash_key` string from the endpoint's `envoy.lb` metadata, if present. Used by `ring_hash` to place the endpoint on the ring (see [ring_hash](../../04-client-channel/lb-policies/ring_hash.md)). |

A LOGICAL_DNS cluster always produces a single endpoint containing all
resolved addresses, in the empty locality (see [LOGICAL_DNS clusters](../05-client.md)).

#### Child Config for a Non-Aggregate Cluster

The `cds` policy generates this child config. `<xds_lb_policy>` is the
cluster's converted LB policy config ([xDS LB Policies: xDS LB Policy Registry](../06-lb-policies.md#2-xds-lb-policy-registry)):

```json
[ { "outlier_detection_experimental": {
      <outlier detection fields from the Cluster, if configured>,
      "childPolicy": [ { "xds_cluster_impl_experimental": {
        "clusterName": "<cluster>",
        "childPolicy": [ { "xds_override_host_experimental": {
          "clusterName": "<cluster>",
          "childPolicy": [ { "priority_experimental": {
            "priorities": [ "<child name for priority 0>", ... ],
            "children": {
              "<child name for priority N>": {
                "config": <xds_lb_policy>,
                "ignore_reresolution_requests": <true for EDS, false for LOGICAL_DNS>
              }
            }
          } } ]
        } } ]
      } } ]
} } ]
```

- `priority`: one child per priority in the endpoint data, in priority order,
  named as in [Priority Child Names](#priority-child-names). If the endpoint data is
  missing (for example, after an EDS error) or has no priorities, there is
  exactly one priority with no endpoints. That priority reports
  TRANSIENT_FAILURE, which fails RPCs with the resolution note, and keeps an
  `xds_cluster_impl` in place so that drops still apply.
- `ignore_reresolution_requests` is true for EDS clusters, because EDS updates
  are pushed and re-resolution would only cause unneeded DNS lookups for
  LOGICAL_DNS clusters elsewhere in the config. It is false for LOGICAL_DNS
  clusters.
- `outlier_detection` is always present. If the Cluster has an
  `outlier_detection` field, its values are converted as follows. Otherwise
  only `childPolicy` is set, which makes the policy a no-op (see
  [outlier_detection](../../04-client-channel/lb-policies/outlier_detection.md)).

  | Cluster `outlier_detection` field | `outlier_detection` config field |
  | --- | --- |
  | `interval` | `interval` |
  | `base_ejection_time` | `baseEjectionTime` |
  | `max_ejection_time` | `maxEjectionTime` |
  | `max_ejection_percent` | `maxEjectionPercent` |
  | `success_rate_stdev_factor` | `successRateEjection.stdevFactor` |
  | `enforcing_success_rate` | `successRateEjection.enforcementPercentage` |
  | `success_rate_minimum_hosts` | `successRateEjection.minimumHosts` |
  | `success_rate_request_volume` | `successRateEjection.requestVolume` |
  | `failure_percentage_threshold` | `failurePercentageEjection.threshold` |
  | `enforcing_failure_percentage` | `failurePercentageEjection.enforcementPercentage` |
  | `failure_percentage_minimum_hosts` | `failurePercentageEjection.minimumHosts` |
  | `failure_percentage_request_volume` | `failurePercentageEjection.requestVolume` |

  `successRateEjection` is omitted when `enforcing_success_rate` is 0.
  `failurePercentageEjection` is omitted when `enforcing_failure_percentage` is
  0 or unset. Defaults and validation are in
  [Cluster](../04-resources/04-cluster.md).

#### Child Config for an Aggregate Cluster

> **Introduced by:** [gRFC A37: xDS Aggregate and Logical DNS Clusters](https://github.com/grpc/proposal/blob/master/A37-xds-aggregate-and-logical-dns-clusters.md)

```json
[ { "priority_experimental": {
      "priorities": [ "<leaf 1>", "<leaf 2>", ... ],
      "children": {
        "<leaf N>": { "config": [ { "cds_experimental": { "cluster": "<leaf N>" } } ] }
      }
} } ]
```

The children are the `leaf_clusters` of the aggregate's `AggregateConfig`, in
order, each named by its leaf cluster name. `ignore_reresolution_requests` is
false. The aggregate `cds` policy does not set endpoint attributes; each leaf
`cds` does so for its own cluster.

#### Endpoint Weight

The endpoint weight attribute is the raw product:

```
endpoint_weight = locality.load_balancing_weight × endpoint_lb_weight
```

where `endpoint_lb_weight` is the endpoint's `load_balancing_weight`, or 1 if
it is unset (an explicit 0 is rejected when the EDS resource is validated; see
[ClusterLoadAssignment and LbEndpointCollection](../04-resources/05-endpoint.md)). Localities with weight 0 or
unset are left out of the parsed resource, so both factors are at least 1. For
a LOGICAL_DNS cluster, both weights are 1.
<!-- REVIEW(divergence) [XDS_LB-1]: overflow of locality weight × endpoint weight (no gRFC covers it). Java: computes the product in a 64-bit long weight attribute (no overflow; uint32 values ≥ 2^31 are sign-extended) (CdsLoadBalancer2.java); Go: uint32 × uint32, wraps mod 2^32 (cdsbalancer/configbuilder.go); C++: uint32 × uint32, wraps mod 2^32, then stored in an int arg (load_balancing/xds/cds.cc). spec says: saturate at max uint32 (none does this; wrapping is clearly a bug). -->
If the product exceeds the maximum uint32 value, it MUST be capped at that
value.

### 3.3 Updates from the Parent

On each update, the `cds` policy:

1. If `isDynamic` is true and it holds no subscription yet, obtains a cluster
   subscription for `cluster` from the cluster subscription interface
   attribute (see [Dynamic cluster subscriptions](../05-client.md)). It holds the subscription until the
   policy is destroyed.
2. Looks up `cluster` in the `XdsConfig` attribute:
   - **Missing entry, dynamic cluster:** ignores the update and keeps its
     current state (CONNECTING if it has none). The subscription may not be
     reflected in the config yet.
   - **Missing entry, non-dynamic cluster:** reports TRANSIENT_FAILURE with a
     picker that drops every RPC with an UNAVAILABLE status (`xDS config has
     no entry for static cluster <name>`), as for an error entry below.
     The resolver guarantees this does not happen.
   - **Entry is an error** (for example, the cluster does not exist): destroys
     its child policy and reports TRANSIENT_FAILURE with a picker that returns
     a **Drop** result with that UNAVAILABLE status for every pick (see
     [Pick Results](../../04-client-channel/06-load-balancing.md#62-pick-results)).
     The RPC fails even if it is wait_for_ready. A queued RPC would keep its
     cluster reference
     ([Cluster references and two-phase removal](../05-client.md#54-cluster-references-and-two-phase-removal))
     for as long as it waits, so a cluster that no route names any more could
     never be removed.
3. For an **EDS or LOGICAL_DNS** cluster: computes the priority child names
   ([Priority Child Names](#priority-child-names)), builds the endpoint list
   ([Endpoint List and Attributes](#endpoint-list-and-attributes)), and builds the child config
   ([Child Config for a Non-Aggregate Cluster](#child-config-for-a-non-aggregate-cluster)). The
   resolution note passed to the child is the `"; "`-joined non-empty values
   of the update's resolution note and the cluster's `resolution_note` from the
   `XdsConfig`. If the cluster's `ClusterConfig` is identical to the one from
   the previous update, the policy MAY skip updating the child.
4. For an **aggregate** cluster: builds the child config described in
   [Child Config for an Aggregate Cluster](#child-config-for-an-aggregate-cluster) and passes the
   aggregate's `resolution_note` as the child's resolution note. The endpoint
   list is empty.
5. Creates the child policy (on the first update) and updates it. The
   `XdsConfig`, XdsClient, and subscription attributes are passed through to
   the child. For a non-aggregate cluster, the policy also passes the cluster
   name to its child as the **backend service** top-level attribute, which
   `weighted_round_robin` uses for its metric labels, and sets it as a
   per-endpoint attribute
   ([Endpoint List and Attributes](#endpoint-list-and-attributes)).

When the policy updates its child, it returns the child's status. Once it has
a child, the policy reports the child's connectivity state as described in
[Calls From Children](#52-calls-from-children).

### 3.4 ExitIdle

Forwarded to the child, if any.

### 3.5 ResetBackoff

Forwarded to the child, if any.

### 3.6 Shutdown

Shuts down the child, if any, and releases the dynamic cluster subscription,
if it holds one.

## 4. Picker Implementation

For a **non-aggregate** cluster, the `cds` policy wraps the child's picker so
that, on every pick, the picker sets the `grpc.lb.backend_service` optional
label of the call attempt to the cluster name (see
[Instrumentation](../../08-observability/02-instrumentation.md) and
[Metric Catalog](../../08-observability/04-metrics.md)), and then delegates the
pick to the child's picker. The `cds` policy for an aggregate cluster does not
set the label and reports its child's picker unchanged; the leaf `cds`
policies below it set the label, so the label is the leaf cluster name.

When the cluster's `XdsConfig` entry is an error, or is missing for a
non-dynamic cluster, the policy's picker returns a Drop result for every pick
([Update](#33-updates-from-the-parent)).

## 5. Children and Subchannels

### 5.1 Child Policies

The `cds` policy has at most one child:

- for an EDS or LOGICAL_DNS cluster, an `outlier_detection` policy with the
  config in
  [Child Config for a Non-Aggregate Cluster](#child-config-for-a-non-aggregate-cluster),
  which receives the endpoint list built in
  [Endpoint List and Attributes](#endpoint-list-and-attributes);
- for an aggregate cluster, a `priority` policy with the config in
  [Child Config for an Aggregate Cluster](#child-config-for-an-aggregate-cluster)
  and an empty endpoint list.

The child is created on the first update and receives the resolution note and
attributes described in [Update](#33-updates-from-the-parent). It is destroyed when the
cluster's entry is an error. `ExitIdle()`, `ResetBackoff()`, and `Shutdown()`
are forwarded to it ([ExitIdle](#34-exitidle), [ResetBackoff](#35-resetbackoff),
[Shutdown](#36-shutdown)).

### 5.2 Calls From Children

- `UpdateState(state, status, picker)`: the `cds` policy passes its child's
  connectivity state and status up unchanged. For a non-aggregate cluster, it
  wraps the child's picker so that every pick sets the
  `grpc.lb.backend_service` label
  ([Picker Implementation](#4-picker-implementation)); for an aggregate
  cluster, it reports the child's picker unchanged.
- `RequestReresolution()`: forwarded to the channel.
- `CreateSubchannel(address, attributes)`: passed through to the policy's own
  helper unchanged.

### 5.3 Subchannels

Not applicable: the policy does not create or watch subchannels; its
descendants do.

## 6. Metrics

The policy records no metrics. Its picker sets the `grpc.lb.backend_service`
label ([Picker Implementation](#4-picker-implementation)), and it passes the
cluster name as the backend service attribute to its descendants
([Update](#33-updates-from-the-parent)).

## 7. API Requirements

- gRPC MUST register this policy in the LB policy registry under the name `cds_experimental` so that the configuration generated by the xDS client data plane can select it.
- This policy is internal to xDS support. Applications are not expected to configure it directly, and gRPC is not required to provide any public API specific to it beyond the general LB policy API requirements in [xDS LB Policies: API Requirements](../06-lb-policies.md#3-api-requirements).
