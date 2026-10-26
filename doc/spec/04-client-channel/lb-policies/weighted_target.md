> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `weighted_target` LB Policy

<!-- Sources: A28 (weighted target LB policy), A56 (hierarchical addresses), A78 (locality attribute), grpc/service_config/service_config.proto (WeightedTargetLoadBalancingPolicyConfig) -->

> **Experimental:** The policy is registered as
> `weighted_target_experimental`. Its name and configuration are not yet
> stable.

## 1. Purpose

`weighted_target` is a parent policy with named, weighted children. It
spreads calls randomly across its READY children in proportion to their
weights. xDS uses it to pick a locality within a priority (see
[../../09-xds/lb-policies.md](../../09-xds/lb-policies.md)), but it is
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

| Field (JSON) | Type | Validation |
| --- | --- | --- |
| `targets` | map of name → Target | The children. The name is the child's identity across updates. |
| `targets[].weight` | uint32 | Required. MUST be greater than 0. A missing or zero weight makes the config invalid. |
| `targets[].childPolicy` | `LoadBalancingConfig` list | Required. Resolved as specified in [../load-balancing.md](../load-balancing.md). |

## 3. Updates and Child Management

On each update, the policy:

1. Splits the endpoints by hierarchical path (the first path element is
   the target name, removed before passing down).
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
| IDLE | — | Queue. The picker MUST also schedule a call to the policy's `ExitIdle()`, which is forwarded to all children (see [../load-balancing.md](../load-balancing.md)), so that IDLE children are not left idle with RPCs queued. |
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

## 6. Other Operations

- **Re-resolution:** forward children's requests to the parent.
- **`ExitIdle()`:** forward to all children.
- **`ResetBackoff()`:** forward to all children.
- **`Shutdown()`:** delete all children.

## 7. API Requirements

- gRPC MUST register this policy under the name
  `weighted_target_experimental`, so that it can be selected through
  `loadBalancingConfig` in the service config and used as a child by other
  policies, including custom ones
  ([../load-balancing.md](../load-balancing.md)).
