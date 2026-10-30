> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `xds_cluster_manager` LB Policy

<!-- Sources: A28, A31, A74, grpc-proto grpc/service_config/service_config.proto -->

> **Experimental:** This policy is registered as `xds_cluster_manager_experimental`.

> **Introduced by:** [gRFC A31: gRPC xDS Timeout Support and Config Selector Design](https://github.com/grpc/proposal/blob/master/A31-xds-timeout-support-and-config-selector.md)

## 1. Overview

The `xds_cluster_manager` policy is the top-level policy of the LB policy
config that the xds resolver generates (see
[Generated service config](../04-client.md#41-generated-service-config)). It
keeps one named child per cluster or cluster specifier plugin that the
resolver references, and routes each pick to the child selected by the xDS
ConfigSelector for the RPC.

The `xds_cluster_manager` policy is a parent policy with named children (see
[Parents With Named Children](../../04-client-channel/05-load-balancing.md#93-parents-with-named-children)).

Registered name: `xds_cluster_manager_experimental`.

### 1.1 Position in the xDS LB Policy Tree

<!-- XDS-LB-TREE: generated; identical in every xDS LB policy document except for the highlighted policy -->
<pre>
<b><a href="xds_cluster_manager.md">xds_cluster_manager</a>  ◀ this policy</b>  (one child per cluster and per cluster specifier plugin)
├── <a href="cds.md">cds</a>  (one per cluster)
│   ├── non-aggregate cluster (EDS or LOGICAL_DNS):
│   │   └── <a href="../../04-client-channel/lb-policies/outlier_detection.md">outlier_detection</a>
│   │       └── <a href="xds_cluster_impl.md">xds_cluster_impl</a>
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

`xds_cluster_manager` is the top-level policy, selected by the service config
that the xds resolver generates. Its children are one `cds` policy per cluster
that the route configuration references and one policy per cluster specifier
plugin (an `rls` policy for the RLS plugin).

## 2. Configuration

Proto: `XdsClusterManagerLoadBalancingPolicyConfig` in
`grpc/service_config/service_config.proto`.

```json
{
  "xds_cluster_manager_experimental": {
    "children": {
      "cluster:cluster_a": {
        "childPolicy": [ { "cds_experimental": { "cluster": "cluster_a" } } ]
      }
    }
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `children` | map of string → object | Yes | — | The children, keyed by child name. |
| `children{}.childPolicy` | LoadBalancingConfig list | Yes | — | The child's policy. Parsed by choosing the first supported entry, as for any `loadBalancingConfig` list. |

### 2.1 Validation

The whole config is invalid, and is rejected as described in
[LB Policy Registry and Configuration](../../04-client-channel/05-load-balancing.md#2-lb-policy-registry-and-configuration),
if:

- `children` is missing.
- A child has no `childPolicy`.
- A child's `childPolicy` has no supported entry, or its chosen entry is
  invalid.

### 2.2 Other Inputs

The policy does not interpret the update's endpoints, resolution note, or
attributes; it passes them to its children ([Update](#32-update)). The picker
reads the cluster call attribute set by the xDS ConfigSelector
([Picker Implementation](#4-picker-implementation)).

## 3. LB Policy Implementation

### 3.1 State

The policy keeps a map of children keyed by child name. For each child it
keeps:

- the child policy;
- the child's most recently reported state and picker;
- whether the child is active or deactivated, and, for a deactivated child,
  its retention timer ([Child Deactivation and Retention](#36-child-deactivation-and-retention)).

It also tracks whether an update is being passed to the children, during which
it does not report pickers.

### 3.2 Update

The policy keeps one child policy per entry in `children`, keyed by child
name. On each update, it creates children that are new and updates the
existing ones, passing each child the update's endpoints, resolution note,
and attributes ([Child Policies](#51-child-policies)). Children not in the new
config are deactivated, and deactivated children named again are reactivated
([Child Deactivation and Retention](#36-child-deactivation-and-retention)).

While an update is being passed to the children, the policy SHOULD NOT
report intermediate pickers. It reports one picker after all children have
been updated, with its aggregate state
([Calls From Children](#52-calls-from-children)).

It combines the statuses returned by its children into its own returned
status.

### 3.3 ExitIdle

Forwarded to every active child.

### 3.4 ResetBackoff

Forwarded to every child, including deactivated children.

### 3.5 Shutdown

Shuts down every child, including deactivated children, and cancels their
retention timers.

### 3.6 Child Deactivation and Retention

Children not in the new config are **deactivated**. A deactivated child is
left out of the picker and of the aggregated state. It SHOULD be kept for 15
minutes and then destroyed. If a later config names it again within that
time, it is reactivated.
<!-- REVIEW(divergence) [XDS_LB-3]: retention of removed children (no gRFC specifies one). Java: 15-minute deletion timer (ClusterManagerLoadBalancer.java); Go: removed immediately, caching disabled (SubBalancerCloseTimeout 0, internal/xds/balancer/clustermanager/clustermanager.go); C++: 15 minutes (kChildRetentionInterval, xds_cluster_manager.cc). spec says: SHOULD keep 15 minutes (majority). With two-phase cluster removal ([Cluster references and two-phase removal](../04-client.md#54-cluster-references-and-two-phase-removal)) a removed child can no longer be selected by any RPC, so retention only helps if the cluster comes back. Also note Java registers this policy as "cluster_manager_experimental", not "xds_cluster_manager_experimental". -->

## 4. Picker Implementation

The picker reads the cluster call attribute set by the xDS ConfigSelector
(see [Call attributes](../04-client.md)) and delegates the pick to that child's
current picker. A child that has not reported a picker yet uses a picker that
queues. If the attribute is missing or names no active child, the pick MUST
fail with status INTERNAL. The ordering guarantees in
[Cluster references and two-phase removal](../04-client.md) mean that this
should never happen.

## 5. Children and Subchannels

### 5.1 Child Policies

The policy has one child per entry in `children`, keyed by child name, with
that entry's `childPolicy`. Each child receives the update's endpoints,
resolution note, and attributes. Children named `cluster:<name>` run a `cds`
policy; children named `cluster_specifier_plugin:<name>` run the policy
produced by a cluster specifier plugin, such as
[`rls`](../../04-client-channel/lb-policies/rls.md)
(see [Generated service config](../04-client.md#41-generated-service-config)).
The policy itself does not interpret child names.

`ExitIdle()` is forwarded to every active child; `ResetBackoff()` and
`Shutdown()` are forwarded to every child, including deactivated children
([ExitIdle](#33-exitidle), [ResetBackoff](#34-resetbackoff),
[Shutdown](#35-shutdown)).

### 5.2 Calls From Children

- `UpdateState(state, status, picker)`: records the child's state and picker.
  If the child is active and no update is being passed to the children, the
  policy recomputes its aggregate state and reports it with a new picker
  ([Picker Implementation](#4-picker-implementation)). A deactivated child's
  state and picker are not used.

  Connectivity state is aggregated over the active children using the standard
  rules (see [Load Balancing](../../04-client-channel/05-load-balancing.md)):
  READY if any child is READY; else CONNECTING if any is CONNECTING; else IDLE
  if any is IDLE; else TRANSIENT_FAILURE (status UNAVAILABLE).
- `RequestReresolution()`: forwarded to the policy's own helper.
- `CreateSubchannel(address, attributes)`: passed through to the policy's own
  helper unchanged.

### 5.3 Subchannels

Not applicable: the policy does not create or watch subchannels; its children
do.

## 6. Metrics

The policy records no metrics.

## 7. API Requirements

- gRPC MUST register this policy in the LB policy registry under the name `xds_cluster_manager_experimental` so that the configuration generated by the xDS client data plane can select it.
- This policy is internal to xDS support. Applications are not expected to configure it directly, and gRPC is not required to provide any public API specific to it beyond the general LB policy API requirements in [xDS LB Policies: API Requirements](../05-lb-policies.md#3-api-requirements).
