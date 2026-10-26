> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `least_request` LB Policy

<!-- Sources: A48, A61, grpc/service_config/service_config.proto (LeastRequestLocalityLoadBalancingPolicyConfig) -->

> **Experimental:** The policy is registered as
> `least_request_experimental`. Its name and configuration are not yet
> stable.

> **Introduced by:** [gRFC A48: xDS Least Request LB Policy](https://github.com/grpc/proposal/blob/master/A48-xds-least-request-lb-policy.md)

## 1. Overview

`least_request` is a petiole policy (see
[Load Balancing: Leaf, Parent, and Petiole Policies](../06-load-balancing.md#91-leaf-parent-and-petiole-policies))
that sends each call to the endpoint with the fewest outstanding calls
among a small random sample of READY endpoints ("power of N choices").
This adapts to endpoints that are slower than others. Only the
equal-weights form of the algorithm is supported. Endpoint weights are
ignored.

Registered name: `least_request_experimental`.

## 2. Configuration

Proto: `LeastRequestLocalityLoadBalancingPolicyConfig` in `grpc/service_config/service_config.proto`.

```json
{ "least_request_experimental": { "choiceCount": 2 } }
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `choiceCount` | uint64 | No | `2` | Number of READY endpoints sampled per pick ([Picker Implementation](#4-picker-implementation)). Values below 2 make the config invalid. Values above 10 are treated as 10. |

### 2.1 Other Inputs

None.

### 2.2 Validation

- The config is invalid if `choiceCount` is less than 2. An invalid config
  is rejected as described in
  [Load Balancing: LB Policy Registry and Configuration](../06-load-balancing.md#2-lb-policy-registry-and-configuration).

## 3. LB Policy Implementation

`least_request` implements the generic
[LB Policy API](../06-load-balancing.md#4-lb-policy-api) as follows.

### 3.1 Internal State

The policy keeps:

- One `pick_first` child per endpoint, keyed by endpoint identity, with
  the most recent state and picker reported by each child.
- Each endpoint's `active_requests` counter, keyed by endpoint identity
  ([Outstanding Request Counters](#outstanding-request-counters)).

### 3.2 Features

#### Outstanding Request Counters

Each endpoint has an atomic counter `active_requests` that belongs to
this policy instance (it is not shared with other policy instances using
the same subchannels). The counter is keyed by endpoint identity, so it
is retained across updates while the endpoint remains present.

- The picker atomically increments the counter of the chosen endpoint
  when it returns a Complete result.
- The picker attaches a call tracker that atomically decrements the
  counter when the call finishes, whatever its status. The decrement
  also happens when the pick is not used (see
  [Load Balancing: Call-Completion Tracking](../06-load-balancing.md#64-call-completion-tracking)).

Counters can be slightly stale when read concurrently. This is accepted.

### 3.3 Updates from the Parent

Endpoint management and connectivity state are the same as
[`round_robin`](round_robin.md):

- One `pick_first` child per endpoint, with health reporting enabled.
- An IDLE child is immediately asked to exit IDLE, and counted as
  CONNECTING.
- Aggregation uses sticky TRANSIENT_FAILURE:
  1. READY if any child is READY.
  2. Otherwise CONNECTING if any child is CONNECTING or IDLE.
  3. Otherwise TRANSIENT_FAILURE.
- Re-resolution requests are forwarded.

Endpoints that repeat an address set MAY be collapsed into one child, OR
left in place if doing so does not cause extra connections (see
[`round_robin`](round_robin.md)). When they are collapsed, their
additional weight is ignored.

Each endpoint's `active_requests` counter is retained by endpoint identity
([Outstanding Request Counters](#outstanding-request-counters)). A new
`choiceCount` takes effect when the next picker is built.

An empty endpoint list, or an endpoint error with no previous list, shuts
down all children, reports TRANSIENT_FAILURE, and returns `UNAVAILABLE`.
An endpoint error with a previous list is ignored, and the existing
children are kept. `Update()` returns OK in all other cases.

### 3.4 ExitIdle

No-op: the policy never reports IDLE, because it calls `ExitIdle()` on any
child that reports IDLE.

### 3.5 ResetBackoff

Forwarded to all children.

### 3.6 Shutdown

Shuts down all children.

## 4. Picker Implementation

The READY picker holds the list of READY children.

```
Pick(args):
  candidate = null
  for i in range(choice_count):
    sampled = ready_children[random_integer(0, len(ready_children))]  # with replacement
    if candidate == null or sampled.active_requests < candidate.active_requests:
      candidate = sampled
  result = candidate.picker.Pick(args)
  if result is COMPLETE:
    atomic_increment(candidate.active_requests)
    attach tracker that decrements candidate.active_requests on completion
  return result
```

Sampling is with replacement, so the same endpoint can be sampled more
than once. In CONNECTING the picker queues. In TRANSIENT_FAILURE it fails
with an error that includes the most recent connection failure and the
resolution note, as for `round_robin`.

## 5. Children and Subchannels

### 5.1 Child Policies

`least_request` creates one `pick_first` child per endpoint, with the
child's internal health-reporting option enabled, as
[`round_robin`](round_robin.md) does ([Update](#33-updates-from-the-parent)). Each child
receives its endpoint with that endpoint's attributes, plus the
resolution note and the top-level attributes.

- `ExitIdle()`: not forwarded (it is a no-op), but `least_request` calls a
  child's `ExitIdle()` whenever that child reports IDLE.
- `ResetBackoff()`: forwarded to all children.
- `Shutdown()`: shuts down all children.

### 5.2 Calls From Children

`least_request` implements the
[Helper API](../06-load-balancing.md#5-helper-api) it provides to its
children as follows:

- `UpdateState(state, status, picker)`: Records the child's state and
  picker. If the state is IDLE, calls the child's `ExitIdle()`. Recomputes
  the aggregate state ([Update](#33-updates-from-the-parent)) and reports a new picker
  ([Picker Implementation](#4-picker-implementation)). While an update is
  being applied to the children, the aggregate is reported only once,
  after all children are updated.
- `RequestReresolution()`: Forwarded to the policy's own helper.
- `CreateSubchannel(address, attributes)`: Passed through to the policy's
  own helper unchanged.

### 5.3 Subchannels

Not applicable: the policy does not create or watch subchannels; its
`pick_first` children do.

## 6. Metrics

The policy records no metrics.

## 7. API Requirements

- gRPC MUST register this policy under the name
  `least_request_experimental`, so that it can be selected through
  `loadBalancingConfig` in the service config and used as a child by other
  policies, including custom ones
  ([Load Balancing](../06-load-balancing.md)).
