# C++ implementation bugs

Bugs in gRPC C++ (C-core) found while writing and reviewing the gRPC spec in this directory: **84** entries, ordered by severity. Other lists: [Go](bugs_go.md), [Java](bugs_java.md), [documentation](bugs_docs.md).

Severity:

- **critical:** crash, data corruption, or a security weakness
- **high:** interoperability failure, or wrong behavior that users commonly hit
- **medium:** spec non-conformance with limited impact
- **low:** cosmetic, or a rare edge case

Each bug lists the review item that identified it (an item ID such as `RLS-4`, an `R<n>` number from the original review list, or "incidental"/"audit"), a summary, a description, evidence (code locations), and the spec section it violates. Open questions are in [review_items.md](review_items.md). None of these bugs has been filed yet.

### [low] C++ xds_override_host does not reset the backoff of the subchannels it owns

- **Item:** XDS_LB-10
- **Summary:** `XdsOverrideHostLb::ResetBackoffLocked()` only forwards to the child policy. The subchannels the policy itself owns (kept for session affinity) stay in backoff.
- **Description:** The spec says ResetBackoff resets the backoff of every subchannel the `xds_override_host` policy owns and forwards the request to the child. C++ forwards to the child only. Subchannels that the policy created or keeps for override-host (stateful session affinity) addresses that the child does not use therefore keep their backoff timers after the application asks for a reset, and session traffic to those hosts can keep failing or waiting until backoff expires.
- **Evidence:** grpc 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81: [xds_override_host.cc L650-L652](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_override_host.cc#L650-L652)
- **Spec:** `xds_override_host` LB Policy: ResetBackoff

### [low] C++ try_to_connect does not start or restart the channel idle timer

- **Item:** IDLE-1
- **Summary:** A C++ channel woken only by `try_to_connect`, with no RPCs, never starts its idle timer, so it holds connections until an RPC starts and completes.
- **Description:** The spec says a `try_to_connect` request counts as activity and restarts the idle timer, both when the channel leaves channel-level IDLE and when the LB policy reports IDLE. In C++, `CheckConnectivityState(true)` calls `TryToConnectLocked()`, which creates the resolver or calls `ExitIdleLocked()` on the LB policy and never touches the idle timer. The timer starts only when the call count drops to zero, in the server-trailing-metadata callback. If the application calls `try_to_connect` and sends no RPCs, the channel never returns to IDLE, which defeats the idle timeout.
- **Evidence:** grpc 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81: [client_channel.cc L692-L708](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L692-L708) (`CheckConnectivityState`), [client_channel.cc L1050-L1058](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L1050-L1058) (`TryToConnectLocked`), [client_channel.cc L1375-L1377](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L1375-L1377) (timer started only on call-count drop)
- **Spec:** Channel: Idle Timeout; Channel: API Requirements

### [low] C++: RLS child picker and status not updated after TRANSIENT_FAILURE

- **Item:** RLS-11
- **Summary:** After an RLS child reports TRANSIENT_FAILURE, C++ drops every update except READY, so the child's new pickers and failure statuses are never used.
- **Description:** The spec keeps the child's recorded state at TRANSIENT_FAILURE until it reports READY, but records every new picker so that picks delegated to the child use its latest picker and status. `ChildPolicyHelper::UpdateState` returns early when the stored state is TRANSIENT_FAILURE and the new state isn't READY, so it skips both the state and the picker. A later TRANSIENT_FAILURE with a different status is ignored (a TODO in the code says so).
- **Evidence:** [rls.cc L864-L890](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L864-L890) (`RlsLb::ChildPolicyWrapper::ChildPolicyHelper::UpdateState`)
- **Spec:** `rls` LB Policy: Calls From Children

### [low] C++: RLS minimum eviction time not reset on successful lookup

- **Item:** RLS-9
- **Summary:** C++ sets an RLS cache entry's minimum eviction time only when it creates the entry, not on each successful lookup.
- **Description:** The spec sets the minimum eviction time to entry creation or last success + 5 seconds. The guard keeps a fresh response in the cache long enough to process the picks that were queued for it, and that applies to every response. `Cache::Entry` sets `min_expiration_time_` in its constructor only, and the success path of `OnRlsResponseLocked` doesn't update it. So an LRU sweep can evict an entry right after a refresh.
- **Evidence:** [rls.cc L1128](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L1128) (constructor), [rls.cc L1250-L1258](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L1250-L1258) (success path)
- **Spec:** `rls` LB Policy: Cache

### [low] C++: outlier detection success-rate algorithm re-ejects ejected endpoints

- **Item:** OUTLIER_DETECTION-1
- **Summary:** C++'s success-rate loop doesn't skip already-ejected endpoints (the failure-percentage loop does), and ejected endpoints still count as candidates and in the statistics.
- **Description:** The spec excludes already-ejected endpoints from the candidates. In C++, an endpoint ejected in an earlier sweep that still has volume can be ejected again by the success-rate algorithm, which resets its timestamp and increments its multiplier. Ejected endpoints are also counted in the mean/stdev and `minimum_hosts` for both algorithms.
- **Evidence:** [outlier_detection.cc L917-L940](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L917-L940) (candidates), [L975-L1003](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L975-L1003) (success-rate loop), [L1035-L1037](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L1035-L1037) (FP skip)
- **Spec:** `outlier_detection` LB Policy: Ejection Timer

### [low] C++ server dispatches requests with a missing or non-gRPC content-type

- **Item:** HTTP2-2
- **Summary:** C++ servers never check the request `content-type`, so they dispatch requests that Java and Go reject with HTTP 415.
- **Description:** `ContentTypeMetadata::ParseMemento` maps any unrecognized value to `kInvalid` and on purpose does not report an error ("to avoid breaking anyone"). `HttpServerFilter` then just removes the header (`md.Remove(ContentTypeMetadata())`), and the call goes to the handler. The spec says the server SHOULD respond with HTTP 415 and MUST NOT dispatch the RPC. Java and Go both respond with 415 and don't dispatch.
- **Evidence:** [http_server_filter.cc#L112](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/server/http_server_filter.cc#L112), [metadata_batch.cc#L132-L150](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/metadata_batch.cc#L132-L150)
- **Spec:** gRPC over HTTP/2: `content-type`; Server Behavior: Request Validation

### [low] C++ DNS service config choices: unknown keys ignored, percentage not range-checked

- **Item:** DNS-2
- **Summary:** The C++ DNS resolver accepts a TXT service config choice that has an unknown key or a `percentage` outside 0–100. gRFC A2 says that makes the whole config invalid.
- **Description:** `ServiceConfigChoice`'s `JsonObjectLoader` ignores unknown keys, and `ChooseServiceConfig` never range-checks `percentage`. So a misspelled criterion (for example `clientHostName` typed as `clienthostname`) is dropped quietly, and the choice then matches every client.
- **Evidence:** [service_config_helper.cc#L44-L50](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/dns/service_config_helper.cc#L44-L50), [service_config_helper.cc#L83-L85](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/dns/service_config_helper.cc#L83-L85)
- **Spec:** Name Resolution: Service Config in DNS › Service Config Choices

### [medium] C++ ring_hash does not validate requestHashHeader

- **Item:** RING_HASH-5
- **Summary:** C++ accepts any `requestHashHeader` string. A `-bin` name or an invalid name is not rejected, and a name with uppercase letters never matches, so every call gets a random hash.
- **Description:** `RingHashLbConfig::JsonPostLoad` validates only the ring sizes. The picker looks up the configured name in the metadata exactly as written. gRFC A76 requires rejecting the config if the name is not a valid header name or ends in `-bin`.
- **Evidence:** [ring_hash.cc#L113-L143](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L113-L143), [ring_hash.cc#L318-L328](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L318-L328)
- **Spec:** `ring_hash` LB Policy: Configuration

### [low] C++ client sends no immediate keepalive PING when a stream starts on a long-idle connection

- **Item:** TRANSPORT-2
- **Summary:** If the keepalive timer fires while there are no streams and `KEEPALIVE_WITHOUT_CALLS` is false, C++ just re-arms the timer. A new stream doesn't trigger an overdue ping, so finding a dead connection can take up to `KEEPALIVE_TIME + KEEPALIVE_TIMEOUT` instead of `KEEPALIVE_TIMEOUT`.
- **Description:** In `init_keepalive_ping_locked`, the no-streams branch reschedules for `keepalive_time`. Nothing on stream creation checks keepalive state. gRFC A8 says a keepalive PING should be sent when a stream is created and more than the keepalive time has passed since the last read. Java and Go do this.
- **Evidence:** [chttp2_transport.cc#L3298-L3313](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L3298-L3313)
- **Spec:** HTTP/2 Transport: Keepalive

### [medium] C++ server keepalive does not ping idle connections by default

- **Item:** TRANSPORT-3
- **Summary:** By default, C++ servers send keepalive PINGs only while the connection has active streams.
- **Description:** `g_default_server_keepalive_permit_without_calls` is `false`, and the keepalive timer pings only if `keepalive_permit_without_calls || !stream_map.empty()`; otherwise it re-arms. gRFC A9 says server keepalives take place whether or not there are outstanding RPCs, and Java and Go do this. With the default, a C++ server never detects a dead idle client and keeps half-open connections until TCP gives up. Setting `GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS=1` on the server gives the A9 behavior. When fixed, update the server default in doc/keepalive.md.
- **Evidence:** [chttp2_transport.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L155-L156), [chttp2_transport.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L3298-L3313)
- **Spec:** HTTP/2 Server Transport: Keepalive

### [low] C++ outlier_detection accepts an interval of 0 and busy-loops

- **Item:** OUTLIER_DETECTION-4
- **Summary:** An `interval` of 0 (service config or xDS `OutlierDetection.interval`) is accepted. The policy then re-arms its ejection timer with zero delay after every sweep.
- **Description:** The spec now makes `interval` 0 invalid: the LB config is rejected, and the xDS Cluster resource is NACKed. C++ accepts it, and each sweep schedules the next one with no delay, which busy-loops on the work serializer.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L881-L894, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L1092-L1093
- **Spec:** `outlier_detection` LB Policy: 2.2 Validation; Cluster: 4. Outlier Detection

### [low] RLS: keys with no cached data never back off exponentially

- **Item:** RLS-8 (incidental)
- **Summary:** C++ passes an entry's backoff state to the next lookup only when the entry still has unexpired data; otherwise it creates a fresh backoff state, so a key with no valid data waits the initial ~1 s after every failure.
- **Description:** The spec's `rls` Backoff section and picker pseudocode carry the entry's backoff state into the lookup started after a backoff period (`backoff_state = e?.backoff_state`), so consecutive failures back off exponentially (also the RLS design doc). C++ only does this when the entry has data, so a failing key with no data retries at the initial delay indefinitely.
- **Evidence:** grpc `src/core/load_balancing/rls/rls.cc` picker (~L1000-1003, L1616-1624) and `OnRlsResponseLocked` (~L1234-1241), at 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81.
- **Spec:** rls: Backoff

### [low] C++: retryableStatusCodes rejects integer status codes

- **Item:** SERVICE_CONFIG-5
- **Summary:** C++ rejects integer status codes (for example `14`) in `retryableStatusCodes`, making the whole service config invalid.
- **Description:** The spec accepts a status code as an integer or as the exact upper-case name (the proto3 JSON enum mapping). C++ loads `retryableStatusCodes` as `std::vector<std::string>`, so an integer element fails with "is not a string" and the service config is rejected. Upper-case names are matched correctly.
- **Evidence:** [retry_service_config.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_service_config.cc#L169-L183), [status_util.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/status_util.cc#L54-L63)
- **Spec:** Retries and Hedging: Fields and Validation; Service Config: Format

### [low] C++: method config with both retryPolicy and hedgingPolicy is accepted

- **Item:** SERVICE_CONFIG-7
- **Summary:** C++ ignores `hedgingPolicy` as an unknown field, so a method config with both policies is accepted and the retry policy is used.
- **Description:** The spec says a method config entry with both `retryPolicy` and `hedgingPolicy` makes the service config invalid. C++ does not implement hedging and does not recognize the field. The fix is to recognize `hedgingPolicy` just enough to reject the combination (hedging itself remains unimplemented).
- **Evidence:** [retry_service_config.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_service_config.cc) (parses only `retryPolicy`)
- **Spec:** Service Config: `methodConfig`

### [low] C++: graceful switch ignores the current policy's state

- **Item:** LB-4
- **Summary:** C++ swaps to the pending LB policy only when it reports a state other than CONNECTING; it never swaps immediately when the current policy is not READY, nor when the current policy leaves READY.
- **Description:** The spec replaces the old policy immediately if the channel is not READY, and otherwise when the new policy leaves CONNECTING or the old policy leaves READY. `ChildPolicyHandler::Helper::UpdateState` never looks at the current child's state, so a failing old policy keeps serving picks until the new one finishes connecting.
- **Evidence:** [child_policy_handler.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/child_policy_handler.cc#L75)
- **Spec:** Load Balancing: Gracefully Switching LB Policies

### [low] C++: chttp2 queues streams beyond MAX_CONCURRENT_STREAMS despite subchannel connection scaling

- **Item:** TRANSPORT-8
- **Summary:** chttp2 queues streams that exceed MAX_CONCURRENT_STREAMS by default, even though C++ subchannels do connection scaling and queue RPCs themselves; the opt-in rejection uses `RESOURCE_EXHAUSTED`, not `UNAVAILABLE`.
- **Description:** With connection scaling, the spec says the transport SHOULD NOT queue RPCs and SHOULD fail an RPC with no stream quota with `UNAVAILABLE` in a way eligible for transparent retry. By default chttp2 puts the stream on `waiting_for_concurrency`. Only with the non-default `GRPC_ARG_MAX_CONCURRENT_STREAMS_REJECT_ON_CLIENT` does it fail the stream, and then with `RESOURCE_EXHAUSTED` (marked `kNotSentOnWire`).
- **Evidence:** [chttp2_transport.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L1645-L1657), default at [L561-L563](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L561-L563)
- **Spec:** HTTP/2 Client Transport: RPCs Beyond the Limit

### [low] C++: failed token prefetch is never retried before the token expires

- **Item:** CALL_CREDS-2
- **Summary:** After a prefetch fails while the cached token is valid, C++ never prefetches again; the next fetch happens only after the token expires, so attempts block on it.
- **Description:** The spec says a new fetch can start once the backoff timer expires. `TokenFetcherCredentials::GetRequestMetadata` starts a fetch only when `fetch_state_ == nullptr`; after a failure the `FetchState` stays in place holding the backoff timer, and after backoff a new fetch starts only from `QueueCall`, which runs only when there is no valid token. This brings back the latency spike prefetching is meant to avoid.
- **Evidence:** [token_fetcher_credentials.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/call/token_fetcher/token_fetcher_credentials.cc#L243-L272), [QueueCall](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/call/token_fetcher/token_fetcher_credentials.cc#L199-L212)
- **Spec:** Call Credentials: Algorithm

### [low] C++: connection-scaling channelz fields not populated

- **Item:** CHANNELZ-4
- **Summary:** C++ does not set `SocketData.received_goaway_error`, `SocketData.peer_max_concurrent_streams`, or `ChannelData.max_connections_per_subchannel`, although it implements connection scaling.
- **Description:** The spec says `received_goaway_error` is set if and only if a GOAWAY was received, `peer_max_concurrent_streams` is populated on clients, and `max_connections_per_subchannel` is set for subchannels. C++ computes `max_connections_per_subchannel` in the subchannel but neither the channelz nodes nor `src/core/channelz/v2tov1` set any of the three fields.
- **Evidence:** [subchannel.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/subchannel.cc#L968-L974); no references under `src/core/channelz/`
- **Spec:** Channelz: `SocketData`; Channelz: Channel and Subchannel Data

### [low] C++: received out-of-range ASCII metadata values are accepted, but echoing them fails the call

- **Item:** METADATA-2
- **Summary:** An ASCII metadata value with bytes outside 0x20–0x7E is accepted on receipt but rejected when the application sends it back.
- **Description:** In the default configuration the HPACK parser does not check received ASCII values (the check is gated by the `optimization_05` experiment). `ValidateMetadata` then rejects the same value on `send_initial_metadata` with `GRPC_CALL_ERROR_INVALID_METADATA`. Proxies and servers that forward incoming metadata can therefore fail RPCs because a non-gRPC peer set such a header. Fix: discard such values on receipt (allowed by the spec), or allow them on send.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/hpack_parser.cc#L1014-L1022, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/surface/call_utils.cc#L193-L212, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/surface/validate_metadata.cc#L44-L52
- **Spec:** 2. Core RPC Semantics: 7.2 Values

### [medium] C++: server compresses with an algorithm the client did not list in grpc-accept-encoding

- **Item:** COMPRESSION-3
- **Summary:** The server uses the handler's or server default algorithm without checking the client's `grpc-accept-encoding`.
- **Description:** `HandleOutgoingMetadata` uses `grpc-internal-encoding-request` (from `ServerContext::set_compression_algorithm`) or the default algorithm and sets `grpc-encoding` without consulting the peer's accepted encodings. Only the compression-level path picks from `encodings_accepted_by_peer`. A C++ server with a default of gzip makes every response fail with `INTERNAL` on a client that lacks gzip. Fix: send the message uncompressed when the client did not list the algorithm.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/message_compress/compression_filter.cc#L216-L227, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/server_context.cc#L509-L519, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/surface/call.cc#L300-L309
- **Spec:** 2. Core RPC Semantics: 13.2 Negotiation; gRPC over HTTP/2 (compression error handling)

### [low] C++: ipv4:/ipv6: targets without a port are rejected instead of defaulting to 443

- **Item:** NAME_RESOLUTION-1
- **Summary:** `ipv4:10.0.0.1` is an invalid target; the port should default to 443.
- **Description:** `grpc_parse_ipv4_hostport` and `grpc_parse_ipv6_hostport` fail with "no port given for ipv4 scheme" / "...ipv6 scheme". The documented syntax is `address[:port]` with a default of 443, matching the `dns` scheme.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/address_utils/parse_address.cc#L234-L237, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/address_utils/parse_address.cc#L323-L326
- **Spec:** Name Resolution: 7.6 `ipv4` and `ipv6`

### [low] C++: method config cannot raise the receive message size limit above the 4 MiB default

- **Item:** SERVICE_CONFIG-6
- **Summary:** The channel receive limit always has a value (4 MiB if the application set none), so a method config `maxResponseMessageBytes` above 4 MiB has no effect.
- **Description:** The built-in default is treated as a channel value and combined by minimum with the method config. Per the spec and service_config.proto, the built-in default applies only if neither the application nor the method config set a limit; if only the method config sets one, it applies.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/transport/message_size_service_config.cc#L55-L59, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/message_size/message_size_filter.cc#L81-L105
- **Spec:** Service Config: 5.4 `methodConfig`; 2. Core RPC Semantics: 12 Message Size Limits

### [low] C++: loadBalancingPolicy validated even when loadBalancingConfig is set

- **Item:** SERVICE_CONFIG-8
- **Summary:** A stale unknown `loadBalancingPolicy` invalidates a service config that has a valid `loadBalancingConfig`.
- **Description:** `JsonPostLoad` lower-cases and checks the deprecated field (unregistered or config-requiring policy → error) regardless of whether `loadBalancingConfig` is present. The spec says the field is ignored when `loadBalancingConfig` is set.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_service_config.cc#L104-L119
- **Spec:** Service Config: 5.3 `loadBalancingPolicy` (deprecated)

### [medium] C++: client KEEPALIVE_TIME below 10 seconds is not raised to 10 seconds

- **Item:** TRANSPORT-1
- **Summary:** C++ accepts any client `GRPC_ARG_KEEPALIVE_TIME_MS` of 1 ms or more, so a misconfigured client can ping very often and be disconnected with `too_many_pings`.
- **Description:** gRFC A8 and the spec require client `KEEPALIVE_TIME` values below 10 seconds to be raised to 10 seconds. C++ clamps only to at least 1 ms, both in the chttp2 transport and in the client channel's initial value. Java and Go raise the value to 10 s.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L441-L445 ; https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L664-L667
- **Spec:** HTTP/2 Client Transport: Keepalive

### [low] C++: retryThrottling maxTokens above 1000 is accepted

- **Item:** RETRY-5
- **Summary:** C++ loads `maxTokens` as `uint32` and rejects only 0, so values such as 5000 are accepted.
- **Description:** gRFC A6 and the spec require `maxTokens` to be a JSON integer in (0, 1000]; a config outside the range is invalid. C++ rejects only 0.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_service_config.cc#L54-L111
- **Spec:** Retries and Hedging: Retry Throttling

### [low] C++: no channel arg for the client-side maxAttempts limit

- **Item:** RETRY-6
- **Summary:** C++ hard-codes the client-side `maxAttempts` cap at 5 (`MAX_MAX_RETRY_ATTEMPTS`) with no channel arg to change it.
- **Description:** gRFC A6: "This client-side maximum value can be changed by the client through the use of channel arguments." The spec requires a channel option. Java (`maxRetryAttempts`, `maxHedgedAttempts`) and Go (`WithMaxCallAttempts`) provide one; C++ has none in `channel_arg_names.h`.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_service_config.cc#L38-L39 ; https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_service_config.cc#L139-L145
- **Spec:** Retries and Hedging: API Requirements

### [low] C++: MAX_CONNECTION_IDLE sends GOAWAY(INTERNAL_ERROR, "connection idle") and closes immediately instead of a graceful max_idle GOAWAY

- **Item:** TRANSPORT-4
- **Summary:** C++ treats max-idle as a forced disconnect: one GOAWAY with `INTERNAL_ERROR` and debug data `connection idle`, then an immediate close; `max_idle` is never sent.
- **Description:** gRFC A9: "the server should send GOAWAY with status code NO_ERROR and ASCII debug data `max_idle` and then continue the graceful connection termination". C++'s idle timer calls `CloseChannel("connection idle")`, a `disconnect_with_error` op; chttp2 sends a final GOAWAY with `immediate_disconnect_hint` and closes the transport. The error has no HTTP/2 code and status UNKNOWN, so the GOAWAY code is `INTERNAL_ERROR`. A non-`NO_ERROR` GOAWAY looks like an error in client logs and metrics; a stream racing the GOAWAY is refused rather than drained (still transparently retried). Java and Go send a two-phase `NO_ERROR` / `max_idle` GOAWAY.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/channel_idle/legacy_channel_idle_filter.cc#L277-L292 ; https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L2209-L2233 ; https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/transport/error_utils.cc#L67-L80
- **Spec:** HTTP/2 Server Transport: Connection Management

### [low] RLS backoff reset keeps the entry's backoff sequence

- **Item:** RLS-8
- **Summary:** On control-channel recovery and on `ResetBackoff`, C++ `Cache::Entry::ResetBackoff` clears the backoff time and timer but keeps `backoff_state_`, so a following failed refresh of an entry that still has data continues the exponential sequence instead of starting at the initial delay.
- **Description:** The spec (matching the RLS design doc) resets the entry's backoff state as well, so that lookups that failed only because the RLS server was unreachable are not penalized after recovery. In C++ the kept state is used only when the picker passes the entry's backoff state with the lookup, which happens only when the entry still has unexpired data; keys without valid data already restart at the initial delay. So the effect is limited to failed refreshes of entries with valid data.
- **Evidence:** src/core/load_balancing/rls/rls.cc (Cache::Entry::ResetBackoff; RlsLb::ResetBackoffLocked; control-channel state watcher; picker passing TakeBackoffState only for entries with unexpired data; OnRlsResponseLocked).
- **Spec:** `rls` LB Policy: Control Channel; `rls` LB Policy: ResetBackoff

### [low] A113 weighted shuffling and cds weight normalization not enabled by default

- **Item:** PICK_FIRST-1
- **Summary:** C++ implements gRFC A113 (weighted `pick_first` shuffle and normalized `cds` endpoint weights) but gates both behind `GRPC_EXPERIMENTAL_PF_WEIGHTED_SHUFFLING`, which defaults to false. By default it does a uniform shuffle and computes the raw `locality weight × endpoint weight` product.
- **Description:** The spec requires the weighted random sort (`u^(1/weight)`, descending) when `shuffleAddressList` is true, and the `cds` endpoint weight to be the product of normalized locality and endpoint weights in UQ1.31. Java and Go enable both by default. With C++'s default, a uniform shuffle ignores control-plane weights, and the raw product (uint32 × uint32) wraps mod 2^32 and is then stored in an `int` channel arg, so large weights can become small or negative; this also affects `ring_hash` weights. Supersedes the C++ XDS_LB-1 bug "Endpoint weight product wraps and is stored as int". Fix: enable the flag by default (and remove it).
- **Evidence:** src/core/load_balancing/pick_first/pick_first.cc (weighted vs. absl::c_shuffle; PfWeightedShufflingEnabled); src/core/load_balancing/xds/cds.cc (endpoint weight computation); src/core/config/experiment_env_var.cc / experiment_env_var.h (default false).
- **Spec:** `pick_first` LB Policy: Address List Processing; `cds` LB Policy: Endpoint Weight

### [medium] C++: stdout_logger audit lines are not JSON-escaped

- **Item:** AUTHZ-7
- **Summary:** C++ builds the stdout audit log line with a printf format string, so client-controlled values (such as `:path`) containing `"` produce invalid JSON or forged fields such as `"authorized":true`.
- **Description:** `kLogFormat` is `{"grpc_audit_log":{"timestamp":"%s","rpc_method":"%s",...}}` filled by `absl::FPrintF` with the raw method, principal, policy name and rule name. HTTP/2 allows `"` in `:path`, and authorization runs for unknown methods too, so a client can inject content into a security audit record. Go uses `json.Marshal`.
- **Evidence:** [stdout_logger.cc L38-L49](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/stdout_logger.cc#L38-L49)
- **Spec:** Authorization: Built-in `stdout_logger`

### [low] C++: OpenTelemetry delay event names have a trailing period

- **Item:** TRACING-4
- **Summary:** C++ records `Delayed name resolution complete.` and `Delayed LB pick complete.` (with a period), so they do not match the A72 names used by Java and Go.
- **Description:** The annotations are turned into OTel span events by the tracer. Event names are meant for exact matching across languages.
- **Evidence:** [client_channel_filter.cc L1897](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_filter.cc#L1897), [L2434](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_filter.cc#L2434), [client_channel.cc L997](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L997), [load_balanced_call_destination.cc L246](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/load_balanced_call_destination.cc#L246)
- **Spec:** Tracing: Client Call Span; Tracing: Client Attempt Span

### [medium] Legacy Cluster lb_policy LEAST_REQUEST is rejected

- **Item:** XDS_CDS-2
- **Summary:** C++ rejects a Cluster whose legacy `lb_policy` is `LEAST_REQUEST` ("LB policy is not supported").
- **Description:** The spec (per A48/A52) accepts legacy `LEAST_REQUEST` (reading `least_request_lb_config`) and converts it to `xds_wrr_locality_experimental` wrapping `least_request_experimental`. C++ handles only ROUND_ROBIN and RING_HASH in the legacy path and NACKs everything else, so the same Cluster that Java and Go accept is NACKed.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L332-L397
- **Spec:** Cluster: Legacy `lb_policy`

### [low] xDS retry base_interval of 0 not NACKed; max_interval < base_interval and the 1ms floor not handled

- **Item:** XDS_ROUTING-8
- **Summary:** C++ does not check `base_interval > 0` or `max_interval >= base_interval` when parsing RetryPolicy, and does not raise sub-millisecond values to 1ms.
- **Description:** The spec (per A44) requires `base_interval` > 0, `max_interval` ≥ `base_interval`, treats values below 1ms as 1ms, and rejects the resource on violations. C++ accepts a zero `base_interval`; the generated method config then fails `initialBackoff` validation and the resolver reports a channel error instead of NACKing. `max_interval < base_interval` is accepted and sub-millisecond values are passed through.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_route_config_parser.cc#L374-L413, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_service_config.cc#L148-L161, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_resolver.cc#L582-L583
- **Spec:** RouteConfiguration: Retry Policy

### [high] Aggregate cluster leaf list omits clusters already visited from another root cluster

- **Item:** XDS_DEPMGR-2
- **Summary:** C++ XdsDependencyManager uses one visited set for all root clusters, so a cluster already in the XdsConfig cluster map adds nothing to a later aggregate's leaf list.
- **Description:** With roots `a` (EDS) and `b` (aggregate `[a, c]`), `b`'s leaf list is `[c]`, so `b`'s primary cluster is lost. If `b` is `[a]` alone, `b` gets "aggregate cluster dependency graph for b has no leaf clusters" and its RPCs fail. The same thing happens when two aggregates share a leaf or a nested aggregate. gRFC A37 expects a cluster that is used directly and through an aggregate to stay in the aggregate's list. Java and Go include it.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_dependency_manager.cc#L675-L677, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_dependency_manager.cc#L905-L908 (`PopulateClusterConfigMap`: emplace fails → return true with no leaves appended)
- **Spec:** Client Data Plane: Aggregate cluster graph

### [low] Fault injection with grpc_status OK or http_status 200 does not abort

- **Item:** XDS_FAULT-3
- **Summary:** C++ `ParseTopLevelConfig` treats `grpc_status` 0 as unset and explicitly skips `http_status` 200, so `abort_code` stays OK and the filter never aborts.
- **Description:** gRFC A33: `http_status` 200 → abort with UNKNOWN; `grpc_status` OK → act as if an OK trailer arrived immediately. Java and Go follow A33.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_fault_filter.cc#L115-L132, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/fault_injection/fault_injection_filter.cc#L265-L287
- **Spec:** xDS HTTP Filters: `OK` and HTTP 200 Aborts

### [low] Header-controlled abort ignores x-envoy-fault-abort-request and uses wrong percentage header name

- **Item:** XDS_FAULT-1
- **Summary:** When `header_abort` is set, C++ reads only `x-envoy-fault-abort-grpc-request`, and reads the percentage from `x-envoy-fault-abort-percentage` instead of A33's `x-envoy-fault-abort-request-percentage`.
- **Description:** gRFC A33 lists `x-envoy-fault-abort-request` (HTTP status) and `x-envoy-fault-abort-request-percentage`. C++ never honors the HTTP abort header, and it ignores the A33 percentage header while reading a header name that is not in A33.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_fault_filter.cc#L133-L138
- **Spec:** xDS HTTP Filters: Header-Controlled Faults

### [low] CSDS does not reject requests with non-empty node_matchers

- **Item:** CSDS-2
- **Summary:** C++ `ClientStatusDiscoveryService::FetchClientStatus` and `StreamClientStatus` never look at the request, so a request with `node_matchers` gets a normal response.
- **Description:** gRFC A40 returns INVALID_ARGUMENT for a non-empty node matcher, to preserve forward compatibility. Java and Go do this.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/csds/csds.cc#L54-L88
- **Spec:** Client Status Discovery Service (CSDS): Request Handling

### [low] RLS accepts negative durations

- **Item:** RLS-1
- **Summary:** Negative `lookupServiceTimeout`, `maxAge`, and `staleAge` values are accepted instead of making the RLS config invalid.
- **Description:** `LoadDuration` parses a signed seconds value, and `RouteLookupConfig::JsonPostLoad` has no sign check. A negative `maxAge` makes every response expire right away, so every pick triggers a lookup. A negative `lookupServiceTimeout` gives every lookup an already-expired deadline. The spec says negative durations make the config invalid. (The existing C++ bug "RLS config validation differs from the spec" covers explicit zero values, not negative ones.)
- **Evidence:** grpc `src/core/util/json/json_object_loader.cc` `LoadDuration::LoadInto`; `src/core/load_balancing/rls/rls.cc` `RlsLbConfig::RouteLookupConfig::JsonLoader` / `JsonPostLoad`.
- **Spec:** `rls` LB Policy: Configuration; Validation

### [low] RLS accepts -bin header names in key builders

- **Item:** RLS-3
- **Summary:** A `NameMatcher` header name ending in `-bin` is accepted. The spec makes such a config invalid.
- **Description:** `NameMatcher::JsonPostLoad` checks only that names are non-empty. At pick time, the binary header's value is looked up and used as a key value. The spec says a key builder header name ending in `-bin` makes the config invalid.
- **Evidence:** grpc `src/core/load_balancing/rls/rls.cc` `GrpcKeyBuilder::NameMatcher::JsonPostLoad`; `BuildKeyMap` (`initial_metadata->Lookup(header_name, ...)`).
- **Spec:** `rls` LB Policy: Configuration; Validation

### [low] C++ excludes time before transparent retries from grpc.client.call.retry_delay

- **Item:** METRICS-3
- **Summary:** C++ does not count the no-active-attempt time preceding a transparent retry in `grpc.client.call.retry_delay`.
- **Description:** The spec defines `grpc.client.call.retry_delay` as the total time during the call with no active attempt, including time before a transparent retry. C++ only accumulates delay before non-transparent retries. (C++'s gating — recording only when a non-transparent retry occurred — conforms.)
- **Evidence:** grpc `src/cpp/ext/otel/otel_client_call_tracer.cc` (retry-delay accumulation in attempt creation / `RecordEnd`)
- **Spec:** Metric Catalog: Retry Metrics

### [medium] C++ subchannel metrics use the default authority for grpc.target

- **Item:** METRICS-4
- **Summary:** C++ labels subchannel metrics with the channel's default authority (e.g. `host:443`) instead of the canonical target URI.
- **Description:** The spec requires `grpc.target` on `grpc.subchannel.*` metrics to be the creating channel's canonical target URI, matching per-call metrics. C++ uses `GRPC_ARG_DEFAULT_AUTHORITY`. Fixing this needs care with the global subchannel pool: sharing already requires equal subchannel args, so the canonical target would need to be part of the key (or otherwise carried) to keep the "creating channel's target" rule.
- **Evidence:** grpc `src/core/client_channel/subchannel.cc` (metric labels from `GRPC_ARG_DEFAULT_AUTHORITY`)
- **Spec:** Metric Catalog: Subchannel Metrics

### [low] xDS bootstrap validates unused channel_creds entries

- **Item:** XDS_BOOTSTRAP-2
- **Summary:** C++ rejects a bootstrap whose `channel_creds` has an invalid config in a supported entry after the first supported one.
- **Description:** gRPC uses only the first `channel_creds` entry whose type it supports, and only that entry's config is validated. Entries after it are never used and are not validated. C++ validates every supported entry, so a malformed later entry makes the whole bootstrap invalid. Java and Go stop at the first supported entry.
- **Evidence:** src/core/xds/grpc/xds_server_grpc.cc `ParseXdsBootstrapChannelCreds`
- **Spec:** xDS Bootstrap: XdsServer Object

### [medium] StringMatcher with safe_regex and ignore_case=true is rejected

- **Item:** XDS_ROUTING-2
- **Summary:** C++ NACKs any resource that has a `StringMatcher` with `safe_regex` and `ignore_case: true`. The spec (and gRFC A63) says `ignore_case` is ignored for regex matches.
- **Description:** `ignore_case` applies only to `exact`, `prefix`, `suffix`, and `contains`, and has no effect on `safe_regex`. C++ rejects the combination with "not supported for regex matcher", so it NACKs route configs (header matchers) and RBAC policies that Java and Go accept. Note: Envoy also rejects this combination, despite its proto comment.
- **Evidence:** src/core/xds/grpc/xds_common_types_parser.cc (StringMatcher parsing)
- **Spec:** xDS Common Types: `StringMatcher`

### [critical] weighted_target crashes on a zero weight

- **Item:** R27
- **Summary:** A target weight of 0 passes config parsing and then hits `GRPC_CHECK_GT(weight, 0)` when a picker is built, crashing the process.
- **Description:** C++ requires the `weight` field but accepts 0 when parsing. When a READY or TRANSIENT_FAILURE child with weight 0 goes into a picker, an assertion fires and the process crashes. The spec says a missing or zero weight makes the config invalid, so the config should be rejected at parse time. A bad control-plane config can therefore crash clients.
- **Evidence:** `src/core/load_balancing/weighted_target/weighted_target.cc` config JsonPostLoad (no > 0 check) and picker construction (`GRPC_CHECK_GT`).
- **Spec:** 04-client-channel/lb-policies/weighted_target.md, Configuration

### [critical] Process crashes when an outgoing message fails to serialize

- **Item:** R113
- **Summary:** Send-side serialization failure triggers `ABSL_CHECK` and aborts the process instead of failing the call with `INTERNAL`.
- **Description:** In most send paths, C++ asserts that serialization succeeded. A message that fails to serialize (for example, a custom `SerializationTraits` returning an error, or a protobuf that fails to serialize) crashes the whole process. Only the async server `Finish` path reports `INTERNAL`. The spec requires the sender to fail just the call with `INTERNAL`. One bad message can take down a server or client process.
- **Evidence:** `include/grpcpp/impl/call_op_set.h` (`CallOpSendMessage::AddOp`: `ABSL_CHECK(serializer_(msg_).ok())`); `include/grpcpp/support/async_stream.h` (several `Write` methods: `ABSL_CHECK(write_ops_.SendMessage(...).ok())` with `// TODO(ctiller): don't assert`); findings/G1.md row 12.
- **Spec:** 02-rpc-semantics.md, "Codecs and Content-Subtype"

### [critical] Possible abort when a referenced cluster specifier plugin is removed

- **Also identified by:** XDS_ROUTING-4 resolution
- **Item:** R133
- **Summary:** `XdsResolver::CreateServiceConfig` reads `current_config_->route_config->cluster_specifier_plugin_map.at(name)` for every plugin entry in the cluster reference map, including entries that only an old ConfigSelector or an in-flight call still references.
- **Description:** When an RDS update removes or renames a plugin, the old ConfigSelector stays alive until the channel switches to the new one, and in-flight calls also keep it alive. Its plugin cluster reference therefore stays in `cluster_ref_map_`. `std::map::at` on the missing name then throws `out_of_range`, which aborts in builds with exceptions disabled. The spec requires the cluster reference to keep the plugin's last LB config. Java and Go both do this. Not yet confirmed with a test.
- **Evidence:** `src/core/resolver/xds/xds_resolver.cc` `XdsResolver::CreateServiceConfig` (the `ConsumePrefix(&cluster_name, "cluster_specifier_plugin:")` branch), `GenerateResult`, and `RouteConfigData::AddRouteEntry` (`maybe_add_cluster` with an empty subscription name).
- **Spec:** `09-xds/05-client.md`, "Cluster references and two-phase removal"

### [critical] xDS server aborts the process when a listening port cannot be bound after start

- **Item:** XDS_SERVER-3
- **Summary:** If binding a listening port fails after `Start()` has returned, the xDS-enabled server aborts the process instead of entering not serving.
- **Description:** C++ binds the listening port only once the xDS config arrives, after `Start()` has returned. If `grpc_tcp_server_add_port` fails then (e.g. the port is in use by another process), the code logs and calls `GRPC_CHECK(0)` (with a TODO noting the assert would not be needed if the port were bound earlier). The spec (and gRFC A36) require the address to enter not serving, notify the application, and retry binding periodically; a bind failure MUST NOT terminate the process. Impact: a port conflict, possibly transient, crashes the whole server process.
- **Evidence:** grpc `src/core/ext/transport/chttp2/server/chttp2_server.cc` (~lines 596-605, `grpc_tcp_server_add_port` error → `GRPC_CHECK(0)`).
- **Spec:** 09-xds/08-server.md, "Port Binding Failures"

### [high] unix: default authority is the percent-encoded path instead of localhost

- **Item:** R39
- **Summary:** The `unix` resolver's default authority is the percent-encoded socket path (e.g. `unix:/tmp/x` → `tmp%2Fx`) instead of `localhost`.
- **Description:** C++ uses the generic default authority (URI path without leading `/`, percent-encoded). The spec requires `localhost` for `unix` targets. The `:authority` header and TLS SNI/verification name therefore differ from other languages, which can break servers or proxies that route or verify on authority. This is a behavior change and needs care when rolled out.
- **Evidence:** `src/core/resolver/resolver_factory.h` `GetDefaultAuthority` (unix resolver uses the default).
- **Spec:** Name Resolution, `unix` (Built-in Resolvers)

### [high] cds policy queues wait_for_ready RPCs for a cluster in error instead of dropping them

- **Item:** R109
- **Summary:** `CdsLb::ReportTransientFailure` uses a `TransientFailurePicker`, so wait_for_ready RPCs queue instead of failing with UNAVAILABLE.
- **Description:** When the cluster's XdsConfig entry is an error (or a static cluster is missing), the cds policy reports TRANSIENT_FAILURE with an ordinary fail picker, which queues wait_for_ready RPCs. The spec (and A31) require a Drop result so the RPC fails with UNAVAILABLE even if wait_for_ready. The resolver's `ClusterRef` (which also holds the CDS `ClusterSubscription`) is released only in the call's OnCommit callback, so a queued RPC keeps the cluster and its CDS watch alive indefinitely and the RPC hangs until its deadline.
- **Evidence:** grpc `src/core/load_balancing/xds/cds.cc` `CdsLb::ReportTransientFailure` (callers at ~343, 355, 377, 383); `src/core/resolver/xds/xds_resolver.cc` `GetOrCreateClusterRef`, `SetOnCommit` (~line 854), `MaybeRemoveUnusedClusters`.
- **Spec:** 09-xds/lb-policies/cds.md, "Update handling"; 09-xds/05-client.md, "Cluster references and two-phase removal"

### [high] Comma-joined `-bin` metadata values fail the call instead of being split

- **Item:** METADATA-1
- **Summary:** A received `-bin` header whose values were joined with `,` fails the call with INTERNAL instead of being split and decoded value by value.
- **Description:** HTTP/2 intermediaries may combine repeated header fields into one comma-separated field. The spec (and PROTOCOL-HTTP2.md) requires receivers to split a `Binary-Header` on `,` before base64-decoding each part. C++ treats the comma as invalid base64 and fails the call. Calls carrying repeated binary metadata through a proxy that joins headers fail, while Java peers handle them.
- **Evidence:** HPACK parser base64 decoding of `-bin` values (`src/core/ext/transport/chttp2/transport/hpack_parser.cc`, `kUnbase64Failed` in `hpack_parse_result.h`).
- **Spec:** 03-wire-protocol/01-http2.md, "Duplicate keys and ordering"

### [high] xDS-enabled server silently runs without xDS when the bootstrap is bad

- **Item:** XDS_SERVER-2
- **Summary:** With a missing or invalid bootstrap, or no `server_listener_resource_name_template`, the xDS server config fetcher is not created and the server runs as a plain non-xDS server.
- **Description:** `grpc_server_config_fetcher_xds_create` logs the error and returns null, so server start succeeds and serves traffic without any xDS-provided security or policy. The spec requires creating or starting the xDS-enabled server to fail in this case, which Java and Go do. Silently serving without the configured mTLS/RBAC is a security hazard.
- **Evidence:** `src/core/server/xds_server_config_fetcher.cc` `grpc_server_config_fetcher_xds_create`.
- **Spec:** 09-xds/08-server.md, "Start-up"

### [high] LOGICAL_DNS cluster loses all endpoints on a DNS error after an earlier success

- **Item:** XDS_RESOLVER-1
- **Summary:** Every DNS error for a LOGICAL_DNS cluster replaces the endpoints with one empty locality, dropping previously resolved addresses.
- **Description:** On each DNS error result, C++ replaces the LOGICAL_DNS cluster's endpoints with a single empty locality, regardless of whether an earlier resolution succeeded. The spec (and gRFC A37) require keeping the previous endpoints when a previous result exists, using an empty list only when there is none, and setting the resolution note to the DNS error. A single transient DNS failure causes an avoidable outage for the cluster.
- **Evidence:** grpc `src/core/resolver/xds/xds_dependency_manager.cc` `XdsDependencyManager::PopulateDnsUpdate`.
- **Spec:** `09-xds/05-client.md`, "LOGICAL_DNS clusters"

### [high] NACK carries the new version_info instead of the previously accepted one

- **Item:** XDS_CLIENT-3
- **Summary:** C++ advances `version_info` when any resource in a response is valid, so a NACK for that response carries the new version.
- **Description:** The xDS protocol and the spec require that `version_info` is not updated for a NACKed response, so a NACK carries the previously accepted version. C++ updates `version_info` whenever any resource in the response was valid, even if the response is NACKed. Control planes that rely on `version_info` to track what the client has accepted will see the rejected version as accepted.
- **Evidence:** grpc `src/core/xds/xds_client/xds_client.cc` `AdsCall` response handling.
- **Spec:** `09-xds/03-xds-client.md`, "Version, nonce, ACK, and NACK"

### [high] Outlier detection: success-rate ejection disabled when enforcing_success_rate is unset

- **Item:** XDS_CDS-1
- **Summary:** C++ disables success-rate ejection when `enforcing_success_rate` is unset; it should be enabled with enforcement 100.
- **Description:** The spec (gRFC A50, Envoy defaults) disables success-rate ejection only when `enforcing_success_rate` is explicitly 0; when unset the algorithm is enabled with enforcement percentage 100. C++ enables each algorithm only when its `enforcing_*` field is set and non-zero, so an unset `enforcing_success_rate` disables success-rate ejection. Clusters relying on the default silently get no success-rate ejection.
- **Evidence:** grpc `src/core/xds/grpc/xds_cluster_parser.cc` outlier detection parsing.
- **Spec:** `09-xds/04-resources/04-cluster.md`, "Outlier Detection"

### [high] File-watcher certificate provider clears certificates when a reload fails

- **Item:** TLS-3
- **Summary:** When a periodic reload of the root or identity files fails, C++ clears the cached material and reports an error to watchers, which fails new handshakes.
- **Description:** The spec requires the file-watcher provider to keep serving the most recently loaded valid material after a reload failure. This matches Java, Go, and the reload-failure rules every gRFC that addresses the question gives (A87 for the SPIFFE bundle loaded by the same provider, A43's policy file watcher, A69's CRL directory provider). C++ instead clears the cached roots or identity and calls `SetErrorForCert`, so one bad or partially written file can cause an outage until the next successful read.
- **Evidence:** `src/core/credentials/transport/tls/grpc_tls_certificate_provider.cc` (`FileWatcherCertificateProvider::ForceUpdate`).
- **Spec:** TLS: File-Watcher Provider

### [high] xDS-enabled server aborts the process when binding fails after configuration arrives

- **Item:** incidental (investigation of old item 199)
- **Summary:** A port bind failure after the Listener arrives hits `GRPC_CHECK(0)` and aborts.
- **Description:** An xDS-enabled server that cannot bind (for example, port in use) after receiving configuration crashes instead of reporting not-serving and retrying. The serving-state behavior itself is an open review item, but a process abort is never acceptable.
- **Evidence:** `src/core/ext/transport/chttp2/server/chttp2_server.cc`; findings G10.
- **Spec:** xDS-Enabled Servers: Port Binding Failures

### [medium] Client "max pings without data" throttle on by default

- **Item:** R8
- **Summary:** C++ clients throttle keepalive pings to one per minute after 2 pings with no data sent (GRPC_ARG_HTTP2_MAX_PINGS_WITHOUT_DATA default 2), which the spec does not allow.
- **Description:** The spec defines no client-side limit on pings sent without data; a client with keepalive enabled pings every KEEPALIVE_TIME. C++ has a client-only limit, default 2, after which pings are throttled to 1/minute. This can break KEEPALIVE_WITHOUT_CALLS configurations with short keepalive times, and C++'s own doc/keepalive.md notes the conflict. The default should be 0 (no limit).
- **Evidence:** grpc `src/core/ext/transport/chttp2/transport/ping_rate_policy.cc`; `doc/keepalive.md`.
- **Spec:** 03-wire-protocol/02-http2-transport.md "Keepalive" / "API Requirements"

### [medium] Response ending with END_STREAM on a DATA frame reports UNKNOWN instead of INTERNAL

- **Item:** R11
- **Summary:** When a response stream ends with END_STREAM on a DATA frame (no trailers at all), C++ reports UNKNOWN; the spec requires INTERNAL.
- **Description:** The chttp2 transport reports UNKNOWN "Stream removed (Data frame with END_STREAM flag received)" when the server ends the stream on a DATA frame without sending trailers. The spec treats a stream with no trailer block as a protocol violation and requires INTERNAL (UNKNOWN is used only when a trailer block is present but lacks grpc-status). Java and Go already report INTERNAL. Applications that classify errors by code see a different status for the same broken server depending on language.
- **Evidence:** C++ chttp2 transport (message "Data frame with END_STREAM flag received"); contrast Java Http2ClientStreamTransportState ("Received unexpected EOS on DATA frame"), Go internal/transport/http2_client.go handleData ("server closed the stream without sending trailers").
- **Spec:** gRPC over HTTP/2 (03-wire-protocol/01-http2.md), "Deriving the status"

### [medium] Service config choice percentage off by one

- **Item:** R38
- **Summary:** A `percentage` choice matches with probability (pct+1)%, so `percentage: 0` still matches 1% of the time.
- **Description:** C++ draws `rand()%100` and skips the choice only when the draw is greater than `percentage`. The spec requires a uniform draw in [0, 99] that matches only when less than `percentage`, so 0 never matches and 100 always matches. Operators using `percentage: 0` to disable a canary config still have 1% of C++ clients pick it up.
- **Evidence:** `src/core/resolver/dns/.../service_config_helper.cc` (choice selection).
- **Spec:** Name Resolution, Service Config in DNS, Service Config Choices (Percentage draw)

### [medium] unix-abstract: default authority is the percent-encoded path instead of localhost

- **Item:** R39
- **Summary:** The `unix-abstract` resolver's default authority is the percent-encoded abstract path instead of `localhost`.
- **Description:** C++ uses the generic default authority for `unix-abstract:` targets. The spec requires `localhost`. The `:authority` header differs from other implementations, which can affect servers that route or verify on authority.
- **Evidence:** `src/core/resolver/resolver_factory.h` `GetDefaultAuthority`.
- **Spec:** Name Resolution, `unix-abstract` (Built-in Resolvers)

### [medium] Proxy name mapping can fetch and apply the proxy host's TXT service config

- **Item:** R40
- **Summary:** When all traffic goes through a proxy, the target URI is rewritten to the proxy name, so with TXT lookup enabled the proxy host's service config is fetched and applied.
- **Description:** The C++ proxy mapper rewrites the target to the proxy's name before resolution. TXT lookup is off by default, but when an application enables it, `_grpc_config.<proxy>` is looked up and applied to the channel. The spec says the resolver MUST NOT fetch a service config for the proxy's name and the channel uses its default service config. Applying a config published for an unrelated host is a safety problem; the default-off TXT lookup limits impact.
- **Evidence:** C++ HTTP proxy mapper (`http_proxy_mapper.cc`) URI rewrite; `GRPC_ARG_SERVICE_CONFIG_DISABLE_RESOLUTION`; dns resolver TXT lookup.
- **Spec:** HTTP CONNECT Proxy Support, All Outbound Traffic Through a Proxy (Name Mapping)

### [medium] "Don't retry" pushback on a non-retryable code is not counted by retry throttling

- **Item:** R42
- **Summary:** C++ does not count a "don't retry" pushback as a throttling failure when the status code is not in `retryableStatusCodes`.
- **Description:** `ShouldRetry` checks `retryableStatusCodes` before looking at `grpc-retry-pushback-ms`, so a negative or unparseable pushback on a non-retryable status returns early without recording a throttling failure. The spec requires that such a failure decrement `token_count`, because the pushback is an explicit server overload signal. As a result, servers that shed load with "don't retry" pushback on non-retryable codes don't make C++ clients throttle.
- **Evidence:** `src/core/client_channel/retry_filter_legacy_call_data.cc` and `src/core/client_channel/retry_interceptor.cc` (`ShouldRetry`).
- **Spec:** Retries and Hedging (`04-client-channel/11-retries.md`), "Behavior" and "Token Accounting".

### [medium] Disabling retries also disables transparent retries

- **Item:** R45
- **Summary:** With `grpc.enable_retries=0`, the retry layer is left out of the stack, so transparent retries stop too, but the spec says they SHOULD continue.
- **Description:** Transparent retries happen inside the retry filter/interceptor. When retries are disabled on the channel, that component isn't installed, so attempts refused before reaching the server application fail straight to the application. The spec says transparent retries SHOULD still happen when retries are disabled. Users see spurious `UNAVAILABLE` errors during server graceful shutdown or stream refusal.
- **Evidence:** `src/core/client_channel/client_channel.cc`, `src/core/client_channel/client_channel_filter.cc` (retry filter installed only when retries are enabled).
- **Spec:** Retries and Hedging (`04-client-channel/11-retries.md`), "Transparent Retries" and "Limits and Disabling Retries".

### [medium] Server silently ignores extra request messages on unary-request methods

- **Item:** R98, R105
- **Summary:** The C++ server does not fail a unary or server-streaming RPC when the client sends more than one request message.
- **Description:** For unary-request methods the C++ server reads one request message and silently ignores any further ones, so the handler runs as if the call were valid. The spec requires the server to fail the RPC with `INTERNAL` when the client sends zero or more than one request message on a unary-request method. Java and Go both reject extra requests with `INTERNAL`. A misbehaving client gets no signal that it is violating the method's cardinality, and data it sent is dropped.
- **Evidence:** `include/grpcpp/support/method_handler.h` (unary/server-streaming handlers read a single message; only the zero-message case fails, with `INTERNAL`, ~L291); `include/grpcpp/support/proto_buffer_reader.h`.
- **Spec:** Core RPC Semantics (`02-rpc-semantics.md`), "Unary Calls"; Server (`05-server.md`), "Request Cardinality".

### [medium] Client response-cardinality violations not reported as INTERNAL

- **Item:** R98
- **Summary:** The C++ client reports `UNIMPLEMENTED` (sync blocking unary only), reports OK for zero responses, or hangs on more than one response, instead of failing with `INTERNAL`.
- **Description:** In the synchronous blocking unary path the C++ client fails a call that ended OK without a response message with `UNIMPLEMENTED`. In the other unary-response paths (async, callback, client-streaming), zero responses with status OK are reported to the application as OK, and more than one response can hang the call (grpc/grpc#36769). The spec requires the client to fail the call with `INTERNAL` when the server sends zero messages with OK, or more than one message, on a unary-response method. Applications may see a successful call with an empty/default response, or a hung RPC.
- **Evidence:** `include/grpcpp/impl/client_unary_call.h` (~L88-90, `StatusCode::UNIMPLEMENTED`); grpc/grpc#36769.
- **Spec:** Core RPC Semantics (`02-rpc-semantics.md`), "Unary Calls".

### [medium] Out-of-range GRPC_ALLOW_TRUE_BINARY_METADATA value fails the connection

- **Item:** R122
- **Summary:** A `GRPC_ALLOW_TRUE_BINARY_METADATA` (0xfe03) value greater than 1 is treated as a connection `PROTOCOL_ERROR` instead of as 0.
- **Description:** `Http2Settings::Apply` returns `Http2ErrorCode::kProtocolError` for values above 1, which tears down the whole connection. The setting ID is in the HTTP/2 experimental range and may be used by another extension, so a peer sending a different value is not necessarily misbehaving. The spec requires values other than 0 and 1 to be treated as 0 (feature off) and not as a connection error. Impact is limited to peers running a colliding extension.
- **Evidence:** `src/core/ext/transport/chttp2/transport/http2_settings.cc`, `Http2Settings::Apply`, case `kGrpcAllowTrueBinaryMetadataWireId`: `if (value > 1) return Http2ErrorCode::kProtocolError;`
- **Spec:** 03-wire-protocol/03-true-binary-metadata.md, "Setting"

### [medium] outlier_detection enforcement draws its random number from [1, 100)

- **Item:** incidental (investigation of old items 61–62)
- **Summary:** With `enforcementPercentage` = 1, no ejection ever happens.
- **Description:** The algorithm ejects when a uniform random value in [0, 100) is below the enforcement percentage. C++ draws from [1, 100), so low percentages are under-enforced and 1% never ejects.
- **Evidence:** `src/core/load_balancing/outlier_detection/outlier_detection.cc`; findings G5.
- **Spec:** `outlier_detection` LB Policy: Ejection Timer

### [medium] DNS TXT lookups performed for localhost and IP literals

- **Item:** incidental (investigation of old item 85)
- **Summary:** The resolver appears to query `_grpc_config.localhost` and `_grpc_config.<ip>`.
- **Description:** The spec forbids service config TXT lookups for `localhost` and IP literals. This causes extra DNS traffic and latency when TXT lookup is enabled. Reported by the investigator from code reading; not re-verified.
- **Evidence:** `src/core/resolver/dns/` (c-ares and event-engine resolvers); findings G4.
- **Spec:** Name Resolution: dns

### [medium] Message with Compressed-Flag 2 may be silently dropped

- **Item:** incidental (investigation of old item 25)
- **Summary:** A length-prefixed message whose flag byte is neither 0 nor 1 appears to be discarded without failing the call.
- **Description:** The spec requires such a message to fail the call with INTERNAL. Silently dropping a message corrupts the message stream. Found by code reading only; untested.
- **Evidence:** `src/core/ext/transport/chttp2/transport/` message framing; findings G1.
- **Spec:** gRPC over HTTP/2: Length-Prefixed Messages

### [medium] Aggregate cluster's LB policy fields are validated instead of ignored

- **Item:** R111
- **Summary:** An aggregate cluster whose LB policy fields are unsupported (e.g. `lb_policy: CLUSTER_PROVIDED`) is NACKed.
- **Description:** `CdsResourceParse` calls `ParseLbPolicyConfig` for every cluster, including aggregate clusters. Envoy requires aggregate clusters to use `lb_policy: CLUSTER_PROVIDED`, which gRPC does not support, so an aggregate cluster configured the Envoy way is NACKed. The spec says the aggregate cluster's LB policy fields are ignored entirely (not validated, never cause rejection). Impact: control planes that serve both Envoy and gRPC cannot use aggregate clusters with gRPC clients.
- **Evidence:** grpc `src/core/xds/grpc/xds_cluster_parser.cc` ~line 490 (`ParseLbPolicyConfig` called unconditionally) and ~line 395 (unsupported `lb_policy` error).
- **Spec:** 09-xds/04-resources/04-cluster.md, "Aggregate Clusters"

### [medium] xDS route header matching treats `:authority` and `host` as the call's authority

- **Item:** XDS_ROUTING-1
- **Summary:** Route header matchers on `:authority` or `host` match the call's authority instead of treating `:authority` as absent and `host` as ordinary metadata.
- **Description:** `GetHeaderValue` returns the call's authority for both `:authority` and `host` (`IsAuthorityHeaderName`), so routes can match on the authority through header matchers. The spec (and gRFC A28) say pseudo-headers are absent during route matching and `host` is looked up like any other metadata name; the authority is matched only by virtual host selection. Java and Go follow the spec. Impact: the same RouteConfiguration routes RPCs differently in C++ than in Java and Go when a route matches on `:authority` or `host`.
- **Evidence:** grpc `src/core/xds/grpc/xds_routing.cc` `GetHeaderValue` (~lines 203-211).
- **Spec:** 09-xds/04-resources/01-common-types.md, "gRPC Header Semantics"

### [medium] file_watcher certificate provider uses `spiffe_bundle_map_file` instead of `spiffe_trust_bundle_map_file`

- **Item:** XDS_BOOTSTRAP-4, XDS_SECURITY-2
- **Summary:** The `file_watcher` plugin config reads the SPIFFE trust bundle map path from `spiffe_bundle_map_file`; the spec, gRFC A87, Java and Go use `spiffe_trust_bundle_map_file`.
- **Description:** The bootstrap `file_watcher` certificate provider factory parses `spiffe_bundle_map_file`. A bootstrap written for the other languages (with `spiffe_trust_bundle_map_file`) gets no SPIFFE trust bundle map in C++ and silently falls back to `ca_certificate_file`, while a C++-style bootstrap is ignored by Java and Go. The name likely came from the C++ API parameter (`spiffe_bundle_map_path`), which is not the JSON key. Suggested fix: accept `spiffe_trust_bundle_map_file`, keeping `spiffe_bundle_map_file` as a deprecated alias for a while. Impact: a shared bootstrap file behaves differently for SPIFFE trust across languages.
- **Evidence:** grpc `src/core/xds/grpc/file_watcher_certificate_provider_factory.cc` (~lines 94 and 112).
- **Spec:** 09-xds/02-bootstrap.md, "`file_watcher` plugin"; 09-xds/09-security.md, "`file_watcher` Plugin"

### [low] outlier_detection max_ejection_percent checked before ejection instead of against the resulting percentage

- **Item:** R18
- **Summary:** max_ejection_percent is compared with the percentage already ejected, so ejection can exceed the limit and 0 still ejects one endpoint.
- **Description:** Both algorithms eject when `ejected_host_count == 0 || current_percent < max_ejection_percent`, comparing the percentage already ejected (so the last ejection can exceed the limit) and always allowing one ejection (so max_ejection_percent = 0 still ejects one endpoint). The spec (gRFC A50 as updated, matching Envoy's default with `always_eject_one_host` off) ejects an endpoint only if `100 * (ejected + 1) / endpoints <= max_ejection_percent`, so the limit is never exceeded and 0 disables ejection. Impact: in small endpoint sets gRPC ejects endpoints that Envoy would not; e.g. with the default 10% and 3 endpoints, gRPC ejects one (33%) while Envoy ejects none.
- **Evidence:** grpc `src/core/load_balancing/outlier_detection/outlier_detection.cc` (~lines 993-995 and 1051-1053).
- **Spec:** 04-client-channel/lb-policies/outlier_detection.md, "Success-Rate Algorithm" / "Failure-Percentage Algorithm"

### [low] priority LB does not reject duplicate names in `priorities`

- **Item:** R21
- **Summary:** The priority policy config parser accepts a child name that appears more than once in `priorities`.
- **Description:** C++ doesn't check for repeated names in the priority policy's `priorities` list. The spec says such a config is invalid. Rejecting it catches control-plane bugs early and gives the same accept/reject result across implementations.
- **Evidence:** `src/core/load_balancing/priority/priority.cc` config JsonPostLoad (no duplicate check).
- **Spec:** 04-client-channel/lb-policies/priority.md, Configuration → Validation

### [low] priority LB accepts children not referenced by `priorities`

- **Item:** R21
- **Summary:** A `children` entry whose name is not in `priorities` is silently accepted and never created.
- **Description:** C++ accepts a priority config with children that no priority refers to, and simply never creates them. Java and Go reject the config, as the spec requires. Silent acceptance hides control-plane mistakes and differs from other clients.
- **Evidence:** `src/core/load_balancing/priority/priority.cc` config JsonPostLoad; grpc-go `priority/config.go` parseConfig and grpc-java PriorityLoadBalancerProvider reject it.
- **Spec:** 04-client-channel/lb-policies/priority.md, Configuration → Validation

### [low] Retry throttling successes counted only for RPCs with a retry policy

- **Item:** R43
- **Summary:** C++ records throttle successes only for RPCs that have a retry policy, not for every RPC on the channel.
- **Description:** In C++, successful RPCs on methods without a retry policy do not add `tokenRatio` to `token_count`. The spec counts an OK attempt on any RPC on the channel, whether or not it has a retry or hedging policy. On channels where only some methods retry, the token bucket recovers more slowly than the spec intends.
- **Evidence:** `src/core/client_channel/retry_filter_legacy_call_data.cc` / `retry_interceptor.cc` (`ShouldRetry`; success recorded only on the retry path).
- **Spec:** Retries and Hedging (`04-client-channel/11-retries.md`), "Token Accounting".

### [low] Negative method-config timeout with a zero seconds part is accepted as positive

- **Item:** R48
- **Summary:** C++ parses `"-0.5s"` as +0.5s instead of rejecting it as a negative duration.
- **Description:** `LoadDuration` range-checks the seconds part, but drops the sign when seconds is 0, so values like `"-0.5s"` become positive timeouts. The spec says any negative timeout makes the service config invalid. It is a rare edge case, but it silently turns an invalid config into a valid one with a different meaning.
- **Evidence:** `src/core/util/json/json_object_loader.cc` (`LoadDuration`).
- **Spec:** Service Config (`04-client-channel/04-service-config.md`), "`methodConfig`" field table (`timeout`).

### [low] No base64 fallback after RST_STREAM(PROTOCOL_ERROR) on true-binary metadata

- **Item:** R124
- **Summary:** The client does not retry in base64 or disable true-binary encoding on the connection when a misconfigured peer rejects true-binary headers.
- **Description:** The spec says a client that sent true-binary metadata and gets `RST_STREAM(PROTOCOL_ERROR)` before any response headers SHOULD retry the request in base64 (not counted against retry policy), SHOULD stop using true binary on that connection, and SHOULD log the event. C++ does not appear to implement any of this, so against a peer that aliases setting 0xfe03 every RPC carrying binary metadata fails. These are SHOULDs, so this is a gap rather than a violation, and it only matters with a colliding extension.
- **Evidence:** findings for R124 (review_items.md); no fallback logic found in `src/core/ext/transport/chttp2/transport/` (`chttp2_transport.cc`, `writing.cc`, `http2_client_transport.cc`).
- **Spec:** 03-wire-protocol/03-true-binary-metadata.md, "Misconfiguration Fallback"

### [low] RLS sends a throttled stale refresh anyway

- **Item:** R133
- **Summary:** When the throttler says to throttle and the entry still has valid data, `RlsLb::Picker::Pick` starts the RLS call anyway.
- **Description:** The throttle check only returns early when there is no valid data. Otherwise it falls through to `StartRlsCall`. The throttled request has already been recorded as a request plus a failure, so the lookup is both counted as throttled and sent. The spec says a throttled refresh is not sent and the data keeps being used.
- **Evidence:** `src/core/load_balancing/rls/rls.cc` `RlsLb::Picker::Pick` (the `ShouldThrottle()` block followed by `StartRlsCall`).
- **Spec:** `04-client-channel/lb-policies/rls.md`, "Adaptive Throttling"

### [low] RLS config validation differs from the spec

- **Item:** R133
- **Summary:** C++ accepts things the spec rejects and rejects things the spec accepts.
- **Description:**
  - Accepts things the spec rejects: an empty `grpcKeybuilders` list and an empty `Name.service`.
  - Rejects things the spec accepts: `requiredMatch: false`, an empty `NameMatcher.names` list, an explicit empty `extraKeys` value, and an explicit empty `defaultTarget`.
  - Keeps an explicit zero `lookupServiceTimeout` and `maxAge` instead of treating them as the default.

  None of these cases occur in configs generated from xDS. They only affect hand-written service configs.
- **Evidence:** `src/core/load_balancing/rls/rls.cc` `GrpcKeyBuilder::NameMatcher::JsonPostLoad`, `ExtraKeys::JsonPostLoad`, `RouteLookupConfig::JsonPostLoad`.
- **Spec:** `04-client-channel/lb-policies/rls.md`, "routeLookupConfig" and "grpcKeybuilders"

### [low] Unparseable `grpc-status` reported as INTERNAL instead of UNKNOWN

- **Item:** incidental (investigation of old items 29–30)
- **Summary:** A non-numeric `grpc-status` value produces INTERNAL.
- **Description:** statuscodes.md and the spec map an unparseable status to UNKNOWN.
- **Evidence:** `src/core/lib/transport/metadata_batch.cc` (grpc-status parsing); findings G1.
- **Spec:** gRPC over HTTP/2: `grpc-status`

### [low] `grpc-timeout` with 9 digits accepted

- **Item:** incidental (investigation of old item 22)
- **Summary:** The timeout parser accepts values longer than the 8-digit maximum.
- **Description:** `TimeoutValue` is at most 8 digits. Accepting longer values is lenient but non-conforming.
- **Evidence:** `src/core/lib/transport/timeout_encoding.cc`; findings G1.
- **Spec:** gRPC over HTTP/2: `grpc-timeout`

### [low] `clientLanguage` matching is case-sensitive

- **Item:** incidental (investigation of old items 84–86)
- **Summary:** Service config choices compare `clientLanguage` case-sensitively.
- **Description:** The choice format specifies case-insensitive matching.
- **Evidence:** `src/core/resolver/dns/dns_resolver_plugin` / `service_config_helper.cc`; findings G4.
- **Spec:** Name Resolution: Service Config Choices

### [low] Channelz ignores `max_results` for GetTopChannels and GetServers

- **Item:** incidental (spec audit, obsb group)
- **Summary:** `GetTopChannels` and `GetServers` ignore the request's `max_results` and always return pages of up to 100.
- **Description:** The Channelz service is supposed to honor `max_results` (up to an implementation cap). C++ always uses a page size of 100 for `GetTopChannels` and `GetServers`. It does honor `max_results` for `GetServerSockets`. Reported by the spec audit; not re-verified.
- **Evidence:** [channelz_service.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/channelz/channelz_service.cc#L79-L80), [channelz_registry.h](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/channelz_registry.h#L311-L316)
- **Spec:** Channelz: Pagination
