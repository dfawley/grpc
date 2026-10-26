# `weighted_round_robin` LB Policy

<!-- Sources: A58, A61, A51 (client side), A78 (WRR metrics), A89, grpc/service_config/service_config.proto (WeightedRoundRobinLbConfig) -->

## 1. Purpose

`weighted_round_robin` (WRR) is a petiole policy that spreads calls
across endpoints in proportion to weights it computes from backend
metrics reported by the endpoints themselves (see
[../../07-services/orca.md](../../07-services/orca.md)). Without usable
weights, it behaves like [`round_robin`](round_robin.md).

Registered name: `weighted_round_robin`.

## 2. Configuration

Proto: `WeightedRoundRobinLbConfig` in
`grpc/service_config/service_config.proto`. Duration fields use the
protobuf JSON duration format (for example, `"10s"`).

```json
{
  "weighted_round_robin": {
    "enableOobLoadReport": false,
    "oobReportingPeriod": "10s",
    "blackoutPeriod": "10s",
    "weightExpirationPeriod": "180s",
    "weightUpdatePeriod": "1s",
    "errorUtilizationPenalty": 1.0
  }
}
```

| Field (JSON) | Type | Default | Validation / normalization | Description |
| --- | --- | --- | --- | --- |
| `enableOobLoadReport` | bool | `false` | — | If true, use out-of-band reports. If false, use per-call reports. |
| `oobReportingPeriod` | Duration | 10 s | Valid duration. | Reporting interval requested from servers in OOB mode. |
| `blackoutPeriod` | Duration | 10 s | Valid duration. `0` disables the blackout. | How long an endpoint must report continuously before its weight is used. |
| `weightExpirationPeriod` | Duration | 180 s | Valid duration. | A weight not updated for this long is no longer used. |
| `weightUpdatePeriod` | Duration | 1 s | Values below 100 ms are treated as 100 ms. | How often the scheduler is rebuilt from current weights. |
| `errorUtilizationPenalty` | float | 1.0 | Negative values make the config invalid. | Multiplier for the error-rate penalty in the weight formula. |

## 3. Endpoint Management and Connectivity State

Endpoint management, connectivity behavior, and state aggregation are the
same as for [`round_robin`](round_robin.md):

- One `pick_first` child per endpoint, with the health-reporting option
  enabled.
- Endpoints that repeat an address set MAY be collapsed into one child,
  OR left in place if doing so does not cause extra connections.
- A child that reports IDLE is immediately asked to exit IDLE, and is
  counted as CONNECTING.
- Aggregation uses sticky TRANSIENT_FAILURE.
- An empty endpoint list causes TRANSIENT_FAILURE and the update is
  rejected.
- Re-resolution requests are forwarded.

Each endpoint's weight state (below) is keyed by endpoint identity, so it
is retained across updates for endpoints that remain present.

## 4. Endpoint Weights

### 4.1 Weight Formula

From each backend metric report, WRR takes:

- `utilization`: the report's `application_utilization` if it is
  non-zero, otherwise its `cpu_utilization`.
- `qps`: the report's `qps`.
- `eps`: the report's `eps`.

The weight is:

$$
weight = \frac{qps}{utilization + \frac{eps}{qps} \times error\_utilization\_penalty}
$$

The `eps/qps` term is applied only when both `utilization` and `qps` are
greater than zero. A report that yields a weight of zero (for example,
zero utilization or zero qps) is ignored.

### 4.2 Blackout and Expiration

Each endpoint tracks `weight`, `last_updated`, and `non_empty_since`
(initially infinite). The endpoint MUST be updated and read under
synchronization, because reports arrive from the data plane or OOB
streams while the scheduler timer reads weights.

