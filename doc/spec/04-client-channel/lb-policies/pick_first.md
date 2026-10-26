> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `pick_first` LB Policy

<!-- Sources: doc/load-balancing.md, grpc/service_config/service_config.proto (PickFirstConfig), A61, A62, A105, A88 -->

## 1. Purpose

`pick_first` connects to one address and sends all calls on it until the
connection fails or is closed. It is:

- The default LB policy for a channel when no policy is configured (see
  [../service-config.md](../service-config.md)).
- The universal leaf policy: petiole policies create one `pick_first`
  child per endpoint to pick an address within that endpoint (see
  [../load-balancing.md](../load-balancing.md)).

Registered name: `pick_first`.

## 2. Configuration

Proto: `PickFirstConfig` in `grpc/service_config/service_config.proto`.

```json
{ "pick_first": { "shuffleAddressList": false } }
```

| Field (JSON) | Type | Default | Description |
| --- | --- | --- | --- |
| `shuffleAddressList` | bool | `false` | If true, randomly shuffle the order of the endpoints on every update from the parent ([Address List Processing](#3-address-list-processing)). |

The config is valid if `shuffleAddressList` is absent or a JSON boolean.

### 2.1 Channel Options

| Option | Default | Description |
| --- | --- | --- |
| Happy Eyeballs Connection Attempt Delay | 250 ms | The delay before the next address is tried in parallel ([Happy Eyeballs Connection Algorithm](#4-happy-eyeballs-connection-algorithm)). Values below 100 ms MUST be treated as 100 ms. Values above 2 s MUST be treated as 2 s. |
| Internal health-reporting option | disabled | Set only by petiole parent policies. Not settable by applications ([Health Reporting Under Petiole Policies](#7-health-reporting-under-petiole-policies)). |

## 3. Address List Processing

When `pick_first` receives an update with a non-empty endpoint list, it
builds a flat, ordered address list as follows:

1. **Shuffle** (only if `shuffleAddressList` is true). Shuffle the
   endpoints using a uniform random permutation (for example,
   Fisher–Yates). The order of addresses within each endpoint is not
   changed. A petiole parent passes a single endpoint, so shuffling has
   no effect there.
2. **Flatten.** Concatenate the address lists of all endpoints, in
   endpoint order.
3. **De-duplicate.** Repeated addresses MAY be removed, keeping the
   first occurrence, OR left in place if doing so does not cause extra
   connections (for example, because the repeated entries share one
   subchannel; see [Subchannel Sharing](../subchannels.md#4-subchannel-sharing)).
   De-duplicating earlier (for example, before the shuffle) is also allowed.
   The only difference is which copy of a repeated address is kept.
4. **Interleave address families** (RFC 8305 [Client Channel](../README.md)). Group the addresses by
   family (IPv6, IPv4, and any other family), keeping their relative order
   within each group. Then build the final list by taking one address at a
   time from each group in turn. The groups are visited in the order in
   which each family first appears in the flattened list. Groups that run
   out are skipped.

The resolver is responsible for RFC 6724 address sorting, so it is
already done before `pick_first` sees the list. Shuffling happens on
each update from the parent, not on reconnection.

## 4. Happy Eyeballs Connection Algorithm

`pick_first` creates one subchannel per address in the processed list,
and then makes a **Happy Eyeballs pass** over the list in order. For
each subchannel, at the point where the pass reaches it:

| Subchannel state | Action |
| --- | --- |
| IDLE | Call `RequestConnection()`. If this is not the last subchannel, start the Connection Attempt Delay timer. If it is the last one, wait for the attempt to finish. |
| CONNECTING | Treat it as if a connection was just requested: start the timer if this is not the last subchannel, otherwise wait. |
| TRANSIENT_FAILURE | The subchannel is in backoff after a recent failure. Treat it as already attempted and move on to the next subchannel immediately. |
| READY | Select it (see below). |

When the timer fires before the current attempt completes, the pass
moves on to the next subchannel. Attempts already in flight are not
cancelled, so several attempts can be in flight at once. A connection
failure on the subchannel the pass is waiting on also moves the pass
along.

Whenever any subchannel reports READY, whether or not `pick_first`
requested its connection and whether or not a pass is in progress,
`pick_first` **selects** it:

1. Cancel the Connection Attempt Delay timer, if running.
2. Release all other subchannels. This cancels their in-flight attempts
   unless the subchannel is shared ([../subchannels.md](../subchannels.md)).
3. Report READY with a picker that returns Complete with the selected
   subchannel. If the health-reporting option is enabled, see
   [Health Reporting Under Petiole Policies](#7-health-reporting-under-petiole-policies).

The pass is **complete** when at least one connection attempt on every
subchannel has failed. Then `pick_first`:

1. Reports TRANSIENT_FAILURE with a picker that fails calls (see
   [Error Messages](#9-error-messages)).
2. Requests re-resolution.
3. Enters steady-state retry mode: it no longer follows address order.
   Each subchannel backs off on its own, reporting TRANSIENT_FAILURE while
   in backoff and IDLE when backoff ends. Whenever a subchannel reports
   IDLE, `pick_first` immediately calls `RequestConnection()` on it.
4. Counts connection failures. When the count reaches the number of
   subchannels, it requests re-resolution and resets the count.

**Sticky TRANSIENT_FAILURE.** Once `pick_first` reports
TRANSIENT_FAILURE, it stays there until a subchannel becomes READY or
the policy is shut down. It does not report CONNECTING in between, even
though its subchannels do, and even if it receives a new update and
starts a new pass.

## 5. State Machine and Updates

| Event | Current state | Action |
| --- | --- | --- |
| First update with non-empty list | (new) | Process the list, create subchannels, start a Happy Eyeballs pass, report CONNECTING with a queueing picker. |
| Update with non-empty list | CONNECTING or TRANSIENT_FAILURE | Replace the subchannel list (subchannels for unchanged addresses MAY be reused) and start a new pass. Stay in the current state. |
| Update with non-empty list | READY | If the selected subchannel's address is in the new list, keep the selected subchannel and stay READY. The new list is stored for future connection attempts. Otherwise, release the selected subchannel and go to IDLE (below). If a subchannel for an address in the new list is already READY (for example, a shared subchannel), `pick_first` MAY select it and stay READY instead. It MUST NOT start a new connection attempt only because of the update. |
| Update with non-empty list | IDLE | Store the list and stay IDLE. |
| Update with empty list, or endpoint error with no previous list | any | Release all subchannels, report TRANSIENT_FAILURE with a failing picker, and reject the update (`UNAVAILABLE`). |
| Endpoint error with a previous list | any | Ignore the error and keep the current list and state. |
| Selected subchannel reports IDLE | READY | Release subchannels, request re-resolution, report IDLE. |
| Selected subchannel reports CONNECTING or TRANSIENT_FAILURE | READY | Can happen with connection scaling ([../subchannels.md](../subchannels.md)). Request re-resolution, report CONNECTING, and start a new Happy Eyeballs pass over all subchannels. |
| `ExitIdle()` | IDLE | Recreate subchannels from the most recent list, start a pass, report CONNECTING. |
| `ExitIdle()` | other | No-op. |

In IDLE, `pick_first` holds no subchannels. Its picker schedules
`ExitIdle()` in the control plane on the first pick, and queues every
pick.

## 6. Picker

```
Pick(args):
  switch state:
    READY:             return COMPLETE(selected_subchannel)
    IDLE:              schedule ExitIdle() in control plane; return QUEUE
    CONNECTING:        return QUEUE
    TRANSIENT_FAILURE: return FAIL(status)
```

## 7. Health Reporting Under Petiole Policies

When the internal health-reporting option is enabled:

- Connection management (passes, selection, retries) uses only the raw
  connectivity state, exactly as described above.
- After selecting a subchannel, `pick_first` starts a generic health
  watch on it ([../load-balancing.md](../load-balancing.md)). It reports
  the health state to its parent instead of READY:
  - Health READY: report READY with a picker that returns the
    subchannel.
  - Health CONNECTING: report CONNECTING with a queueing picker.
  - Health TRANSIENT_FAILURE: report TRANSIENT_FAILURE with a picker that
    fails with the health status.
- The health watch is stopped when the subchannel is released.

When the option is disabled, `pick_first` never starts a health watch,
so [client-side health checking](../health-checking.md) and outlier
ejection have no effect on it.

## 8. Re-resolution

`pick_first` requests re-resolution:

- When a Happy Eyeballs pass completes without a connection.
- In steady-state retry mode, each time the failure count reaches the
  number of subchannels.
- When the selected subchannel leaves READY.

## 9. Error Messages

The TRANSIENT_FAILURE picker fails calls with `UNAVAILABLE`. The message
MUST include:

- The address and status message of the most recent connection failure,
  for example
  `failed to connect to all addresses; last error: ipv4:10.0.0.1:443: Connection refused`.
- The resolution note, if non-empty.

For an empty endpoint list, the message MUST say that the list was empty
and include the resolution note.

## 10. API Requirements

- gRPC MUST register this policy under the name `pick_first`, so that it
  can be selected through `loadBalancingConfig` in the service config and
  used as a child by other policies, including custom ones
  ([../load-balancing.md](../load-balancing.md)).
- The channel API MUST provide a way to set the Happy Eyeballs Connection
  Attempt Delay ([Channel Options](#21-channel-options)).
- The internal health-reporting option MUST be available to petiole
  policies, including custom ones, and MUST NOT be settable by
  applications in any other way
  ([../load-balancing.md](../load-balancing.md)).
