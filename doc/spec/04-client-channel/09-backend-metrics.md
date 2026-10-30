> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4.9 Client-Side Backend Metrics (ORCA)

<!-- Sources: A51, A58, A64, A85, xds/data/orca/v3/orca_load_report.proto, xds/service/orca/v3/orca.proto -->

> **Introduced by:** [gRFC A51: Custom Backend Metrics Support](https://github.com/grpc/proposal/blob/master/A51-custom-backend-metrics.md)

Servers can report **backend metrics** (utilization, request cost, QPS, and
so on) to clients, encoded as ORCA `xds.data.orca.v3.OrcaLoadReport`
messages. Clients use them to make load-balancing decisions, for example in
[`weighted_round_robin`](lb-policies/weighted_round_robin.md), and to
propagate them to a load-reporting server (see
[Load Reporting](../09-xds/09-load-reporting.md)).

There are two ways to receive reports:

| Mode | Transport | Granularity | Typical use |
| --- | --- | --- | --- |
| **Per-call** | `endpoint-load-metrics-bin` trailing-metadata entry on each call | One report per call, describing that call and the server's state when it ended | Request cost; utilization when calls are frequent |
| **Out-of-band (OOB)** | A long-lived `OpenRcaService/StreamCoreMetrics` stream on each connection | Periodic reports of server-wide utilization, independent of calls | Utilization when calls are infrequent, or to avoid per-call overhead |

This section specifies the client side: how reports are received and how
LB policies consume them. The report data model, the wire format, the
server-side recorders, and the server's `OpenRcaService` implementation are
specified in [Backend Metrics (ORCA)](../07-services/03-orca.md).

## 1. Report Representation

- A received report is deserialized from its binary protobuf encoding into
  an `OrcaLoadReport` and exposed to LB policies as a read-only value. The
  same type is used for per-call and OOB reports.
- A report MUST be deserialized at most once, however many LB policies
  consume it.
- If a per-call report cannot be parsed as an `OrcaLoadReport`, the client
  treats it as absent and MAY log the error. A malformed report never
  affects the call's status, or any other call on the connection. (Invalid
  base64 in the trailer is handled by the transport's general binary-header
  rules, before the report is seen; see
  [gRPC over HTTP/2](../03-wire-protocol/01-http2.md).) Field values that are
  out of range, such as a negative utilization, do not make a report
  malformed; consumers apply their own checks.
- If an OOB report cannot be deserialized, the client ends the OOB stream
  and restarts it as for any other stream failure (see
  [Stream Lifecycle](06-subchannels.md#92-stream-lifecycle)).

## 2. Per-Call Reports

- The server sends a per-call report as the value of the
  `endpoint-load-metrics-bin` trailing-metadata entry (see
  [Backend Metrics (ORCA): Per-Request Reporting](../07-services/03-orca.md)). It can appear in normal trailers and in
  a Trailers-Only response.
- An LB policy receives per-call reports through the call tracker it
  attaches to a pick result
  ([Load Balancing](05-load-balancing.md#64-call-completion-tracking)).
  When the call ends, the tracker is given the parsed report, if one was
  present, along with the call's status and trailing metadata.
- Only calls whose pick attached a tracker that asks for backend metrics
  cause the client to parse the report. If no policy asks for it, the
  client MAY skip parsing it.
- If a policy expects a report and none is present, it ignores the call
  for metrics purposes. A missing report is not an error.
- Parent policies see per-call reports for picks their children make only
  if they wrap the child's picker and attach their own tracker.

## 3. Out-of-Band Reports

OOB reports use the connection-scoped watcher and stream mechanism
specified in [Subchannels and Connections: Connection-Scoped Watchers and Streams](06-subchannels.md#9-connection-scoped-watchers-and-streams).
This section specifies only what is specific to OOB backend metrics.

### 3.1 Watchers

- An LB policy subscribes to OOB reports for a subchannel by registering an
  **OOB backend metric watcher** on it, with a requested reporting
  interval. A policy at any level of the tree can do this, including for
  subchannels its descendants create, by intercepting `CreateSubchannel()`
  in the helper it gives them.
- All OOB watchers on a subchannel share one producer and one stream.
- The **effective interval** is the smallest interval requested by the
  current watchers.

### 3.2 Stream

- **Method.** `/xds.service.orca.v3.OpenRcaService/StreamCoreMetrics`, a
  server-streaming method.
- **Request.** A single `OrcaLoadReportRequest` with `report_interval` set
  to the effective interval. `request_cost_names` is left empty.
- **Lifecycle.** As specified in
  [Stream Lifecycle](06-subchannels.md#92-stream-lifecycle). In particular: the
  stream runs on a READY connection while at least one watcher is
  registered; it is restarted with the new interval when the effective
  interval changes; it is never retried on a connection after
  `UNIMPLEMENTED`; other failures are retried with backoff that is reset
  when a report is received; and it is cancelled on GOAWAY, connection
  loss, removal of the last watcher, or subchannel shutdown.
- **Server interval.** The server may send reports less often than
  requested. It enforces its own minimum interval (see
  [Server Behavior](../07-services/03-orca.md)). Clients MUST NOT assume reports arrive
  at exactly the requested interval.

### 3.3 Delivery

- Each `OrcaLoadReport` received on the stream is delivered, unchanged, to
  every OOB watcher registered on the subchannel at that time. The client
  does not aggregate, filter, or rate-limit reports. Each policy does its
  own aggregation and decides how long a report remains valid (for
  example, `weighted_round_robin`'s weight expiration period).
- Every report is a complete snapshot of the server's state. Fields that
  are absent in a report are unset; they do not inherit values from
  earlier reports.
- Watchers are not notified when the stream fails, ends with
  `UNIMPLEMENTED`, or is restarted. They simply stop receiving reports
  until a new report arrives. A policy that needs to detect stale data
  MUST track the time of the last report itself.
- OOB reports carry server-wide utilization metrics. They are not
  propagated to load reporting (LRS); only per-call reports are (see
  [Load Reporting (LRS)](../09-xds/09-load-reporting.md)).

## 4. Consumers in This Specification

| Consumer | Mode | Use |
| --- | --- | --- |
| [`weighted_round_robin`](lb-policies/weighted_round_robin.md) | Per-call or OOB (configurable) | Computes endpoint weights from QPS, EPS, and utilization. |
| [`xds_cluster_impl`](../09-xds/lb-policies/xds_cluster_impl.md) | Per-call | Propagates selected metrics into LRS load reports. |

Custom LB policies can use either mode through the same APIs.

## 5. API Requirements

- The LB policy API MUST let a picker attach a call tracker that receives
  the parsed per-call backend metrics report (if any) when the call ends
  ([Load Balancing](05-load-balancing.md)).
- The internal subchannel API MUST let LB policies at any level of the
  tree register and unregister OOB backend metric watchers on a
  subchannel, with a requested reporting interval, and change that
  interval without re-registering or with re-registration that has the
  same effect.
- Both capabilities MUST be available to custom LB policies registered by
  applications.
- These APIs MUST deliver reports in the same `OrcaLoadReport`
  representation for both modes.

