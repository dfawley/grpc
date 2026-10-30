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
[xDS LB Policy Registry](../05-lb-policies.md#2-xds-lb-policy-registry)).

The `xds_wrr_locality` policy is a parent policy with a single child (see
[Policy Hierarchy](../../04-client-channel/05-load-balancing.md#9-policy-hierarchy)).

Registered name: `xds_wrr_locality_experimental`.

### 1.1 Position in the xDS LB Policy Tree

<!-- XDS-LB-TREE: generated; identical in every xDS LB policy document except for the highlighted policy -->
- [`xds_cluster_manager`](xds_cluster_manager.md): one child per cluster and per cluster specifier plugin
  - [`cds`](cds.md): one per cluster
    - Non-aggregate cluster (EDS or LOGICAL_DNS):
      - [`outlier_detection`](../../04-client-channel/lb-policies/outlier_detection.md)
        - [`xds_cluster_impl`](xds_cluster_impl.md)
          - [`xds_override_host`](xds_override_host.md)
            - [`priority`](../../04-client-channel/lb-policies/priority.md): one child per EDS priority
              - The cluster's xDS LB policy ([xDS LB Policy Registry](../05-lb-policies.md#2-xds-lb-policy-registry)); by default:
                - **[`xds_wrr_locality`](xds_wrr_locality.md) (this policy)**
                  - [`weighted_target`](../../04-client-channel/lb-policies/weighted_target.md): one child per locality
                    - Endpoint picking policy, e.g. [`round_robin`](../../04-client-channel/lb-policies/round_robin.md), [`weighted_round_robin`](../../04-client-channel/lb-policies/weighted_round_robin.md), or [`least_request`](../../04-client-channel/lb-policies/least_request.md)
                      - [`pick_first`](../../04-client-channel/lb-policies/pick_first.md): one per endpoint
              - Or another converted policy, e.g. [`ring_hash`](../../04-client-channel/lb-policies/ring_hash.md) or [`random_subsetting`](../../04-client-channel/lb-policies/random_subsetting.md)
    - Aggregate cluster:
      - [`priority`](../../04-client-channel/lb-policies/priority.md): one child per leaf cluster
        - [`cds`](cds.md): one per leaf cluster, each building the non-aggregate subtree above
  - [`rls`](../../04-client-channel/lb-policies/rls.md): one per RLS cluster specifier plugin
    - [`cds`](cds.md): one per target cluster returned by the lookup server
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
    "childPolicy": [ { "round_robin": {} } ]
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `childPolicy` | LoadBalancingConfig list | Yes | — | The endpoint-picking policy used for each locality. |

### 2.1 Validation

The config is invalid, and is rejected as described in
[LB Policy Registry and Configuration](../../04-client-channel/05-load-balancing.md#2-lb-policy-registry-and-configuration),
if:

- `childPolicy` is missing, or is an invalid `LoadBalancingConfig` list (it
  has no supported entry, or its chosen entry is invalid).

## 3. Child config generation

On each update, the policy builds a `weighted_target` config from the
endpoint list:

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

It passes the update (endpoints, resolution note, attributes) to a single
`weighted_target` child with that config. Endpoints reach their locality's
child through the second element of their hierarchical path (see
[Endpoint list and attributes](cds.md#5-endpoint-list-and-attributes)). The policy reports the child's
state and picker unchanged. If the generated config fails to parse, the policy
reports TRANSIENT_FAILURE with an INTERNAL status. See
[weighted_target](../../04-client-channel/lb-policies/weighted_target.md).

## 4. LB Policy API

The `xds_wrr_locality` policy implements the generic
[LB Policy API](../../04-client-channel/05-load-balancing.md#4-lb-policy-api) and
uses the [Helper API](../../04-client-channel/05-load-balancing.md#5-helper-api) as
follows:

| Operation | Behavior |
| --- | --- |
| `Update(update) → status` | Builds the `weighted_target` config from the endpoint list and passes the update (endpoints, resolution note, attributes) to its `weighted_target` child, creating the child on the first update ([Child config generation](#3-child-config-generation)). If the generated config fails to parse, it reports TRANSIENT_FAILURE with an INTERNAL status. When it updates its child, it returns the child's status. |
| `ExitIdle()` | Forwarded to the child. |
| `ResetBackoff()` | Forwarded to the child. |
| `Shutdown()` | Shuts down the child. |
| Subchannel connectivity / health updates | Not applicable: the policy does not create or watch subchannels; its descendants do. |
| Child `UpdateState(state, status, picker)` | Reports the child's state, status, and picker unchanged. |
| Child `RequestReresolution()` | Forwarded to the policy's own helper. |
| Child `CreateSubchannel(address, attributes)` | Passed through to the policy's own helper unchanged. |

## 5. API Requirements

- gRPC MUST register this policy in the LB policy registry under the name `xds_wrr_locality_experimental` so that the configuration generated by the xDS client data plane can select it.
- This policy is internal to xDS support. Applications are not expected to configure it directly, and gRPC is not required to provide any public API specific to it beyond the general LB policy API requirements in [xDS LB Policies: API Requirements](../05-lb-policies.md#3-api-requirements).
