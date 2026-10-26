# `outlier_detection` LB Policy

<!-- Sources: A50, A61, grpc/service_config/service_config.proto (OutlierDetectionLoadBalancingConfig) -->

> **Experimental:** The policy is registered as
> `outlier_detection_experimental`. Its name and configuration are not
> yet stable.

## 1. Purpose

`outlier_detection` is a parent policy with one child. It watches the
results of calls that the child sends to each endpoint, and temporarily
**ejects** endpoints whose error rates are outliers. An ejected endpoint
is reported unhealthy to the child through the generic health watch
([../load-balancing.md](../load-balancing.md)), so the child stops
using it. The endpoint's connections are kept open, so that it can be
used again immediately when it is un-ejected.

Ejection decisions are per endpoint: calls sent to any address of an
endpoint count toward that endpoint, and ejecting the endpoint affects
the subchannels for all of its addresses. Ejection only affects children
that consume the health state. That means petiole policies, through their
`pick_first` children. It has no effect when the child is `pick_first`
used directly.

The policy is not xDS-specific. For how xDS configures it, see
[../../09-xds/lb-policies.md](../../09-xds/lb-policies.md).

Registered name: `outlier_detection_experimental`.

## 2. Configuration

Proto: `OutlierDetectionLoadBalancingConfig` in
`grpc/service_config/service_config.proto`.

```json
{
  "outlier_detection_experimental": {
    "interval": "10s",
    "baseEjectionTime": "30s",
    "maxEjectionTime": "300s",
    "maxEjectionPercent": 10,
    "successRateEjection": {
      "stdevFactor": 1900, "enforcementPercentage": 100,
      "minimumHosts": 5, "requestVolume": 100
    },
    "failurePercentageEjection": {
      "threshold": 85, "enforcementPercentage": 100,
      "minimumHosts": 5, "requestVolume": 50
    },
    "childPolicy": [ { "round_robin": {} } ]
  }
}
```

| Field (JSON) | Type | Default | Description |
| --- | --- | --- | --- |
| `interval` | Duration | 10 s | Time between ejection-analysis sweeps. |
| `baseEjectionTime` | Duration | 30 s | Base ejection duration. The actual duration is this multiplied by the endpoint's ejection multiplier. |
| `maxEjectionTime` | Duration | max(300 s, `baseEjectionTime`) | Upper bound on ejection duration. |
| `maxEjectionPercent` | uint32 | 10 | Maximum percentage of endpoints that can be ejected at once. Ejection never takes the ejected percentage above this value, so `0` disables ejection. |
| `successRateEjection` | object | unset | If set, run the success-rate algorithm. |
| `successRateEjection.stdevFactor` | uint32 | 1900 | Ejection threshold factor, in thousandths (1900 means 1.9). |
| `successRateEjection.enforcementPercentage` | uint32 | 100 | Percent chance of actually ejecting a detected outlier. |
| `successRateEjection.minimumHosts` | uint32 | 5 | Minimum number of endpoints with enough volume to run the algorithm. |
| `successRateEjection.requestVolume` | uint32 | 100 | Minimum calls in an interval for an endpoint to be considered. |
| `failurePercentageEjection` | object | unset | If set, run the failure-percentage algorithm. |
| `failurePercentageEjection.threshold` | uint32 | 85 | Failure percentage above which an endpoint is an outlier. |
| `failurePercentageEjection.enforcementPercentage` | uint32 | 100 | Percent chance of actually ejecting a detected outlier. |
| `failurePercentageEjection.minimumHosts` | uint32 | 5 | Minimum number of endpoints with enough volume to run the algorithm. |
| `failurePercentageEjection.requestVolume` | uint32 | 50 | Minimum calls in an interval for an endpoint to be considered. |
| `childPolicy` | `LoadBalancingConfig` list | — | Required. The child policy. |

### 2.1 Validation

The config is invalid if any of the following holds:

- `interval`, `baseEjectionTime`, or `maxEjectionTime` is not a valid
  `google.protobuf.Duration`, or is negative.
- `maxEjectionPercent`, `successRateEjection.enforcementPercentage`,
  `failurePercentageEjection.threshold`, or
  `failurePercentageEjection.enforcementPercentage` is greater than 100.
- `childPolicy` is missing or invalid (see
  [../load-balancing.md](../load-balancing.md)).

If both `successRateEjection` and `failurePercentageEjection` are unset,
outlier detection is disabled: the policy passes everything through and
does not count calls.

## 3. State

The policy keeps two maps:

- **Endpoint map**, keyed by the unordered set of an endpoint's addresses
  (ignoring attributes). Each entry holds:
  - A call counter with two buckets (active and inactive), each counting
    successes and failures.
  - The ejection timestamp (null if not ejected).
  - The ejection multiplier (starts at 0).
