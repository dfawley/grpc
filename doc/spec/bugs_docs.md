# Documentation bugs

Errors and stale text in gRFCs (grpc-proposal), `grpc/doc`, and grpc-proto found while writing and reviewing the gRPC spec in this directory, where the spec is believed correct: **62** entries, ordered by severity. Other lists: [Go](bugs_go.md), [Java](bugs_java.md), [C++](bugs_cpp.md).

Severity:

- **critical:** crash, data corruption, or a security weakness
- **high:** interoperability failure, or wrong behavior that users commonly hit
- **medium:** spec non-conformance with limited impact
- **low:** cosmetic, or a rare edge case

Each bug lists the review item that identified it (an item ID such as `RLS-4`, an `R<n>` number from the original review list, or "incidental"/"audit"), a summary, a description, evidence (code locations), and the spec section it violates. Open questions are in [review_items.md](review_items.md). None of these bugs has been filed yet.

### [high] Review A118 TLS offload metric label names and certificate-selection metric

- **Item:** R129
- **Summary:** gRFC A118's TLS offload metrics use inconsistently named labels and define a certificate-selection offload metric with no feature gRFC behind it; review before any implementation ships.
- **Description:** A118 defines the labels `grpc.tls.private_key.offloader_name` (dot after `private_key`) and `grpc.tls.private_key_algorithm` (underscore), which is inconsistent; a normalized name such as `grpc.tls.private_key.algorithm` may be preferable. A118 also defines `grpc.server.tls.offload_certificate_selection_duration`, but no gRFC defines server certificate-selection offloading, so the metric's semantics are undefined. No implementation emits these metrics yet, so renaming or removing them is free now and costly later. The spec currently lists all three names exactly as A118 defines them.
- **Evidence:** grpc-proposal `A118-tls-telemetry.md`; A107-tls-private-key-offloading.md covers signing only.
- **Spec:** 08-observability/04-metrics.md, TLS Metrics

### [high] gRFC A29 NACKs `require_sni` when present, contradicting its own rationale

- **Item:** audit (xdsfilters); related: XDS_SECURITY-3
- **Summary:** A29's LDS rules say an LDS update is NACKed if `require_sni` is *present*, but the rationale only covers the value `true`. Read literally, an explicit `require_sni: false` is NACKed.
- **Description:** A29 says: "If any of the following fields are present, gRPC will NACK an LDS update as part of validating all LDS updates:" and then, for `require_sni`: "when this is set to `true`, it requires the server to \"reject connections without a valid and matching SNI\" … Silently ignoring the `true` value will result into gRPC not rejecting connections … hence gRPC will NACK such an LDS update." The lead-in sentence ("present") and the rationale (`true`) disagree. An explicit `false` asks for nothing gRPC lacks, so rejecting it is wrong, and it breaks control planes that always fill in the field. Java follows the literal reading and NACKs an explicit `false` (`XdsListenerResource`); C++ and Go NACK only `true`, which the spec requires. Suggested correction: "If any of the following fields are set to an unsupported value, gRPC will NACK…", and for `require_sni`, "gRPC will NACK an LDS update if this field is `true`."
- **Evidence:** grpc-proposal `A29-xds-tls-security.md` (master 4125fbd), "LDS for Server Side Security" (the list that begins "If any of the following fields are present").
- **Spec:** xDS Security: Server Side: `DownstreamTlsContext`

### [medium] doc/PROTOCOL-HTTP2.md requires the consumer to verify the grpc-status-details-bin code

- **Item:** audit (wire); spec change R10
- **Summary:** PROTOCOL-HTTP2.md says the receiver MUST check that `grpc-status-details-bin` matches `grpc-status`. The spec makes this a MAY and requires the raw trailer to stay readable.
- **Description:** Responses: "If it contains a status code field, it MUST NOT contradict the **Status** header. The consumer MUST verify this requirement." The spec (after R10) puts the obligation on the sender: the details MUST match, a receiving library MAY check and MAY act on a mismatch but is not required to, and the application MUST be able to read the raw `grpc-status-details-bin` trailer whether or not the library checks. Go, Java, and C++ all let applications read the raw trailer. Suggested correction: "The sender MUST ensure this. A receiver MAY verify it, but MUST still make the raw value available to the application." Not covered by the local doc edits (`doc_changes.md`).
- **Evidence:** grpc `doc/PROTOCOL-HTTP2.md`, "Responses" (paragraph after the percent-encoding notes).
- **Spec:** gRPC over HTTP/2: `grpc-status-details-bin`

### [medium] doc/PROTOCOL-HTTP2.md lists `+json` as a content-subtype

- **Item:** audit (wire); spec change R121
- **Summary:** The Content-Type rule still offers `+json` next to `+proto`, but nothing defines a gRPC JSON encoding and no implementation ships one.
- **Description:** Requests: "**Content-Type** → \"content-type\" \"application/grpc\" [(\"+proto\" / \"+json\" / {_custom_})]". Listing `+json` beside `+proto` reads as a standard subtype with a defined meaning, so an implementer may expect peers to support it. The spec (R121) removed `+json`: `+proto` (or bare `application/grpc`) means Protocol Buffers, and any other subtype is a custom subtype used by agreement. Suggested correction: `[("+proto" / {_custom_})]`.
- **Evidence:** grpc `doc/PROTOCOL-HTTP2.md`, "Requests" (Content-Type rule).
- **Spec:** gRPC over HTTP/2: `content-type`

### [medium] doc/PROTOCOL-HTTP2.md Trailers-Only grammar has no slot for grpc-accept-encoding

