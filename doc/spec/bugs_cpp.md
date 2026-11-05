# C++ implementation bugs

Bugs in gRPC C++ (C-core) found while writing and reviewing the gRPC spec in this directory: **171** entries, ordered by severity. Other lists: [Go](bugs_go.md), [Java](bugs_java.md), [documentation](bugs_docs.md).

Severity:

- **critical:** crash, data corruption, or a security weakness
- **high:** interoperability failure, or wrong behavior that users commonly hit
- **medium:** spec non-conformance with limited impact
- **low:** cosmetic, or a rare edge case

Each bug lists the review item that identified it (an item ID such as `RLS-4`, an `R<n>` number from the original review list, or "incidental"/"audit"), a summary, a description, evidence (code locations), and the spec section it violates. Open questions are in [review_items.md](review_items.md). None of these bugs has been filed yet.

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
- **Spec:** 02-rpc-semantics/README.md, "Codecs and Content-Subtype"

### [critical] Possible abort when a referenced cluster specifier plugin is removed

- **Also identified by:** XDS_ROUTING-4 resolution
- **Item:** R133
- **Summary:** `XdsResolver::CreateServiceConfig` reads `current_config_->route_config->cluster_specifier_plugin_map.at(name)` for every plugin entry in the cluster reference map, including entries that only an old ConfigSelector or an in-flight call still references.
- **Description:** When an RDS update removes or renames a plugin, the old ConfigSelector stays alive until the channel switches to the new one, and in-flight calls also keep it alive. Its plugin cluster reference therefore stays in `cluster_ref_map_`. `std::map::at` on the missing name then throws `out_of_range`, which aborts in builds with exceptions disabled. The spec requires the cluster reference to keep the plugin's last LB config. Java and Go both do this. Not yet confirmed with a test.
- **Evidence:** `src/core/resolver/xds/xds_resolver.cc` `XdsResolver::CreateServiceConfig` (the `ConsumePrefix(&cluster_name, "cluster_specifier_plugin:")` branch), `GenerateResult`, and `RouteConfigData::AddRouteEntry` (`maybe_add_cluster` with an empty subscription name).
- **Spec:** `09-xds/05-client.md`, "Cluster references and two-phase removal"

### [critical] xDS server aborts the process when a listening port cannot be bound after start

- **Item:** XDS_SERVER-3; incidental (investigation of old item 199)
- **Summary:** If binding a listening port fails after `Start()` has returned, the xDS-enabled server aborts the process instead of entering not serving.
- **Description:** C++ binds the listening port only once the xDS config arrives, after `Start()` has returned. If `grpc_tcp_server_add_port` fails then (e.g. the port is in use by another process), the code logs and calls `GRPC_CHECK(0)` (with a TODO noting the assert would not be needed if the port were bound earlier). The spec (and gRFC A36) require the address to enter not serving, notify the application, and retry binding periodically; a bind failure MUST NOT terminate the process. Impact: a port conflict, possibly transient, crashes the whole server process.
- **Evidence:** grpc `src/core/ext/transport/chttp2/server/chttp2_server.cc` (~lines 596-605, `grpc_tcp_server_add_port` error → `GRPC_CHECK(0)`).
- **Spec:** 09-xds/08-server.md, "Port Binding Failures"

### [critical] RLS cache-size gauges race with config updates and can read freed memory

- **Item:** audit (W2-09-013)
- **Summary:** The callback for the `grpc.lb.rls.cache_entries` and `grpc.lb.rls.cache_size` gauges reads the policy's config while holding only the policy mutex, but config updates replace the config without that mutex. A metrics scrape that overlaps a config update is a data race and can use the old config after it is freed.
- **Description:** The policy's config pointer is documented as accessed only from the policy's serializer, and each update replaces it there without taking the policy mutex. The gauge callback runs on the metrics-collection thread, takes only the policy mutex, and reads the config to get the `lookupService` label. If an update replaces the config during a scrape, the callback can read the pointer while it is being written, or use the `lookupService` string of the old config after the update releases its last reference. Only applications that enable the RLS gauges (experimental, off by default) can hit this, and only when a scrape overlaps a config update.
- **Evidence:** grpc 515aaa1743: [rls.cc L725-L728](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L725-L728), [rls.cc L1388-L1399](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L1388-L1399), [rls.cc L1915-L1920](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L1915-L1920), [rls.cc L2025-L2033](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L2025-L2033)
- **Spec:** `04-client-channel/lb-policies/rls.md`, "Metrics"

### [critical] `CertificateValidationContext.match_typed_subject_alt_names` is silently ignored (SAN verification fails open)

