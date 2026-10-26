# Load Reporting (LRS)

<!-- Sources: A27, A32, A42, A47, A64, A85, envoy/service/load_stats/v3/lrs.proto, envoy/config/endpoint/v3/load_report.proto -->

When an xDS cluster enables load reporting, the gRPC client reports
client-side load statistics for that cluster to a Load Reporting Service (LRS)
server. It uses the LRS protocol
(`envoy.service.load_stats.v3.LoadReportingService`). Stats are recorded by
the `xds_cluster_impl` LB policy (see [Load reporting](lb-policies/xds_cluster_impl.md)). They are
aggregated and sent by an **LRS client** that belongs to the XdsClient (see
[XdsClient](xds-client.md)).

## 1. When Load Reporting Is Enabled

- Load reporting is enabled for a cluster if and only if the Cluster resource
  sets `lrs_server`. The only supported form is a `ConfigSource` with `self`
  set (see [resources/cluster.md](resources/cluster.md) for validation).
- `self` means **the xDS server from which this Cluster resource was
  obtained**. The XdsClient expands it to that server's full bootstrap
  definition (server URI, channel credentials, and server features; see
  [Bootstrap](bootstrap.md)) and includes it in the parsed Cluster
  resource. If the Cluster is later obtained from a different server (for
  example, after fallback), the parsed resource changes, and load is reported
  to the new server.
- The LRS client MUST accept only LRS servers that match a server already
  configured in the bootstrap (same server URI, channel credentials, and
  server features). This keeps configuration from directing credentials to
  an arbitrary server.
- If `lrs_server` is not set, no stats are recorded for the cluster, and its
  drops and circuit breaker drops are not reported.

## 2. Stats Model

The LRS client stores stats **per LRS server**. For each server, stats are
keyed by **(cluster name, EDS service name)**. For LOGICAL_DNS clusters the
EDS service name is empty. For each key, the LRS client keeps:

- **Drop stats:** a count for each drop category name, and an
  **uncategorized** drop count.
  - Each EDS `drop_overloads` drop is counted under its category (see
    [Drops](lb-policies/xds_cluster_impl.md)).
  - Each circuit breaker drop is counted as uncategorized (see
    [Circuit breaking](lb-policies/xds_cluster_impl.md)).