- **Item:** audit (wire); spec change R99
- **Summary:** The Trailers-Only rule cannot carry `grpc-accept-encoding`, but doc/compression.md lets a server include it in the `UNIMPLEMENTED` response to an unsupported compression algorithm, which is usually Trailers-Only.
- **Description:** Responses: "**Trailers-Only** → HTTP-Status Content-Type Trailers". doc/compression.md says "The server MAY include a `grpc-accept-encoding` response header" when it rejects a message compressed with an algorithm it doesn't support, and that error is normally sent as Trailers-Only. The two documents contradict each other. The spec's grammar is `Trailers-Only = HTTP-Status Content-Type [Message-Accept-Encoding] Trailers`. Suggested correction: add `[Message-Accept-Encoding]` to the Trailers-Only rule.
- **Evidence:** grpc `doc/PROTOCOL-HTTP2.md`, "Responses" (Trailers-Only rule); `doc/compression.md`, "Compression Method Asymmetry Between Peers".
- **Spec:** gRPC over HTTP/2: Responses › Grammar

### [medium] doc/connectivity-semantics-and-api.md gives a 5-minute default idle timeout

- **Item:** audit (channel)
- **Summary:** The doc says the default IDLE_TIMEOUT is 300 seconds. The spec recommends 30 minutes, which is what C++, Java, and Go use.
- **Description:** IDLE: "We will use a default IDLE_TIMEOUT of 300 seconds (5 minutes)." All three implementations default to 30 minutes, and the spec says the idle timeout MUST be enabled by default with a RECOMMENDED default of 30 minutes. An implementer following the doc would make channels go idle (and drop connections) six times as often as everyone else. Suggested correction: "a default IDLE_TIMEOUT of 30 minutes". The local doc edits (commit e4e62ae4c2) rewrote other parts of this file but left this sentence.
- **Evidence:** grpc `doc/connectivity-semantics-and-api.md`, IDLE state description.
- **Spec:** Channel: Idle Timeout

### [medium] doc/compression.md allows a channel-level default compression level

- **Item:** audit (core)
- **Summary:** compression.md says a default compression *level* MAY be set when the channel is created, but later says levels are only supported on the server.
- **Description:** Intent: "A _default compression level_, to be used in the absence of message-specific settings, MAY be specified for during channel creation." Compression Levels and Algorithms: "Currently however, compression levels are only supported at the server side, which is aware of the client's capabilities through the incoming Message-Accept-Encoding header." The test cases also mention "the default channel level". A client doesn't know which algorithms the server accepts, so it cannot map a level to an algorithm. The spec allows a channel default *algorithm* on clients, and levels only on servers. Suggested correction: "A default compression algorithm (client) or compression level (server) MAY be specified when the channel or server is created." This also fixes the "specified for during" typo.
- **Evidence:** grpc `doc/compression.md`, "Intent", "Compression Levels and Algorithms", and "Test cases" item 1.
- **Spec:** Core RPC Semantics: Configuration and Precedence

### [medium] doc/keepalive.md server default for PERMIT_WITHOUT_CALLS conflicts with gRFC A9

- **Item:** audit (transports); related: TRANSPORT-3 (open)
- **Summary:** The defaults table says the server's `GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS` is 0, so C++ servers don't ping idle connections. gRFC A9 says server keepalive runs whether or not there are RPCs.
- **Description:** Defaults Values: "GRPC_ARG_KEEPALIVE_PERMIT_WITHOUT_CALLS|0 (false)|0 (false)". This correctly describes the current C++ server default, but A9 says server keepalives "should take place independent of whether there are outstanding RPCs", and Java and Go servers ping idle connections. The spec follows A9 ("the server sends keepalive PINGs whether or not the connection has outstanding RPCs"). If TRANSPORT-3 is decided as recommended (fix the C++ default), change the server column to `1 (true)` when the C++ fix lands. Until then the table is accurate for C++ and could add a note that this conflicts with A9.
- **Evidence:** grpc `doc/keepalive.md`, "Defaults Values" table; grpc-proposal `A9-server-side-conn-mgt.md`.
- **Spec:** HTTP/2 Server Transport: Keepalive

### [medium] gRFC A6 and service_config.proto disagree on status code name format

- **Item:** audit (rlsretry); SERVICE_CONFIG-5 (resolved: integer or exact upper-case name)
- **Summary:** gRFC A6 requires case-insensitive status code names in `retryableStatusCodes`/`nonFatalStatusCodes`, while `service_config.proto` declares them as `repeated google.rpc.Code`, whose proto3 JSON form accepts only exact upper-case names (or integers).
- **Description:** A6: "the integer form or the case-insensitive string form (eg. [14], [\"UNAVAILABLE\"] or [\"unavailable\"])". grpc-proto: `repeated google.rpc.Code retryable_status_codes = 5;` and `repeated google.rpc.Code non_fatal_status_codes = 3;`. A config that follows A6 (`"unavailable"`) is rejected by a proto3 JSON parser. No implementation accepts lower-case names: Java and Go accept an integer or an exact upper-case name, and C++ accepts only exact upper-case names. The spec currently follows A6 (pending SERVICE_CONFIG-5). If SERVICE_CONFIG-5 is resolved as recommended (option b), correct A6 to "the integer form or the exact upper-case name (proto3 JSON)"; otherwise add a comment to the proto noting the case-insensitive extension.
- **Evidence:** grpc-proposal `A6-client-retries.md` (master 4125fbd), "Validation of retryPolicy" (item 4) and "Validation of hedgingPolicy" (item 3); grpc-proto `grpc/service_config/service_config.proto` (`RetryPolicy.retryable_status_codes`, `HedgingPolicy.non_fatal_status_codes`).
- **Spec:** Service Config: Format; Retries and Hedging: Fields and Validation
- **Fix:** change A6 to "the integer form or the exact upper-case name (proto3 JSON enum mapping), e.g. [14] or [\"UNAVAILABLE\"]", for both `retryableStatusCodes` and `nonFatalStatusCodes`.

### [medium] gRFC A40 CSDS example marks valid resources in a NACKed response as NACKED

