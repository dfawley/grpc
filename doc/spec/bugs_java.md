# Java implementation bugs

Bugs in grpc-java found while writing and reviewing the gRPC spec in this directory: **115** entries, ordered by severity. Other lists: [Go](bugs_go.md), [C++](bugs_cpp.md), [documentation](bugs_docs.md).

Severity:

- **critical:** crash, data corruption, or a security weakness
- **high:** interoperability failure, or wrong behavior that users commonly hit
- **medium:** spec non-conformance with limited impact
- **low:** cosmetic, or a rare edge case

Each bug lists the review item that identified it (an item ID such as `RLS-4`, an `R<n>` number from the original review list, or "incidental"/"audit"), a summary, a description, evidence (code locations), and the spec section it violates. Open questions are in [review_items.md](review_items.md). None of these bugs has been filed yet.

### [low] Java does not validate retryPolicy, hedgingPolicy, or retryThrottling when retries are disabled

- **Item:** RETRY-4
- **Summary:** On a channel with retries disabled, Java skips parsing the service config's retry, hedging, and throttling settings, so invalid values are accepted instead of making the service config invalid.
- **Description:** `ManagedChannelServiceConfig.fromServiceConfig` calls `ServiceConfigUtil.getThrottlePolicy` only when `retryEnabled`, and `MethodInfo` calls `getRetryPolicyFromMethodConfig` and `getHedgingPolicyFromMethodConfig` only when `retryEnabled`. A service config with an invalid `retryPolicy` (for example `maxAttempts` < 2 or a missing `retryableStatusCodes`) is therefore accepted on a channel with retries disabled and rejected on one with retries enabled. The spec says these fields are still validated when retries are disabled, which C++ and Go do, so whether a config is valid does not depend on a local channel option.
- **Evidence:** grpc-java ed3bf6b76b65fc76c1669ef70b71765844eb8a50: [ManagedChannelServiceConfig.java L95-L98](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelServiceConfig.java#L95-L98), [ManagedChannelServiceConfig.java L285-L293](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelServiceConfig.java#L285-L293)
- **Spec:** Retries and Hedging: Limits and Disabling Retries

### [low] Java: RLS child state not sticky after TRANSIENT_FAILURE

- **Item:** RLS-11
- **Summary:** Java records every state an RLS child reports, so a child that failed counts as CONNECTING or IDLE again while it retries.
- **Description:** The spec keeps the child's recorded state at TRANSIENT_FAILURE until it reports READY (the picker is still updated). The `ChildPolicyWrapper` helper stores every state and picker with no stickiness, which changes target selection (a retrying child is no longer skipped) and the aggregate state.
- **Evidence:** [LbPolicyConfiguration.java L399-L402](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/rls/src/main/java/io/grpc/rls/LbPolicyConfiguration.java#L399-L402)
- **Spec:** `rls` LB Policy: Calls From Children

### [medium] Java: priority LB policy does not forward ExitIdle to the current child

- **Item:** PRIORITY-2
- **Summary:** `PriorityLoadBalancer` doesn't override `requestConnection()`, so `ExitIdle()` never reaches the current priority's child.
- **Description:** The spec forwards `ExitIdle()` to the current priority's child. In Java the call is a no-op, so a child that waits for `ExitIdle()` (for example, an IDLE `pick_first`-based child) is never woken by the parent when the channel leaves idle.
- **Evidence:** [PriorityLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/PriorityLoadBalancer.java) (no `requestConnection` override)
- **Spec:** `priority` LB Policy: ExitIdle

### [medium] Java: outlier detection ejects an endpoint twice in one sweep

- **Item:** OUTLIER_DETECTION-1
- **Summary:** Neither Java algorithm skips ejected trackers, so an endpoint that fails both algorithms in one sweep is ejected twice (multiplier +2), and an endpoint ejected earlier can be ejected again.
- **Description:** The spec excludes already-ejected endpoints from the candidates and from the statistics. Java's success-rate and failure-percentage loops consider every tracker with enough volume, and `ejectSubchannels` increments the multiplier each time. This lengthens ejection times and counts ejected outliers in the mean/stdev.
- **Evidence:** [OutlierDetectionLoadBalancer.java L828-L848](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java#L828-L848) (success rate), [L902-L925](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java#L902-L925) (failure percentage), [L613-L619](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java#L613-L619) (`ejectSubchannels`)
- **Spec:** `outlier_detection` LB Policy: Ejection Timer

### [low] Java DNS service config choices validated only up to the selected choice

- **Item:** DNS-2
- **Summary:** Java rejects unknown keys and an out-of-range `percentage`, but it checks only the choices up to and including the first one that matches.
- **Description:** `DnsNameResolver` loops over the choices and stops at the first match. `maybeChooseServiceConfig` does the key check (`Verify` "Bad key") and the percentage check per choice, so the choices after the selected one are never checked. A malformed record is therefore accepted or rejected depending on the client's language, hostname, and random draw.
- **Evidence:** [DnsNameResolver.java#L469-L492](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/DnsNameResolver.java#L469-L492), caller loop around L340-L355
- **Spec:** Name Resolution: Service Config in DNS › Service Config Choices

### [medium] Java ring_hash does not validate requestHashHeader at parse time

- **Item:** RING_HASH-5
- **Summary:** Java accepts an invalid or `-bin` `requestHashHeader` when it parses the config. Later, `Metadata.Key.of` throws inside `acceptResolvedAddresses`.
- **Description:** `RingHashLoadBalancerProvider.parseLoadBalancingPolicyConfig` reads the field only when `GRPC_EXPERIMENTAL_RING_HASH_SET_REQUEST_HASH_KEY` is set, and it never validates it. gRFC A76 requires the config to be rejected.
- **Evidence:** [RingHashLoadBalancerProvider.java#L82-L110](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RingHashLoadBalancerProvider.java#L82-L110), [RingHashLoadBalancer.java#L109-L112](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java#L109-L112)
- **Spec:** `ring_hash` LB Policy: Configuration

### [low] Java weighted_target reports no state when targets is empty

- **Item:** WEIGHTED_TARGET-3
- **Summary:** With an empty `targets` map, `updateOverallBalancingState` never calls `updateBalancingState`, so RPCs can queue forever.
- **Description:** `overallState` starts as null and stays null when there are no targets. The update is skipped, and the parent keeps its previous picker (at first, a queueing picker). C++ and Go report TRANSIENT_FAILURE with an UNAVAILABLE "no children/targets" error.
- **Evidence:** [WeightedTargetLoadBalancer.java#L146-L177](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/WeightedTargetLoadBalancer.java#L146-L177)
- **Spec:** `weighted_target` LB Policy: Picker Implementation

### [medium] Java subchannel reconnects after backoff and on ResetBackoff instead of reporting IDLE

- **Item:** SUBCHANNEL-1
- **Summary:** By default `InternalSubchannel` goes from TRANSIENT_FAILURE straight to CONNECTING when backoff ends or on `resetConnectBackoff()`, so it makes connection attempts the LB policy never asked for.
- **Description:** `EndOfCurrentBackoff.run()` and `resetConnectBackoff()` both call `gotoNonErrorState(CONNECTING)` and `startNewTransport()`. Only pick_first with the off-by-default `GRPC_SERIALIZE_RETRIES` sets `DISABLE_SUBCHANNEL_RECONNECT_KEY`. C++ and Go go to IDLE and wait for `RequestConnection()`, and LB policies such as pick_first (Happy Eyeballs) and ring_hash (lazy connect) count on that.
- **Evidence:** [InternalSubchannel.java#L296-L306](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L296-L306), [InternalSubchannel.java#L336-L349](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L336-L349)
- **Spec:** Subchannels and Connections: Connectivity States

### [low] Java resets retry throttle tokens on any service config change

- **Item:** RETRY-3
- **Summary:** When any part of the effective service config changes, Java installs the new config's freshly built `Throttle` (full tokens), even if the throttling parameters didn't change. When the parameters do change, it doesn't scale `token_count / maxTokens`.
- **Description:** `transportProvider.throttle = effectiveServiceConfig.getRetryThrottling()` runs whenever `!effectiveServiceConfig.equals(lastServiceConfig)`. The `Throttle` constructor starts at `maxTokens`.
- **Evidence:** [ManagedChannelImpl.java#L1752-L1758](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1752-L1758), [RetriableStream.java#L1503-L1509](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L1503-L1509)
- **Spec:** Retries: Token Accounting

### [low] Java does not treat an empty client_default_listener_resource_name_template as "%s"

- **Item:** XDS_BOOTSTRAP-6
- **Summary:** With `"client_default_listener_resource_name_template": ""`, Java watches the Listener named `""`.
- **Description:** `BootstrapperImpl` stores any non-null value as is, and `XdsNameResolver` uses it as the template for targets without an authority, so every such xDS channel watches an empty Listener name and never gets a config. C++ and Go replace an empty value with `"%s"`.
- **Evidence:** [BootstrapperImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/BootstrapperImpl.java#L204-L211), [XdsNameResolver.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L229)
- **Spec:** xDS Bootstrap: Top-Level Fields

### [medium] Java does not support xDS server call_creds (gRFC A97)

- **Item:** XDS_BOOTSTRAP-8
- **Summary:** Java ignores `call_creds` in bootstrap `xds_servers` entries, so `jwt_token_file` is silently dropped and the xDS channel sends no token.
- **Description:** `BootstrapperImpl.parseServerInfos` never reads `call_creds`. The only call-credentials parser (for `allowed_grpc_services`) returns empty ("Currently no xDS call credentials providers are implemented"). Deployments that rely on JWT auth to the control plane cannot authenticate from Java, and no error is reported. C++ and Go implement `jwt_token_file`.
- **Evidence:** [BootstrapperImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/BootstrapperImpl.java#L267-L304), [GrpcBootstrapperImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/GrpcBootstrapperImpl.java#L211-L220)
- **Spec:** xDS Bootstrap: XdsServer Object

### [low] Java accepts a HeaderMatcher range_match with start > end

- **Item:** XDS_ROUTING-10
- **Summary:** An inverted `range_match` is accepted instead of NACKing the resource.
- **Description:** `MatcherParser` builds the range matcher without checking `start <= end`. The matcher never matches (or always matches when inverted). C++ rejects the resource.
- **Evidence:** [MatcherParser.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/internal/MatcherParser.java#L57-L79)
- **Spec:** xDS Common Types: HeaderMatcher

### [low] Java does not validate VirtualHost domains

- **Item:** XDS_ROUTING-7
- **Summary:** An empty `domains` list or an invalid domain pattern is accepted instead of NACKing the RouteConfiguration.
- **Description:** `parseVirtualHost` copies `getDomainsList()` unchecked. An invalid pattern never matches, and an empty list is accepted. C++ (`XdsRouting::IsValidDomainPattern` plus a non-empty check) and Envoy reject.
- **Evidence:** [XdsRouteConfigureResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L206-L207)
- **Spec:** RouteConfiguration: Domain Patterns

### [low] Java accepts an empty route cluster, empty hash-policy header_name, and regex_rewrite without a pattern

- **Item:** XDS_ROUTING-9
- **Summary:** Several invalid RouteAction fields are accepted instead of NACKing the RouteConfiguration.
- **Description:** `RouteAction.forCluster` only checks the cluster name for null, so `""` is accepted and RPCs fail later. The hash-policy parser accepts an empty `header_name`, and silently ignores a `regex_rewrite` without `pattern` instead of rejecting it. C++ rejects all three.
- **Evidence:** [VirtualHost.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/VirtualHost.java#L171-L177), [XdsRouteConfigureResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L434-L445)
- **Spec:** RouteConfiguration: Cluster Specifier; RouteConfiguration: Hash Policy

### [medium] Java does not reset LRS stats for unrequested clusters

- **Item:** XDS_LRS-2
- **Summary:** Stats for clusters the LRS server did not ask for keep building up and appear in the first report after the server asks for that cluster.
- **Description:** When `send_all_clusters` is false, `sendLoadReport` snapshots only `clusterNames`. Other clusters' counters are never reset, so a later request for them reports load from earlier intervals as current, which skews server load decisions. C++ snapshots and resets every cluster and discards the unrequested ones.
- **Evidence:** [LoadReportClient.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/LoadReportClient.java#L250-L265)
- **Spec:** xDS Load Reporting: Responses

### [low] Java outlier_detection accepts an interval of 0 and throws from acceptResolvedAddresses

- **Item:** OUTLIER_DETECTION-4
- **Summary:** An `interval` of 0 is accepted. `scheduleWithFixedDelay(…, 0, …)` then throws `IllegalArgumentException` from `acceptResolvedAddresses`.
- **Description:** The spec now makes `interval` 0 invalid: the LB config is rejected, and the xDS Cluster resource is NACKed. Java's config parsing and xDS Cluster parsing reject only negative values.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java#L164-L165, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/SynchronizationContext.java#L185-L200
- **Spec:** `outlier_detection` LB Policy: 2.2 Validation; Cluster: 4. Outlier Detection

### [low] Java: method config with both retryPolicy and hedgingPolicy is accepted

- **Item:** SERVICE_CONFIG-7
- **Summary:** Java accepts a method config that sets both `retryPolicy` and `hedgingPolicy` and hedges, instead of rejecting the service config.
- **Description:** The spec (following the `oneof retry_or_hedging_policy` in service_config.proto and gRFC A6) says that setting both in the same method config entry makes the service config invalid. Java parses both, and `RetriableStream` uses hedging when `hedgingPolicy` is set.
- **Evidence:** [ManagedChannelServiceConfig.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelServiceConfig.java#L285-L293), [RetriableStream.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L148)
- **Spec:** Service Config: `methodConfig`

### [low] Java: received_goaway_error and peer_max_concurrent_streams not populated in channelz

- **Item:** CHANNELZ-4
- **Summary:** Java's channelz does not set `SocketData.received_goaway_error` or `SocketData.peer_max_concurrent_streams`.
- **Description:** The spec requires `received_goaway_error` when a GOAWAY has been received and `peer_max_concurrent_streams` on the client. Neither is referenced in `ChannelzProtoUtil` or elsewhere outside generated code. (`max_connections_per_subchannel` is covered by an optionality note, since Java has no connection scaling.)
- **Evidence:** [ChannelzProtoUtil.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/services/src/main/java/io/grpc/protobuf/services/ChannelzProtoUtil.java)
- **Spec:** Channelz: `SocketData`

### [low] Java: received out-of-range ASCII metadata values are accepted, but echoing them silently mangles or drops them

- **Item:** METADATA-2
- **Summary:** Java keeps ASCII values with bytes outside 0x20–0x7E on receipt, but the application cannot send the same value back: it is changed to `?` or the header is silently dropped.
- **Description:** The transport keeps non-binary values as raw bytes with no check. Read as a `String`, `AsciiKey.parseBytes` decodes with US-ASCII so bytes 0x80–0xFF become U+FFFD, and re-sending encodes each as `?`. A `Metadata` object echoed as-is keeps the raw bytes, but `TransportFrameUtil.toHttp2Headers` silently drops (with a logged warning) any non-binary header containing a byte outside 0x20–0x7E, on both Netty and OkHttp. The call does not fail, but the spec requires that an accepted value can be sent back as that same value. Fix: discard such values on receipt (allowed by the spec), or send them unchanged.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/TransportFrameUtil.java#L100-L119, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/TransportFrameUtil.java#L66-L78, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/TransportFrameUtil.java#L170-L177, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/Metadata.java#L981-L990
- **Spec:** 2. Core RPC Semantics: 7.2 Values

### [medium] Java: service config waitForReady overrides the application's explicit wait-for-ready

- **Item:** WAIT_FOR_READY-1
- **Summary:** `ClientCallImpl.applyMethodConfig` replaces the call's wait-for-ready with the method config's value even when the application set it explicitly.
- **Description:** Whenever the method config sets `waitForReady`, Java does `callOptions = info.waitForReady ? withWaitForReady() : withoutWaitForReady()`, ignoring that `CallOptions` records (tri-state `Boolean`) whether the application set it. A service owner can silently flip an application's fail-fast or wait-for-ready choice, changing how RPCs fail during outages. Fix: apply the method config only when the application left it unset.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ClientCallImpl.java#L308-L311, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/CallOptions.java#L78
- **Spec:** 2. Core RPC Semantics: 14 Wait-for-Ready; Service Config: 5.4 `methodConfig`

### [low] Java: duplicate Host headers accepted when :authority is present

- **Item:** HTTP2-5
- **Summary:** The Netty server rejects multiple `Host` headers only when `:authority` is absent.
- **Description:** In `NettyServerHandler.onHeadersRead`, the `hosts.size() > 1` check is inside `if (headers.authority() == null)`. Otherwise all `Host` headers are removed and the request proceeds. The spec (and A41) require rejection (400, `INTERNAL`, or `RST_STREAM(PROTOCOL_ERROR)`) whenever there is more than one `Host` or more than one `:authority`. Duplicate `:authority` handling depends on Netty's HPACK validation and was not verified.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyServerHandler.java#L468-L480
- **Spec:** gRPC over HTTP/2: 3.4 `:authority` and `Host`

### [low] Java: grpc-status ignored on non-gRPC content-type, and HTTP status ignored after gRPC Response-Headers

- **Item:** HTTP2-1
- **Summary:** Java derives the status from the HTTP status mapping when the content-type is not gRPC, even if `grpc-status` is present; and it reports `UNKNOWN` instead of the HTTP mapping when non-200 gRPC-typed Response-Headers are followed by trailers without `grpc-status`.
- **Description:** `validateInitialMetadata` returns the HTTP-mapped error for any non-gRPC content-type, and `transportTrailersReceived` reports that error instead of reading `grpc-status`. A Trailers-Only block with `text/plain` and `grpc-status: 14` (as proxies such as Envoy send) gets the HTTP mapping. Conversely, a non-200 `:status` on gRPC Response-Headers followed by trailers with no `grpc-status` yields `UNKNOWN`.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/Http2ClientStreamTransportState.java#L172-L233
- **Spec:** gRPC over HTTP/2: 7.2 Deriving the status

### [low] Java: client reports CANCELLED and server reports UNKNOWN for a message that fails to parse

- **Item:** PROTOBUF-1
- **Summary:** Deserialization failures produce `CANCELLED` on the client and `UNKNOWN` on the server instead of `INTERNAL`.
- **Description:** The marshaller throws an `INTERNAL` `StatusRuntimeException`, but `ClientCallImpl` catches it and cancels with `CANCELLED` "Failed to read message.", and on the server the exception escapes `messagesAvailable` and `ServerImpl`'s `internalClose` sends `UNKNOWN` "Application error processing RPC". Both drop the marshaller's status. `CANCELLED` wrongly suggests the application cancelled the call.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ClientCallImpl.java#L669-L672, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ServerCallImpl.java#L358-L371, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ServerImpl.java#L832-L836
- **Spec:** Protocol Buffers: 2. Message Encoding (`+proto`); Server Behavior: 2.3 Request Cardinality

### [medium] Java: method config message size limits can raise a channel limit the application set

- **Item:** SERVICE_CONFIG-6
- **Summary:** `maxResponseMessageBytes` from the service config replaces the channel builder's `maxInboundMessageSize` instead of being combined with it by minimum.
- **Description:** `ClientCallImpl.applyMethodConfig` combines the method config value only with a per-call `CallOptions` limit, then `stream.setMaxInboundMessageSize` overrides the transport-level channel setting. A remote service owner can therefore raise a limit the application set explicitly. The spec and service_config.proto require the minimum of the method config value and the application's value.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ClientCallImpl.java#L312-L321, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ClientCallImpl.java#L271-L272
- **Spec:** Service Config: 5.4 `methodConfig`; Call Dispatch (ApplyConfig); 2. Core RPC Semantics: 12 Message Size Limits

### [medium] Java: client connection attempts have no connect deadline covering the handshake and SETTINGS

- **Item:** SUBCHANNEL-2
- **Summary:** Java bounds only the TCP connect (OS/Netty default); a server that accepts TCP but stalls the TLS handshake or never sends SETTINGS holds the subchannel's attempt indefinitely.
- **Description:** The spec bounds each whole connection attempt by `Max(current_deadline, now + MIN_CONNECT_TIMEOUT)` (MIN_CONNECT_TIMEOUT = 20 s), per doc/connection-backoff.md. Java's `InternalSubchannel.startNewTransport()` passes no deadline to the transport, and the Netty and OkHttp transports apply no gRPC timeout to the TLS handshake or to waiting for the server's SETTINGS. `MIN_CONNECT_TIMEOUT` does not exist in the code. A stalled server blocks the subchannel (until keepalive fires, if enabled) instead of failing over. C++ and Go implement the deadline.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L284 ; https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyClientTransport.java#L352
- **Spec:** Subchannels and Connections: Connection Establishment; Subchannels and Connections: Connection Backoff

### [medium] Java: client-side health checking only works with round_robin, and the stream runs without a health watcher

- **Item:** HEALTH-1
- **Summary:** Java's health-check client is a per-policy wrapper applied only to `round_robin`; `weighted_round_robin`, `least_request`, and `ring_hash` silently get no health checking, and inside the wrapper the stream runs regardless of watchers.
- **Description:** gRFC A17 puts health checking in the subchannel so LB policies need no explicit support, and gRFC A61 delivers it through pick_first's health-reporting option under any petiole policy. In Java, the Watch client lives in `HealthCheckingLoadBalancerFactory`, applied only by `HealthCheckingRoundRobinLoadBalancerProvider` (or by custom policies that wrap themselves via `HealthCheckingLoadBalancerUtil`). A service config with `healthCheckConfig` and `weighted_round_robin`, `least_request`, or `ring_hash` gets no health checking. Inside the wrapper, a stream starts for every READY subchannel once a service name is set, whether or not a health watcher is registered, and for a policy that passes no health listener the health result replaces the subchannel's connectivity state. C++ and Go health-check under every petiole and start the stream only when pick_first registers a watcher.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/services/src/main/java/io/grpc/protobuf/services/internal/HealthCheckingRoundRobinLoadBalancerProvider.java#L57 ; https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/services/src/main/java/io/grpc/protobuf/services/HealthCheckingLoadBalancerFactory.java#L333 ; https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/services/src/main/java/io/grpc/protobuf/services/HealthCheckingLoadBalancerFactory.java#L191
- **Spec:** Client-Side Health Checking: Where Health Checking Applies

### [medium] Java: hedging ignores the non-fatal shortcut and overrides positive pushback delays

- **Item:** RETRY-2
- **Summary:** In Java hedging, a non-fatal failure without pushback waits for the normal `hedgingDelay` instead of starting the next attempt immediately, and a positive pushback starts the next attempt immediately instead of after the delay.
- **Description:** gRFC A6 and the spec: a non-fatal status starts the next hedged request immediately, shortcutting its hedging delay; a pushback of n ms issues the next hedged request after n ms. In `RetriableStream.makeHedgingDecision`, a positive pushback is set to 0 only when present (`pushbackMillis != null && pushbackMillis > 0` → 0), and `pushbackHedging(null)` returns without rescheduling. Result: no pushback → normal delay; pushback n > 0 → immediate. The condition appears inverted. (C++ and Go do not implement hedging.)
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L1110-L1124 ; https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L445-L452
- **Spec:** Retries and Hedging: Hedging Policy; Retries and Hedging: Server Pushback

### [low] Java: retryThrottling maxTokens above 1000 or non-integer is accepted

- **Item:** RETRY-5
- **Summary:** Java reads `maxTokens` as a double and only checks `> 0`, so values above 1000 and non-integer values are accepted.
- **Description:** gRFC A6 and the spec require `maxTokens` to be a JSON integer in (0, 1000]. Java accepts any positive number.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ServiceConfigUtil.java#L110-L120
- **Spec:** Retries and Hedging: Retry Throttling

### [low] Java: hedgingPolicy without hedgingDelay is rejected

- **Item:** RETRY-5
- **Summary:** Java requires `hedgingDelay` (`checkNotNull(..., "hedgingDelay cannot be empty")`), making a valid config invalid.
- **Description:** gRFC A6 ("`hedgingDelay` is an optional field") and the spec (Required: no) allow omitting `hedgingDelay`. Java treats its absence as an invalid config.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelServiceConfig.java#L388-L392
- **Spec:** Retries and Hedging: Hedging Policy

### [low] Java (Netty): HTTP CONNECT tunnel accepted only on a 200 response

- **Item:** PROXY-3
- **Summary:** grpc-netty delegates CONNECT to Netty's `HttpProxyHandler`, which fails unless the status code is exactly 200, rejecting other 2xx responses. (OkHttp accepts any 2xx.)
- **Description:** RFC 9110 §9.3.6 and the spec: any 2xx establishes the tunnel. Netty's `HttpProxyHandler.handleResponse` throws `HttpProxyConnectException` when `status.code() != 200`. Not verified against a local checkout (Netty source is not present locally; based on upstream Netty 4.1 source as recalled — confirm before filing).
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/ProtocolNegotiators.java#L567-L571 ; Netty `handler-proxy/src/main/java/io/netty/handler/proxy/HttpProxyHandler.java` (`handleResponse`)
- **Spec:** HTTP CONNECT Proxy Support: CONNECT Handshake

### [medium] outlier_detection JSON parser reads `maxEjectionPercentage` and skips range/sign validation

- **Item:** OUTLIER_DETECTION-2
- **Summary:** Java's service-config parser for `outlier_detection_experimental` reads the key `maxEjectionPercentage` instead of `maxEjectionPercent`, so the configured value is silently ignored and 10 is used. It also does not reject `maxEjectionPercent` > 100 or negative `interval`/`baseEjectionTime`/`maxEjectionTime`.
- **Description:** The proto JSON name is `maxEjectionPercent` (used by C++ and Go). gRFC A50 requires values above 100 to be a parse error, and the spec makes negative durations invalid. In Java, a negative interval reaches `scheduleWithFixedDelay` and throws inside `acceptResolvedAddresses`. Fix: read `maxEjectionPercent` (optionally also accept the old key), validate it is at most 100, and reject negative durations. The xDS path builds the config object directly and is unaffected.
- **Evidence:** util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancerProvider.java (parseLoadBalancingPolicyConfig); util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java (acceptResolvedAddresses timer scheduling).
- **Spec:** `outlier_detection` LB Policy: Validation

### [high] outlier_detection config updates postpone the first ejection sweep and reset call counters

- **Item:** OUTLIER_DETECTION-3
- **Summary:** Java records the detection timer start time only when the timer first fires, so every config update before the first sweep restarts a full `interval`. When a timer exists it also resets all call counters on every update.
- **Description:** Per gRFC A50 and the spec, the start time is recorded when the timer is first started, later updates restart the timer for the remaining time, and counters are reset only when the start time was unset. With xDS, every EDS/CDS change pushes a new config to the policy; updates more frequent than `interval` (default 10 s) keep postponing the first sweep, and each update discards collected data, so outlier detection can be silently disabled.
- **Evidence:** util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java (acceptResolvedAddresses: detectionTimerStartNanos handling and resetCallCounters(); DetectionTimer.run sets detectionTimerStartNanos).
- **Spec:** `outlier_detection` LB Policy: Updates from the Parent

### [medium] pick_first Happy Eyeballs and address-family interleaving disabled by default

- **Item:** PICK_FIRST-2
- **Summary:** Java's `pick_first` uses Happy Eyeballs only when `GRPC_PF_USE_HAPPY_EYEBALLS` is set (default false); by default it tries addresses strictly one at a time with no Connection Attempt Delay and no address-family interleaving.
- **Description:** gRFC A61 and the spec require Happy Eyeballs on the pass through the address list (250 ms default Connection Attempt Delay) and RFC 8305 §4 family interleaving. With Java's default, a dead first address costs a full connect timeout instead of 250 ms, and dual-stack backends connect slowly. Sub-item (low): when enabled, Java interleaves only two groups (IPv4 and everything else), so non-IP families are grouped with IPv6 instead of forming their own group in first-appearance order.
- **Evidence:** core/src/main/java/io/grpc/internal/PickFirstLeafLoadBalancer.java (enableHappyEyeballs, scheduleNextConnection, address flattening/interleaving); core/src/main/java/io/grpc/internal/PickFirstLoadBalancerProvider.java (GRPC_PF_USE_HAPPY_EYEBALLS default).
- **Spec:** `pick_first` LB Policy: Happy Eyeballs Connection Algorithm; Address List Processing

### [low] random_subsetting does not forward requestConnection to its child

- **Item:** RANDOM_SUBSETTING-3
- **Summary:** `RandomSubsettingLoadBalancer` does not override `requestConnection()`, so it inherits the no-op from `LoadBalancer` and never forwards ExitIdle to its child.
- **Description:** The spec requires ExitIdle to be forwarded to the child. In Java, `ManagedChannel.getState(true)` calls `lb.requestConnection()`, which does nothing under `random_subsetting`, so an explicit connect request does not leave IDLE. RPCs still connect because Java `pick_first`'s IDLE picker requests a connection itself.
- **Evidence:** util/src/main/java/io/grpc/util/RandomSubsettingLoadBalancer.java (only acceptResolvedAddresses, handleNameResolutionError, shutdown overridden); api/src/main/java/io/grpc/LoadBalancer.java (requestConnection default no-op).
- **Spec:** `random_subsetting` LB Policy: ExitIdle

### [medium] ring_hash hashes a non-canonical address string

- **Item:** RING_HASH-4
- **Summary:** Java places endpoints on the ring by hashing `SocketAddress.toString()` of the first address, e.g. "/10.0.0.1:443" (leading slash; IPv6 in JDK uncompressed form), instead of the canonical `host:port` string.
- **Description:** The spec (following Envoy via gRFC A42) hashes the canonical `host:port` form ("10.0.0.1:443", "[::1]:443"). Java's ring positions therefore differ from C++, Go, and Envoy, so the same request hash selects a different backend, breaking cross-language and Envoy session affinity. Fixing this changes ring positions for existing Java clients once and may need a release note.
- **Evidence:** xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java (ring construction uses getAddresses().get(0).toString()); xds/src/main/java/io/grpc/xds/XdsEndpointResource.java (InetSocketAddress built from EDS).
- **Spec:** `ring_hash` LB Policy: Ring Construction

### [medium] ring_hash does not support the `hash_key` endpoint attribute

- **Item:** RING_HASH-4
- **Summary:** grpc-java has no support for the gRFC A76 `hash_key` endpoint attribute; `ring_hash` always hashes the first address, and EDS `envoy.lb` metadata `hash_key` is never read.
- **Description:** The spec: if `hash_key` is set and non-empty, the endpoint is placed on the ring by hashing it; otherwise the first address is hashed. `cds` sets it from the endpoint's `envoy.lb` metadata. Without it, Java diverges from C++, Go, and Envoy whenever the control plane sets `hash_key`. (Alternatively, the team may choose to record this as a missing feature in the optionality notes.)
- **Evidence:** xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java; xds/src/main/java/io/grpc/xds/XdsEndpointResource.java (no hash_key parsing).
- **Spec:** `ring_hash` LB Policy: Ring Construction; `ring_hash` LB Policy: Other Inputs

### [low] RLS backoff reset on reconnect keeps the entry's backoff sequence

- **Item:** RLS-8
- **Summary:** On control-channel recovery Java cancels only the backoff timer; the `BackoffCacheEntry` keeps its `backoffPolicy`, which the next lookup reuses, so the sequence continues. Java RLS also has no `ResetBackoff` hook.
- **Description:** The spec resets each entry's backoff state (and clears its backoff time) on recovery and on `ResetBackoff`, so the next failure waits the initial delay. Already partly noted in this file under the Java RLS miscellaneous non-conformances; merge there.
- **Evidence:** rls/src/main/java/io/grpc/rls/CachingRlsLbClient.java (control channel state listener; BackoffCacheEntry backoffPolicy reuse).
- **Spec:** `rls` LB Policy: Control Channel; `rls` LB Policy: ResetBackoff

### [medium] Java: per-RPC authority check is not enforced by default

- **Item:** TLS-6
- **Summary:** Java computes the TLS per-RPC authority check but only logs a failure unless `GRPC_ENABLE_PER_RPC_AUTHORITY_CHECK=true` (default false), so RPCs are sent to servers whose certificate does not cover the RPC's authority.
- **Description:** `NettyClientHandler` reads `enablePerRpcAuthorityCheck = GrpcUtil.getFlag("GRPC_ENABLE_PER_RPC_AUTHORITY_CHECK", false)`. When the flag is off, a failed check logs "This will be an error in the future." and the RPC is sent anyway. OkHttp has the same flag. The spec (and A81) say TLS credentials MUST do the check by default and fail the RPC on mismatch. This flag is a temporary rollout guard, but the default is security-relevant.
- **Evidence:** [NettyClientHandler.java L107-L108](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyClientHandler.java#L107-L108), [L683-L700](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyClientHandler.java#L683-L700); OkHttp transport uses the same flag.
- **Spec:** TLS: Per-RPC Authority Verification

### [high] Java: authorization policy translator silently ignores unknown fields

- **Item:** AUTHZ-3
- **Summary:** Java's `AuthorizationPolicyTranslator` never rejects unrecognized fields, so a typo such as `"deny_rule"` or an unimplemented field such as `"audit_logging_options"` is dropped and the policy is accepted with fewer restrictions.
- **Description:** `translate` reads only `name`, `deny_rules`, `allow_rules` and, inside them, only known keys; it never checks for extra keys at any level. A43 calls rejection of policies with unknown fields a security requirement. C++ and Go reject them. Java should also reject `audit_logging_options` until it implements audit logging.
- **Evidence:** [AuthorizationPolicyTranslator.java L165-L198](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/authz/src/main/java/io/grpc/authz/AuthorizationPolicyTranslator.java#L165-L198)
- **Spec:** Authorization: Schema

### [low] Java: outlier detection metrics (A91) not implemented

- **Item:** METRICS-5
- **Summary:** Java's `outlier_detection` policy registers and records neither `grpc.lb.outlier_detection.ejections_enforced` nor `grpc.lb.outlier_detection.ejections_unenforced`.
- **Description:** gRFC A91 (merged) defines two experimental, off-by-default counters recorded when an ejection algorithm detects an outlier. C++ and Go implement them. Java has no reference to them in its sources.
- **Evidence:** grpc-java ed3bf6b7: no `ejections_enforced` anywhere; [OutlierDetectionLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java) has no metric recording.
- **Spec:** Metric Catalog: Outlier Detection LB Policy Metrics; `outlier_detection` LB Policy: Metrics

### [medium] Java: xDS server's XdsClient uses a no-op MetricRecorder

- **Item:** METRICS-8
- **Summary:** `XdsServerWrapper` creates the `#server` XdsClient with `new MetricRecorder() {}`, so xDS-enabled Java servers record no `grpc.xds_client.*` metrics.
- **Description:** A78 defines `grpc.target="#server"` for the server XdsClient's metrics, and the spec says server-scoped non-per-call metrics, including the server XdsClient, are recorded on the server's stats plugins. C++ (`GetStatsPluginsForServer`) and Go (`MetricsRecorderForServer`) do this.
- **Evidence:** [XdsServerWrapper.java L221](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsServerWrapper.java#L221)
- **Spec:** Metrics Framework and OpenTelemetry Plugin: Server Scoping

### [low] Circuit breaker uses the last DEFAULT thresholds entry instead of the first

- **Item:** XDS_CDS-4
- **Summary:** Java loops over all `circuit_breakers.thresholds` entries without stopping, so a later `DEFAULT` entry with `max_requests` overrides the first.
- **Description:** The spec (per A32) says gRPC uses only the first entry whose `priority` is `DEFAULT`. Java does not break after the first DEFAULT entry; the last DEFAULT entry that sets `max_requests` wins. C++ and Go use the first.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L239-L249
- **Spec:** Cluster: Circuit Breakers

### [medium] RouteConfiguration NACKed when a route has a redirect, direct_response, filter_action, or unset action

- **Item:** XDS_ROUTING-5
- **Summary:** Java's `parseRoute` returns an error for unsupported route actions, rejecting the whole RouteConfiguration (or Listener, if inline).
- **Description:** The spec (per A36) accepts such routes and records their action as unsupported; an RPC matching one fails with UNAVAILABLE. Java NACKs the resource ("with unknown action type"), which breaks clients sharing a RouteConfiguration with Envoy-only routes. C++ and Go accept.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L296-L321
- **Spec:** RouteConfiguration: Route

### [medium] Unset RouteMatch.case_sensitive is treated as false (case-insensitive path matching)

- **Item:** XDS_ROUTING-6
- **Summary:** Java reads `case_sensitive` with `getCaseSensitive().getValue()`, which is false when the wrapper is unset.
- **Description:** The spec (per A28, and Envoy's proto default) says `case_sensitive` defaults to true. Java matches `prefix` and `path` case-insensitively unless the control plane explicitly sets `case_sensitive = true`, so it routes differently from C++, Go, and Envoy for every config that leaves the field unset.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L362, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RoutingUtils.java#L160-L172
- **Spec:** RouteConfiguration: RouteMatch

### [medium] xDS retry policy with num_retries = 0 is accepted and makes every RPC on the route fail

- **Item:** XDS_ROUTING-8
- **Summary:** Java accepts `RetryPolicy.num_retries = 0` (maxAttempts 1) instead of rejecting the resource.
- **Description:** The spec (per A44) says `num_retries` MUST NOT be 0 and violations reject the resource. Java accepts it; the generated method config then fails `maxAttempts >= 2` validation in the name resolver, so every RPC on the route fails rather than the resource being NACKed (losing the last good config).
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L527-L559, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelServiceConfig.java#L333-L337, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L489-L500
- **Spec:** RouteConfiguration: Retry Policy

### [low] Duplicate cluster specifier plugin names rejected only among supported plugins

- **Item:** XDS_ROUTING-3
- **Summary:** Java rejects duplicate plugin names only when the plugins are supported; duplicates involving unsupported (`is_optional`) plugins are accepted.
- **Description:** The spec rejects any two `cluster_specifier_plugins` entries with the same `extension.name`.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L152-L163
- **Spec:** RouteConfiguration: Cluster Specifier Plugins

### [low] RLS cluster specifier plugin config is not validated when the RouteConfiguration is parsed

- **Item:** XDS_ROUTING-3
- **Summary:** Java's RLS plugin `parsePlugin` only converts the proto to JSON; the resulting RLS LB config is not validated by the LB policy registry at RDS parse time.
- **Description:** The spec (per the RLS-in-xDS design) requires the converted LB config to be accepted by the LB policy registry when the resource is parsed, and rejects the resource otherwise. In Java an invalid RLS config is accepted and surfaces later as a service config error.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RouteLookupServiceClusterSpecifierPlugin.java#L69-L73
- **Spec:** RouteConfiguration: Cluster Specifier Plugins

### [low] cds LB policy config uses JSON key "is_dynamic" instead of "isDynamic"

- **Item:** XDS_ROUTING-3
- **Summary:** Java generates and parses the cds config field as `is_dynamic` rather than the proto-JSON name `isDynamic`.
- **Description:** `CdsConfig.is_dynamic` (A74, `grpc/service_config/service_config.proto`) maps to JSON `isDynamic` under the standard proto-to-JSON rules used for service config. Java's xDS resolver emits `is_dynamic` and its cds parser reads only `is_dynamic`, so a config using the correct `isDynamic` key is not honored.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L1046-L1047, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/CdsLoadBalancerProvider.java#L88
- **Spec:** `cds` LB Policy: Configuration

### [medium] outlier_detection and xds_cluster_impl run per priority instead of per cluster

- **Item:** XDS_LB-5
- **Summary:** Java's `CdsLoadBalancer2.generatePriorityChildConfigs` builds `priority` → [`outlier_detection` →] `cluster_impl` → LB policy, one per priority, rather than the A75 shape `outlier_detection` → `xds_cluster_impl` → `priority`.
- **Description:** Outlier-detection statistics and ejection limits are computed separately for each priority instead of across the cluster. That changes observable ejection behavior from gRFC A75 and the spec. Aggregate clusters already use a `priority` of `cds` children, which is correct.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/CdsLoadBalancer2.java#L547-L583
- **Spec:** `cds` LB Policy: Position in the xDS LB Policy Tree

### [medium] cds keeps stale endpoints and skips drops when the EDS data is an error or has no usable endpoints

- **Item:** XDS_LB-4
- **Summary:** When the cluster's EndpointConfig holds an error (e.g. the EDS resource was deleted), or no endpoint is usable, Java `CdsLoadBalancer2` calls `handleNameResolutionError(UNAVAILABLE)` on its existing child instead of updating it with a single empty priority.
- **Description:** An existing `priority` child keeps its old addresses and keeps routing RPCs to endpoints the control plane removed. With no child yet, Java reports a TRANSIENT_FAILURE fail picker, and no `cluster_impl` exists, so EDS drops (including drop_all) are not applied. gRFC A37: "it should report a result that is a single priority with no endpoints." C++ and Go do this.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/CdsLoadBalancer2.java#L139-L161, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L360-L368
- **Spec:** `cds` LB Policy: Features (Child Config for a Non-Aggregate Cluster)

### [high] Circuit breaking (max_concurrent_requests) not enforced when the cluster has no LRS server

- **Item:** XDS_LB-7
- **Summary:** Java increments `inFlights` only in `CountingStreamTracerFactory`, and that tracer is attached only when locality stats exist, i.e. only when `lrs_load_reporting_server` is set.
- **Description:** For any cluster without LRS, which is the common case, the counter never increases, so `max_requests` circuit breaking is silently ignored. gRFC A32 does not tie circuit breaking to LRS. C++ and Go count every completed pick.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L438-L455, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L331-L337
- **Spec:** `xds_cluster_impl` LB Policy: Features (Circuit Breaking)

### [low] grpc.lb.locality label set only when load reporting is enabled

- **Item:** XDS_LB-7
- **Summary:** Java calls `addOptionalLabel("grpc.lb.locality", ...)` only in the `stats != null` branch, so the label is missing for clusters without an LRS server.
- **Description:** The spec says the picker sets the label for every completed pick, using the empty string when there is no locality. C++ and Go do this whether or not LRS is configured.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L489-L514
- **Spec:** `xds_cluster_impl` LB Policy: Picker Labels

### [low] Any unparseable fault abort header disables the header-controlled abort

- **Item:** XDS_FAULT-1
- **Summary:** Java `FaultFilter.determineFaultAbortStatus` parses all three abort headers in one try block and returns null (no abort) on any `NumberFormatException`.
- **Description:** The spec (A33: "the invalid headers will be ignored") says only the invalid header is ignored. In Java, an invalid percentage header or an invalid HTTP header stops a valid abort header from applying, and an invalid gRPC header stops a valid HTTP header from applying.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/FaultFilter.java#L351-L377
- **Spec:** xDS HTTP Filters: Header-Controlled Faults

### [medium] CertificateValidationContext NACK checks skipped when system_root_certs is used (SPKI/hash pinning ignored)

- **Item:** XDS_SECURITY-4
- **Summary:** Java runs the NACK checks for `verify_certificate_spki`, `verify_certificate_hash`, `require_signed_certificate_timestamp`, `crl`, and `custom_validator_config` only inside the `ca_certificate_provider_instance` branch of `validateCommonTlsContext`.
- **Description:** A client using `system_root_certs`, or a server with no CA instance, accepts these fields and silently ignores them. So certificate pinning that the control plane asked for is not enforced. gRFC A29: "If any of the other fields (listed below) are present, the update is NACKed because ignoring these fields compromises security". C++ and Go run the checks regardless of the CA source.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L481-L531
- **Spec:** xDS Security: `CommonTlsContext` Validation

### [low] UpstreamTlsContext sni length not validated

- **Item:** XDS_SECURITY-4
- **Summary:** Java never NACKs an `sni` longer than 255 characters.
- **Description:** The spec NACKs `sni` longer than 255 characters, and C++ and Go do too. Java accepts it.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L481-L531
- **Spec:** xDS Security: `CommonTlsContext` Validation

### [low] require_signed_certificate_timestamp=false is NACKed

- **Item:** XDS_SECURITY-4
- **Summary:** Java NACKs whenever `require_signed_certificate_timestamp` is present (`hasRequireSignedCertificateTimestamp`), even when it is explicitly false.
- **Description:** The spec NACKs only when the value is true. C++ and Go check the value.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L481-L531
- **Spec:** xDS Security: `CommonTlsContext` Validation

### [medium] Top-level ORCA utilization reported as named load_metric_stats instead of UpstreamLocalityStats fields, and zero values not counted

- **Item:** XDS_LRS-3
- **Summary:** Java `LoadStatsManager2.recordTopLevelMetrics` stores propagated cpu/mem/application utilization in the named-metric map, and only when the value is > 0. `LoadReportClient.buildClusterStats` fills only `load_metric_stats`.
- **Description:** gRFC A85: these values "will be propagated to the new LRS fields of the same names in the `UpstreamLocalityStats` message." A control plane that reads the dedicated fields sees no utilization from Java clients, and skipping zero values undercounts `num_requests_finished_with_metric`. C++ and Go fill the dedicated fields.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/LoadStatsManager2.java#L417-L428, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/LoadReportClient.java#L337-L358
- **Spec:** Load Reporting (LRS): Locality stats

### [low] RLS lookupService is not checked for a registered resolver scheme

- **Item:** RLS design-doc comparison
- **Summary:** `lookupService` is validated only as URI syntax, so an unknown scheme is accepted when the config is parsed and fails later, when the control channel is created.
- **Description:** The spec requires `lookupService` to be a valid target URI whose scheme has a registered resolver, and an invalid value makes the config invalid. Java checks only `new URI(lookupService)`.
- **Evidence:** grpc-java `rls/src/main/java/io/grpc/rls/RlsProtoConverters.java` (lookupService parsing).
- **Spec:** rls: Configuration

### [low] RLS duration and cacheSizeBytes handling differs from the spec

- **Item:** RLS-1
- **Summary:** Java rejects `lookupServiceTimeout: 0s`, keeps `maxAge: 0s` as zero, accepts negative `maxAge`/`staleAge`, and treats a missing `cacheSizeBytes` as 5 MiB.
- **Description:** The spec says zero or unset durations mean the default, negative durations make the config invalid, and `cacheSizeBytes` is required.
  - `checkArgument(timeout > 0)` rejects an explicit zero timeout. Proto3 JSON from xDS omits zero values, so this only affects hand-written configs.
  - `maxAge` of zero is kept, so responses are never valid.
  - Negative ages are not checked.
  - A missing `cacheSizeBytes` falls back to `MAX_CACHE_SIZE` instead of being rejected.
- **Evidence:** grpc-java `rls/src/main/java/io/grpc/rls/RlsProtoConverters.java` `RouteLookupConfigConverter.doForward` (timeout, `maxAge`/`staleAge`, `cacheSizeBytes` handling).
- **Spec:** `rls` LB Policy: Configuration; Validation

### [low] RLS uses an empty extraKeys name as a key

- **Item:** RLS-2
- **Summary:** An `extraKeys` entry set to `""` adds a key named `""` to the key map instead of being treated as unset.
- **Description:** The converter passes the raw `extraKeys` strings through, and `RlsRequestFactory` adds the value whenever the name is non-null. So `"host": ""` sends the host under an empty key name. The spec (and the `ExtraKeys` proto comment: "If a key name is empty, no key will be set for that value") says an empty name means the value is not added.
- **Evidence:** grpc-java `rls/src/main/java/io/grpc/rls/RlsProtoConverters.java` (`ExtraKeys.create(rawExtraKeys.get(...))`); `RlsRequestFactory.java` `createRequestHeaders` (`if (extraKeys.host() != null)` etc.).
- **Spec:** `rls` LB Policy: Configuration

### [low] RLS host key value strips the port

- **Item:** RLS-3
- **Summary:** The value added for `extraKeys.host` is the channel's authority with any port removed. The spec uses the default authority as-is.
- **Description:** For an authority like `example.com:8443`, Java sends `example.com`, while C++ (and the spec) send `example.com:8443`. The lookup server then sees different keys from different languages and can route them differently.
- **Evidence:** grpc-java `rls/src/main/java/io/grpc/rls/CachingRlsLbClient.java` constructor (`serverHost = new URI(null, helper.getAuthority(), null, null, null).getHost()`, passed to `new RlsRequestFactory`).
- **Spec:** `rls` LB Policy: Key Building

### [low] Server cardinality violation resets stream with CANCEL instead of sending INTERNAL trailers

- **Item:** SERVER-4
- **Summary:** When a unary/client-streaming handler completes OK without a response, or sends a second response, the Java server detects it as `INTERNAL` but resets the stream with `RST_STREAM(CANCEL)`, so the client sees `CANCELLED`.
- **Description:** `ServerCallImpl` detects "Completed without a response" and "Too many responses" and builds an `INTERNAL` status, but `handleInternalError` calls `stream.cancel(status)`, which on HTTP/2 sends `RST_STREAM(CANCEL)`; the `INTERNAL` status never reaches the client, which reports `CANCELLED` (a status that hides the server bug and can be misread as a client-initiated cancellation). The spec says the server SHOULD fail the RPC by sending Trailers with status `INTERNAL`.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/ServerCallImpl.java`: `sendMessage` (~L164, `TOO_MANY_RESPONSES`), `closeInternal` (~L225, `MISSING_RESPONSE`), `handleInternalError` (~L283-291, `stream.cancel(status)`).
- **Spec:** Server: Status and Trailers; Core RPC Semantics: Unary Calls

### [medium] Per-RPC authority mismatch fails with UNAVAILABLE instead of UNAUTHENTICATED

- **Item:** TLS-2
- **Summary:** When an RPC's authority does not match the server certificate, Java fails the RPC with `UNAVAILABLE` instead of `UNAUTHENTICATED`. This applies only when `GRPC_ENABLE_PER_RPC_AUTHORITY_CHECK=true`; by default the check is not enforced (a warning is logged and the RPC is sent), which is tracked separately as open item TLS-6.
- **Description:** The per-RPC authority check (authority override / xDS authority rewrite) is an authentication failure, not a transient one. `UNAVAILABLE` is retryable (including transparent/configured retries and wait-for-ready style handling), so the call may be retried pointlessly against the same server. The spec requires `UNAUTHENTICATED`.
- **Evidence:** grpc-java `netty/src/main/java/io/grpc/netty/X509AuthorityVerifier.java` / `NettyClientHandler` (authority verification failure status); `okhttp/src/main/java/io/grpc/okhttp/OkHttpClientTransport.java` (`verifyAuthority`).
- **Spec:** TLS: Per-RPC Authority Verification

### [low] dns resolver returns the TXT service config when the address lookup fails

- **Item:** DNS-1
- **Summary:** When the A/AAAA lookup fails or is empty, Java's DNS resolver puts the `UNAVAILABLE` error only in the addresses and still looks up and returns the TXT service config.
- **Description:** The visible outcome before the first success is still TRANSIENT_FAILURE, but the service config field holds a (possibly valid, possibly invalid) config instead of the error, which can interact with the "keep the last valid service config" logic differently from other implementations. The spec requires both fields to hold an `UNAVAILABLE` error naming the host.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/DnsNameResolver.java` (`doResolve` / `Resolve.run`: address error set on the result while the TXT config is still resolved and attached).
- **Spec:** Name Resolution: `dns`

### [medium] Java records a synthetic attempt for calls that fail before any attempt is created

- **Item:** METRICS-1
- **Summary:** Java increments `grpc.client.attempt.started` at call creation and records a synthetic attempt at call end when no stream was ever created.
- **Description:** When a call fails before any attempt is created (for example, a non-wait-for-ready call failing because the resolver reports an error), the spec says no attempt events are generated and only call-level metrics are recorded. Java increments `grpc.client.attempt.started` when the call is created and, if no stream was created, records `grpc.client.attempt.duration` (elapsed call time), attempt message sizes of 0, and the call's status as a synthetic attempt. This inflates attempt counts and skews attempt-duration histograms. Fixing it changes Java's metric values (release note advisable).
- **Evidence:** grpc-java `opentelemetry/src/main/java/io/grpc/opentelemetry/OpenTelemetryMetricsModule.java` (`CallAttemptsTracerFactory` constructor; `recordFinishedCall`, `attemptsPerCall.get() == 0` branch)
- **Spec:** Instrumentation Architecture: Call-Attempt Tracer Event Points

### [low] Java has no generic method attribute predicate for metrics

- **Item:** METRICS-2
- **Summary:** Java's OpenTelemetry plugin provides no predicate to record generic (unregistered) method names verbatim.
- **Description:** The spec requires the plugin to let the application set a generic method attribute predicate, on both client and server, consulted only for generic methods. Java records `"other"` unless `MethodDescriptor.isSampledToLocalTracing()` is true (set per method by generated code); there is no application-supplied predicate over generic method names.
- **Evidence:** grpc-java `opentelemetry/src/main/java/io/grpc/opentelemetry/OpenTelemetryMetricsModule.java` (method-name recording via `isSampledToLocalTracing`); `GrpcOpenTelemetry.Builder` (no predicate setter)
- **Spec:** Metrics Framework and OpenTelemetry Plugin: Generic Method Names

### [low] Java records grpc.client.call.retry_delay for calls with no retries

- **Item:** METRICS-3
- **Summary:** Java always records `grpc.client.call.retry_delay` at call end, including 0 for calls with no retries or hedges.
- **Description:** The spec says `grpc.client.call.retry_delay` is not recorded unless the call made at least one retry or hedged attempt. Java records it unconditionally at call end, filling the histogram with 0 values for every call that had no retries.
- **Evidence:** grpc-java `opentelemetry/src/main/java/io/grpc/opentelemetry/OpenTelemetryMetricsModule.java` (`recordFinishedCall`, `clientCallRetryDelayCounter().record(...)` with no retry check)
- **Spec:** Metric Catalog: Retry Metrics

### [medium] Java subchannel metrics use the raw target string for grpc.target

- **Item:** METRICS-4
- **Summary:** Java labels subchannel metrics with the raw target string passed to the channel builder instead of the canonical target URI.
- **Description:** The spec requires `grpc.target` on `grpc.subchannel.*` metrics to be the creating channel's canonical target URI (scheme included), the same value as per-call metrics, so subchannel and call metrics can be joined. Java uses the raw builder target string.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/InternalSubchannel.java` (`target` used for metric labels), `ManagedChannelImpl` (target passed to subchannels)
- **Spec:** Metric Catalog: Subchannel Metrics

### [low] Java client records inbound message trace events on the call span

- **Item:** TRACING-1
- **Summary:** On the client, Java adds the "Inbound message" event to the call span rather than the attempt span.
- **Description:** The spec says message events are recorded on the client attempt span and on the server span, never on the client call span. Java's client emits the inbound "Inbound message" event (the uncompressed-size half of its split inbound events) on the call span, so the inbound compressed and uncompressed events end up on different spans.
- **Evidence:** grpc-java `opentelemetry/src/main/java/io/grpc/opentelemetry/OpenTelemetryTracingModule.java` (client inbound message handling)
- **Spec:** Tracing: Message Events

### [medium] Java binary logging reads GRPC_BINARY_LOG_CONFIG and requires code to enable

- **Item:** BINARY_LOG-2
- **Summary:** Java reads `GRPC_BINARY_LOG_CONFIG` instead of `GRPC_BINARY_LOG_FILTER`, and only after the application installs a binary log in code.
- **Description:** The spec requires binary logging to be enabled through the `GRPC_BINARY_LOG_FILTER` environment variable without code changes. Java reads `GRPC_BINARY_LOG_CONFIG` (matching its vendored copy of binarylog.proto, not the canonical grpc-proto file), and only when the application calls `BinaryLogs.createBinaryLog()` and installs it on a channel/server builder. Java should also accept `GRPC_BINARY_LOG_FILTER` and enable logging without code changes. (Its malformed-string handling — throwing at creation — conforms.)
- **Evidence:** grpc-java `services/src/main/java/io/grpc/protobuf/services/BinaryLogProviderImpl.java`, `BinlogHelper.FactoryImpl`, `services/src/main/proto/grpc/binlog/v1/binarylog.proto` (comment says GRPC_BINARY_LOG_CONFIG)
- **Spec:** Binary Logging: Enabling Binary Logging

### [high] Java server-side binary logs include the authorization header

- **Item:** BINARY_LOG-3
- **Summary:** Java's server-side binary log records the `authorization` header, leaking bearer tokens into logs.
- **Description:** The spec (and the binarylog.proto `Metadata` comment) requires the server side to exclude the `authorization` header from logged metadata. Java's BinlogHelper only excludes `grpc-status-details-bin` (and other internal keys), so server-side `EVENT_TYPE_CLIENT_HEADER` entries contain credentials.
- **Evidence:** grpc-java `services/src/main/java/io/grpc/protobuf/services/BinlogHelper.java` (`createMetadataProto`, excluded-key set)
- **Spec:** Binary Logging: Metadata

### [low] Empty authority client_listener_resource_name_template rejects the bootstrap

- **Item:** XDS_BOOTSTRAP-3
- **Summary:** Java treats `"client_listener_resource_name_template": ""` in an authority as a non-empty value, so it fails the prefix check and the bootstrap is rejected.
- **Description:** An empty template is the same as an unset one and means the default `xdstp://<authority_name>/envoy.config.listener.v3.Listener/%s`. Java uses the default only when the field is absent. With `""`, the `xdstp://<authority_name>/` prefix check fails. Go and C++ treat `""` as unset.
- **Evidence:** xds/src/main/java/io/grpc/xds/client/BootstrapperImpl.java (authority parsing)
- **Spec:** xDS Bootstrap: Authority Object

### [medium] EDS endpoint weight 0 is accepted as 1 instead of rejecting the resource

- **Item:** XDS_EDS-1
- **Summary:** Java treats an explicit `LbEndpoint.load_balancing_weight` of 0 as 1 and ACKs the resource. Go and C++ NACK it.
- **Description:** An unset endpoint weight defaults to 1, and an explicit 0 rejects the EDS resource (Envoy also validates `gte: 1`). Java maps 0 to 1, so it ACKs resources that the other languages NACK.
- **Evidence:** xds/src/main/java/io/grpc/xds/Endpoints.java `LbEndpoint.create`; xds/src/main/java/io/grpc/xds/XdsEndpointResource.java
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: Endpoint Weight

### [medium] EDS resources with duplicate endpoint addresses are not rejected

- **Item:** XDS_EDS-3
- **Summary:** Java has no duplicate-address check for EDS, so it ACKs resources that Go and C++ NACK.
- **Description:** Every address (`address` and `additional_addresses`) of every endpoint that was not ignored MUST be unique within the ClusterLoadAssignment, across all localities and priorities. A duplicate rejects the resource. Java never checks this.
- **Evidence:** xds/src/main/java/io/grpc/xds/XdsEndpointResource.java
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: Duplicate Addresses

### [medium] ring_hash does not treat an endpoint weight of 0 as 1

- **Item:** RING_HASH-WEIGHT-0
- **Summary:** An endpoint weight of 0 from a non-xDS resolver is used as-is, making the minimum normalized weight 0.
- **Description:** RingHashLoadBalancer defaults a missing weight to 1 but uses an explicit 0. The ring-size scale computation divides by the minimum normalized weight, so a 0 weight breaks ring construction. C++ and Go treat 0 as 1, and the spec requires that.
- **Evidence:** `xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java` L116–133.
- **Spec:** ring_hash: Validation

### [high] pick_first drops working connections on a resolver error

- **Item:** R30
- **Summary:** On a resolver error after a good result, pick_first shuts down all subchannels and reports TRANSIENT_FAILURE, even with a READY connection.
- **Description:** Java's pick_first handleNameResolutionError shuts down every subchannel and moves to TRANSIENT_FAILURE no matter what state it is in. The spec says that once an endpoint list has been accepted, the policy SHOULD keep using it and its connections, and SHOULD NOT close working connections or report TRANSIENT_FAILURE because of the error. As a result, a transient DNS failure causes an outage of otherwise healthy channels.
- **Evidence:** grpc-java `core/.../PickFirstLeafLoadBalancer.handleNameResolutionError` and `PickFirstLoadBalancer.handleNameResolutionError`.
- **Spec:** 04-client-channel/06-load-balancing.md, Endpoint Errors

### [high] unix: default authority is the socket path instead of localhost

- **Item:** R39
- **Summary:** The `unix` resolver's default authority is the socket path instead of `localhost`.
- **Description:** Java uses the path as the default authority for `unix:` targets. The spec requires `localhost`. The `:authority` header and TLS server name therefore differ from other languages, which can break servers or proxies that route or verify on authority. This is a behavior change and needs care when rolled out.
- **Evidence:** grpc-java unix domain socket name resolver (default authority); see findings for R39.
- **Spec:** Name Resolution, `unix` (Built-in Resolvers)

### [high] Negative method-config timeout is accepted and applied

- **Item:** R48
- **Summary:** Java accepts a negative `timeout` in a `methodConfig` and applies it, so every matching RPC fails right away with `DEADLINE_EXCEEDED`.
- **Description:** `JsonUtil.parseDuration` accepts negative durations, and `ClientCallImpl.applyMethodConfig` applies them as a deadline that has already expired. The spec says a negative timeout makes the service config invalid, so the channel keeps its previous config or reports the error. One bad config entry (which may come from DNS) can make every matching RPC fail.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/JsonUtil.java` (`parseDuration`), `ClientCallImpl.applyMethodConfig`.
- **Spec:** Service Config (`04-client-channel/04-service-config.md`), "`methodConfig`" field table (`timeout`).

### [high] cds policy queues wait_for_ready RPCs for a cluster in error instead of dropping them

- **Item:** R109
- **Summary:** When its cluster's XdsConfig entry is an error, the cds policy reports an ordinary TRANSIENT_FAILURE picker, so wait_for_ready RPCs queue instead of failing with UNAVAILABLE.
- **Description:** `CdsLoadBalancer2` reports `FixedResultPicker(PickResult.withError(...))`, which the channel treats as Queue for wait_for_ready RPCs. The spec (and A31) require a Drop result so the RPC fails with UNAVAILABLE even if wait_for_ready. Because the resolver's cluster reference is released only when the call closes (`XdsNameResolver` `releaseCluster` in `onClose`), a queued RPC keeps the deleted cluster (and its CDS subscription) in the cluster manager config indefinitely, and the RPC hangs until its deadline even after routes stop naming the cluster.
- **Evidence:** grpc-java `xds/src/main/java/io/grpc/xds/CdsLoadBalancer2.java` (lines ~207, ~228 `PickResult.withError`); `XdsNameResolver.java` `retainCluster`/`releaseCluster` (release in `onClose`).
- **Spec:** 09-xds/lb-policies/cds.md, "Update handling"; 09-xds/05-client.md, "Cluster references and two-phase removal"

### [high] ring_hash rejects updates containing duplicate addresses

- **Item:** RING_HASH-1
- **Summary:** ring_hash fails the whole update with UNAVAILABLE if any address appears more than once, even across different endpoints.
- **Description:** The spec requires endpoints with the same address set to be merged with their weights summed, and duplicates MUST NOT cause the update to be rejected (consistent with A42/A48/A61). Java's `validateNoDuplicateAddresses` rejects the update, turning a benign duplicate (e.g. from a non-xDS resolver or an aggregate cluster) into an outage; its weight-summing code is unreachable.
- **Evidence:** `xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java` `validateNoDuplicateAddresses`.
- **Spec:** 04-client-channel/lb-policies/ring_hash.md, "Updates and Endpoint Management"

### [high] LOGICAL_DNS cluster loses all endpoints on a DNS error after an earlier success

- **Item:** XDS_RESOLVER-1
- **Summary:** Any DNS error for a LOGICAL_DNS cluster replaces the cluster's data with the error, dropping previously resolved addresses.
- **Description:** When DNS resolution for a LOGICAL_DNS cluster fails, Java replaces the cluster's endpoint data with the error even if an earlier resolution succeeded, so the cluster has no endpoints. The spec (and gRFC A37) require keeping the previous endpoints when a previous result exists, using an empty list only when there is none, and setting the resolution note to the DNS error. A single transient DNS failure causes an avoidable outage for the cluster.
- **Evidence:** grpc-java `xds/src/main/java/io/grpc/xds/XdsDependencyManager.java` `DnsWatcher.onResult2`.
- **Spec:** `09-xds/05-client.md`, "LOGICAL_DNS clusters"

### [high] Outlier detection: failure-percentage ejection enabled when enforcing_failure_percentage is unset

- **Item:** XDS_CDS-1
- **Summary:** Java enables failure-percentage ejection at 100% enforcement when `enforcing_failure_percentage` is unset; it should be disabled.
- **Description:** The spec (gRFC A50, Envoy defaults) disables failure-percentage ejection when `enforcing_failure_percentage` is unset or 0. Java disables it only when the field is explicitly 0, so an unset field enables the algorithm with `enforcementPercentage` 100. Clusters with outlier detection configured silently get failure-percentage ejection that the control plane did not ask for.
- **Evidence:** grpc-java `xds/src/main/java/io/grpc/xds/EnvoyServerProtoData.java` `OutlierDetection.fromEnvoyOutlierDetection`.
- **Spec:** `09-xds/04-resources/04-cluster.md`, "Outlier Detection"

### [high] RingHash LB policy extension: DEFAULT_HASH hash_function rejected

- **Item:** RING_HASH-2
- **Summary:** Java accepts only `XX_HASH` in the `RingHash` LB policy extension, so configs that leave `hash_function` at its default (`DEFAULT_HASH`) are NACKed.
- **Description:** In `envoy.extensions.load_balancing_policies.ring_hash.v3.RingHash`, enum value 0 is `DEFAULT_HASH`, which means xxHash. The spec (and updated gRFC A52) require accepting `XX_HASH` or `DEFAULT_HASH`. Java fails the conversion for `DEFAULT_HASH`, so a common control-plane config that leaves the field unset causes the Cluster to be rejected.
- **Evidence:** grpc-java `xds/src/main/java/io/grpc/xds/LoadBalancerConfigFactory.java` RingHash conversion.
- **Spec:** `09-xds/06-lb-policies.md`, "`load_balancing_policy`"

### [high] Malformed per-call ORCA report throws an uncaught exception

- **Item:** incidental (investigation of old item 49; see open item on malformed reports)
- **Summary:** An `endpoint-load-metrics-bin` value that does not parse as `OrcaLoadReport` throws `IllegalArgumentException` from the ORCA stream tracer.
- **Description:** The exception is not caught. By code reading it most likely becomes a connection-level error that fails every RPC on the connection (not tested). A single bad trailer from one backend should at most be ignored, as Go and C++ do.
- **Evidence:** `xds/.../orca/OrcaPerRequestUtil.java` (tracer parsing the trailer); findings G5.
- **Spec:** Client-Side Backend Metrics (ORCA): Report Representation

### [medium] Servers never set TCP_USER_TIMEOUT

- **Item:** R7
- **Summary:** Java servers do not set TCP_USER_TIMEOUT to KEEPALIVE_TIMEOUT when keepalive is enabled (which is the default).
- **Description:** The spec requires clients and servers to set TCP_USER_TIMEOUT to KEEPALIVE_TIMEOUT (20s by default) when keepalive is enabled, on platforms that support it. Java sets it only on Netty epoll client channels with keepalive enabled, and never on servers. As a result, Java servers take much longer to detect dead peers when sent data goes unacknowledged.
- **Evidence:** grpc-java `NettyClientTransport` sets it (epoll only); `NettyServer` / `NettyServerTransport` do not.
- **Spec:** 03-wire-protocol/02-http2-transport.md "TCP_USER_TIMEOUT"

### [medium] Netty client maps RST_STREAM(NO_ERROR) before trailers to UNAVAILABLE

- **Item:** R12
- **Summary:** grpc-java's Netty transport reports UNAVAILABLE for RST_STREAM(NO_ERROR) received before trailers; the spec requires INTERNAL and forbids a retryable code.
- **Description:** When the server resets a stream with NO_ERROR before sending complete trailers, Netty reports UNAVAILABLE (OkHttp correctly reports INTERNAL). UNAVAILABLE is retryable by retry policies and commonly by applications, but the server may already have processed the call, so retrying can duplicate non-idempotent work. The spec maps NO_ERROR to INTERNAL, as Go and C++ do.
- **Evidence:** grpc-java netty NettyClientHandler / Utils status mapping for RST_STREAM (NO_ERROR -> UNAVAILABLE); okhttp maps to INTERNAL.
- **Spec:** gRPC over HTTP/2 (03-wire-protocol/01-http2.md), "RST_STREAM"

### [medium] ring_hash validates ring sizes after clamping to the local cap

- **Item:** R23
- **Summary:** Ring sizes above 8388608 are clamped rather than rejected, and the min ≤ max check runs after clamping.
- **Description:** Java clamps `minRingSize`/`maxRingSize` to its local cap before validation. So values above 8388608 aren't rejected, and a config with min > max (e.g. min=5000, max=4500) can pass once both are clamped. The spec requires validating the configured values before the local cap so that all clients accept and reject the same configs.
- **Evidence:** grpc-java `xds/.../RingHashLoadBalancerProvider` parseLoadBalancingPolicyConfig.
- **Spec:** 04-client-channel/lb-policies/ring_hash.md, Configuration

### [medium] weighted_target IDLE picker does not trigger ExitIdle

- **Item:** R29
- **Summary:** In aggregate IDLE, the picker queues picks but never asks IDLE children to exit idle.
- **Description:** When weighted_target's aggregate state is IDLE, Java uses a FixedResultPicker with no result (queue) and doesn't override requestConnection, so IDLE children are never told to connect. The spec says the IDLE picker MUST schedule the policy's ExitIdle, which forwards to all children. With a child that stays IDLE until asked (e.g. pick_first), queued RPCs can hang indefinitely.
- **Evidence:** grpc-java `xds/.../WeightedTargetLoadBalancer` (updateOverallBalancingState, no requestConnection override).
- **Spec:** 04-client-channel/lb-policies/weighted_target.md, Picker

### [medium] MultiChildLoadBalancer reports TRANSIENT_FAILURE on a resolver error when not READY

- **Item:** R30
- **Summary:** On a resolver error, round_robin and other MultiChildLoadBalancer policies keep their children but report TRANSIENT_FAILURE whenever they aren't READY.
- **Description:** When it receives a resolver error after a good result, Java's MultiChildLoadBalancer keeps its children but replaces its state with TRANSIENT_FAILURE carrying the error unless it is READY. That makes CONNECTING or IDLE channels fail RPCs that would otherwise have waited for a connection. The spec says to keep using the previous list and not report TRANSIENT_FAILURE because of the error.
- **Evidence:** grpc-java `util/.../MultiChildLoadBalancer.handleNameResolutionError`.
- **Note:** Related (spec audit, lbpolb group): Java's `MultiChildLoadBalancer` handles an empty address list by calling `handleNameResolutionError`, which keeps READY and the old endpoints, and Java `ring_hash` does the same through `validateAddrList` ([RingHashLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java#L249-L255)). The spec (e.g. `ring_hash` 3.3) says an empty endpoint list causes TRANSIENT_FAILURE. Fix together.
- **Spec:** 04-client-channel/06-load-balancing.md, Endpoint Errors

### [medium] dns resolver default port depends on transport security instead of always 443

- **Item:** R34
- **Summary:** A `dns:` target without a port uses the transport's default port (80 for plaintext, 443 for TLS) instead of always 443.
- **Description:** Java fills in the default port from the channel builder's transport (80 plaintext / 443 TLS). The spec requires the `dns` resolver to default to port 443 regardless of channel security. A plaintext client targeting `dns:///host` connects to port 80 in Java but 443 elsewhere, so the same target string reaches different servers across languages. Changing this is a compatibility risk and may need an opt-in.
- **Evidence:** grpc-java `NettyChannelBuilder`, `OkHttpChannelBuilder` (default port selection); `DnsNameResolver`.
- **Spec:** Name Resolution, `dns` (Built-in Resolvers)

### [medium] dns resolver drops early re-resolution requests instead of delaying them

- **Item:** R36
- **Summary:** `refresh()` is dropped when the last success is within `networkaddress.cache.ttl`, rather than being delayed until the minimum interval has passed.
- **Description:** Java has no minimum time between resolutions as such; a re-resolution request that arrives within the cache TTL (30s default) of the last success is ignored. The spec requires the `dns` resolver to enforce a minimum interval (default 30s, configurable per channel or process-wide) and to delay early requests until it has passed, not drop them. Dropping means a re-resolution request triggered by connection failures may never produce a fresh lookup until another request arrives, delaying recovery after address changes. There is also no gRPC-level way to configure the interval.
- **Evidence:** grpc-java `DnsNameResolver` (refresh / cache TTL check against `networkaddress.cache.ttl`).
- **Spec:** Name Resolution, `dns` (Built-in Resolvers), Re-resolution

### [medium] DNS TXT: choices from multiple grpc_config records pooled

- **Item:** R37
- **Summary:** The dns resolver pools the choices of every `grpc_config=` TXT record into one list instead of using only the first matching record.
- **Description:** Java parses every TXT record with the prefix and concatenates their choice arrays. The spec requires using only the first record with the `grpc_config=` prefix and ignoring later ones. When several such records exist, Java may select a choice from a later record that other implementations ignore, so clients in different languages pick different configs.
- **Evidence:** grpc-java `DnsNameResolver.parseTxtResults`.
- **Spec:** Name Resolution, Service Config in DNS, TXT Record Format

### [medium] Retry throttling counts response headers as success instead of an OK status

- **Item:** R43
- **Summary:** Java adds a throttle token when the committed attempt receives response headers, whatever the final status, and does not count a Trailers-Only OK.
- **Description:** `RetriableStream.Sublistener.headersRead` calls the throttle's success hook when headers arrive, so RPCs that later fail still count as successes, and Trailers-Only OK responses never count. The spec says a success is an attempt that finishes with status OK, for any RPC on the channel. Throttling may then recover too fast against a failing server, and it under-credits servers that reply with Trailers-Only OK.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/RetriableStream.java` (`Sublistener.headersRead`).
- **Spec:** Retries and Hedging (`04-client-channel/11-retries.md`), "Token Accounting".

### [medium] Disabling retries also disables transparent retries

- **Item:** R45
- **Summary:** `disableRetry()` bypasses `RetriableStream`, so transparent retries stop too, but the spec says they SHOULD continue.
- **Description:** With retries disabled on the channel, Java creates streams without the retry layer, so failures that never reached the server application (for example `REFUSED_STREAM` or a stream above a GOAWAY's last-stream-id) go straight to the application. The spec says transparent retries SHOULD still happen when retries are disabled, because they are safe and avoid spurious errors. Applications or wrapper libraries that disable retries to avoid duplicating configured retries see extra `UNAVAILABLE` errors, for example during server graceful shutdown.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/ManagedChannelImpl.java` (`ChannelStreamProvider`); grpc-java#7947.
- **Spec:** Retries and Hedging (`04-client-channel/11-retries.md`), "Transparent Retries" and "Limits and Disabling Retries".

### [medium] Custom call credentials cannot declare a minimum security level

- **Item:** R126
- **Summary:** Java's `CallCredentials` API has no way to declare a minimum security level, so custom call credentials default to no check instead of `PRIVACY_AND_INTEGRITY`.
- **Description:** In Java, a custom `CallCredentials` must itself call `allowedSecurityLevel(requestInfo, minSecurity)` (or inspect `RequestInfo.getSecurityLevel()`) inside `applyRequestMetadata`; gRPC performs no check before invoking it. The spec requires application-defined call credentials to be able to declare a minimum level, with a default of `PRIVACY_AND_INTEGRITY` when none is declared, and requires gRPC to skip invoking the credential and fail the RPC with `UNAUTHENTICATED` when the connection's level is too low. As a result, custom credentials that forget the check can send bearer tokens over insecure connections. Fixing this needs an API addition (e.g. a declared minimum level checked by the channel) and has a compatibility risk for existing credentials that rely on running on insecure connections.
- **Evidence:** grpc-java `api/src/main/java/io/grpc/CallCredentials.java` (`allowedSecurityLevel`, `RequestInfo.getSecurityLevel`); `core/src/main/java/io/grpc/internal/CallCredentialsApplyingTransportFactory.java` (no pre-invocation check); `auth/src/main/java/io/grpc/auth/GoogleAuthLibraryCallCredentials.java` (checks inside the credential).
- **Spec:** 06-security/README.md, Call Credential Minimum Security Level

### [medium] RLS ignores config updates other than lookupService

- **Item:** R133
- **Summary:** `RlsLoadBalancer.acceptResolvedAddresses` stores a changed config but applies it only if `lookupService` changed.
- **Description:**
  - If `lookupService` changed, the whole client is rebuilt, which flushes the cache.
  - Changes to the following are never applied: `cacheSizeBytes`, key builders, `maxAge`/`staleAge`, `childPolicy`, `defaultTarget`, and `routeLookupChannelServiceConfig` (TODO in the code).

  An xDS RLS plugin update that changes key builders or the default target therefore has no effect until the lookup service changes. The spec requires the new config to be applied, with a cache resize when the size changes.
- **Evidence:** `rls/src/main/java/io/grpc/rls/RlsLoadBalancer.java` `acceptResolvedAddresses` (lines ~51-84). `LinkedHashLruCache.resize` is unused.
- **Spec:** `04-client-channel/lb-policies/rls.md`, "Cache" (Config updates)

### [medium] RLS failed stale refresh discards valid data

- **Item:** R133
- **Summary:** A failed STALE refresh replaces a still-valid data entry with a backoff entry.
- **Description:** A key holds either a data entry or a backoff entry, never both. When a background refresh fails, `createBackOffEntry` replaces the data entry. Picks then use the default target or fail, even though the data has not expired. A throttled lookup creates a backoff entry the same way. The spec keeps valid data usable until it expires.
- **Evidence:** `rls/src/main/java/io/grpc/rls/CachingRlsLbClient.java` `createBackOffEntry`, `cacheAndClean`, `asyncRlsCall` (throttled branch).
- **Spec:** `04-client-channel/lb-policies/rls.md`, "Cache" and "Adaptive Throttling"

### [medium] RLS key-collision validation is ineffective and fails at pick time

- **Item:** R133
- **Summary:** The uniqueness check for `extraKeys` adds a formatted string instead of the key names, so a collision between an extra key and a header or constant key gets through parsing.
- **Description:** Because the check never sees the real extra-key names, a collision is not detected when the config is parsed. At pick time, `ImmutableMap.Builder.buildOrThrow` throws `IllegalArgumentException`. The check also wrongly rejects header and constant keys named "host", "service", or "method". In addition, a `-bin` header name throws at pick time (the spec requires it to make the config invalid when parsed), and multi-valued headers use the last value instead of the comma-joined values.
- **Evidence:** `rls/src/main/java/io/grpc/rls/RlsProtoConverters.java` (`checkUniqueKey`, around lines 131-140 and 267-276); `RlsRequestFactory.create` and `createRequestHeaders`.
- **Spec:** `04-client-channel/lb-policies/rls.md`, "grpcKeybuilders" and "Key Building"

### [medium] Cluster specifier plugin validation gaps

- **Item:** R133
- **Summary:** Java does not validate the generated RLS config when the RouteConfiguration is parsed, and it misses some duplicate plugin names.
- **Description:**
  - The RLS plugin checks only that `route_lookup_config` is present. A bad RLS config is accepted (ACKed), and the error appears later as a service config error from the resolver.
  - Duplicate plugin names are rejected only among supported plugins.
  - The generated cds config uses the key "is_dynamic" instead of the JSON name "isDynamic". Java's cds parser reads the same key, so Java is internally consistent, but a config that uses the spec's JSON name is not understood.
- **Evidence:**
  - `xds/src/main/java/io/grpc/xds/RouteLookupServiceClusterSpecifierPlugin.java` `parsePlugin`
  - `XdsRouteConfigureResource.java` `extractVirtualHosts`
  - `XdsNameResolver.java` `ClusterRefState.toLbPolicy`
  - `CdsLoadBalancerProvider` ("is_dynamic")
- **Spec:** `09-xds/04-resources/03-route-configuration.md`, "Cluster Specifier Plugins" and "RLS Cluster Specifier Plugin"

### [medium] Retries on a non-negative pushback even when the status code is not retryable

- **Item:** incidental (investigation of old item 94)
- **Summary:** A `grpc-retry-pushback-ms` ≥ 0 causes a retry regardless of `retryableStatusCodes`.
- **Description:** The retry design and the spec retry only when the status is retryable; pushback only changes the delay (or forbids retry when negative). Java's `RetriableStream.makeRetryDecision` retries on any non-negative pushback, so a server can cause retries of non-retryable failures.
- **Evidence:** `core/.../RetriableStream.java` `makeRetryDecision` (`else if (pushbackMillis >= 0)` branch).
- **Spec:** Retries and Hedging: Server Pushback

### [medium] Decompressed-size limit violation reported as CANCELLED / UNKNOWN

- **Item:** incidental (investigation of old item 9)
- **Summary:** Exceeding the maximum receive size after decompression produces CANCELLED on the client and UNKNOWN on the server.
- **Description:** The spec requires RESOURCE_EXHAUSTED when a received message exceeds the size limit, including after decompression. Java reports other codes in this path.
- **Evidence:** `core/.../MessageDeframer.java` (SizeEnforcingInputStream); findings G1.
- **Spec:** Core RPC Semantics: Message Size Limits

### [medium] Aggregate cluster's LB policy fields are validated instead of ignored

- **Item:** R111
- **Summary:** An aggregate cluster whose LB policy fields are unsupported (e.g. `lb_policy: CLUSTER_PROVIDED`) is NACKed.
- **Description:** `XdsClusterResource.processCluster` builds and parses the LB policy config for every cluster, including aggregate clusters. Envoy requires aggregate clusters to use `lb_policy: CLUSTER_PROVIDED`, which gRPC does not support, so an aggregate cluster configured the Envoy way is NACKed. The spec says the aggregate cluster's LB policy fields are ignored entirely (not validated, never cause rejection). Impact: control planes that serve both Envoy and gRPC cannot use aggregate clusters with gRPC clients.
- **Evidence:** grpc-java `xds/src/main/java/io/grpc/xds/XdsClusterResource.java` (~lines 164-173, `LoadBalancerConfigFactory.newConfig` and `parseLoadBalancingPolicyConfig` called for every cluster type); `LoadBalancerConfigFactory` rejects CLUSTER_PROVIDED.
- **Spec:** 09-xds/04-resources/04-cluster.md, "Aggregate Clusters"

### [medium] LRS load_reporting_interval has no 1-second minimum; non-positive values stop reporting

- **Item:** XDS_LRS-1
- **Summary:** The LRS client uses the server's `load_reporting_interval` as-is: a value ≤ 0 schedules no reports at all, and a small positive value is not raised to 1 second.
- **Description:** `LoadReportClient` stores the interval from each response and `scheduleNextLoadReport` schedules the next report only if `intervalNano > 0`. The spec (and gRFC A27 as updated) requires any interval below 1 second, including zero, negative, or unset, to be treated as 1 second. Impact: a zero or unset interval silently disables load reporting; a very small interval floods the LRS server.
- **Evidence:** grpc-java `xds/src/main/java/io/grpc/xds/client/LoadReportClient.java` (~lines 198, 245, 267-275).
- **Spec:** 09-xds/10-load-reporting.md, "Responses"

### [medium] SNI-based SAN check (auto_sni_san_validation) is case-sensitive

- **Item:** XDS_SECURITY-1
- **Summary:** With `auto_sni_san_validation`, the server certificate's DNS SANs are compared with the SNI case-sensitively.
- **Description:** `getAutoSniSanMatchers` builds `StringMatcher.newBuilder().setExact(hostName)` without `ignore_case`, so a SAN that differs from the SNI only in letter case fails verification. The spec (and gRFC A101 as updated) requires an ASCII case-insensitive comparison, since DNS names are case-insensitive (RFC 4343). Go, C++ and Envoy (`Utility::dnsNameMatch` lowercases both sides) all compare case-insensitively. Impact: TLS handshakes fail in Java for mixed-case hostnames that the other implementations accept.
- **Evidence:** grpc-java `xds/src/main/java/io/grpc/xds/internal/security/trust/XdsX509TrustManager.java` `getAutoSniSanMatchers` (~lines 303-312).
- **Spec:** 09-xds/09-security.md, "Server Identity Verification"

### [medium] Authenticated principal matching stops at the first identity type present

- **Item:** AUTHZ-1
- **Summary:** When a client certificate has URI SANs, DNS SANs and the subject are never checked (and likewise the subject when it has DNS SANs), so a principal that matches only a DNS SAN or the subject does not match.
- **Description:** `getPrincipalNames` returns only the URI SANs if the certificate has any, otherwise only the DNS SANs, otherwise only the subject, and `AuthenticatedMatcher` matches against that single set. The spec (and gRFC A41 and A43 as updated, matching the `principal_name` semantics Envoy is adopting in envoyproxy/envoy#48787) matches if any URI SAN, any DNS SAN, or the RFC 2253 subject matches; all three are always checked. Impact: a policy naming a peer by DNS SAN or subject denies a peer whose certificate also carries a non-matching URI SAN (e.g. a SPIFFE ID), while C++ and Envoy allow it. The same engine serves both the gRPC authorization policy and xDS RBAC.
- **Evidence:** grpc-java `xds/src/main/java/io/grpc/xds/internal/rbac/engine/GrpcAuthorizationEngine.java` `getPrincipalNames` (~lines 303-346) and `AuthenticatedMatcher` (~lines 145-176).
- **Spec:** 06-security/04-authorization.md, "Authenticated Principal Matching"

### [low] outlier_detection max_ejection_percent checked before ejection instead of against the resulting percentage

- **Item:** R18
- **Summary:** max_ejection_percent is compared with the percentage already ejected, so ejection can exceed the limit.
- **Description:** Both algorithms return when `trackerMap.ejectionPercentage() >= config.maxEjectionPercent`, comparing the percentage already ejected, so the last ejection can exceed the limit (the code comment says so and claims this matches Envoy, which is no longer true). The spec (gRFC A50 as updated, matching Envoy's default with `always_eject_one_host` off) ejects an endpoint only if `100 * (ejected + 1) / endpoints <= max_ejection_percent`, so the limit is never exceeded and 0 disables ejection. Impact: in small endpoint sets gRPC ejects endpoints that Envoy would not; e.g. with the default 10% and 3 endpoints, gRPC ejects one (33%) while Envoy ejects none.
- **Evidence:** grpc-java `util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java` (~lines 828-835 and 904-910).
- **Spec:** 04-client-channel/lb-policies/outlier_detection.md, "Success-Rate Algorithm" / "Failure-Percentage Algorithm"

### [low] Netty hard header-size limit yields INTERNAL instead of RESOURCE_EXHAUSTED

- **Item:** R2
- **Summary:** Over the Netty hard header-list limit, the Java server sends HTTP 431 with no grpc-status plus RST_STREAM(PROTOCOL_ERROR), and the client reports INTERNAL.
- **Description:** Over the soft limit, Java behaves as specified (RESOURCE_EXHAUSTED both ways), but over the hard limit the server sends HTTP 431 without grpc-status and resets with PROTOCOL_ERROR, and the client reports INTERNAL. The spec says the client SHOULD report RESOURCE_EXHAUSTED. The impact is limited to very large headers.
- **Evidence:** grpc-java Netty transport header-list size handling (NettyServerHandler / NettyClientHandler hard vs. soft limit).
- **Spec:** 02-rpc-semantics.md "Size Limits"; 03-wire-protocol/01-http2.md "Header list size"

### [low] Default per-RPC retry buffer limit is not 256 KiB

- **Item:** R44
- **Summary:** Java's default per-RPC retry buffer limit is 1 MiB, but the spec recommends (SHOULD) 256 KiB.
- **Description:** `ManagedChannelImplBuilder` defaults `perRpcBufferLimit` to 1 MiB (and also has a 16 MiB per-channel limit, which the spec allows). The spec recommends a 256 KiB per-RPC default, so retry behavior for large requests is consistent across languages. The deviation is allowed, but a Java client can still retry requests that other languages would commit without retrying.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/ManagedChannelImplBuilder.java` (`perRpcBufferLimit`, `retryBufferSize`).
- **Spec:** Retries and Hedging (`04-client-channel/11-retries.md`), "Buffer Limits".

### [low] Oversized request headers over the hard limit get no gRPC status

- **Item:** R50
- **Summary:** Over the Netty hard header limit, Java sends HTTP 431 and `RST_STREAM(PROTOCOL_ERROR)` with no `grpc-status`.
- **Description:** Java's soft-limit path sends `RESOURCE_EXHAUSTED`, but the hard-limit path sends only HTTP 431 and a stream reset, so gRPC clients map it to a generic error. The spec says the server SHOULD send a gRPC `RESOURCE_EXHAUSTED` status. With the default settings, soft and hard limits are the same, so this path is common when the limit is hit.
- **Evidence:** grpc-java `netty/src/main/java/io/grpc/netty/NettyServerHandler.java` / `GrpcHttp2HeadersUtils` (hard-limit header handling).
- **Spec:** Server (`05-server.md`), "Request Validation".

### [low] Async stub does not fail unary calls that receive zero responses

- **Item:** R98
- **Summary:** The Java async stub reports a unary call that ends OK with no response message as a successful completion instead of failing it with `INTERNAL`.
- **Description:** Java's blocking and future stubs fail a unary call that ends OK with no response message with `INTERNAL` ("No value received for unary call"), but the async (StreamObserver) stub just calls `onCompleted()` without `onNext()`. The spec requires the client to fail the call with `INTERNAL`. Applications using the async stub may treat a missing response as success. (Also, more than one response surfaces as `CANCELLED` with an `INTERNAL` cause rather than as `INTERNAL`.)
- **Evidence:** `stub/src/main/java/io/grpc/stub/ClientCalls.java` (`UnaryStreamToFuture` ~L620-633 handles both cases; the StreamObserver adapter for `asyncUnaryCall` does not check cardinality).
- **Spec:** Core RPC Semantics (`02-rpc-semantics.md`), "Unary Calls".

### [low] Binary log config accepts `*/M` and `-S/*`, ignores bare `-`

- **Item:** R107
- **Summary:** `GRPC_BINARY_LOG_FILTER` parsing accepts patterns the grammar makes malformed instead of refusing to start.
- **Description:** `BinlogHelper.FactoryImpl` treats `*/<method>` as a literal per-method name and `-<service>/*` as a literal excluded method, and silently skips a bare `-` pattern. The spec (and A16) say these are malformed and the process must refuse to start. Go rejects all three. Impact: typos in the config silently log nothing for the intended methods.
- **Evidence:** grpc-java `services/src/main/java/io/grpc/protobuf/services/BinlogHelper.java` `FactoryImpl(...)` (the `startsWith("-")` branch `continue`s on an empty name; no check for a `*` service or a negated wildcard).
- **Spec:** 08-observability/07-binary-logging.md, "Validation" (Configuration String)

### [low] weighted_clusters entry with empty name accepted

- **Item:** R112
- **Summary:** A `ClusterWeight` with an empty `name` is not rejected.
- **Description:** `XdsRouteConfigureResource` does not check that `ClusterWeight.name` is non-empty; the spec requires it (MUST be non-empty, otherwise the resource is rejected). Impact: RPCs may be routed to a cluster named "" that can never resolve.
- **Evidence:** grpc-java `xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java` `parseClusterWeight`.
- **Spec:** 09-xds/04-resources/03-route-configuration.md, "`weighted_clusters`"

### [low] RLS miscellaneous non-conformances

- **Item:** R133
- **Summary:** Smaller differences in target choice, child config errors, state reporting, and control-channel reconnect handling.
- **Description:**
  - When all targets are in TRANSIENT_FAILURE, the first target is used (spec: the last).
  - A child config parse error passes a null config to the child instead of putting the child in TRANSIENT_FAILURE.
  - With no children, the policy reports CONNECTING (spec: IDLE).
  - Children destroyed by refcount stay in the aggregate-state map.
  - Backoff policies are not reset when the control channel returns to READY. Entries do leave backoff, which is what the spec requires; this one is minor.
- **Evidence:** `rls/src/main/java/io/grpc/rls/CachingRlsLbClient.java` `DataCacheEntry.getChildPolicyWrapper`; `LbPolicyConfiguration.java` `ChildPolicyWrapper` constructor; `SubchannelStateManagerImpl.getAggregatedState`.
- **Spec:** `04-client-channel/lb-policies/rls.md`, "Child Policies", "Connectivity State", "Picker"

### [low] Channelz ignores `max_results`

- **Item:** incidental (investigation of old item 141)
- **Summary:** Paginated Channelz methods ignore the request's `max_results`.
- **Description:** The Channelz service is supposed to honor `max_results` (up to an implementation cap). Java uses its own page size regardless. (C++ has the same problem for `GetTopChannels` and `GetServers`; see the C++ bug. Go honors `max_results`, using 50 for 0 or negative values, per the spec audit.)
- **Evidence:** `services/.../ChannelzService.java`; findings G8.
- **Spec:** Channelz: Pagination

### [low] ±20% retry jitter gated by an unrelated experimental flag

- **Item:** incidental (investigation of old item 93)
- **Summary:** Java switches between ±20% and full-jitter retry backoff based on `GRPC_EXPERIMENTAL_XDS_RLS_LB`.
- **Description:** The flag defaults to the correct (±20%) behavior, but tying retry jitter to an RLS experiment flag is confusing, and setting the flag silently changes retry timing.
- **Evidence:** `core/.../RetriableStream.java` / retry policy jitter code; findings G6.
- **Spec:** Retries and Hedging: Backoff
