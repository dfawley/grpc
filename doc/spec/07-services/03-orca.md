> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 7.3 Backend Metrics (ORCA)

<!-- Sources: A51, xds/data/orca/v3/orca_load_report.proto, xds/service/orca/v3/orca.proto (cncf/xds) -->

> **Introduced by:** [gRFC A51: Custom Backend Metrics Support](https://github.com/grpc/proposal/blob/master/A51-custom-backend-metrics.md)

gRPC servers can report backend metrics, such as CPU, memory, and
application-defined values, to clients. Client-side load balancing policies use
them to make routing decisions. Examples are weighted round robin
([Client-Side Backend Metrics](../04-client-channel/09-backend-metrics.md),
[weighted_round_robin](../04-client-channel/lb-policies/weighted_round_robin.md))
and xDS load reporting ([LRS](../09-xds/09-load-reporting.md)). The data model
and the out-of-band service come from ORCA (Open Request Cost Aggregation).

There are two reporting mechanisms:

* **Per-request reporting.** When an RPC completes, the server attaches a load
  report to its trailers. This works best for short RPCs at high request rates.
* **Out-of-band (OOB) reporting.** The server periodically pushes load reports
  on a dedicated streaming RPC. This works whether RPCs are unary or
  long-lived streams, or whether there are any RPCs at all.

There are two kinds of metrics:

* **Request cost** metrics: the resources it took to handle one particular
  request.
* **Utilization** metrics: the server's state, independent of any RPC.

## 1. Data Model

A load report is an `xds.data.orca.v3.OrcaLoadReport` message, defined in
`xds/data/orca/v3/orca_load_report.proto` in the cncf/xds repository.

| Field | Number | Type | Meaning | Valid range |
| --- | --- | --- | --- | --- |
| `cpu_utilization` | 1 | `double` | CPU utilization as a fraction of the available CPU. Can be above 1.0 when usage exceeds the reporter's soft limit. | [0, ∞) |
| `mem_utilization` | 2 | `double` | Memory utilization as a fraction of the available memory. | [0, 1] |
| `rps` | 3 | `uint64` | Deprecated. gRPC MUST NOT set it. Use `rps_fractional`. | — |
| `request_cost` | 4 | `map<string, double>` | Application-defined request costs. Each value is an absolute cost for this request (for example, bytes of storage). | any |
| `utilization` | 5 | `map<string, double>` | Named resource utilizations, each as a fraction of the total available. | each value in [0, 1] |
| `rps_fractional` | 6 | `double` | Total requests per second (queries per second, "QPS") served by the endpoint, across all its services. | [0, ∞) |
| `eps` | 7 | `double` | Total errors per second served by the endpoint, across all its services. | [0, ∞) |
| `named_metrics` | 8 | `map<string, double>` | Opaque application-defined metrics. The application decides whether each one is per-request or per-server. | any |
| `application_utilization` | 9 | `double` | Application-defined utilization as a fraction of available resources (for example, the larger of CPU and memory utilization). Can be above 1.0. | [0, ∞) |


A field that is unset (zero for scalars, missing for map keys) means "not
reported". Utilization values should come from the latest sample or
measurement.

Recorders MUST ignore values outside the valid range. Recording such a value
leaves any previously recorded value for that metric unchanged. This applies
to every operation that records a single value; the bulk `setAllUtilization`
operation ([Per-Server Recorder](#3-per-server-recorder)) stores its map as given.

## 2. Per-Request Reporting

### 2.1 Wire Format

The server serializes the per-request load report in protobuf binary format and
sends it as trailer metadata under the key **`endpoint-load-metrics-bin`**.
Because the key ends in `-bin`, the value is a binary metadata value. Over
HTTP/2 it is base64-encoded, as specified in [gRPC over HTTP/2](../03-wire-protocol/01-http2.md).
The key is sent only in Trailers, or in a Trailers-Only response, and never in
Response-Headers.

If nothing was recorded for an RPC (and no per-server recorder supplied any
data), the server SHOULD omit `endpoint-load-metrics-bin`.

### 2.2 Per-Call Recorder

When per-request reporting is enabled on a server, every RPC gets a
**per-call metric recorder**, reachable from the handler's call context
([Server: Call Context Available to Handlers](../05-server/README.md)). The recorder offers these operations:

```
recordCpuUtilization(value)               // -> cpu_utilization
recordMemoryUtilization(value)            // -> mem_utilization
recordApplicationUtilization(value)       // -> application_utilization
recordQps(value)                          // -> rps_fractional
recordEps(value)                          // -> eps
recordUtilization(name, value)            // -> utilization[name]
recordRequestCost(name, value)            // -> request_cost[name]
recordNamedMetric(name, value)            // -> named_metrics[name]
```

* The operations can be called at any point during the RPC and from any thread.
* **Last write wins.** Recording the same metric (or the same name in a map)
  again replaces the earlier value.
* The server reads the recorder when the RPC completes, merges it with the
  per-server recorder if one is configured ([Merging with the Per-Server Recorder](#23-merging-with-the-per-server-recorder)),
  and encodes the result into `endpoint-load-metrics-bin`.

### 2.3 Merging with the Per-Server Recorder

The application MAY give the per-request reporting mechanism a **per-server
recorder** ([Per-Server Recorder](#3-per-server-recorder)). The report for an RPC is then
built as follows:

```
report = snapshot(per_server_recorder)           // may be empty
for each scalar metric m set in per_call_recorder:
  report.m = per_call_recorder.m                 // per-call wins
for each map M in {utilization, request_cost, named_metrics}:
  for each (name, value) in per_call_recorder.M:
    report.M[name] = value                       // per-call wins per key
```

When a metric is recorded both per call and per server, the **per-call value
takes precedence**.

Per-request reporting is implemented as a server-side per-call behavior that
runs where interceptors run ([Server: Server Interceptors](../05-server/README.md)). It adds the trailer to
every RPC served while it is enabled.

## 3. Per-Server Recorder

The per-server recorder holds utilization metrics for the whole server. OOB
reporting reads from it, and per-request reporting can optionally merge it in.
All metrics start **unset**. A metric that has been set stays set until it is
cleared or replaced.

```
setCpuUtilization(value)          clearCpuUtilization()
setMemoryUtilization(value)       clearMemoryUtilization()
setApplicationUtilization(value)  clearApplicationUtilization()
setQps(value)                     clearQps()          // rps_fractional
setEps(value)                     clearEps()
putUtilization(name, value)       clearUtilization(name)
setAllUtilization(map)            // replaces the whole utilization map
```

* Last write wins for each metric and each `utilization` key.
* Any operation can be called concurrently with any other. Atomicity across
  several updates is **not** guaranteed: a report can reflect some of a set of
  concurrent updates and not others.
* `setAllUtilization` replaces the whole map with the given map. It does not
  range-check the values.

## 4. Out-of-Band Reporting

### 4.1 Service Definition

The OOB service is `xds.service.orca.v3.OpenRcaService`, defined in
`xds/service/orca/v3/orca.proto` (cncf/xds):

```protobuf
service OpenRcaService {
  rpc StreamCoreMetrics(OrcaLoadReportRequest)
      returns (stream xds.data.orca.v3.OrcaLoadReport);
}

message OrcaLoadReportRequest {
  // Interval for generating Open RCA core metric responses.
  google.protobuf.Duration report_interval = 1;
  // Request costs to collect.
  repeated string request_cost_names = 2;
}
```

The full method name is `/xds.service.orca.v3.OpenRcaService/StreamCoreMetrics`.

### 4.2 Server Behavior

gRPC provides an implementation of `OpenRcaService` that reads from a
per-server recorder ([Per-Server Recorder](#3-per-server-recorder)). It has one setting,
the **minimum reporting interval**, which defaults to **30 seconds**.

For each `StreamCoreMetrics` call:

1. Compute the effective interval:
   ```
   requested = request.report_interval     // 0 if unset
   interval  = max(requested, min_report_interval)
   ```
   An interval below the minimum, or an unset (zero) one, becomes the minimum.
   There is no upper bound.
2. Right away, take a snapshot of the per-server recorder and send it as an
   `OrcaLoadReport`.
3. Start a timer for this call. Each time it fires after `interval`, take a new
   snapshot, send it, and restart the timer.
4. Each report is **state-of-the-world**: it contains every metric currently
   set in the recorder. The server sends reports on every tick **whether or not
   the data has changed**.
5. The call continues until the client cancels it or the connection closes.
   The server then stops the timer at once and releases the call. The server
   does not end the call with a status while it is serving.

OOB reports carry only **utilization** metrics (`cpu_utilization`,
`mem_utilization`, `application_utilization`, `rps_fractional`, `eps`,
`utilization`). Request costs are tied to individual RPCs and are never sent out
of band, so the server ignores `request_cost_names`. `named_metrics` are not
part of OOB reports either.

A client cannot change the interval of an existing call. To change it, the
client cancels the call and starts a new one.

If the server does not register `OpenRcaService`, `StreamCoreMetrics` fails with
`UNIMPLEMENTED` like any unknown method.

### 4.3 Client Behavior

The client side of out-of-band reporting, and of per-request reporting, is
specified in [Client-Side Backend Metrics](../04-client-channel/09-backend-metrics.md).
In summary, the client opens one `StreamCoreMetrics` call per connection
while at least one LB policy is watching OOB reports for that subchannel,
requests the smallest interval any watcher asked for, never retries the
call on a connection after `UNIMPLEMENTED`, and cancels it on GOAWAY or
subchannel shutdown.

## 5. API Requirements

The server API MUST provide a way to:

1. **Enable per-request reporting** on a server, optionally with a per-server
   recorder whose data is merged into each per-request report.
2. **Get the per-call recorder** for the current RPC from the handler's call
   context, and record each metric listed in [Per-Call Recorder](#22-per-call-recorder).
   Getting the recorder when per-request reporting is disabled MUST be safe. It
   either returns a recorder whose data is not sent, or indicates that no
   recorder is available.
3. **Create a per-server recorder** and set and clear each metric listed in
   [Per-Server Recorder](#3-per-server-recorder), safely from any thread.
4. **Create the OOB service** (`OpenRcaService`) with a per-server recorder and
   an optional minimum reporting interval (default 30 seconds), and register it
   on a server like any other service.

The client-side (LB policy) API for consuming per-request and OOB reports is
specified in [Client-Side Backend Metrics](../04-client-channel/09-backend-metrics.md).