- **Item:** audit (xdscore)
- **Summary:** A40's "ADS Parsing Logic Update" example shows endpoint A, which parsed fine, as NACKED with the old version after a response that failed only on endpoint B.
- **Description:** The example: "EDS -> {A, B}, version 2 / gRPC -> NACK, Failed to parse endpoint B / CSDS -> [ {Endpoint A, NACK, version 1, rejected version 2, …}, {Endpoint B, NACK, …} …]". The surrounding text also says to attach the error "to all resources in the ADS update including itself". gRFC A46 made NACKs per resource: valid resources in a NACKed response are accepted. All implementations show them as ACKED with the new version and no `error_state`, and the spec does the same. Suggested correction: in the example, show A as `{Endpoint A, ACK, version 2}`, and add a note that A46 superseded the "attach to all resources" rule.
- **Evidence:** grpc-proposal `A40-csds-support.md` (master 4125fbd), "ADS Parsing Logic Update: Continue After First Error".
- **Spec:** Client Status Discovery Service (CSDS): `error_state`; XdsClient: Processing a response

### [medium] gRFC A76 prose and pseudocode disagree for a present but empty hash header

- **Item:** audit (lbpolb)
- **Summary:** A76's prose covers only a header with a non-empty value (hash it) and a header with no value (random hash). Its pseudocode, and every implementation, hash the empty string when the header is present but empty.
- **Description:** "If `request_hash_header` is not empty, and the header has a non-empty value, then the request hash key will be set to this value. … If `request_hash_header` is not empty, and the request has no value associated with the header, then the picker will generate a random hash for the request." A present but empty value fits neither rule, and "no value associated" can be read as including it. The pseudocode checks only `header != null` before `ComputeHash(header)`, so an empty value is hashed. All implementations do that, and the spec uses a random hash only when the header is absent. Suggested correction: "If … the header is present (even with an empty value), the request hash key is set to its value … If the request does not contain the header, the picker generates a random hash."
- **Evidence:** grpc-proposal `A76-ring-hash-improvements.md` (master 4125fbd), "Explicitly setting the request hash key".
- **Spec:** `ring_hash` LB Policy: Picker Implementation

### [medium] gRFC A29 selects the LDS transport socket by name

- **Item:** audit (xdsfilters); related: XDS_CDS-3 (open)
- **Summary:** A29 says an LDS update is NACKed if a `transport_socket` *name* isn't `envoy.transport_sockets.tls`. Envoy chooses the extension by `typed_config` type and `name` is deprecated for that use.
- **Description:** "As part of validating all LDS updates, if a `transport_socket` name is not `envoy.transport_sockets.tls` i.e. something we don't recognize, gRPC will NACK an LDS update." Java and Go follow this and NACK on the name; C++ ignores the name and uses only the `typed_config` type, and so does the spec ("its `typed_config` … MUST be `DownstreamTlsContext`; any other type → NACK"). A control plane that sets a different name, or none, gets different results in different languages. Both options considered in XDS_CDS-3 that ignore the name ((a) and the recommended (b)) need A29 changed to: "if the `transport_socket`'s `typed_config` is not a `DownstreamTlsContext`, gRPC will NACK". The same change applies to the CDS side.
- **Evidence:** grpc-proposal `A29-xds-tls-security.md` (master 4125fbd), "LDS for Server Side Security".
- **Spec:** xDS Security: Server Side: `DownstreamTlsContext`; xDS Security: Locating the TLS Context

### [low] doc/PROTOCOL-HTTP2.md suggests 8 KiB default header size limits

- **Item:** audit (wire); spec change SERVER-2
- **Summary:** The doc suggests an 8 KiB default for request and response header lists. The spec no longer names a default.
- **Description:** "Servers may limit the size of **Request-Headers**, with a default of 8 KiB suggested." and "Clients may limit the size of **Response-Headers**, **Trailers**, and **Trailers-Only**, with a default of 8 KiB each suggested." The spec (SERVER-2) removed specific defaults and says only that implementations SHOULD provide a safe default limit, chosen by the implementation. Suggested correction: drop the "with a default of 8 KiB suggested" clauses, or replace them with "implementations SHOULD provide a safe default".
- **Evidence:** grpc `doc/PROTOCOL-HTTP2.md`, "Requests" (Request-Headers size) and "Responses" (Response-Headers/Trailers size).
- **Spec:** gRPC over HTTP/2: Header list size

### [low] gRFC A113 header says "In Review" with no implementations