```
OnReport(qps, eps, utilization):
  if utilization > 0 and qps > 0:
    utilization += eps / qps * config.error_utilization_penalty
  new_weight = (utilization == 0) ? 0 : qps / utilization
  if new_weight == 0: return
  if non_empty_since == infinity: non_empty_since = now()
  last_updated = now()
  weight = new_weight

OnEndpointBecomesReady():        # child reports READY
  non_empty_since = infinity

GetWeight():
  if now() - last_updated >= config.weight_expiration_period:
    non_empty_since = infinity
    return 0
  if config.blackout_period > 0 and
     now() - non_empty_since < config.blackout_period:
    return 0
  return weight
```

Blackout applies both after an endpoint (re)connects and after its
weight expires.

## 5. Load Report Sources

### 5.1 Per-Call Reports (Default)

When `enableOobLoadReport` is false, the picker attaches a call tracker
to each Complete result. When the call finishes, the tracker passes the
call's backend metric report, if any, to `OnReport()` for the picked
endpoint. A missing report is ignored.

### 5.2 OOB Reports

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
  [Client-Side Backend Metrics](../backend-metrics.md).

When `enableOobLoadReport` changes, WRR MUST switch modes: it starts or
stops the OOB watchers on existing subchannels, and makes the next picker
attach or omit per-call trackers. When `oobReportingPeriod` changes, WRR
MUST update the watchers' interval. Neither change may recreate
subchannels or drop connections.

## 6. Picker and Scheduler

The READY picker holds the list of READY children and an **earliest
deadline first (EDF)** scheduler. Only READY children are in the
scheduler. Each pick asks the scheduler for an index and delegates to
that child's picker.

### 6.1 Building the Scheduler

```
BuildScheduler(ready_children):
  weights = [c.endpoint.GetWeight() for c in ready_children]
  nonzero = [w for w in weights if w > 0]
  if len(nonzero) < 2:
    weights = [1 for _ in weights]          # behave like round_robin
  else:
    mean = sum(nonzero) / len(nonzero)
    weights = [w if w > 0 else mean for w in weights]
  return EDFScheduler(weights)
```

The scheduler is rebuilt:

- Each time the policy produces a new picker (state changes or config
  updates).
- Every `weightUpdatePeriod`, by a timer that belongs to the current
  picker. The timer rebuilds the scheduler from the current weights and
  atomically replaces it. Picks in progress can keep using the old
  scheduler.

A scheduler MUST be cheap to build and allow concurrent picks with little
or no contention.

### 6.2 EDF Scheduling

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
(each READY endpoint chosen in proportion to its weight), with
comparable smoothness, is conformant.

## 7. Metrics

> **Experimental:** The WRR metrics below are experimental (off by
> default).

On each scheduler build, WRR records the metrics below. All have the
required label `grpc.target`, and the optional labels `grpc.lb.locality`
(from the locality-name attribute that `weighted_target` passes down,
empty if unset) and `grpc.lb.backend_service` (from the backend-service
resolver attribute, empty if unset). Definitions are in
[../../08-observability/metrics.md](../../08-observability/metrics.md).

| Name | Type | Unit | Description |
| --- | --- | --- | --- |
| `grpc.lb.wrr.rr_fallback` | Counter | `{update}` | Scheduler updates with fewer than two endpoints with usable weights (fell back to round-robin behavior). |
| `grpc.lb.wrr.endpoint_weight_not_yet_usable` | Counter | `{endpoint}` | Endpoints in this update with no usable weight yet (no report, or in blackout). |
| `grpc.lb.wrr.endpoint_weight_stale` | Counter | `{endpoint}` | Endpoints in this update whose latest weight is older than the expiration period. |
| `grpc.lb.wrr.endpoint_weights` | Histogram | `{weight}` | Weight of each endpoint in this update (0 if not usable). |

## 8. API Requirements

- gRPC MUST register this policy under the name `weighted_round_robin`, so
  that it can be selected through `loadBalancingConfig` in the service
  config and used as a child by other policies, including custom ones
  ([../load-balancing.md](../load-balancing.md)).
