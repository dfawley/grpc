> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `random_subsetting` LB Policy

<!-- Sources: A68, grpc/service_config/service_config.proto (RandomSubsettingLoadBalancingConfig) -->

> **Experimental:** The policy is registered as
> `random_subsetting_experimental`. Its name and configuration are not yet
> stable.

## 1. Purpose

`random_subsetting` picks a subset of `subsetSize` endpoints from the
endpoint list and passes only that subset to its child policy. Clients
then connect to a bounded number of servers. Connections are spread
across servers nearly uniformly when
`(number of clients × subsetSize) / number of servers` is large. The
policy uses rendezvous hashing, so adding or removing one server changes
at most one entry in each client's subset.

Registered name: `random_subsetting_experimental`.

## 2. Configuration

Proto: `RandomSubsettingLoadBalancingConfig` in
`grpc/service_config/service_config.proto`.

```json
{
  "random_subsetting_experimental": {
    "subsetSize": 10,
    "childPolicy": [ { "round_robin": {} } ]
  }
}
```

| Field (JSON) | Type | Validation |
| --- | --- | --- |
| `subsetSize` | uint32 | Required. MUST be greater than 0. |
| `childPolicy` | `LoadBalancingConfig` list | Required. Resolved as specified in [../load-balancing.md](../load-balancing.md). The config is invalid if the list is missing or invalid. |

## 3. Behavior

When the policy instance is created, it generates a random integer
`seed`, which it keeps for its whole lifetime.

On every update (new endpoints or new config), the policy computes the
subset and sends the child an update. The update contains the subset, the
child config, the parent's top-level attributes, and the resolution
note:

```
filter_endpoints(endpoints, subset_size, seed):
  if subset_size >= len(endpoints):
    return endpoints
  hashed = [(XXH64(AddressString(e.addresses[0]), seed), e) for e in endpoints]
  sort hashed by hash ascending
  return [e for (_, e) in hashed[:subset_size]]
```

Only an endpoint's first address is hashed. `AddressString` is the
canonical `host:port` form of the address.

Everything else is passed straight through: the child's state and picker
reports, its re-resolution requests, and `ExitIdle()`, `ResetBackoff()`,
and `Shutdown()`. The policy creates no subchannels of its own.

## 4. API Requirements

- gRPC MUST register this policy under the name
  `random_subsetting_experimental`, so that it can be selected through
  `loadBalancingConfig` in the service config and used as a child by other
  policies, including custom ones
  ([../load-balancing.md](../load-balancing.md)).
