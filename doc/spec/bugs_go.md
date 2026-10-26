# Go implementation bugs

Bugs in grpc-go found while writing and reviewing the gRPC spec in this directory: **94** entries, ordered by severity. Other lists: [Java](bugs_java.md), [C++](bugs_cpp.md), [documentation](bugs_docs.md).

Severity:

- **critical:** crash, data corruption, or a security weakness
- **high:** interoperability failure, or wrong behavior that users commonly hit
- **medium:** spec non-conformance with limited impact
- **low:** cosmetic, or a rare edge case

Each bug lists the review item that identified it (an item ID such as `RLS-4`, an `R<n>` number from the original review list, or "incidental"/"audit"), a summary, a description, evidence (code locations), and the spec section it violates. Open questions are in [review_items.md](review_items.md). None of these bugs has been filed yet.

### [low] Go server cannot restrict the set of compression algorithms enabled for decompression

- **Item:** COMPRESSION-2
- **Summary:** A Go server decompresses every compressor in the process-wide registry. The application cannot limit which algorithms a server accepts.
- **Description:** The spec requires implementations to let applications restrict the set of algorithms enabled for decompression, and the server API to provide a way to set it. Messages compressed with an algorithm that is not enabled are then treated as unsupported (`UNIMPLEMENTED`). Go's client can restrict decompression with the experimental `AcceptCompressors` call option, but the server has nothing like it. `processStreamingRPC`/`processUnaryRPC` look up any registered compressor with `encoding.GetCompressor(rc)`. The only per-server hook is the deprecated `RPCDecompressor`, which adds a decompressor and cannot remove registered ones. So any package that registers a compressor (for example, by importing `encoding/gzip`) enables it on every server in the process.
- **Evidence:** grpc-go master c2165f27d8bbc81e75aa14b82d23540882ac5f02: [server.go L1398-L1408](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/server.go#L1398-L1408) (server decompressor lookup), [server.go L431-L441](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/server.go#L431-L441) (deprecated `RPCDecompressor`), [experimental.go L78-L84](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/experimental/experimental.go#L78-L84) (client-only `AcceptCompressors`)
- **Spec:** Core RPC Semantics: Configuration and Precedence; Core RPC Semantics: Configuration API

### [low] Go Connect() does not restart the idle timer when the LB policy reports IDLE

- **Item:** IDLE-1
- **Summary:** `ClientConn.Connect()` restarts the idle timer only when the channel was in channel-level idle mode. When the LB policy reports IDLE, it only asks the balancer to exit idle and leaves the timer alone.
- **Description:** The spec says a `try_to_connect` request (Go: `Connect()`) counts as activity and restarts the idle timer in both cases. Go's `Connect()` calls `idlenessMgr.ExitIdleMode()`, which returns early when the channel is not `actuallyIdle`, and then calls `balancerWrapper.exitIdle()`. In the LB-reported-IDLE case, the idle timer is therefore not restarted, and `activeSinceLastTimerCheck` is not set, so the channel can enter idle mode shortly after the application asked it to connect.
- **Evidence:** grpc-go master c2165f27d8bbc81e75aa14b82d23540882ac5f02: [clientconn.go L736-L744](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/clientconn.go#L736-L744), [internal/idle/idle.go L212-L240](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/idle/idle.go#L212-L240)
- **Spec:** Channel: Idle Timeout; Channel: API Requirements

### [low] Go: RLS child TF→IDLE not sticky and picker dropped on TF→CONNECTING

- **Item:** RLS-11
- **Summary:** Go ignores only TF→CONNECTING child updates (both state and picker) and records TF→IDLE as IDLE.
- **Description:** The spec keeps the child's recorded state at TRANSIENT_FAILURE until it reports READY, and always records its picker. `handleChildPolicyStateUpdate` drops a TF→CONNECTING update entirely, so the picker isn't updated, and stores any other update, so TF→IDLE becomes IDLE. That changes target selection (a TF child is skipped, an IDLE one is not) and the aggregate state.
- **Evidence:** Go master c2165f27: [balancer/rls/balancer.go L643-L666](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer/rls/balancer.go#L643-L666)
- **Spec:** `rls` LB Policy: Calls From Children

### [low] Go: endpointsharding aggregates IDLE children as IDLE instead of CONNECTING

- **Item:** LB-3
- **Summary:** Go's `endpointsharding`, used by round_robin, weighted_round_robin, and least_request, reports IDLE when no child is READY or CONNECTING and at least one is IDLE.
- **Description:** The spec (following gRFC A58) counts an IDLE child of these policies as CONNECTING, because the policy immediately asks it to connect. `endpointSharding.updateState` keeps a separate IDLE bucket and reports IDLE ahead of TRANSIENT_FAILURE. A parent such as `priority` can then briefly see the child as IDLE instead of CONNECTING while it reconnects. C++ and Java count IDLE as CONNECTING.
- **Evidence:** Go master c2165f27: [balancer/endpointsharding/endpointsharding.go L268-L289](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer/endpointsharding/endpointsharding.go#L268-L289)
- **Spec:** Load Balancing: Connectivity State Aggregation

### [low] Go: priority LB policy forwards ExitIdle to every child

- **Item:** PRIORITY-2
- **Summary:** Go's priority policy calls `bg.ExitIdle()`, which forwards `ExitIdle()` to every child in the balancer group, not just the current priority.
- **Description:** The spec forwards `ExitIdle()` only to the current priority's child. Only that child serves picks, and waking lower priorities opens connections that aren't needed.
- **Evidence:** Go master c2165f27: [internal/xds/balancer/priority/balancer.go L238-L240](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/priority/balancer.go#L238-L240), [internal/balancergroup/balancergroup.go L574-L583](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/balancergroup/balancergroup.go#L574-L583)
- **Spec:** `priority` LB Policy: ExitIdle

### [high] Go: outlier detection re-ejects ejected endpoints and leaks the ejected count

- **Item:** OUTLIER_DETECTION-1
- **Summary:** Go doesn't skip already-ejected endpoints in either algorithm. Every re-ejection increments `numEndpointsEjected`, which can drift upward until it blocks all further ejections.
- **Description:** The spec excludes already-ejected endpoints from the candidates. `endpointsWithAtLeastRequestVolume` returns every endpoint with enough volume, whether ejected or not. Both algorithms can call `ejectEndpoint` again, which increments `numEndpointsEjected` and the multiplier and resets the timestamp. `unejectEndpoint` decrements the count only once, and removing an ejected endpoint in an update doesn't decrement it at all. Once the count is too high, `numEndpointsEjected/len*100 >= MaxEjectionPercent` blocks every later ejection for the life of the policy. The stale count also affects the mean/stdev and `minimum_hosts`.
- **Evidence:** Go master c2165f27: [internal/xds/balancer/outlierdetection/balancer.go L702-L712](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L702-L712) (candidates), [L743-L803](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L743-L803) (algorithms), [L806-L827](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L806-L827) (eject/uneject), [L329-L333](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L329-L333) (endpoint removal)
- **Spec:** `outlier_detection` LB Policy: Ejection Timer

### [low] Go DNS service config choices: unknown keys ignored, percentage not range-checked

- **Item:** DNS-2
- **Summary:** The Go DNS resolver accepts a TXT service config choice that has an unknown key or a `percentage` outside 0–100. gRFC A2 says that makes the whole config invalid.
- **Description:** `canaryingSC` unmarshals into `rawChoice` with `json.Unmarshal`, which ignores unknown keys. `chosenByPercentage` does no range check. A choice with no `serviceConfig` is skipped instead of being treated as an error. Checked on master.
- **Evidence:** [dns_resolver.go#L419-L470](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/resolver/dns/dns_resolver.go#L419-L470)
- **Spec:** Name Resolution: Service Config in DNS › Service Config Choices

### [low] Go appends picker-supplied headers instead of replacing existing values

- **Item:** LB-1
- **Summary:** If the application already set `x-google-rls-data`, Go sends both that value and the RLS value.
- **Description:** The rls picker adds the header with `metadata.Pairs`/`Append`. The channel then merges `PickResult.Metadata` into the outgoing metadata with `metadata.Join`, which appends. C++ and Java replace the existing value. Checked on master.
- **Evidence:** [picker.go#L211-L215](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer/rls/picker.go#L211-L215), [stream.go#L639-L654](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stream.go#L639-L654)
- **Spec:** Load Balancing: Pick Results; `rls` LB Policy: Picker Implementation

### [low] Go priority policy ignores child update errors

- **Item:** PRIORITY-3
- **Summary:** `priorityBalancer.UpdateClientConnState` returns nil even when a child rejects its config, so the resolver gets no signal to back off.
- **Description:** `childBalancer.sendUpdate` logs the child's error and puts the child in TRANSIENT_FAILURE with an error picker. There is a TODO ("return and aggregate the returned error in the parent"). C++ and Java return a non-OK status. Checked on master.
- **Evidence:** [balancer.go#L117-L208](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/priority/balancer.go#L117-L208), [balancer_child.go#L114-L130](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/priority/balancer_child.go#L114-L130)
- **Spec:** `priority` LB Policy: Updates from the Parent

### [medium] Go random_subsetting hashes Address.String() including attributes

- **Item:** RANDOM_SUBSETTING-1
- **Summary:** The hash input contains the address's attributes, and some of them print as pointers. So the subset can change on every resolver update even when the addresses are the same.
- **Description:** `b.hashDigest.WriteString(endpoint.Addresses[0].String())`. `Address.String()` includes `Attributes` and `BalancerAttributes`, and `Attributes.String()` prints values that are neither strings nor Stringers as `<%p>`. That breaks the low-churn guarantee in gRFC A68. The fix is to hash `Addr` only. Checked on master.
- **Evidence:** [randomsubsetting.go#L180](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer/randomsubsetting/randomsubsetting.go#L180), [resolver.go#L138-L150](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/resolver/resolver.go#L138-L150), [attributes.go#L145](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/attributes/attributes.go#L145)
- **Spec:** `random_subsetting` LB Policy: Subset Selection

### [low] Go ignores healthCheckConfig changes until the subchannel reconnects

- **Item:** HEALTH-2
- **Summary:** Go reads the health-check service name only once, when pick_first registers its health listener after READY. A changed or removed `healthCheckConfig` takes effect only after the next reconnect.
- **Description:** `acBalancerWrapper.healthListenerRegFn` calls `cc.healthCheckConfig()` once and keeps `cfg.ServiceName` in the closure. pick_first calls `RegisterHealthListener` only on the READY transition. Nothing re-registers when the service config changes. Java and C++ restart or stop the stream on update. Checked on master.
- **Evidence:** [balancer_wrapper.go#L443-L463](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer_wrapper.go#L443-L463), [pickfirst.go#L642-L644](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer/pickfirst/pickfirst.go#L642-L644)
- **Spec:** Health Checking: Client Workflow

### [medium] Go resets retry throttle tokens on every resolver update

- **Item:** RETRY-3
- **Summary:** `applyServiceConfigAndBalancer` installs a new `retryThrottler` with `tokens = MaxTokens` on every call. That includes every resolver update with an unchanged config, and resolver errors (through `maybeApplyDefaultServiceConfig`).
- **Description:** With a resolver that updates often (xDS, re-resolving DNS), the token bucket keeps getting refilled, so retry throttling may never kick in. That defeats its overload protection. C++ keeps the throttler when the parameters are unchanged and scales the ratio when they change. Checked on master.
- **Evidence:** [clientconn.go#L1159-L1180](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/clientconn.go#L1159-L1180), [clientconn.go#L794-L850](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/clientconn.go#L794-L850)
- **Spec:** Retries: Token Accounting

### [low] Go channelz GetServerSockets returns OK for an unknown server id

- **Item:** CHANNELZ-3
- **Summary:** `GetServerSockets` with a server id that does not exist returns an empty successful response instead of `NOT_FOUND`.
- **Description:** `channelMap.getServerSockets` returns `nil, true` when the server id is not found, and the service handler always returns `resp, nil`. C++ and Java return `NOT_FOUND`. Tools cannot tell an unknown server from one with no sockets.
- **Evidence:** [channelmap.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/channelz/channelmap.go#L291-L301), [service.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/channelz/service/service.go#L90-L94)
- **Spec:** Channelz: The Channelz Service

### [low] Go accepts a HeaderMatcher range_match with start > end

- **Item:** XDS_ROUTING-10
- **Summary:** An inverted `range_match` is accepted instead of NACKing the resource.
- **Description:** `headermatcher.FromProto` passes start and end to `NewHeaderRangeMatcher` without checking `start <= end`. The matcher never matches (or always matches when inverted). C++ rejects the resource. (Go's former `contains_match` NACK was fixed in v1.84.0, grpc/grpc-go#9223.)
- **Evidence:** [header.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/matcher/header/header.go#L55-L59)
- **Spec:** xDS Common Types: HeaderMatcher

### [low] Go does not validate VirtualHost domains

- **Item:** XDS_ROUTING-7
- **Summary:** An empty `domains` list or an invalid domain pattern is accepted instead of NACKing the RouteConfiguration.
- **Description:** The RDS parser only lower-cases `vh.GetDomains()`; it does not check for an empty list or invalid patterns. At selection time `matchTypeForDomain` returns "invalid" and the pattern never matches. C++ and Envoy reject.
- **Evidence:** [unmarshal_rds.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_rds.go#L104-L116)
- **Spec:** RouteConfiguration: Domain Patterns

### [low] Go accepts an empty route cluster, empty hash-policy header_name, and missing or empty regex_rewrite pattern

- **Item:** XDS_ROUTING-9
- **Summary:** Several invalid RouteAction fields are accepted instead of NACKing the RouteConfiguration.
- **Description:** A `RouteAction_Cluster` with an empty name is used as is. `hashPoliciesProtoToSlice` accepts an empty `header_name`, and compiles `rr.GetPattern().GetRegex()` even when the pattern is missing or empty (an empty regex compiles). C++ rejects all of these.
- **Evidence:** [unmarshal_rds.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_rds.go#L301-L302), [unmarshal_rds.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_rds.go#L392-L410)
- **Spec:** RouteConfiguration: Cluster Specifier; RouteConfiguration: Hash Policy

### [medium] Go does not reset LRS stats for unrequested clusters

- **Item:** XDS_LRS-2
- **Summary:** Stats for clusters the LRS server did not ask for keep building up and appear in the first report after the server asks for that cluster.
- **Description:** `LoadStore.stats(clusterNames)` reads and resets only the listed clusters. Other clusters' counters are never reset, so a later request for them reports load from earlier intervals as current. C++ resets every cluster at each report.
- **Evidence:** [load_store.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/clients/lrsclient/load_store.go#L112-L130)
- **Spec:** xDS Load Reporting: Responses

### [low] Go outlier_detection accepts an interval of 0 and busy-loops

- **Item:** OUTLIER_DETECTION-4
- **Summary:** Both the LB config parser and the xDS Cluster parser reject only a negative `interval`. With 0, `afterFunc(0, …)` re-arms after every sweep.
- **Description:** The spec now makes `interval` 0 invalid: the LB config is rejected, and the xDS Cluster resource is NACKed. Go accepts it and busy-loops the interval timer.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L130-L131, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L695, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L694-L695
- **Spec:** `outlier_detection` LB Policy: 2.2 Validation; Cluster: 4. Outlier Detection

### [low] Go applies the deprecated CertificateProviderInstance fallback to the whole CommonTlsContext instead of per field

- **Item:** XDS_SECURITY-5
- **Summary:** Go reads the deprecated fields only if parsing with the new fields fails or produces an empty config, and then takes identity and CA only from the deprecated fields. A config that mixes a new field with a deprecated one loses the new field.
- **Description:** The spec says each deprecated field is a fallback for its own new field: identity from `tls_certificate_certificate_provider_instance` only when `tls_certificate_provider_instance` is unset, and CA from `combined_validation_context.validation_context_certificate_provider_instance` only when there is no `ca_certificate_provider_instance`. Go's `securityConfigFromCommonTLSContext` first calls `securityConfigFromCommonTLSContextUsingNewFields`. When the CA comes only from the deprecated field, that call fails ("expected field ca_certificate_provider_instance is missing"). Go then calls `securityConfigFromCommonTLSContextWithDeprecatedFields`, which reads identity only from the deprecated field. Result for a CommonTlsContext with `tls_certificate_provider_instance` set and the CA only in `combined_validation_context.validation_context_certificate_provider_instance`:
  - On a client, the resource is accepted, but the client identity certificate is silently dropped, so mTLS handshakes fail.
  - On a server, the Listener is NACKed for having no identity instance.

  A separate issue in the same function: validation errors from the new fields are discarded whenever the deprecated-field parse succeeds.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L401-L427, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L430-L480, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L589-L599
- **Spec:** xDS Security: `CommonTlsContext` Validation

### [low] Go: method config with both retryPolicy and hedgingPolicy is accepted

- **Item:** SERVICE_CONFIG-7
- **Summary:** Go ignores `hedgingPolicy` as an unknown field, so a method config with both policies is accepted and the retry policy is used.
- **Description:** The spec says a method config entry with both `retryPolicy` and `hedgingPolicy` makes the service config invalid. Go's `jsonMC` has no `HedgingPolicy` field. The fix is to recognize `hedgingPolicy` just enough to reject the combination (hedging itself remains unimplemented).
- **Evidence:** [service_config.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/service_config.go#L148-L155) (`jsonMC`)
- **Spec:** Service Config: `methodConfig`

### [low] Go: graceful switch does not swap immediately when the current policy is not READY

- **Item:** LB-4
- **Summary:** When the current policy is already not READY, Go waits for the pending policy's first state report instead of swapping immediately.
- **Description:** The spec says that if the channel is not READY when the policy name changes, the new policy replaces the old one immediately. Go's gracefulswitch swaps only on a state report (from the current policy leaving READY, or from the pending policy), so if the current policy is already not READY, the swap waits for the pending policy to report.
- **Evidence:** [gracefulswitch.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/balancer/gracefulswitch/gracefulswitch.go#L326-L367) (`balancerWrapper.UpdateState`)
- **Spec:** Load Balancing: Gracefully Switching LB Policies

### [low] Go: failed token prefetch is retried on every attempt with no backoff

- **Item:** CALL_CREDS-2
- **Summary:** In Go's JWT token file and GCP service account identity call credentials, after a failed prefetch every attempt in the refresh window starts another fetch, ignoring backoff.
- **Description:** The spec says a prefetch starts only when no fetch is in progress and no backoff timer is running. JWT token file credentials prefetch on `needsPreemptiveRefresh && !c.pendingRefresh` without checking backoff. GCP service account identity credentials prefetch on `isTokenStaleLocked() && c.fetching == nil` and check `nextRetryTime` only after the cached token has expired. In both, every attempt in the refresh window after a failed prefetch starts another file read / metadata server request.
- **Evidence:** [token_file_call_creds.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/credentials/jwt/token_file_call_creds.go#L85-L95), [gcp_service_account_identity_credentials.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/credentials/google/gcp_service_account_identity_credentials.go#L175-L190)
- **Spec:** Call Credentials: Algorithm

### [low] Go: span status description omits the status code name

- **Item:** TRACING-3
- **Summary:** Go sets the span status description to the status message only, without the status code name.
- **Description:** The spec says the description is `<CODE>: <message>` (just `<CODE>` if the message is empty). Go calls `SetStatus(otelcodes.Error, s.Message())` on call, attempt, and server spans.
- **Evidence:** [client_tracing.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stats/opentelemetry/client_tracing.go#L77), [trace.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stats/opentelemetry/trace.go#L68)
- **Spec:** Tracing: Span Status

### [low] Go: received_goaway_error and peer_max_concurrent_streams not populated in channelz

- **Item:** CHANNELZ-4
- **Summary:** Go's channelz does not set `SocketData.received_goaway_error` or `SocketData.peer_max_concurrent_streams`.
- **Description:** The spec requires `received_goaway_error` when a GOAWAY has been received and `peer_max_concurrent_streams` on the client. The fields exist only in the generated `channelz.pb.go`; `channelz/internal/protoconv` never sets them. (`max_connections_per_subchannel` is covered by an optionality note, since Go has no connection scaling.)
- **Evidence:** [protoconv/socket.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/channelz/internal/protoconv/socket.go#L83-L90)
- **Spec:** Channelz: `SocketData`

### [low] Go: received out-of-range ASCII metadata values are accepted, but echoing them fails the call

- **Item:** METADATA-2
- **Summary:** An ASCII metadata value with bytes 0x80–0xFF is accepted on receipt but sending it back fails with `INTERNAL`.
- **Description:** Received values are not validated beyond the HTTP/2 field-value check, so bytes 0x80–0xFF pass. Outgoing client metadata (`newClientStream`) and the streaming server's `SetHeader`/`SendHeader` validate values against 0x20–0x7E (`imetadata.Validate`/`ValidatePair`) and fail with `INTERNAL`. Proxies that forward incoming metadata fail RPCs. Fix: discard such values on receipt (allowed by the spec), or allow them on send. Still present on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stream.go#L311-L320, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stream.go#L1817-L1850, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/metadata/metadata.go (ValidatePair)
- **Spec:** 2. Core RPC Semantics: 7.2 Values

### [low] Go: legacy server compressor and request-mirroring paths ignore the client's grpc-accept-encoding

- **Item:** COMPRESSION-3
- **Summary:** When the deprecated `RPCCompressor` option is set, or when the server mirrors the request's `grpc-encoding`, the send compressor is set without checking the client's `grpc-accept-encoding`.
- **Description:** `SetSendCompressor` checks the client's list, but the path in `processUnaryRPC`/`processStreamingRPC` that uses `s.opts.cp` or mirrors `stream.RecvCompress()` calls `SetSendCompress` without the check. Still present on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/server.go#L1411-L1430, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/server.go#L1894
- **Spec:** 2. Core RPC Semantics: 13.2 Negotiation

### [low] Go: server compresses responses by default using the request's encoding

- **Item:** COMPRESSION-1
- **Summary:** With no compression configured anywhere, a Go server compresses responses with the request's `grpc-encoding`.
- **Description:** When no deprecated `RPCCompressor` is set and the request used a registered non-identity encoding, the server sets the same encoding for the response; `SetSendCompressor` documents this as the default. The spec (and doc/compression.md) require no compression without configuration, partly for CRIME/BEAST-style reasons. Changing this alters Go's default behavior, so a transition period may be needed. Still present on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/server.go#L1411-L1430, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/server.go#L1871-L1894
- **Spec:** 2. Core RPC Semantics: 13.4 Configuration and Precedence

### [medium] Go: grpc-status ignored on non-gRPC content-type, and :status ignored when the content-type is gRPC

- **Item:** HTTP2-1
- **Summary:** Go uses the HTTP status mapping when the content-type is not gRPC even if `grpc-status` is present, and never checks `:status` when the content-type is gRPC, so 503/429 without `grpc-status` become `UNKNOWN`.
- **Description:** In `operateHeaders`, `isGRPC` is set only by a valid gRPC content-type (or by being a trailer block). If false, `grpc-status` is ignored and the HTTP mapping is used. If true, `:status` is never consulted, so a gRPC-typed 503 Trailers-Only block without `grpc-status` ends with the default `codes.Unknown` instead of `UNAVAILABLE`, which affects retry decisions. Still present on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/http2_client.go#L1544-L1651, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/http2_client.go#L1700
- **Spec:** gRPC over HTTP/2: 7.2 Deriving the status

### [low] Go: RST_STREAM FLOW_CONTROL_ERROR maps to RESOURCE_EXHAUSTED instead of INTERNAL

- **Item:** HTTP2-7
- **Summary:** `http2ErrConvTab` maps `http2.ErrCodeFlowControl` to `codes.ResourceExhausted`.
- **Description:** A received `RST_STREAM(FLOW_CONTROL_ERROR)` reports a flow-control protocol violation by the peer and should map to `INTERNAL`, as the spec, PROTOCOL-HTTP2.md, Java, and C++ do. Could be folded into the existing Go bug about unknown RST_STREAM codes, since it is the same table. Still present on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/http_util.go#L57
- **Spec:** gRPC over HTTP/2: 8.2 RST_STREAM

### [medium] Go: loadBalancingPolicy matched case-sensitively; unknown names silently become pick_first

- **Item:** SERVICE_CONFIG-8
- **Summary:** A service config using the proto's own `"ROUND_ROBIN"` value, or a misspelled policy name, silently gets `pick_first` instead of being matched case-insensitively or rejected.
- **Description:** `balancer.Get` is case-sensitive by default (`GRPC_GO_EXPERIMENTAL_CASE_SENSITIVE_BALANCER_REGISTRIES` defaults to true), and `parseServiceConfig` replaces any unregistered `loadBalancingPolicy` name with `pick_first`. The spec requires case-insensitive matching and that an unregistered name (with `loadBalancingConfig` unset) makes the service config invalid. Still present on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/service_config.go#L188-L197, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer/balancer.go#L84-L97, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/envconfig/envconfig.go#L95
- **Spec:** Service Config: 5.3 `loadBalancingPolicy` (deprecated)

### [low] Go: retryThrottling tokenRatio is not truncated to 3 decimal places

- **Item:** RETRY-5
- **Summary:** Go uses `tokenRatio` as a full float64; decimal places beyond 3 are not ignored.
- **Description:** gRFC A6 and the spec: "Decimal places beyond 3 are ignored (e.g. 0.5466 is treated as 0.546)." Go passes `TokenRatio` straight into the throttler. Confirmed on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/clientconn.go#L1174 ; https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/service_config.go#L264-L266
- **Spec:** Retries and Hedging: Retry Throttling

### [low] Go: HTTP CONNECT tunnel accepted only on a 200 response

- **Item:** PROXY-3
- **Summary:** Go fails the CONNECT handshake unless `resp.StatusCode == http.StatusOK`, rejecting other 2xx responses.
- **Description:** RFC 9110 §9.3.6: "Any 2xx (Successful) response indicates that the sender (and all inbound proxies) will switch to tunnel mode". The spec follows it. Go accepts only 200. Confirmed on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/proxy.go#L84
- **Spec:** HTTP CONNECT Proxy Support: CONNECT Handshake

### [low] Subchannels request re-resolution on every connection failure instead of pick_first once per pass

- **Item:** PICK_FIRST-3
- **Summary:** Go's `pick_first` never requests re-resolution; instead every `addrConn` calls `cc.resolveNow` after each failed connection attempt and on each connection loss, for every LB policy.
- **Description:** The spec (and gRFC A61) has `pick_first` request re-resolution once when a Happy Eyeballs pass completes without a connection, each time the steady-state failure count reaches the number of subchannels, and when the selected subchannel leaves READY. Go re-resolves once per subchannel failure, so watch-based and custom polling resolvers get up to N times more re-resolution requests (the `dns` resolver's minimum interval hides most of this). Known TODO grpc-go #7534. Still present on master c2165f27.
- **Evidence:** clientconn.go (`addrConn` connect failure path, "TODO: #7534 - Move re-resolution requests into the pick_first LB policy", and connection-loss path calling `ac.cc.resolveNow`); balancer/pickfirst/pickfirst.go ("We don't need to request re-resolution since the SubConn already does that").
- **Spec:** `pick_first` LB Policy: Re-resolution

### [medium] priority selection has no CONNECTING pass and deactivates lower priorities on every switch

- **Item:** PRIORITY-1
- **Summary:** Go's `syncPriority` never falls back to the highest-priority CONNECTING child (after its failover timer expired); it picks the last priority instead. `switchToChild` always deactivates lower priorities, even when the chosen child is not READY or IDLE.
- **Description:** gRFC A56 and the spec: if no child is READY or IDLE or has a pending failover timer, choose the first CONNECTING child, else the last child; lower priorities are deactivated only when a READY or IDLE child is chosen. With P0 CONNECTING after its timer expired and all others in TRANSIENT_FAILURE, Go reports the last child's TRANSIENT_FAILURE picker and fails RPCs that C++ and Java would queue. Still present on master c2165f27.
- **Evidence:** internal/xds/balancer/priority/balancer_priority.go (syncPriority, switchToChild, stopSubBalancersLowerThanPriority).
- **Spec:** `priority` LB Policy: Priority Selection Algorithm

### [low] ring_hash does not canonicalize xDS IP strings before hashing

- **Item:** RING_HASH-4
- **Summary:** Go hashes `endpoint.Addresses[0].Addr` as given; for xDS this is `net.JoinHostPort` of the EDS address string as sent, so a non-canonical IPv6 spelling is not normalized.
- **Description:** The spec hashes the canonical `host:port` form of the first address. For DNS-resolved addresses Go's string is already canonical, but an EDS address such as "2001:db8:0:0::1" is hashed as written, giving ring positions that differ from C++ and Envoy. Still present on master c2165f27.
- **Evidence:** balancer/ringhash/ringhash.go (hashKey); internal/xds/xdsclient/xdsresource/unmarshal_eds.go (net.JoinHostPort of socketAddress.GetAddress()).
- **Spec:** `ring_hash` LB Policy: Ring Construction

### [medium] Go: xDS credentials apply TLS hostname verification to per-RPC and rewritten authorities

- **Item:** TLS-5
- **Summary:** Go's xDS client credentials return a plain `credentials.TLSInfo`, whose `ValidateAuthority` does `VerifyHostname` on the leaf certificate, so per-call and xDS-rewritten (A81) authorities fail unless the certificate has a matching DNS SAN.
- **Description:** The transport calls `ValidateAuthority` whenever `callHdr.Authority` is set, which includes A81 authority rewriting from the picker. With xDS mTLS certificates that carry no matching DNS SAN (for example SPIFFE certificates with only a URI SAN), every rewritten RPC fails. The spec and A81 say xDS credentials using SAN matching do no per-RPC check. C++ turns the check off for xDS credentials (`set_check_call_host(false)`).
- **Evidence:** Go master c2165f27: [credentials/xds/xds.go L148](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/credentials/xds/xds.go#L148) (returns `credentials.TLSInfo`), [credentials/tls.go L56-L68](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/credentials/tls.go#L56-L68), [internal/transport/http2_client.go L812-L818](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/http2_client.go#L812-L818).
- **Spec:** TLS: Per-RPC Authority Verification; Security Model: Authority and Authority Override

### [low] Go: authorization audit context reports "<policy>_<rule>" as the matched rule

- **Item:** AUTHZ-5
- **Summary:** For the gRPC authorization policy, Go's audit context `MatchedRule` is `<policy name>_<rule name>` instead of the rule name.
- **Description:** The translator keys each RBAC policy as `prefixName + "_" + rule.Name`, and the RBAC engine passes that key as `MatchedRule`. So `stdout_logger` shows `"matched_rule":"example_policy_admin_access"` rather than `"admin_access"`. The policy name is already a separate audit field. C++ reports the rule name.
- **Evidence:** Go master c2165f27: [authz/rbac_translator.go L280](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/authz/rbac_translator.go#L280), [internal/xds/rbac/rbac_engine.go L298](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/rbac/rbac_engine.go#L298)
- **Spec:** Authorization: Audit Context

### [low] Go: outlier detection metrics lack the `grpc.lb.backend_service` optional label

- **Item:** METRICS-5
- **Summary:** Go registers the A91 outlier detection counters with labels `grpc.target`, `grpc.lb.outlier_detection.detection_method` (and `grpc.lb.outlier_detection.unenforced_reason`), but without the `grpc.lb.backend_service` optional label.
- **Description:** A91 and the spec list `grpc.lb.backend_service` as an optional label on both counters, taken from the backend-service resolver attribute set by `cds`. C++ supports it. Go's descriptors have no `OptionalLabels`, so the label cannot be enabled.
- **Evidence:** Go master c2165f27: [internal/xds/balancer/outlierdetection/balancer.go L57-L71](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L57-L71)
- **Spec:** Metric Catalog: Outlier Detection LB Policy Metrics

### [low] Go: grpc-trace-bin propagator and metadata carrier ignore the TextMap base64 and `-bin` rules

- **Item:** TRACING-5
- **Summary:** Go's `GRPCTraceBinPropagator` always passes the raw 29-byte value through the TextMap API (no base64), and its metadata carriers pass every key through unchanged, including other `-bin` keys, without an error log.
- **Description:** `Inject` does `carrier.Set("grpc-trace-bin", string(bd))` and `Extract` parses `[]byte(carrier.Get(...))`, so the propagator emits a non-text value with any non-gRPC TextMapCarrier. `OutgoingCarrier.Set` appends any key to outgoing metadata and `IncomingCarrier.Get` returns any key, with no base64 conversion for `grpc-trace-bin` and no rejection of other `-bin` keys. A72 requires the propagator to work with any Getter/Setter. The wire result with gRPC's own carrier is correct.
- **Evidence:** Go master c2165f27: [stats/opentelemetry/grpc_trace_bin_propagator.go L50](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stats/opentelemetry/grpc_trace_bin_propagator.go#L50), [L62](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stats/opentelemetry/grpc_trace_bin_propagator.go#L62), [stats/opentelemetry/internal/tracing/carrier.go L52](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stats/opentelemetry/internal/tracing/carrier.go#L52), [L109](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stats/opentelemetry/internal/tracing/carrier.go#L109)
- **Spec:** Tracing: Metadata Carrier; Tracing: The `grpc-trace-bin` Propagator and Format

### [low] Go: ORCA OOB UNIMPLEMENTED is not recorded as a subchannel trace event

- **Item:** CHANNELZ-2
- **Summary:** When the ORCA out-of-band stream fails with `UNIMPLEMENTED`, Go only writes a grpclog error and records no channelz trace event.
- **Description:** A51 says the client records a channel trace event and logs at ERROR. C++ (`GRPC_CHANNELZ_LOG`) and Java (`subchannelLogger.log(ERROR, ...)`) do. Go's health-check UNIMPLEMENTED path already uses `channelz.Error`, but the ORCA producer does not.
- **Evidence:** Go master c2165f27: [orca/producer.go L177-L179](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/orca/producer.go#L177-L179)
- **Spec:** Channelz: Required Events

### [medium] Legacy Cluster lb_policy LEAST_REQUEST converted without xds_wrr_locality, ignoring locality weights

- **Item:** XDS_CDS-2
- **Summary:** Go converts legacy `lb_policy = LEAST_REQUEST` to a bare `least_request_experimental` policy instead of wrapping it in `xds_wrr_locality_experimental`.
- **Description:** The spec (per A48/A52) converts `LEAST_REQUEST` to `[{"xds_wrr_locality_experimental": {"childPolicy": [{"least_request_experimental": {"choiceCount": n}}]}}]`, so localities are picked by weight and least_request picks endpoints within a locality. Go emits `[{"least_request_experimental": {"choiceCount": n}}]`, so locality weights are not applied and balancing is flat across all endpoints. Java does the wrapped conversion.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L143-L158
- **Spec:** Cluster: Legacy `lb_policy`

### [medium] EDS endpoint addresses are not validated (host names, invalid ports, and missing fields accepted)

- **Item:** XDS_EDS-5
- **Summary:** Go builds endpoint addresses with `net.JoinHostPort` and performs no validation.
- **Description:** The spec (per A27) requires `endpoint` to be present and each address to be a `socket_address` with an IPv4/IPv6 literal and a `port_value` of at most 65535; violations reject the resource. Go's `parseAddress` is just `net.JoinHostPort(GetAddress(), port)`: a missing endpoint or socket_address becomes ":0", ports above 65535 are accepted, and host names are accepted and later resolved by the dialer (DNS lookups for EDS endpoints). C++ and Java NACK these.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_eds.go#L75-L77, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_eds.go#L110-L113
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: LbEndpoint

### [low] xDS retry max_interval < base_interval not rejected and 1ms floor not applied

- **Item:** XDS_ROUTING-8
- **Summary:** Go's `generateRetryConfig` does not check `max_interval >= base_interval` and does not raise sub-millisecond intervals to 1ms.
- **Description:** The spec (per A44) requires `max_interval` ≥ `base_interval` (else reject) and treats values below 1ms as 1ms. Go checks only `> 0` for each and passes the values through unchanged.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_rds.go#L202-L220
- **Spec:** RouteConfiguration: Retry Policy

### [low] Duplicate cluster specifier plugin names are accepted (last one wins)

- **Item:** XDS_ROUTING-3
- **Summary:** Go stores cluster specifier plugins in a map by name without checking for duplicates; a later plugin silently replaces an earlier one.
- **Description:** The spec rejects a RouteConfiguration with two `cluster_specifier_plugins` of the same `extension.name` (the Envoy proto says the names must be unique). Go keeps the last one.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_rds.go#L140-L168
- **Spec:** RouteConfiguration: Cluster Specifier Plugins

### [medium] xDS server never force-closes drained connections and has no drain grace time option

- **Item:** XDS_SERVER-4
- **Summary:** On a Listener update, Go sends GOAWAY to old connections but never closes them, and offers no API to configure a drain grace time.
- **Description:** The spec (per A36) drains connections accepted under the previous Listener and forcibly closes them after the drain grace time (default 10 minutes), which the xDS-enabled server API MUST let applications configure. Go's `maybeUpdateFilterChains` calls `Drain()` (GOAWAY only) and never closes the connection later; `xds/server_options.go` has no drain option. Long-lived streams therefore keep the old configuration (including old RBAC policy and certificates) indefinitely. C++ and Java implement both.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/server/listener_wrapper.go#L147-L199, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/server/conn_wrapper.go#L139-L160, xds/server_options.go
- **Spec:** xDS-Enabled Servers: Configuration Updates and Draining

### [high] Aggregate clusters use the aggregate cluster's LB policy and a flattened priority list (A75 not implemented for aggregate clusters)

- **Item:** XDS_LB-5
- **Summary:** Go flattens every leaf cluster's priorities into one `priority` policy, with `outlier_detection` and `xds_cluster_impl` per priority, and uses the root aggregate cluster's LB policy for all leaves.
- **Description:** gRFC A75 represents an aggregate cluster as a `priority` policy whose children are per-leaf `cds` policies. Each leaf uses its own LB policy, and outlier detection, cluster_impl, and override_host sit above that leaf's priorities. Go adopted A75 for non-aggregate clusters in v1.85.0 (grpc/grpc-go#9234), but aggregate clusters still use the pre-A75 shape: "The LB policy is configured by the root cluster". So the aggregate cluster's LB policy fields, which the spec says are ignored, are applied to every leaf, and outlier detection runs separately in each priority.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/cdsbalancer/configbuilder.go#L109-L180, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/cdsbalancer/configbuilder.go#L212-L253, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/cdsbalancer/cdsbalancer.go#L318
- **Spec:** `cds` LB Policy: Position in the xDS LB Policy Tree

### [low] Invalid x-envoy-fault-abort-request suppresses a valid x-envoy-fault-abort-grpc-request

- **Item:** XDS_FAULT-1
- **Summary:** Go `injectAbort` checks the gRPC abort header only when the HTTP abort header is absent, so an HTTP header with an invalid value means no abort, even when a valid gRPC header is present.
- **Description:** The spec ignores invalid headers, so a valid `x-envoy-fault-abort-grpc-request` should apply when `x-envoy-fault-abort-request` is invalid. Envoy does this. Still present on Go master.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/httpfilter/fault/fault.go#L227-L244
- **Spec:** xDS HTTP Filters: Header-Controlled Faults

### [low] RLS cache key includes the RPC method path

- **Item:** RLS-4
- **Summary:** The data cache and pending-request map are keyed by the RPC's full method path plus the key map, not the key map alone.
- **Description:** The lookup request carries only the key map, so two methods with the same key map get the same answer. Keying on the path as well creates duplicate cache entries and extra RLS lookups. The spec keys the cache by the key map only (per-method routing is still available by putting the service or method into the key map with `extraKeys`).
- **Evidence:** `balancer/rls/cache.go` `cacheKey{path, keys}`.
- **Spec:** rls: Cache

### [low] RLS rejects a key builder method name containing "/"

- **Item:** RLS-2
- **Summary:** A `GrpcKeyBuilder.Name` whose `method` contains "/" makes Go reject the whole RLS config. The spec does not make this invalid; such a name just never matches.
- **Description:** `MakeBuilderMap` returns an error if the method contains "/". The spec's validation rules don't include this, so a config that other languages accept fails in Go.
- **Evidence:** grpc-go `balancer/rls/internal/keys/builder.go` `MakeBuilderMap` (`strings.Contains(name.GetMethod(), "/")`).
- **Spec:** `rls` LB Policy: Validation

### [low] RLS accepts -bin header names in key builders

- **Item:** RLS-3
- **Summary:** A `NameMatcher` header name ending in `-bin` is accepted, and the raw binary value is used as a key value. The spec makes such a config invalid.
- **Description:** `MakeBuilderMap` doesn't check header names for a `-bin` suffix, and the builder copies the decoded binary metadata value into the key map. The spec says such a config is invalid.
- **Evidence:** grpc-go `balancer/rls/internal/keys/builder.go` `MakeBuilderMap`, `matcher.Equal`/`builder.Keys`.
- **Spec:** `rls` LB Policy: Configuration; Validation

### [low] RLS host key value is the target endpoint, not the default authority

- **Item:** RLS-3
- **Summary:** The value added for `extraKeys.host` is the endpoint part of the channel's target URI, not the channel's default authority.
- **Description:** The value differs from the spec whenever the default authority is not the target endpoint: with an authority override, with a resolver that sets a different authority, or when the endpoint carries a path. The lookup server then sees different keys from different languages.
- **Evidence:** grpc-go `balancer/rls/balancer.go` (picker built with `origEndpoint: b.bopts.Target.Endpoint()`); `balancer/rls/picker.go` (`origEndpoint` used as the host key value).
- **Spec:** `rls` LB Policy: Key Building

### [medium] Per-RPC authority mismatch fails with UNAVAILABLE instead of UNAUTHENTICATED

- **Item:** TLS-2
- **Summary:** When an RPC's authority does not match the server certificate, Go fails the RPC with `UNAVAILABLE` instead of `UNAUTHENTICATED`.
- **Description:** The per-RPC authority check (`CallAuthority` override / xDS authority rewrite) is an authentication failure, not a transient one. `UNAVAILABLE` is retryable, so the call may be retried pointlessly against the same server. The spec requires `UNAUTHENTICATED`.
- **Evidence:** grpc-go `internal/transport/http2_client.go` (`NewStream`, call authority validation against `AuthInfo`).
- **Spec:** TLS: Per-RPC Authority Verification

### [low] Reflection ends the stream with INVALID_ARGUMENT for an unset or unknown message_request

- **Item:** REFLECTION-1
- **Summary:** Go's reflection service terminates the whole `ServerReflectionInfo` stream with `INVALID_ARGUMENT` when a request has no (or an unrecognized) `message_request`, instead of replying with an `error_response` carrying `UNIMPLEMENTED` and continuing.
- **Description:** A newer client that sends a request kind this server does not know loses the entire reflection stream, rather than getting a per-request error and being able to continue with supported request kinds. The spec requires an `error_response` with `error_code` `UNIMPLEMENTED` (12), leaving the stream open.
- **Evidence:** grpc-go `reflection/internal/internal.go` (`ServerReflectionInfo`, default case of the `MessageRequest` type switch returns `status.Errorf(codes.InvalidArgument, …)`).
- **Spec:** Server Reflection: Errors

### [low] dns resolver reports NXDOMAIN as an empty address list instead of an error

- **Item:** DNS-1
- **Summary:** For NXDOMAIN-type errors the Go DNS resolver sends an update with zero addresses (and no service config error) instead of an `UNAVAILABLE` error in both the endpoints and service config fields.
- **Description:** The visible outcome is still TRANSIENT_FAILURE (pick_first rejects the empty list), but the resolver result differs from the spec: the service config field does not carry the error, so the channel's "keep the last valid service config"/initial-failure logic treats the result differently, and LB policies other than pick_first see an empty list rather than an error. The spec requires both fields to hold an `UNAVAILABLE` error naming the host.
- **Evidence:** grpc-go `internal/resolver/dns/dns_resolver.go` (`handleDNSError`; NXDOMAIN path calls `UpdateState` with empty addresses instead of `ReportError`).
- **Spec:** Name Resolution: `dns`

### [medium] Go MethodAttributeFilter is server-only, applies to registered methods, and cannot record generic methods

- **Item:** METRICS-2
- **Summary:** Go's `MethodAttributeFilter` exists only on the server, is applied to all methods, and can only replace names with `"other"`.
- **Description:** The spec requires a generic method attribute predicate on both client and server that is consulted only for generic methods and that, when it returns true, records the generic method name verbatim. Go's `MethodAttributeFilter` is only consulted on the server; it is applied to every method, so it can turn a registered method into `"other"`; and it never causes an unregistered method to be recorded verbatim. This also contradicts Go's own A66-documented API ("used only for generic methods, and not registered methods").
- **Evidence:** grpc-go `stats/opentelemetry/server_metrics.go`, `stats/opentelemetry/opentelemetry.go` (`MetricsOptions.MethodAttributeFilter`), `stats/opentelemetry/client_metrics.go` (no filter)
- **Spec:** Metrics Framework and OpenTelemetry Plugin: Generic Method Names

### [medium] Go subchannel metrics use the raw cc.target for grpc.target

- **Item:** METRICS-4
- **Summary:** Go labels subchannel metrics with the raw `cc.target`, not the canonical target used by per-call metrics.
- **Description:** The spec requires `grpc.target` on `grpc.subchannel.*` metrics to be the creating channel's canonical target URI, matching per-call metrics. Go uses the raw target string, so subchannel and call metrics carry different `grpc.target` values when the scheme was omitted.
- **Evidence:** grpc-go `clientconn.go` (target passed to subchannel metrics recorder), `internal/transport` / `balancer_wrapper.go` subchannel metric recording
- **Spec:** Metric Catalog: Subchannel Metrics

### [medium] Go binary logging drops grpc-trace-bin under the header limit

- **Item:** BINARY_LOG-4
- **Summary:** Go stops at the first metadata entry that exceeds the `h` limit and drops every later entry, including a later `grpc-trace-bin`.
- **Description:** The spec requires `grpc-trace-bin`, if present, to always be logged and not count toward the header limit. Go's truncation omits the first entry that does not fit and all entries after it, so a `grpc-trace-bin` entry appearing later in the metadata is dropped. (The stop-at-first omission order itself is allowed.)
- **Evidence:** grpc-go `internal/binarylog/method_logger.go` (`truncateMetadata`)
- **Spec:** Binary Logging: Truncation

### [low] EDS resource rejected when a locality's endpoint weights sum above uint32 max

- **Item:** XDS_EDS-1
- **Summary:** Go NACKs an EDS resource when the endpoint weights in one locality add up to more than the uint32 maximum.
- **Description:** The spec puts no limit on the per-locality sum of endpoint weights. The effective weight (locality weight × endpoint weight) is capped at the uint32 maximum instead. Go rejects resources whose sum overflows; Java and C++ do not.
- **Evidence:** internal/xds/xdsclient/xdsresource/unmarshal_eds.go
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: Endpoint Weight

### [low] EDS duplicate-address check counts ignored (unhealthy) endpoints

- **Item:** XDS_EDS-3
- **Summary:** Go counts endpoints of every health status in the duplicate-address check. So a healthy endpoint that shares an address with an ignored (for example, UNHEALTHY) endpoint gets the resource rejected.
- **Description:** Endpoints that are ignored because of their health status (anything other than UNKNOWN, HEALTHY, or DRAINING), and endpoints in localities ignored because of zero weight, are not counted for uniqueness. Go keeps and counts every endpoint. C++ drops ignored endpoints first.
- **Evidence:** internal/xds/xdsclient/xdsresource/unmarshal_eds.go
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: Duplicate Addresses

### [critical] LRS client panics on a non-positive load reporting interval

- **Item:** incidental (investigation of old item 182)
- **Summary:** A `LoadStatsResponse` with `load_reporting_interval` ≤ 0 makes the LRS client panic.
- **Description:** The LRS client passes the server-provided interval directly to `time.NewTicker`, which panics on a non-positive duration. A misconfigured or malicious control plane can crash every client. The spec (and gRFC A27 as updated) requires any interval below 1 second, including zero, negative, or unset, to be treated as 1 second; Go applies no minimum, so small positive intervals are also used as-is.
- **Evidence:** grpc-go `internal/xds/clients/lrsclient/lrs_stream.go` (~line 151 `time.NewTicker(interval)`; interval read from the first response ~line 220).
- **Spec:** Load Reporting (LRS): Responses

### [high] DNS TXT: strings of all TXT records concatenated before matching grpc_config=

- **Item:** R37
- **Summary:** The dns resolver concatenates the strings of every TXT record on `_grpc_config.H` before checking for the `grpc_config=` prefix.
- **Description:** Go joins all TXT records into one string. If an unrelated TXT record is listed first, the prefix check fails and no service config is used; if two `grpc_config` records exist, the result is invalid JSON and a service config error. The spec requires concatenating strings only within a record and using the first record whose value starts with `grpc_config=`, ignoring all others. Users publishing other TXT data on the name silently lose their service config.
- **Evidence:** grpc-go `internal/resolver/dns` (TXT lookup / service config parsing).
- **Spec:** Name Resolution, Service Config in DNS, TXT Record Format

### [high] cds policy queues wait_for_ready RPCs for a cluster in error instead of dropping them

- **Item:** R109
- **Summary:** When its cluster is in error, the cds balancer (and cluster manager's error picker) uses `base.NewErrPicker`, so wait_for_ready RPCs queue instead of failing with UNAVAILABLE.
- **Description:** `cdsbalancer` reports `base.NewErrPicker(err)` with a non-status error, and `clustermanager.setErrorPickerForChild` also uses `base.NewErrPicker`; both are treated as transient failures that queue wait_for_ready RPCs. The spec (and A31) require a drop (`status.Error(codes.Unavailable, ...)` wrapped as a drop) so the RPC fails even if wait_for_ready. The resolver's cluster ref is released in the OnCommitted callback, so a queued RPC keeps the cluster alive in the service config indefinitely and the RPC hangs until its deadline.
- **Evidence:** grpc-go `internal/xds/balancer/cdsbalancer/cdsbalancer.go` (~line 505), `internal/xds/balancer/clustermanager/clustermanager.go` `setErrorPickerForChild`; `internal/xds/resolver/serviceconfig.go` `newContextWithOnCommittedFunc` refCount handling.
- **Spec:** 09-xds/lb-policies/cds.md, "Update handling"; 09-xds/05-client.md, "Cluster references and two-phase removal"

### [high] Comma-joined `-bin` metadata values fail the call instead of being split

- **Item:** METADATA-1
- **Summary:** A received `-bin` header whose values were joined with `,` fails the call with INTERNAL instead of being split and decoded value by value.
- **Description:** HTTP/2 intermediaries may combine repeated header fields into one comma-separated field. The spec (and PROTOCOL-HTTP2.md) requires receivers to split a `Binary-Header` on `,` before base64-decoding each part. Go treats the comma as invalid base64 and fails the call ("transport: malformed ...-bin"). Calls carrying repeated binary metadata through a proxy that joins headers fail, while Java peers handle them.
- **Evidence:** `internal/transport/http_util.go` `decodeMetadataHeader` / `decodeBinHeader`; `internal/transport/http2_client.go` and `http2_server.go` `operateHeaders`.
- **Spec:** 03-wire-protocol/01-http2.md, "Duplicate keys and ordering"

### [high] RingHash LB policy extension: DEFAULT_HASH hash_function rejected

- **Item:** RING_HASH-2
- **Summary:** Go accepts only `XX_HASH` in the `RingHash` LB policy extension, so configs that leave `hash_function` at its default (`DEFAULT_HASH`) are NACKed.
- **Description:** In `envoy.extensions.load_balancing_policies.ring_hash.v3.RingHash`, enum value 0 is `DEFAULT_HASH`, which means xxHash. The spec (and updated gRFC A52) require accepting `XX_HASH` or `DEFAULT_HASH`. Go fails the conversion for `DEFAULT_HASH`, so a common control-plane config that leaves the field unset causes the Cluster to be rejected.
- **Evidence:** grpc-go `internal/xds/xdsclient/xdslbregistry/converter/converter.go` RingHash converter.
- **Spec:** `09-xds/06-lb-policies.md`, "`load_balancing_policy`"

### [high] Picker errors are treated like drops: no retry, wait-for-ready ignored

- **Item:** incidental (investigation of old item 76)
- **Summary:** Any picker error that carries a status fails the RPC immediately, as if it were a DROP.
- **Description:** The spec distinguishes Fail (eligible for retry; queued when wait-for-ready) from Drop (fails even wait-for-ready RPCs and is not retried). Go fails all status-carrying picker errors without honoring wait-for-ready or retries, so wait-for-ready RPCs fail while a policy is in TRANSIENT_FAILURE. Reported by the investigator; not re-verified.
- **Evidence:** `picker_wrapper.go` (pick error handling); see findings G5.
- **Spec:** Load Balancing: Pick Results

### [medium] ring_hash missing request hash fails with UNAVAILABLE instead of INTERNAL

- **Item:** R25
- **Summary:** When no request hash is set and `requestHashHeader` is empty, the picker returns a non-status error, so fail-fast RPCs get UNAVAILABLE.
- **Description:** Go's ring_hash picker returns a plain error when the request hash is missing. The channel maps it to UNAVAILABLE for fail-fast RPCs. The spec (and C++ and Java) fail the pick with INTERNAL, because this is a configuration or programming error, not a transient condition. UNAVAILABLE misleads users and retry policies into treating it as transient.
- **Evidence:** grpc-go `balancer/ringhash/picker.go` Pick; `picker_wrapper.go` handling of non-status errors.
- **Spec:** 04-client-channel/lb-policies/ring_hash.md, Picker

### [medium] weighted_target does not validate weights

- **Item:** R27
- **Summary:** A missing or zero target weight is accepted (missing means 0).
- **Description:** Go doesn't validate weighted_target weights. A missing weight defaults to 0, and a zero-weight child is silently never picked, unless all weights are equal. The spec says a missing or zero weight makes the config invalid. Silent acceptance hides control-plane errors and differs from other clients.
- **Evidence:** grpc-go `balancer/weightedtarget/weightedtarget_config.go` parseConfig; `weightedaggregator/aggregator.go`.
- **Spec:** 04-client-channel/lb-policies/weighted_target.md, Configuration

### [medium] weighted_target IDLE picker does not trigger ExitIdle

- **Item:** R29
- **Summary:** In aggregate IDLE, the picker queues picks but never asks IDLE children to exit idle.
- **Description:** When weighted_target's aggregate state is IDLE, Go's picker returns ErrNoSubConnAvailable (queue) without scheduling ExitIdle on the children. The spec says the IDLE picker MUST schedule the policy's ExitIdle, which forwards to all children. With a child that stays IDLE until asked (e.g. pick_first), queued RPCs can hang indefinitely.
- **Evidence:** grpc-go `balancer/weightedtarget/weightedaggregator/aggregator.go` (empty picker in IDLE).
- **Spec:** 04-client-channel/lb-policies/weighted_target.md, Picker

### [medium] Negative method-config timeout is accepted and ignored

- **Item:** R48
- **Summary:** Go accepts a negative `timeout` in a `methodConfig` and silently ignores it, but the spec says it makes the service config invalid.
- **Description:** The service config parser accepts negative durations, and the timeout is applied only if it is ≥ 0, so a misconfigured timeout silently disappears. The spec requires rejecting the service config (normal invalid-config handling). Service owners get no signal that their timeout isn't in effect.
- **Evidence:** grpc-go `internal/serviceconfig/duration.go`; `stream.go` (timeout applied only when ≥ 0).
- **Spec:** Service Config (`04-client-channel/04-service-config.md`), "`methodConfig`" field table (`timeout`).

### [medium] Server shutdown does not wait for handlers by default

- **Item:** R49
- **Summary:** `Server.Stop` doesn't wait for running handlers to return unless the `WaitForHandlers` option is set. (`GracefulStop` always waits.)
- **Description:** In Go, handler goroutines are resources consumed by the server, so by the spec's guidance (follow the language's norms for server-owned resources) shutdown should wait for them. `GracefulStop` always waits for handlers, but `Stop` waits only when `WaitForHandlers` is set, an opt-in kept for backward compatibility. Applications that tear down shared state after `Stop` returns can race with handlers that are still running.
- **Evidence:** grpc-go `server.go` (`handlersWG`, `WaitForHandlers` server option); on master, `stop` waits only `if graceful || s.opts.waitForHandlers` ([server.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/server.go#L1724-L1730)).
- **Spec:** Server (`05-server.md`), "Forced Shutdown" → "Waiting for Handlers".

### [medium] Oversized request headers reset the stream with no gRPC status

- **Item:** R50
- **Summary:** Go answers oversized request headers with `RST_STREAM(FRAME_SIZE_ERROR)` and no gRPC status, but the spec says the server SHOULD send `RESOURCE_EXHAUSTED`.
- **Description:** When request headers exceed the limit, the Go server resets the stream without a status, so the client sees a generic transport error (usually `INTERNAL`) and can't tell why the RPC failed. The spec says the server SHOULD fail the RPC with a gRPC `RESOURCE_EXHAUSTED` status (for example, Trailers-Only), and allows a reset only when a status can't be sent.
- **Evidence:** grpc-go `internal/transport/http2_server.go` (header-size handling in `operateHeaders` / framer `MaxHeaderListSize`).
- **Spec:** Server (`05-server.md`), "Request Validation".

### [medium] RLS adaptive throttling never triggers

- **Item:** R133
- **Summary:** `RegisterBackendResponse` is never called, so the throttler's counts stay at zero and it never throttles.
- **Description:** The adaptive throttler is created per control channel, but lookup results are never reported to it. The throttling probability is therefore always 0. A failing or overloaded lookup server keeps receiving lookups at full rate. The spec requires completions to be counted.
- **Evidence:** `balancer/rls/control_channel.go` (`throttler` interface, `lookup`); `balancer/rls/internal/adaptive/adaptive.go` `RegisterBackendResponse` (no production callers).
- **Spec:** `04-client-channel/lb-policies/rls.md`, "Adaptive Throttling"

### [medium] RLS children may not receive resolver updates when the RLS config is unchanged

- **Item:** R133
- **Summary:** `rlsBalancer.UpdateClientConnState` returns early when the new config equals the current one, before it saves or forwards the new resolver state.
- **Description:** With xDS, each new `XdsConfig` arrives as a resolver attribute while the RLS config usually stays the same. The `cds` children would then keep an old `XdsConfig`, and dynamically subscribed clusters might never appear. The spec requires every parent update to be passed to all children. Confirmed by reading the v1.82.0 code that the early return skips saving and forwarding the resolver state; the effect on `cds` children is not verified with a test.
- **Evidence:** `balancer/rls/balancer.go` `UpdateClientConnState` (the early return around lines 307-311).
- **Spec:** `04-client-channel/lb-policies/rls.md`, "Child Policies"

### [medium] RLS cache eviction leaks child policies

- **Item:** R133
- **Summary:** `dataCache.deleteAndCleanup` does not release child policy references, so evicted or expired entries keep their child policies until the balancer closes.
- **Description:** References are released only when a target list changes or the default target changes. With many keys and changing targets, child policies (and their subchannels or xDS subscriptions) build up. Also:
  - New and failed entries count as size 0, and no resize runs after a size update.
  - Clearing `defaultTarget` creates a child for the empty target "".
- **Evidence:** `balancer/rls/cache.go` `deleteAndCleanup`, `addEntry`, `updateEntrySize`; `balancer/rls/balancer.go` `handleChildPolicyConfigUpdate`.
- **Spec:** `04-client-channel/lb-policies/rls.md`, "Cache" and "Child Policies"

### [medium] ring_hash keeps only the first duplicate endpoint's weight

- **Item:** RING_HASH-1
- **Summary:** When several endpoints share an address set, ring_hash uses the first one's weight instead of the sum.
- **Description:** The spec requires duplicate endpoints to be merged with their weights added together, so a repeated endpoint gets proportionally more ring entries (A42 "repeat = more weight"). Go's `endpointsharding` skips later duplicates, so the extra weight intended by the control plane or resolver is dropped and traffic is skewed relative to other implementations.
- **Evidence:** `balancer/endpointsharding/endpointsharding.go` (duplicate endpoint skip); `balancer/ringhash/ringhash.go`.
- **Spec:** 04-client-channel/lb-policies/ring_hash.md, "Updates and Endpoint Management"

### [medium] Unused pick reported to the call tracker as a success

- **Item:** incidental (investigation of old item 77)
- **Summary:** When a Complete pick cannot be used, Go calls `Done` with an empty `DoneInfo` (nil error).
- **Description:** Policies that account per pick (for example, LRS load stats or least_request counters) see the abandoned pick as a successful call. C++ records it as a failure. This can skew load reports.
- **Evidence:** `picker_wrapper.go` / `balancer` `DoneInfo` usage; findings G5.
- **Spec:** Load Balancing: Call-Completion Tracking

### [medium] Service config choice with no matching entry becomes a service config error

- **Item:** incidental (investigation of old items 84–86)
- **Summary:** When no choice in a DNS TXT `grpc_config` record matches, Go reports an invalid service config.
- **Description:** The spec says no matching choice means "no service config" (the default config applies). Go instead treats it as a service config error, which can put a new channel into TRANSIENT_FAILURE.
- **Evidence:** `internal/resolver/dns/dns_resolver.go` (service config choice selection); findings G4.
- **Spec:** Name Resolution: Service Config Choices

### [medium] `clientLanguage` matching is case-sensitive and only matches "GO"

- **Item:** incidental (investigation of old items 84–86)
- **Summary:** Choice entries with `clientLanguage: ["go"]` never match.
- **Description:** The service config choice format says `clientLanguage` matching is case-insensitive. Go compares case-sensitively against "GO", so lower-case values from existing configs are ignored.
- **Evidence:** `internal/resolver/dns/dns_resolver.go`; findings G4.
- **Spec:** Name Resolution: Service Config Choices

### [medium] DNS TXT lookup performed for localhost

- **Item:** incidental (investigation of old item 85)
- **Summary:** The DNS resolver queries `_grpc_config.localhost`.
- **Description:** The spec forbids service config TXT lookups when the target is `localhost` or an IP literal, to avoid latency and spurious NXDOMAIN traffic. Go skips IP literals but still queries for localhost.
- **Evidence:** `internal/resolver/dns/dns_resolver.go`; findings G4.
- **Spec:** Name Resolution: dns

### [medium] Aggregate cluster's LB policy fields are validated instead of ignored

- **Item:** R111
- **Summary:** An aggregate cluster whose LB policy fields are unsupported (e.g. `lb_policy: CLUSTER_PROVIDED`) is NACKed.
- **Description:** `validateClusterAndConstructClusterUpdate` converts and validates `lb_policy` / `load_balancing_policy` for every cluster, including aggregate clusters. Envoy requires aggregate clusters to use `lb_policy: CLUSTER_PROVIDED`, which gRPC does not support, so an aggregate cluster configured the Envoy way is NACKed. The spec says the aggregate cluster's LB policy fields are ignored entirely (not validated, never cause rejection). Impact: control planes that serve both Envoy and gRPC cannot use aggregate clusters with gRPC clients.
- **Evidence:** internal/xds/xdsclient/xdsresource/unmarshal_cds.go: the `lb_policy` switch and `load_balancing_policy` conversion (~lines 121-192) run before the cluster type is examined (aggregate case ~line 270), and `default:` rejects CLUSTER_PROVIDED (~line 160).
- **Spec:** 09-xds/04-resources/04-cluster.md, "Aggregate Clusters"

### [medium] LRS client honors only the first LoadStatsResponse on a stream

- **Item:** XDS_LRS-1
- **Summary:** Later `LoadStatsResponse` messages on an LRS stream are ignored, so changes to the interval or cluster list never take effect until the stream restarts.
- **Description:** The LRS stream receives the first `LoadStatsResponse` (`recvFirstLoadStatsResponse`), starts reporting with its parameters, and does not apply later responses. The spec says every response on the stream applies and the most recent one sets the current parameters (restarting the timer if the interval changes). Envoy also applies each new response. Impact: an LRS server cannot change the reporting interval or the set of requested clusters without breaking the stream.
- **Evidence:** grpc-go `internal/xds/clients/lrsclient/lrs_stream.go` (`recvFirstLoadStatsResponse` ~lines 198-225 and the reporting loop ~line 151).
- **Spec:** 09-xds/10-load-reporting.md, "Responses"

### [medium] Authenticated principal matching stops at the first identity type present

- **Item:** AUTHZ-1
- **Summary:** When a client certificate has URI SANs, DNS SANs and the subject are never checked (and likewise the subject when it has DNS SANs), so a principal that matches only a DNS SAN or the subject does not match.
- **Description:** `authenticatedMatcher.match` checks URI SANs if the certificate has any and returns false if none match; only if there are no URI SANs does it check DNS SANs (again returning false on no match), and only then the subject. The spec (and gRFC A41 and A43 as updated, matching the `principal_name` semantics Envoy is adopting in envoyproxy/envoy#48787) matches if any URI SAN, any DNS SAN, or the RFC 2253 subject matches; all three are always checked. Impact: a policy naming a peer by DNS SAN or subject denies a peer whose certificate also carries a non-matching URI SAN (e.g. a SPIFFE ID), while C++ and Envoy allow it. The same engine serves both the gRPC authorization policy and xDS RBAC.
- **Evidence:** grpc-go `internal/xds/rbac/matchers.go` `authenticatedMatcher.match` (~lines 470-505).
- **Spec:** 06-security/04-authorization.md, "Authenticated Principal Matching"

### [low] outlier_detection max_ejection_percent checked before ejection instead of against the resulting percentage

- **Item:** R18
- **Summary:** max_ejection_percent is compared with the percentage already ejected, so ejection can exceed the limit.
- **Description:** The success-rate and failure-percentage loops skip ejection only when `ejected% >= MaxEjectionPercent`, comparing the percentage already ejected, so the last ejection can exceed the limit. The spec (gRFC A50 as updated, matching Envoy's default with `always_eject_one_host` off) ejects an endpoint only if `100 * (ejected + 1) / endpoints <= max_ejection_percent`, so the limit is never exceeded and 0 disables ejection. Impact: in small endpoint sets gRPC ejects endpoints that Envoy would not; e.g. with the default 10% and 3 endpoints, gRPC ejects one (33%) while Envoy ejects none.
- **Evidence:** grpc-go `internal/xds/balancer/outlierdetection/balancer.go` (~line 757 and the matching check in `failurePercentageAlgorithm`).
- **Spec:** 04-client-channel/lb-policies/outlier_detection.md, "Success-Rate Algorithm" / "Failure-Percentage Algorithm"

### [low] Oversized metadata not reported as RESOURCE_EXHAUSTED

- **Item:** R2
- **Summary:** Go reports INTERNAL (client) and resets with FRAME_SIZE_ERROR (server) instead of failing the call with RESOURCE_EXHAUSTED when received metadata exceeds the size limit.
- **Description:** When a Go client receives response headers or trailers over its limit, it fails the call with INTERNAL "peer header list size exceeded limit". A Go server receiving oversized request headers sends RST_STREAM(FRAME_SIZE_ERROR) instead of a Trailers-Only RESOURCE_EXHAUSTED response. The spec says both sides SHOULD use RESOURCE_EXHAUSTED, which describes the cause accurately. Users see a misleading INTERNAL error that is hard to diagnose.
- **Evidence:** grpc-go `internal/transport/http2_client.go` (header list size check, "peer header list size exceeded limit"); `internal/transport/http2_server.go` (RST_STREAM FRAME_SIZE_ERROR on oversized headers).
- **Spec:** 02-rpc-semantics.md "Size Limits"; 03-wire-protocol/01-http2.md "Header list size"

### [low] Client does not send SETTINGS_ENABLE_PUSH=0

- **Item:** R5
- **Summary:** Go clients do not advertise SETTINGS_ENABLE_PUSH=0, so the HTTP/2 default of 1 (push enabled) applies.
- **Description:** The spec says clients SHOULD send ENABLE_PUSH=0 because gRPC never uses server push. Go's client SETTINGS frame omits it. No gRPC server pushes, so interop impact is negligible, but a non-gRPC server or proxy could legally send PUSH_PROMISE.
- **Evidence:** grpc-go `internal/transport/http2_client.go` (initial SETTINGS frame has no SettingEnablePush).
- **Spec:** 03-wire-protocol/02-http2-transport.md "SETTINGS sent"

### [low] Server header-size handling and SETTINGS_MAX_HEADER_LIST_SIZE advertisement

- **Item:** R9
- **Summary:** Go advertises SETTINGS_MAX_HEADER_LIST_SIZE only when explicitly configured, although it enforces a default limit.
- **Description:** The spec says implementations SHOULD advertise the header list size limit they enforce. Go enforces a default limit but advertises it only when the user configures one, so peers cannot avoid sending oversized headers. (The status-code part of Go's header-size handling is recorded under R2.)
- **Evidence:** grpc-go `internal/transport/http2_client.go` / `http2_server.go` (SettingMaxHeaderListSize added only if maxHeaderListSize is set).
- **Spec:** 03-wire-protocol/01-http2.md "Header list size"; 03-wire-protocol/02-http2-transport.md "SETTINGS sent"

### [low] Unknown RST_STREAM error code maps to UNKNOWN instead of INTERNAL

- **Item:** R12
- **Summary:** Go maps an RST_STREAM with an unrecognized HTTP/2 error code to UNKNOWN; the spec requires INTERNAL.
- **Description:** internal/transport/http_util.go http2ErrConvTab has no entry for unknown codes, so the client falls back to UNKNOWN. The spec's RST_STREAM mapping table says any other code maps to INTERNAL, which Java and C++ do. Impact is limited to peers sending non-standard error codes.
- **Evidence:** grpc-go internal/transport/http_util.go (http2ErrConvTab miss), http2_client.go handleRSTStream.
- **Note:** The same `http2ErrConvTab` also maps `FLOW_CONTROL_ERROR` to `RESOURCE_EXHAUSTED` instead of `INTERNAL` (open item HTTP2-7). If HTTP2-7 is decided as a Go bug, consider merging the two into one bug about the table.
- **Spec:** gRPC over HTTP/2 (03-wire-protocol/01-http2.md), "RST_STREAM"

### [low] pick_first reconnects immediately when a READY update drops the selected address

- **Item:** R20
- **Summary:** When pick_first is READY and an update no longer contains the selected address, Go reports CONNECTING and starts a new pass; the spec requires releasing it and going IDLE.
- **Description:** pickfirst.go updateClientConnState starts a first pass right away in this case. The spec (matching Java and C++) releases the selected subchannel and goes IDLE (or MAY use a new-list subchannel that is already READY). It must not start a connection attempt only because of the update. Go's behavior creates connections on channels that may no longer be in use.
- **Evidence:** grpc-go balancer/pickfirst/pickfirst.go updateClientConnState.
- **Spec:** pick_first (04-client-channel/lb-policies/pick_first.md), "State Machine and Updates"

### [low] priority LB does not reject duplicate names in `priorities`

- **Item:** R21
- **Summary:** The priority policy config parser accepts a child name that appears more than once in `priorities`.
- **Description:** Go's priority config parsing doesn't check for repeated names in `priorities`. The spec says such a config is invalid. A duplicate priority has no sensible meaning and usually points to a control-plane bug, so it should be rejected early rather than processed with undefined behavior.
- **Evidence:** grpc-go `internal/xds/balancer/priority/config.go` parseConfig (no duplicate check); compare grpc-java PriorityLoadBalancerProvider, which rejects it.
- **Spec:** 04-client-channel/lb-policies/priority.md, Configuration → Validation

### [low] ring_hash treats `minRingSize`/`maxRingSize` of 0 as "use default"

- **Item:** R23
- **Summary:** An explicit ring size of 0 is accepted and replaced by the default instead of making the config invalid.
- **Description:** Go's ring_hash config parser treats 0 as unset. The spec says both sizes MUST be in [1, 8388608] and an explicit 0 is invalid. A config that one client rejects and another accepts is an interoperability hazard.
- **Evidence:** grpc-go `balancer/ringhash/config.go` parseConfig.
- **Spec:** 04-client-channel/lb-policies/ring_hash.md, Configuration

### [low] weighted_clusters entry with empty name accepted

- **Item:** R112
- **Summary:** A `ClusterWeight` with an empty `name` is not rejected.
- **Description:** `unmarshal_rds.go` does not check that `ClusterWeight.name` is non-empty; the spec requires it (otherwise the resource is rejected). Impact: RPCs may be routed to a cluster named "" that can never resolve.
- **Evidence:** grpc-go `internal/xds/xdsclient/xdsresource/unmarshal_rds.go` (`RouteAction_WeightedClusters` case).
- **Spec:** 09-xds/04-resources/03-route-configuration.md, "`weighted_clusters`"

### [low] RLS config and picker non-conformances

- **Item:** R133
- **Summary:** Smaller differences in limits, config validation, and pick results.
- **Description:**
  - Limits and durations:
    - `cacheSizeBytes` is capped at 40 MiB instead of 5 MiB.
    - Negative durations are accepted.
  - Config validation:
    - Duplicates among `extraKeys` values are not detected.
    - Empty header and constant keys are rejected only by accident.
    - A change to `routeLookupChannelServiceConfig` alone does not recreate the control channel. (Depends on open item RLS-12: the current spec does not cover this, and C++ behaves the same way. Keep this bullet only if RLS-12 resolves to (a); remove it if (b).)
  - Picker:
    - The method path is part of the cache key.
    - The backoff failure is a status error, so wait-for-ready RPCs fail (a drop) instead of waiting.
    - `x-google-rls-data` is added even when the header data is empty.
  - The first backoff delay is about 1.6 s instead of 1 s.
- **Evidence:** `balancer/rls/config.go` (`maxCacheSize`, `parseRLSProto`); `balancer/rls/internal/keys/builder.go` `MakeBuilderMap`; `balancer/rls/picker.go` (`Pick`, `delegateToChildPoliciesLocked`, `handleRouteLookupResponse`); `balancer/rls/balancer.go` `handleControlChannelUpdate`.
- **Spec:** `04-client-channel/lb-policies/rls.md`

### [low] Duplicate cluster specifier plugin names are not rejected

- **Item:** R133
- **Summary:** `processClusterSpecifierPlugins` keeps the last plugin when two have the same name. It should reject (NACK) the resource.
- **Description:** A RouteConfiguration with duplicate plugin names is accepted, and the earlier definition is silently overwritten. The spec, like C++, rejects the resource.
- **Evidence:** `internal/xds/xdsclient/xdsresource/unmarshal_rds.go` `processClusterSpecifierPlugins`.
- **Spec:** `09-xds/04-resources/03-route-configuration.md`, "Cluster Specifier Plugins"

### [low] LOGICAL_DNS cluster DNS error does not update the resolution note

- **Item:** XDS_RESOLVER-1
- **Summary:** On a DNS error after an earlier success, Go keeps the previous addresses (correct) but does not set the resolution note to the DNS error.
- **Description:** The spec requires that, on a DNS resolution failure for a LOGICAL_DNS cluster, the resolution note is set to the DNS resolver's note or to `DNS resolution failed for <host:port>: <status>`, whether or not previous endpoints are kept. Go keeps the previous addresses but leaves the note unchanged, so the failure is not surfaced in later RPC failure messages or debugging output.
- **Evidence:** grpc-go `internal/xds/xdsdepmgr/xds_dependency_manager.go` `onDNSError`.
- **Spec:** `09-xds/05-client.md`, "LOGICAL_DNS clusters"

## Fixed upstream or withdrawn

Bugs found during the spec work that have since been fixed upstream. Not to be filed.

- **Go [high]: server-side binary logs include the authorization header** (BINARY_LOG-3). Fixed by 40ef73b4, [grpc/grpc-go#9412](https://github.com/grpc/grpc-go/pull/9412) ("binarylog: omit the \"authorization\" header from logged metadata"), first in v1.85.0. grpc-go v1.82.0 through v1.84.x are affected.
- **Go, Java, C++ [low]: endpoint weight product overflow** (XDS_LB-1). Withdrawn: the spec adopted gRFC A113 (PICK_FIRST-1), whose normalized UQ1.31 weights cannot overflow. Go and Java use A113 by default; the C++ case is superseded by the C++ PICK_FIRST-1 bug (A113 off by default).
