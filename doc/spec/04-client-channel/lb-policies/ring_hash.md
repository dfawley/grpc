> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `ring_hash` LB Policy

<!-- Sources: A42, A61, A76, grpc/service_config/service_config.proto (RingHashLoadBalancingConfig), A88 -->

> **Experimental:** The policy is registered as `ring_hash_experimental`.
> Its name and configuration are not yet stable.

> **Introduced by:** [gRFC A42: xDS Ring Hash LB Policy](https://github.com/grpc/proposal/blob/master/A42-xds-ring-hash-lb-policy.md), [gRFC A76: Improvements to the Ring Hash LB Policy](https://github.com/grpc/proposal/blob/master/A76-ring-hash-improvements.md)

## 1. Overview

`ring_hash` is a petiole policy (see
[Policy Hierarchy](../06-load-balancing.md#9-policy-hierarchy)) that does
consistent hashing. It places each endpoint on a hash ring one or more
times, and sends each call to the first usable endpoint at or after the
call's request hash. Calls with the same request hash go to the same
endpoint while the endpoint set and reachability stay stable. The policy
connects lazily: it connects to an endpoint only when calls hash to it,
or when needed to recover from failure.

The request hash comes from one of two sources:

- A configured request header ([Configuration](#2-configuration)).
- A hash computed per call by the
  [ConfigSelector](../05-call-dispatch.md) and passed as a call attribute.
  The xDS ConfigSelector does this from the route's hash policies, see
  [RouteConfiguration: Hash Policy](../../09-xds/04-resources/03-route-configuration.md#7-hash-policy).

Registered name: `ring_hash_experimental`.

## 2. Configuration

Proto: `RingHashLoadBalancingConfig` in
`grpc/service_config/service_config.proto`.

```json
{
  "ring_hash_experimental": {
    "minRingSize": 1024,
    "maxRingSize": 4096,
    "requestHashHeader": "x-session-id"
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `minRingSize` | uint64 | No | 1024 | Minimum ring size ([Ring Construction](#ring-construction)). MUST be in `[1, 8388608]`. |
| `maxRingSize` | uint64 | No | 4096 | Maximum ring size ([Ring Construction](#ring-construction)). MUST be in `[1, 8388608]`. |
| `requestHashHeader` | string | No | `""` | Request header whose value is hashed to compute the request hash ([Picker Implementation](#4-picker-implementation)). If empty, the request hash is taken from the call attribute set by the ConfigSelector. If non-empty, MUST be a valid header name, and MUST NOT end in `-bin`. |

### 2.1 Validation

- Any field value outside the limits in the table makes the config
  invalid.
- `minRingSize` MUST NOT be greater than `maxRingSize`.

Any violation makes the config invalid (see
[LB Policy Registry and Configuration](../06-load-balancing.md#2-lb-policy-registry-and-configuration)).
An explicit value of 0 is invalid; it does not mean "use the default".
These checks MUST be applied to the values as configured, before the
local [Ring Size Cap](#22-other-inputs), so that every client accepts or
rejects the same configs.

### 2.2 Other Inputs

| Input | Location | Default | Used for |
| --- | --- | --- | --- |
| Ring size cap | Channel option | 4096 | Local cap on ring size. If `minRingSize` or `maxRingSize` is above the cap, it MUST be treated as the cap ([Ring Construction](#ring-construction)). When `ring_hash` is configured through xDS and the xDS resource does not set a maximum, the xDS layer sets `maxRingSize` to 8388608, so the effective maximum is the local cap (see [xDS LB Policies](../../09-xds/06-lb-policies.md)). |
| Endpoint weight | Endpoint attribute endpoint weight, set by the resolver or, with xDS, by `cds` | 1 | Relative share of ring entries ([Ring Construction](#ring-construction)). Endpoints merged because they have the same address set have their weights added together ([Update](#33-updates-from-the-parent)). |
| `hash_key` | Endpoint attribute `hash_key`, set by the resolver or, with xDS, by `cds` from the endpoint's `envoy.lb` metadata | unset | If set and non-empty, the string hashed to place the endpoint on the ring. If unset or empty, the endpoint's first address is hashed ([Ring Construction](#ring-construction)). If several endpoints share a `hash_key`, the endpoint chosen among them for a given ring position is unspecified. |
| Request hash | Call attribute request hash, set by the [ConfigSelector](../05-call-dispatch.md) (the xDS ConfigSelector computes it from the route's hash policies; see [Call attributes](../../09-xds/05-client.md#53-call-attributes)) | — | The call's position on the ring, read by the picker only when `requestHashHeader` is empty. If it is unset, the pick fails with INTERNAL ([Picker Implementation](#4-picker-implementation)). |
| Request header named by `requestHashHeader` | Pick argument: request metadata | — | When `requestHashHeader` is non-empty, the header's value is hashed to compute the request hash ([Picker Implementation](#4-picker-implementation)). |

## 3. LB Policy Implementation

`ring_hash` implements the generic
[LB Policy API](../06-load-balancing.md#4-lb-policy-api) as follows.

### 3.1 Internal State

The policy keeps:

- An **endpoint map**, keyed by endpoint identity (see
  [Update](#33-updates-from-the-parent)). Each entry holds the endpoint's weight and
  `hash_key`, its `pick_first` child if one has been created
  ([Child Policies](#51-child-policies)), and the endpoint's current state
  and picker as last reported by that child (IDLE for an endpoint without
  a child).
- The **ring** ([Ring Construction](#ring-construction)).

### 3.2 Features

#### Ring Construction

The ring is a list of `(hash, endpoint)` entries sorted by hash. Hashes
are computed with XXH64 (xxHash, 64-bit) with seed 0. The ring is built
with the same algorithm as Envoy:

```
BuildRing(endpoints, min_ring_size, max_ring_size):   # sizes already capped
  total = sum(e.weight for e in endpoints)
  normalized = [e.weight / total for e in endpoints]
  min_norm = min(normalized)
  scale = min(ceil(min_norm * min_ring_size) / min_norm, max_ring_size)
  ring = []
  current = 0.0
  target = 0.0
  for e, w in zip(endpoints, normalized):
    key = e.hash_key if non-empty else AddressString(e.addresses[0])
    target += scale * w
    count = 0
    while current < target:
      ring.append((XXH64(key + "_" + str(count), seed=0), e))
      count += 1
      current += 1
  sort ring by hash
  return ring
```

`AddressString` is the canonical `host:port` form of the address (IPv6
hosts in brackets).

The ring size is about `scale`. It is the smallest size of at least
`min_ring_size` at which the lowest-weighted endpoint gets a whole number
of entries, capped at `max_ring_size`.

`FindIndexForHash(h)` returns the index of the first entry whose hash is
greater than or equal to `h`, or 0 if there is none (the ring wraps).

#### Connectivity State Aggregation

Endpoint states are the states reported by the `pick_first` children
(IDLE for endpoints without a child). `pick_first` already keeps a failed
endpoint in TRANSIENT_FAILURE until it connects. A child that loses a
READY connection reports IDLE. The aggregate state is (first match
wins):

1. If at least one endpoint is READY, report READY.
2. If two or more endpoints are TRANSIENT_FAILURE, report
   TRANSIENT_FAILURE.
3. If at least one endpoint is CONNECTING, report CONNECTING.
4. If exactly one endpoint is TRANSIENT_FAILURE and there is more than one
   endpoint, report CONNECTING.
5. If at least one endpoint is IDLE, report IDLE.
6. Otherwise, report TRANSIENT_FAILURE.

With an entirely new set of endpoints (all IDLE), `ring_hash` reports
IDLE. The `priority` policy restarts its failover timer when such a
child later reports CONNECTING (see
[`priority` LB Policy](priority.md#failover-timer)).

#### Proactive Connection Attempts

When `ring_hash` is a child of `priority`, it may get no picks while it
reports TRANSIENT_FAILURE or CONNECTING. To make sure it recovers, after
every endpoint state change and every update, the policy applies this
rule:

> If the aggregated state is TRANSIENT_FAILURE or CONNECTING, and no
> endpoint is CONNECTING, trigger a connection on one IDLE endpoint, if
> there is one.

Which IDLE endpoint is chosen is up to the implementation. For example:

```
if aggregated_state in (TRANSIENT_FAILURE, CONNECTING):
  first_idle = None
  for e in endpoints:
    if e.state == CONNECTING: first_idle = None; break
    if first_idle is None and e.state == IDLE: first_idle = e
  if first_idle is not None: trigger connection on first_idle
```

"Trigger a connection" has the same meaning as in the picker
([Picker Implementation](#4-picker-implementation)).

`pick_first` children retry forever once they have failed (sticky
TRANSIENT_FAILURE), so the number of endpoints trying to connect grows
by one each time an attempt fails, until one connects.

### 3.3 Updates from the Parent

Endpoints are identified by the unordered set of their addresses,
ignoring attributes. If the update contains several endpoints with the
same address set, they are merged into one endpoint, and their weights
are added together. Duplicate endpoints MUST NOT cause the update to be
rejected.

On each update with a non-empty endpoint list, `ring_hash`:

1. Updates its endpoint map:
   - Retained endpoints keep their `pick_first` child, if they have one,
     and the child gets the endpoint's current address order.
   - New endpoints start with no child.
   - Removed endpoints' children are shut down.
2. Rebuilds the ring from the endpoints and the (capped) ring sizes
   ([Ring Construction](#ring-construction)). An endpoint's ring
   positions change when its `hash_key`, its first address, or its weight
   changes.
3. Applies the proactive connection rule ([Proactive Connection Attempts](#proactive-connection-attempts)).
4. Reports its aggregate state
   ([Connectivity State Aggregation](#connectivity-state-aggregation))
   and a new picker.

It then returns OK.

An empty endpoint list, or an endpoint error with no previous list,
causes TRANSIENT_FAILURE and a rejected update (`UNAVAILABLE`, including
the resolution note). An endpoint error when a previous list exists is
handled per [Endpoint Errors](../06-load-balancing.md#42-endpoint-errors):
the policy keeps using its previous endpoints.

`ring_hash` MUST produce a new picker every time any endpoint's state
changes, because the picker holds the ring together with the state of
every endpoint (see [Calls From Children](#52-calls-from-children)).

### 3.4 ExitIdle

No effect: connections are started by picks
([Picker Implementation](#4-picker-implementation)) and by the proactive
connection rule
([Proactive Connection Attempts](#proactive-connection-attempts)).

### 3.5 ResetBackoff

Forwarded to every existing `pick_first` child.

### 3.6 Shutdown

Shuts down every `pick_first` child.

## 4. Picker Implementation

The picker holds the ring, each endpoint's current state, and each
endpoint child's picker. It also stores
`picker_has_endpoint_in_connecting_state`, which is true if any endpoint
was CONNECTING when the picker was built. "Trigger a connection" means:
schedule work in the control plane that creates the endpoint's
`pick_first` child if it does not exist, and otherwise calls the child's
`ExitIdle()`.

```
Pick(args):
  # 1. Determine the request hash.
  using_random_hash = false
  if config.request_hash_header is empty:
    request_hash = args.call_attributes.request_hash      # set by ConfigSelector
    if request_hash is unset:
      return FAIL(INTERNAL, "ring_hash: request hash not set")
  else:
    values = args.metadata.get_all(config.request_hash_header)
    if values is non-empty:
      request_hash = XXH64(join(values, ","), seed=0)
    else:
      request_hash = random_uint64()
      using_random_hash = true

  first_index = ring.FindIndexForHash(request_hash)

  # 2a. Deterministic hash.
  if not using_random_hash:
    for i in range(len(ring)):
      e = ring[(first_index + i) % len(ring)].endpoint
      if e.state == READY:      return e.picker.Pick(args)
      if e.state == IDLE:       trigger connection on e; return QUEUE
      if e.state == CONNECTING: return QUEUE
      # TRANSIENT_FAILURE: keep walking the ring
    return ring[first_index].endpoint.picker.Pick(args)   # all failed

  # 2b. Random hash: pick the first READY endpoint; start at most one connection.
  requested_connection = picker_has_endpoint_in_connecting_state
  for i in range(len(ring)):
    e = ring[(first_index + i) % len(ring)].endpoint
    if e.state == READY:
      return e.picker.Pick(args)
    if not requested_connection and e.state == IDLE:
      trigger connection on e
      requested_connection = true
  if requested_connection:
    return QUEUE
  return ring[first_index].endpoint.picker.Pick(args)
```

When all endpoints are in TRANSIENT_FAILURE, the pick is delegated to the
`pick_first` child at `first_index`. That child exists, because it
reported TRANSIENT_FAILURE, so the call fails with that child's
connection error.

Multi-valued headers are joined with `,` before hashing. With random
hashing, a single call causes at most two endpoints to leave IDLE.

## 5. Children and Subchannels

### 5.1 Child Policies

The policy has one `pick_first` child per endpoint. `pick_first` children
are created **lazily**: a child is created only when the policy wants to
connect to that endpoint. Each child gets just its endpoint, with health
reporting enabled. An endpoint without a child is treated as IDLE.

Children are created by the picker or the proactive connection rule
("trigger a connection", [Picker Implementation](#4-picker-implementation)),
updated or shut down by [Update](#33-updates-from-the-parent), and receive
`ResetBackoff()` and `Shutdown()` as specified in
[ResetBackoff](#35-resetbackoff) and [Shutdown](#36-shutdown).
`ExitIdle()` is not forwarded ([ExitIdle](#34-exitidle)).

### 5.2 Calls From Children

- **`UpdateState(state, status, picker)`:** records the state and picker
  as the state of that child's endpoint, recomputes the aggregate state
  ([Connectivity State Aggregation](#connectivity-state-aggregation)),
  applies the proactive connection rule
  ([Proactive Connection Attempts](#proactive-connection-attempts)),
  and reports the aggregate state with a new picker.
- **`RequestReresolution()`:** forwarded to the policy's own helper.
- **`CreateSubchannel(address, attributes)`:** passed through to the
  policy's own helper unchanged.

### 5.3 Subchannels

Not applicable: the policy does not create or watch subchannels; its
`pick_first` children do.

## 6. Metrics

The policy records no metrics.

## 7. API Requirements

- gRPC MUST register this policy under the name `ring_hash_experimental`,
  so that it can be selected through `loadBalancingConfig` in the service
  config and used as a child by other policies, including custom ones
  ([Load Balancing](../06-load-balancing.md)).
- The channel API MUST provide a way to set the local ring size cap
  (default 4096) ([Ring Size Cap](#22-other-inputs)).