- **Item:** XDS_SECURITY-20
- **Summary:** `CertificateValidationContextParse` never reads `match_typed_subject_alt_names`, so a resource that sets it is ACKed and the SAN matchers are not applied.
- **Description:** The spec requires a NACK when `match_typed_subject_alt_names` is non-empty, because the field isn't supported and ignoring it compromises security (the A29 rule). Envoy deprecated `match_subject_alt_names` in favor of this field. A control plane that sets only `match_typed_subject_alt_names` on an `UpstreamTlsContext` (without `auto_sni_san_validation`) gets a client that accepts any certificate chaining to the CA. If both fields are set, gRPC checks the deprecated list, which Envoy ignores. On the server side, the field is silently dropped as well.
- **Evidence:** grpc 515aaa1743: [xds_tls_context_parser.cc L92-L157](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_tls_context_parser.cc#L92-L157)
- **Spec:** xDS Security: `CommonTlsContext` Validation (`09-xds/09-security.md`)

### [high] Aggregate cluster leaf list omits clusters already visited from another root cluster

- **Item:** XDS_DEPMGR-2
- **Summary:** C++ XdsDependencyManager uses one visited set for all root clusters, so a cluster already in the XdsConfig cluster map adds nothing to a later aggregate's leaf list.
- **Description:** With roots `a` (EDS) and `b` (aggregate `[a, c]`), `b`'s leaf list is `[c]`, so `b`'s primary cluster is lost. If `b` is `[a]` alone, `b` gets "aggregate cluster dependency graph for b has no leaf clusters" and its RPCs fail. The same thing happens when two aggregates share a leaf or a nested aggregate. gRFC A37 expects a cluster that is used directly and through an aggregate to stay in the aggregate's list. Java and Go include it.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_dependency_manager.cc#L675-L677, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_dependency_manager.cc#L905-L908 (`PopulateClusterConfigMap`: emplace fails → return true with no leaves appended)
- **Spec:** Client Data Plane: Aggregate cluster graph

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

### [high] Failures from custom call credentials plugins always become UNAVAILABLE

- **Item:** audit (W2-10-020)
- **Summary:** When an application's metadata credentials plugin fails, C++ discards the plugin's status code and fails the attempt with `UNAVAILABLE`.
- **Description:** A call credential that fails should fail the attempt with its own status. Codes reserved for the control plane (`INVALID_ARGUMENT`, `NOT_FOUND`, `ALREADY_EXISTS`, `FAILED_PRECONDITION`, `ABORTED`, `OUT_OF_RANGE`, `DATA_LOSS`) are rewritten to `INTERNAL` with the original code and message. C++ converts every plugin failure to `UNAVAILABLE` before the restriction check runs. A plugin's `UNAUTHENTICATED` or `PERMISSION_DENIED` therefore reaches the application as `UNAVAILABLE`, which looks transient and may be retried by the retry policy or by the application. Restricted codes also become `UNAVAILABLE` instead of `INTERNAL`.
- **Evidence:** grpc 515aaa1743: [plugin_credentials.cc L64-L71](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/call/plugin/plugin_credentials.cc#L64-L71), [auth_filters.h L60-L68](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/filter/auth/auth_filters.h#L60-L68)
- **Spec:** `06-security/03-call-credentials.md`, "1.3 Results"

### [high] GCP authentication filter keeps using stale CDS data after cluster-only updates

- **Item:** audit (W2-17-002)
- **Summary:** The xDS HTTP filter chain is rebuilt only when the Listener or RouteConfiguration changes. A CDS-only update, such as a new audience in `Cluster.metadata` or a cluster recovering from an error, never reaches the GCP authentication filter.
- **Description:** The GCP authentication filter reads the audience from the RPC's cluster in the current `XdsConfig`, and fails the RPC with `UNAVAILABLE` if that cluster's CDS resource is not available. C++ gives the filter the `XdsConfig` that was current when the filter chain was built. The channel rebuilds the chain only when the service config or the ConfigSelector changes. The ConfigSelector equality check compares only the Listener and RouteConfiguration, and the generated service config contains only cluster names. A CDS update alone therefore leaves the old filter instance in place. It keeps minting tokens for the old audience, or, if the cluster first had an error, keeps failing every RPC with `UNAVAILABLE` after the cluster becomes valid. This continues until an unrelated Listener or RouteConfiguration change.
- **Evidence:** grpc 515aaa1743: [xds_resolver.cc L252-L259](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_resolver.cc#L252-L259), [client_channel_filter.cc L1247-L1270](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_filter.cc#L1247-L1270), [client_channel.cc L1214-L1244](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L1214-L1244), [gcp_authentication_filter.cc L73-L92](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/gcp_authentication/gcp_authentication_filter.cc#L73-L92), [gcp_authentication_filter.cc L177](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/gcp_authentication/gcp_authentication_filter.cc#L177)
- **Spec:** `09-xds/07-http-filters.md`, "11.3 Per-RPC Behavior"

### [high] xDS TLS handshakes fail when auto_sni_san_validation is set but no SNI applies

- **Item:** audit (W2-18-016)
- **Summary:** With `auto_sni_san_validation` true and no SNI chosen (for example `auto_host_sni` with an endpoint that has no hostname, and empty `sni`), C++ checks the server's DNS SANs against an empty name. Every handshake fails, instead of falling back to `match_subject_alt_names`.
- **Description:** The SNI-based SAN check applies only when an SNI was sent. Otherwise, the SANs are checked against `match_subject_alt_names`, which succeeds when that list is empty. C++ applies the SNI-based check whenever `auto_sni_san_validation` is true, using the empty string when no SNI was chosen. No certificate has a matching SAN, so the handshake fails with `UNAUTHENTICATED` ("SANs from certificate did not match SNI from xDS control plane"), and the cluster is unusable. Java and Go fall back to `match_subject_alt_names` in this case.
- **Evidence:** grpc 515aaa1743: [xds_credentials.cc L82-L95](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/xds/xds_credentials.cc#L82-L95), [xds_credentials.cc L176-L196](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/xds/xds_credentials.cc#L176-L196)
- **Spec:** `09-xds/09-security.md`, "3. Server Identity Verification"

### [high] RBAC header matchers with uppercase names never match

- **Item:** audit (W2-11-009)
- **Summary:** C++ looks up the header named in an RBAC or gRPC authorization policy header matcher case-sensitively, so a matcher whose name has uppercase letters never finds the (lowercase) request header. The xDS RBAC check that rejects `:scheme` and `grpc-` header matchers is also case-sensitive.
- **Description:** Header names in RBAC matching are case-insensitive, because HTTP/2 header names are lowercase on the wire. C++ does not lowercase the configured name, and it looks the name up in the request metadata with an exact comparison. A matcher on `Authorization` or `X-User` therefore behaves as if the header were absent. A DENY rule on it never fires (fail open), an ALLOW rule never matches, and an inverted or `present_match: false` matcher always matches. For xDS RBAC, a header matcher on `:Scheme` or `GRPC-foo` is accepted instead of NACKed.
- **Evidence:** grpc 515aaa1743: [evaluate_args.cc L125-L139](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/evaluate_args.cc#L125-L139), [metadata_batch.cc L115-L128](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/metadata_batch.cc#L115-L128), [matchers.cc L146-L150](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/matchers.cc#L146-L150), [xds_http_rbac_filter.cc L115-L119](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L115-L119), [xds_http_rbac_filter.cc L632-L636](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L632-L636)
- **Spec:** `06-security/04-authorization.md`, "1.3 Header Matching Rules"; `09-xds/07-http-filters.md`, "9.1 Configuration Validation"

### [medium] Retries on the v3 call stack skip transparent retries and retry LB drops

- **Item:** audit (W2-09-006)
- **Summary:** On channels that use the v3 call stack (`GRPC_ARG_USE_V3_STACK`, used by the chaotic_good and inproc transports), the retry layer never transparently retries attempts that did not reach the server, and it retries LB drops whose status is in `retryableStatusCodes`.
- **Description:** The spec says an attempt that failed before anything reached the network is transparently retried until success or the deadline. An attempt that reached the server's gRPC library but not the application (`REFUSED_STREAM`, or a `GOAWAY` below the stream ID) is transparently retried once. An attempt whose pick result is Drop fails the RPC immediately with no retries of any kind. On the v3 stack, `RetryInterceptor` decides retries only from `grpc-status`, pushback, throttling, and `maxAttempts`. It never looks at the stream's network state, so these failures go to the configured retry policy, or fail the RPC when there is none. The v3 LB pick path does not mark dropped calls (a `TODO` says the drop trait still needs to be set), so a drop with a retryable code such as `UNAVAILABLE` is retried with backoff. The legacy `RetryFilter` (the default stack) handles both cases.
- **Evidence:** grpc 515aaa1743: [retry_interceptor.cc L57-L130](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_interceptor.cc#L57-L130), [retry_interceptor.cc L277-L303](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_interceptor.cc#L277-L303), [load_balanced_call_destination.cc L176-L186](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/load_balanced_call_destination.cc#L176-L186), [retry_filter_legacy_call_data.cc L1093-L1120](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_filter_legacy_call_data.cc#L1093-L1120)
- **Spec:** `04-client-channel/12-retries.md`, "Behavior" and "Transparent Retries"

### [medium] Service config and xDS timeouts are not sent in `grpc-timeout`

- **Item:** audit (W2-01-010)
- **Summary:** When a method config `timeout` (or an xDS route `max_stream_duration`) shortens or sets a call's deadline, C++ enforces it locally but does not send it. The request carries the application's looser `grpc-timeout`, or none.
- **Description:** The effective deadline is the earliest of the application deadline and the per-call configuration timeout, and the client MUST send the deadline in the request headers. C++ sets `grpc-timeout` from the application deadline when the call's initial metadata is prepared. When the client channel applies the method config later, it only re-arms the local deadline timer and does not update the outgoing timeout. The server never learns the shorter deadline (or any deadline, if the application set none), so it keeps working after the client has given up. Java and Go send the tightened deadline.
- **Evidence:** grpc 515aaa1743: [filter_stack_call.cc L799-L801](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/surface/filter_stack_call.cc#L799-L801), [client_channel_filter.cc L185-L191](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_filter.cc#L185-L191), [client_channel_filter.cc L1853-L1858](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_filter.cc#L1853-L1858), [client_channel.cc L1485-L1491](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L1485-L1491), [call.cc L369-L391](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/surface/call.cc#L369-L391)
- **Spec:** `02-rpc-semantics/README.md`, "8.1 Effective Deadline" and "8.2 Communication and Enforcement"

### [medium] Server reflection responses accumulate data from earlier requests on the same stream

- **Item:** audit (W2-12-009)
- **Summary:** The reflection service reuses one response message for every request on a stream without clearing it. Consecutive requests of the same kind get the previous responses' entries plus their own.
- **Description:** Each `ServerReflectionResponse` should answer only its own request. C++ builds every response in a single message that lives for the whole stream and only appends to its repeated fields. Two `list_services` requests in a row return every service twice on the second response, and so on. Consecutive `all_extension_numbers_of_type` requests return the earlier types' extension numbers under the new `base_type_name`. Consecutive file, symbol, or extension queries return the earlier responses' descriptors first, so the requested file is not first in the list. A request of a different kind resets the message because it switches the response oneof. Java and Go build a new response for each request.
- **Evidence:** grpc 515aaa1743: [proto_server_reflection.cc L35-L74](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/proto_server_reflection.cc#L35-L74), [proto_server_reflection.cc L84-L93](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/proto_server_reflection.cc#L84-L93), [proto_server_reflection.cc L153-L193](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/proto_server_reflection.cc#L153-L193)
- **Spec:** `07-services/02-reflection.md`, "3. Requests" and "4. File Descriptor Semantics"

### [medium] No option to fail closed when revocation status is undetermined

- **Item:** audit (W2-10-015)
- **Summary:** With a CRL provider configured, C++ always treats a certificate whose issuer has no CRL as unrevoked. Applications cannot make the handshake fail in that case.
- **Description:** The spec requires TLS credentials to have a policy for the `Undetermined` revocation status (no CRL found for the issuer): treat it as `Revoked` (fail closed) or `Unrevoked` (fail open), chosen by the application. C++ hard-codes fail-open, with a TODO to add an option, and the TLS credentials API has no such setting. Applications that need strict revocation checking cannot get it, and a missing or not-yet-loaded CRL silently allows the connection.
- **Evidence:** grpc 515aaa1743: [ssl_transport_security.cc L1803-L1821](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/tsi/ssl_transport_security.cc#L1803-L1821)
- **Spec:** `06-security/02-tls.md`, "9.2 Revocation Status" and "13. API Requirements"

### [medium] OpenTelemetry span names use `/` between service and method

- **Item:** audit (W2-13-008)
- **Summary:** C++ names tracing spans `Sent.<service>/<method>`, `Attempt.<service>/<method>`, and `Recv.<service>/<method>` instead of using `.` between service and method.
- **Description:** Span names must be `Sent.<service>.<method>`, `Attempt.<service>.<method>`, and `Recv.<service>.<method>`. For example, the client call span for `/helloworld.Greeter/SayHello` is `Sent.helloworld.Greeter.SayHello`. C++ strips the leading `/` from the path but keeps the `/` between service and method, and its tests expect that form. Traces from C++ use different span names from Java and Go, which breaks span-name queries and dashboards across languages.
- **Evidence:** grpc 515aaa1743: [otel_plugin.cc L969-L973](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_plugin.cc#L969-L973), [otel_client_call_tracer.cc L162](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_client_call_tracer.cc#L162), [otel_client_call_tracer.cc L492](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_client_call_tracer.cc#L492), [otel_server_call_tracer.cc L152](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_server_call_tracer.cc#L152), [otel_tracing_test.cc L157-L164](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/test/cpp/ext/otel/otel_tracing_test.cc#L157-L164)
- **Spec:** `08-observability/05-tracing.md`, "1. Span Structure"

### [medium] Channelz cannot return internal child channels and leaves them out of channel_ref

- **Item:** audit (W2-14-005)
- **Summary:** `GetChannel` on the ID of an internal child channel (such as an RLS or grpclb control-plane channel) fails with `INTERNAL`, and parent channels and subchannels never list internal child channels in `channel_ref`.
- **Description:** `GetChannel` must return any channel, top-level or child. A channel's child channels appear in its `channel_ref` list. C++ builds Channelz v1 responses by converting its internal v2 entities, and internal channels have the kind `internal_channel`. The converter accepts only the top-level channel kind. A `GetChannel` for an internal channel therefore fails with `INTERNAL` ("Entity kind is not channel or top_level_channel"). When it lists a parent's children, the converter adds only top-level-kind channels to `channel_ref`, so internal child channels are missing from the entity graph. Tools that walk the graph cannot reach control-plane channels.
- **Evidence:** grpc 515aaa1743: [channelz.h L163-L170](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/channelz.h#L163-L170), [convert.cc L535-L540](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/v2tov1/convert.cc#L535-L540), [convert.cc L559-L564](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/v2tov1/convert.cc#L559-L564), [convert.cc L613-L618](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/v2tov1/convert.cc#L613-L618), [channelz_service.cc L181-L200](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/channelz/channelz_service.cc#L181-L200)
- **Spec:** `08-observability/06-channelz.md`, "3. Entity Graph" and "8. The Channelz Service"

### [medium] xDS RBAC audit logging is off unless an experimental environment variable is set

- **Item:** audit (W2-11-010, W2-18-007)
- **Summary:** C++ ignores `RBAC.rules.audit_logging_options` in the xDS RBAC filter unless `GRPC_EXPERIMENTAL_XDS_RBAC_AUDIT_LOGGING` is set to true. By default, audit logging configured through xDS produces no audit records, and invalid audit configuration is not NACKed.
- **Description:** The spec requires xDS RBAC to apply `audit_logging_options`: invoke the configured loggers when the decision meets `audit_condition`, and NACK an unknown `audit_condition` or a missing or unsupported logger. In C++ both the filter config parser and the per-route override parser skip the field entirely unless the environment variable is set (the code carries a TODO to remove the guard once the feature is stable). Audit logging through gRPC authorization policy JSON is not gated. Go applies xDS RBAC audit logging unconditionally. Fix: enable by default and remove the guard.
- **Evidence:** grpc 515aaa1743: [xds_http_rbac_filter.cc L471-L473](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L471-L473), [xds_http_rbac_filter.cc L895-L897](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L895-L897), [experiment_env_var.h L22](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/config/experiment_env_var.h#L22)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), "Audit Logging Configuration"

### [medium] New-style resource names with an empty authority are sent without the `//`

- **Item:** audit (W2-15-004)
- **Summary:** For an `xdstp:` resource name whose authority is empty (for example `xdstp:///envoy.config.listener.v3.Listener/foo`), C++ re-serializes the name as `xdstp:/envoy.config.listener.v3.Listener/foo` in ADS requests and in CSDS output.
- **Description:** New-style names have the form `xdstp://[<authority>]/<resource type>/<id>[?<context params>]`, and the XdsClient puts the normalized form of the name in `DiscoveryRequest`. C++ rebuilds the name from its parts with a generic URI builder that treats an empty authority as "no authority" and drops the `//`. A control plane that matches the requested name as a string sees a different name than the one configured, and may never send the resource. The bootstrap explicitly supports the empty authority (key `""` in `authorities`).
- **Evidence:** grpc 515aaa1743: [xds_client.cc L1901-L1913](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/xds_client/xds_client.cc#L1901-L1913), [uri.cc L403-L414](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/util/uri.cc#L403-L414)
- **Spec:** XdsClient (`09-xds/03-xds-client.md`), "Old-style and new-style names"

### [medium] C++ ring_hash does not validate requestHashHeader

- **Item:** RING_HASH-5
- **Summary:** C++ accepts any `requestHashHeader` string. A `-bin` name or an invalid name is not rejected, and a name with uppercase letters never matches, so every call gets a random hash.
- **Description:** `RingHashLbConfig::JsonPostLoad` validates only the ring sizes. The picker looks up the configured name in the metadata exactly as written. gRFC A76 requires rejecting the config if the name is not a valid header name or ends in `-bin`.
- **Evidence:** [ring_hash.cc#L113-L143](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L113-L143), [ring_hash.cc#L318-L328](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L318-L328)
- **Spec:** `ring_hash` LB Policy: Configuration

### [medium] C++ server keepalive does not ping idle connections by default

- **Item:** TRANSPORT-3
- **Summary:** By default, C++ servers send keepalive PINGs only while the connection has active streams.
- **Description:** `g_default_server_keepalive_permit_without_calls` is `false`, and the keepalive timer pings only if `keepalive_permit_without_calls || !stream_map.empty()`; otherwise it re-arms. gRFC A9 says server keepalives take place whether or not there are outstanding RPCs, and Java and Go do this. With the default, a C++ server never detects a dead idle client and keeps half-open connections until TCP gives up. Setting `GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS=1` on the server gives the A9 behavior. When fixed, update the server default in doc/keepalive.md.
- **Evidence:** [chttp2_transport.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L155-L156), [chttp2_transport.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L3298-L3313)
- **Spec:** HTTP/2 Server Transport: Keepalive

### [medium] C++: server compresses with an algorithm the client did not list in grpc-accept-encoding

- **Item:** COMPRESSION-3
- **Summary:** The server uses the handler's or server default algorithm without checking the client's `grpc-accept-encoding`.
- **Description:** `HandleOutgoingMetadata` uses `grpc-internal-encoding-request` (from `ServerContext::set_compression_algorithm`) or the default algorithm and sets `grpc-encoding` without consulting the peer's accepted encodings. Only the compression-level path picks from `encodings_accepted_by_peer`. A C++ server with a default of gzip makes every response fail with `INTERNAL` on a client that lacks gzip. Fix: send the message uncompressed when the client did not list the algorithm.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/message_compress/compression_filter.cc#L216-L227, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/server_context.cc#L509-L519, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/surface/call.cc#L300-L309
- **Spec:** 2. Core RPC Semantics: 13.2 Negotiation; gRPC over HTTP/2 (compression error handling)

### [medium] C++: client KEEPALIVE_TIME below 10 seconds is not raised to 10 seconds

- **Item:** TRANSPORT-1
- **Summary:** C++ accepts any client `GRPC_ARG_KEEPALIVE_TIME_MS` of 1 ms or more, so a misconfigured client can ping very often and be disconnected with `too_many_pings`.
- **Description:** gRFC A8 and the spec require client `KEEPALIVE_TIME` values below 10 seconds to be raised to 10 seconds. C++ clamps only to at least 1 ms, both in the chttp2 transport and in the client channel's initial value. Java and Go raise the value to 10 s.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L441-L445 ; https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L664-L667
- **Spec:** HTTP/2 Client Transport: Keepalive

### [medium] C++: stdout_logger audit lines are not JSON-escaped

- **Item:** AUTHZ-7
- **Summary:** C++ builds the stdout audit log line with a printf format string, so client-controlled values (such as `:path`) containing `"` produce invalid JSON or forged fields such as `"authorized":true`.
- **Description:** `kLogFormat` is `{"grpc_audit_log":{"timestamp":"%s","rpc_method":"%s",...}}` filled by `absl::FPrintF` with the raw method, principal, policy name and rule name. HTTP/2 allows `"` in `:path`, and authorization runs for unknown methods too, so a client can inject content into a security audit record. Go uses `json.Marshal`.
- **Evidence:** [stdout_logger.cc L38-L49](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/stdout_logger.cc#L38-L49)
- **Spec:** Authorization: Built-in `stdout_logger`

### [medium] Legacy Cluster lb_policy LEAST_REQUEST is rejected

- **Item:** XDS_CDS-2
- **Summary:** C++ rejects a Cluster whose legacy `lb_policy` is `LEAST_REQUEST` ("LB policy is not supported").
- **Description:** The spec (per A48/A52) accepts legacy `LEAST_REQUEST` (reading `least_request_lb_config`) and converts it to `xds_wrr_locality_experimental` wrapping `least_request_experimental`. C++ handles only ROUND_ROBIN and RING_HASH in the legacy path and NACKs everything else, so the same Cluster that Java and Go accept is NACKed.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L332-L397
- **Spec:** Cluster: Legacy `lb_policy`

### [medium] C++ subchannel metrics use the default authority for grpc.target

- **Item:** METRICS-4
- **Summary:** C++ labels subchannel metrics with the channel's default authority (e.g. `host:443`) instead of the canonical target URI.
- **Description:** The spec requires `grpc.target` on `grpc.subchannel.*` metrics to be the creating channel's canonical target URI, matching per-call metrics. C++ uses `GRPC_ARG_DEFAULT_AUTHORITY`. Fixing this needs care with the global subchannel pool: sharing already requires equal subchannel args, so the canonical target would need to be part of the key (or otherwise carried) to keep the "creating channel's target" rule.
- **Evidence:** grpc `src/core/client_channel/subchannel.cc` (metric labels from `GRPC_ARG_DEFAULT_AUTHORITY`)
- **Spec:** Metric Catalog: Subchannel Metrics

### [medium] StringMatcher with safe_regex and ignore_case=true is rejected

- **Item:** XDS_ROUTING-2
- **Summary:** C++ NACKs any resource that has a `StringMatcher` with `safe_regex` and `ignore_case: true`. The spec (and gRFC A63) says `ignore_case` is ignored for regex matches.
- **Description:** `ignore_case` applies only to `exact`, `prefix`, `suffix`, and `contains`, and has no effect on `safe_regex`. C++ rejects the combination with "not supported for regex matcher", so it NACKs route configs (header matchers) and RBAC policies that Java and Go accept. Note: Envoy also rejects this combination, despite its proto comment.
- **Evidence:** src/core/xds/grpc/xds_common_types_parser.cc (StringMatcher parsing)
- **Spec:** xDS Common Types: `StringMatcher`

### [medium] Client "max pings without data" throttle on by default

- **Item:** R8
- **Summary:** C++ clients throttle keepalive pings to one per minute after 2 pings with no data sent (GRPC_ARG_HTTP2_MAX_PINGS_WITHOUT_DATA default 2), which the spec does not allow.
- **Description:** The spec defines no client-side limit on pings sent without data; a client with keepalive enabled pings every KEEPALIVE_TIME. C++ has a client-only limit, default 2, after which pings are throttled to 1/minute. This can break KEEPALIVE_WITHOUT_CALLS configurations with short keepalive times, and C++'s own doc/keepalive.md notes the conflict. The default should be 0 (no limit).
- **Evidence:** grpc `src/core/ext/transport/chttp2/transport/ping_rate_policy.cc`; `doc/keepalive.md`.
- **Spec:** 04-client-channel/08-transports/02-http2.md, "Keepalive" / "API Requirements"

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
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), "Behavior" and "Token Accounting".

### [medium] Disabling retries also disables transparent retries

- **Item:** R45
- **Summary:** With `grpc.enable_retries=0`, the retry layer is left out of the stack, so transparent retries stop too, but the spec says they SHOULD continue.
- **Description:** Transparent retries happen inside the retry filter/interceptor. When retries are disabled on the channel, that component isn't installed, so attempts refused before reaching the server application fail straight to the application. The spec says transparent retries SHOULD still happen when retries are disabled. Users see spurious `UNAVAILABLE` errors during server graceful shutdown or stream refusal.
- **Evidence:** `src/core/client_channel/client_channel.cc`, `src/core/client_channel/client_channel_filter.cc` (retry filter installed only when retries are enabled).
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), "Transparent Retries" and "Limits and Disabling Retries".

### [medium] Server silently ignores extra request messages on unary-request methods

- **Item:** R98, R105
- **Summary:** The C++ server does not fail a unary or server-streaming RPC when the client sends more than one request message.
- **Description:** For unary-request methods the C++ server reads one request message and silently ignores any further ones, so the handler runs as if the call were valid. The spec requires the server to fail the RPC with `INTERNAL` when the client sends zero or more than one request message on a unary-request method. Java and Go both reject extra requests with `INTERNAL`. A misbehaving client gets no signal that it is violating the method's cardinality, and data it sent is dropped.
- **Evidence:** `include/grpcpp/support/method_handler.h` (unary/server-streaming handlers read a single message; only the zero-message case fails, with `INTERNAL`, ~L291); `include/grpcpp/support/proto_buffer_reader.h`.
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), "Unary Calls"; Server (`05-server/01-server.md`), "Request Cardinality".

### [medium] Client response-cardinality violations not reported as INTERNAL

- **Item:** R98
- **Summary:** The C++ client reports `UNIMPLEMENTED` (sync blocking unary only), reports OK for zero responses, or hangs on more than one response, instead of failing with `INTERNAL`.
- **Description:** In the synchronous blocking unary path the C++ client fails a call that ended OK without a response message with `UNIMPLEMENTED`. In the other unary-response paths (async, callback, client-streaming), zero responses with status OK are reported to the application as OK, and more than one response can hang the call (grpc/grpc#36769). The spec requires the client to fail the call with `INTERNAL` when the server sends zero messages with OK, or more than one message, on a unary-response method. Applications may see a successful call with an empty/default response, or a hung RPC.
- **Evidence:** `include/grpcpp/impl/client_unary_call.h` (~L88-90, `StatusCode::UNIMPLEMENTED`); grpc/grpc#36769.
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), "Unary Calls".

### [medium] Out-of-range GRPC_ALLOW_TRUE_BINARY_METADATA value fails the connection

- **Item:** R122
- **Summary:** A `GRPC_ALLOW_TRUE_BINARY_METADATA` (0xfe03) value greater than 1 is treated as a connection `PROTOCOL_ERROR` instead of as 0.
- **Description:** `Http2Settings::Apply` returns `Http2ErrorCode::kProtocolError` for values above 1, which tears down the whole connection. The setting ID is in the HTTP/2 experimental range and may be used by another extension, so a peer sending a different value is not necessarily misbehaving. The spec requires values other than 0 and 1 to be treated as 0 (feature off) and not as a connection error. Impact is limited to peers running a colliding extension.
- **Evidence:** `src/core/ext/transport/chttp2/transport/http2_settings.cc`, `Http2Settings::Apply`, case `kGrpcAllowTrueBinaryMetadataWireId`: `if (value > 1) return Http2ErrorCode::kProtocolError;`
- **Spec:** 03-wire-protocol/02-true-binary-metadata.md, "Setting"

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

### [medium] Server rejects an unknown request `grpc-encoding` with `INTERNAL`, and does not reject a disabled one

- **Item:** audit (W2-02-007); related: COMPRESSION-4
- **Summary:** A request whose `grpc-encoding` names an algorithm C++ does not know fails with `INTERNAL` instead of `UNIMPLEMENTED`. A request whose `grpc-encoding` names a known but disabled algorithm is not rejected at all unless a compressed message arrives.
- **Description:** The spec requires the server to fail the call with `UNIMPLEMENTED` when the request's `grpc-encoding` header names an algorithm it does not support or has not enabled (the rule is triggered by the header, not by a received message). In C++, an unknown value fails metadata parsing in the HPACK parser, which fails the stream with `INTERNAL` ("Error parsing 'grpc-encoding' metadata") before the compression filter sees it. For a known algorithm that the server has disabled, the server compression filter only records the algorithm from the headers; the enabled-set check happens when a compressed message is decompressed (and then returns `UNIMPLEMENTED`), so a call with no compressed messages succeeds.
- **Evidence:** grpc 515aaa1743: [metadata_batch.cc L308-L316](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/metadata_batch.cc#L308-L316), [hpack_parser.cc L1042-L1050](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/hpack_parser.cc#L1042-L1050), [hpack_parse_result.cc L123-L128](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/hpack_parse_result.cc#L123-L128), [compression_filter.cc L271-L276](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/message_compress/compression_filter.cc#L271-L276), [compression_filter.cc L186-L194](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/message_compress/compression_filter.cc#L186-L194)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), "Errors"; gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), "`grpc-encoding` and `grpc-accept-encoding`"; Server Behavior (`05-server/01-server.md`), "Compression"

### [medium] Method config name with `"service": ""` and a method is accepted as the default for all methods

- **Item:** audit (W2-04-015)
- **Summary:** A `methodConfig` name entry such as `{"service": "", "method": "Foo"}` is accepted and becomes the default method config for every RPC on the channel, instead of making the service config invalid.
- **Description:** The spec treats an absent `service` and `""` alike, and says an entry with an empty `service` and a non-empty `method` makes the service config invalid. C++ rejects the combination only when `service` is absent. With `"service": ""`, the entry passes validation and its path is computed as the empty path, which is the channel-wide default, so its settings (timeouts, retry policy, message limits) apply to all methods. Go and Java reject it.
- **Evidence:** grpc 515aaa1743: [service_config_impl.cc L58-L68](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/service_config/service_config_impl.cc#L58-L68)
- **Spec:** Service Config (`04-client-channel/04-service-config.md`), "`methodConfig`"

### [medium] `ring_hash` builds an empty ring and reads out of bounds when the ring size cap is 0

- **Item:** audit (W2-08-004)
- **Summary:** C++ does not raise a local ring size cap below 1 to 1. A cap of 0 produces an empty ring, and picks then index past the end of it. A negative cap disables the cap.
- **Description:** The spec says a ring size cap below 1 MUST be treated as 1. C++ reads the cap channel option and converts it to `size_t` without clamping. With 0, the minimum and maximum ring sizes become 0, no ring entries are created, and the picker's search ends at index 0 of the empty ring; when no endpoint is found, the failure message reads that entry, which is an out-of-bounds read. A negative value wraps to a huge `size_t`, so the cap has no effect.
- **Evidence:** grpc 515aaa1743: [ring_hash.cc L464-L471](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L464-L471), [ring_hash.cc L333-L357](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L333-L357), [ring_hash.cc L392-L394](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L392-L394)
- **Spec:** `ring_hash` LB Policy (`04-client-channel/lb-policies/ring_hash.md`), "Validation"

### [medium] Client call span never gets a status

- **Item:** audit (W2-13-009)
- **Summary:** The OpenTelemetry `Sent.<service>.<method>` client call span ends without a span status, so its status is always `UNSET`.
- **Description:** The spec says that when the call ends, the client call span's status is set to OK for gRPC status `OK` and to ERROR with `<CODE>: <message>` otherwise. C++ sets the status on the attempt span when each attempt ends, but the call tracer's destructor ends the call span without setting any status. Tracing backends therefore cannot tell failed calls from successful ones at the call level. Go sets the final RPC status on the call span.
- **Evidence:** grpc 515aaa1743: [otel_client_call_tracer.cc L496-L539](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_client_call_tracer.cc#L496-L539) (call span ended without status), [otel_client_call_tracer.cc L347-L354](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_client_call_tracer.cc#L347-L354) (attempt span status, for comparison)
- **Spec:** `08-observability/05-tracing.md`, "Client Call Span" and "Span Status"

### [medium] Channelz trace loses event count, creation time, severity, and child references

- **Item:** audit (W2-14-007)
- **Summary:** The Channelz service's `ChannelTrace` never sets `num_events_logged` or event `child_ref`, uses the oldest retained event's time as `creation_timestamp`, and reports every event as `CT_INFO`.
- **Description:** The spec says `ChannelTrace` reports the total number of events logged (including evicted ones) and the entity's creation time, and each event carries a severity and, when it concerns a child, a `channel_ref` or `subchannel_ref`. C++ builds the v1 response from its internal v2 trace, which keeps only a description and a timestamp per event. The conversion leaves `num_events_logged` at 0 and copies `creation_timestamp` from the first retained event, which moves forward as old events are evicted. It hardcodes `CT_INFO` for every event, including errors such as health-checking `UNIMPLEMENTED`, and never sets `child_ref`, so subchannel creation events have no `subchannel_ref`. The LB policy helper's `AddTraceEvent` also takes no severity, so components cannot provide one.
- **Evidence:** grpc 515aaa1743: [convert.cc L155-L185](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/v2tov1/convert.cc#L155-L185), [channel_trace.h L292-L296](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/channel_trace.h#L292-L296), [channelz.proto L57-L64](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/proto/grpc/channelz/v2/channelz.proto#L57-L64), [lb_policy.h L341-L342](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/lb_policy.h#L341-L342)
- **Spec:** `08-observability/06-channelz.md`, "Format", "Required Events", and "API Requirements"

### [medium] Channelz ids are not assigned in creation order

- **Item:** audit (W2-14-008)
- **Summary:** C++ assigns Channelz ids lazily, when an entity is first queried, so an older entity can get a larger id than a newer one.
- **Description:** The spec says an entity created later must have a larger id than every entity created earlier, so clients can infer relative age from ids. C++ registers new entities without an id in one of several sharded lists and assigns ids only when a query or reference first needs one. Queries visit the shards in random order and number entities in list order. Looking up a single entity (for example, through a child reference) numbers only that entity. As a result, ids do not follow creation order. Pagination still works, because entities numbered later get ids above all existing ones.
- **Evidence:** grpc 515aaa1743: [channelz_registry.cc L69-L75](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/channelz_registry.cc#L69-L75), [channelz_registry.cc L147-L215](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/channelz_registry.cc#L147-L215), [channelz_registry.cc L226-L247](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/channelz_registry.cc#L226-L247)
- **Spec:** `08-observability/06-channelz.md`, "Identifiers and References"

### [medium] Cluster with `failure_percentage_threshold` above 100 is accepted instead of NACKed

- **Item:** audit (W2-16-012)
- **Summary:** The Cluster parser checks the wrong field when it validates `outlier_detection.failure_percentage_threshold`, so a value above 100 is not rejected.
- **Description:** The spec requires `failure_percentage_threshold` ≤ 100 and says validation failures reject the resource. When `enforcing_failure_percentage` is non-zero, the parser reads `failure_percentage_threshold` but then tests `enforcing_failure_percentage > 100` again (already checked a few lines earlier) instead of testing the threshold. A Cluster with a threshold above 100 is therefore ACKed. The value is only rejected later, when the `outlier_detection` policy parses its generated config, so the cluster's RPCs fail with TRANSIENT_FAILURE instead of the client NACKing the resource and keeping the previous version. Java and Go NACK it.
- **Evidence:** grpc 515aaa1743: [xds_cluster_parser.cc L675-L685](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L675-L685) (checks `*enforcement_percentage`, not `*threshold`), [outlier_detection.cc L1192-L1195](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L1192-L1195) (later LB-config rejection)
- **Spec:** 09-xds/04-resources/04-cluster.md, "4. Outlier Detection"

### [medium] Fault injection aborts RPCs beyond `max_active_faults` when a delay was also chosen

- **Item:** audit (W2-18-005)
- **Summary:** If an RPC rolls both a delay and an abort while the active-fault limit is reached, the delay is skipped but the abort is still injected.
- **Description:** The spec says an abort is injected only if a delay was actually injected for the RPC, or the active-fault limit permits it. When the limit is reached, the filter correctly skips the delay, but it keeps the chosen delay duration. The abort check then sees a non-zero delay, assumes the RPC already holds an active-fault slot, and aborts it. Abort faults can therefore exceed `max_active_faults`, even when it is 0.
- **Evidence:** grpc 515aaa1743: [fault_injection_filter.cc L294-L308](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/fault_injection/fault_injection_filter.cc#L294-L308) (`DelayUntil` and `MaybeAbort`), [L206-L209](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/fault_injection/fault_injection_filter.cc#L206-L209) (call sequence)
- **Spec:** 09-xds/07-http-filters.md, "8.2 Per-RPC Algorithm"; 09-xds/07-http-filters.md, "8.5 Maximum Active Faults"

### [medium] Server Listener with listener filters is accepted instead of NACKed

- **Item:** audit (W2-18-010)
- **Summary:** The server-side Listener parser does not check `listener_filters`, so a Listener that configures listener filters such as `tls_inspector` is accepted and the filters are silently ignored.
- **Description:** The spec requires a server Listener's `listener_filters` to be empty and the resource to be NACKed otherwise. C++ never reads the field, so it accepts the Listener and serves without those filters. A control plane that relies on, for example, `tls_inspector` to populate SNI or ALPN for filter chain matching gets different matching behavior with no error. Java and Go NACK such Listeners.
- **Evidence:** grpc 515aaa1743: [xds_listener_parser.cc L915-L977](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_listener_parser.cc#L915-L977)
- **Spec:** 09-xds/08-server.md, "4. Listener Validation"

### [medium] xDS SAN matching skips email SANs and uses DNS rules for URI and IP SANs

- **Item:** audit (W2-18-018)
- **Summary:** When checking `match_subject_alt_names`, the xDS certificate verifier does not consider email SANs, and it uses DNS hostname matching (case-insensitive, with wildcards) for `exact` matchers on URI and IP SANs as well as DNS SANs.
- **Description:** The spec says DNS, URI, email, and IP address SANs are all considered, each matcher uses its usual `StringMatcher` semantics, and only for DNS SANs does an `exact` value also match a wildcard SAN. C++ checks URI, IP, and DNS SANs but not email SANs, even though the TLS layer provides them, so a certificate that matches only on an email SAN fails the handshake. For every `exact` matcher it calls the DNS hostname matcher whatever the SAN type, so URI and IP SANs are compared case-insensitively and with wildcard expansion, which can accept SANs that a plain exact match would reject.
- **Evidence:** grpc 515aaa1743: [xds_credentials.cc L42-L68](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/xds/xds_credentials.cc#L42-L68) (DNS rules for all `exact` matchers), [xds_credentials.cc L96-L110](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/xds/xds_credentials.cc#L96-L110) (no email SANs)
- **Spec:** 09-xds/09-security.md, "3. Server Identity Verification"

### [medium] Authorization policies cannot match the request's content-type

- **Item:** audit (W2-11-011)
- **Summary:** Header matchers on `content-type` in xDS RBAC and gRPC authorization policies never see the value the client sent. The server's HTTP filter removes the header before authorization runs.
- **Description:** The spec says the authorization engine matches `content-type` against the value the client sent. In C++, the transport parses `content-type` into an enum that keeps only "is gRPC", which loses any subtype such as `+proto`. The server HTTP filter then removes it from the metadata before the authorization filters run, and the engine's header lookup has no fallback. A matcher on `content-type` therefore sees the header as absent: positive matchers never match and `present_match: false` always matches. Go and Java expose the client-sent `content-type` to the engine.
- **Evidence:** grpc 515aaa1743: [metadata_batch.cc L132-L150](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/metadata_batch.cc#L132-L150), [http_server_filter.cc L112](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/server/http_server_filter.cc#L112), [evaluate_args.cc L125-L139](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/evaluate_args.cc#L125-L139)
- **Spec:** 06-security/04-authorization.md, "1.3 Header Matching Rules"; 09-xds/07-http-filters.md, "9.2 Mapping RBAC Fields to gRPC"

### [medium] Legacy xDS RBAC path lets plaintext connections match `authenticated` principals

- **Item:** audit (W2-11-013)
- **Summary:** With the `xds_server_filter_chain_per_route` experiment disabled, an RBAC `authenticated` principal with no `principal_name` matches every connection, including plaintext ones.
- **Description:** The spec says an `authenticated` principal never matches a non-TLS connection, and with no `principal_name` it matches any TLS connection. On the legacy path, xDS RBAC config is converted to service-config JSON and parsed by the RBAC service config parser. That parser turns an `authenticated` principal with no `principal_name` into an "any" principal and skips the transport security check. An ALLOW policy meant for TLS clients then also admits plaintext clients, and a DENY policy meant for TLS clients also denies plaintext ones. The default path, with the experiment enabled, requires TLS as specified.
- **Evidence:** grpc 515aaa1743: [rbac_service_config_parser.cc L637-L647](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/rbac/rbac_service_config_parser.cc#L637-L647), [xds_http_rbac_filter.cc L325-L338](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L325-L338) (legacy JSON generation), [xds_http_rbac_filter.cc L763-L781](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L763-L781) (default path)
- **Spec:** 06-security/04-authorization.md, "1.4 Authenticated Principal Matching"; 09-xds/07-http-filters.md, "9.2 Mapping RBAC Fields to gRPC"

### [medium] `ring_hash` with a ring size cap channel arg of 0 builds an empty ring and reads out of bounds on every pick; a negative cap disables the cap

- **Item:** audit (lbpol follow-up)
- **Summary:** C++ uses `GRPC_ARG_RING_HASH_LB_RING_SIZE_CAP` without clamping. A cap of 0 makes both ring sizes 0, so the ring is empty and the picker's failure path reads `ring[0]` of an empty vector (undefined behavior, typically a crash). A negative cap converts to a huge `size_t`, so no cap applies.
- **Description:** The spec says a cap below 1 MUST be treated as 1. Java (`RingHashOptions.setRingSizeCap` uses `Math.max(1, cap)`) and Go (`GRPC_RING_HASH_CAP` bounded to [1, 8 Mi]) clamp it. In C++, `BuildRing` computes `min_ring_size = min(config, cap)` and `max_ring_size = min(config, cap)`; with cap 0 the scale is 0 and no entries are added. `Pick` then finds no endpoint in the (empty) loops and builds the failure message from `endpoints_[ring[index].endpoint_index]` with `index == 0`. Only an application that sets the channel arg to 0 or a negative value is affected.
- **Evidence:** [ring_hash.cc L464-L473](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L464-L473) (cap use), [L333-L342](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L333-L342) and [L392-L394](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/ring_hash/ring_hash.cc#L392-L394) (picker).
- **Spec:** `ring_hash` LB Policy: Validation (Ring size cap)

### [medium] RBAC `CidrRange` with a non-IP or empty `address_prefix` accepted (fails open)

- **Item:** XDS_RBAC-22
- **Summary:** C++ accepts an RBAC `CidrRange` whose `address_prefix` is not an IP literal; the resulting matcher never matches, so a `DENY` rule silently allows traffic and a `not_rule`/`not_id` always matches.
- **Description:** The spec requires `address_prefix` in RBAC `destination_ip`, `source_ip`, `direct_remote_ip`, and `remote_ip` to be an IPv4 or IPv6 literal, else NACK. `ParseCidrRange` copies the fields without validation; `IpAuthorizationMatcher` logs at VLOG(2) and zeroes the subnet when the address doesn't parse, and the zeroed subnet has no address family, so it never matches.
- **Evidence:** grpc 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81: [xds_http_rbac_filter.cc L603-L611](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L603-L611), [matchers.cc L152-L165](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/matchers.cc#L152-L165)
- **Spec:** xDS HTTP Filters: RBAC: Configuration Validation

### [low] RLS does not forward resolver endpoint errors to its child policies

- **Item:** audit (W2-09-014)
- **Summary:** When an update's endpoints field is an error, the `rls` policy keeps its previous endpoints and passes them to its children instead of the error. If no endpoints were ever received, the children get a generic UNKNOWN error instead of the resolver's error.
- **Description:** The spec says that when the endpoints field of an update is an error, the `rls` policy forwards the error to every child. Each child then applies the normal endpoint-error rules: keep a previous list and return the error from its update, or report TRANSIENT_FAILURE with the error. C++ RLS instead keeps its last good endpoint list and updates every child with that list as if the update had succeeded. Children therefore return OK, and RLS's own update status does not reflect the resolver error, so a polling resolver does not retry with backoff. On the first update, the stored list is an empty status value, so children get a generic UNKNOWN error with no message. Their failing pickers then lack the resolver's error and resolution note.
- **Evidence:** grpc 515aaa1743: [rls.cc L725-L728](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L725-L728), [rls.cc L850-L858](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L850-L858), [rls.cc L1927-L1936](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L1927-L1936)
- **Spec:** `04-client-channel/lb-policies/rls.md`, "5.1 Child Policies"

### [low] Control-plane failures with status `OK` are not rewritten to `INTERNAL`

- **Item:** audit (W2-01-016)
- **Summary:** The channel's control-plane status check rewrites seven inappropriate codes to `INTERNAL` but not `OK`, so a picker Fail/Drop result, resolver error, or call-credentials failure that carries `OK` is passed through.
- **Description:** The spec lists `OK` among the codes that are inappropriate when a control-plane status reaches an RPC, and requires such statuses to be rewritten as `INTERNAL` with a message that includes the original code. C++ leaves `OK` unchanged. In the filter-stack client channel, a Fail pick that carries `OK` is then handled as a successful pick. Java includes `OK` in its set.
- **Evidence:** grpc 515aaa1743: [status_util.cc L128-L147](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/status_util.cc#L128-L147), [client_channel_filter.cc L2437-L2445](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_filter.cc#L2437-L2445)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), "Status Codes from the Control Plane"

### [low] Client fails the call on a 1xx informational response instead of skipping it

- **Item:** audit (W2-03-006)
- **Summary:** If a server or proxy sends a `1xx` header block (such as `100 Continue`) before the real response headers, the C++ client treats it as the response headers and fails the call.
- **Description:** The spec requires a client to skip any 1xx header block and read the next header block as the response headers (RFC 9113 §8.1). The C++ HTTP/2 transport has no 1xx handling: the first header block on a stream is always taken as the response headers and the second as trailers. The client HTTP filter then sees a non-200 `:status` with no `grpc-status` and fails the call with the status derived from the HTTP code.
- **Evidence:** grpc 515aaa1743: [parsing.cc L856-L880](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/parsing.cc#L856-L880), [parsing.cc L1083-L1090](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/parsing.cc#L1083-L1090), [http_client_filter.cc L59-L73](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/client/http_client_filter.cc#L59-L73)
- **Spec:** gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), "Informational (1xx) responses"

### [low] Address-literal resolvers split socket paths on commas and accept empty targets

- **Item:** audit (W2-04-016)
- **Summary:** The C++ resolver for `ipv4:`, `ipv6:`, `unix:`, `unix-abstract:` and `vsock:` splits the target path on `,` for every scheme and accepts targets with no address, producing an empty endpoint list.
- **Description:** For `unix`, `unix-abstract` and `vsock`, the spec says the result has one endpoint with one address; only `ipv4` and `ipv6` take a comma-separated list. C++ uses the same comma-splitting parser for all five schemes, so `unix:/tmp/a,b` becomes two addresses (`/tmp/a` and `b`) instead of one socket path. Empty elements are skipped and a target with no addresses (such as `ipv4:` or `unix:`) is accepted as valid, yielding zero endpoints instead of being rejected.
- **Evidence:** grpc 515aaa1743: [sockaddr_resolver.cc L74-L101](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/sockaddr/sockaddr_resolver.cc#L74-L101), [sockaddr_resolver.cc L137-L163](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/sockaddr/sockaddr_resolver.cc#L137-L163)
- **Spec:** Name Resolution (`04-client-channel/03-name-resolution.md`), "`unix`", "`unix-abstract`", "`vsock`", "`ipv4` and `ipv6`"

### [low] OOB backend metric stream keeps the old interval after the fastest watcher is removed

- **Item:** audit (W2-05-027)
- **Summary:** When the OOB watcher with the shortest reporting interval is removed, C++ keeps the stream running at that shorter interval instead of restarting it with the new, longer effective interval.
- **Description:** The effective interval is the smallest interval requested by the current watchers, and the stream must be restarted when it changes. C++ restarts the stream on watcher removal only if the new minimum is smaller than the current interval, which can never happen when a watcher is removed. The backend keeps sending reports at the faster rate, and the stored interval is stale for later comparisons when watchers are added.
- **Evidence:** grpc 515aaa1743: [oob_backend_metric.cc L237-L250](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/oob_backend_metric.cc#L237-L250)
- **Spec:** Client-Side Backend Metrics (ORCA) (`04-client-channel/11-backend-metrics.md`), "Stream"

### [low] `weighted_round_robin` accepts a NaN endpoint weight

- **Item:** audit (W2-07-009)
- **Summary:** C++ drops a computed endpoint weight only when it equals 0, so a NaN weight (for example from a report with infinite `qps` and positive `eps`) is stored and used to build the scheduler.
- **Description:** The spec ignores a report unless the computed weight is greater than 0, which also rejects NaN. C++ checks only for 0. When a backend reports `qps` = +infinity and a positive `eps`, the error penalty is infinity/infinity = NaN, the weight is NaN, and it is stored. The scheduler builder then rounds NaN values to integers, which gives unspecified results, so the weights of all endpoints in the scheduler become meaningless until the NaN weight expires.
- **Evidence:** grpc 515aaa1743: [weighted_round_robin.cc L499-L518](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_round_robin/weighted_round_robin.cc#L499-L518), [static_stride_scheduler.cc L79-L151](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_round_robin/static_stride_scheduler.cc#L79-L151)
- **Spec:** `weighted_round_robin` LB Policy (`04-client-channel/lb-policies/weighted_round_robin.md`), "Blackout and Expiration"

### [low] Disabling outlier detection leaves endpoints ejected if the same update has an endpoint error

- **Item:** audit (W2-08-010)
- **Summary:** When a config update disables outlier detection and its endpoint list is an error, C++ cancels the ejection timer but does not un-eject ejected endpoints or reset their multipliers.
- **Description:** The spec requires that, on every config update that disables outlier detection, the policy cancels the timer, un-ejects all ejected endpoints, and resets every multiplier. C++ cancels the timer for every such update, but un-ejects only while walking the new endpoint list, which is skipped when the endpoint list is an error. Endpoints that were ejected stay ejected (reported as TRANSIENT_FAILURE to the child), and with the timer cancelled nothing un-ejects them until a later update with a valid endpoint list arrives.
- **Evidence:** grpc 515aaa1743: [outlier_detection.cc L670-L675](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L670-L675), [outlier_detection.cc L698](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L698), [outlier_detection.cc L735-L741](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L735-L741)
- **Spec:** `outlier_detection` LB Policy (`04-client-channel/lb-policies/outlier_detection.md`), "Updates from the Parent"

### [low] weighted_target does not forward ExitIdle to its children

- **Item:** audit (W2-08-022); see resolved_items R29 post-resolution note
- **Summary:** `WeightedTargetLb` does not override `ExitIdleLocked()`. An `ExitIdle()` call from the parent policy, or from weighted_target's own IDLE picker, does nothing.
- **Description:** The spec says weighted_target forwards `ExitIdle()` to all children, and its IDLE picker schedules `ExitIdle()`. C++ has no `ExitIdleLocked()` override, so these requests reach the empty base-class method. In practice the impact is small: C++ calls `ExitIdleLocked()` on a child as soon as it reports IDLE, and children start in CONNECTING, so the aggregate state is rarely IDLE. The gap shows only when a child reports IDLE again after being asked to exit idle (for example, a child whose own `ExitIdle()` does nothing) and the parent or picker later asks weighted_target to exit idle.
- **Evidence:** grpc 515aaa1743: [weighted_target.cc L115-L122](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_target/weighted_target.cc#L115-L122) (no `ExitIdleLocked()` override), [weighted_target.cc L440-L443](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_target/weighted_target.cc#L440-L443) (IDLE uses `QueuePicker`), [weighted_target.cc L606-L607](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_target/weighted_target.cc#L606-L607), [lb_policy.h L428](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/lb_policy.h#L428)
- **Spec:** `04-client-channel/lb-policies/weighted_target.md`, "ExitIdle" and "Picker Implementation"

### [low] IPv6 target names are compared to certificate IP SANs as strings

- **Item:** audit (W2-10-008)
- **Summary:** Hostname verification compares an IP-address target name to IP-address SANs as text. A valid IPv6 literal written differently from `inet_ntop`'s output fails to match.
- **Description:** The spec says hostname verification follows RFC 9525 §6, which matches an IP-address reference identity by comparing octets. C++ converts each `iPAddress` SAN to text with `inet_ntop` and compares it to the target host by string equality, both in the default verifier and in `HostNameCertificateVerifier`. A target such as `[2001:0db8::1]` or `[2001:DB8::1]` fails to match a certificate whose SAN is `2001:db8::1`, so the handshake fails.
- **Evidence:** grpc 515aaa1743: [ssl_transport_security.cc L1199-L1203](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/tsi/ssl_transport_security.cc#L1199-L1203), [ssl_transport_security.cc L3802-L3804](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/tsi/ssl_transport_security.cc#L3802-L3804), [grpc_tls_certificate_verifier.cc L146-L156](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/tls/grpc_tls_certificate_verifier.cc#L146-L156)
- **Spec:** `06-security/02-tls.md`, "Server Certificate Verification"

### [low] File-watcher authorization policy reload failures are not logged by default

- **Item:** audit (W2-11-014)
- **Summary:** When a periodic reload of the authorization policy file fails, C++ logs the error only if the `grpc_authz_api` trace flag is on.
- **Description:** The spec says a failed reload is skipped, the error is logged, and the last valid policy stays in effect. C++ keeps the last valid policy, but its refresh thread logs the failure only when the `grpc_authz_api` trace flag is on. With default settings, a broken policy file goes unnoticed, and the server keeps enforcing the old policy with no indication. Go logs a warning on every failed reload.
- **Evidence:** grpc 515aaa1743: [grpc_authorization_policy_provider.cc L112-L118](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/grpc_authorization_policy_provider.cc#L112-L118)
- **Spec:** `06-security/04-authorization.md`, "Policy Providers"

### [low] Health service shutdown registers unknown services that are being watched

- **Item:** audit (W2-12-002)
- **Summary:** Calling `Shutdown()` or `SetServingStatus(bool)` on the default health service turns every unknown service with an active `Watch` call into a registered service.
- **Description:** The spec says watching an unknown service reports `SERVICE_UNKNOWN` without registering it, and entering shutdown sets every registered service to `NOT_SERVING`. C++ keeps watchers and statuses in the same map. A `Watch` on an unknown service adds an entry with status `NOT_FOUND`, and `Shutdown()` and `SetServingStatus(bool)` overwrite every entry. After `Shutdown()`, `Check` for that service returns `OK` with `NOT_SERVING` instead of `NOT_FOUND`. After `SetServingStatus(true)`, an unregistered service reports `SERVING`. The entry then remains after the watch ends. Go updates only registered services.
- **Evidence:** grpc 515aaa1743: [default_health_check_service.cc L59-L77](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/health/default_health_check_service.cc#L59-L77), [default_health_check_service.cc L89-L96](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/health/default_health_check_service.cc#L89-L96), [default_health_check_service.h L122-L125](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/health/default_health_check_service.h#L122-L125)
- **Spec:** `07-services/01-health.md`, "Health Status Registry" and "API Requirements"

### [low] Reflection client utility and grpc_cli use only the v1alpha reflection service

- **Item:** audit (W2-12-012); related open item REFLECTION-20
- **Summary:** `ProtoReflectionDescriptorDatabase`, which `grpc_cli` uses, calls only `grpc.reflection.v1alpha.ServerReflection`. It never tries `grpc.reflection.v1.ServerReflection`.
- **Description:** The spec says reflection clients should call `v1` first and fall back to `v1alpha` on `UNIMPLEMENTED`, and that the client-side descriptor database prefers `v1`. The C++ utility is built only on the `v1alpha` stub, so `grpc_cli` cannot use reflection against servers that register only `v1` (for example, Java servers that register only `ProtoReflectionServiceV1`).
- **Evidence:** grpc 515aaa1743: [proto_reflection_descriptor_database.h L21](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/test/cpp/util/proto_reflection_descriptor_database.h#L21), [proto_reflection_descriptor_database.h L59](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/test/cpp/util/proto_reflection_descriptor_database.h#L59), [proto_reflection_descriptor_database.h L120](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/test/cpp/util/proto_reflection_descriptor_database.h#L120)
- **Spec:** `07-services/02-reflection.md`, "Versions" and "API Requirements"

### [low] Subchannel, outlier detection, TLS, and TCP metrics can only be enabled through an experiment

- **Item:** audit (W2-13-011)
- **Summary:** Enabling these metrics by name in the OpenTelemetry plugin has no effect unless the default-off `otel_export_telemetry_domains` experiment is also enabled.
- **Description:** The spec says applications must be able to turn on each experimental metric by name. In C++, the `grpc.subchannel.*`, `grpc.lb.outlier_detection.*`, `grpc.client.tls.handshakes`/`grpc.server.tls.handshakes`, and `grpc.tcp.*` metrics are registered only through the newer instrument-domain framework. The OpenTelemetry plugin connects that framework to OpenTelemetry only when the `otel_export_telemetry_domains` experiment is on, and the experiment is off by default. An application that calls `EnableMetrics` with these names gets no data.
- **Evidence:** grpc 515aaa1743: [otel_plugin.cc L739-L750](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_plugin.cc#L739-L750), [experiments.h L113](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/experiments/experiments.h#L113), [experiments.yaml L244-L248](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/experiments/experiments.yaml#L244-L248), [subchannel_metrics.cc L23-L46](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/subchannel_metrics.cc#L23-L46)
- **Spec:** `08-observability/04-metrics.md`, "API Requirements"; `08-observability/03-metrics-framework.md`, "Enabling and Disabling Metrics"

### [low] Subchannel metrics have wrong units and some optional labels are always recorded

- **Item:** audit (W2-13-011)
- **Summary:** The subchannel metrics are registered with units `attempt`, `disconnection`, and `connection` without braces. The OpenTelemetry exporter for these metrics also records several optional labels even when the application did not configure them.
- **Description:** The spec gives the units as `{attempt}`, `{disconnection}`, and `{connection}`, and says optional labels that are not configured are dropped. C++ registers the subchannel counters without braces. When exporting instrument-domain metrics, the plugin treats only `grpc.lb.locality` and `grpc.lb.backend_service` as optional. So `grpc.disconnect_error`, `grpc.security_level`, `grpc.tls.handshake.resumed`, and the `network.*` TCP labels are always recorded, which adds unrequested attributes and cardinality. Both problems are visible only when the `otel_export_telemetry_domains` experiment is on.
- **Evidence:** grpc 515aaa1743: [subchannel_metrics.cc L23-L46](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/subchannel_metrics.cc#L23-L46), [otel_plugin.cc L63-L71](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_plugin.cc#L63-L71), [otel_plugin.cc L744-L751](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_plugin.cc#L744-L751)
- **Spec:** `08-observability/03-metrics-framework.md`, "Units" and "Optional Labels"; `08-observability/04-metrics.md`, "Subchannel Metrics"

### [low] Huge route runtime_fraction values wrap around instead of being capped at 100%

- **Item:** audit (W2-16-005)
- **Summary:** When normalizing a route's `runtime_fraction` to parts per million, C++ multiplies in 32-bit arithmetic without capping. Very large numerators wrap around to small fractions.
- **Description:** The spec says a fractional percentage is normalized to parts per million and capped at 1,000,000 (100%). C++ multiplies the `uint32_t` numerator by 10000 (`HUNDRED`) or 100 (`TEN_THOUSAND`) and stores the result unchanged. Values that are above 100% but do not overflow still match every RPC. A numerator large enough to overflow wraps around. For example, `numerator: 429497, denominator: HUNDRED` becomes 2704 (about 0.27%) instead of 100%, so the route matches almost no RPCs.
- **Evidence:** grpc 515aaa1743: [xds_route_config_parser.cc L260-L280](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_route_config_parser.cc#L260-L280)
- **Spec:** `09-xds/04-resources/01-common-types.md`, "Fractional Percentages"; `09-xds/04-resources/03-route-configuration.md`, "RouteMatch"

### [low] EDS endpoint addresses without a port_value are accepted with port 0

- **Item:** audit (W2-16-006)
- **Summary:** When parsing EDS endpoint addresses and `envoy.config.core.v3.Address` metadata, C++ does not check that `socket_address.port_value` is set. An address that uses `named_port` or has no port gets port 0 instead of being rejected.
- **Description:** The spec says an `Address` is valid only if its port is given in `socket_address.port_value`, and `named_port` is not supported. C++'s shared address parser reads `port_value` without checking that it is set. Because the proto default is 0, an endpoint with `named_port` or no port specifier is accepted as `<ip>:0` instead of NACKing the resource, and connections to it fail. The `LOGICAL_DNS` cluster parser does check that the port is set.
- **Evidence:** grpc 515aaa1743: [xds_common_types_parser.cc L120-L128](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_common_types_parser.cc#L120-L128), [xds_cluster_parser.cc L268-L271](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L268-L271) (for comparison)
- **Spec:** `09-xds/04-resources/01-common-types.md`, "Addresses"

### [low] Aggregate cluster name can be recorded as the backend service metric label

- **Item:** audit (W2-17-012)
- **Summary:** The `cds` policy wraps its child's picker for aggregate clusters too, so the `grpc.lb.backend_service` label is set to the aggregate cluster name before the pick reaches a leaf cluster.
- **Description:** The spec says the `cds` policy sets `grpc.lb.backend_service` only for non-aggregate clusters. For an aggregate cluster it reports the `priority` child's picker unchanged, so the label is always a leaf cluster name. C++ wraps the child picker for every cluster type. A leaf `cds` policy normally overwrites the label, but if the pick is queued (and the attempt then ends, for example on deadline) or the selected leaf is in TRANSIENT_FAILURE with its plain failure picker, the attempt's metrics carry the aggregate cluster name. Java sets the label only for non-aggregate clusters.
- **Evidence:** grpc 515aaa1743: [cds.cc L216-L251](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/cds.cc#L216-L251) (picker sets the label; helper wraps unconditionally), [cds.cc L674-L681](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/cds.cc#L674-L681) (leaf failure picker does not set the label)
- **Spec:** 09-xds/lb-policies/cds.md, "4. Picker Implementation"; 09-xds/lb-policies/cds.md, "5.2 Calls From Children"

### [low] Server resets ping strikes when it sends flow-control window updates

- **Item:** audit (W2-06-004)
- **Summary:** The server's ping-abuse counter and last-ping time are reset whenever the server sends a `WINDOW_UPDATE`, not only when it sends HEADERS or DATA.
- **Description:** In the spec's ping enforcement algorithm, the server resets its ping strikes and last valid ping time only when it sends a HEADERS or DATA frame. In chttp2, writing a connection-level or stream-level `WINDOW_UPDATE` also resets them. A client that keeps sending request data, so that the server keeps sending window updates, can ping far more often than `PERMIT_KEEPALIVE_TIME` allows without being sent `too_many_pings`, even while the server sends no responses.
- **Evidence:** grpc 515aaa1743: [writing.cc L296-L307](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/writing.cc#L296-L307), [writing.cc L511-L526](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/writing.cc#L511-L526), [chttp2_transport.cc L2251-L2256](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L2251-L2256), [ping_abuse_policy.cc L84-L87](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/ping_abuse_policy.cc#L84-L87)
- **Spec:** 05-server/02-transports/02-http2.md, "7.2 Ping Enforcement"

### [low] CSDS reports a node `client_features` list that differs from the one sent to the xDS server

- **Item:** audit (W2-15-013)
- **Summary:** The `node` in the CSDS `ClientConfig` lacks the `xds.config.resource-in-sotw` client feature that the client sends on its ADS stream.
- **Description:** The spec says CSDS reports the `Node` exactly as the XdsClient sends it to xDS servers. When the ADS stream sends its first request, it fills in the node and then adds `xds.config.resource-in-sotw`. The CSDS dump fills in the node with the same helper but does not add that feature, so operators see a `client_features` list that differs from what the server received.
- **Evidence:** grpc 515aaa1743: [xds_client.cc L882-L892](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/xds_client/xds_client.cc#L882-L892) (ADS request), [xds_client.cc L1976-L1984](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/xds_client/xds_client.cc#L1976-L1984) (CSDS dump), [xds_api.cc L126](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/xds_client/xds_api.cc#L126)
- **Spec:** 09-xds/11-csds.md, "3.1 `ClientConfig`"

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

### [low] C++ client sends no immediate keepalive PING when a stream starts on a long-idle connection

- **Item:** TRANSPORT-2
- **Summary:** If the keepalive timer fires while there are no streams and `KEEPALIVE_WITHOUT_CALLS` is false, C++ just re-arms the timer. A new stream doesn't trigger an overdue ping, so finding a dead connection can take up to `KEEPALIVE_TIME + KEEPALIVE_TIMEOUT` instead of `KEEPALIVE_TIMEOUT`.
- **Description:** In `init_keepalive_ping_locked`, the no-streams branch reschedules for `keepalive_time`. Nothing on stream creation checks keepalive state. gRFC A8 says a keepalive PING should be sent when a stream is created and more than the keepalive time has passed since the last read. Java and Go do this.
- **Evidence:** [chttp2_transport.cc#L3298-L3313](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L3298-L3313)
- **Spec:** HTTP/2 Transport: Keepalive

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

### [low] C++: OpenTelemetry delay event names have a trailing period

- **Item:** TRACING-4
- **Summary:** C++ records `Delayed name resolution complete.` and `Delayed LB pick complete.` (with a period), so they do not match the A72 names used by Java and Go.
- **Description:** The annotations are turned into OTel span events by the tracer. Event names are meant for exact matching across languages.
- **Evidence:** [client_channel_filter.cc L1897](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_filter.cc#L1897), [L2434](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_filter.cc#L2434), [client_channel.cc L997](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L997), [load_balanced_call_destination.cc L246](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/load_balanced_call_destination.cc#L246)
- **Spec:** Tracing: Client Call Span; Tracing: Client Attempt Span

### [low] xDS retry base_interval of 0 not NACKed; max_interval < base_interval and the 1ms floor not handled

- **Item:** XDS_ROUTING-8
- **Summary:** C++ does not check `base_interval > 0` or `max_interval >= base_interval` when parsing RetryPolicy, and does not raise sub-millisecond values to 1ms.
- **Description:** The spec (per A44) requires `base_interval` > 0, `max_interval` ≥ `base_interval`, treats values below 1ms as 1ms, and rejects the resource on violations. C++ accepts a zero `base_interval`; the generated method config then fails `initialBackoff` validation and the resolver reports a channel error instead of NACKing. `max_interval < base_interval` is accepted and sub-millisecond values are passed through.
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_route_config_parser.cc#L374-L413, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_service_config.cc#L148-L161, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_resolver.cc#L582-L583
- **Spec:** RouteConfiguration: Retry Policy

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

### [low] xDS bootstrap validates unused channel_creds entries

- **Item:** XDS_BOOTSTRAP-2
- **Summary:** C++ rejects a bootstrap whose `channel_creds` has an invalid config in a supported entry after the first supported one.
- **Description:** gRPC uses only the first `channel_creds` entry whose type it supports, and only that entry's config is validated. Entries after it are never used and are not validated. C++ validates every supported entry, so a malformed later entry makes the whole bootstrap invalid. Java and Go stop at the first supported entry.
- **Evidence:** src/core/xds/grpc/xds_server_grpc.cc `ParseXdsBootstrapChannelCreds`
- **Spec:** xDS Bootstrap: XdsServer Object

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
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), "Token Accounting".

### [low] Negative method-config timeout with a zero seconds part is accepted as positive

- **Item:** R48
- **Summary:** C++ parses `"-0.5s"` as +0.5s instead of rejecting it as a negative duration.
- **Description:** `LoadDuration` range-checks the seconds part, but drops the sign when seconds is 0, so values like `"-0.5s"` become positive timeouts. The spec says any negative timeout makes the service config invalid. It is a rare edge case, but it silently turns an invalid config into a valid one with a different meaning. The same parser is used for every JSON duration, so this also affects, for example, the RLS `lookupServiceTimeout`, `maxAge`, and `staleAge` fields.
- **Evidence:** `src/core/util/json/json_object_loader.cc` (`LoadDuration`).
- **Spec:** Service Config (`04-client-channel/04-service-config.md`), "`methodConfig`" field table (`timeout`).

### [low] No base64 fallback after RST_STREAM(PROTOCOL_ERROR) on true-binary metadata

- **Item:** R124
- **Summary:** The client does not retry in base64 or disable true-binary encoding on the connection when a misconfigured peer rejects true-binary headers.
- **Description:** The spec says a client that sent true-binary metadata and gets `RST_STREAM(PROTOCOL_ERROR)` before any response headers SHOULD retry the request in base64 (not counted against retry policy), SHOULD stop using true binary on that connection, and SHOULD log the event. C++ does not appear to implement any of this, so against a peer that aliases setting 0xfe03 every RPC carrying binary metadata fails. These are SHOULDs, so this is a gap rather than a violation, and it only matters with a colliding extension.
- **Evidence:** findings for R124 (review_items.md); no fallback logic found in `src/core/ext/transport/chttp2/transport/` (`chttp2_transport.cc`, `writing.cc`, `http2_client_transport.cc`).
- **Spec:** 03-wire-protocol/02-true-binary-metadata.md, "Misconfiguration Fallback"

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

### [low] `grpc-timeout` values over 8 digits accepted, and longer ones read as infinite without checking the unit

- **Item:** incidental (investigation of old item 22); audit (W2-01-014)
- **Summary:** The timeout parser accepts values longer than the 8-digit maximum. For values past 9 digits it returns an infinite timeout right away, without checking the unit or the bytes that follow.
- **Description:** `TimeoutValue` is at most 8 ASCII digits followed by one unit character (`H`, `M`, `S`, `m`, `u`, `n`). The C++ parser accepts any 9-digit value, and also exactly `1000000000`. Once the value would go past that, the digit loop returns `Duration::Infinity()` immediately, so the unit and trailing-character checks that run after the loop are skipped. A malformed header such as `1234567890XYZ` therefore becomes "no deadline" instead of being rejected as unparseable (the spec says the server SHOULD fail such a call with INTERNAL). Accepting 9-digit values is lenient but non-conforming.
- **Evidence:** grpc 515aaa1743: [timeout_encoding.cc L232-L286](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/transport/timeout_encoding.cc#L232-L286) (early return at L245-L248; unit and trailing checks at L256-L284); findings G1.
- **Spec:** gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), "`grpc-timeout`"

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

### [low] Proxy credentials without a password are sent without the `:` separator

- **Item:** audit (W2-05-018)
- **Summary:** For a proxy URI like `http://alice@proxy:8080`, the `Proxy-Authorization` header carries `base64("alice")` instead of `base64("alice:")`.
- **Description:** The spec says an omitted `:password` in the proxy URI's userinfo means an empty password, and that the CONNECT request carries `Proxy-Authorization: Basic base64(username ":" password)` (RFC 7617 always includes the colon). The C++ proxy mapper takes the userinfo string unchanged and base64-encodes it, so when there is no `:` in the userinfo the credential has no separator. Proxies that parse Basic credentials strictly can reject it.
- **Evidence:** grpc 515aaa1743: [http_proxy_mapper.cc L166-L169](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/handshaker/http_connect/http_proxy_mapper.cc#L166-L169), [http_proxy_mapper.cc L263-L269](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/handshaker/http_connect/http_proxy_mapper.cc#L263-L269)
- **Spec:** HTTP CONNECT Proxy Support (`04-client-channel/09-proxy.md`), "Choosing the Proxy" and "CONNECT Handshake"

### [low] weighted_round_robin does not count endpoints with no load report as "not yet usable" when the blackout period is 0

- **Item:** audit (W2-07-008)
- **Summary:** With `blackoutPeriod` set to `0s`, an endpoint that has never reported a weight gets weight 0 but is not counted in `grpc.lb.wrr.endpoint_weight_not_yet_usable`.
- **Description:** The spec counts an endpoint as "not yet usable" whenever it has not received a load report yet, whatever the blackout period. In C++, a fresh endpoint has `last_update_time_` and `non_empty_since_` set to infinite future. The expiration check (`now - last_update_time_ >= expiration`) is therefore false, and the blackout check only runs when `blackout_period > 0`. With blackout disabled, `GetWeight` returns the initial weight of 0 without incrementing either the not-yet-usable or the stale counter, so the metric under-reports endpoints that have no weight yet.
- **Evidence:** grpc 515aaa1743: [weighted_round_robin.cc L288-L290](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_round_robin/weighted_round_robin.cc#L288-L290), [weighted_round_robin.cc L535-L563](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_round_robin/weighted_round_robin.cc#L535-L563)
- **Spec:** `weighted_round_robin` LB Policy (`04-client-channel/lb-policies/weighted_round_robin.md`), "Blackout and Expiration" and "Metrics"; Metric Catalog (`08-observability/04-metrics.md`), "Weighted Round Robin LB Policy Metrics"

### [low] outlier_detection does not report a new picker when outlier detection is turned on or off

- **Item:** audit (W2-08-011)
- **Summary:** When a config update enables or disables outlier detection and the child policy keeps its existing picker, call counting does not start or stop until the child happens to report a new picker.
- **Description:** The spec requires the policy to report an updated picker when outlier detection toggles between enabled and disabled, so that call counting starts or stops right away. In C++, the outlier detection picker records whether counting was enabled when it was built, and a new one is built only when the child calls `UpdateState`. `UpdateLocked` updates the config and the ejection timer but does not re-wrap the child's current picker. If the child does not report a new picker for that update, counting stays in its old state: newly enabled ejection gets no call results, and disabled ejection keeps attaching call trackers.
- **Evidence:** grpc 515aaa1743: [outlier_detection.cc L555-L592](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L555-L592), [outlier_detection.cc L663-L807](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/outlier_detection/outlier_detection.cc#L663-L807)
- **Spec:** `outlier_detection` LB Policy (`04-client-channel/lb-policies/outlier_detection.md`), "Updates from the Parent"

### [low] Retry pushback values outside the 32-bit range are treated as a delay instead of "do not retry"

- **Item:** audit (W2-09-010)
- **Summary:** `grpc-retry-pushback-ms` is parsed as a 64-bit integer, so values above the signed 32-bit range are used as retry delays.
- **Description:** The spec defines `grpc-retry-pushback-ms` as a signed 32-bit decimal integer and says a value outside that range is unparseable, which means "do not retry". C++ parses the value with `absl::SimpleAtoi` into an `int64_t` and turns it into a millisecond delay. An out-of-range positive value schedules a very long retry (limited only by the call deadline) instead of failing the RPC with the attempt's status. An out-of-range negative value still means "do not retry". Java's `Integer.valueOf` rejects out-of-range values.
- **Evidence:** grpc 515aaa1743: [metadata_batch.cc L318-L326](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/metadata_batch.cc#L318-L326)
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), "Server Pushback"

### [low] TLS accepts `h2` negotiated through legacy NPN when ALPN was not negotiated

- **Item:** audit (W2-10-005)
- **Summary:** If ALPN does not select a protocol, the TLS handshaker uses the protocol negotiated by the legacy NPN extension, so a connection without ALPN `h2` passes the ALPN check.
- **Description:** The spec requires the client to offer ALPN `h2` and the server to select it, and both sides MUST fail the handshake if `h2` is not negotiated (as RFC 9113 requires for HTTP/2 over TLS). The C++ TLS stack also advertises NPN, and when `SSL_get0_alpn_selected` returns nothing it falls back to `SSL_get0_next_proto_negotiated`. It stores the result in the same "ALPN selected protocol" peer property that the security connector checks, so a peer that negotiates `h2` only through NPN is accepted. The impact is limited to legacy peers that support NPN but not ALPN.
- **Evidence:** grpc 515aaa1743: [ssl_transport_security.cc L2282-L2289](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/tsi/ssl_transport_security.cc#L2282-L2289), [ssl_transport_security.cc L2326-L2330](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/tsi/ssl_transport_security.cc#L2326-L2330), [ssl_utils.cc L132-L146](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/tls/ssl_utils.cc#L132-L146)
- **Spec:** TLS (`06-security/02-tls.md`), "Protocol Requirements"

### [low] TLS server credentials can be created without an identity provider

- **Item:** audit (W2-10-009)
- **Summary:** `grpc_tls_server_credentials_create` succeeds when no identity certificate provider is configured. The failure only shows up later, at handshake time.
- **Description:** The spec says a TLS server MUST have an identity and that server credentials creation MUST fail if no identity provider is configured. The C++ `TlsServerCredentialsOptions::Create()` factory enforces this. However, the C-core `grpc_tls_server_credentials_create` sanity check never looks at the identity provider, and the deprecated `TlsServerCredentialsOptions(provider)` constructor sets the identity provider only if `watch_identity_key_cert_pairs()` is also called. Through either path, a server without an identity is created successfully, and every handshake then fails.
- **Evidence:** grpc 515aaa1743: [tls_credentials.cc L41-L92](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/tls/tls_credentials.cc#L41-L92), [tls_credentials.cc L164-L172](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/tls/tls_credentials.cc#L164-L172), [tls_credentials_options.h L190-L210](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/include/grpcpp/security/tls_credentials_options.h#L190-L210), [tls_credentials_options.cc L139-L152](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/common/tls_credentials_options.cc#L139-L152)
- **Spec:** TLS (`06-security/02-tls.md`), "Client Certificates and Mutual TLS"

### [low] Peer SPIFFE ID is not reported for trust-domain-only IDs or an upper-case scheme

- **Item:** audit (W2-10-017)
- **Summary:** The check that fills the `peer_spiffe_id` AuthContext property rejects SPIFFE IDs with an empty path (`spiffe://example.com`) and compares the `spiffe://` scheme case-sensitively.
- **Description:** `peer_spiffe_id` is present when the peer leaf certificate has exactly one URI SAN that is a valid SPIFFE ID. The spec defines a valid ID with a case-insensitive scheme and an empty path allowed. The C++ helper that fills the property, `IsSpiffeId`, requires a literal lower-case `spiffe://` prefix and a non-empty first path segment. Peers whose ID is just a trust domain, or that use a different scheme case, get no `peer_spiffe_id`, so authorization policies that match on the principal see an empty principal. The C++ SPIFFE parser used for trust bundle map verification (`SpiffeId::FromString`) is separate code and is not affected.
- **Evidence:** grpc 515aaa1743: [ssl_utils.cc L238-L259](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/tls/ssl_utils.cc#L238-L259), [ssl_utils.cc L330-L337](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/tls/ssl_utils.cc#L330-L337)
- **Spec:** Security Model (`06-security/01-security-model.md`), "Standard Properties"; TLS (`06-security/02-tls.md`), "SPIFFE Trust Bundle Map Verification"

### [low] Call credentials get a service URL without a scheme on insecure and local channels

- **Item:** audit (W2-10-021)
- **Summary:** On channels using insecure or local credentials, the service URL passed to call credentials is `://host/pkg.Svc` instead of `https://host/pkg.Svc`.
- **Description:** The spec defines the call credential service URL as `"https://" + host + "/" + service`, with port 443 removed. C++ builds it from the security connector's URL scheme. The insecure connector and the local connector set that scheme to an empty string, so the service URL has no scheme (and the port-443 removal is skipped as well). Local credentials over Unix domain sockets have security level `PRIVACY_AND_INTEGRITY`, so standard call credentials such as JWT access credentials run on them and use the malformed URL, for example as the JWT audience.
- **Evidence:** grpc 515aaa1743: [call_creds_util.cc L63-L73](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/call/call_creds_util.cc#L63-L73), [insecure_security_connector.h L57-L60](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/insecure/insecure_security_connector.h#L57-L60), [local_security_connector.cc L178](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/local/local_security_connector.cc#L178)
- **Spec:** Call Credentials (`06-security/03-call-credentials.md`), "Inputs"

### [low] Health Watch sends repeated responses when the status has not changed

- **Item:** audit (W2-12-004)
- **Summary:** The default health service sends a `Watch` response to every watcher on every status update, even when the new status equals the last one sent.
- **Description:** The spec says the server sends a new `Watch` response when the service's status changes and SHOULD NOT send a response with the same status as the last one on that call. In C++, every `SetServingStatus` call on a service (including the all-services `SetServingStatus(bool)` and `Shutdown()`) pushes the status to all of that service's watchers without comparing it to the previous value, and the watch reactor does not filter repeats. Applications that refresh health status periodically cause a stream of identical responses.
- **Evidence:** grpc 515aaa1743: [default_health_check_service.cc L59-L77](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/health/default_health_check_service.cc#L59-L77), [default_health_check_service.cc L120-L126](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/health/default_health_check_service.cc#L120-L126), [default_health_check_service.cc L270-L285](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/health/default_health_check_service.cc#L270-L285)
- **Spec:** Health Service (`07-services/01-health.md`), "`Watch`"

### [low] Health status updates after shutdown can still add services to the registry

- **Item:** audit (W2-12-003)
- **Summary:** After `Shutdown()`, `SetServingStatus(name, ...)` is not ignored: it stores `name` as `NOT_SERVING`, adding it to the registry if it was unknown.
- **Description:** The spec says entering shutdown sets every registered service to `NOT_SERVING` and ignores later status updates. C++ instead forces the value to `NOT_SERVING` and still writes it to the registry. A service name that was not registered before shutdown becomes known: `Check` returns `NOT_SERVING` instead of `NOT_FOUND`, and existing watchers of that name get a `NOT_SERVING` response instead of staying at `SERVICE_UNKNOWN`. Either way the server keeps reporting not serving, so the impact is small.
- **Evidence:** grpc 515aaa1743: [default_health_check_service.cc L49-L57](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/health/default_health_check_service.cc#L49-L57)
- **Spec:** Health Service (`07-services/01-health.md`), "API Requirements"

### [low] OpenTelemetry span error descriptions do not follow the `<CODE>: <message>` format

- **Item:** audit (W2-13-010); related: TRACING-3
- **Summary:** Attempt and server spans set the `ERROR` description from `absl::Status::ToString()`, which leaves a trailing `": "` when the message is empty and can append internal status payloads.
- **Description:** The spec requires an `ERROR` span status description of `<CODE>: <message>`, or just `<CODE>` when the status message is empty. Java implements this in `OpenTelemetryTracingModule.statusString`. C++ uses `absl::Status::ToString()` instead. That always produces `<CODE>: <message>`, so an empty message gives a description like `UNAVAILABLE: `. On client attempt spans it also appends any payloads attached to the core status, in the form ` [type.googleapis.com/...='...']`, which exposes internal details in trace backends.
- **Evidence:** grpc 515aaa1743: [otel_client_call_tracer.cc L347-L354](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_client_call_tracer.cc#L347-L354), [otel_server_call_tracer.cc L305-L313](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_server_call_tracer.cc#L305-L313), [otel_tracing_test.cc L454-L457](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/test/cpp/ext/otel/otel_tracing_test.cc#L454-L457)
- **Spec:** Tracing (`08-observability/05-tracing.md`), "Span Status"

### [low] LOGICAL_DNS cluster accepts a port above 65535

- **Item:** audit (W2-16-014)
- **Summary:** A `LOGICAL_DNS` Cluster whose `socket_address.port_value` is greater than 65535 is accepted instead of NACKed.
- **Description:** `LogicalDnsParse` checks that `port_value` is set but not that it is at most 65535 (`port_value` is a `uint32`; the Envoy proto constrains it to `lte: 65535`). The out-of-range port is formatted into the `host:port` DNS name, so the Cluster is accepted and every RPC to it then fails at DNS resolution instead of the resource being rejected. The EDS and server Listener address parsers in C++ do reject ports above 65535.
- **Evidence:** grpc 515aaa1743: [xds_cluster_parser.cc L268-L274](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L268-L274)
- **Spec:** Cluster (`09-xds/04-resources/04-cluster.md`), "Logical DNS Clusters"; Common Types (`09-xds/04-resources/01-common-types.md`), "Validation Conventions"

### [low] Cluster `lrs_report_endpoint_metrics` treats `"named_metrics."` as a request for an empty-named metric

- **Item:** audit (W2-16-018, W2-18-027)
- **Summary:** The entry `"named_metrics."` in `Cluster.lrs_report_endpoint_metrics` is not ignored. C++ adds the empty string to the set of named metric keys to propagate.
- **Description:** The spec recognizes `named_metrics.<key>` only when `<key>` is non-empty and not `*`, and says `"named_metrics."` with an empty key is ignored. When parsing the Cluster, C++ strips the `named_metrics.` prefix and inserts the remainder whenever it is not `*`, so an empty key is inserted. An ORCA `named_metrics` entry with an empty key would then be copied into load reports as `named_metrics.`. Go and Java both require a non-empty key.
- **Evidence:** grpc 515aaa1743: [xds_cluster_parser.cc L541-L546](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L541-L546)
- **Spec:** Cluster (`09-xds/04-resources/04-cluster.md`), "Load Reporting"; Load Reporting (`09-xds/10-load-reporting.md`), "Propagation config"

### [low] xDS server skips duplicate-matcher checks for filter chains that can never match

- **Item:** audit (W2-18-011)
- **Summary:** When building the filter chain map, C++ drops chains whose `FilterChainMatch` can never match before checking for duplicates. A Listener with duplicate matchers among those chains is therefore accepted instead of NACKed.
- **Description:** The spec says a server MAY prune chains with always-failing criteria (non-empty `server_names`, a `transport_protocol` other than empty or `raw_buffer`, non-empty `application_protocols`) but MUST still include them in the uniqueness check. C++ detects duplicates only when it inserts a chain into the source-port map. It returns early for chains with `server_names`, unsupported `transport_protocol`, or `application_protocols`, so those chains are never inserted. It also discards chains with an empty `transport_protocol` once a `raw_buffer` chain is seen for the same destination prefix. As a result, two identical never-matching chains (or two identical empty-`transport_protocol` chains that are shadowed by a `raw_buffer` chain) do not cause a NACK. Java checks uniqueness across all chains.
- **Evidence:** grpc 515aaa1743: [xds_listener_parser.cc L725-L741](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_listener_parser.cc#L725-L741), [xds_listener_parser.cc L803-L851](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_listener_parser.cc#L803-L851)
- **Spec:** xDS-Enabled Servers (`09-xds/08-server.md`), "Matching Algorithm" and "Normalization and Uniqueness"

### [low] xDS server treats only 127.0.0.1 as an IPv4 loopback peer for `source_type`

- **Item:** audit (W2-18-012)
- **Summary:** For `FilterChainMatch.source_type`, C++ classifies IPv4 peers in 127.0.0.0/8 other than 127.0.0.1 (for example 127.0.0.2) as `EXTERNAL` instead of `SAME_IP_OR_LOOPBACK`.
- **Description:** `SAME_IP_OR_LOOPBACK` matches when the peer address is a loopback address or equals the local address. The entire IPv4 127.0.0.0/8 block is loopback. C++ compares the peer address only against 127.0.0.1, so a connection from another 127.x.y.z address to a different local address picks a chain meant for external peers (or no chain at all). Go and Java check the whole /8.
- **Evidence:** grpc 515aaa1743: [xds_server_config_fetcher.cc L806-L824](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/server/xds_server_config_fetcher.cc#L806-L824)
- **Spec:** xDS-Enabled Servers (`09-xds/08-server.md`), "Matching Algorithm"

### [low] xDS server does not validate the range of `FilterChainMatch.source_ports`

- **Item:** audit (W2-18-013)
- **Summary:** C++ accepts `source_ports` entries of 0 or greater than 65535 instead of NACKing the Listener. A port of 0 also behaves like an empty `source_ports` list.
- **Description:** The spec requires every `FilterChainMatch.source_ports` entry to be in [1, 65535]. C++ copies the entries without any range check. Internally it stores a chain with no `source_ports` under port key 0 and falls back to key 0 when there is no exact match. So `source_ports: [0]` matches every peer port, and it is reported as a duplicate of a chain with an otherwise identical matcher and no `source_ports`. Entries above 65535 are accepted and never match.
- **Evidence:** grpc 515aaa1743: [xds_listener_parser.cc L587-L593](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_listener_parser.cc#L587-L593), [xds_listener_parser.cc L743-L754](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_listener_parser.cc#L743-L754), [xds_server_config_fetcher.cc L763-L777](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/server/xds_server_config_fetcher.cc#L763-L777)
- **Spec:** xDS-Enabled Servers (`09-xds/08-server.md`), "Listener Validation"

### [low] `weighted_round_robin` does not count `rr_fallback` when only one of several READY endpoints has a usable weight

- **Item:** audit (WRR-21)
- **Summary:** With two or more READY endpoints and exactly one usable weight, C++ builds a static-stride scheduler with every weight equal (behaving like round_robin) but doesn't increment `grpc.lb.wrr.rr_fallback`.
- **Description:** `StaticStrideScheduler::Make` returns `std::nullopt`, and so triggers the `rr_fallback` increment in `Picker::BuildSchedulerAndStartTimerLocked`, only when there is a single weight or every weight is zero. With one non-zero weight among N ≥ 2, the zero weights are replaced by the mean (equal to that one weight), and a scheduler is returned. The spec (`rr_fallback`: "Scheduler updates with fewer than two endpoints with usable weights"), gRFC A78 ("not enough endpoints with valid weight, which caused the WRR policy to fall back to RR behavior"), Java, and Go all count this case.
- **Evidence:** [static_stride_scheduler.cc#L79-L101](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_round_robin/static_stride_scheduler.cc#L79-L101), [weighted_round_robin.cc#L696-L713](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_round_robin/weighted_round_robin.cc#L696-L713)
- **Spec:** `weighted_round_robin` LB Policy: Building the Scheduler; Metrics

### [low] C++ fault-injection filter treats an unrecognized `FractionalPercent.denominator` as `HUNDRED` instead of NACKing

- **Item:** XDS_FAULT-20 (converted review item)
- **Summary:** In `HTTPFault` `delay.percentage` and `abort.percentage`, an unrecognized `FractionalPercent.denominator` enum value is silently treated as `HUNDRED` (denominator 100), and the Listener/RouteConfiguration is accepted.
- **Description:** `Common Types` §5 (Fractional Percentages) requires any `denominator` other than `HUNDRED`, `TEN_THOUSAND`, or `MILLION` to reject the resource, and xDS HTTP Filters §8.1 applies that rule to the fault filter's percentages (Envoy's `percent.proto` marks `DenominatorType` `defined_only`; Java NACKs). C++'s fault filter computes the denominator with a local `GetDenominator` helper whose `default:` case returns 100, so no validation error is recorded.
- **Evidence:** grpc 515aaa1743: [xds_http_fault_filter.cc L47-L64](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_fault_filter.cc#L47-L64) (`GetDenominator`), used at [L146](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_fault_filter.cc#L146) and [L176](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_fault_filter.cc#L176).
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), Fractional Percentages; xDS HTTP Filters (`09-xds/07-http-filters.md`), Fault Injection: Configuration

### [low] C++ xDS server does not perform configuration error logging for unusable RDS resources or non-`non_forwarding_action` routes

- **Item:** XDS_SERVER-20 (converted review item)
- **Summary:** The C++ xDS server does not log a default-visible warning when an RDS resource it uses becomes unusable or when a RouteConfiguration contains a route whose action is not `non_forwarding_action`, and logs nothing when the error clears.
- **Description:** xDS-Enabled Servers §9 (from gRFC A36 "configuration error logging") says the server SHOULD log a warning each time it receives an update while an unusable RDS resource or a non-`non_forwarding_action` route will cause RPC failures, and SHOULD log a single message once no such error remains. In C++, `L4FilterChain::OnRouteConfigChanged` converts an RDS error into an `UNAVAILABLE` config selector with only a trace-level log; `OnAmbientError` logs at ERROR but there is no recovery message; non-`non_forwarding_action` routes are only flagged for per-RPC failure.
- **Evidence:** grpc 515aaa1743: [xds_server_config_fetcher.cc L1210-L1233](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/server/xds_server_config_fetcher.cc#L1210-L1233), [L1260-L1270](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/server/xds_server_config_fetcher.cc#L1260-L1270).
- **Spec:** xDS-Enabled Servers (`09-xds/08-server.md`), Configuration Error Logging

### [low] Channelz reports ALTS-secured sockets as `tls`

- **Item:** audit (bugs-cpp follow-up)
- **Summary:** Every security handshake that creates a frame protector (TLS and ALTS) fills the channelz socket `security` field with the `tls` variant; for ALTS the result is a `tls` entry with no cipher suite and no certificates.
- **Description:** The spec's channelz `Security` is a oneof: `tls` for TLS, and `other` (`name` plus an `Any` value) for any other mechanism. C++'s `MakeChannelzSecurityFromAuthContext` always sets `ModelType::kTls` (a TODO says it assumes TLS) and fills only `remote_certificate`. ALTS uses the same `SecurityHandshaker`, so ALTS sockets are reported as TLS. Local credentials create no frame protector, so they correctly report no security.
- **Evidence:** [security_handshaker.cc L193-L212](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/handshaker/security/security_handshaker.cc#L193-L212), [L302-L306](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/handshaker/security/security_handshaker.cc#L302-L306); ALTS uses it: [alts_security_connector.cc L112](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/alts/alts_security_connector.cc#L112).
- **Spec:** Channelz: Security

### [low] ORCA recorders accept non-finite metric values

- **Item:** ORCA_SVC-20
- **Summary:** The recorders accept `+Infinity` for `cpu_utilization`, `application_utilization`, `rps_fractional`, and `eps`, and accept `NaN` and `±Infinity` for `request_cost` and `named_metrics` values.
- **Description:** The spec's valid ranges contain only finite numbers (`[0, ∞)` means finite non-negative values; `request_cost` and `named_metrics` take any finite value), and recorders MUST ignore values outside the valid range. `IsUtilizationWithSoftLimitsValid` and `IsRateValid` check only `value >= 0.0` (which rejects `NaN` but not `+Infinity`), and `RecordRequestCostMetric` / `RecordNamedMetric` check nothing. A non-finite value in a report can corrupt the client-side `weighted_round_robin` weight.
- **Evidence:** [backend_metric_recorder.cc L36-L45](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/backend_metric_recorder.cc#L36-L45), [L307-L325](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/backend_metric_recorder.cc#L307-L325).
- **Spec:** Backend Metrics (ORCA): Data Model

### [low] Authorization policy translator rejects an empty `deny_rules`, accepts an empty `name`, and checks the `grpc-` prefix case-sensitively

- **Item:** AUTHZ-4
- **Summary:** C++ rejects a gRPC authorization policy with `"deny_rules": []`, accepts one with `"name": ""`, and accepts header keys such as `GRPC-foo`.
- **Description:** The spec treats an empty `deny_rules` array as absent, requires a non-empty policy `name`, and compares disallowed header keys (including the `grpc-` and `:` prefixes) case-insensitively. C++ fails an empty `deny_rules` with "rules is empty.", checks only that `name` is present, and compares the `grpc-` prefix case-sensitively (the hop-by-hop and `host` checks are case-insensitive). Java and Go accept an empty `deny_rules` and reject an empty `name`; Go lowercases the key before every check.
- **Evidence:** grpc 515aaa1743: [rbac_translator.cc L320](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/rbac_translator.cc#L320), [L505](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/rbac_translator.cc#L505), [L176](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/rbac_translator.cc#L176)
- **Spec:** gRPC Authorization: 2.1 Schema

### [low] Trailing dot of the default authority sent in SNI

- **Item:** TLS-22
- **Summary:** For a default authority that is a fully qualified name with a trailing dot (for example from `dns:///example.com.:443`), C++ sends `example.com.` as the TLS SNI.
- **Description:** The spec, following RFC 6066 §3 ("without a trailing dot"), says one trailing `.` is removed from the name before it is sent as SNI. `TlsChannelSecurityConnector` keeps the host from `SplitHostPort` unchanged and passes it to `SSL_set_tlsext_host_name`, skipping only IP-looking names. A server that is strict about SNI may reject the handshake or pick the wrong certificate. (Hostname verification already strips the dot in `does_entry_match_name`, which agrees with the spec.)
- **Evidence:** `src/core/credentials/transport/tls/tls_security_connector.cc` (https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/tls/tls_security_connector.cc#L285-L288, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/credentials/transport/tls/tls_security_connector.cc#L364-L366); `src/core/tsi/ssl_transport_security.cc` (https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/tsi/ssl_transport_security.cc#L3006-L3010).
- **Spec:** TLS: Server Name Indication (SNI)

### [low] `priority_experimental` does not accept `ignoreReresolutionRequests`

- **Item:** PRIORITY-4
- **Summary:** C++ `priority` config parsing reads only the snake_case `ignore_reresolution_requests`, and `cds` generates that name. The JSON name the spec uses, `ignoreReresolutionRequests`, is ignored.
- **Description:** The spec names the child field `ignoreReresolutionRequests` (lowerCamelCase, as in the rest of the service config and as `service_config.proto`'s JSON mapping gives) and lets parsers also accept `ignore_reresolution_requests`. C++'s JSON loader for the child config reads only `"ignore_reresolution_requests"`, so a config that uses `ignoreReresolutionRequests: true` silently gets `false`. Suggested fix: accept `ignoreReresolutionRequests` (keep the snake_case name for compatibility) and generate the camelCase name in `cds`.
- **Evidence:** `src/core/load_balancing/priority/priority.cc` (https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/priority/priority.cc#L784-L785); `src/core/load_balancing/xds/cds.cc` (https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/cds.cc#L546).
- **Spec:** `priority` LB Policy: Configuration; `cds` LB Policy: Child Config for a Non-Aggregate Cluster

### [low] "Don't retry" pushback not counted by retry throttling for RPCs without a retry policy

- **Item:** RETRY-1
- **Summary:** When an RPC's method has no retry policy, C++ does not record a `retryThrottling` failure for a response that carries a "do not retry" (negative or unparseable) `grpc-retry-pushback-ms`.
- **Description:** The spec (following gRFC A6: "Every outgoing RPC (regardless of service or method invoked)…"; "…or that receive a pushback response indicating not to retry") says a "do not retry" pushback subtracts 1 from `token_count` for every RPC on the channel, policy or not, the same way successes are counted for every RPC. `ShouldRetry` returns first thing when there is no retry policy, before it looks at pushback. Related: the existing C++ medium bug "\"Don't retry\" pushback on a non-retryable code is not counted by retry throttling" (R42) is in the same function; fixing both means checking pushback before both the policy and the retryable-code checks.
- **Evidence:** `src/core/client_channel/retry_filter_legacy_call_data.cc` (https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_filter_legacy_call_data.cc#L534-L535); `src/core/client_channel/retry_interceptor.cc` (https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_interceptor.cc#L60-L65).
- **Spec:** Retries and Hedging: Behavior; Retries and Hedging: Token Accounting

### [low] Send message size limit checked against the uncompressed size instead of the framed size

- **Item:** MESSAGE_SIZE-20
- **Summary:** C++ checks the send limit (`GRPC_ARG_MAX_SEND_MESSAGE_LENGTH`, `maxRequestMessageBytes`) against the uncompressed payload, and never checks the compressed (framed) size on send.
- **Description:** The spec (following `service_config.proto`: "The size which is measured is the serialized payload after per-message compression") says the send limit is checked against the message as framed and MUST NOT be applied to the uncompressed size. The message size filters sit above the compression filter on the client, and on the server too unless the off-by-default `fix_v3_filter_stack_server_side_ordering` experiment is on, so `CheckPayload` sees the uncompressed length. A compressible message whose framed size is within the limit fails with `RESOURCE_EXHAUSTED`. Sender and receiver with the same limit also disagree, because the receiver checks the wire length.
- **Evidence:** `src/core/ext/filters/http/http_filters_plugin.cc` (https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/http_filters_plugin.cc#L40-L84); `src/core/ext/filters/message_size/message_size_filter.cc` (https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/message_size/message_size_filter.cc#L63-L78, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/message_size/message_size_filter.cc#L116-L130).
- **Spec:** Core RPC Semantics: Message Size Limits

### [low] RBAC matches binary headers on decoded bytes instead of base64

- **Item:** AUTHZ-2
- **Summary:** C++ RBAC/authorization-policy header matchers compare a `-bin` header's decoded binary value instead of its unpadded base64 form.
- **Description:** The spec (following gRFC A41: "Binary headers are represented in their base64-encoded form") says `-bin` headers are matched in unpadded base64 form, each value encoded separately and then joined with `,`. `EvaluateArgs::GetHeaderValue` returns `metadata_->GetStringValue(key, ...)`, which holds the decoded bytes, so value matchers (exact, prefix, regex, and so on) written against the base64 form never match. Presence matchers are unaffected.
- **Evidence:** `src/core/call/evaluate_args.cc` (https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/evaluate_args.cc#L125-L139).
- **Spec:** Authorization: Header Matching Rules

### [low] Aggregate cluster type check strips only the `type.googleapis.com/` prefix

- **Item:** XDS_COMMON-1
- **Summary:** C++ recognizes an aggregate `cluster_type` only when its `type_url` prefix is exactly `type.googleapis.com/`.
- **Description:** C++ `ExtractXdsExtension` correctly takes the text after the last `/`, but the CDS parser's aggregate `cluster_type` check uses `absl::StripPrefix(type_url, "type.googleapis.com/")`, so any other prefix makes the aggregate cluster type unrecognized. The spec says the prefix is not checked.
- **Evidence:** grpc 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81: [xds_cluster_parser.cc L467-L471](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L467-L471)
- **Spec:** Common Types: Extensions: `google.protobuf.Any` and `TypedStruct`

### [low] Empty `prefix`, `suffix`, `contains`, and regex accepted in `StringMatcher` and `HeaderMatcher`

- **Item:** XDS_COMMON-20
- **Summary:** C++ accepts `""` for `prefix`/`prefix_match`, `suffix`/`suffix_match`, `contains`/`contains_match`, and `safe_regex.regex`/`safe_regex_match.regex`.
- **Description:** The spec (following Envoy's PGV `min_len: 1` rules) requires these strings to be non-empty and rejects the resource otherwise. C++ accepts empty values everywhere (routing header matchers, RBAC, security SAN matchers), treating them as match-all patterns.
- **Evidence:** grpc 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81: [xds_common_types_parser.cc L209-L249](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_common_types_parser.cc#L209-L249), [xds_common_types_parser.cc L294-L363](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_common_types_parser.cc#L294-L363)
- **Spec:** Common Types: `StringMatcher`; Common Types: `HeaderMatcher`

### [low] Fault injection: out-of-range `grpc_status` NACKed; missing `error_type` and out-of-range `http_status` accepted

- **Item:** XDS_FAULT-2
- **Summary:** C++ NACKs a `FaultAbort.grpc_status` above 16, but accepts a `FaultAbort` with no `error_type` and an `http_status` outside [200, 600).
- **Description:** The spec follows Envoy: any `grpc_status` is accepted (a value outside 0–16 aborts with `UNKNOWN`), `http_status` MUST be in [200, 600), and a `FaultAbort` MUST have its `error_type` set, else the Listener (or the resource with the override) is NACKed. C++ rejects `grpc_status` > 16 ("invalid gRPC status code"), maps any non-zero, non-200 `http_status`, and treats a `FaultAbort` with no error type as no abort.
- **Evidence:** grpc 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81: [xds_http_fault_filter.cc L113-L132](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_fault_filter.cc#L113-L132)
- **Spec:** xDS HTTP Filters: Fault Injection: Configuration

### [low] RBAC `CidrRange.prefix_len` above 128 accepted

- **Item:** XDS_RBAC-22
- **Summary:** C++ accepts an RBAC `CidrRange.prefix_len` greater than 128 instead of NACKing.
- **Description:** The spec (following Envoy's `lte: 128` rule) NACKs `prefix_len` > 128 and clamps values between the address width and 128. C++ does not validate `prefix_len`; any value at or above the width acts as a full-length mask, which matches the clamping but accepts values above 128.
- **Evidence:** grpc 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81: [xds_http_rbac_filter.cc L603-L611](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L603-L611), [sockaddr_utils.cc L419-L439](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/address_utils/sockaddr_utils.cc#L419-L439)
- **Spec:** xDS HTTP Filters: RBAC: Configuration Validation

### [low] CDS: non-empty `transport_socket_matches` not rejected

- **Item:** XDS_CDS-3
- **Summary:** C++ ignores `Cluster.transport_socket_matches` instead of NACKing a Cluster that sets it.
- **Description:** The spec rejects a Cluster with a non-empty `transport_socket_matches`, since ignoring it could drop TLS that the control plane intended for some endpoints. C++ selects the transport socket only from `transport_socket.typed_config` and never looks at `transport_socket_matches`.
- **Evidence:** grpc 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81: [xds_cluster_parser.cc L491-L513](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L491-L513)
- **Spec:** Cluster: Transport Socket; xDS Security: Locating the TLS Context

### [low] `google-c2p` always sets `TRAFFICDIRECTOR_DIRECTPATH_C2P_IPV6_CAPABLE` without querying the metadata server

- **Item:** VENDOR-3
- **Summary:** C++'s `google-c2p` resolver sends only the zone query and always reports the client as IPv6-capable.
- **Description:** The spec says the resolver queries `.../network-interfaces/0/ipv6s` and sets the node metadata only if the trimmed body is non-empty. C++ `StartLocked` sends only the zone query; `IPv6QueryDone` is declared but never defined or called, and the generated bootstrap always sets the metadata to `true`. On IPv4-only VMs Traffic Director may then send IPv6 endpoints the client can't reach.
- **Evidence:** grpc 515aaa1743ec9a318e7e22d11a5bfaa835d5fa81: [google_c2p_resolver.cc L72](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/google_c2p/google_c2p_resolver.cc#L72), [L162-L175](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/google_c2p/google_c2p_resolver.cc#L162-L175), [L215-L218](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/google_c2p/google_c2p_resolver.cc#L215-L218)
- **Spec:** `google-c2p` Resolver: Metadata Server Queries

### [low] Unregistered `typed_filter_metadata` entries are extracted and validated, and can reject the resource

- **Item:** XDS_COMMON-21
- **Summary:** `ParseXdsMetadataMap` calls `ExtractXdsExtension` on every `Metadata.typed_filter_metadata` entry before it checks the metadata registry. As a result, an unregistered entry with a malformed `type_url` or an unparseable `TypedStruct` NACKs the Cluster or ClusterLoadAssignment, and a `TypedStruct` wrapping `Audience` or `Address` is NACKed.
- **Description:** The spec (following gRFC A83) looks up the type name of `Any.type_url` directly in the metadata registry. Entries whose type isn't registered are ignored without any validation, and a `TypedStruct` is not unwrapped, so a `TypedStruct` wrapping a registered type is treated as unregistered and the key falls back to `filter_metadata`. C++ runs extension extraction first, so unrelated control-plane or Envoy metadata that fails extraction rejects the whole resource. Java and Go follow A83.
- **Evidence:** grpc 515aaa1743: [xds_metadata_parser.cc L120-L153](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_metadata_parser.cc#L120-L153) (`ParseXdsMetadataMap`)
- **Spec:** Common Types: Metadata › Parsing (`09-xds/04-resources/01-common-types.md`)

### [low] Top-level-only HTTP filter config in `typed_per_filter_config` is ignored when wrapped in `FilterConfig{is_optional: true}`

- **Item:** XDS_FILTERS-20
- **Summary:** The HTTP filter registry indexes override types only by `OverrideConfigProtoName()`, so a registered filter's top-level-only config type (for example `Router`, or `RBAC` instead of `RBACPerRoute`) in `typed_per_filter_config` is treated as an unknown type. When it is wrapped in `FilterConfig{is_optional: true}`, it is silently skipped.
- **Description:** The spec (following gRFC A39) says that if the override config type is registered by any filter, as either a top-level or an override type, the filter validates it as an override. A top-level config type for a filter that has no override type, or that uses a different one, fails validation and NACKs the resource even if `FilterConfig.is_optional` is true. `is_optional` covers only types that no filter registers. Java and Go NACK. C++ ignores the entry.
- **Evidence:** grpc 515aaa1743: [xds_http_filter_registry.cc L27-L52](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_filter_registry.cc#L27-L52), [xds_route_config_parser.cc L328-L335](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_route_config_parser.cc#L328-L335)
- **Spec:** xDS HTTP Filters: Override Configuration (`typed_per_filter_config`) (`09-xds/07-http-filters.md`)

### [low] Stateful session filter misses the session cookie when `cookie` metadata has more than one entry

- **Item:** XDS_SSA-1
- **Summary:** `GetCookieValue` reads `GetStringValue("cookie")`, which joins multiple entries with `","`, and then splits on `"; "`. A session cookie that isn't in the first entry is therefore missed or merged into the previous cookie's value.
- **Description:** The spec (following gRFC A55; Envoy agrees) says every `cookie` metadata entry is parsed, and the first cookie whose name matches across all entries is used. With entries `a=1` and `sess=X`, C++ sees one cookie `a` with value `1,sess=X`, so SSA silently falls back to normal load balancing.
- **Evidence:** grpc 515aaa1743: [metadata_batch.cc L115-L128](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/metadata_batch.cc#L115-L128), [stateful_session_filter.cc L187-L208](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/stateful_session/stateful_session_filter.cc#L187-L208)
- **Spec:** xDS HTTP Filters: Stateful Session Affinity › Request Processing (`09-xds/07-http-filters.md`)

### [low] Channelz GetServerSockets treats a negative `max_results` as an unlimited page size

- **Item:** CHANNELZ-5
- **Summary:** A negative `max_results` in `GetServerSocketsRequest` is cast to `size_t`, which makes the page size effectively unlimited.
- **Description:** The spec lets the server reject a negative `max_results` or treat it as zero, but says the server MUST NOT treat it as an unlimited page. `ChannelzService::GetServerSockets` uses `static_cast<size_t>(request->max_results())` for any non-zero value, so `-1` becomes `SIZE_MAX` and every socket of the server is returned in one response. That is expensive on servers with many connections. Fix: treat values ≤ 0 as the default (`kMaxResults`), or reject negatives with `INVALID_ARGUMENT`.
- **Evidence:** grpc 515aaa1743: [channelz_service.cc L154-L156](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/server/channelz/channelz_service.cc#L154-L156)
- **Spec:** Channelz: Pagination

### [low] LOGICAL_DNS cluster accepts an explicit `port_value` of 0

- **Item:** XDS_CDS-21
- **Summary:** A `LOGICAL_DNS` Cluster whose `socket_address` sets `port_value: 0` explicitly is accepted, because only oneof presence is checked.
- **Description:** The spec says the `LOGICAL_DNS` `port_value` MUST be in 1–65535. `LogicalDnsParse` checks only `envoy_config_core_v3_SocketAddress_has_port_value` (the `port_specifier` oneof case), then builds `host:0`. Port 0 can never reach a DNS-resolved backend, so RPCs fail at connect time instead of the resource being NACKed. (Ports above 65535 are a separate existing bug.)
- **Evidence:** grpc 515aaa1743: [xds_cluster_parser.cc L268-L274](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L268-L274)
- **Spec:** Cluster: Logical DNS Clusters

### [low] EDS rejects a LocalityLbEndpoints with no locality

- **Item:** XDS_EDS-2
- **Summary:** A `LocalityLbEndpoints` entry (with non-zero weight) whose `locality` field is unset makes the resource invalid, instead of being treated as the empty locality.
- **Description:** The spec, following Envoy, treats an unset `locality` as the empty locality (`region`, `zone`, `sub_zone` all empty). `LocalityParse` adds "field not present" for `.locality` and NACKs the ClusterLoadAssignment. It does skip unset/0-weight entries first, as the spec requires.
- **Evidence:** grpc 515aaa1743: [xds_endpoint_parser.cc L226-L235](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_endpoint_parser.cc#L226-L235)
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: LocalityLbEndpoints

### [low] EDS NACKs a drop_overloads entry with no drop_percentage

- **Item:** XDS_EDS-4
- **Summary:** A `DropOverload` whose `drop_percentage` is unset NACKs the resource ("field not present") instead of meaning a drop rate of 0.
- **Description:** The spec, following Envoy (which reads an unset `drop_percentage` as the default `FractionalPercent`, numerator 0), says an unset `drop_percentage` means a drop rate of 0. `DropParseAndAppend` adds an error and returns when `drop_percentage` is null.
- **Evidence:** grpc 515aaa1743: [xds_endpoint_parser.cc L300-L311](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_endpoint_parser.cc#L300-L311)
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: Drop Overloads

### [low] EDS drop rate normalization can wrap in uint32 before the cap

- **Item:** XDS_EDS-4
- **Summary:** `DropParseAndAppend` multiplies the numerator by 10,000 (HUNDRED) or 100 (TEN_THOUSAND) in `uint32_t` before capping at 1,000,000, so an oversized numerator can wrap to a small value.
- **Description:** The spec caps the normalized drop rate at 1,000,000 per million. A HUNDRED numerator above 429,496 (or a TEN_THOUSAND numerator above 42,949,672) wraps. For example, 429,497 × 10,000 wraps to 2,704, so the drop rate becomes about 0.27% instead of 100%. Fix: clamp the numerator to the denominator before multiplying, or compute in 64 bits.
- **Evidence:** grpc 515aaa1743: [xds_endpoint_parser.cc L311-L332](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_endpoint_parser.cc#L311-L332)
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: Drop Overloads

### [low] `weighted_target` treats a child's TRANSIENT_FAILURE as sticky when aggregating

- **Item:** WEIGHTED_TARGET-2
- **Summary:** A child that reported TRANSIENT_FAILURE keeps counting as TRANSIENT_FAILURE in the aggregate until it reports READY.
- **Description:** The spec aggregates `weighted_target` children with the normal rules, using each child's current state. Sticky TRANSIENT_FAILURE is handled by the `pick_first` children (gRFC A62), so the parent doesn't need its own. C++ keeps a child in TRANSIENT_FAILURE for aggregation until it reports READY, which predates A62.
- **Evidence:** [weighted_target.cc L606-L614](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_target/weighted_target.cc#L606-L614).
- **Spec:** `weighted_target` LB Policy: Calls From Children

