# Spec review items

Open decisions for the gRPC spec draft in `grpc/doc/spec/`: **45** items, grouped by type (spec divergences first, then doc conflicts, language divergences, judgment calls, and language bugs last) and, within each type, sorted by position in the spec (by full section number; LB policy docs follow their parent section, and appendices come last). Each item is named for the system it concerns, and each matches an inline `<!-- REVIEW(...) [<name>]: ... -->` comment at the linked line in the spec.

The type in each header is one of:

- **language bug** — the spec matches at least one language (usually the majority or the gRFC); other languages deviate.
- **language divergence** — languages differ and there is no clear right answer yet.
- **spec divergence** — no language implements what the spec says.
- **judgment** — a design choice that implementation behavior doesn't settle.
- **doc conflict** — the spec disagrees with a gRFC or existing doc on a point where the implementations don't settle it (or agree with the spec).

Sections: [Language divergences](#language-divergences-23) · [Judgment calls](#judgment-calls-2) · [Language bugs](#language-bugs-20)

Every item quotes the prior documentation (gRFCs, older `grpc/doc` text, proto comments, or the pending call-semantics and client-channel PRs) that bears on it, or says that no prior documentation covers it. Resolved items are in [resolved_items.md](resolved_items.md); implementation bugs are in [bugs_go.md](bugs_go.md), [bugs_java.md](bugs_java.md), [bugs_cpp.md](bugs_cpp.md), and documentation bugs in [bugs_docs.md](bugs_docs.md).

## Language divergences (23)

### WEIGHTED_TARGET-2. Sticky TRANSIENT_FAILURE in weighted_target aggregation (language divergence)

C++ and Go treat a child's TRANSIENT_FAILURE as sticky when they aggregate. The spec and Java use the plain normal rules.

- **Where:** [`weighted_target` LB Policy: 5.2 Calls From Children](04-client-channel/lb-policies/weighted_target.md#52-calls-from-children) in `04-client-channel/lb-policies/weighted_target.md`
- **Current spec:** "The aggregate state is computed over all children with the normal rules (first match wins)". Load Balancing › Connectivity State Aggregation limits the sticky-TRANSIENT_FAILURE variation to `round_robin`, `weighted_round_robin`, and `least_request`.
- **Findings:**
  - C++: a child counts as TRANSIENT_FAILURE until it reports READY. It also calls `ExitIdle()` on any child that reports IDLE ([weighted_target.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/weighted_target/weighted_target.cc#L606-L616))
  - Java: plain normal rules ([WeightedTargetLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/WeightedTargetLoadBalancer.java#L146-L196))
  - Go: ignores only TRANSIENT_FAILURE → CONNECTING. TRANSIENT_FAILURE → IDLE is counted ([aggregator.go](https://github.com/grpc/grpc-go/blob/v1.82.0/balancer/weightedtarget/weightedaggregator/aggregator.go#L204-L210))
- **Prior documentation:**
  - gRFC A28, "Weighted target LB policy": "The WRR algorithm will be random based." It says nothing about state aggregation.
  - Not otherwise covered (searched: A28, A42, A56, A61, A62; `doc/load-balancing.md`).
- **Decision:** (a) normal rules (spec, Java); (b) sticky TRANSIENT_FAILURE until READY (C++), also for IDLE; (c) ignore only TRANSIENT_FAILURE → CONNECTING (Go).
- **Recommendation:** (b). Children are petiole policies that already apply sticky TRANSIENT_FAILURE, and a locality that keeps flapping TRANSIENT_FAILURE → CONNECTING should not hold the whole priority in CONNECTING (which delays the `priority` failover timer path). Add `weighted_target` to the sticky-TRANSIENT_FAILURE variation. Bugs: Java (medium), Go (low: the TRANSIENT_FAILURE → IDLE gap).
- **Why this rank:** Affects whether RPCs queue or fail, and how failover behaves, when a locality is retrying.

### RETRY-7. Case-3 transparent retry after a configured retry (language divergence)

Languages differ on whether the one "reached the server library but not the application" transparent retry can happen after a configured retry.

- **Where:** [4.12.8 Transparent Retries](04-client-channel/12-retries.md#8-transparent-retries) in `04-client-channel/12-retries.md`
- **Current spec:** Case 3: "Transparently retried **once** per RPC. If that retry also fails this way, the failure goes to the configured retry policy." It does not say whether it can happen on a later attempt.
- **Findings:**
  - C++: allowed on any uncommitted attempt, at most once per RPC (`sent_transparent_retry_not_seen_by_server_`). ([retry_filter_legacy_call_data.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_filter_legacy_call_data.cc#L1111-L1122))
  - Java: `REFUSED` is retried transparently only if `noMoreTransparentRetry` is still false. Any non-transparent attempt failure sets it, so after the first configured retry REFUSED goes to the retry policy. (`MISCARRIED`, case 2, is unlimited up to 1000.) ([RetriableStream.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L962-L996))
  - Go: `cs.firstAttempt && unprocessed` allows it only on the very first attempt; `firstAttempt` is cleared after any retry. ([stream.go](https://github.com/grpc/grpc-go/blob/v1.82.0/stream.go#L702-L705), [stream.go](https://github.com/grpc/grpc-go/blob/v1.82.0/stream.go#L791))
- **Prior documentation:** gRFC A6, "Transparent Retries": "If the RPC reaches the gRPC server library, but has never been seen by the server application logic (the third case), the client library will immediately retry it once. If this fails, then the RPC will be handled by the configured retry policy." It does not decide the question.
- **Decision:** (a) once per RPC, on any attempt (C++, current wording); (b) only before the first configured retry (Java, Go); or (c) leave it implementation-defined.
- **Recommendation:** (a). A REFUSED_STREAM on a later attempt (for example during a server's graceful shutdown) is just as safe to retry, and the once-per-RPC cap already bounds the extra load. State it outright. Bugs (low): Java and Go: case-3 transparent retry not available after a configured retry.
- **Why this rank:** A rare edge case. The effect is that a configured retry attempt is used up (or the RPC fails) instead of retrying transparently.

### SERVER-6. Malformed `:path` and the unknown-method handler (language divergence)

Implementations differ on whether a `:path` that is not of the form `/<service>/<method>` reaches the unknown-method handler. Core RPC Semantics also contradicts this section.

- **Where:** [5.1.2.2 Method Dispatch](05-server/01-server.md#22-method-dispatch) in `05-server/01-server.md`
- **Current spec:** A malformed `:path` cannot match a registered method. It goes to the unknown-method handler if there is one, and otherwise fails with UNIMPLEMENTED. Core RPC Semantics: Call ABNF (`02-rpc-semantics/README.md`) says a call whose name "is malformed ... or matches no registered method fails with `UNIMPLEMENTED`", and does not mention the unknown-method handler.
- **Findings:**
  - C++: every unmatched path, malformed or not, goes to the unregistered (generic) request matcher ([server.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/server/server.cc#L1101)).
  - Java: a path with no leading `/` is rejected in the transport with HTTP 404 plus UNIMPLEMENTED ([NettyServerHandler.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyServerHandler.java#L491-L495)). A path like `/foo` goes to the fallback registry ([ServerImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ServerImpl.java#L545)).
  - Go: a path with no leading `/`, or no `/` between service and method, goes to `handleMalformedMethodName` (UNIMPLEMENTED). The unknown-service handler is never called ([server.go](https://github.com/grpc/grpc-go/blob/v1.82.0/server.go#L1825-L1834), compare [L1867](https://github.com/grpc/grpc-go/blob/v1.82.0/server.go#L1867)).
- **Prior documentation:**
  - doc/PROTOCOL-HTTP2.md: "Path → ":path" "/" Service-Name "/" {_method name_}". This defines the well-formed shape only and says nothing about handling malformed paths.
  - Resolved item ABNF-1 added the 02-rpc-semantics text ("fail malformed or unmatched names with `UNIMPLEMENTED`"), but did not address unknown-method handlers.
- **Decision:** (a) malformed paths go to the unknown-method handler (C++, current server text), (b) malformed paths always fail with UNIMPLEMENTED, even with an unknown-method handler (Go), (c) implementation-defined.
- **Recommendation:** (c), and fix the 02-rpc-semantics sentence to say "and no unknown-method handler handles it". Proxies and generic handlers rarely see malformed paths, and every choice is safe. Under (c), no bugs.
- **Why this rank:** An edge case for malformed requests, but the two spec documents contradict each other.

### TRANSPORT-7. Minimum server KEEPALIVE_TIME differs and is unspecified (language divergence)

The server table says `KEEPALIVE_TIME` has the "same meaning as on the client", and the client rules include the 10-second floor. Servers enforce three different floors.

- **Where:** [5.2.2.7.1 Keepalive](05-server/02-transports/02-http2.md#71-keepalive) in `05-server/02-transports/02-http2.md`
- **Current spec:** Server `KEEPALIVE_TIME` | 2 hours | "Same meaning as on the client." The client row says "Values below 10 seconds MUST be raised to 10 seconds."
- **Findings:**
  - C++: 1 ms floor, the same code path as the client ([chttp2_transport.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/chttp2_transport.cc#L441-L445)).
  - Java: 10 s floor ([NettyServerBuilder.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyServerBuilder.java#L587-L590), via `KeepAliveManager.clampKeepAliveTimeInNanos`).
  - Go: 1 s floor ([server.go](https://github.com/grpc/grpc-go/blob/v1.82.0/server.go#L338-L340)).
- **Prior documentation:**
  - gRFC A9 gives only the default ("`KEEPALIVE_TIME`, defaulting to `2 hours`"). A8's 10-second floor is stated for "Clients". Not otherwise covered (searched A8, A9, doc/keepalive.md).
- **Decision:** (a) say the 10-second floor is client-only and the server floor is implementation-defined, (b) apply the 10-second floor to servers too.
- **Recommendation:** (a). Server pings are not subject to peer abuse enforcement, so a floor matters less. Reword the server row so it doesn't inherit the client floor. No bugs.
- **Why this rank:** Spec ambiguity with little interop impact.

### TRANSPORT-6. Ping enforcement: Go and C++ measure from the last PING received, not the last valid one (language divergence)

The spec's ping-enforcement pseudocode (from A8) updates `last_valid_ping_time` only for an acceptable PING. Go and C++ update their timestamp on every PING received, including PINGs that earn a strike. Java follows the pseudocode, but its `epoch` is the transport's creation time.

- **Where:** [5.2.2.7.2 Ping Enforcement](05-server/02-transports/02-http2.md#72-ping-enforcement) in `05-server/02-transports/02-http2.md`
- **Current spec:** `if ok: last_valid_ping_time = now() else: ping_strikes += 1 …`; on HEADERS or DATA sent, `last_valid_ping_time = epoch`.
- **Findings:**
  - C++: `last_ping_recv_time_ = now` before the comparison, so it is updated for every PING ([ping_abuse_policy.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/transport/chttp2/transport/ping_abuse_policy.cc#L53-L62)). The reset sets it to `InfPast`, which matches `epoch`.
  - Java: updates only on a valid PING ([KeepAliveEnforcer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/KeepAliveEnforcer.java#L57-L71)). But `epoch = ticker.nanoTime()` at construction ([L51-L52](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/KeepAliveEnforcer.java#L51-L52)), so after a reset, a PING within `PERMIT_KEEPALIVE_TIME` of connection start counts as a strike.
  - Go: `defer t.lastPingAt = now` runs for every PING. After a reset, the next PING is accepted unconditionally ([http2_server.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/transport/http2_server.go#L892-L917)).
  - Effect: a client pinging steadily a bit faster than allowed is disconnected on its 4th PING in Go/C++. Under the pseudocode, only every other PING is a strike, so it lasts about twice as long.
- **Prior documentation:**
  - gRFC A8, Server Enforcement: "If either verification failed, ping\_strikes++ … otherwise `last_valid_ping_time = now()`" and "set `last_valid_ping_time = epoch`". This matches the spec.
  - doc/keepalive.md: "If the time between successive pings is less that than this time, then the ping will be considered a bad ping". This describes the C++ behavior: successive PINGs, valid or not.
- **Decision:** (a) keep the A8 algorithm and file Go/C++ bugs, (b) allow measuring from the last PING received (either algorithm conforms), (c) adopt the Go/C++ algorithm.
- **Recommendation:** (b). Both variants are stricter or looser only for clients that are already misconfigured. A8 calls it a "Suggested algorithm", and doc/keepalive.md describes the C++ variant. Say that `epoch` means "earlier than any possible PING". No bugs, unless (a) is chosen.
- **Why this rank:** Affects only misbehaving clients. The spec pseudocode currently matches only one implementation.

### AUTHZ-4. Authorization policy validation edge cases (language divergence)

The implementations disagree on an empty `deny_rules` array, an empty policy `name`, and case-insensitive matching of the `grpc-` prefix in header keys.

- **Where:** [6.4.2.1 Schema](06-security/04-authorization.md#21-schema) in `06-security/04-authorization.md`
- **Current spec:** `deny_rules`: "If present, MUST NOT be empty." Policy `name`: required (it doesn't say whether it may be empty). Disallowed header names "are compared case-insensitively".
- **Findings:**
  - C++: rejects an empty `deny_rules` ("rules is empty."). Checks only that `name` is present, so `""` is accepted. The `grpc-` and `:` prefix checks are case-sensitive, while the hop-by-hop and `host` checks are not ([rbac_translator.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/rbac_translator.cc#L320), [L505](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/rbac_translator.cc#L505), [L176](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/rbac_translator.cc#L176)).
  - Java: treats an empty `deny_rules` as absent and rejects an empty `name`. The `grpc-` prefix check is case-sensitive, so `"GRPC-foo"` is accepted, and because `Metadata.Key` lowercases names, the rule then matches the `grpc-foo` header ([AuthorizationPolicyTranslator.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/authz/src/main/java/io/grpc/authz/AuthorizationPolicyTranslator.java#L79-L83), [L175-L187](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/authz/src/main/java/io/grpc/authz/AuthorizationPolicyTranslator.java#L175-L187)).
  - Go: treats an empty `deny_rules` as absent (`len(policy.DenyRules) > 0`) and rejects an empty `name`. Lowercases the key before every check ([rbac_translator.go](https://github.com/grpc/grpc-go/blob/v1.82.0/authz/rbac_translator.go#L369-L380), [L235-L237](https://github.com/grpc/grpc-go/blob/v1.82.0/authz/rbac_translator.go#L235-L237)).
- **Prior documentation:**
  - gRFC A43 schema: `"required": ["name", "allow_rules"]`. It doesn't say whether `deny_rules` may be empty. Its key description says: "The following headers are *not* supported: the \"Host\" header, \"hop-by-hop\" headers ..., HTTP/2 pseudo headers (\":\"-prefixed) and headers prefixed with \"grpc-\"." No case rule is given, but header names are case-insensitive in HTTP.
- **Decision:** (a) empty `deny_rules` is invalid (C++, current spec), or (b) the same as absent (Java, Go). Separately, (c) also require a non-empty policy `name`, and keep the case-insensitive prefix check.
- **Recommendation:** (b) for `deny_rules` (two of three, and harmless), plus (c). Record low bugs: C++ (accepts empty name; case-sensitive `grpc-` check) and Java (case-sensitive `grpc-` check, which lets a policy match a reserved `grpc-` header).
- **Why this rank:** Mostly validation strictness. Only the Java `grpc-` case lets a policy match a header that should not be matchable.

### AUTHZ-6. C++ aborts on duplicate audit logger factory registration (language divergence)

The spec says the last registration under a name wins. C++ aborts the process instead.

- **Where:** [6.4.3.5 Logger Registry and Plugin Contract](06-security/04-authorization.md#35-logger-registry-and-plugin-contract) in `06-security/04-authorization.md`
- **Current spec:** "If two factories are registered under the same name, the last one wins."
- **Findings:**
  - C++: `GRPC_CHECK(registry->logger_factories_map_.emplace(name, std::move(factory)).second)`. A duplicate, including an application factory named `stdout_logger` (which is built in), crashes the process ([audit_logging.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/security/authorization/audit_logging.cc#L50-L57)).
  - Java: no audit logging.
  - Go: `registry.builders[b.Name()] = b`, so the last registration wins ([audit_logger.go](https://github.com/grpc/grpc-go/blob/v1.82.0/authz/audit/audit_logger.go#L46-L50)).
- **Prior documentation:**
  - gRFC A59, Go API: "If multiple builders are registered with the same name, the one registered last will take effect." The C++ API says only: "Registers an audit logger factory. This should only be called during initialization." It gives no duplicate rule.
- **Decision:** (a) last wins (Go, A59 Go API), (b) a duplicate is an error, reported in an implementation-defined way (C++ crash allowed), (c) implementation-defined.
- **Recommendation:** (c), with "SHOULD NOT register two factories under the same name". Registration happens at init and is under the application's control. Under (c), no bugs. If the owner prefers (a), record a low C++ bug.
- **Why this rank:** Init-time programming error only.

### METRICS-7. Callback gauge minimum interval exists only in C++ (language divergence)

The spec requires a per-callback minimum interval with a 5-second default. Only C++ supports it. Java and Go callbacks take no interval and run on every collection.

- **Where:** [8.3.4 Callback Gauges](08-observability/03-metrics-framework.md#4-callback-gauges) in `08-observability/03-metrics-framework.md`
- **Current spec:** "A component registers a callback … together with the list of gauge handles … and a **minimum interval**. The default minimum interval is **5 seconds**. Each plugin invokes the callback when it collects metrics, but no more often than the minimum interval."
- **Findings:**
  - C++: `RegisterCallback(..., Duration min_interval)`, and the OTel plugin skips the callback if `now - last < min_interval()`. ([metrics.h](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/telemetry/metrics.h#L486), [otel_plugin.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/cpp/ext/otel/otel_plugin.cc#L1317))
  - Java: `registerBatchCallback(BatchCallback, CallbackMetricInstrument...)` has no interval. ([MetricRecorder.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/MetricRecorder.java#L139))
  - Go: `RegisterAsyncReporter(AsyncMetricReporter, ...AsyncMetric)` has no interval. ([metrics.go](https://github.com/grpc/grpc-go/blob/v1.82.0/experimental/stats/metrics.go#L86), [metricregistry.go](https://github.com/grpc/grpc-go/blob/v1.82.0/experimental/stats/metricregistry.go#L316))
- **Prior documentation:**
  - gRFC A79 (Core API only): "The callback will be invoked no more often than min_interval." The example declares `Duration min_interval = Duration::Seconds(5)`. The Java and Go API sections have no interval.
- **Decision:** (a) Keep the requirement (Java and Go bugs). (b) Make the minimum interval a MAY: a component MAY give one, and a plugin that supports it MUST honor it. (c) Drop the interval from the spec.
- **Recommendation:** (b). Only the Core API section of A79 has the interval, and the plugin's collection period already limits how often callbacks run. Bugs: none.
- **Why this rank:** API-shape divergence with little user-visible effect.

### CHANNELZ-1. Channel trace memory bound is not configurable everywhere, and Java disables trace by default (language divergence)

The spec requires a way to control the trace memory bound through the channel and server APIs. Only C++ does this. Java's control is per channel only and defaults to 0, which turns channel trace off. Go has no public control.

- **Where:** [8.6.7.2 Memory Bound](08-observability/06-channelz.md#72-memory-bound) in `08-observability/06-channelz.md`
- **Current spec:** "Implementations MUST provide a way to control the bound." API Requirements: "The channel and server APIs MUST provide a way to configure the channel trace memory bound." Section 7.3 lists events that MUST be logged.
- **Findings:**
  - C++: channel arg `GRPC_ARG_MAX_CHANNEL_TRACE_EVENT_MEMORY_PER_NODE` on channels, subchannels, and servers, default 4 KiB ([channelz.h](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/channelz/channelz.h#L71-L77), [channel_create.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/surface/channel_create.cc#L76-L80), [server.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/server/server.cc#L1066-L1069)).
  - Java: `ManagedChannelBuilder.maxTraceEvents(int)` only. The builder field defaults to 0, and `ChannelTracer` keeps no events when `maxEvents` is not positive, so channel trace (including the required events) is off unless the application opts in ([ManagedChannelImplBuilder.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelImplBuilder.java#L586-L588), [ChannelTracer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ChannelTracer.java#L63-L72)). Servers have no trace (`ServerStats` has no trace field) ([InternalChannelz.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/InternalChannelz.java#L292-L297)).
  - Go: fixed at 30 events per entity. The setter `SetMaxTraceEntry` is in `internal/channelz`, so applications cannot call it ([trace.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/channelz/trace.go#L31-L50)). Servers have no trace.
- **Prior documentation:**
  - gRFC A3, Memory Limitation: "Implementations MUST provide some control for limiting the amount of memory used for channel trace events, such as a max number of trace events per node or the max amount of memory used." The control is required, but A3 does not say it must be per channel or per server, or what the default is.
- **Decision:** (a) keep both MUSTs (C++ conforms; Java needs a server control only if it adds server trace, and a non-zero default; Go needs a public control), (b) relax the API requirement to "MUST provide some way (for example a global setting) to control the bound" and add "trace MUST be enabled by default", or (c) relax both and allow trace to be off by default.
- **Recommendation:** (b). A3 requires only "some control", and a global setting is enough. Trace that is off by default defeats the 7.3 required events. Bugs: Java (medium): channel trace disabled by default (`maxTraceEvents` = 0). Go (low): no public way to change the trace bound.
- **Why this rank:** With Java's default, channelz shows no trace events for Java channels, which removes most of channelz's debugging value.

### XDS_BOOTSTRAP-5. When certificate_providers entries are validated (language divergence)

The three languages validate bootstrap `certificate_providers` entries at different times and for different things.

- **Where:** [9.2.4.4 Certificate Provider Instances](09-xds/02-bootstrap.md#44-certificate-provider-instances) in `09-xds/02-bootstrap.md`
- **Current spec:** `plugin_name` "MUST be a plugin that gRPC supports, or the bootstrap is invalid". `config` is not required, defaults to `{}`, and "MUST be valid for the plugin, or the bootstrap is invalid".
- **Findings:**
  - C++: conforms. An unknown plugin name or an invalid config makes the bootstrap invalid, and a missing config is treated as `{}` ([certificate_provider_store.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/certificate_provider_store.cc#L44-L75))
  - Java: requires `config` to be present (`checkForNull`), but checks neither the plugin name nor the config at bootstrap time ([BootstrapperImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/BootstrapperImpl.java#L181-L196)). An unknown plugin fails only when a resource uses the instance ([CertificateProviderStore.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/internal/security/certprovider/CertificateProviderStore.java#L129-L131))
  - Go: skips entries with an unknown plugin name and rejects the bootstrap for an invalid config ([bootstrap.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/bootstrap/bootstrap.go#L608-L624))
- **Prior documentation:**
  - gRFC A29: the value "is a JSON object having exactly 2 fields: `plugin_name` … and `config`". It says nothing about when validation happens.
  - doc/grpc_xds_bootstrap_format.md: "The \"config\" field is optional; it may be missing if the credential type does not require config parameters." So Java requiring `config` is wrong.
- **Decision:** (a) keep the spec: validate at bootstrap time and reject unknown plugins (C++), or (b) ignore unknown plugins at bootstrap time (Go), so that a resource naming that instance is then NACKed, or (c) implementation-defined.
- **Recommendation:** (a). It matches the spec's general rule that the bootstrap fails with every validation error found, and it surfaces misconfiguration at start-up instead of as a NACK later. Bugs: Java (low): certificate provider plugin name and config are not validated at bootstrap time, and a missing `config` is rejected. Go (low): an unknown certificate provider `plugin_name` is ignored instead of rejected.
- **Why this rank:** Only affects misconfigured bootstraps. The failure shows up later or in a different form.

### XDS_COMMON-1. type_url prefix is compared in Java and Go (language divergence)

The spec says the prefix before the last `/` of a `type_url` is not checked. C++ (mostly) and Envoy follow that. Java and Go compare the full `type.googleapis.com/...` string at most extension points.

- **Where:** [9.4.1.2 Extensions: `google.protobuf.Any` and `TypedStruct`](09-xds/04-resources/01-common-types.md#2-extensions-googleprotobufany-and-typedstruct) in `09-xds/04-resources/01-common-types.md`
- **Current spec:** "The *type name* is the part of the `type_url` after the last `/`. The prefix before the last `/` (normally `type.googleapis.com`) is not checked."
- **Findings:**
  - C++: `StripTypePrefix` takes the text after the last `/` for every `ExtractXdsExtension` user ([xds_common_types_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_common_types_parser.cc#L403-L416)). The aggregate `cluster_type` check only strips the literal "type.googleapis.com/" ([xds_cluster_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L467-L471)).
  - Java: registries and checks use full URLs, for example the Router filter's "type.googleapis.com/envoy.extensions.filters.http.router.v3.Router" ([RouterFilter.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RouterFilter.java#L30)), looked up by the raw `typeUrl` ([XdsRouteConfigureResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L236-L252)).
  - Go: full-URL comparisons in `IsHTTPConnManagerResource` ([type.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsclient/xdsresource/type.go#L59-L61)), `httpfilter.Get` ([httpfilter.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/httpfilter/httpfilter.go#L142-L144)), the metadata registry ([metadata.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsclient/xdsresource/metadata.go#L33-L36)), and the UpstreamTlsContext check ([unmarshal_cds.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L335-L338)).
  - Envoy: resolves extensions by the descriptor name after the last `/`. Not re-verified in this checkout.
- **Prior documentation:**
  - Not covered by any prior documentation (searched A27, A39, A52, A83). The `google.protobuf.Any` docs say only the last path segment names the type.
- **Decision:** (a) Keep the spec (ignore the prefix). (b) Require the `type.googleapis.com/` prefix.
- **Recommendation:** (a). This matches protobuf `Any` semantics and Envoy. Real control planes almost always send `type.googleapis.com/`, so impact is low. Bugs: Java (low), Go (low): extension type URLs are compared including the prefix. C++ (low): the aggregate cluster type check only strips "type.googleapis.com/".
- **Why this rank:** Interop edge case, rarely hit in practice.

### XDS_RESOLVER-3. Reset backoff on the xds resolver (language divergence)

Only C++ resets the XdsClient's and the LOGICAL_DNS resolvers' backoff when the channel resets backoff. Java and Go have no resolver reset-backoff hook.

- **Where:** [9.5.1.5 Resolver operations](09-xds/05-client.md#15-resolver-operations) in `09-xds/05-client.md`
- **Current spec:** Reset backoff MUST reset the XdsClient's backoff and the backoff of every LOGICAL_DNS DNS resolver. API Requirements: the resolver API MUST let the channel ask the resolver to reset backoff.
- **Findings:**
  - C++: conforms ([xds_resolver.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_resolver.cc#L133-L136)).
  - Java: `NameResolver` has no reset-backoff method. `resetConnectBackoff` calls `refreshNameResolution()` (which in xds only re-resolves LOGICAL_DNS) and resets subchannels ([ManagedChannelImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1280-L1297)). The ADS stream backoff is not reset.
  - Go: the resolver interface has only `ResolveNow`, and `ResetConnectBackoff` only touches subchannels ([clientconn.go](https://github.com/grpc/grpc-go/blob/v1.82.0/clientconn.go#L1181)).
- **Prior documentation:**
  - Not covered by any prior documentation (searched: A27, A37, A74, A88).
- **Decision:** (a) keep the MUST, (b) make it a SHOULD, (c) implementation-defined.
- **Recommendation:** (b). This is a convenience: the XdsClient and DNS recover on their own, and adding a resolver API in Java and Go has a cost. Bugs: none under (b) or (c). Under (a), Java (low) and Go (low): channel reset-backoff doesn't reach the XdsClient or the LOGICAL_DNS resolvers.
- **Why this rank:** Only affects how quickly a channel recovers after an explicit reset-backoff call.

### XDS_DEPMGR-5. When the XdsDependencyManager delivers a config (language divergence)

Languages differ on which pending resources hold back a new `XdsConfig`. Go doesn't wait for dynamically subscribed clusters, and Java can wait on clusters that are no longer needed.

- **Where:** [9.5.2.7 When a config is delivered](09-xds/05-client.md#27-when-a-config-is-delivered) in `09-xds/05-client.md`
- **Current spec:** A config is delivered if and only if a valid Listener and virtual host exist, and every cluster reachable from the root set (route clusters plus dynamic subscriptions) has its CDS result and endpoint data or error.
- **Findings:**
  - C++: conforms. It walks every root, including subscriptions, and returns no config if anything is missing ([xds_dependency_manager.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_dependency_manager.cc#L892-L961)).
  - Go: `haveAllResources` becomes false only for clusters with `staticRefCount > 0`. A pending dynamic cluster (and everything under it) is left out of the config, and the config is delivered anyway ([xds_dependency_manager.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L234-L253)).
  - Java: waits until no watcher it holds has a missing result ([XdsDependencyManager.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L196-L206)). Unneeded watchers are closed only after a config is built ([L219-L227](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L219-L227)). So if a route update removes a cluster whose CDS response never arrived, all further updates are blocked until that resource arrives or its does-not-exist timer fires. I found this by reading the code; I didn't test it.
- **Prior documentation:**
  - gRFC A74, "Changes in cds LB policy": "when a cds LB policy obtains a dynamic subscription to a cluster, there may be subsequent updates from the xds resolver that do not yet include the newly subscribed-to cluster. Therefore, the cds policy will need to ignore updates in which the XdsConfig does not contain the cluster." This expects updates that don't include a just-subscribed cluster, so Go's approach is arguably allowed.
  - gRFC A74: "Only once it has all necessary resources will it return a new configuration to the xds resolver."
- **Decision:** (a) keep the strict rule (C++), (b) let a config be delivered without dynamically subscribed clusters that are still pending, which then have no entry (Go), (c) leave it implementation-defined. In all cases, state that resources no longer needed MUST NOT hold back delivery.
- **Recommendation:** (b). It keeps a slow or missing dynamic (RLS) target from freezing route and cluster updates for the whole channel, and cds already ignores updates that lack its dynamic cluster. Bugs: under (b), C++ (low): pending dynamic subscriptions block all config delivery. Under any option, Java (medium): watchers for clusters no longer needed can block config delivery.
- **Why this rank:** Affects how fast updates arrive in edge cases. Java's case can delay every update by up to the does-not-exist timeout.

### XDS_LB-2. xds_cluster_impl JSON config field and registered name (language divergence)

The implementations disagree on the JSON field name for the cluster in the `xds_cluster_impl` config, and Java registers the policy under a different name.

- **Where:** [`xds_cluster_impl` LB Policy: 2. Configuration](09-xds/lb-policies/xds_cluster_impl.md#2-configuration) in `09-xds/lb-policies/xds_cluster_impl.md`
- **Current spec:** Registered as `xds_cluster_impl_experimental`, with JSON field `clusterName`.
- **Findings:**
  - Java: the config cannot be parsed from JSON (it is built in-process), and the policy is registered as `cluster_impl_experimental` ([XdsLbPolicies.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsLbPolicies.java#L23), [ClusterImplLoadBalancerProvider.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancerProvider.java#L67-L75)).
  - Go: JSON field `cluster` (matching `service_config.proto`), registered as `xds_cluster_impl_experimental` ([config.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/clusterimpl/config.go#L38), [clusterimpl.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/clusterimpl/clusterimpl.go#L61)).
    - Also (spec audit): Go's generated `xds_cluster_impl` config differs structurally from the spec's tree: it sits under `priority` and `outlier_detection` and has no `xds_override_host` above it (see XDS_LB-5). No change to the JSON-name question.
  - C++: JSON field `clusterName` (matching A74), registered as `xds_cluster_impl_experimental` ([xds_cluster_impl.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_cluster_impl.cc#L146), [xds_cluster_impl.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_cluster_impl.cc#L857-L864)).
  - Envoy: not applicable — `xds_cluster_impl` and its JSON LB config are gRPC-internal objects with no Envoy counterpart.
- **Prior documentation:**
  - gRFC A37, "`xds_cluster_impl_experimental` LB Policy": the config is "message XdsClusterImplLoadBalancingPolicyConfig { // Cluster name.  Required. string cluster = 1;". The proto field is `cluster`, so its JSON name is `cluster` (Go). A37 also names the policy "`xds_cluster_impl_experimental`".
  - gRFC A74, "Changes in xds_cluster_impl and xds_override_host LB policies": "In the xds_cluster_impl policy config, we will retain only the clusterName and childPolicy fields." This uses `clusterName` (C++).
  - grpc-proto `service_config.proto` (HEAD): "// Cluster name.  Required. string cluster = 1;" and "XdsClusterImplLoadBalancingPolicyConfig xds_cluster_impl_experimental = 12 [json_name = \"xds_cluster_impl_experimental\"];". The field is `cluster`, and the registered name is `xds_cluster_impl_experimental` (the local diff doesn't touch these lines).
  - gRFC A48 mentions "the `cluster_impl_experimental` policy" in passing (Java's name). The gRFCs are inconsistent on both the field name and the policy name, which supports option (c).
- **Decision:** (a) `clusterName` (A74, C++), (b) `cluster` (proto, Go), or (c) leave the JSON form unspecified, since this is an internal policy.
- **Recommendation:** (c), or (a) if the spec must give a JSON form. This policy is built internally by the xDS resolver, so its JSON is never exchanged between implementations, and requiring one name would force churn with no interop benefit. If (a) is chosen, Go and `service_config.proto` need updates.
- **Why this rank:** Internal-only policy JSON that is never exchanged between implementations.

### XDS_LB-3. xds_cluster_manager retention of removed children (language divergence)

How long should `xds_cluster_manager` keep a child after its cluster is removed from the config? No gRFC says.

- **Where:** [`xds_cluster_manager` LB Policy: 3.2 Features › Child Deactivation and Retention](09-xds/lb-policies/xds_cluster_manager.md#child-deactivation-and-retention) in `09-xds/lb-policies/xds_cluster_manager.md`
- **Current spec:** Removed children are deactivated, SHOULD be kept for 15 minutes, and are reactivated if they return within that time.
- **Findings:** Java (`ClusterManagerLoadBalancer`, [ClusterManagerLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterManagerLoadBalancer.java#L56), [ClusterManagerLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterManagerLoadBalancer.java#L231-L235)) and C++ (`kChildRetentionInterval`, [xds_cluster_manager.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_cluster_manager.cc#L68), [xds_cluster_manager.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_cluster_manager.cc#L495-L499)) keep removed children for 15 minutes. Go removes them immediately (`SubBalancerCloseTimeout` 0, [clustermanager.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/clustermanager/clustermanager.go#L54)). Java's `ClusterManagerLoadBalancer` also never forwards ExitIdle to any child, active or deactivated (see XDS_LB-9). With two-phase cluster removal (9.4.5.4), no RPC can pick a removed child, so keeping it only helps if the cluster comes back. Java also registers the policy as `cluster_manager_experimental` ([XdsLbPolicies.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsLbPolicies.java#L20)).
  - Envoy: Only an analogy. Envoy ties cluster lifetime to CDS, not to whether routes reference the cluster, so there is no grace period like `xds_cluster_manager`'s. When CDS removes an API-added cluster, `ClusterManagerImpl::removeCluster` erases it right away: from the active and warming maps, and from every worker's thread-local cluster map, after calling `onClusterRemoval` callbacks. That is closest to (c) "destroy immediately". It is no reason to require 15-minute retention, and it is consistent with (b). (https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/upstream/cluster_manager_impl.cc#L887-L938)
- **Prior documentation:**
  - gRFC A28, "Weighted target LB policy" (HEAD; the local edit is unrelated): "The WRR algorithm will be random based. When a child policy is removed, it will be cached for 15 minutes." This is the origin of the 15-minute retention. It applied to weighted_target, whose children at the time were the per-cluster `cds` policies. A31 later moved that role into `xds_cluster_manager`. So "no gRFC says" is true only for `xds_cluster_manager` itself.
  - gRFC A31, "Config Selector": "To avoid races, the removal of a cluster will require two steps" and "when the count of RPCs referencing a deleted cluster is zero, the cluster can safely be removed from the Load Balancing Config in the Service Config." This supports the finding that two-phase removal makes retention only an optimization.
  - gRFC A31: "the top-level Load Balancing Policy will be named \"xds_cluster_manager_experimental\"". The proto `service_config.proto` also uses `xds_cluster_manager_experimental`, so Java's `cluster_manager_experimental` disagrees with both.
- **Decision:** (a) SHOULD keep for 15 minutes (Java/C++), (b) MAY keep for an implementation-defined time, or (c) destroy immediately (Go).
- **Recommendation:** (b). Retention is now only an optimization with no effect on correctness, so a SHOULD with a fixed duration isn't needed. With (b), none of the three implementations needs a change. Separately, Java's registered name should be noted or fixed.
- **Why this rank:** Child retention is only an optimization after two-phase removal; the recommendation relaxes the spec so no implementation changes.

### XDS_LB-9. ExitIdle forwarding in xds parent policies (language divergence)

No language does what the spec says for `xds_cluster_manager`'s ExitIdle (forward only to active children). Java does not forward ExitIdle at all in `xds_cluster_manager`, `cds`, or `xds_wrr_locality`.

- **Where:** [`xds_cluster_manager` LB Policy: 3.4 ExitIdle](09-xds/lb-policies/xds_cluster_manager.md#34-exitidle) in `09-xds/lb-policies/xds_cluster_manager.md`
- **Current spec:** `xds_cluster_manager`: "Forwarded to every active child." `cds` and `xds_wrr_locality` 3.4: "Forwarded to the child."
- **Findings:**
  - C++: `for (auto& [_, child] : children_) child->ExitIdleLocked();`, i.e. every child, including deactivated ones. `cds` and `xds_wrr_locality` forward. ([xds_cluster_manager.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_cluster_manager.cc#L262-L264))
  - Java: `ClusterManagerLoadBalancer`, `CdsLoadBalancer2`, and `WrrLocalityLoadBalancer` do not override `requestConnection()`, so they inherit the no-op default. ([LoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/LoadBalancer.java#L444))
  - Go: forwards to every child in the balancer group (removed children are closed immediately, so all are active). `cds` and `xds_wrr_locality` forward. ([balancergroup.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/balancergroup/balancergroup.go#L574-L583))
  - Envoy: not applicable.
- **Prior documentation:**
  - Not covered by any prior documentation (searched: A31, A61 ExitIdle text).
- **Decision:** (a) forward to all children (C++, Go); (b) keep "active children only"; (c) leave it unspecified for deactivated children.
- **Recommendation:** (a) for `xds_cluster_manager` (it is harmless and matches two implementations), and keep "forwarded to the child" for `cds` and `xds_wrr_locality`. Bugs: Java (low): cds, xds_cluster_manager, and xds_wrr_locality do not forward ExitIdle (requestConnection).
- **Why this rank:** Leaf policies usually start connecting on their own, so the visible effect is small.

### XDS_LB-8. xds_cluster_manager: status for an unknown cluster (language divergence)

The status for a pick whose cluster attribute names no child differs between languages.

- **Where:** [`xds_cluster_manager` LB Policy: 4. Picker Implementation](09-xds/lb-policies/xds_cluster_manager.md#4-picker-implementation) in `09-xds/lb-policies/xds_cluster_manager.md`
- **Current spec:** "If the attribute is missing or names no active child, the pick MUST fail with status INTERNAL."
- **Findings:**
  - C++: `PickResult::Fail(absl::InternalError("xds cluster manager picker: unknown cluster ..."))`. ([xds_cluster_manager.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_cluster_manager.cc#L238-L239))
  - Java: `PickResult.withError(Status.UNAVAILABLE ... "CDS encountered error: unable to find available subchannel for cluster ...")`. A wait_for_ready RPC queues. ([ClusterManagerLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterManagerLoadBalancer.java#L147-L151))
  - Go: `status.Errorf(codes.Unavailable, "unknown cluster selected for RPC: %q", ...)`. ([picker.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/balancer/clustermanager/picker.go#L50))
  - Envoy: not applicable.
- **Prior documentation:**
  - Not covered by any prior documentation (searched: A31, A74).
- **Decision:** (a) INTERNAL (C++); (b) UNAVAILABLE (Java, Go); (c) leave the code unspecified, since it "should never happen".
- **Recommendation:** (a). The case indicates an internal bug (the two-phase removal guarantees it doesn't happen), and INTERNAL avoids retries and wait_for_ready hangs. Bugs: Java (low), Go (low): unknown-cluster pick fails with UNAVAILABLE instead of INTERNAL.
- **Why this rank:** Not expected to happen in practice.

### XDS_LB-11. xds_wrr_locality: handling of missing locality or weight (language divergence)

The three languages handle endpoints with a missing locality, a missing or 0 locality weight, and conflicting weights differently. Only C++ matches the spec.

- **Where:** [`xds_wrr_locality` LB Policy: 3.2 Features › Child Config Generation](09-xds/lb-policies/xds_wrr_locality.md#child-config-generation) in `09-xds/lb-policies/xds_wrr_locality.md`
- **Current spec:** skip endpoints with no locality or weight 0. On conflicting weights, log and keep the first. If the generated config fails to parse, report TRANSIENT_FAILURE with INTERNAL.
- **Findings:**
  - C++: matches. It skips `locality_name == nullptr || weight == 0`, keeps the first weight with an error log, and reports TRANSIENT_FAILURE INTERNAL on a parse failure. ([xds_wrr_locality.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_wrr_locality.cc#L164-L221))
  - Java: a missing locality or weight fails the whole update: TRANSIENT_FAILURE with UNAVAILABLE "wrr_locality error: ...". Weight 0 is not skipped. Keeps the first weight with a warning. ([WrrLocalityLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/WrrLocalityLoadBalancer.java#L75-L101))
  - Go: a missing locality becomes the empty locality name. A missing weight, or a generated config that fails to parse, returns an error without reporting a state. Weight 0 is not skipped. On a conflict the last weight wins (map overwrite, no log). ([balancer.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/balancer/wrrlocality/balancer.go#L161-L183))
  - Envoy: not applicable.
- **Prior documentation:**
  - gRFC A52 says the locality weight attribute is set by the cluster resolver for every address (quoted in Go's configbuilder.go). It does not say how missing values are handled. Otherwise not covered (searched: A52).
- **Decision:** (a) keep the spec (skip); (b) treat missing values as an error that fails the update; (c) leave it unspecified, since `cds` always sets these attributes.
- **Recommendation:** (c), or (a) if the spec should stay precise. `cds` always sets a locality and a weight ≥ 1, so these paths never run in the generated tree. Bugs: none recommended. If (a) is chosen: Java (low), Go (low).
- **Why this rank:** Unreachable when the tree is generated by `cds`.

### XDS_FILTERS-1. HttpFilter / FilterConfig `disabled` fields (language divergence)

`HttpFilter.disabled` and `FilterConfig.disabled` let a filter be turned off by default and re-enabled per route, but no merged gRFC specifies them.

- **Where:** [9.7.2.1 Extracting the Filter Type](09-xds/07-http-filters.md#21-extracting-the-filter-type) in `09-xds/07-http-filters.md`
- **Current spec:** Does not mention the fields, so they are ignored.
- **Findings:**
  - Java: not implemented (fields ignored; there is no `getDisabled()` call anywhere in grpc-java's `xds/src/main`).
  - Go: honored only behind the ext_proc/ext_authz env-var guards. The most specific override wins, and any override that is not disabled re-enables the filter (`unmarshal_lds.go`) ([unmarshal_lds.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L190-L198), [unmarshal_lds.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L248-L253), [xds_resolver.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/resolver/xds_resolver.go#L636-L643)).
  - C++: always honored, with precedence ClusterWeight > Route > VirtualHost > HCM (`xds_routing.cc` `IsFilterDisabled`) ([xds_routing.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_routing.cc#L280-L314)).
  - Envoy: Envoy always honors both fields, which matches option (b) (C++ semantics). `HttpFilter.disabled` sets a default-off flag, and it is an error to set it on the last (terminal) filter. When the filter chain is built, the route-level answer is used if there is one, and the HCM default otherwise (`filterDisabled(name).value_or(disabled)`). For overrides, `FilterConfig{disabled: true}` disables the filter, and any other override (a plain `typed_per_filter_config` or a `FilterConfig` with an empty `config`) explicitly enables it. Precedence is ClusterWeight > Route > VirtualHost > RouteConfiguration > HCM default; the RouteConfiguration level is one more than C++ lists. (https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/http/filter_chain_helper.h#L116-L126, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/http/filter_chain_helper.cc#L22-L27, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/router/per_filter_config.cc#L91-L122, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/router/weighted_cluster_specifier.cc#L235-L241, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/router/config_impl.cc#L1415-L1421, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/router/config_impl.cc#L1794-L1800, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/router/config_impl.h#L1439-L1441)
- **Prior documentation:**
  - gRFC A39 (xDS HTTP filters) lists the `HttpFilter` fields gRPC uses (`name`, `typed_config`, `is_optional`), and for `FilterConfig` says "gRPC will look inside that type's [`config`] field ... In addition, gRPC will look at the [`is_optional`] field". It never mentions `disabled`, which supports option (a).
  - Envoy `http_connection_manager.proto`, `HttpFilter.disabled`: "If true, the filter is disabled by default and must be explicitly enabled by setting per filter configuration in the route configuration." Envoy `route_components.proto`, `FilterConfig.disabled`: "If true, the filter is disabled in the route or virtual host and the ``config`` field is ignored."
  - gRFC A55 (stateful session affinity) mentions a filter-specific mechanism only: "This configuration can either be overridden or disabled by a [StatefulSessionPerRoute] config". That is not the generic `disabled` field.
  - Otherwise not covered by any merged gRFC, doc/*.md, protos, or pending PRs (searched all gRFCs for "disabled"/"FilterConfig").
- **Decision:** (a) keep the fields out of the spec until a gRFC (e.g., A92/A93) defines them, (b) specify the C++ semantics now, or (c) mark them implementation-defined.
- **Recommendation:** (a), plus a note that some implementations honor them. Their semantics are still being designed in gRFCs, and specifying them now would make Java non-conformant and could conflict with the final gRFC. Revisit when the gRFC is merged.
- **Why this rank:** C++/Go honor filter disabled fields while Java ignores them, so the same config enables different filters, which can matter for security filters; semantics await a gRFC.

### XDS_FAULT-2. FaultAbort status-code validation (language divergence)

The implementations validate `FaultAbort` status codes differently, and the spec's NACK rule for `grpc_status` matches only C++.

- **Where:** [9.7.8.1 Configuration](09-xds/07-http-filters.md#81-configuration) in `09-xds/07-http-filters.md`
- **Current spec:** `abort.grpc_status` MUST be 0–16, else NACK. Every `abort.http_status` value is mapped to a gRPC code (unknown values map to `UNKNOWN`). A `FaultAbort` with no error type set is not covered.
- **Findings:**
  - C++: `grpc_status` > 16 NACKs. `http_status` is always mapped, and 0 counts as unset. With no error type, no abort happens ([xds_http_fault_filter.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_fault_filter.cc#L113-L132)).
  - Java: `grpc_status` > 16 becomes `UNKNOWN` (`Status.fromCodeValue`). `http_status` is always mapped. With no error type, it NACKs ([FaultFilter.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/FaultFilter.java#L163-L181)).
  - Go: `grpc_status` > 16 becomes `UNKNOWN` (`sanitizeGRPCCode`). An `http_status` outside [200, 600) is accepted but never aborts. With no error type, no abort happens ([fault.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/httpfilter/fault/fault.go#L216-L249), [grpcFromHTTP](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/httpfilter/fault/fault.go#L280-L299)).
  - Envoy: `error_type` is a required oneof, `http_status` must be in [200, 600), and `grpc_status` has no range check ([fault.proto](https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/api/envoy/extensions/filters/http/fault/v3/fault.proto#L41-L52)).
- **Prior documentation:**
  - gRFC A33, "Status Code Mapping": "gRPC should accept fault injection settings with either HTTP status code or gRPC status code." It gives no validation rules.
  - Not otherwise covered (searched A33, A39, doc/http-grpc-status-mapping.md).
- **Decision:** (a) keep the spec (NACK `grpc_status` > 16) and add Envoy's rules (NACK `http_status` outside [200, 600) and NACK an unset error type), (b) map out-of-range `grpc_status` to `UNKNOWN` (Java/Go) and use Envoy's rules for the rest, or (c) declare it implementation-defined.
- **Recommendation:** (b). It matches two of three implementations for `grpc_status`, and Envoy doesn't reject such values either. Envoy's PGV rules for `http_status` and `error_type` are what control planes are written against. Bugs: C++ (low): out-of-range grpc_status NACKs the Listener; Go (low): out-of-range http_status accepted and ignored; C++/Go (low): FaultAbort with no error_type accepted.
- **Why this rank:** Only affects malformed fault configs. The result is a NACK in one implementation and a silently different fault in another.

### XDS_RBAC-2. RBAC rule types the spec does not list (language divergence)

The spec does not say how gRPC handles `Permission`/`Principal` rule types outside its mapping tables, and the implementations differ on `destination_port_range`.

- **Where:** [9.7.9.2 Mapping RBAC Fields to gRPC](09-xds/07-http-filters.md#92-mapping-rbac-fields-to-grpc) in `09-xds/07-http-filters.md`
- **Current spec:** Lists only the fields that "need interpretation". It says nothing about `Permission.destination_port_range`, `matcher`, `uri_template`, `sourced_metadata`; `Principal.filter_state`, `sourced_metadata`, `custom`; or a rule with no type set.
- **Findings:**
  - C++: any rule type not handled NACKs with "invalid rule", including `destination_port_range` ([xds_http_rbac_filter.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L283-L285), [xds_http_rbac_filter.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L371-L373)).
  - Java: supports `destination_port_range`. Other types and unset rules NACK through the default case ([RbacFilter.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RbacFilter.java#L242-L253), [RbacFilter.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RbacFilter.java#L296-L301)).
  - Go: both type switches now have a default case that NACKs ("unsupported permission rule type" / "unsupported principal identifier type"), and an unset rule also NACKs. `destination_port_range` is not supported, so it NACKs, as in C++ ([matchers.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/rbac/matchers.go#L78-L143), [matchers.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/rbac/matchers.go#L146-L225)). Fixed by be1b06d6 (security-advisory merge, "xds/rbac: Fix multiple deviations in implementation from A41 spec", first in v1.84.0). v1.82.0 had no default case and silently dropped these rules, with the same semantic problems as XDS_RBAC-1 (now resolved).
  - Envoy: `rbac.proto` defines `destination_port_range` (11), `matcher` (12), `uri_template` (13), and `sourced_metadata` (14) on Permission, and `filter_state` (12), `sourced_metadata` (13), and `custom` (14) on Principal ([rbac.proto](https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/api/envoy/config/rbac/v3/rbac.proto#L235-L460)).
- **Prior documentation:**
  - gRFC A41: "All current (Envoy-implemented) fields will be considered in gRPC." A41 links `rbac.proto` at Envoy commit 10c17a7, and its tables do not list `destination_port_range`. A41 does not say how fields added later are handled.
- **Decision:** (a) support `destination_port_range` (local port in range) and NACK any other rule type gRPC does not support, including an unset rule; (b) NACK everything not listed, including `destination_port_range` (C++); or (c) leave it implementation-defined.
- **Recommendation:** (a). NACKing unknown authorization rules is the safe default, and it follows the spec's general rule that an ignored field that weakens security causes a NACK. All three now do that. `destination_port_range` is trivial and Java already supports it. Note: C++ and Go now both implement (b), so (b) is the majority behavior and would need no Go or C++ change. Bugs: C++ (low), Go (low): destination_port_range NACKed. The former Go (high) bug, where unknown RBAC rule types were silently dropped, was fixed in v1.84.0 (be1b06d6).
- **Why this rank:** Only `destination_port_range` still differs: C++ and Go NACK it, and Java supports it.

### XDS_CDS-3. transport_socket.name and transport_socket_matches cause rejection in Java and Go (language divergence)

The spec says `transport_socket.name` and `transport_socket_matches` are ignored, and C++ ignores them. Java and Go reject the Cluster if `transport_socket_matches` is non-empty or if the name is not `envoy.transport_sockets.tls`.

- **Where:** [9.9.2.1 Locating the TLS Context](09-xds/09-security.md#21-locating-the-tls-context) in `09-xds/09-security.md`
- **Current spec:** "`transport_socket.name` and `transport_socket_matches` are ignored." The type is chosen from `typed_config`.
- **Findings:**
  - C++: only looks at `typed_config` ([xds_cluster_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L492-L513)).
  - Java: rejects a non-empty `transport_socket_matches`, and a name other than "envoy.transport_sockets.tls" unless the typed_config is Http11ProxyUpstreamTransport. Inside the HTTP CONNECT wrapper, a nested socket whose name isn't the TLS name is silently ignored ([XdsClusterResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L250-L295)).
  - Go: rejects a non-empty `transport_socket_matches` and a name other than "envoy.transport_sockets.tls" ([unmarshal_cds.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L320-L334)).
  - Envoy: `name` is not used to select the extension when `typed_config` is set.
- **Prior documentation:**
  - A29: "Note that we don't (currently) support [`transport_socket_matches`]" for CDS, without saying whether to NACK. The name check ("if a `transport_socket` name is not `envoy.transport_sockets.tls` … gRPC will NACK") is stated only for server Listeners (LDS).
- **Also found at:** [9.9 xDS Security: 2.1 Locating the TLS Context](09-xds/09-security.md#21-locating-the-tls-context) in `09-xds/09-security.md` (same issue, reported by a second auditor; its REVIEW comment carries this ID too).
  - Second auditor's findings:
    - C++: ignores `transport_socket_matches` and `transport_socket.name`, and selects by type only ([xds_cluster_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_cluster_parser.cc#L491-L512), [xds_listener_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_listener_parser.cc#L411-L425)).
    - Java: NACKs non-empty `transport_socket_matches`. NACKs a CDS `transport_socket` with a name other than `envoy.transport_sockets.tls` unless its type is `Http11ProxyUpstreamTransport` ([XdsClusterResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L250-L262)). Does the same name check on LDS ([XdsListenerResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L261-L264)).
    - Go: NACKs non-empty `transport_socket_matches`, and NACKs a name other than `envoy.transport_sockets.tls` on CDS and LDS ([unmarshal_cds.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L321-L338), [unmarshal_lds.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L336-L341)).
- **Decision:** (a) Keep the spec (ignore both; C++, Envoy). (b) Require NACK for a non-empty `transport_socket_matches` (Java, Go) but ignore `name`. (c) NACK on both (Java, Go).
- **Recommendation:** (b). Ignoring `transport_socket_matches` could silently drop TLS that the control plane meant to apply to some endpoints, so a NACK is safer. The name is an Envoy-deprecated selector and should be ignored. Bugs under (b): C++ (low): non-empty `transport_socket_matches` is not rejected. Java (low), Go (low): `transport_socket.name` other than "envoy.transport_sockets.tls" rejects the Cluster.
- **Why this rank:** A control plane that uses a different name, or sends matches, gets different accept/reject results per language. Security-relevant only for matches.

### XDS_LRS-4. LRS stream wait_for_ready (language divergence)

The spec says the LRS stream is started with wait_for_ready. Only C++ does this.

- **Where:** [9.10.3.1 Stream lifecycle](09-xds/10-load-reporting.md#31-stream-lifecycle) in `09-xds/10-load-reporting.md`
- **Current spec:** "It is created with wait_for_ready set."
- **Findings:**
  - C++: `set_wait_for_ready(true)` ([lrs_client.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/xds_client/lrs_client.cc#L577-L578))
  - Java: `CallOptions.DEFAULT`, with the comment "TODO(zivy): support waitForReady" ([GrpcXdsTransportFactory.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/GrpcXdsTransportFactory.java#L129-L139))
  - Go: `cc.NewStream` with no call options ([grpc_transport.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/clients/grpctransport/grpc_transport.go#L182-L183))
- **Prior documentation:**
  - Not covered by any prior documentation (searched: A27, A57, A71, A88 for wait_for_ready. A57 mentions wait_for_ready only for ADS).
- **Decision:** (a) keep the MUST-like statement (C++), or (b) mirror the ADS rule from XDS_CLIENT-2: SHOULD use wait_for_ready if the client monitors channel connectivity, otherwise it MAY fail fast and back off, or (c) drop the statement.
- **Recommendation:** (b). This keeps LRS consistent with the ADS decision. The difference only changes how fast the stream retries while the xDS channel is down. Bugs: none, if (b) is chosen.
- **Why this rank:** Small behavioral difference while the server is unreachable. No data loss, because stats are kept until a report is sent.

## Judgment calls (2)

### RLS-12. A change to routeLookupChannelServiceConfig alone is not applied (judgment)

The spec doesn't say what happens when only `routeLookupChannelServiceConfig` changes. No language applies the change, yet an existing Go bug treats this as a non-conformance.

- **Where:** [`rls` LB Policy: 3.2 Features › Control Channel](04-client-channel/lb-policies/rls.md#control-channel) in `04-client-channel/lb-policies/rls.md`
- **Current spec:** "When an update changes `lookupService`, a new control channel is created for new lookups." Nothing covers a change to `routeLookupChannelServiceConfig` alone.
- **Findings:**
  - C++: a new `RlsChannel` is created only when `lookup_service()` changes. The old channel keeps its service config. ([rls.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L1973-L1978))
  - Java: the config is applied only when `lookupService` changes (TODO in the code; already in the bug "RLS ignores config updates other than lookupService"). ([RlsLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/rls/src/main/java/io/grpc/rls/RlsLoadBalancer.java#L55-L80))
  - Go: a new control channel is created only when `lookupService` or `lookupServiceTimeout` changes. ([balancer.go](https://github.com/grpc/grpc-go/blob/v1.82.0/balancer/rls/balancer.go#L360-L363))
- **Prior documentation:** Not covered by any prior documentation (searched: the RLS design doc and RLS-in-xDS design doc, grpc-proto `rls_config.proto` and `service_config.proto` `RlsLoadBalancingPolicyConfig`).
- **Decision:** (a) say that a change to `lookupService` or `routeLookupChannelServiceConfig` creates a new control channel; or (b) say that only a `lookupService` change does, and a service config change takes effect with the next new control channel (current behavior everywhere).
- **Recommendation:** (a). Ignoring a config change silently is surprising, and recreating the channel is cheap and already happens for `lookupService`. Then file bugs (low) against C++ and Go, and keep the Java bullet. If (b) is chosen instead, remove the routeLookupChannelServiceConfig bullet from the Go bug "RLS config and picker non-conformances".
- **Why this rank:** The control channel's service config rarely changes on its own.

### RETRY-1. Throttle failures from "don't retry" pushback on RPCs without a retry policy (judgment)

When an RPC has no retry policy, it isn't clear whether a "don't retry" pushback counts as a retry-throttling failure.

- **Where:** [4.12.2.3 Behavior](04-client-channel/12-retries.md#23-behavior) in `04-client-channel/12-retries.md`
- **Current spec:** The pseudocode commits RPCs that have no retry policy before it checks pushback, so a "don't retry" pushback is not recorded. Token Accounting's failure rule ("…or if the response carries a pushback that says not to retry") reads as applying to any RPC. Successes are now counted for every RPC on the channel, policy or not, which makes the asymmetry stand out.
- **Findings:**
  - Go records pushback failures even when the method has no retry policy: `shouldRetry` throttles on a negative or multi-valued pushback before it checks the policy ([stream.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stream.go#L837-L860), [stream.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/stream.go#L869-L872)). This applies only to Trailers-Only responses, since other responses have committed the attempt.
  - C++ does not: `ShouldRetry` returns first thing when there is no retry policy ([retry_filter_legacy_call_data.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_filter_legacy_call_data.cc#L534-L535); same in the promise-based [retry_interceptor.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_interceptor.cc#L60-L65)). Even with a policy, C++ records a failure only for a retryable status code, so a "don't retry" pushback on a non-retryable code is never counted ([retry_filter_legacy_call_data.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/retry_filter_legacy_call_data.cc#L557-L570)).
  - Java does not either. Correction: this was listed as unverified on the theory that `RetriableStream` is used only with a policy, but with retries enabled (the default) every RPC uses `RetriableStream`, with a possibly null policy ([ManagedChannelImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L482-L509)). `makeRetryDecision` returns before any throttle accounting when `retryPolicy == null` ([RetriableStream.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L1076-L1079)). With a policy, Java does count a negative pushback even for a non-retryable code ([RetriableStream.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L1083-L1089)).
- **Prior documentation:**
  - gRFC A6, "Throttling Retry Attempts and Hedged RPCs": "Every outgoing RPC (regardless of service or method invoked) will effect `token_count` as follows: Every failed RPC will decrement the `token_count` by 1. Every successful RPC will increment the `token_count` by `tokenRatio`." It continues: "The only RPCs that are counted as failures for the throttling policy are RPCs that fail with a status code that qualifies as a retryable or non-fatal status code, or that receive a pushback response indicating not to retry." The pushback clause doesn't depend on having a policy, and "regardless of service or method" points to (a). The status-code clause, though, only makes sense when a retry/hedging policy exists.
  - grpc-proto `service_config.proto` (`retry_throttling` comment) says the same: "Every outgoing RPC (regardless of service or method invoked) will change token_count as follows: - Every failed RPC will decrement the token_count by 1."
  - Neither source says outright whether a policy-less RPC's pushback counts.
- **Decision:** (a) count "don't retry" pushback failures for every RPC on the channel (symmetric with successes, matches Go), or (b) count failures only for RPCs with a retry or hedging policy (current pseudocode).
- **Recommendation:** (a). It is symmetric with the success rule, and the pushback is a server-overload signal regardless of the method's policy. Move the pushback check above the `retry_policy == null` check in the pseudocode, and file bugs against implementations that don't record it.
- **Why this rank:** Throttling accounting for policy-less RPCs is a design choice with modest effect on retry throttling under server overload.

## Language bugs (20)

### MESSAGE_SIZE-1. Java has no channel- or server-level maximum send message size (language bug)

Java can limit outgoing message size only per call on the client, and not at all on the server.

- **Where:** [2.12 Message Size Limits](02-rpc-semantics/README.md#12-message-size-limits) in `02-rpc-semantics/README.md`
- **Current spec:** Implementations MUST support a maximum size for sent messages, set through the channel API and server API (and on the client also through `maxRequestMessageBytes`). 18.4 says the same: the channel and server APIs MUST provide a way to set the maximum send message size.
- **Findings:**
  - C++: `GRPC_ARG_MAX_SEND_MESSAGE_LENGTH` and `ServerBuilder::SetMaxSendMessageSize` ([channel_arg_names.h](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/include/grpc/impl/channel_arg_names.h#L49), [server_builder.h](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/include/grpcpp/server_builder.h#L196))
  - Java: the builders have only `maxInboundMessageSize`. On the client the limit can be set per call (`CallOptions.withMaxOutboundMessageSize`) or through the method config. The server never limits outgoing messages ([ManagedChannelBuilder.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/ManagedChannelBuilder.java#L348), [ServerBuilder.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/ServerBuilder.java#L390), [CallOptions.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/CallOptions.java#L482))
  - Go: `MaxCallSendMsgSize` as a default call option on the client, and the `MaxSendMsgSize` ServerOption ([server.go](https://github.com/grpc/grpc-go/blob/v1.82.0/server.go#L456-L462))
- **Prior documentation:**
  - Not covered by any prior documentation beyond the service config field (searched: doc/*.md, A6/A31/A54, grpc-proto). `service_config.proto` defines only `max_request_message_bytes` / `max_response_message_bytes`.
- **Decision:** (a) keep the requirement and treat Java as a bug, (b) require a send limit only on the client (per call or channel), (c) move send limits to spec-optionality-notes.md.
- **Recommendation:** (a) for the client: Java can add a channel-level option easily, and the per-call and service config paths already exist. For the server, (c) is acceptable if the owner prefers, since the default is "no limit" anyway. Record a low Java bug: no channel- or server-level maximum send message size.
- **Why this rank:** Missing configuration knob. The default (no limit) behavior is the same everywhere.

### HTTP2-3. Servers rejecting requests without `:authority` (language bug)

C++ servers fail a request that has neither `:authority` nor `Host` with grpc-status `UNKNOWN`. They also reject a request with a missing `te`.

- **Where:** [3.1.3.4 `:authority` and `Host`](03-wire-protocol/01-http2.md#34-authority-and-host) in `03-wire-protocol/01-http2.md`
- **Current spec:** `Authority` is optional in the grammar, and the client SHOULD send it. Nothing lets a server reject a request without it, and the spec does not define server behavior when `te` is missing.
- **Findings:**
  - C++: `MalformedRequest("Missing :authority header")` and `MalformedRequest("Missing :te header")`, both `UNKNOWN` ([http_server_filter.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/server/http_server_filter.cc#L63-L70), [L93-L100](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/server/http_server_filter.cc#L93-L100), [L130-L131](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/http/server/http_server_filter.cc#L130-L131)).
  - Java: Accepts a missing authority. A missing `te` is only logged ([NettyServerHandler.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyServerHandler.java#L468-L480), [L531](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyServerHandler.java#L531)).
  - Go: rejects a request with neither `:authority` nor `Host`: HTTP 400 with grpc-status `INTERNAL` ("no host or :authority header present") ([http2_server.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/http2_server.go#L509-L528)). This changed in [grpc/grpc-go#9365](https://github.com/grpc/grpc-go/pull/9365), first in v1.83.2 and v1.84.0; v1.82.0 accepted such a request ("no eventual :authority header is a valid RPC"). Did not find a `te` check.
- **Prior documentation:**
  - PROTOCOL-HTTP2.md grammar: "Call-Definition → Method Scheme Path [Authority] TE ..." (Authority optional, TE required from clients). A41 says only what to do when `Host` is present.
- **Decision:** (a) Servers MUST accept a missing `:authority` (file a C++ bug), and say nothing about `te`. (b) Allow servers to reject a request without an authority, and say so. (c) Also specify that servers MAY (or MUST NOT) reject a missing `te`.
- **Recommendation:** (b), plus (c) with "servers MAY ignore a missing `te`". Servers MAY reject a request with neither `:authority` nor `Host`, and if they do, they MUST fail it with `INTERNAL` (HTTP 400, as Go does). C++ and Go now reject such a request and only Java accepts it, so (b) is the majority behavior. Note: this recommendation used to be (a), which keeps the grammar's optional `Authority` meaningful; that argument still holds, but it would now require changing two of the three implementations, and only non-gRPC or hand-built clients omit the authority. If (a) is chosen instead, both C++ and Go need bugs. Bugs: C++ (low): request without `:authority`/`Host` rejected with `UNKNOWN` instead of `INTERNAL`.
- **Why this rank:** Only non-gRPC or hand-built clients omit the authority.

### SERVICE_CONFIG-2. Invalid service config with no previous valid config (duplicate) (language bug)

This is the same question as item SERVICE_CONFIG-3: whether the channel falls back to the default service config when the first config it gets is invalid.

- **Where:** [4.3.3 Channel Handling of Resolver Results](04-client-channel/03-name-resolution.md#3-channel-handling-of-resolver-results) in `04-client-channel/03-name-resolution.md`
- **Current spec:** No fallback. The channel reports TRANSIENT_FAILURE.
- **Findings:**
  - C++ reports TRANSIENT_FAILURE ("no valid service config") when there is no saved config, and doesn't use the default config; the default is used only when the resolver returns no config ([client_channel.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L1156-L1178), [client_channel.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L1179-L1185)).
  - Go applies a failing LB policy (TRANSIENT_FAILURE) only when it has no current config (`cc.sc == nil`), and doesn't use the default config ([clientconn.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/clientconn.go#L851-L860)). If an earlier result applied the default (e.g., a result with no service config), `cc.sc` is the default and Go keeps it.
  - Java falls back to the default config whenever one is set: the `defaultServiceConfig != null` branch comes before the error check ([ManagedChannelImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1727-L1747)).
  - gRFC A21 supports both readings, in different sections.
- **Prior documentation:** Same sources as SERVICE_CONFIG-3; A21 does contradict itself.
  - gRFC A21, Proposal step 5.2 (no local edits): "If the client has not previously selected a valid service config or no service config, for example a new client, then it treats the resolution attempt as having failed ... In other words, the channel will remain in state TRANSIENT_FAILURE until the resolver returns a valid response." Supports C++/Go and the spec: no fallback.
  - gRFC A21, channel-arguments section: "If a default service config is provided, the client should fallback on the default service config (in case of an invalid config with no valid service config received earlier)." Supports Java's fallback.
  - Pending PR grpc/grpc#38953 (client channel), "Channel Handling of Resolver Result" pseudo code: "// No previously returned valid config, so we fail. channel.SetConnectivityState(TRANSIENT_FAILURE); result_status = UNAVAILABLE(\"no valid service config\");". The default config is used only when "Resolver did not return any service config." Supports the spec (no fallback).
  - doc/service_config.md: the default config is the one "that will be used if the resolver plugin does not return a service config." It says nothing about invalid configs.
- **Decision:** Same as item SERVICE_CONFIG-3.
- **Recommendation:** Decide once, under item SERVICE_CONFIG-3, and apply the result to both spec locations.
- **Owner note:** Leave open.
- **Why this rank:** Duplicate of SERVICE_CONFIG-3: Java falls back to the default config where C++/Go and the spec report TRANSIENT_FAILURE.

### SERVICE_CONFIG-3. Invalid first service config: fall back to the default? (language bug)

gRFC A21 contradicts itself on what happens when the first config from the resolver is invalid, and Java also behaves differently when a previous valid config exists.

- **Where:** [4.4.3 Validation and Error Handling](04-client-channel/04-service-config.md#3-validation-and-error-handling) in `04-client-channel/04-service-config.md`
- **Current spec:** With a previous valid config, keep it. With none, report TRANSIENT_FAILURE and don't use the default config.
- **Findings:**
  - A21 step 5 says to treat the resolution as failed (TRANSIENT_FAILURE). Its "Service Config Channel Arguments" section says to fall back to the default config.
  - C++ keeps the saved config if there is one, otherwise reports TRANSIENT_FAILURE and ignores the default ([client_channel.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L1156-L1178)).
  - Go does the same ([clientconn.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/clientconn.go#L851-L860)), despite what its `WithDefaultServiceConfig` godoc says ("The name resolver does not provide a service config or provides an invalid service config", [dialoptions.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/dialoptions.go#L660-L667)).
  - Java falls back to the default whenever one is set, even replacing a previous valid config: the `defaultServiceConfig != null` branch is checked before `serviceConfigError` ([ManagedChannelImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1727-L1732)). Without a default, Java keeps the last config, or reports the error if no config was ever applied ([ManagedChannelImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1733-L1747)), matching C++ and Go.
- **Prior documentation:**
  - gRFC A21 (service config error handling), step 5.2: "If the client has not previously selected a valid service config or no service config, for example a new client, then it treats the resolution attempt as having failed ... In other words, the channel will remain in state TRANSIENT_FAILURE until the resolver returns a valid response." Step 5.1: "If it previously had selected a valid service config or no service config, it should continue using that previous configuration". This matches option (a) and C++/Go.
  - gRFC A21, "Service Config Channel Arguments": "If a default service config is provided, the client should fallback on the default service config (in case of an invalid config with no valid service config received earlier). On the other hand, if there is no default service config provided as a channel argument, the client should fail to start and keep waiting for a valid service config." This is the conflicting text. Note that even this section limits fallback to "no valid service config received earlier", so nothing in A21 supports Java replacing a previous valid config.
  - gRFC A21, the second step 5 (numbering is duplicated): "If the resolver does not support service config resolution OR if no gRPC config is received OR if gRPC config is received but no service config is chosen ..., the client should use the default service config". Here the default applies only when *no* config is returned.
  - Pending PR grpc/grpc#38953 (client channel), "Channel Handling of Resolver Result" pseudocode: "if (channel.service_config != null) { // We have a valid service config from a previous resolver result, so keep using it. ... } else { // No previously returned valid config, so we fail. channel.SetConnectivityState(TRANSIENT_FAILURE);" The default is used only for `result.service_config.IsEmpty()`. Elsewhere it says: "The default config is used when the resolver does not return any service config." This exactly matches option (a).
  - Not covered by doc/service_config.md or grpc-proto.
- **Decision:** (a) no fallback (C++/Go), fixing A21's channel-arguments section and Go's godoc, or (b) fall back to the default when there is no previous valid config, treating C++ and Go as bugs.
- **Recommendation:** (a). It's what most implementations do, and an invalid config is a visible error rather than being hidden by a default the service owner never chose. File a bug against Java, especially for replacing a previous valid config. Update A21 and Go's godoc. Apply the same decision to item SERVICE_CONFIG-2.
- **Owner note:** Leave open.
- **Why this rank:** Java replacing a previous valid config with the default on a bad update changes channel behavior silently; C++/Go match the spec.

### SERVICE_CONFIG-4. Empty `loadBalancingConfig` list (language bug)

An empty `loadBalancingConfig` array is either an error or the same as leaving the field out, depending on the language.

- **Where:** [4.4.5.2 `loadBalancingConfig`](04-client-channel/04-service-config.md#52-loadbalancingconfig) in `04-client-channel/04-service-config.md`
- **Current spec:** An empty list makes the service config invalid.
- **Findings:**
  - C++: invalid ("No known policies in list"). Any present `loadBalancingConfig` field is parsed, and an empty array falls through the loop to the error ([client_channel_service_config.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_service_config.cc#L93-L100), [lb_policy_registry.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/lb_policy_registry.cc#L98-L123)).
  - Go: invalid ("no supported policies found in config", from `gracefulswitch.ParseConfig`). It falls back to `loadBalancingPolicy` only when the field is absent (or JSON `null`) ([service_config.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/service_config.go#L188-L208), [config.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/balancer/gracefulswitch/config.go#L49-L83)).
  - Java: treats an empty list as unset and falls back to `loadBalancingPolicy` ([ServiceConfigUtil.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ServiceConfigUtil.java#L287-L303)); with neither, `parseLoadBalancingPolicyConfig` returns null and the channel uses its default policy (`pick_first`) ([AutoConfiguredLoadBalancerFactory.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/AutoConfiguredLoadBalancerFactory.java#L194-L197)).
  - The service_config.proto comment says that if no listed policy is supported, the config is invalid. An empty list fits that rule.
- **Prior documentation:**
  - grpc-proto `service_config.proto`, `LoadBalancingConfig` message comment: "If the list doesn't contain any supported policy, the whole service config is invalid." `ServiceConfig.load_balancing_config`: "clients will iterate through the list in order and stop at the first policy that they support. If none are supported, the service config is considered invalid." An empty list has no supported policy, so this supports (a).
  - `ServiceConfig.load_balancing_policy`: "load_balancing_policy is deprecated in favor of load_balancing_config; the former will be used only if the latter is unset." In proto3 JSON, an empty repeated field is the same as unset. This could be read as supporting Java, but the comments never mention an empty list.
  - gRFC A24 has the same proto text ("If none are supported, the service config is considered invalid."). It says nothing about empty lists.
  - Pending PR grpc/grpc#38953 (client channel): "If the service config has its loadBalancingConfig field set, use that policy". It doesn't say whether an empty list counts as set.
- **Decision:** (a) keep "invalid" and treat Java as a bug, (b) say an empty list means unset, or (c) leave it implementation-defined.
- **Recommendation:** (a). It matches C++, Go, and the proto comment, and it catches config mistakes instead of silently falling back. Java needs a fix.
- **Owner note:** Leave open.
- **Why this rank:** Java silently treats an empty loadBalancingConfig as unset where C++/Go reject it; rare misconfiguration.

### SERVICE_CONFIG-9. When the method config timeout starts (language bug)

The spec says the method config `timeout` counts from when the application started the RPC. Go and Java start it when the config is applied, after any wait for the first resolver result.

- **Where:** [4.5.3.2 Applying the Method Config](04-client-channel/05-call-dispatch.md#32-applying-the-method-config) in `04-client-channel/05-call-dispatch.md`
- **Current spec:** `rpc.deadline = min(rpc.deadline, rpc.start_time + mc.timeout)`. "The timeout counts from the time the application started the RPC, not from the time the config was applied."
- **Findings:**
  - C++: the deadline is the call start time plus the timeout, in both client channel implementations ([client_channel.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel.cc#L1485-L1491), [client_channel_filter.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/client_channel/client_channel_filter.cc#L185-L191))
  - Java: `Deadline.after(timeout)` in `ClientCallImpl.applyMethodConfig`, which runs in `start()` of the real call. That call is created only when the `PendingCall` is reprocessed after the first resolver result ([ClientCallImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ClientCallImpl.java#L300-L307), [ManagedChannelImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1051-L1058))
  - Go: `context.WithTimeout(ctx, timeout)` in `newClientStreamWithParams`, after `waitForResolvedAddrs` and `SelectConfig` ([stream.go](https://github.com/grpc/grpc-go/blob/v1.82.0/stream.go#L240-L252), [stream.go](https://github.com/grpc/grpc-go/blob/v1.82.0/stream.go#L298-L302))
- **Prior documentation:**
  - service_config.proto, `timeout`: "The actual deadline used will be the minimum of the value specified here and the value set by the application via the gRPC client API." It doesn't say when the timeout starts.
  - Otherwise not covered (searched: doc/service_config.md, gRFC A31, gRFC A6).
- **Decision:** (a) from RPC start (C++), or (b) from config application (Go, Java).
- **Recommendation:** (a). A timeout is a bound on the RPC's total latency as the application sees it, and initial name resolution can be slow. File low bugs against Go and Java.
- **Why this rank:** It only matters for the first RPCs on a channel (or after idle), which can run longer than the configured timeout.

### TRANSPORT-5. MAX_CONNECTION_AGE_GRACE measured from the first GOAWAY in Go and C++ (language bug)

The spec, following A9, measures the grace period from the second GOAWAY. Go and C++ start it when the first GOAWAY is sent. The spec's settings table also reads as "from the first GOAWAY".

- **Where:** [5.2.2.6 Connection Management](05-server/02-transports/02-http2.md#6-connection-management) in `05-server/02-transports/02-http2.md`
- **Current spec:** Procedure: "`MAX_CONNECTION_AGE_GRACE` SHOULD be measured from the second GOAWAY of the graceful shutdown." Table: "After the age-triggered graceful shutdown starts, the longest time outstanding RPCs may run…"
- **Findings:**
  - C++: sends the GOAWAY op, then immediately sleeps for the grace period ([legacy_channel_idle_filter.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/ext/filters/channel_idle/legacy_channel_idle_filter.cc#L178-L216)).
  - Java: applies the grace time in `secondGoAwayAndClose`, after the second GOAWAY ([NettyServerHandler.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyServerHandler.java#L1151-L1175)).
  - Go: `t.Drain("max_age")`, then `ageTimer.Reset(t.kp.MaxConnectionAgeGrace)` right away ([http2_server.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/transport/http2_server.go#L1229-L1231)).
- **Prior documentation:**
  - gRFC A9: "`MAX_CONNECTION_AGE_GRACE` is the maximum time the connection will be kept alive for outstanding RPCs to complete, ideally relative to the second GOAWAY of the graceful connection termination."
- **Decision:** (a) keep the SHOULD, file low bugs, and fix the table wording to match, (b) allow either starting point (MAY), since the difference is at most one PING round trip (bounded by the 5 s / 10 s / 20 s graceful-GOAWAY PING timeouts).
- **Recommendation:** (b) and fix the table. The difference is bounded and small, and "ideally" in A9 is weak. If (a) is chosen instead: Go (low) and C++ (low), grace measured from the first GOAWAY.
- **Why this rank:** Small timing difference, plus an internal wording inconsistency.

### SECURITY-1. Go checks channel-level call credentials' security level at channel creation or connection time (language bug)

For call credentials set on the channel, Go enforces the minimum security level by failing channel creation or the connection, not by failing the RPC with `UNAUTHENTICATED`.

- **Where:** [6.1.5.1 Call Credential Minimum Security Level](06-security/01-security-model.md#51-call-credential-minimum-security-level) in `06-security/01-security-model.md`
- **Current spec:** "If the connection's level is lower, the call credentials MUST NOT be invoked and their metadata MUST NOT be sent. The RPC fails with status `UNAUTHENTICATED` ..."
- **Findings:**
  - C++: channel and per-call credentials are combined and checked per RPC, returning `UnauthenticatedError("Established channel does not have a sufficient security level ...")` ([client_auth_filter.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/filter/auth/client_auth_filter.cc#L138-L157)).
  - Java: the check is inside the credentials. The built-in Google credentials fail the RPC with `UNAUTHENTICATED` ([GoogleAuthLibraryCallCredentials.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/auth/src/main/java/io/grpc/auth/GoogleAuthLibraryCallCredentials.java#L101-L105)). Custom credentials are already covered by an existing bug.
  - Go: with insecure transport credentials, `Dial`/`NewClient` fails with "the credentials require transport level security" ([clientconn.go](https://github.com/grpc/grpc-go/blob/v1.82.0/clientconn.go#L496-L501)). With other transport credentials below `PRIVACY_AND_INTEGRITY`, every connection fails right after the handshake as a temporary connection error ([http2_client.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/transport/http2_client.go#L299-L310)). RPCs then see `UNAVAILABLE`, or wait if wait-for-ready is set, and never `UNAUTHENTICATED`. Per-call credentials are checked per RPC with `UNAUTHENTICATED` ([http2_client.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/transport/http2_client.go#L707-L711)).
- **Prior documentation:**
  - Not covered by any prior documentation (searched: A29, A54, A83, A97, doc/server_side_auth.md, grpc_security_constants.h comments).
- **Decision:** (a) Keep the spec: the check is per RPC, with `UNAUTHENTICATED`. (b) Also allow the channel to reject the configuration at creation time when it is statically known to be incompatible (insecure credentials plus channel-level credentials that need privacy). Keep the per-RPC `UNAUTHENTICATED` rule for connections whose level is only known after the handshake.
- **Recommendation:** (b). Failing fast at channel creation is safe and helpful. Failing every connection is not: it looks like a connectivity problem (`UNAVAILABLE`, TRANSIENT_FAILURE, backoff), and wait-for-ready RPCs hang. Bug: Go (low): channel-level call credentials with an insufficient connection security level fail the connection instead of the RPC with `UNAUTHENTICATED`.
- **Why this rank:** It is rare (it needs non-TLS, non-insecure transport credentials below privacy), but the error is misleading and RPCs can hang.

### AUTHZ-2. Binary header values in RBAC matching (language bug)

The spec and gRFC A41 say `-bin` headers are matched in base64 form. Only Java does this. C++ and Go match the decoded bytes.

- **Where:** [6.4.1.3 Header Matching Rules](06-security/04-authorization.md#13-header-matching-rules) in `06-security/04-authorization.md`
- **Current spec:** "Binary headers (`-bin` suffix) are matched in their base64-encoded form."
- **Findings:**
  - C++: `EvaluateArgs::GetHeaderValue` returns `metadata_->GetStringValue(key, ...)`, which holds the decoded binary value ([evaluate_args.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/call/evaluate_args.cc#L125-L139)).
  - Java: each value is base64-encoded without padding (`BaseEncoding.base64().omitPadding()`), and the results are joined with "," ([GrpcAuthorizationEngine.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/internal/rbac/engine/GrpcAuthorizationEngine.java#L370-L387)).
  - Go: the transport base64-decodes `-bin` values into metadata (`decodeMetadataHeader`), and the RBAC header matchers compare those decoded values ([http2_server.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/transport/http2_server.go#L470), [matcher_header.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/matcher/matcher_header.go#L42-L48)).
- **Prior documentation:**
  - gRFC A41: "Binary headers are represented in their base64-encoded form, although we rarely expect binary header matchers other than presence-checking." This supports the spec. A41 doesn't say whether padding is included.
- **Decision:** (a) base64 form as written, also specifying padding (Java uses none), (b) decoded bytes (C++, Go).
- **Recommendation:** (a), and state "unpadded base64" to match Java (the transport encoding is also unpadded). Record low bugs against C++ and Go. Presence matchers, the common case, work the same everywhere.
- **Why this rank:** Value matchers on binary headers are rare. Presence checks are unaffected.

### BINARY_LOG-6. Go does not keep metadata order in binary logs (language bug)

Go builds logged metadata by iterating a map, so entry order is random. Header truncation then runs on that random order, so which entries are kept under an `h:N` limit is also random. Java keeps wire order.

- **Where:** [8.7.3.3 Metadata](08-observability/07-binary-logging.md#33-metadata) in `08-observability/07-binary-logging.md`
- **Current spec:** "`Metadata` is a list of `MetadataEntry{key, value}` in order." Truncation: "Logged entries keep their relative order."
- **Findings:**
  - C++: no binary logging.
  - Java: iterates `InternalMetadata.serialize(metadata)` in wire/insertion order and truncates in that order ([BinlogHelper.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/services/src/main/java/io/grpc/protobuf/services/BinlogHelper.java#L833-L864)).
  - Go: `mdToMetadataProto` does `for k, vv := range md` over `metadata.MD` (a map). Values of one key stay in order, but key order is random per call ([method_logger.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/binarylog/method_logger.go#L406-L422)). `truncateMetadata` then keeps a prefix of that random order ([method_logger.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/binarylog/method_logger.go#L113-L143)).
- **Prior documentation:**
  - Not covered by any prior documentation (searched: A16, `grpc/binlog/v1/binarylog.proto`, `doc/binary-logging.md` for "order").
- **Decision:** (a) keep "in order" (Java), (b) require order only within a key, or (c) make order unspecified.
- **Recommendation:** (b). Go's metadata model cannot keep order across keys, and per-key value order is what applications can see. Also say that which entries survive the header limit may depend on that order. Bugs: none if (b). Under (a), Go (low).
- **Why this rank:** Affects only log readability and which entries survive truncation. RPCs are unaffected.

### XDS_EDS-2. EDS LocalityLbEndpoints with no locality (language bug)

What happens when a `LocalityLbEndpoints` entry has no `locality` field, and does that check apply to entries with zero weight?

- **Where:** [9.4.5.2 LocalityLbEndpoints](09-xds/04-resources/05-endpoint.md#2-localitylbendpoints) in `09-xds/04-resources/05-endpoint.md`
- **Current spec:** `locality` MUST be present, or the resource is rejected. Entries with weight unset or 0 are ignored without any validation.
- **Findings:**
  - Java: an absent locality is treated as the empty locality (all fields `""`) (`XdsEndpointResource.parseLocality`) ([XdsEndpointResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L138), [XdsEndpointResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L159-L161)).
  - Go: rejects ("locality without ID"). The check runs before zero-weight entries are skipped, so zero-weight entries without a locality are rejected too (`unmarshal_eds.go`) ([unmarshal_eds.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_eds.go#L181-L189)).
  - C++: rejects, but checks after zero-weight entries are skipped (`xds_endpoint_parser.cc`) ([xds_endpoint_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_endpoint_parser.cc#L218-L235)).
  - Envoy: A missing `locality` is not rejected. The hosts get the default (empty) `Locality` via `getObject(locality_lb_endpoint.locality())`. `initializePriorityFor` records a locality weight only when both `has_locality()` and `has_load_balancing_weight()` are true, so such an entry ends up with locality weight 0. This matches option (c) (Java). Entries with an unset weight are not skipped: their endpoints are still parsed and registered as hosts (weight 0 just means locality-weighted LB gives them no traffic). An explicit locality weight of 0 NACKs via PGV `gte: 1`. (https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/upstream/upstream_impl.cc#L2421-L2434, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/upstream/upstream_impl.cc#L2449-L2456, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/api/envoy/config/endpoint/v3/endpoint_components.proto#L189-L224, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/extensions/load_balancing_policies/common/thread_aware_lb_impl.cc#L56-L70)
- **Prior documentation:**
  - gRFC A27 ("ClusterLoadAssignment Proto"): "If the `load_balancing_weight` field is unset, the `endpoints` entry is skipped". It also says "The `locality` field must be unique within a given priority. If more than one entry in the `endpoints` field has the same values in both the `locality` and `priority` field, the resource will be considered invalid." A27 skips unset-weight entries (no mention of 0). It never requires `locality` to be present.
  - Envoy `LocalityLbEndpoints.locality` comment: "Identifies location of where the upstream hosts run." It doesn't say the field is required.
  - Whether a missing locality is rejected is not covered by any prior documentation (searched: gRFCs A27/A46/A52/A56/A61/A74/A88, doc/*.md, protos, pending PRs).
- **Decision:** (a) reject, without validating zero-weight entries (C++), (b) reject, and validate zero-weight entries too (Go), or (c) treat a missing locality as empty (Java).
- **Recommendation:** (a). Two of three implementations reject, and skipping ignored entries entirely is the simplest rule and matches how other ignored data is handled. Java needs a fix to reject, and Go needs a fix to move the check after the zero-weight skip.
- **Why this rank:** A missing locality is an unusual control-plane output; Java accepts it and Go over-validates zero-weight entries.

### XDS_EDS-4. EDS drop_overloads validation gaps (language bug)

Go and Java accept an empty `category` and treat a missing `drop_percentage` as 0, and C++ can wrap when normalizing an oversized numerator. Go used to panic on an unknown denominator and compute the wrong drop fraction; that was fixed in v1.84.0.

- **Where:** [9.4.5.5 Drop Overloads](09-xds/04-resources/05-endpoint.md#5-drop-overloads) in `09-xds/04-resources/05-endpoint.md`
- **Current spec:** `category` MUST be non-empty. `drop_percentage` MUST be present, is normalized to a value per million, and is capped at 1,000,000. An unknown denominator rejects the resource.
- **Findings:**
  - C++: rejects an empty category, a missing `drop_percentage`, and an unknown denominator, and caps at 1,000,000. The `numerator *= 10000` / `*= 100` multiplication is in uint32 and can wrap before the cap for absurd numerators (above 429496 for HUNDRED) ([xds_endpoint_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_endpoint_parser.cc#L288-L335)).
  - Java: rejects an unknown denominator (IllegalArgumentException, which the generic catch NACKs) and caps the value. It accepts an empty category and treats a missing `drop_percentage` as 0 ([XdsEndpointResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L163-L189)).
  - Go: `parseDropPolicy` now calls `NewFractionalPercent`, which NACKs an unknown denominator, caps the value at 1,000,000 per million, and computes it in uint64. `xds_cluster_impl` uses the precomputed per-million value, so the divide-by-zero panic, the uint32 overflow, and the >100% underflow are gone ([unmarshal_eds.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_eds.go#L79-L88), [fractional_percent.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/fractional_percent.go#L38-L70), [clusterimpl.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/clusterimpl/clusterimpl.go#L167-L176)). Fixed by [grpc/grpc-go#9218](https://github.com/grpc/grpc-go/pull/9218) and [#9257](https://github.com/grpc/grpc-go/pull/9257), both first in v1.84.0. Like Java, it accepts an empty category and treats a missing `drop_percentage` as 0.
- **Prior documentation:**
  - A27, EDS validation: "The `policy.drop_overloads` field may be set." The gRFC gives no other rules. The validation and capping rules come from the spec (which follows C++).
- **Decision:** (a) Keep the spec; Java and Go must reject an empty category and a missing `drop_percentage`. (b) Relax the empty-category and missing-percentage rules to "treated as 0 / allowed" (Java), keeping the denominator and cap rules.
- **Recommendation:** (a). The spec behavior is the safe one. Bugs: Java (low), Go (low): empty drop category and missing `drop_percentage` accepted. C++ (low): uint32 wrap when normalizing an oversized HUNDRED/TEN_THOUSAND numerator. The former Go (critical) bug (unknown drop denominator panics; uint32 overflow above 4294 per denominator unit and above 100%) was fixed in v1.84.0 (grpc/grpc-go#9218, #9257).
- **Why this rank:** Now that Go's panic and overflow are fixed, these are low-impact validation gaps.

### XDS_DEPMGR-3. Failed underlying clusters, cycles, and depth in aggregate expansion (language bug)

Only C++ skips an underlying cluster that does not exist or has an error. Go fails the whole aggregate, and Java keeps the failed cluster as a leaf. Java also handles cycles and the depth limit differently.

- **Where:** [9.5.2.3 Aggregate cluster graph](09-xds/05-client.md#23-aggregate-cluster-graph) in `09-xds/05-client.md`
- **Current spec:** An underlying cluster whose CDS resource does not exist, or has an error and no cached resource, MUST be skipped, and its error goes into the aggregate's resolution note. Cycles end the traversal. Exceeding depth 16 gives UNAVAILABLE `aggregate cluster graph exceeds max depth` to the aggregate at the root of that branch and to every aggregate above it.
- **Findings:**
  - C++: conforms ([xds_dependency_manager.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_dependency_manager.cc#L665-L697)). Tests UnderlyingClusterDoesNotExist and DependencyLoopWithLeafClusters cover it ([xds_cluster_type_end2end_test.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/test/cpp/end2end/xds/xds_cluster_type_end2end_test.cc#L953-L975)).
  - Go: a CDS error on any underlying cluster is returned as an error ([xds_dependency_manager.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L336-L339)). The aggregate then stores that error as its own entry and passes it up to every ancestor ([L423-L426](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L423-L426)). One missing underlying cluster fails the whole aggregate (the old A37 behavior). Cycles and depth match the spec.
  - Java: adds the failed cluster to the leaf list, so `priority` gets a child that always fails (A74's first option) ([XdsDependencyManager.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L336-L348)). When a cluster is reached again through a cycle, it gets an INTERNAL "Aggregate cluster cycle detected" entry, which then can't be overwritten ([L306-L311](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L306-L311), [L384-L388](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L384-L388)), so an aggregate on a cycle fails even when the cycle has leaves. The depth check is `ancestors.size() > 16` with INTERNAL status, and it sets the error only on the too-deep cluster, which ancestors then treat as a failing leaf ([L312-L316](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L312-L316)).
  - Envoy: skips absent underlying clusters ([aggregate/cluster.cc](https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/extensions/clusters/aggregate/cluster.cc#L71-L77)).
- **Prior documentation:**
  - gRFC A74, "Changes in xds Resolver": "So instead, we will now simply skip any underlying cluster that does not exist. There are two ways to implement this." The first way adds the missing cluster to the leaf list ("a child of the priority policy that will always report state TRANSIENT_FAILURE"), which is Java's behavior. The second omits it, which is C++ and the spec. A74 does not allow Go's behavior.
  - gRFC A37: "The tree of aggregate clusters has a depth limit of 16." Java's limit is one level more.
- **Decision:** (a) keep the spec (skip), (b) also allow A74's first option (a leaf that always fails), (c) other.
- **Recommendation:** (a), or (b) if the owner wants to follow A74 exactly. Bugs: Go (high): a missing or failed underlying cluster fails the whole aggregate cluster. Java (medium): an aggregate cluster on a cycle fails with INTERNAL even when it has leaves. Java (low): the aggregate depth limit allows 17 levels, uses INTERNAL, and is not passed up to ancestor aggregates. Under (a), also Java (low): failed underlying clusters are kept as leaves instead of skipped.
- **Why this rank:** Go loses aggregate failover entirely when any one underlying cluster is missing, and Java fails valid cyclic graphs.

### XDS_DEPMGR-4. Ambient errors and the resolution note (language bug)

Only C++ records ambient errors and the node ID in each cluster's resolution note. Java and Go only log ambient errors, or drop them, and don't send a new config when one arrives.

- **Where:** [9.5.2.5 Error handling](09-xds/05-client.md#25-error-handling) in `09-xds/05-client.md`
- **Current spec:** The note for each EDS or LOGICAL_DNS cluster joins the LDS, RDS, and cluster CDS ambient errors with the endpoint note. If all are empty, it MUST be `xDS node ID:<id>`. Ambient errors cause a new config to be delivered.
- **Findings:**
  - C++: conforms ([xds_dependency_manager.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_dependency_manager.cc#L368-L381), [L631-L651](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_dependency_manager.cc#L631-L651)).
  - Java: `onAmbientError` writes a field marked `@SuppressWarnings("unused")` that is never read, and does not republish ([XdsDependencyManager.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L666-L677)). `EndpointConfig` holds a `StatusOr<EdsUpdate>` and has no note. Node info is appended to error statuses instead.
  - Go: ambient errors are only logged ([xds_dependency_manager.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L591-L601), [L698-L707](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L698-L707), [L766-L775](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L766-L775)). The note is just the EDS/DNS error ([L380-L384](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L380-L384)). The node ID is added to error text instead (`annotateErrorWithNodeID`).
- **Prior documentation:**
  - gRFC A88, "Handling Ambient Errors": "the `resolution_note` for each cluster will contain the ambient errors for all resources for that cluster: ambient errors for the top-level LDS and RDS resources will be included for all clusters, but each cluster will include the ambient errors for only its own CDS and EDS resources." Also: "If none of the resources for a given cluster have ambient errors, the XdsDependencyManager will set the resolution note to indicate the xDS node ID". Matches the spec.
  - spec-optionality-notes.md, xDS: Go doesn't implement "the A88 data-error handling". That covers the server features, not this resolution-note behavior; Java isn't mentioned.
- **Decision:** (a) keep the spec (A88), (b) require only that ambient errors appear in data-plane errors, leaving the format and the node-ID fallback implementation-defined.
- **Recommendation:** (a) for ambient errors, which A88 requires and which matter during outages. If the owner doesn't want to require one string format, (b) for the exact `xDS node ID:` text. Bugs: Java (medium) and Go (medium): ambient xDS errors are not added to cluster resolution notes or RPC failure messages.
- **Why this rank:** Without this, Java and Go hide the main clue in xDS-server-loss outages, but routing doesn't change.

### XDS_RESOLVER-2. Resolver result when the xDS config has an error (language bug)

When `OnUpdate()` reports an error, does the resolver result include a ConfigSelector that fails every RPC, including wait_for_ready RPCs?

- **Where:** [9.5.4 Resolver Result](09-xds/05-client.md#4-resolver-result) in `09-xds/05-client.md`
- **Current spec:** Empty endpoints, service config `{}`, no ConfigSelector, and the error as the resolution note. Only RPCs that are not wait_for_ready fail.
- **Findings:**
  - Java: empty config plus a ConfigSelector that fails every RPC, so wait_for_ready RPCs also fail (`XdsNameResolver.cleanUpRoutes`, `RoutingConfig.errorStatus`) ([XdsNameResolver.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L930-L931), [XdsNameResolver.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L429-L430)).
  - Go: empty config with no ConfigSelector, and the error is reported as a resolver error. Its `erroringConfigSelector` is never passed to the channel ([xds_resolver.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/resolver/xds_resolver.go#L369-L382)).
  - C++: empty config, error as resolution note, no ConfigSelector (`XdsResolver::GenerateErrorResult`) ([xds_resolver.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/xds/xds_resolver.cc#L1035-L1043)).
  - Envoy: This is an analogy only, because Envoy has no resolver result, ConfigSelector, or wait_for_ready. Envoy never queues a request while waiting for config to be fixed. If no route matches, the router immediately sends a local `404` (`NoRouteFound`). If the route's cluster is missing, it immediately sends `clusterNotFoundResponseCode()` (`NoClusterFound`). If RDS fails or arrives empty before any config was received, Envoy stops waiting and serves a null route config (`createNullConfig`), so every request gets the immediate no-route reply. In effect this matches option (b), "fail all RPCs", rather than (a). Separately, a delta RDS removal is ignored, so the last good config stays in use. (https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/router/router.cc#L521-L590, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/rds/rds_route_config_subscription.cc#L112-L124, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/rds/rds_route_config_subscription.cc#L195-L220, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/rds/route_config_update_receiver_impl.cc#L56-L60)
- **Prior documentation:**
  - gRFC A74 (xDS config tears), `XdsDependencyManager::Watcher`: "Called when a new xDS config is available or when there is an error for the LDS or RDS resource for which we want to stop using the previously seen resource, if any." It lists when `OnUpdate()` gets an error, but doesn't say what resolver result to produce.
  - gRFC A27 and A28: "If no matching VirtualHost is found in the RouteConfiguration, the `xds` resolver will return an error to the client channel." (A27). Also: "the xDS resolver will return an error to the client channel." (A28). They say "return an error" without saying how, so they don't decide ConfigSelector vs. resolution note.
  - gRFC A88 (xDS data error handling), "Summary of Behavior Changes" table: errors with no cached resource result in "`OnResourceChanged(Status)`, Fail data plane RPCs". It doesn't say whether wait_for_ready RPCs are included.
  - gRFC A54 (restrict control-plane status codes) lists "When applying a failed Config Selector result from the name resolver (an internal API for xDS in [gRFC A31][])". This assumes a resolver *may* produce a failing ConfigSelector result, which is consistent with Java's approach existing, but it doesn't require it.
  - doc/wait-for-ready.md: "gRPC implementations MAY provide a per-RPC option to not fail RPCs as a result of the channel being in `TRANSIENT_FAILURE` state. Instead, the implementation queues the RPCs until the channel is `READY`." Pending PR grpc/grpc#38953 (client channel), picker results: "Note, however, that if the RPC is [wait\_for\_ready], then it will be queued instead of being failed." These general semantics support option (a).
  - Pending PR grpc/grpc#38953 also says: "if a resolver returns an error for the service config and it has not previously returned a valid result to the channel, the channel will be placed into TRANSIENT\_FAILURE state, and RPCs that are not [wait\_for\_ready] will fail with that status."
  - No gRFC states the xDS resolver's error-result shape (searched A27, A28, A31, A47, A53, A54, A71, A74, A88).
- **Decision:** (a) no ConfigSelector, so wait_for_ready RPCs wait (C++/Go), or (b) an erroring ConfigSelector that fails all RPCs (Java).
- **Recommendation:** (a). Two of three implementations do this, and it follows normal wait_for_ready semantics: the error may be transient, and the RPC should wait for a fixed config. Java needs a fix.
- **Why this rank:** Java fails wait-for-ready RPCs on transient xDS config errors, against standard wait-for-ready semantics.

### XDS_LB-6. xds_cluster_impl: drops while not READY and drop_all → READY (language bug)

Only C++ applies EDS drops to every pick and reports READY when a category drops 100%. Go drops only while the child is READY, and Java never forces READY.

- **Where:** [`xds_cluster_impl` LB Policy: 3.2 Features › Drops](09-xds/lb-policies/xds_cluster_impl.md#drops) in `09-xds/lb-policies/xds_cluster_impl.md`
- **Current spec:** "For every pick, before anything else" apply drops. "If any category drops 100% of requests (`drop_all`), the policy MUST report READY with its drop picker, whatever state the child reports (or whether it has reported at all)."
- **Findings:**
  - C++: drops first on every pick. `MaybeUpdatePickerLocked` reports READY when `drop_config_->drop_all()`. ([xds_cluster_impl.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_cluster_impl.cc#L397-L403), [xds_cluster_impl.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/xds/xds_cluster_impl.cc#L724-L736))
  - Java: drops on every pick, but reports the child's state unchanged, with no `drop_all` handling. ([ClusterImplLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L216-L223), [ClusterImplLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L409-L419))
  - Go: "Don't drop unless the inner picker is READY": drops are skipped when the child is not READY. It reports the child's state unchanged, with no `drop_all` handling. With 100% drops and no reachable backends, nothing is dropped, and RPCs fail with the child's error or wait. ([picker.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/balancer/clusterimpl/picker.go#L102-L114), [clusterimpl.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/balancer/clusterimpl/clusterimpl.go#L517-L536))
  - Envoy: not checked.
- **Prior documentation:**
  - Not covered by any prior documentation (searched: A27, A37, A74 for "drop"; A37 only says drops are handled by `xds_cluster_impl`).
- **Decision:** (a) keep the spec (always drop; `drop_all` → READY); (b) keep "always drop" but drop the READY requirement; (c) allow dropping only when the child is READY.
- **Recommendation:** (a). A control plane uses `drop_all` to shed all traffic for a cluster. That must work when the backends are down, and drops must not depend on connection state. Bugs: Go (medium): EDS drops not applied unless the child is READY, and no READY for drop_all. Java (low): drop_all does not report READY.
- **Why this rank:** In Go, configured drops silently stop working exactly when backends are unreachable.

### XDS_FILTERS-2. `http_filters` validation edge cases (language bug)

Java and Go differ from the spec (and from C++) on three edge cases in `HttpConnectionManager.http_filters` validation: an empty name, a missing `typed_config` on an optional entry, and when the terminal-filter check runs.

- **Where:** [9.7.3 Top-Level Configuration (`HttpConnectionManager.http_filters`)](09-xds/07-http-filters.md#3-top-level-configuration-httpconnectionmanagerhttp_filters) in `09-xds/07-http-filters.md`
- **Current spec:** An empty `name` NACKs. A missing `typed_config` NACKs (even if `is_optional`). The terminal-placement check runs after optional unknown entries are dropped.
- **Findings:**
  - C++: matches the spec on all three: empty name NACK, `ExtractXdsExtension` fails on a missing `typed_config`, and the terminal check runs on the filtered list ([xds_listener_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_listener_parser.cc#L268-L297), [terminal check](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_listener_parser.cc#L324-L350)).
  - Java: checks only for duplicate names, so one empty name is accepted. It checks "the last entry is terminal" against the original list, so `[router, optional-unknown]` is NACKed. A missing `typed_config` with `is_optional` is silently dropped ([XdsListenerResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L516-L549), [parseHttpFilter](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L586-L591)).
  - Go: empty name and terminal check match the spec. A missing `typed_config` gives an empty type URL, which is "not found" in the registry, so it is ignored if `is_optional` ([unmarshal_lds.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L152-L163)).
- **Prior documentation:**
  - gRFC A39: "Every filter in the list must have a unique instance name." and "validation will fail if a terminal filter is not the last filter in the chain or if a non-terminal filter is the last filter in the chain." A39 does not explicitly mention empty names, a missing `typed_config`, or when the terminal check runs.
- **Decision:** (a) keep the spec (C++ behavior), (b) allow an optional entry without `typed_config` to be ignored (Java/Go), or (c) leave these edge cases implementation-defined.
- **Recommendation:** (a). "Ignore if optional" exists for unknown types, and a missing `typed_config` is malformed, not unknown. Checking the terminal filter after dropping optional entries is the only reading consistent with `is_optional`. Bugs: Java (low): empty HTTP filter name accepted; Java (low): terminal-filter check runs before dropping optional entries; Java/Go (low): optional HTTP filter without typed_config ignored instead of NACKed.
- **Why this rank:** Edge cases that only affect malformed or unusual configs.

### XDS_GCP_AUTHN-1. GCP authn filter per-route override (language bug)

gRFC A83 says a per-route `GcpAuthnFilterConfig` override is "validated ... but will not actually be used". C++ instead rejects any override.

- **Where:** [9.7.11.1 Configuration Validation](09-xds/07-http-filters.md#111-configuration-validation) in `09-xds/07-http-filters.md`
- **Current spec:** An override is validated as a top-level config and never used.
- **Findings:** Java (`GcpAuthenticationFilter.parseFilterConfigOverride`, which parses the override as a top-level config, while `buildClientInterceptor` never reads `overrideConfig`; [GcpAuthenticationFilter.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/GcpAuthenticationFilter.java#L126-L129), [GcpAuthenticationFilter.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/GcpAuthenticationFilter.java#L134-L140)) and Go (`gcp_authn_filter.go`) validate the override and ignore it, as A83 says. C++ registers no override type (`OverrideConfigProtoName() == ""`), so any override NACKs unless `is_optional` is set (`xds_http_gcp_authn_filter.cc`) ([xds_http_gcp_authn_filter.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_gcp_authn_filter.cc#L39-L42); an empty name is never registered as an override type, [xds_http_filter_registry.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_filter_registry.cc#L32-L36); and an unknown override type is "unsupported filter type" unless optional, [xds_route_config_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_route_config_parser.cc#L330-L335)).
  - **Go (master re-check):** grpc-go v1.82.0 had no GCP authentication filter (only the CDS `Audience` metadata converter), so in that release only Java validated and ignored the override. Go master now has the filter and conforms. The filter is registered unconditionally (imported by `xds/xds.go`), and `ParseFilterConfigOverride` validates the override as a top-level `GcpAuthnFilterConfig` and never uses it ([gcp_authn_filter.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/httpfilter/gcpauthn/gcp_authn_filter.go#L82-L88), [xds.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/xds/xds.go#L45)). The filter was added in [grpc/grpc-go#9119](https://github.com/grpc/grpc-go/pull/9119) (v1.83.0) but registered only by [#9471](https://github.com/grpc/grpc-go/pull/9471) (on master, not yet in a release as of v1.85.0). The CDS `Audience` metadata converter is still gated by `GRPC_EXPERIMENTAL_XDS_GCP_AUTHENTICATION_FILTER` (default false) ([metadata.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/metadata.go#L36)).
  - **Spec self-contradiction:** 9.7 "4. Override Configuration" table row "Type known" says an override "fails validation if the value is the filter's top-level config type and the filter either does not support overrides or uses a different override type" (A39's rule, which C++ follows), while 11.1 says a `GcpAuthnFilterConfig` override is validated and never used. Whichever option is chosen, also update that table row (and the "Override config type" column of the 2. registry table).
  - Envoy: Envoy **rejects** per-route overrides, matching option (b) (C++), not A83's "validate and ignore". `GcpAuthnFilterFactory` does not override `createRouteSpecificFilterConfigTyped`, so the base class returns `nullptr`. `PerFilterConfigs::createRouteSpecificFilterConfig` first parses and validates the override as a `GcpAuthnFilterConfig`. It then fails with "The filter … doesn't support virtual host or route specific configurations". The override is skipped instead only if it is wrapped in a `FilterConfig` with `is_optional: true`. (https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/extensions/filters/http/gcp_authn/filter_config.h#L14-L32, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/extensions/filters/http/common/factory_base.h#L62-L75, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/router/per_filter_config.cc#L44-L66)
- **Prior documentation:**
  - gRFC A83, filter config section: "Note that this filter does not support having its config overridden in a `typed_per_filter_config` field on a per-route, per-virtualhost, or per-clusterweight basis. If the filter's config message appears in a `typed_per_filter_config` field, it will be validated as part of the normal resource validation, but the configuration will not actually be used." Supports Java/Go and the spec: validate, then ignore.
  - gRFC A39, `typed_per_filter_config` validation: "The filter implementation will also verify that the config is of the right type (i.e., it will fail validation if the override config is of the filter's top-level config type and either the filter does not support an override config or it uses different types for its top-level config and its override config). Any validation error will cause the resource to be NACKed." Under this general rule, a filter that supports no override NACKs, which is C++'s behavior. **A83 and A39 conflict here.** A83 is the more specific gRFC.
- **Decision:** (a) follow A83 (validate, ignore) and fix C++, or (b) change the spec and A83 to say overrides are rejected (C++).
- **Recommendation:** (a). It matches the gRFC and two of three implementations, and accepting a harmless override avoids NACKing configs that Envoy accepts. C++ needs a fix. **Note (Envoy code check):** Envoy actually rejects a non-optional per-route gcp_authn override (see Findings), so Envoy agrees with C++ (b) and the "Envoy accepts" argument does not hold.
- **Why this rank:** C++ NACKs configs with a per-route override that A83 and Java/Go accept, rejecting the resource.

### XDS_SECURITY-3. `DownstreamTlsContext` validation gaps, mostly in Java (language bug)

Java doesn't NACK several invalid server TLS configs, and one of them leaves required mTLS unenforced. C++ accepts a validation context with no CA source.

- **Where:** [9.9.7 Server Side: `DownstreamTlsContext`](09-xds/09-security.md#7-server-side-downstreamtlscontext) in `09-xds/09-security.md`
- **Current spec:** `require_client_certificate: true` without `ca_certificate_provider_instance` NACKs. A validation context without `ca_certificate_provider_instance` NACKs. `system_root_certs` on servers NACKs. `require_sni` NACKs only if true. `require_client_certificate` takes its value.
- **Findings:**
  - C++: NACKs `require_client_certificate` without a CA provider and NACKs `system_root_certs` on servers. Accepts a validation context with no CA source (no client certificate is requested). `require_sni` and SCT are checked by value ([xds_listener_parser.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_listener_parser.cc#L440-L505)).
  - Java:
    - Does not NACK `require_client_certificate: true` without a CA. It then sets `ClientAuth.NONE` because there is no trust manager, so mTLS that the control plane required is silently not enforced ([XdsClusterResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L481-L489), [SslContextProvider.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/internal/security/SslContextProvider.java#L77-L90)).
    - Uses `hasRequireClientCertificate()` instead of the value, so an explicit `false` is treated as required ([EnvoyServerProtoData.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/EnvoyServerProtoData.java#L165-L170)).
    - NACKs `require_sni` whenever it is present, even if false ([XdsListenerResource.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L296-L318)).
    - Does not NACK `system_root_certs` or a CA-less validation context on servers.
  - Go: NACKs all of the spec's cases. `require_sni` is checked by value ([unmarshal_lds.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L347-L365), [unmarshal_cds.go](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L529-L575)).
- **Prior documentation:**
  - gRFC A29: "Note that if [`require_client_certificate`] is true, and if no `CertificateValidationContext` is provided, gRPC will NACK the LDS resource." This supports the spec.
  - gRFC A82: "The new `system_root_certs` field will not be supported on the gRPC server side. If `ca_certificate_provider_instance` is unset and `system_root_certs` is set, the LDS resource will be NACKed." This supports the spec.
  - gRFC A29: "If any of the following fields are present, gRPC will NACK an LDS update ... [require_sni]: when this is set to `true` ...". "Present" literally supports Java, but the rationale is about `true`.
  - A CA-less validation context on servers is not covered by any gRFC (A29 only requires one for `require_client_certificate`).
- **Decision:** (a) keep the spec (Go), (b) relax "validation context without CA → NACK" to "no client certificate requested" (C++), keeping everything else, or (c) leave the presence-vs-value distinction implementation-defined.
- **Recommendation:** (b). The failure that matters is Java not enforcing required mTLS. An empty validation context is harmless, and C++ treats it as "no client certificate requested", so the spec's NACK isn't needed. Bugs: Java (high): require_client_certificate=true without a CA provider is accepted and the client certificate is not required; Java (medium): explicit require_client_certificate=false treated as true; Java (medium): system_root_certs on the server not NACKed; Java (low): require_sni=false NACKed. If (a) is chosen: C++ (low): validation context without a CA source not NACKed.
- **Why this rank:** Java silently fails open on mTLS the control plane required.

### CSDS-1. CSDS error_state details for per-resource NACKs (language bug)

When one response has several invalid resources, should each NACKed resource's `error_state.details` show only its own error, or all of the response's errors?

- **Where:** [9.11.3.3 `error_state`](09-xds/11-csds.md#33-error_state) in `09-xds/11-csds.md`
- **Current spec:** Only resources that failed validation are NACKED and get an `error_state`. Valid resources in the same response are ACKED.
- **Findings:** All three implementations mark only the failing resources NACKED (C++ `SetNacked`/`SetAcked`, [xds_client.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/xds_client/xds_client.cc#L1054-L1064), [xds_client.cc](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/xds_client/xds_client.cc#L1468-L1478); Java `XdsClientImpl.handleResourceUpdate`, [XdsClientImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L618-L620); Go `authority.go`, [authority.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/clients/xdsclient/authority.go#L390-L398)). This differs from A40's example, which marks all resources NACKED but was written before A46. For `details`, C++ and Go store each resource's own error (the per-resource `decode_status` / `uErr.Err` in the links above), and Java stores the joined errors for the whole response (`Joiner.on('\n').join(errors)`, passed to every invalid resource's `onRejected`; [XdsClientImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L593-L598), [XdsClientImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L1017-L1020)).
  - Envoy: For LDS, Envoy applies each valid listener in the response and records an `UpdateFailureState` only for each listener that fails. That entry's `details` holds only that listener's own error message. `config_dump` reports it as that listener's `error_state`. The joined message for the whole response goes only into the NACK. This matches option (a), as in C++ and Go. I checked LDS only. `CdsApiHelper` collects cluster errors into a list for the NACK, and I did not check whether CDS fills a per-cluster `error_state`. (https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/listener_manager/lds_api.cc#L63-L119, https://github.com/envoyproxy/envoy/blob/a40510120eea1083a3300fc1dd2c3402f66cf26b/source/common/listener_manager/listener_manager_impl.cc#L587-L598)
- **Prior documentation:**
  - gRFC A40, "NACK handling": "If one resource has validation error: record the error, and attach the error string to all resources in the ADS update including itself." Its example shows "{Endpoint A, NACK, ... rejected reason: Failed to parse endpoint B}". **On `details`, A40 favors (b), Java's response-wide error string.** A46 changed which resources are used, but it didn't revisit what error text CSDS shows. A40's example (all resources NACKED) is still the gRFC text on grpc-proposal master 89f34f2; A40 has not been updated for A46. No change in implementation behavior found (spec audit).
  - gRFC A46, "Proposal": "when a response is NACKed, gRPC will still use all valid resources from the response; it will ignore only the invalid resources." This supports marking only the failing resources NACKED.
  - gRFC A88, "Cache Entry States, CSDS, and XdsClient Metrics": "`NACKED`: The most recent version of the resource seen from the control plane was invalid.  The error will indicate the validation failure." And: "Those states map directly to the states in the CSDS `ClientResourceStatus` enum." This newer text describes a per-resource error, which supports (a). So A40 and A88 point in opposite directions.
- **Decision:** For `details`: (a) the resource's own error (C++/Go), (b) all errors in the response (Java), or (c) implementation-defined.
- **Recommendation:** (a). It matches two of three implementations and is more useful when debugging a single resource. Java needs a minor fix. Add a note that A40's example is out of date after A46.
- **Why this rank:** Only the debug details of the CSDS error string differ (Java joins all errors).
