# Documentation bugs

Errors and stale text in gRFCs (grpc-proposal), `grpc/doc`, `grpc.io`, and grpc-proto found while writing and reviewing the gRPC spec in this directory, where the spec is believed correct: **85** entries, ordered by severity. Other lists: [Go](bugs_go.md), [Java](bugs_java.md), [C++](bugs_cpp.md).

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

### [medium] grpc.io `guides/retry.md` misstates retry throttling accounting and says disabling retries disables transparent retries

- **Item:** audit (W1-C-013); related: R45
- **Summary:** The grpc.io retry guide says that disabling retries on a channel also disables transparent retries, and describes retry throttling token accounting loosely enough to be wrong.
- **Description:** `content/en/docs/guides/retry.md` says: "You can also disable retries entirely when creating a channel, which disables transparent retries and any configured retry policies." The spec (decision R45) says transparent retries SHOULD still happen when the application disables retries; C++ and Java currently disable them too, which is tracked as implementation bugs, so the guide should change once those are fixed. The throttling paragraph says: "Failed RPCs decrement the count by 1, successful RPCs increment it by `tokenRatio`. If the `token_count` falls below half of `maxTokens`, retries are paused until the count recovers." Per gRFC A6 and the spec, only failures with a retryable (or non-fatal) status code or a "do not retry" pushback decrement the count, and throttling applies while `token_count` is less than or equal to half of `maxTokens`; a throttled RPC fails with its current status instead of waiting. Suggested correction: say that disabling retries disables configured retries and hedging only, and restate the throttling rules as in A6.
- **Evidence:** grpc.io 81fb52b: `content/en/docs/guides/retry.md` (introduction to retry policies, and the `retryThrottling` paragraph).
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`): Token Accounting; Transparent Retries; Limits and Disabling Retries

### [medium] grpc.io `guides/deadlines.md` says the server fails an expired call with `CANCELLED`

- **Item:** audit (W1-C-015)
- **Summary:** The deadlines guide says a server deals with an expired client deadline "by automatically cancelling a call (`CANCELLED` status)". The status for an expired deadline is `DEADLINE_EXCEEDED`.
- **Description:** `content/en/docs/guides/deadlines.md` says: "A gRPC server deals with this situation by automatically cancelling a call (`CANCELLED` status) once a deadline set by the client has passed." The spec says that when the deadline passes on the server, the server cancels the call and SHOULD send status `DEADLINE_EXCEEDED` (or abort the stream), and the client completes the call with `DEADLINE_EXCEEDED`. The server application does see the call as cancelled, but the status is not `CANCELLED`. Suggested correction: "... by automatically cancelling the call and failing it with `DEADLINE_EXCEEDED` once a deadline set by the client has passed."
- **Evidence:** grpc.io 81fb52b: `content/en/docs/guides/deadlines.md` (section on deadlines on the server).
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`): Deadlines (Communication and Enforcement)

### [medium] `doc/grpc_xds_features.md` contains superseded statements contradicting gRFCs A42, A46, A65, A82, A97, and A113

