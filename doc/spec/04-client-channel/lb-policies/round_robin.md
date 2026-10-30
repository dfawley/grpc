> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `round_robin` LB Policy

<!-- Sources: doc/load-balancing.md, grpc/service_config/service_config.proto (RoundRobinConfig), A61, A88 -->

## 1. Overview

`round_robin` spreads calls evenly across all endpoints by sending each
successive call to the next READY endpoint. It is a petiole policy (see
[Load Balancing: Leaf, Parent, and Petiole Policies](../06-load-balancing.md#91-leaf-parent-and-petiole-policies)):
it creates one `pick_first` child per endpoint and tries to keep every
endpoint connected at all times.

Registered name: `round_robin`.

## 2. Configuration

Proto: `RoundRobinConfig` in `grpc/service_config/service_config.proto`.

```json
{ "round_robin": {} }
```

The config has no fields; it MUST be an empty JSON object.

### 2.1 Validation

The config is invalid if it is not an empty JSON object.

### 2.2 Other Inputs

None.

## 3. LB Policy Implementation

`round_robin` implements the generic
[LB Policy API](../06-load-balancing.md#4-lb-policy-api) as follows.

### 3.1 Internal State

The policy keeps one `pick_first` child per endpoint, matched by endpoint
identity (the unordered set of addresses), and the most recent state and
picker reported by each child.

### 3.2 Features

None.

### 3.3 Updates from the Parent

On each update with a non-empty endpoint list, `round_robin`:

1. Matches endpoints against its existing children by endpoint identity
   (the unordered set of addresses). It keeps existing children, creates
   `pick_first` children for new endpoints, and shuts down children for
   removed endpoints.
2. Sends each child an update containing only its endpoint, with the
   addresses in their current order. The child's internal
   health-reporting option is enabled.
3. Recomputes its aggregate state and picker after all children have been
   updated, and reports them once.

If several endpoints in the list have the same address set, the policy
MAY collapse them into one child, OR leave them in place (one child per
entry) if doing so does not cause extra connections, for example because
the children's subchannels for the same address are shared (see
[Subchannel Sharing](../07-subchannels.md#4-subchannel-sharing)). When repeated
endpoints are left in place, each entry gets its own share of picks.

An update with an empty endpoint list, or an endpoint error when there is
no previous list, makes `round_robin` shut down all children, report
TRANSIENT_FAILURE, and reject the update with `UNAVAILABLE`. The message
includes the resolution note.

An endpoint error with a previous list is ignored, and the existing
children are kept. `Update()` returns OK in all cases other than those
above.

#### Connectivity State

`round_robin` aggregates the children's states with the normal rules,
using both the sticky-TRANSIENT_FAILURE and IDLE-counts-as-CONNECTING
variations
([Load Balancing: Connectivity State Aggregation](../06-load-balancing.md#8-connectivity-state-aggregation)).
First match wins:

| Condition | Reported state | Picker |
| --- | --- | --- |
| At least one child READY | READY | Round-robin over READY children. |
| At least one child CONNECTING (or IDLE) | CONNECTING | Queue all picks. |
| Otherwise (all children TRANSIENT_FAILURE) | TRANSIENT_FAILURE | Fail picks with an error that includes the most recent connection failure and the resolution note. For example, delegate to the picker of the child that reported the most recent failure. |

The aggregate state is recomputed and a new picker reported whenever a
child reports a new state ([Calls From Children](#52-calls-from-children)).

#### Re-resolution

`round_robin` forwards its children's re-resolution requests
([Calls From Children](#52-calls-from-children)).

### 3.4 ExitIdle

No-op: the policy never reports IDLE, because it calls `ExitIdle()` on any
child that reports IDLE.

### 3.5 ResetBackoff

Forwarded to all children.

### 3.6 Shutdown

Shuts down all children.

## 4. Picker Implementation

The READY picker holds the list of READY children, in the order they
appear in the endpoint list, and a shared index.

```
NewPicker(ready_children):
  index = random integer in [0, len(ready_children))

Pick(args):
  i = atomic_fetch_and_increment(index) mod len(ready_children)
  return ready_children[i].picker.Pick(args)
```

Each new picker starts at a random index. The index MUST be updated
atomically or under synchronization, because picks are concurrent.

The CONNECTING and TRANSIENT_FAILURE pickers are specified in
[Connectivity State](#connectivity-state).

## 5. Children and Subchannels

### 5.1 Child Policies

`round_robin` creates one `pick_first` child per endpoint, with the
child's internal health-reporting option enabled
([Update](#33-updates-from-the-parent)). Each child receives its endpoint with that
endpoint's attributes, plus the resolution note and the top-level
attributes.

- `ExitIdle()`: not forwarded (it is a no-op), but `round_robin` calls a
  child's `ExitIdle()` whenever that child reports IDLE.
- `ResetBackoff()`: forwarded to all children.
- `Shutdown()`: shuts down all children.

### 5.2 Calls From Children

`round_robin` implements the
[Helper API](../06-load-balancing.md#5-helper-api) it provides to its
children as follows:

- `UpdateState(state, status, picker)`: Records the child's state and
  picker. If the state is IDLE, `round_robin` immediately calls the
  child's `ExitIdle()`, so every endpoint keeps trying to connect.
  Recomputes the aggregate state ([Connectivity State](#connectivity-state))
  and reports a new picker ([Picker Implementation](#4-picker-implementation)).
  While an update is being applied to the children, the aggregate is
  reported only once, after all children are updated.
- `RequestReresolution()`: The `pick_first` children request
  re-resolution (see [Re-resolution](pick_first.md#re-resolution)).
  `round_robin` forwards those requests to its own helper.
- `CreateSubchannel(address, attributes)`: Passed through to the policy's
  own helper unchanged.

### 5.3 Subchannels

Not applicable: the policy does not create or watch subchannels; its
`pick_first` children do.

## 6. Metrics

The policy records no metrics.

## 7. API Requirements

- gRPC MUST register this policy under the name `round_robin`, so that it
  can be selected through `loadBalancingConfig` in the service config and
  used as a child by other policies, including custom ones
  ([Load Balancing](../06-load-balancing.md)).
