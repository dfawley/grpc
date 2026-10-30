> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `random_subsetting` LB Policy

<!-- Sources: A68, grpc/service_config/service_config.proto (RandomSubsettingLoadBalancingConfig) -->

> **Experimental:** The policy is registered as
> `random_subsetting_experimental`. Its name and configuration are not yet
> stable.

> **Introduced by:** [gRFC A68: Random subsetting with rendezvous hashing LB policy.](https://github.com/grpc/proposal/blob/master/A68-random-subsetting.md)

## 1. Overview

`random_subsetting` is a parent policy with one child (see
[Policy Hierarchy](../05-load-balancing.md#9-policy-hierarchy)). It picks a
subset of `subsetSize` endpoints from the endpoint list and passes only
that subset to its child policy. Clients then connect to a bounded number
of servers. Connections are spread across servers nearly uniformly when
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

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `subsetSize` | uint32 | Yes | — | Number of endpoints in the subset passed to the child. MUST be greater than 0. |
| `childPolicy` | LoadBalancingConfig list | Yes | — | The child policy. Resolved as specified in [LB Policy Registry and Configuration](../05-load-balancing.md#2-lb-policy-registry-and-configuration). |

### 2.1 Validation

The config is invalid if any of the following holds:

- `subsetSize` is missing or 0.
- `childPolicy` is missing or invalid.

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

## 4. LB Policy API

`random_subsetting` implements the generic
[LB Policy API](../05-load-balancing.md#4-lb-policy-api) as follows.

| Operation | Behavior |
| --- | --- |
| `Update(update) → status` | Computes the subset and sends the child an update containing the subset, the child config, the top-level attributes, and the resolution note ([Behavior](#3-behavior)). If the endpoints field is an error, the error is passed to the child in place of the subset. If the child's policy name changes, the child is replaced using the procedure in [Gracefully Switching LB Policies](../05-load-balancing.md#12-gracefully-switching-lb-policies). Returns the child's status. |
| `ExitIdle()` | Forwarded to the child. |
| `ResetBackoff()` | Forwarded to the child. |
| `Shutdown()` | Shuts down the child. |
| Subchannel connectivity / health updates | Not applicable: the policy does not create or watch subchannels; its child does. |
| Child `UpdateState(state, status, picker)` | Passed through to the policy's own helper unchanged. |
| Child `RequestReresolution()` | Forwarded to the policy's own helper. |
| Child `CreateSubchannel(address, attributes)` | Passed through to the policy's own helper unchanged. |

## 5. API Requirements

- gRPC MUST register this policy under the name
  `random_subsetting_experimental`, so that it can be selected through
  `loadBalancingConfig` in the service config and used as a child by other
  policies, including custom ones
  ([Load Balancing](../05-load-balancing.md)).