- **Item:** audit (lbpola, xdslbpol); related: PICK_FIRST-1
- **Summary:** A113 was merged on 2026-02-18 (8699014) and is implemented in Java and Go (on by default) and C++ (off by default), but its header is still a draft.
- **Description:** Header: "Status: In Review", "Implemented in: \<language, ...\>", "Last updated: Jan 26, 2026". Suggested correction: set the status to the merged state, "Implemented in: Java, Go, C++ (behind `GRPC_EXPERIMENTAL_PF_WEIGHTED_SHUFFLING`, default off)", and update the date.
- **Evidence:** grpc-proposal `A113-pick-first-weighted-shuffling.md` (master 4125fbd), header.
- **Spec:** `pick_first` LB Policy: Address List Processing
- **Also:** A113's normalization pseudocode doesn't say the per-locality `weight_sum` must be computed without uint32 overflow (sums aren't validated to fit in uint32); it could say sums are computed in 64 bits.

### [low] gRFC A114 header says "In review" with no implementations

- **Item:** audit (lbpola); related: WRR-1
- **Summary:** A114 was merged on 2026-05-12 (93180dc) and C++ implements it, but the header still says "In review" and lists no implementations.
- **Description:** Header: "Status: In review", "Implemented in:" (empty). C++ implements `metricNamesForComputingUtilization`, and Java has it behind `GRPC_EXPERIMENTAL_WRR_CUSTOM_METRICS` (default false). Suggested correction: update the status and "Implemented in: C++, Java (behind `GRPC_EXPERIMENTAL_WRR_CUSTOM_METRICS`)".
- **Evidence:** grpc-proposal `A114-wrr-metric-names-for-computing-utilization.md` (master 4125fbd), header.
- **Spec:** `weighted_round_robin` LB Policy: Features › Weight Formula

### [low] gRFC A68 header says "Draft" and "PoC in Go"

- **Item:** audit (lbpola)
- **Summary:** A68 (random subsetting) was merged and ships in Java and Go, but its header still says it is a draft with only a Go proof of concept.
- **Description:** Header: "Status: Draft", "Implemented in: PoC in Go", "Last updated: 2024-04-15". The gRFC was merged in 12d272d (2024-08-19) and later updated to mark the policy experimental (2405799, 2025-12-12). Suggested correction: update the status and "Implemented in: Java, Go".
- **Evidence:** grpc-proposal `A68-random-subsetting.md` (master 4125fbd), header.
- **Spec:** `random_subsetting` LB Policy: Overview

### [low] gRFC A91 header says "In Review" with no implementations

- **Item:** audit (lbpolb, obsa); related: METRICS-5
- **Summary:** A91 (outlier detection metrics) was merged on 2025-07-08 (4f833c5) and C++ and Go emit its metrics, but the header still says "In Review".
- **Description:** Header: "Status: In Review", "Implemented in:" (empty), "Last updated: 2025-03-05". Suggested correction: update the status and "Implemented in: C++, Go".
- **Evidence:** grpc-proposal `A91-outlier-detection-metrics.md` (master 4125fbd), header.
- **Spec:** Metric Catalog: Outlier Detection LB Policy Metrics (incorporated by METRICS-5)
- **Also:** A91 does not say which `unenforced_reason` to report when both the enforcement-percentage check fails and the max-ejection limit is reached (C++ and Go differ; the spec allows either).

### [low] gRFC A80 header says "In Review"

- **Item:** audit (obsa); related: METRICS-6
- **Summary:** A80 (TCP telemetry) was merged on 2026-06-11 (be9a5da), but the header still says "In Review".
- **Description:** Header: "Status: In Review", "Implemented in: C-Core", "Last updated: 2025-12-16". Suggested correction: update the status and date.
- **Evidence:** grpc-proposal `A80-tcp-telemetry.md` (master 4125fbd), header.
- **Spec:** Metric Catalog (A80 metrics not yet listed; METRICS-6)

### [low] gRFC A16 precedence example separates patterns with `;`

- **Item:** audit (obsb)
- **Summary:** A16's precedence example joins two patterns with `;`, but the corrected ABNF (#571) separates patterns with `,` and uses `;` only inside `{h;m}`.
- **Description:** "Control Interface": "`GRPC_BINARY_LOG_FILTER=Foo/*{h};Foo/Bar{m:256}`". The grammar is `Config-String -> [ Pattern *( "," Pattern ) ]`, and the other examples use `,` (e.g. "`GRPC_BINARY_LOG_FILTER=Foo/*,Foo/Bar{m:256}`"). As written, the example is an invalid config string. Suggested correction: `GRPC_BINARY_LOG_FILTER=Foo/*{h},Foo/Bar{m:256}`.
- **Evidence:** grpc-proposal `A16-binary-logging.md` (master 4125fbd), "Control Interface" (precedence example).
- **Spec:** Binary Logging: Precedence

### [low] gRFC A28 header matcher list omits `contains_match` and `string_match`

- **Item:** audit (xdsres)
- **Summary:** A28's RDS validation lists the supported `header_match_specifier` options without `contains_match` or `string_match`, which gRPC supports.
- **Description:** "Options supported: exact\_match, safe\_regex\_match, range\_match, present\_match, prefix\_match, suffix\_match". gRFC A63 added `string_match` and lists `contains_match` among the legacy fields gRPC "will continue to support", and the spec lists both. An implementer reading only A28 might NACK them. Suggested correction: add `contains_match` and `string_match` (per A63) to the list, or add a pointer to A63.
- **Evidence:** grpc-proposal `A28-xds-traffic-splitting-and-routing.md` (master 4125fbd), "Response validation" (route `headers`).
- **Spec:** Common Types: `HeaderMatcher` › Fields

### [low] gRFC A102 misspells `trusted_xds_server`

- **Item:** audit (xdscore)
- **Summary:** A102 calls the server feature "`trused_xds_server`".
- **Description:** "will rely on the `trused_xds_server` server feature that was added to the …". The bootstrap server feature is `trusted_xds_server`. A literal copy would never match. Suggested correction: `trusted_xds_server`.
- **Evidence:** grpc-proposal `A102-xds-grpc-service.md` (master 4125fbd).
- **Spec:** Bootstrap: Server Features

### [low] gRFC A72 example span status description uses a comma

- **Item:** TRACING-3 (resolved)
- **Summary:** A72's example status description "UNAVAILABLE, unable to resolve host" doesn't match what implementations write or what the spec now requires.
- **Description:** The spec now requires the description `<CODE>: <message>` (just `<CODE>` if the message is empty), matching C++ and Java. A72's example uses a comma. Suggested correction: "UNAVAILABLE: unable to resolve host".
- **Evidence:** grpc-proposal `A72-open-telemetry-tracing.md` (master 4125fbd), tracing information example.
- **Spec:** Tracing: Span status

### [low] gRFC A105 queuing guidance does not say it applies only with connection scaling

- **Item:** TRANSPORT-8 (resolved)
- **Summary:** A105 says transports "should no longer need to handle this queuing", but that is only true where the subchannel implements connection scaling.
- **Description:** The spec now limits the transport's no-queue / fail-UNAVAILABLE rule to subchannels doing connection scaling; otherwise the transport holds the RPC. A105 could say the same.
- **Evidence:** grpc-proposal `A105-max_concurrent_streams-connection-scaling.md` (master 4125fbd), "Picking a Connection for Each RPC".
- **Spec:** HTTP/2 Client Transport: RPCs Beyond the Limit; Transport Model: Stream Limits

### [low] gRFC A29 does not describe the deprecated CertificateProviderInstance fallbacks

- **Item:** XDS_SECURITY-5
- **Summary:** All implementations accept two deprecated `CertificateProviderInstance` fields as fallbacks, but A29 says gRPC supports only `CertificateProviderPluginInstance`.
- **Description:** gRFC A29 says: "gRPC supports only one of them and that is the `CertificateProviderPluginInstance` proto." C++, Java, and Go all also accept `CommonTlsContext.tls_certificate_certificate_provider_instance` (identity) and `CombinedCertificateValidationContext.validation_context_certificate_provider_instance` (CA). Each is used only when the corresponding new field (`tls_certificate_provider_instance` / `ca_certificate_provider_instance`) is unset, and its instance name is validated against the bootstrap. Java's code notes this is "for backward compatibility with Istio". The spec now describes these fallbacks, and A29 should too (or be amended to say that they are accepted).
- **Evidence:** https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_tls_context_parser.cc#L185-L206, https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_tls_context_parser.cc#L231-L244, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L534-L573, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L401-L480; gRFC A29 (A29-xds-tls-security.md)
- **Spec:** xDS Security: `CommonTlsContext` Validation

### [low] gRFC A50 does not require a positive `interval`

- **Item:** OUTLIER_DETECTION-4 (resolved)
- **Summary:** A50 requires the outlier-detection durations to be non-negative but allows an `interval` of 0, which makes the ejection timer spin.
- **Description:** A50 "Validation": `interval`, `base_ejection_time`, and `max_ejection_time` "must have non-negative values". With `interval` 0, C++ and Go busy-loop and Java throws. The spec now requires `interval` to be greater than zero, as Envoy does (`duration.gt {}`). Suggested correction: add that `interval` must be greater than zero.
- **Evidence:** grpc-proposal `A50-xds-outlier-detection.md` (master 4125fbd), "Validation".
- **Spec:** `outlier_detection` LB Policy: Validation

### [low] gRFC A3 header status is "Draft"

- **Item:** GRFC-STATUS
- **Summary:** A3 (Channel Tracing) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: Draft", "Implemented in: N/A", "Last updated: 2018-07-01". The gRFC was added to master in d020609 2017-03-09. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A3-channel-tracing.md` (master 4125fbd), header.
- **Spec:** Channelz (Channelz: Channel Trace)

### [low] gRFC A10 header status is "Draft"

- **Item:** GRFC-STATUS
- **Summary:** A10 (Special case localhost and ip literals for service-config and grpclb-in-DNS) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: Draft", "Implemented in: none currently, suited for all languages", "Last updated: 2018-10-29". The gRFC was added to master in ae1968d 2018-04-25. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A10-avoid-grpclb-and-service-config-for-localhost-and-ip-literals.md` (master 4125fbd), header.
- **Spec:** Name Resolution (`dns`, Service Config in DNS)

### [low] gRFC A17 header status is "Draft"

- **Item:** GRFC-STATUS
- **Summary:** A17 (Client-Side Health Checking) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: Draft", "Implemented in:", "Last updated: 2018-08-27". The gRFC was added to master in 8b40b2b 2018-08-27. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A17-client-side-health-checking.md` (master 4125fbd), header.
- **Spec:** Client-Side Health Checking; Health Service; Service Config (`healthCheckConfig`); Channelz

### [low] gRFC A21 header status is "Draft"

- **Item:** GRFC-STATUS
- **Summary:** A21 (Service Config Error Handling) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: Draft", "Implemented in:", "Last updated: 02-19-2019". The gRFC was added to master in ff8c3cf 2019-03-05. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A21-service-config-error-handling.md` (master 4125fbd), header.
- **Spec:** Service Config (Service Config: Validation and Error Handling); Name Resolution (Name Resolution: Channel Handling of Resolver Results, Name Resolution: Resolver Errors); Channel

### [low] gRFC A24 header status is "In Review"

- **Item:** GRFC-STATUS
- **Summary:** A24 (Load Balancing Policy Configuration) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: In Review", "Implemented in: C-core", "Last updated: 2018-12-05". The gRFC was added to master in 84c4be1 2018-12-05. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A24-lb-policy-config.md` (master 4125fbd), header.
- **Spec:** Service Config (`loadBalancingConfig`, `loadBalancingPolicy` (deprecated)); Load Balancing (Load Balancing: LB Policy Registry and Configuration); Name Resolution (LB Policy Selection)

### [low] gRFC A53 header status is "In Review"

- **Item:** GRFC-STATUS
- **Summary:** A53 (A53: Option for Ignoring xDS Resource Deletion) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: In Review", "Implemented in: C-core, Java", "Last updated: 2022-05-19". The gRFC was added to master in cd5d024 2022-06-03. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A53-xds-ignore-resource-deletion.md` (master 4125fbd), header.
- **Spec:** Bootstrap (Bootstrap: Server Features)

### [low] gRFC A56 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A56 (A56: `priority_experimental` LB policy) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: C-core, Java, Go, Node", "Last updated: 2025-08-18". The gRFC was added to master in 6da6b41 2022-12-06. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A56-priority-lb-policy.md` (master 4125fbd), header.
- **Spec:** `priority`; Load Balancing (Hierarchical Address Paths); xDS LB Policies

### [low] gRFC A57 header status is "Draft"

- **Item:** GRFC-STATUS
- **Summary:** A57 (A57: XdsClient Failure Mode Behavior) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: Draft", "Implemented in:", "Last updated: 2022-10-26". The gRFC was added to master in f1ef153 2022-11-15. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A57-xds-client-failure-mode-behavior.md` (master 4125fbd), header.
- **Spec:** XdsClient (XdsClient: Error Handling)

### [low] gRFC A59 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A59 (A59: gRPC Audit Logging) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: In Review {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: C++ and Go", "Last updated: 2023-10-02". The gRFC was added to master in 257a7aa 2023-10-02. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A59-audit-logging.md` (master 4125fbd), header.
- **Spec:** Authorization (Authorization: Audit Logging); xDS HTTP Filters (Audit Logging Configuration)

### [low] gRFC A60 header status is "In Review"

- **Item:** GRFC-STATUS
- **Summary:** A60 (A60: xDS-Based Stateful Session Affinity for Weighted Clusters) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: In Review", "Implemented in: \<language, ...\>", "Last updated: 2023-03-19". The gRFC was added to master in e38db65 2023-04-27. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A60-xds-stateful-session-affinity-weighted-clusters.md` (master 4125fbd), header.
- **Spec:** xDS HTTP Filters (xDS HTTP Filters: Stateful Session Affinity); Client Data Plane (Cluster selection, Cluster references and two-phase removal); RouteConfiguration

### [low] gRFC A62 header status is "Draft"

- **Item:** GRFC-STATUS
- **Summary:** A62 (A62: `pick_first`: sticky TRANSIENT_FAILURE and address order randomization) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: Draft", "Implemented in:", "Last updated: 2023-04-20". The gRFC was added to master in 15c94db 2023-05-17. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A62-pick-first.md` (master 4125fbd), header.
- **Spec:** `pick_first`; Load Balancing; Name Resolution; Channel

### [low] gRFC A63 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A63 (A63: xDS StringMatcher in Header Matching) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2023-05-03". The gRFC was added to master in 20f475f 2023-05-18. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A63-xds-string-matcher-in-header-matching.md` (master 4125fbd), header.
- **Spec:** Common Types (`StringMatcher`, `HeaderMatcher`); RouteConfiguration

### [low] gRFC A65 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A65 (A65: mTLS Credentials in xDS Bootstrap File) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2023-05-24". The gRFC was added to master in e027a56 2023-06-09. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A65-xds-mtls-creds-in-bootstrap.md` (master 4125fbd), header.
- **Spec:** Bootstrap (XdsServer Object); xDS Security

### [low] gRFC A74 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A74 (A74: xDS Config Tears) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2025-03-11". The gRFC was added to master in 9240c4b 2024-02-15. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A74-xds-config-tears.md` (master 4125fbd), header.
- **Spec:** Client Data Plane (Client Data Plane: XdsDependencyManager, Client Data Plane: XdsConfig); xDS LB Policies (`cds`)

### [low] gRFC A75 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A75 (A75: xDS Aggregate Cluster Behavior Fixes) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: C-core", "Last updated: 2024-02-28". The gRFC was added to master in 52eb931 2024-03-04. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A75-xds-aggregate-cluster-behavior-fixes.md` (master 4125fbd), header.
- **Spec:** Client Data Plane (Aggregate cluster graph); xDS LB Policies (Aggregate cluster, Child config for an aggregate cluster); Cluster (Aggregate Clusters); xDS HTTP Filters

### [low] gRFC A76 header status is "Draft"

- **Item:** GRFC-STATUS
- **Summary:** A76 (A76: Improvements to the Ring Hash LB Policy) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: Draft", "Implemented in: C-core", "Last updated: 2024-12-19". The gRFC was added to master in b64e6d3 2024-12-23. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A76-ring-hash-improvements.md` (master 4125fbd), header.
- **Spec:** `ring_hash`; ClusterLoadAssignment and LbEndpointCollection (Endpoint Metadata); Client Data Plane (Request hash)

### [low] gRFC A78 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A78 (A78: gRPC OTel Metrics for WRR, Pick First, and XdsClient) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2025-07-01". The gRFC was added to master in b9e9a34 2024-04-11. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A78-grpc-metrics-wrr-pf-xds.md` (master 4125fbd), header.
- **Spec:** Metric Catalog (Metric Catalog: Weighted Round Robin LB Policy Metrics, Metric Catalog: XdsClient Metrics); `weighted_round_robin` (Metrics); XdsClient (XdsClient: Metrics); `weighted_target`

### [low] gRFC A81 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A81 (A81: xDS Authority Rewriting) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2024-07-19". The gRFC was added to master in 2eded1b 2024-08-16. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A81-xds-authority-rewriting.md` (master 4125fbd), header.
- **Spec:** Client Data Plane (Authority rewriting); xDS LB Policies (Authority rewriting); Channel (Authority Overrides); Load Balancing (Authority Override); TLS (TLS: Per-RPC Authority Verification); Security; Bootstrap (Bootstrap: Server Features)

### [low] gRFC A82 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A82 (A82: xDS System Root Certificates) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2024-07-08". The gRFC was added to master in 62a1b7c 2024-07-09. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A82-xds-system-root-certs.md` (master 4125fbd), header.
- **Spec:** xDS Security (`UpstreamTlsContext` Validation, xDS Security: `CommonTlsContext` Validation)

### [low] gRFC A83 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A83 (A83: xDS GCP Authentication Filter) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2025-09-19". The gRFC was added to master in b638bb0 2024-10-25. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A83-xds-gcp-authn-filter.md` (master 4125fbd), header.
- **Spec:** xDS HTTP Filters (xDS HTTP Filters: GCP Authentication); Call Credentials (Call Credentials: GCP Service Account Identity Credentials); Common Types (Metadata)

### [low] gRFC A85 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A85 (A85: Changes to xDS LRS Custom Metrics Support) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2024-09-27". The gRFC was added to master in 1658b6e 2024-11-19. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A85-lrs-custom-metrics-changes.md` (master 4125fbd), header.
- **Spec:** Load Reporting (LRS) (Load Reporting (LRS): Backend Metrics from ORCA); Cluster

### [low] gRFC A86 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A86 (A86: xDS-Based HTTP CONNECT) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2024-10-25". The gRFC was added to master in 990daca 2024-11-19. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A86-xds-http-connect.md` (master 4125fbd), header.
- **Spec:** Cluster (Transport Socket); ClusterLoadAssignment and LbEndpointCollection; xDS Security (xDS Security: HTTP CONNECT and TLS); HTTP CONNECT Proxy Support (HTTP CONNECT Proxy Support: xDS-Configured Proxies)

### [low] gRFC A87 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A87 (A87: mTLS SPIFFE Support) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2025-03-31". The gRFC was added to master in 413b966 2025-04-01. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A87-mtls-spiffe-support.md` (master 4125fbd), header.
- **Spec:** TLS (TLS: SPIFFE Trust Bundle Map Verification); xDS Security; Bootstrap (Certificate Provider Instances)

### [low] gRFC A88 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A88 (A88: xDS Data Error Handling) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2025-03-11". The gRFC was added to master in 341672b 2025-03-27. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A88-xds-data-error-handling.md` (master 4125fbd), header.
- **Spec:** XdsClient (XdsClient: Watcher API–XdsClient: Error Handling); Bootstrap (Bootstrap: Server Features); Client Data Plane; xDS-Enabled Servers; Client Status Discovery Service (CSDS); Metric Catalog

### [low] gRFC A95 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A95 (A95: xDS Endpoint Fallback) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2025-06-16". The gRFC was added to master in 910893b 2026-02-12. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A95-xds-endpoint-fallback.md` (master 4125fbd), header.
- **Spec:** XdsClient (XdsClient: Fallback); Bootstrap; ClusterLoadAssignment and LbEndpointCollection (LbEndpointCollection (LEDS List Collections)); Client Data Plane

### [low] gRFC A97 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A97 (A97: xDS JWT Call Credentials) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2025-06-05". The gRFC was added to master in 0323c30 2025-06-16. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A97-xds-jwt-call-creds.md` (master 4125fbd), header.
- **Spec:** Call Credentials (Call Credentials: JWT Token File Credentials); Bootstrap (XdsServer Object); XdsClient

### [low] gRFC A101 header status is "Draft"

- **Item:** GRFC-STATUS
- **Summary:** A101 (A101: xDS-Based setting SNI and server certificate SAN validation) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: Draft", "Implemented in:", "Last updated: 2025-07-28". The gRFC was added to master in 517c416 2025-09-22. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A101-SNI-setting-and-SNI-SAN-validation.md` (master 4125fbd), header.
- **Spec:** xDS Security (SNI Selection, xDS Security: Server Identity Verification); TLS (TLS: Server Name Indication (SNI)); Cluster

### [low] gRFC A102 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A102 (A102: xDS `GrpcService` Support and Header Representations) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2026-09-09". The gRFC was added to master in 0bd7e9f 2026-09-09. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A102-xds-grpc-service.md` (master 4125fbd), header.
- **Spec:** Bootstrap (Bootstrap: Allowed gRPC Service Object)

### [low] gRFC A103 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A103 (A103: xDS Composite Filter) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2026-03-02". The gRFC was added to master in 9cabee3 2026-02-27. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A103-xds-composite-filter.md` (master 4125fbd), header.
- **Spec:** Appendix D. gRFC Traceability Matrix

### [low] gRFC A105 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A105 (A105: MAX_CONCURRENT_STREAMS Connection Scaling) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft, In Review, Ready for Implementation, Implemented}", "Implemented in: \<language, ...\>", "Last updated: 2026-01-30". The gRFC was added to master in 6a8163b 2026-01-30. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A105-max_concurrent_streams-connection-scaling.md` (master 4125fbd), header.
- **Spec:** Subchannels and Connections (Subchannels and Connections: MAX_CONCURRENT_STREAMS Connection Scaling); Service Config (`connectionScaling`); HTTP/2 Client Transport (HTTP/2 Client Transport: Stream Limits); Per-call Configuration and Call Flow; Channel; `pick_first`; Cluster (Upstream Connection Options); xDS LB Policies (Connection scaling); Channelz

### [low] gRFC A110 header status is "In Review"

- **Item:** GRFC-STATUS
- **Summary:** A110 (A110: Child Channel Options) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: In Review", "Implemented in: \<language, ...\>", "Last updated: 2026-03-18". The gRFC was added to master in 83e2878 2026-08-05. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A110-child-channel-plugins.md` (master 4125fbd), header.
- **Spec:** Appendix D. gRFC Traceability Matrix

### [low] gRFC A115 header status is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** A115 (A115: disable Priority LB policy child policy retention cache) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: {Draft}", "Implemented in: C-core, Java, Go, Node", "Last updated: 2026-03-17". The gRFC was added to master in db3c8f2 2026-03-30. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `A115-remove-priority-lb-child-policy-cache.md` (master 4125fbd), header.
- **Spec:** `priority` (Child Lifetime)

### [low] gRFC G1 header status is "Draft"

- **Item:** GRFC-STATUS
- **Summary:** G1 (True Binary Metadata) is merged on grpc-proposal master, but its header Status is not a final status.
- **Description:** Header: "Status: Draft", "Implemented in: n/a", "Last updated: 3/29/17". The gRFC was added to master in 6011282 2017-03-29. Every merged gRFC should carry a final status. Suggested correction: set the Status to the merged state and fill in "Implemented in" and "Last updated".
- **Evidence:** grpc-proposal `G1-true-binary-metadata.md` (master 4125fbd), header.
- **Spec:** True Binary Metadata

### [low] L-series gRFC headers have non-final statuses

- **Item:** GRFC-STATUS
- **Summary:** 50 merged language-specific (L) gRFCs on grpc-proposal master still have a draft, in-review, proposed, or template-placeholder Status.
- **Description:** Every merged gRFC should carry a final status. Verbatim Status headers:
  - `L1-cpp-stream-coalescing.md`: "Status: Draft"
  - `L24-cpp-extensible-api.md`: "Status: Draft"
  - `L25-cpp-expose-buffer-reader-writer.md`: "Status: Draft"
  - `L26-cpp-raw-codegen-api.md`: "Status: Draft"
  - `L29-cpp-opencensus-filter.md`: "Status: In Review"
  - `L30-cpp-control-max-threads-in-SyncServer.md`: "Status: In Review"
  - `L32-node-channel-API.md`: "Status: Draft"
  - `L33-node-checkServerIdentity-callback.md`: "Status: Draft"
  - `L34-cpp-opencensus-span-api.md`: "Status: Draft"
  - `L35-node-getAuthContext.md`: "Status: Draft"
  - `L39-core-remove-grpc-use-signal.md`: "Status: Proposed"
  - `L40-node-call-invocation-transformer.md`: "Status: Draft"
  - `L41-node-server-async-bind.md`: "Status: Draft"
  - `L42-python-metadata-flags.md`: "Status: In Review"
  - `L43-node-type-info.md`: "Status: Draft"
  - `L44-python-rich-status.md`: "Status: Draft"
  - `L45-cpp-server-load-reporting.md`: "Status: Draft"
  - `L46-python-compression-api.md`: "Status: Draft"
  - `L48-node-metadata-options.md`: "Status: Draft"
  - `L62-core-call-credential-security-level.md`: "Status: In review"
  - `L63-core-call-credentials-debug-string.md`: "Status: In review"
  - `L67-cpp-callback-api.md`: "Status: Proposed"
  - `L72-core-google_default_credentials-extension.md`: "Status: Draft"
  - `L77-core-cpp-third-party-identity-support-for-call-credentials.md`: "Status: Draft"
  - `L78-python-rich-server-context.md`: "Status: Draft"
  - `L80-cpp-async-response-reader-destruction.md`: "Status: Draft"
  - `L84-cpp-call-failed-before-recv-message.md`: "Status: In Review"
  - `L86-aspect-based-python-bazel-rules.md`: "Status: Draft"
  - `L88-cpp-absl-status-conversions.md`: "Status: {In Review}"
  - `L89-core-remove-grpc-insecure-channel-creation-api.md`: "Status: {In Review}"
  - `L91-improved-directory-support-for-python-bazel-rules.md`: "Status: Draft"
  - `L95-python-reflection-client.md`: "Status: In Review"
  - `L99-core-eliminate-corking.md`: "Status: In Review"
  - `L100-core-narrow-call-details.md`: "Status: In Review"
  - `L101-core-remove-grpc_register_plugin.md`: "Status: In Review"
  - `L104-core-ban-recv-with-send-status.md`: "Status: In Review"
  - `L105-python-expose-new-error-types.md`: "Status: In Review"
  - `L106-node-heath-check-library.md`: "Status: In Review"
  - `L107-node-noop-start.md`: "Status: In Review"
  - `L108-node-grpc-reflection-library.md`: "Status: In Review"
  - `L109-node-server-unbind.md`: "Status: In Review"
  - `L110-csharp-nullable-reference-types.md`: "Status: Draft"
  - `L111-node-server-drain.md`: "Status: In Review"
  - `L112-node-server-interceptors.md`: "Status: In Review"
  - `L114-node-server-connection-injection.md`: "Status: In Review"
  - `L115-core-refactor-generic-service-stub.md`: "Status: Draft"
  - `L116-core-loosen-max-pings-without-data.md`: "Status: Draft"
  - `L118-core-remove-cronet.md`: "Status: Draft"
  - `L119-python-add-typing-to-sync-api.md`: "Status: Draft"
  - `L126-core-add-alts-google-call-credentials.md`: "Status: In Review"
  Suggested correction: set each Status to the merged state (and fill in "Implemented in" and "Last updated" where empty).
- **Evidence:** grpc-proposal `L*.md` (master 4125fbd), headers.
- **Spec:** Not applicable (language-specific gRFCs are not spec sources).

### [low] grpc-proto `service_config.proto` lacks A114's `metric_names_for_computing_utilization`

- **Item:** WRR-1 (resolved)
- **Summary:** `WeightedRoundRobinLbConfig` has no `metric_names_for_computing_utilization` field, although gRFC A114 adds it as field 7 and the spec now incorporates it.
- **Description:** A114 defines `repeated string metric_names_for_computing_utilization = 7;` in the WRR LB config. grpc-proto master (8133308) does not have it. Suggested correction: add the field with A114's comment.
- **Evidence:** grpc-proto `grpc/service_config/service_config.proto`, `WeightedRoundRobinLbConfig`.
- **Spec:** `weighted_round_robin` LB Policy: Configuration

### [low] gRFC A114 does not say whether unsupported metric names are invalid

- **Item:** WRR-1 (resolved)
- **Summary:** A114 lists the supported metric names but doesn't say what happens when `metric_names_for_computing_utilization` contains an unsupported name.
- **Description:** C++ rejects the config; Java (behind its flag) and the spec treat this as implementation-defined. Suggested correction: state whether such a config is invalid or the name is ignored.
- **Evidence:** grpc-proposal `A114-wrr-metric-names-for-computing-utilization.md` (master 4125fbd).
- **Spec:** `weighted_round_robin` LB Policy: Custom Utilization Metrics

### [low] gRFC A50 does not say that already-ejected addresses are skipped

- **Item:** OUTLIER_DETECTION-1 (resolved)
- **Summary:** A50's ejection algorithms don't say to skip addresses that are already ejected, so an address can be ejected again (all three implementations do this in some form).
- **Description:** The spec now excludes ejected endpoints from the candidates, `minimum_hosts`, and the statistics, as Envoy does. Suggested correction: add the same rule to both algorithms in A50 "Ejection".
- **Evidence:** grpc-proposal `A50-xds-outlier-detection.md` (master 4125fbd), success-rate and failure-percentage algorithms.
- **Spec:** `outlier_detection` LB Policy: Success-Rate Algorithm / Failure-Percentage Algorithm
