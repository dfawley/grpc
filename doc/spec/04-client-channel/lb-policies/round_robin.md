> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `round_robin` LB Policy

<!-- Sources: doc/load-balancing.md, grpc/service_config/service_config.proto (RoundRobinConfig), A61, A88 -->

## 1. Overview

`round_robin` spreads calls evenly across all endpoints by sending each
successive call to the next READY endpoint. It is a petiole policy (see
[Load Balancing: Leaf, Parent, and Petiole Policies](../05-load-balancing.md#91-leaf-parent-and-petiole-policies)):
it creates one `pick_first` child per endpoint and tries to keep every
endpoint connected at all times.

Registered name: `round_robin`.

## 2. Configuration

Proto: `RoundRobinConfig` in `grpc/service_config/service_config.proto`.

```json
{ "round_robin": {} }
```

The config has no fields; it MUST be an empty JSON object.

## 3. Updates and Endpoint Management

On each update with a non-empty endpoint list, `round_robin`:

1. Matches endpoints against its existing children by endpoint identity
   (the unordered set of addresses). It keeps existing children, creates
   `pick_first` children for new endpoints, and shuts down children for
   removed endpoints.
2. Sends each child an update containing only its endpoint, with the
   addresses in their current order. The child's internal
   health-reporting option is enabled.
3. Recomputes its aggregate state and picker after all children have been
   updated.

If several endpoints in the list have the same address set, the policy
MAY collapse them into one child, OR leave them in place (one child per
entry) if doing so does not cause extra connections, for example because
the children's subchannels for the same address are shared (see
[Subchannel Sharing](../06-subchannels.md#4-subchannel-sharing)). When repeated
endpoints are left in place, each entry gets its own share of picks.

When a child reports IDLE, `round_robin` immediately calls the child's
`ExitIdle()`, so every endpoint keeps trying to connect.

An update with an empty endpoint list, or an endpoint error when there is
no previous list, makes `round_robin` shut down all children, report
TRANSIENT_FAILURE, and reject the update with `UNAVAILABLE`. The message
includes the resolution note.

## 4. Connectivity State

`round_robin` aggregates the children's states with the normal rules,
using both the sticky-TRANSIENT_FAILURE and IDLE-counts-as-CONNECTING
variations
([Load Balancing: Connectivity State Aggregation](../05-load-balancing.md#8-connectivity-state-aggregation)).
First match wins:

| Condition | Reported state | Picker |
| --- | --- | --- |
| At least one child READY | READY | Round-robin over READY children. |
| At least one child CONNECTING (or IDLE) | CONNECTING | Queue all picks. |
| Otherwise (all children TRANSIENT_FAILURE) | TRANSIENT_FAILURE | Fail picks with an error that includes the most recent connection failure and the resolution note. For example, delegate to the picker of the child that reported the most recent failure. |

## 5. Picker

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

## 6. LB Policy API

`round_robin` implements the generic
[LB Policy API](../05-load-balancing.md#4-lb-policy-api) and the
[Helper API](../05-load-balancing.md#5-helper-api) it provides to its
children as follows:

| Operation | Behavior |
| --- | --- |
| `Update(update) → status` | Creates, retains, and shuts down `pick_first` children by endpoint identity and sends each child its endpoint, then reports its state and picker once ([Updates and Endpoint Management](#3-updates-and-endpoint-management)). Each child receives its endpoint with that endpoint's attributes, plus the resolution note and the top-level attributes. An empty endpoint list, or an endpoint error with no previous list, shuts down all children, reports TRANSIENT_FAILURE, and returns `UNAVAILABLE`. An endpoint error with a previous list is ignored, and the existing children are kept. Returns OK in all other cases. |
| `ExitIdle()` | No-op: the policy never reports IDLE, because it calls `ExitIdle()` on any child that reports IDLE. |
| `ResetBackoff()` | Forwarded to all children. |
| `Shutdown()` | Shuts down all children. |
| Subchannel connectivity / health updates | Not applicable: the policy does not create or watch subchannels; its `pick_first` children do. |
| Child `UpdateState(state, status, picker)` | Records the child's state and picker. If the state is IDLE, calls the child's `ExitIdle()`. Recomputes the aggregate state ([Connectivity State](#4-connectivity-state)) and reports a new picker ([Picker](#5-picker)). While an update is being applied to the children, the aggregate is reported only once, after all children are updated. |
| Child `RequestReresolution()` | The `pick_first` children request re-resolution (see [Re-resolution](pick_first.md#8-re-resolution)). `round_robin` forwards those requests to its own helper. |
| Child `CreateSubchannel(address, attributes)` | Passed through to the policy's own helper unchanged. |

## 7. API Requirements

- gRPC MUST register this policy under the name `round_robin`, so that it
  can be selected through `loadBalancingConfig` in the service config and
  used as a child by other policies, including custom ones
  ([Load Balancing](../05-load-balancing.md)).
