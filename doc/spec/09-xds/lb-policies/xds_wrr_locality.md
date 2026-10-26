> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `xds_wrr_locality` LB Policy

<!-- Sources: A52, grpc-proto grpc/service_config/service_config.proto -->

> **Experimental:** This policy is registered as `xds_wrr_locality_experimental`.

> **Introduced by:** [gRFC A52: gRPC xDS Custom Load Balancer Configuration](https://github.com/grpc/proposal/blob/master/A52-xds-custom-lb-policies.md)

## 1. Overview

The `xds_wrr_locality` policy weights the localities of a cluster priority by
their locality weights and delegates endpoint picking within each locality to
a configured child policy. It does this by generating a `weighted_target`
config with one target per locality and running a single `weighted_target`
child with that config. The xDS LB policy registry produces its config (see
[xDS LB Policy Registry](../06-lb-policies.md#2-xds-lb-policy-registry)).

The `xds_wrr_locality` policy is a parent policy with a single child (see
[Policy Hierarchy](../../04-client-channel/06-load-balancing.md#9-policy-hierarchy)).

Registered name: `xds_wrr_locality_experimental`.

### 1.1 Position in the xDS LB Policy Tree

<!-- XDS-LB-TREE: generated; identical in every xDS LB policy document except for the highlighted policy -->
<pre>
<a href="xds_cluster_manager.md">xds_cluster_manager</a>  (one child per cluster and per cluster specifier plugin)
├── <a href="cds.md">cds</a>  (one per cluster)
│   ├── non-aggregate cluster (EDS or LOGICAL_DNS):
│   │   └── <a href="../../04-client-channel/lb-policies/outlier_detection.md">outlier_detection</a>
│   │       └── <a href="xds_cluster_impl.md">xds_cluster_impl</a>
│   │           └── <a href="xds_override_host.md">xds_override_host</a>
│   │               └── <a href="../../04-client-channel/lb-policies/priority.md">priority</a>  (one child per EDS priority)
│   │                   ├── <b><a href="xds_wrr_locality.md">xds_wrr_locality</a>  ◀ this policy</b>  (default; see <a href="../06-lb-policies.md#2-xds-lb-policy-registry">xDS LB Policy Registry</a>)
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

`xds_wrr_locality` is the default child of each priority under a cluster's
`priority` policy (it is what the xDS LB Policy Registry produces by default),
and its child is a `weighted_target` policy with one child per locality.

## 2. Configuration

Proto: `XdsWrrLocalityLoadBalancingPolicyConfig` in
`grpc/service_config/service_config.proto`.

```json
{
  "xds_wrr_locality_experimental": {
    "childPolicy": [ { "child_policy_name": {} } ]
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `childPolicy` | LoadBalancingConfig list | Yes | — | The endpoint-picking policy used for each locality. |

### 2.1 Validation

The config is invalid, and is rejected as described in
[LB Policy Registry and Configuration](../../04-client-channel/06-load-balancing.md#2-lb-policy-registry-and-configuration),
if:

- `childPolicy` is missing, or is an invalid `LoadBalancingConfig` list (it
  has no supported entry, or its chosen entry is invalid).

### 2.2 Other Inputs

| Input | Location | Default | Used for |
| --- | --- | --- | --- |
| Locality | Endpoint attribute locality, set by `cds` (see [Endpoint List and Attributes](cds.md#endpoint-list-and-attributes)) | — | Endpoints without a locality are left out of the generated targets ([Child Config Generation](#child-config-generation)). |
| Locality name string | Endpoint attribute locality name string, set by `cds` (see [Endpoint List and Attributes](cds.md#endpoint-list-and-attributes)) | — | The `weighted_target` target name ([Child Config Generation](#child-config-generation)). |
| Locality weight | Endpoint attribute locality weight, set by `cds` (see [Endpoint List and Attributes](cds.md#endpoint-list-and-attributes)) | — | The `weighted_target` target weight; endpoints whose locality weight is 0 are left out ([Child Config Generation](#child-config-generation)). |

## 3. LB Policy Implementation

### 3.1 Internal State

The policy keeps its `weighted_target` child policy.

### 3.2 Features

#### Child Config Generation

The policy builds the `weighted_target` config from the endpoint list:

```
targets = {}
for endpoint in update.endpoints:
  name = endpoint.locality_name_string; w = endpoint.locality_weight
  if endpoint has a locality and w > 0:
    if name not in targets: targets[name] = w
    elif targets[name] != w: log an error; keep the first weight
child_config = [ { "weighted_target_experimental": { "targets": {
    name: { "weight": w, "childPolicy": config.childPolicy } for name, w in targets
} } } ]
```

Endpoints reach their locality's child through the second element of their
hierarchical path (see
[Endpoint List and Attributes](cds.md#endpoint-list-and-attributes)). See
[weighted_target](../../04-client-channel/lb-policies/weighted_target.md).

### 3.3 Updates from the Parent

On each update, the policy builds a `weighted_target` config from the endpoint
list ([Child Config Generation](#child-config-generation)) and passes the
update (endpoints, resolution note, attributes) to a single `weighted_target`
child with that config, creating the child on the first update. If the
generated config fails to parse, the policy reports TRANSIENT_FAILURE with an
INTERNAL status. When it updates its child, it returns the child's status.

### 3.4 ExitIdle

Forwarded to the child.

### 3.5 ResetBackoff

Forwarded to the child.

### 3.6 Shutdown

Shuts down the child.

## 4. Picker Implementation

Not applicable: the policy reports its child's picker unchanged.

## 5. Children and Subchannels

### 5.1 Child Policies

The policy has a single `weighted_target` child with the generated config
([Child Config Generation](#child-config-generation)). It receives the
update's endpoints, resolution note, and attributes ([Update](#33-updates-from-the-parent)).
`ExitIdle()`, `ResetBackoff()`, and `Shutdown()` are forwarded to it
([ExitIdle](#34-exitidle), [ResetBackoff](#35-resetbackoff),
[Shutdown](#36-shutdown)).

### 5.2 Calls From Children

- `UpdateState(state, status, picker)`: reports the child's state, status, and
  picker unchanged.
- `RequestReresolution()`: forwarded to the policy's own helper.
- `CreateSubchannel(address, attributes)`: passed through to the policy's own
  helper unchanged.

### 5.3 Subchannels

Not applicable: the policy does not create or watch subchannels; its
descendants do.

## 6. Metrics

The policy records no metrics.

## 7. API Requirements

- gRPC MUST register this policy in the LB policy registry under the name `xds_wrr_locality_experimental` so that the configuration generated by the xDS client data plane can select it.
- This policy is internal to xDS support. Applications are not expected to configure it directly, and gRPC is not required to provide any public API specific to it beyond the general LB policy API requirements in [xDS LB Policies: API Requirements](../06-lb-policies.md#3-api-requirements).