- **Subchannel map**, keyed by individual address (ignoring attributes).
  Each entry holds the subchannel wrappers for that address, and a
  reference to the endpoint map entry for the endpoint that contains the
  address.

Both maps are rebuilt from the endpoint list in each update. Entries for
endpoints and addresses still present are kept. New ones are added, and
removed ones are deleted. The subchannel map's endpoint references are
updated if an endpoint's address set changed. The update is then passed
to the child unchanged.

Call counts are updated from the data plane, and the endpoint map is used
from the control plane, so access to them MUST be synchronized.

## 4. Subchannel Wrapping and Ejection

The policy intercepts `CreateSubchannel()` from the child and wraps every
subchannel it returns. If the subchannel's address is in the subchannel
map, the wrapper is added to that entry. If the address's endpoint is
currently ejected, the wrapper starts out ejected.

The wrapper intercepts the **health state watch**. The raw connectivity
watch passes through unchanged.

- **Not ejected:** health watchers receive the underlying subchannel's
  health state.
- **`eject()`:** the wrapper reports TRANSIENT_FAILURE to health watchers,
  with an `UNAVAILABLE` status saying that the endpoint was ejected by
  outlier detection. It stops passing along underlying updates.
- **`uneject()`:** the wrapper reports the latest underlying health state
  and resumes passing updates along.

**Eject an endpoint:** set its ejection timestamp to the sweep's
timestamp, increase its multiplier by 1, and call `eject()` on the
wrappers for all of its addresses.

**Un-eject an endpoint:** set its ejection timestamp to null and call
`uneject()` on the wrappers for all of its addresses.

## 5. Picker and Call Counting

The policy reports the child's state unchanged, with a picker that wraps
the child's picker. When outlier detection is enabled, and the child
returns Complete with a wrapped subchannel whose endpoint is in the
endpoint map, the picker attaches a call tracker. When the call
finishes, the tracker increments the success count (status `OK`) or the
failure count (any other status) in that endpoint's active bucket.

## 6. Ejection Timer

The policy remembers the start time of the most recent timer. On each
config update:

- **If outlier detection is enabled:**
  - If there is no recorded start time, record the current time, start
    the timer for `interval`, and reset every endpoint's call counters.
  - Otherwise, cancel the timer and restart it for
    `interval − (now − start time)`, or 0 if that is negative.
- **If outlier detection is disabled:**
  - Cancel the timer and clear the start time.
  - Un-eject all ejected endpoints, and reset every multiplier to 0.

When the timer fires, it records the current time as the new start time
and does the following:

1. Record `sweep_time = now()`.
2. For each endpoint, swap the counter buckets: the active bucket becomes
   inactive, and the old inactive bucket is zeroed and becomes active.
   The inactive bucket now holds the counts for the last interval.
3. If `successRateEjection` is set, run the success-rate algorithm.
4. If `failurePercentageEjection` is set, run the failure-percentage
   algorithm.
5. For each endpoint:
   - If not ejected and the multiplier is greater than 0, decrease the
     multiplier by 1.
   - If ejected and
     `now() > ejection_timestamp + min(baseEjectionTime × multiplier, max(baseEjectionTime, maxEjectionTime))`,
     un-eject it.
6. Restart the timer for `interval`.

The volume of an endpoint is `successes + failures` in its inactive
bucket. The ejected percentage is
`100 × (ejected endpoints) / (endpoints in map)`.

### 6.1 Success-Rate Algorithm

```
candidates = [e for e in endpoints if e.volume >= sr.request_volume]
if len(candidates) < sr.minimum_hosts: return
rates = [e.successes / e.volume for e in candidates]
mean = average(rates); stdev = population_standard_deviation(rates)
threshold = mean - stdev * (sr.stdev_factor / 1000)
for e in candidates:
  if ejected_percentage() >= max_ejection_percent: return
  if success_rate(e) < threshold and random_int(0, 100) < sr.enforcement_percentage:
    eject(e)
```

### 6.2 Failure-Percentage Algorithm

```
candidates = [e for e in endpoints if e.volume >= fp.request_volume]
if len(candidates) < fp.minimum_hosts: return
for e in candidates:
  if ejected_percentage() >= max_ejection_percent: return
  if 100 * e.failures / e.volume > fp.threshold and random_int(0, 100) < fp.enforcement_percentage:
    eject(e)
```

`random_int(0, 100)` is uniform over `[0, 100)`. Endpoints that are
already ejected are not ejected again.

## 7. Other Operations

`ExitIdle()`, `ResetBackoff()`, and re-resolution requests pass straight
through to and from the child.

## 8. API Requirements

- gRPC MUST register this policy under the name
  `outlier_detection_experimental`, so that it can be selected through
  `loadBalancingConfig` in the service config and used as a child by other
  policies, including custom ones
  ([../load-balancing.md](../load-balancing.md)).
