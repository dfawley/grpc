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
([Child config for a non-aggregate cluster](cds.md#6-child-config-for-a-non-aggregate-cluster)).

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
    "childPolicy": [ { "round_robin": {} } ]
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

## 3. Cluster data

The policy looks up `clusterName` in the `XdsConfig`. The entry MUST be an OK
`ClusterConfig` with an `EndpointConfig`. If not, the policy reports
TRANSIENT_FAILURE with an INTERNAL status (this does not happen when the tree
is generated by `cds`). It uses these fields of the cluster resource and
endpoint data:

- the EDS service name (empty for LOGICAL_DNS clusters);
- `max_concurrent_requests` (circuit breaking; default 1024);
- the LRS server (`lrs_load_reporting_server`, or none) and the backend metric
  propagation config (`lrs_backend_metric_propagation`);
- the EDS drop config (`drop_overloads`);
- the upstream TLS config (`upstream_tls_context`);
- `max_connections_per_subchannel` (connection scaling).

It passes the update to its child (creating it on the first update), adding
the cluster name as an attribute.

## 4. Drops

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

## 5. Circuit breaking

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

## 6. Load reporting

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

## 7. Picker labels

> **Introduced by:** [gRFC A78: gRPC OTel Metrics for WRR, Pick First, and XdsClient](https://github.com/grpc/proposal/blob/master/A78-grpc-metrics-wrr-pf-xds.md)

- The picker sets the `grpc.lb.locality` optional label on the call attempt
  to the locality name string (`{region="…", zone="…", sub_zone="…"}`) of the
  chosen subchannel. It sets the empty string if there is no locality.
- `grpc.lb.backend_service` is set by `cds` ([Update handling](cds.md#3-update-handling)).

## 8. Authority rewriting

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

## 9. Transport security

> **Introduced by:** [gRFC A29: xDS-Based Security for gRPC Clients and Servers](https://github.com/grpc/proposal/blob/master/A29-xds-tls-security.md)

If the channel was created with XdsCredentials, the policy builds the TLS
configuration from the cluster's `UpstreamTlsContext`: root certificate
provider and certificate name (or system root certificates), identity
certificate provider and certificate name, SAN matchers, and SNI settings. It
passes this to the subchannels that its child creates, so that XdsCredentials
can use it in the handshake. If XdsCredentials are not in use, this step is
skipped. See [xDS Security](../08-security.md).

## 10. Connection scaling

> **Introduced by:** [gRFC A105: MAX_CONCURRENT_STREAMS Connection Scaling](https://github.com/grpc/proposal/blob/master/A105-max_concurrent_streams-connection-scaling.md)

If the parsed cluster's `max_connections_per_subchannel` is set (from
`max_connections` in its DEFAULT per-host circuit breaker thresholds), the
policy MUST apply that value as the `max_connections_per_subchannel` setting
of every subchannel its child creates. When a later update changes the value,
the policy MUST update the setting on existing subchannels without recreating
them. If the value is unset, the policy applies no setting, so the
subchannel's value comes from the service config, else defaults to 1. See
[Subchannels](../../04-client-channel/06-subchannels.md).

## 11. LB Policy API

The `xds_cluster_impl` policy implements the generic
[LB Policy API](../../04-client-channel/05-load-balancing.md#4-lb-policy-api) and
uses the [Helper API](../../04-client-channel/05-load-balancing.md#5-helper-api) as
follows:

| Operation | Behavior |
| --- | --- |
| `Update(update) → status` | Looks up `clusterName` in the `XdsConfig` and applies the cluster data ([Cluster data](#3-cluster-data)); if the entry is not an OK `ClusterConfig` with an `EndpointConfig`, it reports TRANSIENT_FAILURE with an INTERNAL status. It replaces its circuit-breaker counter and drop stats object when their keys change ([Circuit breaking](#5-circuit-breaking), [Load reporting](#6-load-reporting)) and updates the connection scaling setting of existing subchannels ([Connection scaling](#10-connection-scaling)). It passes the update (endpoints, resolution note, and attributes, plus the cluster name attribute) to its child, creating the child on the first update. When it updates its child, it returns the child's status. |
| `ExitIdle()` | Forwarded to the child. |
| `ResetBackoff()` | Forwarded to the child. |
| `Shutdown()` | Shuts down the child and releases its drop stats object and its reference to the circuit-breaker counter. |
| Subchannel connectivity / health updates | Not applicable: the policy does not create or watch subchannels; its descendants do. The policy wraps the subchannels they create, and state updates reach the descendants' watchers unchanged. |
| Child `UpdateState(state, status, picker)` | Reports the child's state and status with a picker that wraps the child's picker. The wrapping picker applies drops, circuit breaking, load reporting, metric labels, and authority rewriting ([Drops](#4-drops) through [Authority rewriting](#8-authority-rewriting)). If any drop category drops 100% of requests, the policy reports READY whatever the child reports ([Drops](#4-drops)). |
| Child `RequestReresolution()` | Forwarded to the policy's own helper. |
| Child `CreateSubchannel(address, attributes)` | Creates the subchannel through the policy's own helper, adding the transport security configuration ([Transport security](#9-transport-security)) and the `max_connections_per_subchannel` setting ([Connection scaling](#10-connection-scaling)). Returns a wrapper that stores the locality stats object or locality name ([Load reporting](#6-load-reporting)) and the endpoint's `hostname` ([Authority rewriting](#8-authority-rewriting)). The picker unwraps the subchannel in pick results. |

## 12. API Requirements

- gRPC MUST register this policy in the LB policy registry under the name `xds_cluster_impl_experimental` so that the configuration generated by the xDS client data plane can select it.
- This policy is internal to xDS support. Applications are not expected to configure it directly, and gRPC is not required to provide any public API specific to it beyond the general LB policy API requirements in [xDS LB Policies: API Requirements](../05-lb-policies.md#3-api-requirements).
