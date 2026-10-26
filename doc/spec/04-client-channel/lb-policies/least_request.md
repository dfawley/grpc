# `least_request` LB Policy

<!-- Sources: A48, A61, grpc/service_config/service_config.proto (LeastRequestLocalityLoadBalancingPolicyConfig) -->

> **Experimental:** The policy is registered as
> `least_request_experimental`. Its name and configuration are not yet
> stable.

## 1. Purpose

`least_request` is a petiole policy that sends each call to the endpoint
with the fewest outstanding calls among a small random sample of READY
endpoints ("power of N choices"). This adapts to endpoints that are
slower than others. Only the equal-weights form of the algorithm is
supported. Endpoint weights are ignored.

Registered name: `least_request_experimental`.

## 2. Configuration

Proto: `LeastRequestLocalityLoadBalancingPolicyConfig` in
`grpc/service_config/service_config.proto`.

```json
{ "least_request_experimental": { "choiceCount": 2 } }
```

| Field (JSON) | Type | Default | Validation / normalization |
| --- | --- | --- | --- |
| `choiceCount` | uint | 2 | Values below 2 make the config invalid. Values above 10 are treated as 10. |

## 3. Endpoint Management and Connectivity State

The same as [`round_robin`](round_robin.md):

- One `pick_first` child per endpoint, with health reporting enabled.
- An IDLE child is immediately asked to exit IDLE, and counted as
  CONNECTING.
- Aggregation uses sticky TRANSIENT_FAILURE:
  1. READY if any child is READY.
  2. Otherwise CONNECTING if any child is CONNECTING or IDLE.
  3. Otherwise TRANSIENT_FAILURE.
- An empty endpoint list causes TRANSIENT_FAILURE and the update is
  rejected.
- Re-resolution requests are forwarded.

Endpoints that repeat an address set MAY be collapsed into one child, OR
left in place if doing so does not cause extra connections (see
[`round_robin`](round_robin.md)). When they are collapsed, their
additional weight is ignored.

## 4. Outstanding Request Counters

Each endpoint has an atomic counter `active_requests` that belongs to
this policy instance (it is not shared with other policy instances using
the same subchannels). The counter is keyed by endpoint identity, so it
is retained across updates while the endpoint remains present.

- The picker atomically increments the counter of the chosen endpoint
  when it returns a Complete result.
- The picker attaches a call tracker that atomically decrements the
  counter when the call finishes, whatever its status. The decrement
  also happens when the pick is not used (see
  [../load-balancing.md](../load-balancing.md)).

Counters can be slightly stale when read concurrently. This is accepted.

## 5. Picker

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

## 6. API Requirements

- gRPC MUST register this policy under the name
  `least_request_experimental`, so that it can be selected through
  `loadBalancingConfig` in the service config and used as a child by other
  policies, including custom ones
  ([../load-balancing.md](../load-balancing.md)).
