> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `weighted_target` LB Policy

<!-- Sources: A28 (weighted target LB policy), A56 (hierarchical addresses), A78 (locality attribute), grpc/service_config/service_config.proto (WeightedTargetLoadBalancingPolicyConfig) -->

> **Experimental:** The policy is registered as
> `weighted_target_experimental`. Its name and configuration are not yet
> stable.

> **Introduced by:** [gRFC A28: gRPC xDS traffic splitting and routing](https://github.com/grpc/proposal/blob/master/A28-xds-traffic-splitting-and-routing.md)

## 1. Overview

`weighted_target` is a parent policy (see
[Policy Hierarchy](../05-load-balancing.md#9-policy-hierarchy)) with named,
weighted children. It spreads calls randomly across its READY children in
proportion to their weights. xDS uses it to pick a locality within a
priority (see [xDS LB Policies](../../09-xds/05-lb-policies.md)), but it is
not xDS-specific. Only READY children get calls when any child is READY.
This differs from Envoy's weighted clusters, which also count children
that are not READY.

Registered name: `weighted_target_experimental`.

## 2. Configuration

Proto: `WeightedTargetLoadBalancingPolicyConfig` in
`grpc/service_config/service_config.proto`.

```json
{
  "weighted_target_experimental": {
    "targets": {
      "localityA": { "weight": 3, "childPolicy": [ { "round_robin": {} } ] },
      "localityB": { "weight": 1, "childPolicy": [ { "round_robin": {} } ] }
    }
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `targets` | map of string → object | No | empty map | The children. The map key is the child's name, which is its identity across updates. |
| `targets{}.weight` | uint32 | Yes | — | The child's weight. MUST be greater than 0. |
| `targets{}.childPolicy` | `LoadBalancingConfig list` | Yes | — | The child's policy. Resolved as specified in [LB Policy Registry and Configuration](../05-load-balancing.md#2-lb-policy-registry-and-configuration). |

### 2.1 Validation

The config is invalid, and is rejected as specified in
[LB Policy Registry and Configuration](../05-load-balancing.md#2-lb-policy-registry-and-configuration),
if any of the following holds:

- A target's `weight` is missing or zero.
- A target's `childPolicy` is missing, or is an invalid
  `LoadBalancingConfig` list (no entry names a registered policy, or the
  selected policy rejects its config).

## 3. Updates and Child Management

On each update, the policy:

1. Splits the endpoints by hierarchical path (the first path element is
   the target name, removed before passing down; see
   [Hierarchical Address Paths](../05-load-balancing.md#94-hierarchical-address-paths)).
2. For each target in the config, creates the child if needed, or
   updates the existing child of that name. The update contains the
   child's config, its endpoints, the resolution note, and the
   top-level attributes plus a **locality-name attribute** set to the
   target name. Policies below can use this attribute, for example as
   the `grpc.lb.locality` label in `weighted_round_robin` metrics. If a
   child's policy name changed, the graceful-switch procedure is used.
3. Deletes children whose names are no longer in `targets` (see
   below).
4. After all children are updated, computes and reports its aggregate
   state and picker once.

**Removed children.** A child whose name is no longer in `targets` is
deleted immediately, when the update is applied. It is not retained. If a
later update adds the name back, a new child is created.

<!-- REVIEW(divergence) [WEIGHTED_TARGET-1]: Java and Go delete removed children immediately (grpc-java WeightedTargetLoadBalancer shutdown, with "TODO cache removed target for 15 minutes"; grpc-go balancer/weightedtarget/weightedtarget.go SubBalancerCloseTimeout: 0, "Disable caching of removed child policies"). C++ deactivates them and deletes them after 15 minutes (src/core/load_balancing/weighted_target/weighted_target.cc DeactivateLocked, kChildRetentionInterval). gRFC A28 says "When a child policy is removed, it will be cached for 15 minutes." The spec now says immediate deletion, following the Java/Go majority. This is consistent with priority.md. -->

## 4. Connectivity State

The aggregate state is computed over all children with the normal
rules (first match wins): READY if any child is READY; otherwise
CONNECTING if any is CONNECTING; otherwise IDLE if any is IDLE; otherwise
TRANSIENT_FAILURE (including when there are no children).

## 5. Picker

In READY and TRANSIENT_FAILURE, the picker does a weighted random choice
among the children that are in the aggregate state, and delegates to the
chosen child's picker. In CONNECTING and IDLE, it queues:

| Aggregate state | Children in the picker | Behavior |
| --- | --- | --- |
| READY | READY children | Weighted random choice, delegated to the child's picker. |
| CONNECTING | — | Queue. |
| IDLE | — | Queue. The picker MUST also schedule a call to the policy's `ExitIdle()`, which is forwarded to all children (see [Triggering Work From a Picker](../05-load-balancing.md#63-triggering-work-from-a-picker)), so that IDLE children are not left idle with RPCs queued. |
| TRANSIENT_FAILURE | TRANSIENT_FAILURE children | Weighted random choice, delegated, so that the call fails with a child's error. If there are no children, fail with `UNAVAILABLE` and a message saying that there are no children. |

```
NewPicker(children):                      # children in the aggregate state
  cumulative = []; total = 0
  for c in children:
    total += c.weight
    cumulative.append((total, c))

Pick(args):
  r = random_uniform_integer(0, total)    # in [0, total)
  c = first entry in cumulative with r < entry.total   # binary search
  return c.picker.Pick(args)
```

## 6. LB Policy API

The policy implements the generic
[LB Policy API](../05-load-balancing.md#4-lb-policy-api) and the
[Helper API](../05-load-balancing.md#5-helper-api) it provides to its
children as follows:

| Operation | Behavior |
| --- | --- |
| `Update(update) → status` | Creates, updates, and deletes children by target name and routes endpoints to them by hierarchical path, then reports its state and picker once ([Updates and Child Management](#3-updates-and-child-management)). Each child receives the resolution note and the top-level attributes plus the locality-name attribute. If the endpoints field is an error, the error is passed to every child. Returns a status that combines the children's statuses. |
| `ExitIdle()` | Forwarded to all children. |
| `ResetBackoff()` | Forwarded to all children. |
| `Shutdown()` | Deletes all children. |
| Subchannel connectivity / health updates | Not applicable: the policy does not create or watch subchannels; its children do. |
| Child `UpdateState(state, status, picker)` | Records the child's state and picker, recomputes the aggregate state ([Connectivity State](#4-connectivity-state)), and reports a new picker ([Picker](#5-picker)). While an update is being applied to the children, the aggregate is reported only once, after all children are updated. |
| Child `RequestReresolution()` | Forwarded to the policy's own helper. |
| Child `CreateSubchannel(address, attributes)` | Passed through to the policy's own helper unchanged. |

## 7. API Requirements

- gRPC MUST register this policy under the name
  `weighted_target_experimental`, so that it can be selected through
  `loadBalancingConfig` in the service config and used as a child by other
  policies, including custom ones
  ([Load Balancing](../05-load-balancing.md)).
