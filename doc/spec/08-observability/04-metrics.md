> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 8.4 Metric Catalog

<!-- Sources: A66, A78, A79, A88, A89, A94, A96, A108, A118 -->

This section lists every metric that gRPC defines. The framework is specified
in [Metrics Framework and OpenTelemetry Plugin](03-metrics-framework.md), and the event points in
[Instrumentation Architecture](02-instrumentation.md). In the tables, "Required labels" MUST always be
present. "Optional labels" are recorded only when the stats plugin is
configured to record them (see [Metrics Framework and OpenTelemetry Plugin](03-metrics-framework.md)). Histogram bucket
sets refer to the defaults in [Metrics Framework and OpenTelemetry Plugin](03-metrics-framework.md).

## 1. Common Attributes (Labels)

| Label | Values | Used by |
| --- | --- | --- |
| `grpc.method` | Fully-qualified method name without the leading `/`, e.g. `google.bigtable.v2.Bigtable/CheckAndMutateRow`. Generic (unregistered) methods are recorded as `other` unless the application's generic method attribute predicate allows them. | Per-call client and server metrics, retry metrics |
| `grpc.status` | Status code name, e.g. `OK`, `CANCELLED`, `DEADLINE_EXCEEDED` (see [Core RPC Semantics](../02-rpc-semantics/README.md)). On the client it is the status the attempt or call ended with, whether received from the server or generated locally. On the server it is the status sent. For TLS offload metrics, it is the result of the offloaded operation. | Attempt, call, and server metrics; TLS offload metrics |
| `grpc.target` | Canonical target URI of the channel (see [Metrics Framework and OpenTelemetry Plugin](03-metrics-framework.md)). For XdsClient metrics on servers, the value is `#server`. | All client-side metrics |
| `grpc.lb.locality` | `{region="${REGION}", zone="${ZONE}", sub_zone="${SUB_ZONE}"}` with the xDS locality values substituted. Empty string if no locality is known. | Attempt metrics, WRR, subchannel, TLS client metrics |
| `grpc.lb.backend_service` | The backend service the traffic is sent to. This matters when one channel target can route to different sets of servers. With xDS it is the (leaf) cluster name. Empty string if not applicable. | Attempt metrics, WRR, subchannel, TLS client metrics |
| `grpc.client.call.custom` | The application-supplied custom telemetry label of the call (see [Instrumentation Architecture](02-instrumentation.md)). Empty string if not set. **Experimental**, and never enabled by default. | All client per-call, per-attempt, and retry metrics |
| `grpc.security_level` | `none`, `integrity_only`, or `privacy_and_integrity` (see [Security](../06-security/README.md)) | `grpc.subchannel.open_connections` |
| `grpc.disconnect_error` | Reason for disconnection ([Subchannel Metrics](#4-subchannel-metrics)) | `grpc.subchannel.disconnections` |
| `grpc.xds.server` | Target URI of the xDS server | XdsClient metrics |
| `grpc.xds.authority` | xDS authority name. `#old` for resource names that are not `xdstp:` names. | XdsClient metrics |
| `grpc.xds.cache_state` | Cache state of a resource ([XdsClient Metrics](#6-xdsclient-metrics)) | XdsClient metrics |
| `grpc.xds.resource_type` | xDS resource type, e.g. `envoy.config.listener.v3.Listener` | XdsClient metrics |
| `grpc.tls.handshake.result` | Handshake result enum string ([TLS Metrics](#7-tls-metrics)) | TLS handshake metrics |
| `grpc.tls.handshake.resumed` | `FULL_HANDSHAKE` or `RESUMED_HANDSHAKE` | TLS handshake metrics |
| `grpc.tls.private_key.offloader_name` | Low-cardinality string identifying the private key signer implementation, e.g. `HSM` | TLS offload metrics |
| `grpc.tls.private_key_algorithm` | Signing algorithm enum string, e.g. `RsaPkcs1Sha256` | TLS offload metrics |

The `grpc.lb.locality` and `grpc.lb.backend_service` values reach the metrics
as follows:

- **Per-attempt metrics:** from the picker (see [Instrumentation Architecture](02-instrumentation.md)).
- **WRR metrics:** from channel-level resolver attributes that are passed down
  the LB tree. The `weighted_target` policy sets a child-name (locality)
  attribute for each child. The `cds` policy (non-aggregate clusters) sets the
  backend-service attribute.
- **Subchannel and TLS client metrics:** from *per-endpoint* attributes. The
  `cds` policy sets locality and backend-service attributes on each endpoint,
  and the subchannel copies them. Because the subchannel is keyed by its
  attributes, a change to these values creates a new subchannel.

See [xDS LB policies](../09-xds/06-lb-policies.md).

## 2. Per-Call Metrics

> **Introduced by:** [gRFC A66: OpenTelemetry Metrics](https://github.com/grpc/proposal/blob/master/A66-otel-stats.md)

The OpenTelemetry plugin records these from its call tracers. They are
**stable and on by default**.

### 2.1 Client Per-Attempt Metrics

| Name | Type | Unit | Required labels | Optional labels | Description and measurement points |
| --- | --- | --- | --- | --- | --- |
| `grpc.client.attempt.started` | Counter (int) | `{attempt}` | `grpc.method`, `grpc.target` | `grpc.client.call.custom` | Number of attempts started, including attempts that have not completed. Incremented when the attempt is created, before the LB pick. Every attempt counts, including transparent retries and hedged attempts. |
| `grpc.client.attempt.duration` | Histogram (double), latency buckets | `s` | `grpc.method`, `grpc.target`, `grpc.status` | `grpc.lb.locality`, `grpc.lb.backend_service`, `grpc.client.call.custom` | End-to-end time of an attempt, from attempt creation (which includes the time to pick a subchannel) until the attempt's status is known. |
| `grpc.client.attempt.sent_total_compressed_message_size` | Histogram (int), size buckets | `By` | `grpc.method`, `grpc.target`, `grpc.status` | `grpc.lb.locality`, `grpc.lb.backend_service`, `grpc.client.call.custom` | Total bytes of all request messages sent on the attempt, after compression and before encryption. Metadata and gRPC and transport framing bytes are excluded. Recorded when the attempt ends. |
| `grpc.client.attempt.rcvd_total_compressed_message_size` | Histogram (int), size buckets | `By` | `grpc.method`, `grpc.target`, `grpc.status` | `grpc.lb.locality`, `grpc.lb.backend_service`, `grpc.client.call.custom` | Total bytes of all response messages received on the attempt, compressed and not encrypted. Metadata and framing are excluded. Recorded when the attempt ends. |

### 2.2 Client Per-Call Metrics

| Name | Type | Unit | Required labels | Optional labels | Description and measurement points |
| --- | --- | --- | --- | --- | --- |
| `grpc.client.call.duration` | Histogram (double), latency buckets | `s` | `grpc.method`, `grpc.target`, `grpc.status` | `grpc.client.call.custom` | End-to-end time for gRPC to complete an RPC from the application's perspective. Starts after the application starts the RPC, before payload serialization. Ends before the status is delivered to the application. |

### 2.3 Server Metrics

| Name | Type | Unit | Required labels | Optional labels | Description and measurement points |
| --- | --- | --- | --- | --- | --- |
| `grpc.server.call.started` | Counter (int) | `{call}` | `grpc.method` | — | Number of server calls started, including calls that have not completed. Incremented at S1 (see [Instrumentation Architecture](02-instrumentation.md)). |
| `grpc.server.call.sent_total_compressed_message_size` | Histogram (int), size buckets | `By` | `grpc.method`, `grpc.status` | — | Total bytes of all response messages sent, compressed and not encrypted, excluding metadata and framing. |
| `grpc.server.call.rcvd_total_compressed_message_size` | Histogram (int), size buckets | `By` | `grpc.method`, `grpc.status` | — | Total bytes of all request messages received, compressed and not encrypted, excluding metadata and framing. |
| `grpc.server.call.duration` | Histogram (double), latency buckets | `s` | `grpc.method`, `grpc.status` | — | End-to-end time of the call from the server transport's perspective, from S1 (first HEADERS frame received and decoded) to S4 (trailers with END_STREAM scheduled, RST_STREAM, or connection abort). |

## 3. Retry Metrics

> **Experimental:** all metrics in this subsection (off by default).

> **Introduced by:** [gRFC A96: OTel Metrics for Retries](https://github.com/grpc/proposal/blob/master/A96-retry-otel-stats.md)

These metrics are recorded by the call tracer when the call ends (C5).

| Name | Type | Unit | Required labels | Optional labels | Description | Recommended buckets |
| --- | --- | --- | --- | --- | --- | --- |
| `grpc.client.call.retries` | Histogram (int) | `{retry}` | `grpc.method`, `grpc.target` | `grpc.client.call.custom` | Number of retry attempts made during the call: non-transparent attempts after the first one, under a retry policy. **Not recorded if zero.** | 1, 2, 3, 4, 5 |
| `grpc.client.call.transparent_retries` | Histogram (int) | `{transparent_retry}` | `grpc.method`, `grpc.target` | `grpc.client.call.custom` | Number of transparent retries during the call. **Not recorded if zero.** | 1, 2, 3, 4, 5, 10 |
| `grpc.client.call.hedges` | Histogram (int) | `{hedge}` | `grpc.method`, `grpc.target` | `grpc.client.call.custom` | Number of hedged attempts made during the call, excluding the original attempt. **Not recorded if zero.** | 1, 2, 3, 4, 5 |
| `grpc.client.call.retry_delay` | Histogram (double) | `s` | `grpc.method`, `grpc.target` | `grpc.client.call.custom` | Total time during the call when there was no active attempt, i.e. the time between the end of one attempt and the start of the next. Even when the policy specifies no delay, this may be non-zero because of the retry mechanism's internal overhead. Time with no active attempt before a transparent retry is included. **Not recorded unless the call made at least one retry or hedged attempt** (that is, unless `grpc.client.call.retries` or `grpc.client.call.hedges` is recorded for the call). | Latency buckets |

## 4. Subchannel Metrics

> **Experimental:** all metrics in this subsection (off by default).

> **Introduced by:** [gRFC A94: OTel metrics for Subchannels](https://github.com/grpc/proposal/blob/master/A94-subchannel-otel-metrics.md)

These metrics are recorded by the subchannel (see
[Subchannels](../04-client-channel/07-subchannels.md)), so they apply whichever
LB policy is in use. A subchannel shared by several channels records each
event once, on the stats plugin group and target of the channel that created
it (see [Metrics Framework and OpenTelemetry Plugin](03-metrics-framework.md)).
The `grpc.target` label value is that channel's canonical target URI, the same
value used by the per-call metrics
([Target Attribute](03-metrics-framework.md#96-target-attribute)).

| Name | Type | Unit | Required labels | Optional labels | Description |
| --- | --- | --- | --- | --- | --- |
| `grpc.subchannel.disconnections` | Counter (int) | `{disconnection}` | `grpc.target` | `grpc.lb.backend_service`, `grpc.lb.locality`, `grpc.disconnect_error` | Number of times an established connection of the subchannel was disconnected. |
| `grpc.subchannel.connection_attempts_succeeded` | Counter (int) | `{attempt}` | `grpc.target` | `grpc.lb.backend_service`, `grpc.lb.locality` | Number of successful connection attempts. |
| `grpc.subchannel.connection_attempts_failed` | Counter (int) | `{attempt}` | `grpc.target` | `grpc.lb.backend_service`, `grpc.lb.locality` | Number of failed connection attempts. |
| `grpc.subchannel.open_connections` | UpDownCounter (int) | `{connection}` | `grpc.target` | `grpc.security_level`, `grpc.lb.backend_service`, `grpc.lb.locality` | Number of open connections. Incremented when a connection is established and decremented when it closes. This includes additional connections created by connection scaling (see [Subchannels](../04-client-channel/07-subchannels.md)). |

If the subchannel is shut down while a connection attempt is in flight, that
attempt MUST NOT be recorded as either succeeded or failed.

`grpc.disconnect_error` values:

| Value | Meaning |
| --- | --- |
| `GOAWAY <ERROR_CODE>` | An HTTP/2 GOAWAY was received. `<ERROR_CODE>` is the RFC 9113 error code name, e.g. `GOAWAY NO_ERROR`, `GOAWAY PROTOCOL_ERROR`, `GOAWAY ENHANCE_YOUR_CALM`. |
| `subchannel shutdown` | The subchannel was shut down: for example, the channel shut down or went idle, the LB policy changed, or the endpoint's addresses changed. |
| `connection reset` | The connection was reset (e.g. `ECONNRESET`, `WSAECONNRESET`). |
| `connection timed out` | The connection timed out (e.g. `ETIMEDOUT`, `WSAETIMEDOUT`), including connections closed by keepalive timeout. |
| `connection aborted` | The connection was aborted (e.g. `ECONNABORTED`, `WSAECONNABORTED`). |
| `socket error` | Any other socket error, including socket errors whose code cannot be determined. |
| `unknown` | Any other reason. |

If several reasons are reported for one connection (for example, a GOAWAY
with `ENHANCE_YOUR_CALM` followed by a broken-pipe socket error), the
**first** reason seen MUST be used. More values may be added in the future.

## 5. Weighted Round Robin LB Policy Metrics

> **Experimental:** all metrics in this subsection (off by default).

> **Introduced by:** [gRFC A78: gRPC OTel Metrics for WRR, Pick First, and XdsClient](https://github.com/grpc/proposal/blob/master/A78-grpc-metrics-wrr-pf-xds.md)

These metrics are recorded by the `weighted_round_robin` policy (see
[weighted_round_robin](../04-client-channel/lb-policies/weighted_round_robin.md))
each time it updates its scheduler.

| Name | Type | Unit | Required labels | Optional labels | Description |
| --- | --- | --- | --- | --- | --- |
| `grpc.lb.wrr.rr_fallback` | Counter (int) | `{update}` | `grpc.target` | `grpc.lb.locality`, `grpc.lb.backend_service` | Number of scheduler updates in which too few endpoints had a valid weight, so the policy fell back to round-robin behavior. |
| `grpc.lb.wrr.endpoint_weight_not_yet_usable` | Counter (int) | `{endpoint}` | `grpc.target` | `grpc.lb.locality`, `grpc.lb.backend_service` | Number of endpoints in each scheduler update that do not yet have a usable weight: either no load report has been received, or the endpoint is still in its blackout period. |
| `grpc.lb.wrr.endpoint_weight_stale` | Counter (int) | `{endpoint}` | `grpc.target` | `grpc.lb.locality`, `grpc.lb.backend_service` | Number of endpoints in each scheduler update whose latest weight is older than the expiration period. |
| `grpc.lb.wrr.endpoint_weights` | Histogram (double) | `{weight}` | `grpc.target` | `grpc.lb.locality`, `grpc.lb.backend_service` | The weight of each endpoint, recorded on every scheduler update. Endpoints without a usable weight are recorded as 0. |

`grpc.lb.locality` is taken from the child-name attribute set by the
`weighted_target` parent, or the empty string if the attribute is unset.
`grpc.lb.backend_service` is taken from the backend-service attribute, or the
empty string if it is unset. The backend-service attribute is not specific to
xDS. In this specification, only the xDS `cds` policy sets it.

## 6. XdsClient Metrics

> **Experimental:** all metrics in this subsection (off by default).

> **Introduced by:** [gRFC A78: gRPC OTel Metrics for WRR, Pick First, and XdsClient](https://github.com/grpc/proposal/blob/master/A78-grpc-metrics-wrr-pf-xds.md)

These metrics are recorded by the XdsClient (see
[XdsClient](../09-xds/03-xds-client.md)). There is one XdsClient per channel
target (and one for servers), and it uses the stats plugins of the first
channel that created it.

| Name | Type | Unit | Required labels | Optional labels | Description |
| --- | --- | --- | --- | --- | --- |
| `grpc.xds_client.connected` | Gauge (int) | `{bool}` | `grpc.target`, `grpc.xds.server` | — | Whether the XdsClient currently has a working ADS stream to the xDS server. Set to 1 when the stream is first created. Set to 0 on a connectivity failure, or when the ADS stream fails without having received a response. Reset from 0 to 1 when the first response is received on an ADS stream. |
| `grpc.xds_client.server_failure` | Counter (int) | `{failure}` | `grpc.target`, `grpc.xds.server` | — | Number of times an xDS server went from healthy to unhealthy. A server becomes unhealthy on a connectivity failure, or when the ADS stream fails without having received a response. |
| `grpc.xds_client.resource_updates_valid` | Counter (int) | `{resource}` | `grpc.target`, `grpc.xds.server`, `grpc.xds.resource_type` | — | Number of resources received that were valid. Incremented even for resources that have not changed. |
| `grpc.xds_client.resource_updates_invalid` | Counter (int) | `{resource}` | `grpc.target`, `grpc.xds.server`, `grpc.xds.resource_type` | — | Number of resources received that were invalid (NACKed). |
| `grpc.xds_client.resources` | Gauge (int) | `{resource}` | `grpc.target`, `grpc.xds.authority`, `grpc.xds.cache_state`, `grpc.xds.resource_type` | — | Number of xDS resources in the cache, by cache state. |

`grpc.xds.cache_state` values. Each corresponds to an XdsClient cache entry
state (which also maps to the CSDS `ClientResourceStatus`; see
[CSDS](../09-xds/11-csds.md)):

| Value | Cache entry state | Meaning |
| --- | --- | --- |
| `requested` | REQUESTED | Subscribed, but the resource has not yet been received. |
| `does_not_exist` | DOES_NOT_EXIST, no cached resource | The resource does not exist: the resource timer fired (without the `resource_timer_is_transient_error` server feature), or an LDS or CDS resource was deleted. |
| `does_not_exist_but_cached` | DOES_NOT_EXIST, resource cached | An LDS or CDS deletion was seen but ignored. The previous resource is still cached. |
| `acked` | ACKED | The resource was received and is valid. |
| `nacked` | NACKED, no cached resource | The most recent version received was invalid, and no valid version is cached. |
| `nacked_but_cached` | NACKED, resource cached | The most recent update was invalid, but an earlier valid version is cached. |
| `received_error` | RECEIVED_ERROR, no cached resource | The control plane sent a per-resource error, and no resource is cached. |
| `received_error_but_cached` | RECEIVED_ERROR, resource cached | The control plane sent a per-resource error, which was ignored because `fail_on_data_errors` is not in effect. The previous resource is still cached. |
| `timeout` | TIMEOUT | The resource timer fired with the `resource_timer_is_transient_error` server feature present. No resource is cached. |

## 7. TLS Metrics

> **Experimental:** all metrics in this subsection (off by default).

> **Introduced by:** [gRFC A118: TLS Telemetry](https://github.com/grpc/proposal/blob/master/A118-tls-telemetry.md)

These metrics cover TLS handshakes only, whether TLS is configured directly or
through xDS (see [TLS credentials](../06-security/02-tls.md)). They are not
recorded for other handshakers. Handshake metrics are recorded once per
handshake, when it completes or fails.

| Name | Type | Unit | Required labels | Optional labels | Description |
| --- | --- | --- | --- | --- | --- |
| `grpc.client.tls.handshakes` | Counter (int) | `{handshake}` | `grpc.tls.handshake.result`, `grpc.target` | `grpc.tls.handshake.resumed`, `grpc.lb.locality`, `grpc.lb.backend_service` | Number of TLS handshakes performed on the client side. The result label gives the failure reason. |
| `grpc.server.tls.handshakes` | Counter (int) | `{handshake}` | `grpc.tls.handshake.result` | `grpc.tls.handshake.resumed` | Number of TLS handshakes performed on the server side. |
| `grpc.client.tls.offload_private_key_signing_duration` | Histogram (double), latency buckets | `s` | `grpc.status`, `grpc.target`, `grpc.tls.private_key.offloader_name` | `grpc.tls.private_key_algorithm`, `grpc.lb.locality`, `grpc.lb.backend_service` | Duration of an offloaded private key signing operation on the client. |
| `grpc.server.tls.offload_private_key_signing_duration` | Histogram (double), latency buckets | `s` | `grpc.status`, `grpc.tls.private_key.offloader_name` | `grpc.tls.private_key_algorithm` | Duration of an offloaded private key signing operation on the server. |
| `grpc.server.tls.offload_certificate_selection_duration` | Histogram (double), latency buckets | `s` | `grpc.status` | — | Duration of an offloaded certificate selection operation (server only). |


Private key offload covers signing only, because signing is the only private
key operation that gRPC offloads (see [TLS credentials](../06-security/02-tls.md)).

`grpc.tls.handshake.result` values. These strings MUST be used exactly as
listed. `UNKNOWN_FAILURE` is the catch-all for any failure that cannot be
classified more precisely.

| Group | Values |
| --- | --- |
| Success | `SUCCESS` |
| Catch-all | `UNKNOWN_FAILURE` |
| Peer certificate verification failures | `CERTIFICATE_VERIFICATION_FAILED`, `CERTIFICATE_REVOKED`, `CERTIFICATE_EXPIRED`, `CERTIFICATE_NOT_YET_VALID`, `CERTIFICATE_AUTHORITY_INVALID` |
| TLS negotiation mismatch failures | `CERTIFICATE_HOSTNAME_MISMATCH`, `CERTIFICATE_MALFORMED`, `CIPHER_SUITE_MISMATCH`, `PROTOCOL_VERSION_UNSUPPORTED`, `INAPPROPRIATE_FALLBACK`, `NO_APPLICATION_PROTOCOL` |
| Cryptographic failures | `SIGNATURE_VERIFICATION_FAILED`, `DECRYPTION_FAILED`, `KEY_EXCHANGE_FAILURE` |
| Other failures | `UNEXPECTED_MESSAGE`, `HANDSHAKE_TIMEOUT`, `PEER_CONNECTION_CLOSED` |

`grpc.tls.handshake.resumed` values: `FULL_HANDSHAKE` (no resumption) and
`RESUMED_HANDSHAKE` (session resumption of any kind). More specific values may
be added in the future.

## 8. RLS LB Policy Metrics

> **Experimental:** all metrics in this section (off by default).

These metrics are recorded by the [`rls`](../04-client-channel/lb-policies/rls.md)
policy. Label values are defined in
[`rls`: Metrics](../04-client-channel/lb-policies/rls.md#6-metrics).

| Name | Type | Unit | Required labels | Optional labels | Description |
| --- | --- | --- | --- | --- | --- |
| `grpc.lb.rls.cache_entries` | Gauge (int) | `{entry}` | `grpc.target`, `grpc.lb.rls.server_target`, `grpc.lb.rls.instance_uuid` | | Number of entries in the RLS cache. |
| `grpc.lb.rls.cache_size` | Gauge (int) | `By` | `grpc.target`, `grpc.lb.rls.server_target`, `grpc.lb.rls.instance_uuid` | | Estimated size of the RLS cache. |
| `grpc.lb.rls.default_target_picks` | Counter (int) | `{pick}` | `grpc.target`, `grpc.lb.rls.server_target`, `grpc.lb.rls.data_plane_target`, `grpc.lb.pick_result` | `grpc.client.call.custom` | Number of LB picks sent to the default target. |
| `grpc.lb.rls.target_picks` | Counter (int) | `{pick}` | `grpc.target`, `grpc.lb.rls.server_target`, `grpc.lb.rls.data_plane_target`, `grpc.lb.pick_result` | `grpc.client.call.custom` | Number of LB picks sent to each RLS target. |
| `grpc.lb.rls.failed_picks` | Counter (int) | `{pick}` | `grpc.target`, `grpc.lb.rls.server_target` | `grpc.client.call.custom` | Number of LB picks failed because the RLS request failed or was throttled. |

## 9. API Requirements

- The OpenTelemetry plugin MUST implement every per-call and retry metric in
  [Per-Call Metrics](#2-per-call-metrics) and [Retry Metrics](#3-retry-metrics), with the names, types, units, and labels given here.
- gRPC components MUST register the non-per-call metrics in [Subchannel Metrics](#4-subchannel-metrics) through
  [RLS LB Policy Metrics](#8-rls-lb-policy-metrics) in the instrument registry, with exactly the names, units, label keys,
  optional label keys, and default-enabled state given here.
- Applications MUST be able to enable each experimental metric and each
  optional label individually by name (see [Metrics Framework and OpenTelemetry Plugin](03-metrics-framework.md)).