- **Locality stats:** for each locality (region, zone, sub-zone; LOGICAL_DNS
  endpoints use the empty locality):

  | Counter | Meaning | Reset after each report |
  | --- | --- | --- |
  | `total_issued_requests` | Calls started on an endpoint of this locality (completed picks) | Yes |
  | `total_successful_requests` | Calls that finished with status OK | Yes |
  | `total_error_requests` | Calls that finished with any non-OK status | Yes |
  | `total_requests_in_progress` | Calls started and not yet finished | **No**. It is a gauge. |
  | backend metrics | Aggregated per-request ORCA data ([Backend Metrics from ORCA](#4-backend-metrics-from-orca)) | Yes |

Calls that are dropped, or whose picks fail or are queued, are never counted
in locality stats.

The `xds_cluster_impl` policy obtains stats objects from the LRS client. Their
interfaces are:

- `GetDropStats(lrs_server, cluster, eds_service_name)` → object with
  `AddCallDropped(category)` and `AddUncategorizedDrop()`.
- `GetLocalityStats(lrs_server, cluster, eds_service_name, locality,
  backend_metric_propagation)` → object with `AddCallStarted()` (increments
  issued and in-progress) and `AddCallFinished(backend_metrics, failed)`
  (increments successful or error, decrements in-progress, and aggregates the
  ORCA data allowed by the propagation config).

Stats objects are reference-counted and shared by all users with the same key.
The backend metric propagation config is part of the locality stats key, so
two clusters that report the same locality with different propagation configs
get separate objects. Their snapshots are merged into one
`UpstreamLocalityStats` when a report is built. When a stats object is
released, its final unreported counts MUST be kept and included in the next
report. They are then discarded.

## 3. LRS Stream Protocol

### 3.1 Stream lifecycle

- The LRS client keeps at most one LRS stream per LRS server. The stream uses
  the method
  `/envoy.service.load_stats.v3.LoadReportingService/StreamLoadStats` on the
  XdsClient's channel to that server. It is created with wait_for_ready set.
- The stream is started when the first stats object for that server is
  created. It is stopped when the server has no stats objects left and all
  final counts have been reported.
- If the stream fails, it MUST be restarted after a backoff delay, using the
  exponential backoff algorithm and parameters defined for connection backoff
  in [Subchannels](../04-client-channel/subchannels.md) (initial delay
  1 second, multiplier 1.6, jitter 0.2, maximum delay 120 seconds). The
  backoff is reset if the failed stream had received at least one response.

### 3.2 Initial request

The first `LoadStatsRequest` on each stream contains only `node`. It is
populated as for ADS requests (see [XdsClient](xds-client.md) and
[Bootstrap](bootstrap.md)), including `user_agent_name` and
`user_agent_version`. Its `client_features` MUST include
`envoy.lrs.supports_send_all_clusters`. It contains no `cluster_stats`.

### 3.3 Responses

Each `LoadStatsResponse` from the server sets the reporting parameters:

| Field | Use |
| --- | --- |
| `send_all_clusters` | If true, report all clusters that have stats for this server. |
| `clusters` | If `send_all_clusters` is false, report only clusters whose **cluster name** is in this list. |
| `load_reporting_interval` | The interval between reports. Values below 1 second MUST be treated as 1 second. |
<!-- REVIEW(divergence) [XDS_LRS-1]: minimum load_reporting_interval (no gRFC defines one). Java: no minimum; an interval ≤ 0 means no reports are scheduled (xds/client/LoadReportClient.java); Go: no minimum; the value goes straight to time.NewTicker, which panics on ≤ 0 (internal/xds/clients/lrsclient/lrs_stream.go); C++: clamps to 1s (GRPC_XDS_MIN_CLIENT_LOAD_REPORTING_INTERVAL_MS, xds_client/lrs_client.cc). spec says: clamp to 1s. Separately, Go honors only the first LoadStatsResponse on a stream and ignores later ones. -->

- The client MUST NOT send any load report before it receives the first
  response.
- A response identical to the current parameters is ignored.
- If the interval changes, the report timer is restarted with the new
  interval.
- Stats for clusters the server did not ask for are still reset at each
  report and are discarded, so that a later request for those clusters does
  not include data from earlier intervals.

### 3.4 Load reports

Every `load_reporting_interval`, the client builds a snapshot of all stats for
the server and resets the resettable counters. It sends one
`LoadStatsRequest` whose `cluster_stats` has one `ClusterStats` per requested
(cluster, EDS service name) key:

| `ClusterStats` field | Value |
| --- | --- |
| `cluster_name` | The cluster name. |
| `cluster_service_name` | The EDS service name, if not empty. |
| `upstream_locality_stats` | One entry per locality with stats ([Locality stats](#35-locality-stats)). |
| `dropped_requests` | One `{category, dropped_count}` entry per drop category with a count in this interval. |
| `total_dropped_requests` | Sum of all categorized drop counts plus the uncategorized (circuit breaker) drop count. |
| `load_report_interval` | The actual time since the previous report for this key (or since its stats were created). |

If all counters in the snapshot are zero, and they were also all zero in the
previous report, the client SHOULD skip sending the report. It still schedules
the next one.

After a report has been sent (the send completed), the client schedules the
next report one interval later.

### 3.5 Locality stats

Each `UpstreamLocalityStats` entry contains:

- `locality`: `region`, `zone`, and `sub_zone`. Empty values are omitted.
- `total_successful_requests`, `total_requests_in_progress`,
  `total_error_requests`, and `total_issued_requests`, as defined in
  [Stats Model](#2-stats-model).
- `cpu_utilization`, `mem_utilization`, `application_utilization`
  (`UnnamedEndpointLoadMetricStats`): set only if the propagation config
  includes the field and the aggregate is not zero. Each has
  `num_requests_finished_with_metric` and `total_metric_value`.
- `load_metric_stats`: one `EndpointLoadMetricStats` per propagated named
  metric, with `metric_name`, `num_requests_finished_with_metric`, and
  `total_metric_value`.

gRPC reports per-locality stats only. It does not report per-endpoint stats
(`upstream_endpoint_stats`).

## 4. Backend Metrics from ORCA

The client can propagate backend metrics reported by servers through ORCA (see
[Backend Metrics (ORCA)](../07-services/orca.md)) to LRS. What is
propagated is controlled per cluster by the Cluster resource's
`lrs_report_endpoint_metrics` field (see
[resources/cluster.md](resources/cluster.md)).

### 4.1 Propagation config

`lrs_report_endpoint_metrics` is a list of strings. gRPC MUST support these
values:

| Value | Effect |
| --- | --- |
| `cpu_utilization` | Propagate ORCA `cpu_utilization` to `UpstreamLocalityStats.cpu_utilization`. |
| `mem_utilization` | Propagate ORCA `mem_utilization` to `UpstreamLocalityStats.mem_utilization`. |
| `application_utilization` | Propagate ORCA `application_utilization` to `UpstreamLocalityStats.application_utilization`. |
| `named_metrics.*` | Propagate every entry of the ORCA `named_metrics` map. |
| `named_metrics.<key>` | Propagate the ORCA `named_metrics` entry with key `<key>`. |

- Other strings MUST be ignored, for forward compatibility.
- If the field is unset or empty, **nothing** is propagated from ORCA to LRS.
- A propagated named metric with ORCA key `k` is reported in
  `load_metric_stats` with `metric_name` = `named_metrics.k`.

### 4.2 Aggregation

- Only **per-request** ORCA reports (received in a call's trailing metadata)
  are used. Out-of-band ORCA reports MUST NOT be propagated to LRS.
- Each per-request report counts as one request. When a call finishes with a
  report, then for each propagated field present in it:
  `num_requests_finished_with_metric += 1` and
  `total_metric_value += value`, tracked separately for each field and each
  named metric key, per locality.
- Values are opaque to gRPC. They are not validated, and they are always
  summed.
- Aggregates are reset after each report.

Example: named metrics with `lrs_report_endpoint_metrics: ["named_metrics.*"]`
and three per-request reports for one locality:

```textproto
# report 1
named_metrics { key: "key1" value: 1.0 }
named_metrics { key: "key2" value: 2.0 }
# report 2
named_metrics { key: "key2" value: 3.0 }
named_metrics { key: "key3" value: 4.0 }
# report 3: no named_metrics
```

produce:

```textproto
upstream_locality_stats {
  load_metric_stats { metric_name: "named_metrics.key1" num_requests_finished_with_metric: 1 total_metric_value: 1.0 }
  load_metric_stats { metric_name: "named_metrics.key2" num_requests_finished_with_metric: 2 total_metric_value: 5.0 }
  load_metric_stats { metric_name: "named_metrics.key3" num_requests_finished_with_metric: 1 total_metric_value: 4.0 }
}
```

## 5. API Requirements

Load reporting has no application-facing API. It is configured entirely by the
xDS server. Internally:

- The XdsClient MUST give LB policies access to its LRS client, through the
  XdsClient resolver attribute (see [Client Data Plane: Resolver Result](client.md)).
- The LB picker API MUST let a policy observe the end of each call, with its
  final status and its per-request ORCA backend metric data (see
  [Load Balancing](../04-client-channel/load-balancing.md)).
