> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `xds_cluster_impl` LB Policy

<!-- Sources: A27, A32, A37, A42, A64, A74, A78, A81, A85, A89, A105, grpc-proto grpc/service_config/service_config.proto -->

> **Experimental:** This policy is registered as `xds_cluster_impl_experimental`.

## 1. Overview

The `xds_cluster_impl` policy applies the per-cluster behavior of one leaf
(EDS or LOGICAL_DNS) cluster: EDS-configured drops, circuit breaking, load
reporting, per-call metric labels, authority rewriting, transport security
configuration, and connection scaling. It reads the cluster's data from the
`XdsConfig` resolver attribute. The `cds` policy places it in the subtree of
every leaf cluster
([Child config for a non-aggregate cluster](cds.md#38-child-config-for-a-non-aggregate-cluster)).

The `xds_cluster_impl` policy is a parent policy with a single child (see
[Policy Hierarchy](../../04-client-channel/05-load-balancing.md#9-policy-hierarchy)).
It wraps the subchannels that its descendants create and the picker that its
child reports.

Registered name: `xds_cluster_impl_experimental`.

### 1.1 Position in the xDS LB Policy Tree

<!-- XDS-LB-TREE: generated; identical in every xDS LB policy document except for the highlighted policy -->
<pre>
<a href="xds_cluster_manager.md">xds_cluster_manager</a>  (one child per cluster and per cluster specifier plugin)
├── <a href="cds.md">cds</a>  (one per cluster)
│   ├── non-aggregate cluster (EDS or LOGICAL_DNS):
│   │   └── <a href="../../04-client-channel/lb-policies/outlier_detection.md">outlier_detection</a>
│   │       └── <b><a href="xds_cluster_impl.md">xds_cluster_impl</a>  ◀ this policy</b>
│   │           └── <a href="xds_override_host.md">xds_override_host</a>
│   │               └── <a href="../../04-client-channel/lb-policies/priority.md">priority</a>  (one child per EDS priority)
│   │                   ├── <a href="xds_wrr_locality.md">xds_wrr_locality</a>  (default; see <a href="../05-lb-policies.md#2-xds-lb-policy-registry">xDS LB Policy Registry</a>)
│   │                   │   └── <a href="../../04-client-channel/lb-policies/weighted_target.md">weighted_target</a>  (one child per locality)
│   │                   │       └── endpoint-picking policy (e.g. <a href="../../04-client-channel/lb-policies/round_robin.md">round_robin</a>)
│   │                   │           └── <a href="../../04-client-channel/lb-policies/pick_first.md">pick_first</a>  (one per endpoint)
│   │                   └── or another converted policy: <a href="../../04-client-channel/lb-policies/ring_hash.md">ring_hash</a> | <a href="../../04-client-channel/lb-policies/random_subsetting.md">random_subsetting</a> | ...
│   └── aggregate cluster:
│       └── <a href="../../04-client-channel/lb-policies/priority.md">priority</a>  (one child per leaf cluster)
│           └── <a href="cds.md">cds</a>  (one per leaf cluster; non-aggregate subtree above)
└── <a href="../../04-client-channel/lb-policies/rls.md">rls</a>  (one per RLS cluster specifier plugin)
    └── <a href="cds.md">cds</a>  (one per target cluster returned by the lookup server)
</pre>
<!-- /XDS-LB-TREE -->

`xds_cluster_impl` is the child of `outlier_detection` in a non-aggregate
cluster's subtree, and its child is `xds_override_host`.

## 2. Configuration

Proto: `XdsClusterImplLoadBalancingPolicyConfig` in
`grpc/service_config/service_config.proto`.

```json
{
  "xds_cluster_impl_experimental": {
    "clusterName": "cluster_a",
    "childPolicy": [ { "child_policy_name": {} } ]
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `clusterName` | string | Yes | — | The leaf cluster name. It MUST NOT change over the life of the policy instance. |
| `childPolicy` | LoadBalancingConfig list | Yes | — | Child policy (first supported entry). |

All other fields of `XdsClusterImplLoadBalancingPolicyConfig` in the proto are
deprecated and MUST be ignored.
<!-- REVIEW(divergence) [XDS_LB-2]: Java: config is not parseable from JSON at all (provider rejects service-config use; built in-process), and the policy is registered as "cluster_impl_experimental"; Go: JSON field "cluster" (matches service_config.proto), registered "xds_cluster_impl_experimental"; C++: JSON field "clusterName" (matches A74), registered "xds_cluster_impl_experimental". spec says: "clusterName" (A74 / C++). -->

### 2.1 Validation

The config is invalid, and is rejected as described in
[LB Policy Registry and Configuration](../../04-client-channel/05-load-balancing.md#2-lb-policy-registry-and-configuration),
if:

- `clusterName` is missing.
- `childPolicy` is missing, or is an invalid `LoadBalancingConfig` list (it
  has no supported entry, or its chosen entry is invalid).

### 2.2 Other Inputs

- **`XdsConfig` attribute:** the policy looks up `clusterName` in the
  `XdsConfig` ([Update](#32-update)) and uses these fields of the cluster
  resource and endpoint data:
  - the EDS service name (empty for LOGICAL_DNS clusters);
  - `max_concurrent_requests` (circuit breaking; default 1024);
  - the LRS server (`lrs_load_reporting_server`, or none) and the backend metric
    propagation config (`lrs_backend_metric_propagation`);
  - the EDS drop config (`drop_overloads`);
  - the upstream TLS config (`upstream_tls_context`);
  - `max_connections_per_subchannel` (connection scaling).
- **Per-endpoint attributes**, read when the child creates a subchannel: the
  endpoint's locality ([Load Reporting](#38-load-reporting)) and `hostname`
  ([Authority Rewriting](#39-authority-rewriting)).
- **XdsClient**, whose LRS client provides the drop stats and locality stats
  objects ([Load Reporting](#38-load-reporting)).
- **Channel credentials:** whether the channel was created with
  XdsCredentials ([Transport Security](#310-transport-security)).
- **Route call attribute**, read by the picker for `auto_host_rewrite`
  ([Authority Rewriting](#39-authority-rewriting)).

## 3. LB Policy Implementation

### 3.1 State

The `xds_cluster_impl` policy keeps:

- its child policy;
- the cluster data from the last update ([Other Inputs](#22-other-inputs));
- its reference to the process-wide circuit-breaker counter for (cluster name,
  EDS service name) ([Circuit Breaking](#37-circuit-breaking));
- its drop stats object, if the cluster has an LRS server
  ([Load Reporting](#38-load-reporting));
- the TLS configuration built from the cluster's `UpstreamTlsContext`, if
  XdsCredentials are in use ([Transport Security](#310-transport-security));
- the subchannels its child has created, whose `max_connections_per_subchannel`
  setting it updates ([Connection Scaling](#311-connection-scaling)).

### 3.2 Update

On each update, the `xds_cluster_impl` policy:

1. Looks up `clusterName` in the `XdsConfig`. The entry MUST be an OK
   `ClusterConfig` with an `EndpointConfig`. If not, the policy reports
   TRANSIENT_FAILURE with an INTERNAL status (this does not happen when the tree
   is generated by `cds`).
2. Applies the cluster data ([Other Inputs](#22-other-inputs)). It replaces its
   circuit-breaker counter and drop stats object when their keys change
   ([Circuit Breaking](#37-circuit-breaking), [Load Reporting](#38-load-reporting))
   and updates the connection scaling setting of existing subchannels
   ([Connection Scaling](#311-connection-scaling)).
3. Passes the update (endpoints, resolution note, and attributes) to its
   child (creating it on the first update), adding the cluster name as an
   attribute.

When it updates its child, it returns the child's status. It reports its
connectivity state and picker when the child reports
([Calls From Children](#52-calls-from-children)); if any drop category drops
100% of requests, it reports READY whatever the child reports
([Drops](#36-drops)).

### 3.3 ExitIdle

Forwarded to the child.

### 3.4 ResetBackoff

Forwarded to the child.

### 3.5 Shutdown

Shuts down the child and releases its drop stats object and its reference to
the circuit-breaker counter.

### 3.6 Drops

> **Introduced by:** [gRFC A27: xDS-Based Global Load Balancing](https://github.com/grpc/proposal/blob/master/A27-xds-global-load-balancing.md)

The EDS resource's `policy.drop_overloads` gives an ordered list of drop
categories. Each has a `category` name and a drop rate, normalized to
requests per million (see [ClusterLoadAssignment and LbEndpointCollection](../03-resources/05-endpoint.md)).
For every pick, before anything else:

```
for each category in drop_config, in order:
  if uniform_random(0, 1_000_000) < category.requests_per_million:
    record a drop for category.name (if load reporting is enabled)
    return DROP with status UNAVAILABLE "EDS-configured drop: <category>"
```

A drop result fails the RPC even if it is wait_for_ready, and the RPC is not
retried (see [Load Balancing](../../04-client-channel/05-load-balancing.md)). If
any category drops 100% of requests (`drop_all`), the policy MUST report READY
with its drop picker, whatever state the child reports (or whether it has
reported at all).

### 3.7 Circuit Breaking

> **Introduced by:** [gRFC A32: gRPC xDS circuit breaking](https://github.com/grpc/proposal/blob/master/A32-xds-circuit-breaking.md)

- The limit is the cluster's `max_concurrent_requests`: from the first
  `circuit_breakers.thresholds` entry with priority DEFAULT, its
  `max_requests`, and 1024 if not set (see
  [Cluster](../03-resources/04-cluster.md)).
- The in-flight request count is a **process-wide** counter keyed by
  (cluster name, EDS service name). All policy instances in all channels with
  the same key share it. Counters are reference-counted and created when
  first used. A policy gets a new counter only when its EDS service name
  changes. A change to the limit alone does not reset the count.
- After the drop check, the picker checks the counter. If
  `count >= max_concurrent_requests`, the pick returns DROP with status
  UNAVAILABLE (`circuit breaker drop`), and, if load reporting is enabled, the
  drop is recorded as an uncategorized drop (it counts in
  `total_dropped_requests`; see [Load Reporting (LRS)](../09-load-reporting.md)).
- Otherwise the pick is delegated to the child picker. When the child returns
  a completed pick, the picker MUST increment the counter **in the picker**.
  The counter is decremented when the call ends, whether or not the call was
  actually sent on a connection. (With connection scaling, a call may wait in
  the subchannel after the pick.)

### 3.8 Load Reporting

> **Introduced by:** [gRFC A27: xDS-Based Global Load Balancing](https://github.com/grpc/proposal/blob/master/A27-xds-global-load-balancing.md)

If the cluster has an LRS server (see [Load Reporting](../09-load-reporting.md)):

- The policy obtains a **drop stats** object from the XdsClient's LRS client
  for (LRS server, cluster name, EDS service name). It replaces this object
  when the LRS server or EDS service name changes. Drops (EDS categories and
  circuit breaker drops) are recorded there.
- When the child creates a subchannel, the policy's helper obtains a
  **locality stats** object for (LRS server, cluster name, EDS service name,
  the endpoint's locality attribute, the cluster's backend metric
  propagation config). A missing locality attribute means the empty
  locality. The policy wraps the subchannel and stores the stats object in
  the wrapper.
- When the child picker returns a completed pick, the picker unwraps the
  subchannel and records a call start on its locality stats. It attaches a
  call tracker that, when the call ends, records success (status OK) or error
  (any other status), together with the call's per-request ORCA backend
  metric report if any (see [ORCA](../../07-services/03-orca.md)). If the call
  ends without the tracker being notified, it is recorded as an error.
- Picks that fail or queue are not counted.

If load reporting is disabled, the wrapper still stores the locality name.

### 3.9 Authority Rewriting

> **Introduced by:** [gRFC A81: xDS Authority Rewriting](https://github.com/grpc/proposal/blob/master/A81-xds-authority-rewriting.md)

When the child creates a subchannel, the wrapper also stores the endpoint's
`hostname` attribute. On a completed pick, if the route call attribute (see
[Call attributes](../04-client.md)) has `auto_host_rewrite` set and the stored hostname is
not empty, the picker MUST set the RPC's `:authority` override to the
hostname. This override takes precedence over the channel's default authority
and over per-endpoint authority attributes, but not over an authority the
application set explicitly for the RPC (see
[Authority](../../04-client-channel/01-channel.md)). With TLS credentials, the
rewritten authority is subject to the per-RPC authority check (see
[TLS](../../06-security/01-tls.md)).

### 3.10 Transport Security

> **Introduced by:** [gRFC A29: xDS-Based Security for gRPC Clients and Servers](https://github.com/grpc/proposal/blob/master/A29-xds-tls-security.md)

If the channel was created with XdsCredentials, the policy builds the TLS
configuration from the cluster's `UpstreamTlsContext`: root certificate
provider and certificate name (or system root certificates), identity
certificate provider and certificate name, SAN matchers, and SNI settings. It
passes this to the subchannels that its child creates, so that XdsCredentials
can use it in the handshake. If XdsCredentials are not in use, this step is
skipped. See [xDS Security](../08-security.md).

### 3.11 Connection Scaling

> **Introduced by:** [gRFC A105: MAX_CONCURRENT_STREAMS Connection Scaling](https://github.com/grpc/proposal/blob/master/A105-max_concurrent_streams-connection-scaling.md)

If the parsed cluster's `max_connections_per_subchannel` is set (from
`max_connections` in its DEFAULT per-host circuit breaker thresholds), the
policy MUST apply that value as the `max_connections_per_subchannel` setting
of every subchannel its child creates. When a later update changes the value,
the policy MUST update the setting on existing subchannels without recreating
them. If the value is unset, the policy applies no setting, so the
subchannel's value comes from the service config, else defaults to 1. See
[Subchannels](../../04-client-channel/06-subchannels.md).

## 4. Picker Implementation

The policy's picker wraps the child's picker. It applies drops, circuit
breaking, load reporting, metric labels, and authority rewriting, in this
order:

```
def Pick(pick_args):
  apply drops (Drops); if a category drops the pick, return its DROP result
  if circuit_breaker.count >= max_concurrent_requests:
    return circuit breaker DROP (Circuit Breaking)
  result = child_picker.Pick(pick_args)
  if result is not COMPLETE:
    return result                     # failed and queued picks are not counted
  increment circuit_breaker.count; decrement it when the call ends
  wrapper = result.subchannel
  result.subchannel = wrapper.underlying_subchannel
  if load reporting is enabled:
    record a call start on wrapper.locality_stats and attach the call tracker
      (Load Reporting)
  set the grpc.lb.locality label (Picker Labels)
  if route attribute auto_host_rewrite is set and wrapper.hostname is not empty:
    set the :authority override to wrapper.hostname (Authority Rewriting)
  return result
```

### 4.1 Picker Labels

> **Introduced by:** [gRFC A78: gRPC OTel Metrics for WRR, Pick First, and XdsClient](https://github.com/grpc/proposal/blob/master/A78-grpc-metrics-wrr-pf-xds.md)

- The picker sets the `grpc.lb.locality` optional label on the call attempt
  to the locality name string (`{region="…", zone="…", sub_zone="…"}`) of the
  chosen subchannel. It sets the empty string if there is no locality.
- `grpc.lb.backend_service` is set by `cds` ([Picker Implementation](cds.md#4-picker-implementation)).

## 5. Children and Subchannels

### 5.1 Child Policies

The policy has a single child, created from `childPolicy` on the first update.
The child receives the update's endpoints, resolution note, and attributes,
plus the cluster name attribute ([Update](#32-update)). `ExitIdle()`,
`ResetBackoff()`, and `Shutdown()` are forwarded to it
([ExitIdle](#33-exitidle), [ResetBackoff](#34-resetbackoff),
[Shutdown](#35-shutdown)).

### 5.2 Calls From Children

- `UpdateState(state, status, picker)`: reports the child's state and status
  with a picker that wraps the child's picker
  ([Picker Implementation](#4-picker-implementation)). If any drop category
  drops 100% of requests, the policy reports READY whatever the child reports
  ([Drops](#36-drops)).
- `RequestReresolution()`: forwarded to the policy's own helper.
- `CreateSubchannel(address, attributes)`: creates the subchannel through the
  policy's own helper, adding the transport security configuration
  ([Transport Security](#310-transport-security)) and the
  `max_connections_per_subchannel` setting
  ([Connection Scaling](#311-connection-scaling)). Returns a wrapper that
  stores the locality stats object or locality name
  ([Load Reporting](#38-load-reporting)) and the endpoint's `hostname`
  ([Authority Rewriting](#39-authority-rewriting)). The picker unwraps the
  subchannel in pick results.

### 5.3 Subchannels

The policy does not create subchannels itself or watch their connectivity or
health; its descendants do. It wraps the subchannels they create
([Calls From Children](#52-calls-from-children)), and state updates reach the
descendants' watchers unchanged. It updates the
`max_connections_per_subchannel` setting of these subchannels when the
cluster's value changes ([Connection Scaling](#311-connection-scaling)).

## 6. Metrics

The policy records no metrics. Its picker sets the `grpc.lb.locality` label
([Picker Labels](#41-picker-labels)).

## 7. API Requirements

- gRPC MUST register this policy in the LB policy registry under the name `xds_cluster_impl_experimental` so that the configuration generated by the xDS client data plane can select it.
- This policy is internal to xDS support. Applications are not expected to configure it directly, and gRPC is not required to provide any public API specific to it beyond the general LB policy API requirements in [xDS LB Policies: API Requirements](../05-lb-policies.md#3-api-requirements).