- **Item:** audit (W1-C-018)
- **Summary:** The prose before the feature table in `doc/grpc_xds_features.md` states xDS limitations that later gRFCs removed.
- **Description:** (1) "This will cause all cluster configurations to be rejected by the client because the xDS protocol currently requires rejecting all resources in a given response" is superseded by gRFC A46 (xDS NACK Semantics Improvement): valid resources in a response are accepted and only the invalid ones are NACKed. (2) "The optional `load_balancing_weight` is always ignored." is superseded: endpoint weights are used by `ring_hash` (gRFC A42) and by weighted shuffling in `pick_first` (gRFC A113). (3) "Initially, only `google_default` channel creds will be supported to authenticate with the xDS server." is stale: the bootstrap supports other channel credentials, including mTLS (gRFC A65) and system root certificates (gRFC A82), and call credentials (gRFC A97). Suggested correction: delete or update these paragraphs; the feature table already lists the gRFCs.
- **Evidence:** grpc 515aaa1743: [doc/grpc_xds_features.md L17-L49](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/doc/grpc_xds_features.md#L17-L49).
- **Spec:** XdsClient (`09-xds/03-xds-client.md`); Bootstrap (`09-xds/02-bootstrap.md`); xDS LB Policies (`09-xds/06-lb-policies.md`)

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

- **Item:** audit (xdsfilters); related: XDS_CDS-3 (resolved: CDS `transport_socket.name` is ignored; LDS text unchanged)
- **Summary:** A29 says an LDS update is NACKed if a `transport_socket` *name* isn't `envoy.transport_sockets.tls`. Envoy chooses the extension by `typed_config` type and `name` is deprecated for that use.
- **Description:** "As part of validating all LDS updates, if a `transport_socket` name is not `envoy.transport_sockets.tls` i.e. something we don't recognize, gRPC will NACK an LDS update." Java and Go follow this and NACK on the name; C++ ignores the name and uses only the `typed_config` type, and so does the spec ("its `typed_config` … MUST be `DownstreamTlsContext`; any other type → NACK"). A control plane that sets a different name, or none, gets different results in different languages. Both options considered in XDS_CDS-3 that ignore the name ((a) and the recommended (b)) need A29 changed to: "if the `transport_socket`'s `typed_config` is not a `DownstreamTlsContext`, gRPC will NACK". The same change applies to the CDS side.
- **Evidence:** grpc-proposal `A29-xds-tls-security.md` (master 4125fbd), "LDS for Server Side Security".
- **Spec:** xDS Security: Server Side: `DownstreamTlsContext`; xDS Security: Locating the TLS Context

### [medium] `doc/PROTOCOL-HTTP2.md` "Idempotency and Retries" section predates gRFC A6

- **Item:** audit (W2-02-011)
- **Summary:** The "Idempotency and Retries" section of `doc/PROTOCOL-HTTP2.md` says "Calls that cannot be proven to have started will not be retried", which, read literally, forbids transparent retries, and it does not describe gRFC A6 retries or hedging.
- **Description:** The section says: "Unless explicitly defined to be, gRPC Calls are not assumed to be idempotent. Specifically: Calls that cannot be proven to have started will not be retried. There is no mechanism for duplicate suppression as it is not necessary. Calls that are marked as idempotent may be sent multiple times." Under gRFC A6 and the spec, calls known not to have reached the server application are retried transparently, and the service config can configure retry and hedging policies for any method. The document also never mentions the `grpc-previous-rpc-attempts` request header or the `grpc-retry-pushback-ms` trailer. Suggested correction: replace the section with a summary of transparent retries and a pointer to gRFC A6, and add the two retry headers to the grammar.
- **Evidence:** grpc 515aaa1743: [doc/PROTOCOL-HTTP2.md L197-L203](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/doc/PROTOCOL-HTTP2.md#L197-L203).
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`): Idempotency and Retries; gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`): Retry-related request headers, Retry pushback, Idempotency and Retries

### [medium] grpc-proto `rls_config.proto` `NameMatcher.names` comment ("first one with a non-empty value") contradicts the RLS key-building rule

- **Item:** audit (W2-09-012)
- **Summary:** The comment on `NameMatcher.names` in `grpc/lookup/v1/rls_config.proto` says "the first one with a non-empty value is used", but the spec and C++, Go, and Java use the first header that is present, even if its value is empty.
- **Description:** The comment reads: "Ordered list of names (headers or query parameter names) that can supply this value; the first one with a non-empty value is used." The spec's key-building pseudocode takes the first name in `names` for which the request has the header, and all three implementations check presence only (C++ `Lookup(...).has_value()`, Go `md.Get(name) != nil`, Java `value != null`). Java's `RlsProtoData.NameMatcher.names()` Javadoc copies the proto wording. Suggested correction: "the first one present in the request is used, even if its value is empty."
- **Evidence:** grpc-proto ffb297a: [rls_config.proto L37-L39](https://github.com/grpc/grpc-proto/blob/ffb297aeea/grpc/lookup/v1/rls_config.proto#L37-L39); grpc-java ed3bf6b76b: [RlsProtoData.java L186](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/rls/src/main/java/io/grpc/rls/RlsProtoData.java#L186), [RlsRequestFactory.java L98-L108](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/rls/src/main/java/io/grpc/rls/RlsRequestFactory.java#L98-L108); grpc 515aaa1743: [rls.cc L917-L926](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/rls/rls.cc#L917-L926); grpc-go cbf30c4130: [builder.go L242-L248](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/balancer/rls/internal/keys/builder.go#L242-L248)
- **Spec:** `rls` LB Policy (`04-client-channel/lb-policies/rls.md`): Key Building

### [medium] `grpc/doc/server-reflection.md` has a dead proto URL and an obsolete service schema, and the grpc-java reflection tutorial shows `grpc_cli` working with only the `v1` service

- **Item:** audit (W2-12-013)
- **Summary:** `doc/server-reflection.md` links to `src/proto/grpc/reflection/v1/reflection.proto` in the grpc repo, which no longer exists, and embeds an obsolete pre-release `service ProtoDescriptorDatabase` schema. The grpc-java reflection tutorial registers only `ProtoReflectionServiceV1` but shows `grpc_cli ls` listing `grpc.reflection.v1alpha.ServerReflection`.
- **Description:** The canonical protos are in grpc-proto (`grpc/reflection/v1/reflection.proto` and `v1alpha`), defining `service ServerReflection { rpc ServerReflectionInfo(...) }`; `doc/server-reflection.md` instead shows `service ProtoDescriptorDatabase { rpc DescriptorDatabaseInfo(...) }`. `grpc_cli` uses the `v1alpha` service, so against a Java server that registers only `ProtoReflectionServiceV1` it does not work, and the tutorial's sample output cannot occur (that server exports `grpc.reflection.v1.ServerReflection`). grpc-go's `reflection/README.md` and package comment also link to the removed grpc-repo proto paths. Suggested correction: link to the grpc-proto files, drop the obsolete schema, and fix the tutorial's registration or output.
- **Evidence:** grpc 515aaa1743: [doc/server-reflection.md L26-L27](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/doc/server-reflection.md#L26-L27), [L131-L133](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/doc/server-reflection.md#L131-L133); grpc-java ed3bf6b76b: `documentation/server-reflection-tutorial.md` (server registration and `grpc_cli ls` output); grpc-go cbf30c4130: `reflection/README.md` L5, `reflection/serverreflection.go` L23.
- **Spec:** Server Reflection (`07-services/02-reflection.md`): Service Definition; Versions

### [medium] `grpc/doc/binary-logging.md` documents a superseded, unimplemented pre-A16 binary logging API

- **Item:** audit (W2-14-018)
- **Summary:** `doc/binary-logging.md` is an obsolete design sketch of a separate binary logging library with explicit per-RPC logging calls (`LogRequestHeaders`, `LogResponseHeaders`, `LogUserData`) and an `rpc_id`. gRFC A16 replaced it with built-in logging controlled by configuration, and the sketched API was never implemented.
- **Description:** The doc says: "The binary logger will be a separate library from gRPC, in each language that we support. The user will need to explicitly call into the library to generate logs." gRFC A16 instead says: "The proposed design is adding binary logging as a built-in functionality in gRPC. ... Turning on binary logging should be a configuration setting and require no code changes." The log entry field is `call_id`, not `rpc_id`. Suggested correction: remove `doc/binary-logging.md` or replace it with a pointer to gRFC A16 and `grpc/binlog/v1/binarylog.proto`.
- **Evidence:** grpc 515aaa1743: [doc/binary-logging.md L1-L59](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/doc/binary-logging.md#L1-L59); grpc-proposal 4125fbd: `A16-binary-logging.md` ("Proposal").
- **Spec:** Binary Logging (`08-observability/07-binary-logging.md`): Enabling Binary Logging

### [low] grpc.io `guides/opentelemetry-metrics.md` gives the wrong definition for the `grpc.xds.server` label

- **Item:** audit (W1-C-014)
- **Summary:** The OpenTelemetry metrics guide defines the `grpc.xds.server` label with the description of `grpc.target` instead of the xDS server's target URI.
- **Description:** The label table in `content/en/docs/guides/opentelemetry-metrics.md` says `grpc.xds.server`: "For clients, indicates the target of the gRPC channel in which the XdsClient is used. For servers, will be the string \"#server\"." That is the `grpc.target` definition. Per gRFC A78 and the spec, `grpc.xds.server` is the target URI of the xDS server (the bootstrap `server_uri`). Suggested correction: replace the description with "The target URI of the xDS server."
- **Evidence:** grpc.io 81fb52b: `content/en/docs/guides/opentelemetry-metrics.md` (attribute table).
- **Spec:** Metric Catalog (`08-observability/04-metrics.md`): Labels; XdsClient Metrics

### [low] grpc-proto `service_config.proto` types `choice_count` as `uint64` instead of `uint32`

- **Item:** audit (W1-B-005)
- **Summary:** In `grpc/service_config/service_config.proto`, `LeastRequestLocalityLoadBalancingPolicyConfig.choice_count` is `uint64`; gRFC A48 defines it as `uint32`.
- **Description:** gRFC A48 shows `uint32 choice_count = 1;  // Optional, defaults to 2.` and clamps the value to `[2, 10]`. `service_config.proto` declares `uint64 choice_count = 1;`. Suggested correction: change the type to `uint32`.
- **Evidence:** grpc-proto ffb297a: `grpc/service_config/service_config.proto` L461-L463 (`LeastRequestLocalityLoadBalancingPolicyConfig`); grpc-proposal 4125fbd: `A48-xds-least-request-lb-policy.md`.
- **Spec:** `least_request` LB Policy (`04-client-channel/lb-policies/least_request.md`)

### [low] `doc/PROTOCOL-HTTP2.md` `ASCII-Value` and `Percent-Encoded` ABNF rules forbid empty values

- **Item:** audit (W2-01-004, W2-03-017); spec change ABNF-1
- **Summary:** `doc/PROTOCOL-HTTP2.md` defines `ASCII-Value → 1*( %x20-%x7E )` and `Percent-Encoded → 1*(Percent-Byte-Unencoded / Percent-Byte-Encoded)`, which forbid an empty ASCII metadata value and an empty `grpc-message`. HTTP/2 allows empty field values, and the spec (decision ABNF-1) allows empty ASCII values.
- **Description:** C++, Java, and Go send and accept empty ASCII metadata values, and the spec's grammar uses `*( %x20-7E )` for `ASCII-Value` and `*(...)` for `Percent-Encoded`. Suggested correction: change both `1*` to `*`.
- **Evidence:** grpc 515aaa1743: `doc/PROTOCOL-HTTP2.md` L50 (`ASCII-Value`) and L114 (`Percent-Encoded`).
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`): Metadata, Call ABNF; gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`): Requests (Grammar), Responses (Grammar)

### [low] `doc/statuscodes.md` truncates the `DEADLINE_EXCEEDED` description mid-sentence

- **Item:** audit (W2-01-017)
- **Summary:** The `DEADLINE_EXCEEDED` row of `doc/statuscodes.md` ends mid-sentence: "For example, a successful response from a server could have been delayed long".
- **Description:** `google/rpc/code.proto` continues "... could have been delayed long enough for the deadline to expire." Suggested correction: complete the sentence.
- **Evidence:** grpc 515aaa1743: [doc/statuscodes.md L12](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/doc/statuscodes.md#L12).
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`): Status Codes

### [low] doc/PROTOCOL-HTTP2.md suggests 8 KiB default header size limits

- **Item:** audit (wire); spec change SERVER-2
- **Summary:** The doc suggests an 8 KiB default for request and response header lists. The spec no longer names a default.
- **Description:** "Servers may limit the size of **Request-Headers**, with a default of 8 KiB suggested." and "Clients may limit the size of **Response-Headers**, **Trailers**, and **Trailers-Only**, with a default of 8 KiB each suggested." The spec (SERVER-2) removed specific defaults and says only that implementations SHOULD provide a safe default limit, chosen by the implementation. Suggested correction: drop the "with a default of 8 KiB suggested" clauses, or replace them with "implementations SHOULD provide a safe default".
- **Evidence:** grpc `doc/PROTOCOL-HTTP2.md`, "Requests" (Request-Headers size) and "Responses" (Response-Headers/Trailers size).
- **Also:** grpc.io `content/en/docs/guides/metadata.md` (81fb52b) repeats the first sentence as a warning ("Servers may limit the size of Request-Headers, with a default of 8 KiB suggested."); fix it the same way.
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
- **Spec:** Metric Catalog: TCP Metrics (incorporated by METRICS-6)

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

### [low] `doc/compression.md` test cases 4 and 5 over-specify the status message and require `grpc-accept-encoding` on a client failure

- **Item:** audit (W2-02-010); related: R99, COMPRESSION-4
- **Summary:** Test case 5 (client receives an unsupported compression) says "The returned `grpc-accept-encoding` header MUST NOT contain the compression method (encoding) used", which makes no sense for a failure detected by the client. Test cases 4 and 5 both require the status message to list the supported encodings, which the spec leaves as MAY.
- **Description:** Test case 5 copies the server-side `grpc-accept-encoding` sentence onto the client failure path, where the client returns no headers. Test cases 4 and 5 say the call fails with "its associated description indicating the unsupported condition as well as the supported ones"; the spec says the status message SHOULD identify the unsupported algorithm and MAY list the supported ones. Suggested correction: delete the `grpc-accept-encoding` sentence from test case 5 and change both to "... indicating the unsupported condition; it MAY also list the supported ones".
- **Evidence:** grpc 515aaa1743: [doc/compression.md L111-L120](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/doc/compression.md#L111-L120) ("Test cases" items 4 and 5).
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`): Compression (Errors)

### [low] gRFC G2 maps `H3_FRAME_UNEXPECTED` to HTTP/2 `FRAME_SIZE_ERROR`

- **Item:** audit (W2-03-014)
- **Summary:** G2's error-code table lists `FRAME_SIZE_ERROR` as the HTTP/2 equivalent of `H3_FRAME_UNEXPECTED (0x0105)`; the equivalent is `PROTOCOL_ERROR`.
- **Description:** G2 has `H3_FRAME_UNEXPECTED(0x0105)|FRAME_SIZE_ERROR|INTERNAL` and `H3_FRAME_ERROR(0x0106)|FRAME_SIZE_ERROR|INTERNAL`. [RFC 9114 Appendix A.4](https://www.rfc-editor.org/rfc/rfc9114#appendix-A.4) maps HTTP/2 `PROTOCOL_ERROR` to `H3_GENERAL_PROTOCOL_ERROR` or a more specific code such as `H3_FRAME_UNEXPECTED`, and `FRAME_SIZE_ERROR` to `H3_FRAME_ERROR`. Both rows map to gRPC `INTERNAL`, so behavior is unaffected; the spec's table uses `PROTOCOL_ERROR`. Suggested correction: change the HTTP/2 column of the `H3_FRAME_UNEXPECTED` row to `PROTOCOL_ERROR(1)`.
- **Evidence:** grpc-proposal 4125fbd: `G2-http3-protocol.md` L79.
- **Spec:** gRPC over HTTP/3 (`03-wire-protocol/03-http3.md`): error code mapping

### [low] `doc/naming.md` has a stale note that C-core's default DNS resolver does not support an authority

- **Item:** audit (W2-04-022); related: R34
- **Summary:** `doc/naming.md` says "In C-core, the default DNS resolver does not support this, but the c-ares based resolver supports specifying this in the form \"IP:port\"." C-core's default DNS resolver now passes the URI authority to the EventEngine DNS resolver as the DNS server.
- **Description:** The note describes the old native resolver. The spec leaves DNS-server authority support implementation-defined (R34), so the doc is only stale, not in conflict with the spec. Suggested correction: drop the parenthetical, or say that support depends on the DNS resolver in use.
- **Evidence:** grpc 515aaa1743: [doc/naming.md L32-L35](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/doc/naming.md#L32-L35); [dns_resolver.cc L192](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/resolver/dns/dns_resolver.cc#L192) (`GetDNSResolver({/*dns_server=*/authority()})`).
- **Spec:** Name Resolution (`04-client-channel/03-name-resolution.md`): `dns`

### [low] `grpc/doc/health-checking.md` omits `Health.List`, `HealthListRequest`, and `HealthListResponse` added by gRFC A90

- **Item:** audit (W2-12-007)
- **Summary:** The service definition in `doc/health-checking.md` shows only `Check` and `Watch`, omitting the `List` RPC and its `HealthListRequest` and `HealthListResponse` messages added by gRFC A90.
- **Description:** Suggested correction: update the embedded `grpc.health.v1` proto snippet to match grpc-proto `grpc/health/v1/health.proto`, or link to it.
- **Evidence:** grpc 515aaa1743: [doc/health-checking.md L26-L50](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/doc/health-checking.md#L26-L50); grpc-proto ffb297a: `grpc/health/v1/health.proto` L43-L74.
- **Spec:** Health Service (`07-services/01-health.md`): Service Definition; `List`

### [low] gRFC A80 has typo `8196` instead of `8192` in the `grpc.transfer_size` table

- **Item:** audit (W2-13-022)
- **Summary:** The `grpc.transfer_size` bucket table in `A80-tcp-telemetry.md` lists `8196` instead of `8192` for the "First 8KiB" row.
- **Description:** 8 KiB is 8192 bytes. C++ copied the typo into the metric description ("Time taken to transmit the first 8196 bytes of a write.") while using 8192 in code. The spec uses `8192`. Suggested correction: change `8196` to `8192`.
- **Evidence:** grpc-proposal 4125fbd: `A80-tcp-telemetry.md` L91 (`| \[8KiB, 64KiB) | First 8KiB | 8196 |`); grpc 515aaa1743: [tcp_telemetry.cc L123](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/lib/event_engine/tcp_telemetry.cc#L123).
- **Spec:** Metric Catalog (`08-observability/04-metrics.md`): TCP Metrics

### [low] Broken link to `A108-otel-custom-per-rpc-label.md` in gRFCs A66 and A96

- **Item:** audit (W2-13-023)
- **Summary:** `A66-otel-stats.md` and `A96-retry-otel-stats.md` link to `A108-otel-custom-per-rpc-label.md`; the file is `A108-otel-custom-per-call-label.md`.
- **Description:** In both gRFCs, the "Updated by: gRFC A108: OpenTelemetry Custom Per-Call Metric Label" header line links to the nonexistent file `A108-otel-custom-per-rpc-label.md`. Suggested correction: change the link target to `A108-otel-custom-per-call-label.md`.
- **Evidence:** grpc-proposal 4125fbd: `A66-otel-stats.md` L10-L11, `A96-retry-otel-stats.md` L10-L11.
- **Spec:** Instrumentation Architecture (`08-observability/02-instrumentation.md`): Custom Per-Call Label

### [low] gRFC A59 examples have an invalid timestamp and trailing commas, and its Go `PolicyName` comment contradicts the xDS case

- **Item:** audit (W2-11-025)
- **Summary:** A59's example log entry uses the Go layout string `2006-01-02T15:04:05.999999999Z07:00` as a timestamp, two JSON examples have trailing commas, and the Go API comment says `PolicyName` is "the authorization policy name or the xDS RBAC filter name", while A59's own field table says the policy name is "not applicable in xDS case".
- **Description:** `Z07:00` is Go `time` layout syntax; a valid RFC 3339 timestamp has either `Z` or a numeric offset, not both. The xDS and authorization-policy config examples end objects with a trailing comma, which is not valid JSON. The spec says the policy name is empty for xDS RBAC, matching A59's table; grpc-go copied the contradicting comment into `authz/audit/audit_logger.go`. Suggested correction: use a real timestamp such as `2023-05-09T01:40:06.798505167Z`, remove the trailing commas, and change the comment to "the authorization policy name; empty for xDS RBAC".
- **Evidence:** grpc-proposal 4125fbd: `A59-audit-logging.md` L53, L296, L305, L312, L445; grpc-go cbf30c4130: `authz/audit/audit_logger.go` L69.
- **Spec:** Authorization (`06-security/04-authorization.md`): Audit Logging; xDS HTTP Filters (`09-xds/07-http-filters.md`): Audit Logging Configuration

### [low] gRFC A41 header "Implemented in" is a template placeholder

- **Item:** GRFC-STATUS
- **Summary:** `A41-xds-rbac.md` lists "Implemented in: \<language, ...\>", although xDS RBAC is implemented in C++, Java, and Go.
- **Description:** Header: "Status: Ready for Implementation", "Implemented in: \<language, ...\>", "Last updated: 2021-09-08". Suggested correction: set "Implemented in: C++, Java, Go" and update the date.
- **Evidence:** grpc-proposal 4125fbd: `A41-xds-rbac.md` L6-L7.
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`): RBAC

### [low] gRFC A43 schema allows an empty policy `name`

- **Item:** AUTHZ-4
- **Summary:** A43's JSON schema requires `name` but allows the empty string; the spec now requires a non-empty `name`.
- **Description:** A43's schema defines the policy `name` as `"type": "string"` with description "The name of an authorization policy. It is mainly for monitoring and error message generation." and `"required": ["name", "allow_rules"]`; nothing excludes `""`. The spec now says the policy `name` MUST NOT be empty (Java and Go reject `""`). Suggested correction: add `"minLength": 1` to `name` in the schema, or say in its description that it must be non-empty. (A43's `deny_rules` description, "If none of the deny rules matches or there are no deny rules, the allow rules will be evaluated", already agrees with the spec's "an empty array is the same as absent".)
- **Evidence:** grpc-proposal `A43-grpc-authorization-api.md` (master 4125fbd), policy JSON schema, `properties.name`.
- **Spec:** gRPC Authorization: 2.1 Schema

### [low] gRFC A37 says only that the LOGICAL_DNS `port_value` "must be set"

- **Item:** XDS_CDS-21
- **Summary:** A37 doesn't say whether "set" means the oneof case or a non-zero value, and gives no range. Implementations read it differently.
- **Description:** A37, Cluster validation: "The `port_value` field must be set." C++ and Java read this as the `port_specifier` oneof being set, so they accept an explicit 0. Go reads it as non-zero. None of the three applies an upper bound. The spec now says `port_value` MUST be in 1–65535 (an unset port, an explicit 0, or a value above 65535 NACKs the Cluster). Suggested correction: "The `port_value` field must be in the range 1–65535; a value of 0 (or unset) or above 65535 causes the resource to be NACKed."
- **Evidence:** grpc-proposal `A37-xds-aggregate-and-logical-dns-clusters.md` (master 4125fbd), Cluster validation section.
- **Spec:** Cluster: Logical DNS Clusters

### [low] gRFC A61 doesn't say that `weighted_target` should stop applying its own sticky TRANSIENT_FAILURE

- **Item:** WEIGHTED_TARGET-2
- **Summary:** A61 moved sticky TRANSIENT_FAILURE into `pick_first` (via A62) and made petiole policies rely on it, but it doesn't update `weighted_target`, whose implementations still apply their own sticky TRANSIENT_FAILURE when aggregating.
- **Description:** gRFC A28 says only that "The connectivity state of the policy will be the aggregated state of all child policies." C++ and Go added sticky-TRANSIENT_FAILURE handling to `weighted_target` aggregation before A62. A61 notes that "as of [gRFC A62][A62], pick_first has sticky-TF behavior in all languages" but never says that parents like `weighted_target` should now aggregate with the normal rules. The spec does (normal rules, relying on `pick_first`). Suggested correction: add a note to A61 (or A28) that `weighted_target` aggregates its children's current states with the normal rules.
- **Evidence:** grpc-proposal `A61-IPv4-IPv6-dualstack-backends.md` and `A28-xds-traffic-splitting-and-routing.md` ("Weighted target LB policy"), master 4125fbd.
- **Spec:** `weighted_target` LB Policy: Calls From Children

### [low] gRFC A58 doesn't mention clamping endpoint weights before building the scheduler

- **Item:** WRR-20
- **Summary:** A58 describes WRR picking in proportion to endpoint weights with no clamping, but C++ and Java clamp weights relative to the mean, and the spec now requires it.
- **Description:** A58 says each endpoint is picked in proportion to its weight and doesn't mention any bound on the ratio between weights. C++ (grpc/grpc#33045) and Java (grpc/grpc-java#10480) later added clamping to `[MIN_RATIO × mean, 10 × mean]` (MIN_RATIO 0.01 and 0.1) to bound pick cost, and the spec now requires clamping with `MAX_RATIO` 10 and `MIN_RATIO` in [0.01, 0.1]. Suggested correction: add the clamping rule and its rationale to A58's scheduler description.
- **Evidence:** grpc-proposal `A58-client-side-weighted-round-robin-lb-policy.md` (master 4125fbd).
- **Spec:** `weighted_round_robin` LB Policy: Building the Scheduler

