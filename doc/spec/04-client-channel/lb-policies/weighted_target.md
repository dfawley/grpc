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
[Policy Hierarchy](../06-load-balancing.md#9-policy-hierarchy)) with named,
weighted children. It spreads calls randomly across its READY children in
proportion to their weights. xDS uses it to pick a locality within a
priority (see [xDS LB Policies](../../09-xds/06-lb-policies.md)), but it is
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
      "localityA": { "weight": 3, "childPolicy": [ { "child_policy_name": {} } ] },
      "localityB": { "weight": 1, "childPolicy": [ { "child_policy_name": {} } ] }
    }
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `targets` | map of string → object | No | empty map | The children. The map key is the child's name, which is its identity across updates. |
| `targets{}.weight` | uint32 | Yes | — | The child's weight. MUST be greater than 0. |
| `targets{}.childPolicy` | `LoadBalancingConfig list` | Yes | — | The child's policy. Resolved as specified in [LB Policy Registry and Configuration](../06-load-balancing.md#2-lb-policy-registry-and-configuration). |

### 2.1 Other Inputs

| Input | Location | Default | Used for |
| --- | --- | --- | --- |
| Hierarchical path | Endpoint attribute hierarchical path, set by the parent that routes endpoints to named children (with xDS, by `cds`, with the first element removed by `priority`) | — | The first element names the target whose child receives the endpoint, and is removed before the endpoint is passed down ([Hierarchical Address Paths](../06-load-balancing.md#94-hierarchical-address-paths); [Update](#33-updates-from-the-parent)). |

### 2.2 Validation

The config is invalid, and is rejected as specified in
[LB Policy Registry and Configuration](../06-load-balancing.md#2-lb-policy-registry-and-configuration),
if any of the following holds:

- A target's `weight` is missing or zero.
- A target's `childPolicy` is missing, or is an invalid
  `LoadBalancingConfig` list (no entry names a registered policy, or the
  selected policy rejects its config).

Other inputs ([Other Inputs](#21-other-inputs)) are validated as follows:

- **Hierarchical path:** an endpoint whose path is empty, or whose first
  element is not a key of `targets`, is ignored (see
  [Hierarchical Address Paths](../06-load-balancing.md#94-hierarchical-address-paths)).

## 3. LB Policy Implementation

The policy implements the generic
[LB Policy API](../06-load-balancing.md#4-lb-policy-api) as follows.

### 3.1 Internal State

- The children, keyed by target name.
- For each child, its latest reported connectivity state and picker
  ([Calls From Children](#52-calls-from-children)).
- Any retained (deactivated) children and their deletion timers
  ([Updates from the Parent](#33-updates-from-the-parent)).

### 3.2 Features

None.

### 3.3 Updates from the Parent

On each update, the policy:

1. Splits the endpoints by hierarchical path (the first path element is
   the target name, removed before passing down; see
   [Hierarchical Address Paths](../06-load-balancing.md#94-hierarchical-address-paths)).
2. For each target in the config, creates the child if needed, or
   updates the existing child of that name, passing it the update
   described in [Child Policies](#51-child-policies). If a child's policy
   name changed, the graceful-switch procedure is used.
3. Deletes (or retains, see below) children whose names are no longer in
   `targets`.
4. After all children are updated, computes and reports its aggregate
   state and picker once.

If the endpoints field is an error, the error is passed to every child.
The policy returns a status that combines the children's statuses.

**Removed children.** A child whose name is no longer in `targets` SHOULD
be deleted immediately, when the update is applied. If a later update adds
the name back, a new child is created. An implementation MAY instead
deactivate the removed child, retaining it for up to 15 minutes and then
deleting it. A retained child is not part of the aggregate state or the
picker, and it is reactivated (instead of a new child being created) if
its name returns to `targets` before it is deleted.

### 3.4 ExitIdle

Forwarded to all children.

### 3.5 ResetBackoff

Forwarded to all children.

### 3.6 Shutdown

Deletes all children.

## 4. Picker Implementation

In READY and TRANSIENT_FAILURE, the picker does a weighted random choice
among the children that are in the aggregate state, and delegates to the
chosen child's picker. In CONNECTING and IDLE, it queues:

| Aggregate state | Children in the picker | Behavior |
| --- | --- | --- |
| READY | READY children | Weighted random choice, delegated to the child's picker. |
| CONNECTING | — | Queue. |
| IDLE | — | Queue. The picker MUST also schedule a call to the policy's `ExitIdle()`, which is forwarded to all children (see [Triggering Work From a Picker](../06-load-balancing.md#63-triggering-work-from-a-picker)), so that IDLE children are not left idle with RPCs queued. |
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

## 5. Children and Subchannels

### 5.1 Child Policies

The policy has one child per entry in `targets`, named by the target
name. Each child's update contains the child's config (`childPolicy`),
its endpoints (routed by hierarchical path; see [Update](#33-updates-from-the-parent)),
the resolution note, and the top-level attributes plus a
**locality-name attribute** set to the target name. Policies below can
use this attribute, for example as the `grpc.lb.locality` label in
`weighted_round_robin` metrics.

`ExitIdle()` and `ResetBackoff()` are forwarded to all children, and
`Shutdown()` deletes all children ([ExitIdle](#34-exitidle),
[ResetBackoff](#35-resetbackoff), [Shutdown](#36-shutdown)).

### 5.2 Calls From Children

The policy handles calls from its children through the
[Helper API](../06-load-balancing.md#5-helper-api) it provides to them:

- `UpdateState(state, status, picker)`: Records the child's state and
  picker, recomputes the aggregate state, and reports a new picker
  ([Picker Implementation](#4-picker-implementation)). While an update is
  being applied to the children, the aggregate is reported only once,
  after all children are updated.

  The aggregate state is computed over all children with the normal
  rules (first match wins): READY if any child is READY; otherwise
  CONNECTING if any is CONNECTING; otherwise IDLE if any is IDLE; otherwise
  TRANSIENT_FAILURE (including when there are no children).
- `RequestReresolution()`: Forwarded to the policy's own helper.
- `CreateSubchannel(address, attributes)`: Passed through to the policy's
  own helper unchanged.

### 5.3 Subchannels

Not applicable: the policy does not create or watch subchannels; its
children do.

## 6. Metrics

The policy records no metrics.

## 7. API Requirements

- gRPC MUST register this policy under the name
  `weighted_target_experimental`, so that it can be selected through
  `loadBalancingConfig` in the service config and used as a child by other
  policies, including custom ones
  ([Load Balancing](../06-load-balancing.md)).
