> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# `weighted_round_robin` LB Policy

<!-- Sources: A58, A61, A51 (client side), A78 (WRR metrics), A89, A114 -->

> **Introduced by:** [gRFC A58: `weighted_round_robin` LB policy](https://github.com/grpc/proposal/blob/master/A58-client-side-weighted-round-robin-lb-policy.md)

## 1. Overview

`weighted_round_robin` (WRR) is a petiole policy (see
[Load Balancing: Leaf, Parent, and Petiole Policies](../06-load-balancing.md#91-leaf-parent-and-petiole-policies))
that spreads calls across endpoints in proportion to weights it computes
from backend metrics reported by the endpoints themselves (see
[Backend Metrics (ORCA)](../../07-services/03-orca.md)). Without usable
weights, it behaves like [`round_robin`](round_robin.md).

Registered name: `weighted_round_robin`.

## 2. Configuration

```json
{
  "weighted_round_robin": {
    "enableOobLoadReport": false,
    "oobReportingPeriod": "10s",
    "blackoutPeriod": "10s",
    "weightExpirationPeriod": "180s",
    "weightUpdatePeriod": "1s",
    "errorUtilizationPenalty": 1.0,
    "metricNamesForComputingUtilization": []
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `enableOobLoadReport` | bool | No | `false` | If true, use out-of-band reports. If false, use per-call reports ([Load Report Sources](#load-report-sources)). |
| `oobReportingPeriod` | Duration | No | `"10s"` | Reporting interval requested from servers in OOB mode. |
| `blackoutPeriod` | Duration | No | `"10s"` | How long an endpoint must report continuously before its weight is used. `0` disables the blackout. |
| `weightExpirationPeriod` | Duration | No | `"180s"` | A weight not updated for this long is no longer used. |
| `weightUpdatePeriod` | Duration | No | `"1s"` | How often the scheduler is rebuilt from current weights. Values below 100 ms are treated as 100 ms. |
| `errorUtilizationPenalty` | number | No | `1.0` | Multiplier for the error-rate penalty in the weight formula. MUST NOT be negative. |
| `metricNamesForComputingUtilization` | list of string | No | `[]` | Backend metrics whose largest value is used as the endpoint's utilization ([Custom Utilization Metrics](#custom-utilization-metrics)). Each entry is `application_utilization`, `cpu_utilization`, `mem_utilization`, `named_metrics.<key>`, or `utilization.<key>`. |

### 2.1 Other Inputs

| Input | Location | Default | Used for |
| --- | --- | --- | --- |
| Locality name | Top-level attribute locality name, set by `weighted_target` on each child to the target name | empty | The `grpc.lb.locality` metric label ([Metrics](#6-metrics)). |
| Backend service | Top-level attribute backend service, set by xDS (by `cds`, to the cluster name) | empty | The `grpc.lb.backend_service` metric label ([Metrics](#6-metrics)). |
| Channel target | Channel: the parent channel's target | — | The `grpc.target` metric label ([Metrics](#6-metrics)). |

### 2.2 Validation

The config is invalid, and is rejected as described in
[Load Balancing: LB Policy Registry and Configuration](../06-load-balancing.md#2-lb-policy-registry-and-configuration),
if:

- `oobReportingPeriod`, `blackoutPeriod`, `weightExpirationPeriod`, or
  `weightUpdatePeriod` is not a valid Duration string (for example,
  `"10s"`), or is negative (including a value with a zero seconds part, such
  as `"-0.5s"`).
- `errorUtilizationPenalty` is negative.

Whether an entry of `metricNamesForComputingUtilization` that is not one
of the supported forms makes the config invalid is implementation-defined.
If the config is accepted, such an entry never yields a value
([Custom Utilization Metrics](#custom-utilization-metrics)).

The policy does not validate its other inputs ([Other Inputs](#21-other-inputs)).

## 3. LB Policy Implementation

`weighted_round_robin` implements the generic
[LB Policy API](../06-load-balancing.md#4-lb-policy-api) as follows.

### 3.1 Internal State

The policy keeps:

- One `pick_first` child per endpoint, keyed by endpoint identity, with
  the most recent state and picker reported by each child.
- Each endpoint's weight state (`weight`, `last_updated`, and
  `non_empty_since`; see [Endpoint Weights](#endpoint-weights)), keyed
  by endpoint identity.
- When `enableOobLoadReport` is true, the OOB backend metric watchers it
  registered on its children's subchannels ([OOB Reports](#oob-reports)).
- The current picker's scheduler and weight update timer
  ([Scheduler](#scheduler)).

### 3.2 Features

#### Endpoint Weights

##### Weight Formula

From each backend metric report, WRR takes:

- `utilization`: the largest positive value among the metrics named in
  `metricNamesForComputingUtilization`, if there is one
  ([Custom Utilization Metrics](#custom-utilization-metrics)); otherwise
  the report's `application_utilization` if it is non-zero, otherwise its
  `cpu_utilization`.
- `qps`: the report's `qps`.
- `eps`: the report's `eps`.

The weight is:

$$
weight = \frac{qps}{utilization + \frac{eps}{qps} \times error\_utilization\_penalty}
$$

The `eps/qps` term is applied only when both `utilization` and `qps` are
greater than zero. A report that yields a weight of zero (for example,
zero utilization or zero qps) is ignored.

##### Custom Utilization Metrics

> **Introduced by:** [gRFC A114: WRR Support for Custom Backend Metrics](https://github.com/grpc/proposal/blob/master/A114-wrr-metric-names-for-computing-utilization.md)

`metricNamesForComputingUtilization` selects which fields of the backend
metric report ([Backend Metrics (ORCA)](../../07-services/03-orca.md))
determine `utilization`. Each entry names one value in the report:

| Entry | Value |
| --- | --- |
| `application_utilization` | The report's `application_utilization`. |
| `cpu_utilization` | The report's `cpu_utilization`. |
| `mem_utilization` | The report's `mem_utilization`. |
| `named_metrics.<key>` | The entry for `<key>` in the report's `named_metrics` map. |
| `utilization.<key>` | The entry for `<key>` in the report's `utilization` map. |

For the map forms, the entry is split at its first period: the part after
it is the map key, even if it contains more periods
(`named_metrics.foo.bar` names the key `foo.bar`). Other report fields
cannot be selected.

```
GetUtilization(report):
  max_util = none
  for name in config.metric_names_for_computing_utilization:
    value = value named by name in report, or none if absent
    if value != none and not is_nan(value) and value > 0:
      max_util = (max_util == none) ? value : max(max_util, value)
  if max_util != none:
    return max_util
  if report.application_utilization > 0:
    return report.application_utilization
  return report.cpu_utilization
```

Values that are absent, zero, negative, or NaN are ignored. The policy does
not normalize the selected values; applications that combine metrics are
responsible for reporting them on comparable scales.

##### Blackout and Expiration

Each endpoint tracks `weight`, `last_updated` (initially unset), and
`non_empty_since` (initially infinite). The endpoint MUST be updated and
read under synchronization, because reports arrive from the data plane or
OOB streams while the scheduler timer reads weights.

```
OnReport(qps, eps, utilization):
  if not (qps > 0 and utilization > 0): return   # also ignores NaN
  if eps > 0:
    utilization += eps / qps * config.error_utilization_penalty
  new_weight = qps / utilization
  if not (new_weight > 0): return
  if non_empty_since == infinity: non_empty_since = now()
  last_updated = now()
  weight = new_weight

OnEndpointBecomesReady():        # child transitions from non-READY to READY
  non_empty_since = infinity

GetWeight():
  if last_updated is unset:
    return 0                     # counted as endpoint_weight_not_yet_usable
  if now() - last_updated >= config.weight_expiration_period:
    non_empty_since = infinity
    return 0                     # counted as endpoint_weight_stale
  if config.blackout_period > 0 and
     now() - non_empty_since < config.blackout_period:
    return 0                     # counted as endpoint_weight_not_yet_usable
  return weight
```

Reports whose `qps` or `utilization` is not greater than 0 (including NaN)
are ignored; an `eps` that is not greater than 0 contributes no error
penalty. Blackout applies both after an endpoint (re)connects and after
its weight expires.

#### Load Report Sources

##### Per-Call Reports (Default)

When `enableOobLoadReport` is false, the picker attaches a call tracker
to each Complete result. When the call finishes, the tracker passes the
call's backend metric report, if any, to `OnReport()` for the picked
endpoint. A missing report is ignored.

##### OOB Reports

When `enableOobLoadReport` is true:

- WRR intercepts `CreateSubchannel()` in the helper it gives each
  `pick_first` child, and registers an OOB backend metric watcher on every
  subchannel created. The watcher uses `oobReportingPeriod` as its
  interval and feeds reports to `OnReport()` for that endpoint. A
  `pick_first` child can create several subchannels, but after it selects
  one it releases the others, so in steady state there is one watcher per
  endpoint.
- Per-call reports are not parsed.
- The OOB stream lifecycle is specified in
  [Client-Side Backend Metrics (ORCA)](../11-backend-metrics.md).

When `enableOobLoadReport` changes, WRR MUST switch modes: it starts or
stops the OOB watchers on existing subchannels, and makes the next picker
attach or omit per-call trackers. When `oobReportingPeriod` changes, WRR
MUST update the watchers' interval. Neither change may recreate
subchannels or drop connections.

#### Scheduler

##### Building the Scheduler

```
BuildScheduler(ready_children):
  weights = [c.endpoint.GetWeight() for c in ready_children]
  nonzero = [w for w in weights if w > 0]
  if len(nonzero) < 2:
    weights = [1 for _ in weights]          # behave like round_robin
  else:
    mean = sum(nonzero) / len(nonzero)
    weights = [w if w > 0 else mean for w in weights]
    # Clamp to bound the cost of a pick (see below).
    weights = [min(max(w, MIN_RATIO * mean), MAX_RATIO * mean) for w in weights]
  return EDFScheduler(weights)
```

Before building the scheduler, each weight MUST be clamped to
`[MIN_RATIO × mean, MAX_RATIO × mean]`, where `mean` is the mean of the
non-zero weights, `MAX_RATIO` is 10, and `MIN_RATIO` is a fixed value in
`[0.01, 0.1]` (0.1 is RECOMMENDED). Clamping bounds how many entries a pick
may have to skip when weights are very uneven, for example when high-weight
endpoints are not accepting picks and the remaining endpoints have near-zero
weights. As a consequence, an endpoint never gets more than about `MAX_RATIO`
times, or less than `MIN_RATIO` times, the average share of picks, even if its
reported weight is further from the mean.

The scheduler is rebuilt:

- Each time the policy produces a new picker (state changes or config
  updates).
- Every `weightUpdatePeriod`, by a timer that belongs to the current
  picker. The timer rebuilds the scheduler from the current weights and
  atomically replaces it. Picks in progress can keep using the old
  scheduler.

A scheduler MUST be cheap to build and allow concurrent picks with little
or no contention.

##### EDF Scheduling

Each entry `i` has period `1 / weights[i]` and a deadline. The initial
deadline is chosen uniformly at random in `[0, period]`, so that
different pickers do not pick in lockstep. A pick takes the entry with
the earliest deadline, adds its period to its deadline, and returns its
index. Ties are broken by insertion order, using a monotonically
increasing sequence number.

```
EDFScheduler(weights):
  for i, w in enumerate(weights):
    push(heap, (deadline=random_uniform(0, 1/w), seq=next_seq(), index=i))

Pick():                                     # concurrent-safe
  e = pop_min(heap)                         # by (deadline, seq)
  push(heap, (e.deadline + 1/weights[e.index], next_seq(), e.index))
  return e.index
```

Any implementation that gives the same long-run selection proportions
(each READY endpoint chosen in proportion to its clamped weight), with
comparable smoothness, is conformant. In particular, a scheduler that quantizes
weights (for example, to 16 bits) MUST NOT turn a positive weight into zero.

### 3.3 Updates from the Parent

Endpoint management, connectivity behavior, and state aggregation are the
same as for [`round_robin`](round_robin.md):

- One `pick_first` child per endpoint, with the health-reporting option
  enabled.
- Endpoints that repeat an address set MAY be collapsed into one child,
  OR left in place if doing so does not cause extra connections.
- A child that reports IDLE is immediately asked to exit IDLE, and is
  counted as CONNECTING.
- Aggregation uses each child's current state; the `pick_first` children
  apply sticky TRANSIENT_FAILURE themselves.
- Re-resolution requests are forwarded.

Each endpoint's weight state ([Endpoint Weights](#endpoint-weights))
is keyed by endpoint identity, so it is retained across updates for
endpoints that remain present.

A change to `enableOobLoadReport` or `oobReportingPeriod` is applied
without recreating subchannels ([OOB Reports](#oob-reports)), and
reporting a new picker at the end of the update switches per-call report
tracking on or off immediately; the other config fields also take effect
when that picker is built ([Building the Scheduler](#building-the-scheduler)).

An empty endpoint list, or an endpoint error with no previous list, shuts
down all children, reports TRANSIENT_FAILURE, and returns `UNAVAILABLE`.
For an endpoint error with a previous list, the existing children are
kept, but `Update()` still returns the endpoint error, so that a polling
resolver keeps retrying with backoff. `Update()` returns OK in all other
cases.

### 3.4 ExitIdle

No-op: the policy never reports IDLE, because it calls `ExitIdle()` on any
child that reports IDLE.

### 3.5 ResetBackoff

Forwarded to all children.

### 3.6 Shutdown

Shuts down all children, stops all OOB backend metric watchers, and
cancels the weight update timer.

## 4. Picker Implementation

The READY picker holds the list of READY children and an **earliest
deadline first (EDF)** scheduler ([Scheduler](#scheduler)). Only READY
children are in the scheduler. Each pick asks the scheduler for an index
and delegates to that child's picker. When `enableOobLoadReport` is false,
the picker attaches a call tracker to each Complete result
([Per-Call Reports (Default)](#per-call-reports-default)).

In CONNECTING (including when any child is IDLE), the picker queues all
picks. In TRANSIENT_FAILURE, it fails picks with an error that includes a
child's connection failure and the resolution note, as for
[`round_robin`](round_robin.md).

## 5. Children and Subchannels

### 5.1 Child Policies

WRR creates one `pick_first` child per endpoint, with the child's
internal health-reporting option enabled, as [`round_robin`](round_robin.md)
does ([Updates from the Parent](#33-updates-from-the-parent)). Each child receives its endpoint with that
endpoint's attributes, plus the resolution note and the top-level
attributes.

- `ExitIdle()`: not forwarded (it is a no-op), but WRR calls a child's
  `ExitIdle()` whenever that child reports IDLE.
- `ResetBackoff()`: forwarded to all children.
- `Shutdown()`: shuts down all children.

### 5.2 Calls From Children

`weighted_round_robin` implements the
[Helper API](../06-load-balancing.md#5-helper-api) it provides to its
children as follows:

- `UpdateState(state, status, picker)`: Records the child's state and
  picker. If the state is IDLE, calls the child's `ExitIdle()`. If the
  child transitions from a non-READY state to READY, calls
  `OnEndpointBecomesReady()` for the endpoint
  ([Blackout and Expiration](#blackout-and-expiration)). Recomputes the
  aggregate state as for `round_robin` and reports a new picker with a
  newly built scheduler ([Picker Implementation](#4-picker-implementation)).
  While an update is being applied to the children, the aggregate is
  reported only once, after all children are updated.
- `RequestReresolution()`: Forwarded to the policy's own helper.
- `CreateSubchannel(address, attributes)`: Passed through to the policy's
  own helper. When `enableOobLoadReport` is true, the policy registers an
  OOB backend metric watcher on the returned subchannel
  ([OOB Reports](#oob-reports)).

### 5.3 Subchannels

The policy does not watch subchannel connectivity or health; its
`pick_first` children do. When `enableOobLoadReport` is true, the policy
receives OOB backend metric reports from the watchers it registers on its
children's subchannels and passes them to `OnReport()` for the endpoint
([OOB Reports](#oob-reports)).

## 6. Metrics

> **Experimental:** The WRR metrics below are experimental (off by
> default).

> **Introduced by:** [gRFC A78: gRPC OTel Metrics for WRR, Pick First, and XdsClient](https://github.com/grpc/proposal/blob/master/A78-grpc-metrics-wrr-pf-xds.md)

On each scheduler build, WRR records the metrics below. All have the
required label `grpc.target`, and the optional labels `grpc.lb.locality`
(from the locality-name attribute that `weighted_target` passes down,
empty if unset) and `grpc.lb.backend_service` (from the backend-service
resolver attribute, empty if unset). Definitions are in
[Metric Catalog: Weighted Round Robin LB Policy Metrics](../../08-observability/04-metrics.md#5-weighted-round-robin-lb-policy-metrics).

| Name | Type | Unit | Description |
| --- | --- | --- | --- |
| `grpc.lb.wrr.rr_fallback` | Counter | `{update}` | Scheduler updates with fewer than two endpoints with usable weights (fell back to round-robin behavior). |
| `grpc.lb.wrr.endpoint_weight_not_yet_usable` | Counter | `{endpoint}` | Endpoints in this update with no usable weight yet (no report, or in blackout). |
| `grpc.lb.wrr.endpoint_weight_stale` | Counter | `{endpoint}` | Endpoints in this update whose latest weight is older than the expiration period. |
| `grpc.lb.wrr.endpoint_weights` | Histogram | `{weight}` | Weight of each endpoint in this update (0 if not usable). |

## 7. API Requirements

- gRPC MUST register this policy under the name `weighted_round_robin`, so
  that it can be selected through `loadBalancingConfig` in the service
  config and used as a child by other policies, including custom ones
  ([Load Balancing](../06-load-balancing.md)).
