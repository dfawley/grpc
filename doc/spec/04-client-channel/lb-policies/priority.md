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
[Policy Hierarchy](../06-load-balancing.md#9-policy-hierarchy)). It sends
calls to the highest-priority child that is usable, and fails over to
lower priorities when higher ones cannot connect. It is not
xDS-specific. xDS uses it to choose a priority within a cluster and to
implement aggregate clusters (see
[xDS LB Policies](../../09-xds/06-lb-policies.md)).

Registered name: `priority_experimental`.

## 2. Configuration

Proto: `PriorityLoadBalancingPolicyConfig` in
`grpc/service_config/service_config.proto`.

```json
{
  "priority_experimental": {
    "children": {
      "child0": { "config": [ { "child_policy_name": {} } ], "ignoreReresolutionRequests": false },
      "child1": { "config": [ { "child_policy_name": {} } ], "ignoreReresolutionRequests": true }
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
  [LB Policy Registry and Configuration](../06-load-balancing.md#2-lb-policy-registry-and-configuration)).
- A name in `priorities` is not a key of `children`.
- A name appears more than once in `priorities`.
- A key of `children` does not appear in `priorities`.

An empty `priorities` list (with an empty `children` map) is valid (see
[Priority Selection Algorithm](#priority-selection-algorithm)).

### 2.2 Other Inputs

| Input | Location | Default | Used for |
| --- | --- | --- | --- |
| Hierarchical path | Endpoint attribute hierarchical path, set by the parent that routes endpoints to named children (with xDS, by `cds`) | — | The first element selects the child that receives the endpoint, and is removed before the endpoint is passed down ([Endpoint Distribution](#endpoint-distribution); [Hierarchical Address Paths](../06-load-balancing.md#94-hierarchical-address-paths)). |

## 3. LB Policy Implementation

`priority` implements the generic
[LB Policy API](../06-load-balancing.md#4-lb-policy-api) as follows.

### 3.1 Internal State

For each child, the policy stores the most recent connectivity state,
status, and picker. Children start in CONNECTING (see
[Initial State](../06-load-balancing.md#43-initial-state)). Each child
also has a failover timer ([Failover Timer](#failover-timer)) and, while
deactivated, a deletion timer ([Child Lifetime](#child-lifetime)).

The policy also tracks the **current priority**
([Priority Selection Algorithm](#priority-selection-algorithm)).

### 3.2 Features

#### Endpoint Distribution

Endpoints are sent to children by hierarchical path: an endpoint goes to
the child named by the first element of its path, with that element
removed (see
[Hierarchical Address Paths](../06-load-balancing.md#94-hierarchical-address-paths)).
Each child's update contains its subset of endpoints, its config, the
top-level attributes, and the resolution note.

#### Failover Timer

Each child has a **failover timer** of **10 seconds**. While it runs, the
child is considered to still be trying to connect.

- **Started** when the child is created. Also started when the child
  reports CONNECTING after some other state (repeated CONNECTING reports
  are ignored), if its most recent non-CONNECTING report was READY or
  IDLE rather than TRANSIENT_FAILURE.
- **Cancelled** when the child reports READY, IDLE, or TRANSIENT_FAILURE.
- **On expiry**, the policy runs the priority-selection algorithm
  ([Priority Selection Algorithm](#priority-selection-algorithm)).

#### Child Lifetime

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

#### Priority Selection Algorithm

The algorithm is idempotent: running it again with the same child states
gives the same result. It runs after each config update and after each
child state report (except during step 3 of [Update](#33-updates-from-the-parent)), and
when a failover timer fires.

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

### 3.3 Updates from the Parent

When the policy receives an update:

1. Delete (or deactivate, as permitted by
   [Child Lifetime](#child-lifetime)) every child whose name is not in
   the new `priorities`.
2. For every remaining existing child, send an update with its new
   config and endpoint subset ([Endpoint Distribution](#endpoint-distribution)).
   If the child's policy name changed, use the graceful-switch procedure
   (see
   [Gracefully Switching LB Policies](../06-load-balancing.md#12-gracefully-switching-lb-policies)).
3. While applying steps 1–2, ignore picker updates from children for the
   purpose of choosing a priority (but still record them).
4. Run the priority-selection algorithm once
   ([Priority Selection Algorithm](#priority-selection-algorithm)).

If the endpoints field is an error, the error is passed to each child in
place of its endpoint subset.

The policy returns a non-OK status from the update if any child rejected
its update, and OK otherwise.

### 3.4 ExitIdle

Forwarded to the current priority's child.

### 3.5 ResetBackoff

Forwarded to all children.

### 3.6 Shutdown

Deletes all children and cancels all timers.

## 4. Picker Implementation

Not applicable: the policy reports the current priority's picker
unchanged, or, with an empty `priorities` list, a picker that fails calls
([Priority Selection Algorithm](#priority-selection-algorithm)).

## 5. Children and Subchannels

### 5.1 Child Policies

The policy creates one child per name in `priorities`, lazily
([Child Lifetime](#child-lifetime)), using the policy in that name's
`children{}.config`. Each child's update is described in
[Endpoint Distribution](#endpoint-distribution). `ExitIdle()`,
`ResetBackoff()`, and `Shutdown()` are forwarded as specified in
[ExitIdle](#34-exitidle), [ResetBackoff](#35-resetbackoff), and
[Shutdown](#36-shutdown).

### 5.2 Calls From Children

- **`UpdateState(state, status, picker)`:** records the child's state,
  status, and picker, starts or cancels the child's failover timer
  ([Failover Timer](#failover-timer)), and runs the priority-selection
  algorithm, except while applying an update
  ([Priority Selection Algorithm](#priority-selection-algorithm)). The
  policy reports the current priority's state, status, and picker.
- **`RequestReresolution()`:** forwarded to the policy's own helper,
  unless that child's `ignoreReresolutionRequests` is true, in which case
  it is ignored.
- **`CreateSubchannel(address, attributes)`:** passed through to the
  policy's own helper unchanged.

### 5.3 Subchannels

Not applicable: the policy does not create or watch subchannels; its
children do.

## 6. Metrics

The policy records no metrics.

## 7. API Requirements

- gRPC MUST register this policy under the name `priority_experimental`,
  so that it can be selected through `loadBalancingConfig` in the service
  config and used as a child by other policies, including custom ones
  ([Load Balancing](../06-load-balancing.md)).
