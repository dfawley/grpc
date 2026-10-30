> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `priority` LB Policy

<!-- Sources: A56, A115, A37 (ignore_reresolution_requests), A42 (failover timer interaction), grpc/service_config/service_config.proto (PriorityLoadBalancingPolicyConfig) -->

> **Experimental:** The policy is registered as `priority_experimental`.
> Its name and configuration are not yet stable.

> **Introduced by:** [gRFC A56: `priority_experimental` LB policy](https://github.com/grpc/proposal/blob/master/A56-priority-lb-policy.md)

## 1. Overview

`priority` is a parent policy with an ordered list of named children (see
[Policy Hierarchy](../05-load-balancing.md#9-policy-hierarchy)). It sends
calls to the highest-priority child that is usable, and fails over to
lower priorities when higher ones cannot connect. It is not
xDS-specific. xDS uses it to choose a priority within a cluster and to
implement aggregate clusters (see
[xDS LB Policies](../../09-xds/05-lb-policies.md)).

Registered name: `priority_experimental`.

## 2. Configuration

Proto: `PriorityLoadBalancingPolicyConfig` in
`grpc/service_config/service_config.proto`.

```json
{
  "priority_experimental": {
    "children": {
      "child0": { "config": [ { "round_robin": {} } ], "ignoreReresolutionRequests": false },
      "child1": { "config": [ { "round_robin": {} } ], "ignoreReresolutionRequests": true }
    },
    "priorities": [ "child0", "child1" ]
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `children` | map of string → object | No | `{}` | The children's configs, keyed by child name. The names let the policy update existing children in place rather than recreate them, even when a child moves to a different priority. |
| `children{}.config` | LoadBalancingConfig list | Yes | — | The child's policy. |
| `children{}.ignoreReresolutionRequests` | bool | No | `false` | If true, the policy ignores re-resolution requests from this child. |
| `priorities` | list of string | No | `[]` | Child names in decreasing priority order (the first element has the highest priority). |

### 2.1 Validation

The config is invalid if any of the following holds:

- A `config` list is missing or invalid (see
  [LB Policy Registry and Configuration](../05-load-balancing.md#2-lb-policy-registry-and-configuration)).
- A name in `priorities` is not a key of `children`.
- A name appears more than once in `priorities`.
- A key of `children` does not appear in `priorities`.

An empty `priorities` list (with an empty `children` map) is valid (see
[Priority Selection Algorithm](#7-priority-selection-algorithm)).

## 3. Endpoint Distribution

Endpoints are sent to children by hierarchical path: an endpoint goes to
the child named by the first element of its path, with that element
removed (see
[Hierarchical Address Paths](../05-load-balancing.md#94-hierarchical-address-paths)).
Each child's update contains its subset of endpoints, its config, the
top-level attributes, and the resolution note.

## 4. Child State Tracking and Failover Timer

For each child, the policy stores the most recent connectivity state,
status, and picker. Children start in CONNECTING (see
[Initial State](../05-load-balancing.md#43-initial-state)).

Each child has a **failover timer** of **10 seconds**. While it runs, the
child is considered to still be trying to connect.

- **Started** when the child is created. Also started when the child
  reports CONNECTING after some other state (repeated CONNECTING reports
  are ignored), if its most recent non-CONNECTING report was READY or
  IDLE rather than TRANSIENT_FAILURE.
- **Cancelled** when the child reports READY, IDLE, or TRANSIENT_FAILURE.
- **On expiry**, the policy runs the priority-selection algorithm
  ([Priority Selection Algorithm](#7-priority-selection-algorithm)).

## 5. Child Lifetime

- **Lazy creation.** A child is created only when the selection algorithm
  reaches its priority. When a priority is chosen, lower-priority children
  are not created.
- **Deactivation.** When the policy switches to a higher priority, it
  *deactivates* every existing lower-priority child. A deactivated child
  keeps running (and keeps its connections), and starts a **15-minute**
  deletion timer. When the timer fires, the child is deleted.
- **Reactivation.** If the selection algorithm reaches a deactivated child
  before it is deleted, the child is reactivated and its deletion timer is
  cancelled.
- **Removal from config.** A child whose name is no longer in the
  config's `priorities` SHOULD be deleted immediately, when the update is
  applied. An implementation MAY instead deactivate it, retaining it for
  up to 15 minutes as above. A retained child receives no picks and is
  reactivated if its name returns to `priorities` before it is deleted.

## 6. Configuration Updates

When the policy receives an update:

1. Delete (or deactivate, as permitted by
   [Child Lifetime](#5-child-lifetime)) every child whose name is not in
   the new `priorities`.
2. For every remaining existing child, send an update with its new
   config and endpoint subset. If the child's policy name changed, use
   the graceful-switch procedure (see
   [Gracefully Switching LB Policies](../05-load-balancing.md#12-gracefully-switching-lb-policies)).
3. While applying steps 1–2, ignore picker updates from children for the
   purpose of choosing a priority (but still record them).
4. Run the priority-selection algorithm once.

The policy returns a non-OK status from the update if any child rejected
its update.

## 7. Priority Selection Algorithm

The algorithm is idempotent: running it again with the same child states
gives the same result. It runs after each config update and after each
child state report (except during step 3 above), and when a failover timer
fires.

```python
def SetCurrentPriority(self, priority, deactivate_lower_priorities):
  if deactivate_lower_priorities:
    for p in range(priority + 1, len(self.config.priorities)):
      name = self.config.priorities[p]
      if name in self.children:
        self.children[name].Deactivate()
  child = self.children[self.config.priorities[priority]]
  self.helper.UpdateState(child.state, child.status, child.picker)

def ChoosePriority(self):
  if not self.config.priorities:
    status = Status(UNAVAILABLE, "priority policy has empty priority list")
    self.helper.UpdateState(TRANSIENT_FAILURE, status, FailPicker(status))
    return
  # Look for a child in READY or IDLE, or one whose failover timer is pending,
  # creating children as needed.
  for priority, name in enumerate(self.config.priorities):
    if name not in self.children:
      child = self.CreateChild(name)              # starts failover timer
      self.children[name] = child
      child.Update(self.config.children[name], endpoints_for(name))
    else:
      child = self.children[name]
      child.MaybeReactivate()
    if child.state in (READY, IDLE):
      self.SetCurrentPriority(priority, True)
      return
    if child.FailoverTimerPending():
      self.SetCurrentPriority(priority, False)
      return
  # None found; prefer the highest-priority child in CONNECTING.
  for priority, name in enumerate(self.config.priorities):
    if self.children[name].state == CONNECTING:
      self.SetCurrentPriority(priority, False)
      return
  # Everything is in TRANSIENT_FAILURE; use the last child.
  self.SetCurrentPriority(len(self.config.priorities) - 1, False)
```

The child chosen by the last `SetCurrentPriority()` call is the
**current priority**. The policy reports exactly that child's state,
status, and picker. When the current child later reports a new picker
without changing the selection, the policy passes it through.

## 8. LB Policy API

`priority` implements the generic
[LB Policy API](../05-load-balancing.md#4-lb-policy-api) as follows.

| Operation | Behavior |
| --- | --- |
| `Update(update) → status` | Deletes or deactivates removed children, updates the remaining children with their new configs and endpoint subsets, and runs the priority-selection algorithm once ([Configuration Updates](#6-configuration-updates), [Endpoint Distribution](#3-endpoint-distribution)). If the endpoints field is an error, the error is passed to each child in place of its endpoint subset. Returns a non-OK status if any child rejected its update, and OK otherwise. |
| `ExitIdle()` | Forwarded to the current priority's child. |
| `ResetBackoff()` | Forwarded to all children. |
| `Shutdown()` | Deletes all children and cancels all timers. |
| Subchannel connectivity / health updates | Not applicable: the policy does not create or watch subchannels; its children do. |
| Child `UpdateState(state, status, picker)` | Records the child's state, status, and picker, starts or cancels the child's failover timer ([Child State Tracking and Failover Timer](#4-child-state-tracking-and-failover-timer)), and runs the priority-selection algorithm, except while applying an update ([Priority Selection Algorithm](#7-priority-selection-algorithm)). The policy reports the current priority's state, status, and picker. |
| Child `RequestReresolution()` | Forwarded to the policy's own helper, unless that child's `ignoreReresolutionRequests` is true, in which case it is ignored. |
| Child `CreateSubchannel(address, attributes)` | Passed through to the policy's own helper unchanged. |

## 9. API Requirements

- gRPC MUST register this policy under the name `priority_experimental`,
  so that it can be selected through `loadBalancingConfig` in the service
  config and used as a child by other policies, including custom ones
  ([Load Balancing](../05-load-balancing.md)).
