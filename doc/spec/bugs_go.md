# Go implementation bugs

Bugs in grpc-go found while writing and reviewing the gRPC spec in this directory: **195** entries, ordered by severity. Other lists: [Java](bugs_java.md), [C++](bugs_cpp.md), [documentation](bugs_docs.md).

Severity:

- **critical:** crash, data corruption, or a security weakness
- **high:** interoperability failure, or wrong behavior that users commonly hit
- **medium:** spec non-conformance with limited impact
- **low:** cosmetic, or a rare edge case

Each bug lists the review item that identified it (an item ID such as `RLS-4`, an `R<n>` number from the original review list, or "incidental"/"audit"), a summary, a description, evidence (code locations), and the spec section it violates. Open questions are in [review_items.md](review_items.md). None of these bugs has been filed yet.

### [critical] LRS client panics on a non-positive load reporting interval

- **Item:** incidental (investigation of old item 182)
- **Summary:** A `LoadStatsResponse` with `load_reporting_interval` ≤ 0 makes the LRS client panic.
- **Description:** The LRS client passes the server-provided interval directly to `time.NewTicker`, which panics on a non-positive duration. A misconfigured or malicious control plane can crash every client. The spec (and gRFC A27 as updated) requires any interval below 1 second, including zero, negative, or unset, to be treated as 1 second; Go applies no minimum, so small positive intervals are also used as-is.
- **Evidence:** grpc-go `internal/xds/clients/lrsclient/lrs_stream.go` (~line 151 `time.NewTicker(interval)`; interval read from the first response ~line 220).
- **Spec:** Load Reporting (LRS): Responses

### [critical] `CertificateValidationContext.match_typed_subject_alt_names` is silently ignored (SAN verification fails open)

- **Item:** XDS_SECURITY-20
- **Summary:** `securityConfigFromCommonTLSContextUsingNewFields` reads only `GetMatchSubjectAltNames()` and never checks `GetMatchTypedSubjectAltNames()`, so a resource that sets the typed field is ACKed and its SAN matchers are not applied.
- **Description:** The spec requires a NACK when `match_typed_subject_alt_names` is non-empty, because ignoring it compromises security. A control plane that uses Envoy's non-deprecated SAN matcher field gets a client that skips peer SAN verification (unless `auto_sni_san_validation` is set). If both fields are set, gRPC checks the deprecated list, which Envoy ignores. The same applies to LDS (`unmarshal_lds.go`).
- **Evidence:** grpc-go cbf30c4130: [unmarshal_cds.go L492-L615](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L492-L615)
- **Spec:** xDS Security: `CommonTlsContext` Validation (`09-xds/09-security.md`)

### [high] `GrpcService.initial_metadata` honored from untrusted xDS servers

- **Item:** audit (W2-15-001)
- **Summary:** Go parses `GrpcService.initial_metadata` and attaches it to side-channel RPCs whether or not the xDS server that sent the resource lists `trusted_xds_server`.
- **Description:** gRFC A102 says `initial_metadata` is ignored when the `GrpcService` comes from an untrusted xDS server. For untrusted servers, only the target URI from the allowlist is honored, and the credentials come from `allowed_grpc_services`. Go's `grpcservice.Parse` checks trust only when choosing credentials. It always parses `initial_metadata` into `Config.InitialMetadata`, and the ext_authz and ext_proc filters add that metadata to every side-channel RPC. An untrusted control plane can therefore inject arbitrary headers into RPCs to an allowlisted side-channel service. (C++ parses `initial_metadata` only for trusted servers.)
- **Evidence:** grpc-go cbf30c4130: [grpcservice.go L188-L211](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/grpcservice/grpcservice.go#L188-L211), [ext_authz.go L383](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/ext_authz/ext_authz.go#L383), [ext_proc.go L388](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/extproc/ext_proc.go#L388)
- **Spec:** Bootstrap (`09-xds/02-bootstrap.md`), Allowed gRPC Service Object; Server Features (source: gRFC A102, "`GrpcService` Proto Validation")

### [high] xDS client transport configs keyed only by channel credential type, so servers share or overwrite credentials

- **Item:** audit (W2-15-002)
- **Summary:** `BuildXDSClientConfig` stores one transport config per `channel_creds` type string (for example `"tls"`). When several `xds_servers` use the same type with different TLS files or `call_creds`, the last server processed overwrites the others, and every server with that type uses its credentials.
- **Description:** `populateGRPCTransportConfigsFromServerConfig` builds a bundle from each server's channel creds and stores it in `grpcTransportConfigs[cc.Type]`, together with a dial function that appends that server's `DialOptions()` (where bootstrap `call_creds` such as `jwt_token_file` are attached). Each server's `ServerIdentifierExtension` names only `ConfigName: SelectedChannelCreds().Type`, and the grpctransport builder looks up the config by that name. With two servers (top-level vs. per-authority, or primary vs. fallback) that both use `tls` with different CA or identity files, or different call credentials, all of them connect with the credentials of whichever server was processed last. This can send one server's bearer token to another server. The spec defines a server's identity by its URI, selected channel credentials (type and config), and call credentials, and says each xDS channel uses its own configured credentials.
- **Evidence:** grpc-go cbf30c4130: [clientimpl.go L192-L200](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/clientimpl.go#L192-L200), [clientimpl.go L262-L280](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/clientimpl.go#L262-L280), [bootstrap.go L548-L570](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/bootstrap/bootstrap.go#L548-L570), [grpc_transport.go L101](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/grpctransport/grpc_transport.go#L101)
- **Spec:** Bootstrap (`09-xds/02-bootstrap.md`), XdsServer Object; XdsClient (`09-xds/03-xds-client.md`), xDS Channels

### [high] Go: outlier detection re-ejects ejected endpoints and leaks the ejected count

- **Item:** OUTLIER_DETECTION-1
- **Summary:** Go doesn't skip already-ejected endpoints in either algorithm. Every re-ejection increments `numEndpointsEjected`, which can drift upward until it blocks all further ejections.
- **Description:** The spec excludes already-ejected endpoints from the candidates. `endpointsWithAtLeastRequestVolume` returns every endpoint with enough volume, whether ejected or not. Both algorithms can call `ejectEndpoint` again, which increments `numEndpointsEjected` and the multiplier and resets the timestamp. `unejectEndpoint` decrements the count only once, and removing an ejected endpoint in an update doesn't decrement it at all. Once the count is too high, `numEndpointsEjected/len*100 >= MaxEjectionPercent` blocks every later ejection for the life of the policy. The stale count also affects the mean/stdev and `minimum_hosts`.
- **Evidence:** Go master c2165f27: [internal/xds/balancer/outlierdetection/balancer.go L702-L712](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L702-L712) (candidates), [L743-L803](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L743-L803) (algorithms), [L806-L827](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L806-L827) (eject/uneject), [L329-L333](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/outlierdetection/balancer.go#L329-L333) (endpoint removal)
- **Spec:** `outlier_detection` LB Policy: Ejection Timer

### [high] Aggregate clusters use the aggregate cluster's LB policy and a flattened priority list (A75 not implemented for aggregate clusters)

- **Item:** XDS_LB-5
- **Summary:** Go flattens every leaf cluster's priorities into one `priority` policy, with `outlier_detection` and `xds_cluster_impl` per priority, and uses the root aggregate cluster's LB policy for all leaves.
- **Description:** gRFC A75 represents an aggregate cluster as a `priority` policy whose children are per-leaf `cds` policies. Each leaf uses its own LB policy, and outlier detection, cluster_impl, and override_host sit above that leaf's priorities. Go adopted A75 for non-aggregate clusters in v1.85.0 (grpc/grpc-go#9234), but aggregate clusters still use the pre-A75 shape: "The LB policy is configured by the root cluster". So the aggregate cluster's LB policy fields, which the spec says are ignored, are applied to every leaf, and outlier detection runs separately in each priority.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/cdsbalancer/configbuilder.go#L109-L180, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/cdsbalancer/configbuilder.go#L212-L253, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/balancer/cdsbalancer/cdsbalancer.go#L318
- **Spec:** `cds` LB Policy: Position in the xDS LB Policy Tree

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

### [high] Per-request ORCA drops per-server metrics unless the handler fetches the per-call recorder, and sends empty reports

- **Item:** audit (W2-12-014)
- **Summary:** With `orca.CallMetricsServerOption(smp)`, Go sends `endpoint-load-metrics-bin` only for RPCs whose handler called `CallMetricsRecorderFromContext`. Otherwise the per-server recorder's metrics are never sent. When the handler fetched the recorder but nothing was recorded, Go sends an empty report.
- **Description:** The unary and stream interceptors allocate the per-call recorder lazily and call `setTrailerMetadata` only if it was allocated. A server that publishes utilization only through the per-server recorder (a common setup for `weighted_round_robin` with per-call reports) sends no load reports for handlers that never touch the per-call recorder, so WRR clients get no weights. The spec says per-request reporting adds the trailer to every RPC while it is enabled, merging the per-server snapshot with the per-call values. It also says the server SHOULD omit `endpoint-load-metrics-bin` when nothing was recorded and the per-server recorder supplied no data.
- **Evidence:** grpc-go cbf30c4130: [call_metrics.go L76-L108](https://github.com/grpc/grpc-go/blob/cbf30c4130/orca/call_metrics.go#L76-L108), [call_metrics.go L138-L179](https://github.com/grpc/grpc-go/blob/cbf30c4130/orca/call_metrics.go#L138-L179)
- **Spec:** Backend Metrics (ORCA) (`07-services/03-orca.md`), Wire Format, Per-Call Recorder, and Merging with the Per-Server Recorder

### [high] OpenTelemetry tracing panics when `TracerProvider` is set without `TextMapPropagator`

- **Item:** audit (W2-13-013)
- **Summary:** With `TraceOptions.TracerProvider` set and `TraceOptions.TextMapPropagator` nil, every client and server RPC panics with a nil-interface dereference.
- **Description:** The plugin enables tracing whenever `TracerProvider` is non-nil. The client attempt-span code calls `TextMapPropagator.Inject` and the server code calls `TextMapPropagator.Extract`, with no nil check. Comments in those files, and the `TraceOptions` documentation, say that without a propagator the context is returned unchanged or tracing is not recorded. Only a warning is logged when exactly one of the two options is set, and only on one path. The spec makes the propagator a separate setting and says only that no traces are produced when the TracerProvider is unset. Crashing on every RPC is not acceptable behavior for this configuration.
- **Evidence:** grpc-go cbf30c4130: [opentelemetry.go L73-L75](https://github.com/grpc/grpc-go/blob/cbf30c4130/stats/opentelemetry/opentelemetry.go#L73-L75), [client_tracing.go L98-L103](https://github.com/grpc/grpc-go/blob/cbf30c4130/stats/opentelemetry/client_tracing.go#L98-L103), [server_tracing.go L57-L59](https://github.com/grpc/grpc-go/blob/cbf30c4130/stats/opentelemetry/server_tracing.go#L57-L59), [trace_options.go L33-L35](https://github.com/grpc/grpc-go/blob/cbf30c4130/experimental/opentelemetry/trace_options.go#L33-L35)
- **Spec:** Metrics Framework and OpenTelemetry Plugin (`08-observability/03-metrics-framework.md`), Tracing Configuration; Tracing (`08-observability/05-tracing.md`), Propagator Model

### [high] Dynamic `cds` hangs in CONNECTING when its cluster is already subscribed

- **Item:** audit (W2-17-007)
- **Summary:** On its first update, a dynamic (`isDynamic: true`) `cds` policy subscribes to its cluster and returns without checking the current `XdsConfig`. If the cluster was already subscribed (for example, a route also references it statically), no new `XdsConfig` is sent, so the policy never creates its child.
- **Description:** The spec says `cds`, after obtaining the cluster subscription, looks up the cluster in the `XdsConfig` from the same update, and waits only if the entry is missing. Go returns from `handleXDSConfigUpdate` right after `SubscribeToCluster`. When the cluster is already tracked, `XdsDependencyManager.SubscribeToCluster` only increments the dynamic reference count and does not call `maybeSendUpdateLocked`. The `cds` policy (typically an RLS child) stays in CONNECTING and queues RPCs until an unrelated `XdsConfig` change happens to be delivered to it. Because of "RLS children may not receive resolver updates when the RLS config is unchanged", that may never happen.
- **Evidence:** grpc-go cbf30c4130: [cdsbalancer.go L210-L214](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/cdsbalancer/cdsbalancer.go#L210-L214), [xds_dependency_manager.go L981-L998](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsdepmgr/xds_dependency_manager.go#L981-L998)
- **Spec:** `cds` LB Policy (`09-xds/lb-policies/cds.md`), Updates from the Parent; Client Data Plane (`09-xds/05-client.md`), Dynamic cluster subscriptions

### [high] xDS server never requests a client certificate when `require_client_certificate` is false

- **Item:** audit (W2-18-019)
- **Summary:** With a `DownstreamTlsContext` that has a CA source but `require_client_certificate` false or unset, Go leaves `tls.Config.ClientAuth` at `NoClientCert`, so clients are never asked for a certificate and are always unauthenticated.
- **Description:** The spec says that when `require_client_certificate` is false and a validation context is present, the server requests a client certificate and validates it if one is presented, while still allowing clients without one. Go sets `ClientAuth` only when `requireClientCert` is true (`RequireAndVerifyClientCert`, or `RequireAnyClientCert` plus a custom verifier for SPIFFE). Otherwise it configures `ClientCAs` but never sends a `CertificateRequest`. In permissive-mTLS deployments, clients that have certificates connect without a peer identity, so RBAC principal rules that should match them do not.
- **Evidence:** grpc-go cbf30c4130: [handshake_info.go L327-L363](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/credentials/xds/handshake_info.go#L327-L363)
- **Spec:** xDS Security (`09-xds/09-security.md`), Server Side: `DownstreamTlsContext`

### [high] Authorization policy with a `null` `audit_loggers` entry panics

- **Item:** audit (W2-11-023)
- **Summary:** The gRPC authorization policy translator decodes `audit_logging_options.audit_loggers` as `[]*auditLogger` and dereferences each element without a nil check. A policy containing `"audit_loggers": [null]` panics instead of being rejected.
- **Description:** The spec says a field with the wrong JSON type makes the policy invalid. A static policy that is invalid must return an error at creation, and an invalid file-watcher reload must be skipped with an error logged, keeping the previous policy. In `auditLoggingOptions.toProtos`, a `null` array element decodes as a nil `*auditLogger`, and `config.Name` dereferences it. With `NewStatic`, the panic happens in the caller's goroutine. With `NewFileWatcher`, a bad reload panics in the background refresh goroutine and crashes the server.
- **Evidence:** grpc-go cbf30c4130: [rbac_translator.go L64-L73](https://github.com/grpc/grpc-go/blob/cbf30c4130/authz/rbac_translator.go#L64-L73), [rbac_translator.go L305-L311](https://github.com/grpc/grpc-go/blob/cbf30c4130/authz/rbac_translator.go#L305-L311), [rbac_translator.go L362-L378](https://github.com/grpc/grpc-go/blob/cbf30c4130/authz/rbac_translator.go#L362-L378), [grpc_authz_server_interceptors.go L149-L194](https://github.com/grpc/grpc-go/blob/cbf30c4130/authz/grpc_authz_server_interceptors.go#L149-L194)
- **Spec:** Authorization (`06-security/04-authorization.md`), Schema; Policy Providers; Audit Options in the gRPC Authorization Policy

### [high] A missing or failed underlying cluster fails the whole aggregate cluster

- **Item:** XDS_DEPMGR-3
- **Summary:** When an underlying cluster of an aggregate cluster does not exist, or has a CDS error with no cached resource, the XdsDependencyManager returns that error for the aggregate cluster and every aggregate above it, instead of skipping the failed cluster.
- **Description:** The spec (following gRFC A74) says a failed underlying cluster MUST NOT fail the aggregate cluster. It is either skipped, with its error added to the resolution note, or kept as an always-failing leaf. Go returns the underlying cluster's error from `populateClusterConfigLocked`, stores it as the aggregate's own entry, and passes it up to every ancestor. That is the pre-A74 A37 behavior, so a single missing cluster removes aggregate failover entirely.
- **Evidence:** grpc-go v1.82.0: [xds_dependency_manager.go L336-L339](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L336-L339), [L423-L426](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L423-L426)
- **Spec:** Client Data Plane: Aggregate cluster graph (`09-xds/05-client.md`)

### [medium] Picker errors are treated like drops: no retry, wait-for-ready ignored

- **Item:** incidental (investigation of old item 76)
- **Summary:** Any picker error that carries a gRPC status fails the RPC immediately as a Drop. Go has no way for a picker to return a Fail with a specific status.
- **Description:** The spec distinguishes Fail from Drop. A Fail is queued when the RPC is wait-for-ready, and otherwise fails the attempt so configurable retries can retry it. A Drop fails even wait-for-ready RPCs and is never retried. Go's picker wrapper wraps every status-carrying pick error in `dropError`, and the retry code marks the attempt as dropped and does not retry it. Non-status errors are queued for wait-for-ready RPCs and otherwise become UNAVAILABLE, so a policy cannot report a Fail with any other code or message status. Policies that return status errors for what the spec calls Fail therefore fail wait-for-ready RPCs and bypass `retryableStatusCodes`. One example is the RLS picker's backoff failure, which `rls.md` requires to be a Fail; see also "RLS config and picker non-conformances".
- **Evidence:** grpc-go cbf30c4130: [picker_wrapper.go L157-L177](https://github.com/grpc/grpc-go/blob/cbf30c4130/picker_wrapper.go#L157-L177), [stream.go L611-L613](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L611-L613), [stream.go L816](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L816), [rls/picker.go L144](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/rls/picker.go#L144)
- **Spec:** Load Balancing (`04-client-channel/06-load-balancing.md`), Pick Results; `rls` LB Policy (`04-client-channel/lb-policies/rls.md`), Picker Implementation

### [medium] `outlier_detection` never reports TRANSIENT_FAILURE to a health listener registered on an already-ejected endpoint

- **Item:** audit (W2-08-008)
- **Summary:** When a child registers a health listener on a subchannel whose endpoint is already ejected, `outlier_detection` suppresses all health updates and never delivers the ejected TRANSIENT_FAILURE state, so `pick_first` reports CONNECTING until the endpoint is un-ejected.
- **Description:** For an already-ejected endpoint, `NewSubConn` marks the new wrapper ejected right away, before any health listener exists, so the synthetic TRANSIENT_FAILURE from `handleEjection` goes nowhere. When the subchannel becomes READY, `pick_first` reports CONNECTING and registers its health listener. Every later underlying health update is dropped because the wrapper is ejected, and no TRANSIENT_FAILURE is sent to the new listener. The same happens when an ejected endpoint's subchannel reconnects and the listener is registered again. The spec says the wrapper of an ejected endpoint starts out ejected and reports TRANSIENT_FAILURE to health watchers, so petiole policies should see TRANSIENT_FAILURE, not CONNECTING. The endpoint is not picked in either case, but the petiole's aggregate state can be CONNECTING when it should be TRANSIENT_FAILURE.
- **Evidence:** grpc-go cbf30c4130: [balancer.go L503-L508](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/outlierdetection/balancer.go#L503-L508), [subconn_wrapper.go L95-L136](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/outlierdetection/subconn_wrapper.go#L95-L136), [subconn_wrapper.go L159-L169](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/outlierdetection/subconn_wrapper.go#L159-L169), [pickfirst.go L637-L644](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/pickfirst/pickfirst.go#L637-L644)
- **Spec:** `outlier_detection` LB Policy (`04-client-channel/lb-policies/outlier_detection.md`), Calls From Children and Subchannels; Load Balancing (`04-client-channel/06-load-balancing.md`), Generic Health Reporting

### [medium] RLS default-target child policy reference counting is wrong across picker updates

- **Item:** audit (W2-09-016)
- **Summary:** When `defaultTarget` changes, the old default target's child policy is never released (it leaks with its subchannels), and the new default's child can later be removed while a picker still uses it.
- **Description:** `sendNewPickerLocked` acquires a reference on `b.defaultPolicy` for the new picker and then, if there was a previous picker, releases a reference on `b.defaultPolicy` again. It should release the previous picker's `defaultPolicy`. When the default changes from A to B, `handleChildPolicyConfigUpdate` releases only A's config reference, so the reference held by the previous picker on A is never released. A's child policy stays in the balancer group until the LB policy shuts down. B's picker reference is cancelled out, so B holds only its config reference. On the next default change, B is removed from the balancer group while the current picker still delegates to it. The spec says children are reference-counted and destroyed when their last reference is released.
- **Evidence:** grpc-go cbf30c4130: [balancer.go L415-L429](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/rls/balancer.go#L415-L429), [balancer.go L527-L571](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/rls/balancer.go#L527-L571), [child_policy.go L74-L98](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/rls/child_policy.go#L74-L98)
- **Spec:** `rls` LB Policy (`04-client-channel/lb-policies/rls.md`), Child Policies

### [medium] `hash_policy` `header.regex_rewrite` substitution uses Go `$1` syntax instead of RE2 `\1`

- **Item:** audit (W2-16-010, W2-17-006)
- **Summary:** Go applies `regex_rewrite.substitution` with `regexp.Regexp.ReplaceAllString`, which expands `$1` / `${name}` and treats `\1` as literal text, instead of RE2's `\1`..`\9` capture-group syntax.
- **Description:** The spec (following Envoy's `RegexMatchAndSubstitute` and gRFC A42) says the substitution may use RE2 capture-group references such as `\1`. Go passes the substitution string unchanged to `ReplaceAllString`. A substitution such as `\1` produces the literal text `\1`, and a literal `$` is treated as a group reference. The hashed value, and with it `ring_hash` endpoint affinity, then differs from Envoy and C++ (which uses `RE2::GlobalReplace`).
- **Evidence:** grpc-go cbf30c4130: [serviceconfig.go L329-L331](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/resolver/serviceconfig.go#L329-L331), [unmarshal_rds.go L400-L408](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_rds.go#L400-L408)
- **Spec:** RouteConfiguration (`09-xds/04-resources/03-route-configuration.md`), Hash Policy; Client Data Plane (`09-xds/05-client.md`), Request hash

### [medium] Aggregate cluster in a diamond graph gets an empty leaf list, which can overwrite its own result

- **Item:** audit (W2-17-008)
- **Summary:** When resolving one root's aggregate graph, a cluster already visited through another branch contributes no leaves. An inner aggregate whose only leaves were already visited is then recorded as an error ("no leaf clusters"), and that error can replace the cluster's correct entry in the `XdsConfig`.
- **Description:** `populateClusterConfigLocked` returns `(true, nil, nil)` for any cluster already in the per-root `clusterConfigs` map. For `A -> [B, C]`, `B -> [D]`, `C -> [D]`, B adds D, and C then gets no leaves, so C's entry becomes "aggregate cluster graph has no leaf clusters". If C also has other leaves, its leaf list silently lacks D. A's own leaf list is still correct. However, `maybeSendUpdateLocked` resolves each subscribed root separately and merges the results into `config.Clusters` with `maps.Copy`, iterating over a Go map in random order. If C is also a root (referenced directly by a route), its correct entry from its own traversal is overwritten by the bad entry from A's traversal some of the time, and RPCs routed to C fail. The spec says de-duplication is per aggregate cluster: a cluster reached earlier through another aggregate still contributes its leaf clusters to every aggregate that lists it.
- **Evidence:** grpc-go cbf30c4130: [xds_dependency_manager.go L240-L259](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsdepmgr/xds_dependency_manager.go#L240-L259), [xds_dependency_manager.go L325-L328](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsdepmgr/xds_dependency_manager.go#L325-L328), [xds_dependency_manager.go L421-L446](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsdepmgr/xds_dependency_manager.go#L421-L446)
- **Spec:** Client Data Plane (`09-xds/05-client.md`), Aggregate cluster graph

### [medium] `cds` keeps its child policy when the cluster's `XdsConfig` entry is an error

- **Item:** audit (W2-17-009)
- **Summary:** When the cluster's `XdsConfig` entry has an error (or a static cluster is missing), `cdsBalancer` returns the error from `UpdateClientConnState` instead of calling `closeChildPolicyAndReportTF`. The old child policy and its connections stay alive.
- **Description:** The spec requires `cds`, on an error entry, to destroy its child policy and report TRANSIENT_FAILURE. Go returns `clusterUpdate.Err`. Under `xds_cluster_manager`, the parent installs an error picker for that child, but the child stays alive with its subchannels. The child's next state update (for example, a subchannel becoming READY) replaces the error picker, so RPCs are routed to the endpoints of a cluster the control plane reported as failed. Under `rls`, child update errors are only logged, so a dynamic `cds` child stays in its previous state.
- **Evidence:** grpc-go cbf30c4130: [cdsbalancer.go L216-L230](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/cdsbalancer/cdsbalancer.go#L216-L230), [cdsbalancer.go L498-L507](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/cdsbalancer/cdsbalancer.go#L498-L507), [clustermanager.go L132-L138](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/clustermanager/clustermanager.go#L132-L138), [balancerstateaggregator.go L146-L167](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/clustermanager/balancerstateaggregator.go#L146-L167)
- **Spec:** `cds` LB Policy (`09-xds/lb-policies/cds.md`), Updates from the Parent

### [medium] `outlier_detection` JSON config defaults `failurePercentageEjection.enforcementPercentage` to 0 instead of 100

- **Item:** audit (W1-B-007)
- **Summary:** When `failurePercentageEjection` is present without `enforcementPercentage`, Go uses 0, so failure-percentage ejection never ejects anything.
- **Description:** The spec and gRFC A50 give `failurePercentageEjection.enforcementPercentage` a default of 100. Go's `FailurePercentageEjection.UnmarshalJSON` explicitly defaults it to 0 (and the field comment says "Defaults to 0"). A JSON service config that enables failure-percentage ejection without setting `enforcementPercentage` therefore detects outliers but never ejects them. Configs built from xDS are not affected, because the CDS converter enables this algorithm only when `enforcing_failure_percentage` is set and non-zero, and copies the value.
- **Evidence:** grpc-go cbf30c4130: [config.go L105-L109](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/outlierdetection/config.go#L105-L109), [config.go L127-L140](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/outlierdetection/config.go#L127-L140)
- **Spec:** `outlier_detection` LB Policy (`04-client-channel/lb-policies/outlier_detection.md`), Configuration

### [medium] Go random_subsetting hashes Address.String() including attributes

- **Item:** RANDOM_SUBSETTING-1
- **Summary:** The hash input contains the address's attributes, and some of them print as pointers. So the subset can change on every resolver update even when the addresses are the same.
- **Description:** `b.hashDigest.WriteString(endpoint.Addresses[0].String())`. `Address.String()` includes `Attributes` and `BalancerAttributes`, and `Attributes.String()` prints values that are neither strings nor Stringers as `<%p>`. That breaks the low-churn guarantee in gRFC A68. The fix is to hash `Addr` only. Checked on master.
- **Evidence:** [randomsubsetting.go#L180](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer/randomsubsetting/randomsubsetting.go#L180), [resolver.go#L138-L150](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/resolver/resolver.go#L138-L150), [attributes.go#L145](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/attributes/attributes.go#L145)
- **Spec:** `random_subsetting` LB Policy: Subset Selection

### [medium] Go resets retry throttle tokens on every resolver update

- **Item:** RETRY-3
- **Summary:** `applyServiceConfigAndBalancer` installs a new `retryThrottler` with `tokens = MaxTokens` on every call. That includes every resolver update with an unchanged config, and resolver errors (through `maybeApplyDefaultServiceConfig`).
- **Description:** With a resolver that updates often (xDS, re-resolving DNS), the token bucket keeps getting refilled, so retry throttling may never kick in. That defeats its overload protection. C++ keeps the throttler when the parameters are unchanged and scales the ratio when they change. Checked on master.
- **Evidence:** [clientconn.go#L1159-L1180](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/clientconn.go#L1159-L1180), [clientconn.go#L794-L850](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/clientconn.go#L794-L850)
- **Spec:** Retries: Token Accounting

### [medium] Go does not reset LRS stats for unrequested clusters

- **Item:** XDS_LRS-2
- **Summary:** Stats for clusters the LRS server did not ask for keep building up and appear in the first report after the server asks for that cluster.
- **Description:** `LoadStore.stats(clusterNames)` reads and resets only the listed clusters. Other clusters' counters are never reset, so a later request for them reports load from earlier intervals as current. C++ resets every cluster at each report.
- **Evidence:** [load_store.go](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/clients/lrsclient/load_store.go#L112-L130)
- **Spec:** xDS Load Reporting: Responses

### [medium] Go: grpc-status ignored on non-gRPC content-type, and :status ignored when the content-type is gRPC

- **Item:** HTTP2-1
- **Summary:** Go uses the HTTP status mapping when the content-type is not gRPC even if `grpc-status` is present, and never checks `:status` when the content-type is gRPC, so 503/429 without `grpc-status` become `UNKNOWN`.
- **Description:** In `operateHeaders`, `isGRPC` is set only by a valid gRPC content-type (or by being a trailer block). If false, `grpc-status` is ignored and the HTTP mapping is used. If true, `:status` is never consulted, so a gRPC-typed 503 Trailers-Only block without `grpc-status` ends with the default `codes.Unknown` instead of `UNAVAILABLE`, which affects retry decisions. Still present on master c2165f27. Because the 1xx check is also inside the `!isGRPC` branch, a 1xx informational header block that carries a gRPC `content-type` is accepted as the Response-Headers instead of being skipped; the real response headers that follow then fail the call with `INTERNAL` ("a HEADERS frame cannot appear in the middle of a stream") (audit W2-03-008).
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/http2_client.go#L1544-L1651, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/http2_client.go#L1700; 1xx case at cbf30c4130: [http2_client.go L1516-L1521](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L1516-L1521), [http2_client.go L1602-L1621](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L1602-L1621)
- **Spec:** gRPC over HTTP/2: 7.2 Deriving the status; gRPC over HTTP/2: Informational (1xx) responses

### [medium] Go: loadBalancingPolicy matched case-sensitively; unknown names silently become pick_first

- **Item:** SERVICE_CONFIG-8
- **Summary:** A service config using the proto's own `"ROUND_ROBIN"` value, or a misspelled policy name, silently gets `pick_first` instead of being matched case-insensitively or rejected.
- **Description:** `balancer.Get` is case-sensitive by default (`GRPC_GO_EXPERIMENTAL_CASE_SENSITIVE_BALANCER_REGISTRIES` defaults to true), and `parseServiceConfig` replaces any unregistered `loadBalancingPolicy` name with `pick_first`. The spec requires case-insensitive matching and that an unregistered name (with `loadBalancingConfig` unset) makes the service config invalid. Still present on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/service_config.go#L188-L197, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer/balancer.go#L84-L97, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/envconfig/envconfig.go#L95
- **Spec:** Service Config: 5.3 `loadBalancingPolicy` (deprecated)

### [medium] priority selection has no CONNECTING pass and deactivates lower priorities on every switch

- **Item:** PRIORITY-1
- **Summary:** Go's `syncPriority` never falls back to the highest-priority CONNECTING child (after its failover timer expired); it picks the last priority instead. `switchToChild` always deactivates lower priorities, even when the chosen child is not READY or IDLE.
- **Description:** gRFC A56 and the spec: if no child is READY or IDLE or has a pending failover timer, choose the first CONNECTING child, else the last child; lower priorities are deactivated only when a READY or IDLE child is chosen. With P0 CONNECTING after its timer expired and all others in TRANSIENT_FAILURE, Go reports the last child's TRANSIENT_FAILURE picker and fails RPCs that C++ and Java would queue. Still present on master c2165f27.
- **Evidence:** internal/xds/balancer/priority/balancer_priority.go (syncPriority, switchToChild, stopSubBalancersLowerThanPriority).
- **Spec:** `priority` LB Policy: Priority Selection Algorithm

### [medium] Go: xDS credentials apply TLS hostname verification to per-RPC and rewritten authorities

- **Item:** TLS-5
- **Summary:** Go's xDS client credentials return a plain `credentials.TLSInfo`, whose `ValidateAuthority` does `VerifyHostname` on the leaf certificate, so per-call and xDS-rewritten (A81) authorities fail unless the certificate has a matching DNS SAN.
- **Description:** The transport calls `ValidateAuthority` whenever `callHdr.Authority` is set, which includes A81 authority rewriting from the picker. With xDS mTLS certificates that carry no matching DNS SAN (for example SPIFFE certificates with only a URI SAN), every rewritten RPC fails. The spec and A81 say xDS credentials using SAN matching do no per-RPC check. C++ turns the check off for xDS credentials (`set_check_call_host(false)`).
- **Evidence:** Go master c2165f27: [credentials/xds/xds.go L148](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/credentials/xds/xds.go#L148) (returns `credentials.TLSInfo`), [credentials/tls.go L56-L68](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/credentials/tls.go#L56-L68), [internal/transport/http2_client.go L812-L818](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/http2_client.go#L812-L818).
- **Spec:** TLS: Per-RPC Authority Verification; Security Model: Authority and Authority Override

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

### [medium] xDS server never force-closes drained connections and has no drain grace time option

- **Item:** XDS_SERVER-4
- **Summary:** On a Listener update, Go sends GOAWAY to old connections but never closes them, and offers no API to configure a drain grace time.
- **Description:** The spec (per A36) drains connections accepted under the previous Listener and forcibly closes them after the drain grace time (default 10 minutes), which the xDS-enabled server API MUST let applications configure. Go's `maybeUpdateFilterChains` calls `Drain()` (GOAWAY only) and never closes the connection later; `xds/server_options.go` has no drain option. Long-lived streams therefore keep the old configuration (including old RBAC policy and certificates) indefinitely. C++ and Java implement both.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/server/listener_wrapper.go#L147-L199, https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/server/conn_wrapper.go#L139-L160, xds/server_options.go
- **Spec:** xDS-Enabled Servers: Configuration Updates and Draining

### [medium] Per-RPC authority mismatch fails with UNAVAILABLE instead of UNAUTHENTICATED

- **Item:** TLS-2
- **Summary:** When an RPC's authority does not match the server certificate, Go fails the RPC with `UNAVAILABLE` instead of `UNAUTHENTICATED`.
- **Description:** The per-RPC authority check (`CallAuthority` override / xDS authority rewrite) is an authentication failure, not a transient one. `UNAVAILABLE` is retryable, so the call may be retried pointlessly against the same server. The spec requires `UNAUTHENTICATED`.
- **Evidence:** grpc-go `internal/transport/http2_client.go` (`NewStream`, call authority validation against `AuthInfo`).
- **Spec:** TLS: Per-RPC Authority Verification

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
- **Spec:** Server (`05-server/01-server.md`), "Forced Shutdown" → "Waiting for Handlers".

### [medium] Oversized headers reset the stream (server) or report INTERNAL (client) instead of RESOURCE_EXHAUSTED

- **Item:** R50, R2
- **Summary:** Go answers oversized request headers with `RST_STREAM(FRAME_SIZE_ERROR)` and no gRPC status on the server, and reports `INTERNAL` on the client when received headers or trailers exceed the limit, whereas the spec says both sides SHOULD use `RESOURCE_EXHAUSTED`.
- **Description:** When request headers exceed the limit, the Go server resets the stream without a status, so the client sees a generic transport error (usually `INTERNAL`) and can't tell why the RPC failed. When a Go client receives response headers or trailers over its limit, it fails the call with `INTERNAL` ("peer header list size exceeded limit"). The spec says both sides SHOULD fail the RPC with `RESOURCE_EXHAUSTED` (and on the server allows a reset only when a status can't be sent).
- **Evidence:** grpc-go cbf30c4130: [http2_server.go L389-L399](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_server.go#L389-L399) (server resets on `frame.Truncated`), [http2_client.go L1525-L1531](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L1525-L1531) (client `INTERNAL`)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), Size Limits; gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), Header list size; Server Behavior (`05-server/01-server.md`), Request Validation

### [medium] RLS adaptive throttling never triggers

- **Item:** R133
- **Summary:** `RegisterBackendResponse` is never called, so the throttler's counts stay at zero and it never throttles.
- **Description:** The adaptive throttler is created per control channel, but lookup results are never reported to it. The throttling probability is therefore always 0. A failing or overloaded lookup server keeps receiving lookups at full rate. The spec requires completions to be counted.
- **Evidence:** `balancer/rls/control_channel.go` (`throttler` interface, `lookup`); `balancer/rls/internal/adaptive/adaptive.go` `RegisterBackendResponse` (no production callers).
- **Spec:** `04-client-channel/lb-policies/rls.md`, "Adaptive Throttling"

### [medium] RLS children may not receive resolver updates when the RLS config is unchanged

- **Item:** R133
- **Summary:** `rlsBalancer.UpdateClientConnState` returns early when the new config equals the current one, before it saves or forwards the new resolver state.
- **Description:** With xDS, each new `XdsConfig` arrives as a resolver attribute while the RLS config usually stays the same. The `cds` children would then keep an old `XdsConfig`, and dynamically subscribed clusters might never appear. The spec requires every parent update to be passed to all children. Confirmed by reading the v1.82.0 code that the early return skips saving and forwarding the resolver state; the effect on `cds` children is not verified with a test. The same happens when the RLS config changes only in fields that do not affect children (for example `maxAge` or `lookupService`): `handleChildPolicyConfigUpdate` returns early when `childPolicyName`, `childPolicyConfigTargetFieldName`, and `childPolicyConfig` are unchanged, so the new resolver state is saved but not forwarded (audit W2-09-016).
- **Evidence:** `balancer/rls/balancer.go` `UpdateClientConnState` (the early return around lines 307-311); cbf30c4130: [balancer.go L432-L435](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/rls/balancer.go#L432-L435).
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

### [medium] Subchannel metrics emit wrong `grpc.security_level` label values

- **Item:** audit (W2-05-015)
- **Summary:** Go fills the `grpc.security_level` label on `grpc.subchannel.open_connections` with `credentials.SecurityLevel.String()`, giving `"NoSecurity"`, `"IntegrityOnly"`, and `"PrivacyAndIntegrity"`, not the spec values `"none"`, `"integrity_only"`, and `"privacy_and_integrity"`.
- **Description:** gRFC A94 and the metric catalog define the allowed values of the `grpc.security_level` label as `none`, `integrity_only`, and `privacy_and_integrity`. `addrConn.securityLevelLocked` returns `ci.GetCommonAuthInfo().SecurityLevel.String()`, so Go's values differ from the other implementations, and dashboards or alerts written against the spec values don't match Go.
- **Evidence:** grpc-go cbf30c4130: [clientconn.go L1458-L1477](https://github.com/grpc/grpc-go/blob/cbf30c4130/clientconn.go#L1458-L1477), [credentials.go L74-L85](https://github.com/grpc/grpc-go/blob/cbf30c4130/credentials/credentials.go#L74-L85)
- **Spec:** Metric Catalog (`08-observability/04-metrics.md`), Common Attributes (Labels)

### [medium] Retry exhaustion rewrites the final status message

- **Item:** audit (W2-09-007)
- **Summary:** When `maxAttempts` is reached, Go wraps the last attempt's error as `"max retries exhausted: failed after N attempts: rpc error: code = ... desc = ..."`, so the status the application sees has a different message from the server's.
- **Description:** The spec says that when attempts are exhausted the RPC fails with the status of its last attempt. `csAttempt.shouldRetry` returns `fmt.Errorf("max retries exhausted: failed after %d attempts: %w", cs.numRetries+1, err)`, and this error is returned to the application. `status.FromError` finds the wrapped status through `errors.As`, but sets `Message = err.Error()`. So `status.Convert(err).Message()` holds the whole wrapped string, and a direct `err.(interface{ GRPCStatus() *Status })` type assertion fails. The code and details are kept.
- **Evidence:** grpc-go cbf30c4130: [stream.go L879-L881](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L879-L881), [stream.go L910-L917](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L910-L917), [status.go L113-L125](https://github.com/grpc/grpc-go/blob/cbf30c4130/status/status.go#L113-L125)
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), Behavior

### [medium] advancedtls CRL providers: static provider skips unparseable CRLs, directory provider fails creation on a read error, and the error callback runs per file

- **Item:** audit (W2-10-016)
- **Summary:** `NewStaticCRLProvider` logs and skips CRLs it can't parse instead of failing. `NewFileWatcherCRLProvider` fails if the directory can't be read at creation. `scanCRLDirectory` calls `CRLReloadingFailedCallback` once per failed file, and twice when the directory can't be opened.
- **Description:** The spec says static provider creation fails if any CRL can't be parsed. Go's `NewStaticCRLProvider` returns no error and only logs a warning, so a malformed CRL silently becomes "no CRL for this issuer", which is `Undetermined` and fails open if so configured. For the directory-reloading provider, the spec says errors in the first read don't make creation fail, and the error callback is called at most once per reload pass with one error describing every failed file. Go's `validate()` returns an error when `os.ReadDir` fails. `scanCRLDirectory` calls the callback for each unreadable file, and when `os.Open` fails it calls it again for the following `ReadDir` error on the nil `*os.File`.
- **Evidence:** grpc-go cbf30c4130: [crl_provider.go L65-L77](https://github.com/grpc/grpc-go/blob/cbf30c4130/security/advancedtls/crl_provider.go#L65-L77), [crl_provider.go L130-L137](https://github.com/grpc/grpc-go/blob/cbf30c4130/security/advancedtls/crl_provider.go#L130-L137), [crl_provider.go L179-L213](https://github.com/grpc/grpc-go/blob/cbf30c4130/security/advancedtls/crl_provider.go#L179-L213)
- **Spec:** TLS (`06-security/02-tls.md`), Static CRL Provider; Directory-Reloading CRL Provider

### [medium] ORCA recorders lose concurrent updates and accept NaN

- **Item:** audit (W2-12-015)
- **Summary:** `serverMetricsRecorder`, which backs both `ServerMetricsRecorder` and the per-call `CallMetricsRecorder`, updates its state with an unsynchronized load-copy-store, so concurrent updates can be lost. Its range checks don't reject `NaN`.
- **Description:** The spec allows recorder operations to be called concurrently from any thread, with last write winning per metric. It also says recorders MUST ignore values outside each metric's valid range. Every Set/Delete method does `copyServerMetrics(s.state.Load())`, changes one field, and calls `s.state.Store(...)`. Two goroutines updating different metrics at the same time can each store a copy without the other's change, so one update is lost until that metric is set again. The checks `if val < 0` and `if val < 0 || val > 1` are false for `math.NaN()`, so `NaN` is stored and reported for CPU, memory, application utilization, QPS, EPS, and named utilizations.
- **Evidence:** grpc-go cbf30c4130: [server_metrics.go L144-L146](https://github.com/grpc/grpc-go/blob/cbf30c4130/orca/server_metrics.go#L144-L146), [server_metrics.go L196-L352](https://github.com/grpc/grpc-go/blob/cbf30c4130/orca/server_metrics.go#L196-L352), [call_metrics.go L78](https://github.com/grpc/grpc-go/blob/cbf30c4130/orca/call_metrics.go#L78)
- **Spec:** Backend Metrics (ORCA) (`07-services/03-orca.md`), Data Model; Per-Call Recorder; Per-Server Recorder

### [medium] XdsClient metrics use internal Go type names for `grpc.xds.resource_type`

- **Item:** audit (W2-13-016)
- **Summary:** The XdsClient records `"ListenerResource"`, `"RouteConfigResource"`, `"ClusterResource"`, and `"EndpointsResource"` as the `grpc.xds.resource_type` label value, instead of the xDS resource type name (for example `envoy.config.listener.v3.Listener`).
- **Description:** The spec defines `grpc.xds.resource_type` on `grpc.xds_client.resource_updates_valid`, `grpc.xds_client.resource_updates_invalid`, and `grpc.xds_client.resources` as the xDS resource type, for example `envoy.config.listener.v3.Listener`. Go fills the label from `ResourceType.TypeName`, which holds Go-internal identifiers, so the label values do not match other implementations and cross-language dashboards break.
- **Evidence:** grpc-go cbf30c4130: [resource_types.go L28-L53](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/resource_types.go#L28-L53), [authority.go L372-L375](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/authority.go#L372-L375), [authority.go L403-L406](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/authority.go#L403-L406), [authority.go L951-L960](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/authority.go#L951-L960), [metrics_test.go L153](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/metrics_test.go#L153)
- **Spec:** Metric Catalog (`08-observability/04-metrics.md`), Common Attributes (Labels); XdsClient Metrics

### [medium] Binary logging never applies the header limit to `Trailer.metadata`

- **Item:** audit (W2-14-019)
- **Summary:** `TruncatingMethodLogger.Build` truncates `ClientHeader` and `ServerHeader` metadata and `Message` data, but not `Trailer` metadata. Trailing metadata is always logged in full with `payload_truncated = false`, whatever the `h:<N>` limit.
- **Description:** The header limit (`h:<N>`, or no headers when only `m` is given) applies to logged metadata entries, and `payload_truncated` is set when any entry is omitted. The payload type switch in `Build` has no case for `*binlogpb.GrpcLogEntry_Trailer`, so `EVENT_TYPE_SERVER_TRAILER` entries ignore the limit.
- **Evidence:** grpc-go cbf30c4130: [method_logger.go L97-L105](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/binarylog/method_logger.go#L97-L105)
- **Spec:** Binary Logging (`08-observability/07-binary-logging.md`), Truncation

### [medium] Binary logging omits half-close on non-client-streaming RPCs, never logs server-side cancel, and logs nothing for calls that fail before a stream is created

- **Item:** audit (W2-14-021)
- **Summary:** Go logs `EVENT_TYPE_CLIENT_HALF_CLOSE` only for client-streaming and bidi RPCs. It never logs `EVENT_TYPE_CANCEL` on the server. On the client it logs nothing (no `CLIENT_HEADER`, no locally generated `SERVER_TRAILER`) when the first attempt fails before a stream exists.
- **Description:** The spec logs these events: `EVENT_TYPE_CLIENT_HALF_CLOSE` when the client half-closes (client) or the half-close is received (server); `EVENT_TYPE_CANCEL` when the server detects cancellation; and, on the client, a `SERVER_TRAILER` for a status generated locally to report a failure. In Go: (1) for `!desc.ClientStreams`, the client's `SendMsg` sets `sentLast` without logging a half-close, and the server's post-message EOF check returns without logging. (2) Server-side code never logs `binarylog.Cancel`; only `ServerHeader`/`ServerTrailer` are logged. (3) If the first `withRetry` in `newClientStreamWithParams` fails (for example a fail-fast RPC on a `TRANSIENT_FAILURE` channel), the function returns before `ClientHeader` is logged, and `cs.finish` (which logs the trailer) is never called.
- **Evidence:** grpc-go cbf30c4130: [stream.go L487-L500](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L487-L500), [stream.go L1080-L1082](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L1080-L1082), [stream.go L1166-L1188](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L1166-L1188), [stream.go L1227-L1235](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L1227-L1235), [stream.go L2005-L2015](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L2005-L2015), [server.go L1477-L1515](https://github.com/grpc/grpc-go/blob/cbf30c4130/server.go#L1477-L1515)
- **Spec:** Binary Logging (`08-observability/07-binary-logging.md`), What Is Logged

### [medium] ring_hash ring sizes: explicit 0 treated as "use default", and legacy `RING_HASH` clusters not validated at CDS time

- **Item:** R23; audit (W2-16-013)
- **Summary:** The ring_hash config parser treats an explicit `minRingSize`/`maxRingSize` of 0 as unset and substitutes the default instead of rejecting the config. Separately, for legacy `lb_policy: RING_HASH` Clusters, the converted config is never parsed with the LB policy registry during CDS validation, so out-of-range (0 or > 8388608) and inverted (`min > max`) ring sizes are ACKed.
- **Description:** The spec says both sizes MUST be in [1, 8388608], with min ≤ max, and that an explicit 0 is invalid, not "use the default". These checks apply to the configured values, before the local cap. `ringhash.parseConfig` unmarshals into plain `uint64` fields and replaces 0 with 1024/4096. This applies to any ring_hash config (service config JSON as well as xDS). A config that one client rejects and another accepts is an interop hazard. For xDS, Cluster: Legacy `lb_policy` requires the converted config to parse with the gRPC LB policy registry or the resource is rejected. Go runs that parse only when `load_balancing_policy` is set. The legacy `RING_HASH` branch builds the JSON without validating it, so bad sizes are ACKed and the error appears only later, when the cds balancer parses its child config.
- **Evidence:** grpc-go cbf30c4130: [config.go L37-L56](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/ringhash/config.go#L37-L56), [unmarshal_cds.go L126-L142](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L126-L142), [unmarshal_cds.go L178-L193](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L178-L193)
- **Spec:** `ring_hash` LB Policy (`04-client-channel/lb-policies/ring_hash.md`), Configuration and Validation; Cluster (`09-xds/04-resources/04-cluster.md`), Legacy `lb_policy`; xDS LB Policies (`09-xds/06-lb-policies.md`), xDS LB Policy Registry

### [medium] `grpc.lb.backend_service` is set only on successful picks

- **Item:** audit (W2-17-013)
- **Summary:** Go sets the `grpc.lb.backend_service` (and `grpc.lb.locality`) optional labels in the `xds_cluster_impl` picker only after the child picker returns a SubConn. Dropped, circuit-breaker-failed, failed, and queued picks carry no backend service label.
- **Description:** A picker that has a label value MUST supply it on every pick, whatever the result (complete, queue, or fail), so that attempts ending with `UNAVAILABLE` or `DEADLINE_EXCEEDED` while waiting for a pick still carry the label. The spec has the `cds` policy's picker set `grpc.lb.backend_service` on every pick for a non-aggregate cluster. Go calls `stats.UpdateLabels` with the cluster name only at the end of `clusterimpl`'s `Pick`, after the drop, circuit-breaker, and child-pick error returns.
- **Evidence:** grpc-go cbf30c4130: [picker.go L97-L161](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/balancer/clusterimpl/picker.go#L97-L161)
- **Spec:** Instrumentation Architecture (`08-observability/02-instrumentation.md`), Picker-Supplied Optional Labels; `cds` LB Policy (`09-xds/lb-policies/cds.md`), Picker Implementation

### [medium] Server Listener parsing skips validation of never-matching filter chains and deviates on `rds` source, HCM count, and CIDR `prefix_len`

- **Item:** audit (W2-16-008, W2-18-011, W2-18-013)
- **Summary:** Go's server `Listener` parser: (1) drops never-matching `FilterChain`s before validating them or checking uniqueness, and NACKs a Listener whose chains are all never-matching when there is no `default_filter_chain`; (2) NACKs `rds.config_source.self` in a filter chain's HCM; (3) accepts more than one `HttpConnectionManager` in `FilterChain.filters`; (4) NACKs a `CidrRange.prefix_len` above 32/128 instead of clamping it.
- **Description:** The spec says: every `filter_chains` entry MUST be valid, and chains with always-failing criteria MAY be pruned for matching but MUST still be included in the uniqueness check; at least one of `filter_chains`/`default_filter_chain` must be present (not matching; unmatched connections are closed); the server HCM's `rds` may use `ads` or `self`; `FilterChain.filters` MUST contain exactly one entry, an HCM; and CIDR `prefix_len` is clamped to [0, 32] / [0, 128] during normalization. In Go, `buildFilterChainMap` and the `addFilterChainsFor*` helpers return early for `destination_port`, `server_names`, unsupported `transport_protocol`, empty `transport_protocol` after a `raw_buffer` chain, and `application_protocols`, so those chains are never passed to `filterChainFromProto` or checked for overlap. The Listener is NACKed with "no supported filter chains and no default filter chain". `processNetworkFilters` rejects a non-`ads` config source and allows extra HCMs (with distinct names) after the first. `parsePrefixRanges` returns an error when `prefix_len` exceeds the address length.
- **Evidence:** grpc-go cbf30c4130: [unmarshal_lds.go L303-L314](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L303-L314), [unmarshal_lds.go L376-L392](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L376-L392), [unmarshal_lds.go L457-L498](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L457-L498), [unmarshal_lds.go L546-L565](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L546-L565), [filter_chain.go L84-L180](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/filter_chain.go#L84-L180)
- **Spec:** xDS-Enabled Servers (`09-xds/08-server.md`), Listener Validation; Matching Algorithm; Normalization and Uniqueness; Routing on the Server

### [medium] xDS RBAC NACKs unsupported protobuf audit loggers even when `is_optional` is true, and accepts a `TypedStruct.type_url` with no `/`

- **Item:** audit (W2-11-022)
- **Summary:** `buildLogger` calls `getCustomConfig` before it checks `is_optional`. `getCustomConfig` fails for any `typed_config` that is not a `TypedStruct` or `StdoutAuditLog` (including types not in the protobuf registry), so an optional but unsupported protobuf-configured logger NACKs the resource. Separately, `convertCustomConfig`'s check `len(strings.Split(typeURL, "/")) == 0` is always false, so a `TypedStruct.type_url` without `/` is accepted.
- **Description:** An entry in `audit_logging_options.logger_configs` whose logger type is not supported is ignored when `is_optional` is true, and NACKed only when it is false. Extension `type_url`s MUST contain a `/` followed by at least one character, or the resource is rejected. Go applies `is_optional` only when the type name was extracted successfully and no builder is registered.
- **Evidence:** grpc-go cbf30c4130: [converter.go L35-L58](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/rbac/converter.go#L35-L58), [converter.go L61-L74](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/rbac/converter.go#L61-L74), [converter.go L82-L90](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/rbac/converter.go#L82-L90)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), Audit Logging Configuration; Common Types (`09-xds/04-resources/01-common-types.md`), Extensions: `google.protobuf.Any` and `TypedStruct`

### [medium] pemfile provider: default refresh interval is 1 hour, and intervals under 1 second are not raised (negative values panic)

- **Item:** audit (W2-10-012)
- **Summary:** The programmatic `pemfile.NewProvider` defaults the refresh interval to 1 hour instead of 600 seconds. Neither the programmatic nor the xDS `file_watcher` path raises intervals under 1 second to 1 second, and a negative interval makes `time.NewTicker` panic.
- **Description:** The spec gives the file-watcher provider a default refresh interval of 600 seconds and raises values under 1 second to 1 second. Go's `pemfile` package uses `defaultCertRefreshDuration = 1 * time.Hour` when `Options.RefreshDuration` is 0. The xDS builder uses 10 minutes. `Options.validate()` does not check the duration, so a sub-second interval is used as is, and a negative one (for example `"refresh_interval": "-1s"` in the bootstrap) reaches `time.NewTicker` in the watcher goroutine, which panics.
- **Evidence:** grpc-go cbf30c4130: [watcher.go L44](https://github.com/grpc/grpc-go/blob/cbf30c4130/credentials/tls/certprovider/pemfile/watcher.go#L44), [watcher.go L80-L97](https://github.com/grpc/grpc-go/blob/cbf30c4130/credentials/tls/certprovider/pemfile/watcher.go#L80-L97), [watcher.go L110-L112](https://github.com/grpc/grpc-go/blob/cbf30c4130/credentials/tls/certprovider/pemfile/watcher.go#L110-L112), [watcher.go L254](https://github.com/grpc/grpc-go/blob/cbf30c4130/credentials/tls/certprovider/pemfile/watcher.go#L254), [builder.go L89-L97](https://github.com/grpc/grpc-go/blob/cbf30c4130/credentials/tls/certprovider/pemfile/builder.go#L89-L97)
- **Spec:** TLS (`06-security/02-tls.md`), File-Watcher Provider

### [medium] Initial DNS resolution failure applies the default service config and releases wait-for-ready RPCs

- **Item:** audit (possible item 16)
- **Summary:** When a DNS lookup fails, Go's dns resolver calls `ReportError`, which reports no service config error. Before the first successful resolution, the channel therefore applies the default (or empty) service config and dispatches queued RPCs, so wait-for-ready RPCs stop waiting for the first real config.
- **Description:** The spec's `dns` resolver reports a failed or empty lookup as a result whose endpoints field and service config field both hold an `UNAVAILABLE` error, so the channel stays in TRANSIENT_FAILURE until the first successful resolution and keeps RPCs queued (C++ does this). Go's `ReportError` → `updateResolverStateAndUnlock(resolver.State{}, err)` → `maybeApplyDefaultServiceConfig()` applies a config instead. The equivalent Java bug is "Initial resolution failure releases wait-for-ready RPCs from the resolver queue without a service config".
- **Evidence:** [dns_resolver.go L206-L213](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/resolver/dns/dns_resolver.go#L206-L213), [resolver_wrapper.go L148-L159](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/resolver_wrapper.go#L148-L159), [clientconn.go L794-L826](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/clientconn.go#L794-L826).
- **Spec:** Name Resolution: `dns` (lookup failure)

### [medium] Google default credentials panic when `ALTSPerRPCCreds` is set and ADC is missing

- **Item:** VENDOR-6
- **Summary:** With `ALTSPerRPCCreds` set and no ADC available, Go wraps a nil `perRPCCreds` in `dualPerRPCCreds`, which panics with a nil-interface call on the first non-ALTS RPC (or in `RequireTransportSecurity` if the ALTS credentials don't require security).
- **Description:** The spec requires that missing ADC either fails credential creation or fails RPCs with `UNAUTHENTICATED`. Go's `NewDefaultCredentialsWithOptions` ignores the `newADC` error and builds `dualPerRPCCreds{perRPCCreds: nil, ...}`; `GetRequestMetadata` calls `d.perRPCCreds.GetRequestMetadata` for non-ALTS connections, crashing the process through a public API.
- **Evidence:** grpc-go cbf30c41309983ce66c6a81abe569a75fd2b9dcd: [google.go L50-L73](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/credentials/google/google.go#L50-L73), [google.go L159-L178](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/credentials/google/google.go#L159-L178)
- **Spec:** Google Default Credentials: Application Default Credentials; Google Default Credentials: ALTS-Specific Call Credentials

### [medium] Ambient xDS errors are only logged, not added to cluster resolution notes

- **Item:** XDS_DEPMGR-4
- **Summary:** The XdsDependencyManager's ambient-error callbacks for Listener, Cluster, and Endpoint only log the error. The cluster resolution note is only the EDS/DNS error, and no new config is sent when an ambient error arrives.
- **Description:** The spec (following gRFC A88) says ambient errors for LDS, RDS, and the cluster's CDS resource go into each cluster's resolution note, which falls back to `xDS node ID:<id>`, and that ambient errors cause a new config to be delivered. Go only logs them, so a lost xDS stream never shows up in RPC failure messages. The node ID is added to error text instead (`annotateErrorWithNodeID`). The existing Go bug "LOGICAL_DNS cluster DNS error does not update the resolution note" is related but separate.
- **Evidence:** grpc-go v1.82.0: [xds_dependency_manager.go L591-L601](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L591-L601), [L698-L707](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L698-L707), [L766-L775](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L766-L775), [L380-L384](https://github.com/grpc/grpc-go/blob/v1.82.0/internal/xds/xdsdepmgr/xds_dependency_manager.go#L380-L384)
- **Spec:** Client Data Plane: Error handling (`09-xds/05-client.md`)

### [medium] `weighted_round_robin` does not clamp endpoint weights before building the scheduler

- **Item:** WRR-20
- **Summary:** Go builds its static-stride scheduler from the raw weights, with no clamping relative to the mean, so very uneven weights make picks expensive and can quantize a small positive weight to zero.
- **Description:** The spec requires clamping each weight to `[MIN_RATIO × mean, MAX_RATIO × mean]` (`MAX_RATIO` 10, `MIN_RATIO` in [0.01, 0.1]) before building the scheduler, as C++ and Java do, to bound how many entries a pick skips. Go scales the largest weight to 65535 and the rest proportionally. When one endpoint's weight dominates, `nextIndex` loops many times per pick (about once per endpoint in the worst case), which is the pick-cost problem that led C++ (grpc/grpc#33045) and Java (grpc/grpc-java#10480) to add clamping. A weight below about 1/131070 of the maximum also rounds to 0 in `uint16`, so that endpoint is never picked even though it reported a positive weight.
- **Evidence:** [scheduler.go L46-L84](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/balancer/weightedroundrobin/scheduler.go#L46-L84) (no clamping; `uint16(math.Round(scalingFactor * w))`), `edfScheduler.nextIndex` in the same file.
- **Spec:** `weighted_round_robin` LB Policy: Building the Scheduler

### [low] Control-plane status restriction does not rewrite `OK`

- **Item:** audit (W2-01-016)
- **Summary:** `IsRestrictedControlPlaneCode` omits `codes.OK`, so an OK status from a picker or call credentials is not rewritten to INTERNAL.
- **Description:** The spec lists `OK` first among the codes that MUST be rewritten to INTERNAL when a control-plane status reaches a call (picker Fail/Drop, call credentials). Go's check covers only INVALID_ARGUMENT, NOT_FOUND, ALREADY_EXISTS, FAILED_PRECONDITION, ABORTED, OUT_OF_RANGE, and DATA_LOSS. This can only happen with a custom error type whose `GRPCStatus()` returns a non-nil status with code OK (`status.Error(codes.OK, ...)` is nil), so it is rare. When it does happen, the RPC fails with status OK.
- **Evidence:** grpc-go cbf30c4130: [status.go L232-L238](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/status/status.go#L232-L238), [picker_wrapper.go L161-L168](https://github.com/grpc/grpc-go/blob/cbf30c4130/picker_wrapper.go#L161-L168), [http2_client.go L713](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L713)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), Status Codes from the Control Plane; Load Balancing (`04-client-channel/06-load-balancing.md`), Pick Results

### [low] `weighted_target` does not publish a new picker when only target weights change

- **Item:** audit (W2-08-018)
- **Summary:** A config update that changes only `targets[name].weight` updates the stored weight but sends a new picker only if some child calls `UpdateState` during the update.
- **Description:** The spec requires `weighted_target` to report its aggregate state and picker once after every update from the parent. Go pauses aggregator updates, calls `UpdateWeight` (which only changes the stored weight and does not mark an update as needed), forwards the update to the children, and resumes. `ResumeStateUpdates` publishes a picker only if a child reported state while updates were paused, or if all targets were removed. Go's endpointsharding-based children report synchronously, so they hide the problem. With a child policy that does not call `UpdateState` when its own config and endpoints are unchanged, the channel keeps the old picker with the old weights until some child next changes state.
- **Evidence:** grpc-go cbf30c4130: [weightedtarget.go L101-L102](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedtarget/weightedtarget.go#L101-L102), [weightedtarget.go L133-L136](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedtarget/weightedtarget.go#L133-L136), [aggregator.go L148-L159](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedtarget/weightedaggregator/aggregator.go#L148-L159), [aggregator.go L171-L180](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedtarget/weightedaggregator/aggregator.go#L171-L180)
- **Spec:** `weighted_target` LB Policy (`04-client-channel/lb-policies/weighted_target.md`), Updates from the Parent

### [low] RLS ignores child policy update errors

- **Item:** audit (W2-09-016)
- **Summary:** When a child rejects an update, RLS only logs the error. It does not request re-resolution, and it always returns success to its parent.
- **Description:** `buildAndPushChildPolicyConfigs` logs the error returned by the child's `UpdateClientConnState` and returns nil, and `rlsBalancer.UpdateClientConnState` always returns nil. The spec requires the policy to request re-resolution when a child rejects an update, and to return a status that combines the children's statuses.
- **Evidence:** grpc-go cbf30c4130: [balancer.go L476-L481](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/rls/balancer.go#L476-L481), [balancer.go L296-L354](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/rls/balancer.go#L296-L354)
- **Spec:** `rls` LB Policy (`04-client-channel/lb-policies/rls.md`), Updates from the Parent

### [low] `advancedtls` CRL checking also checks the trust anchor

- **Item:** audit (W2-10-016)
- **Summary:** `checkChain` checks revocation for every certificate in the verified chain, including the trust anchor at the end of the chain.
- **Description:** The spec says revocation checking covers every certificate in the verified chain except the trust anchor. Go's `checkChain` calls `checkCert` on every element, including the root. If the provider has no CRL issued by the root (for example when a self-signed leaf certificate is itself the trust anchor), the chain becomes `Undetermined`, and with `DenyUndetermined` set the handshake fails even though every certificate that should be checked is unrevoked.
- **Evidence:** grpc-go cbf30c4130: [crl.go L149-L167](https://github.com/grpc/grpc-go/blob/cbf30c4130/security/advancedtls/crl.go#L149-L167)
- **Spec:** TLS (`06-security/02-tls.md`), Certificate Revocation (CRL)

### [low] `ring_hash` config rejects JSON string values for `minRingSize` / `maxRingSize`

- **Item:** audit (W1-B-006)
- **Summary:** `ring_hash` decodes `minRingSize` and `maxRingSize` into plain `uint64` fields, so the canonical proto3 JSON form (a string such as `"1024"`) makes the config invalid.
- **Description:** The spec says service config uses the proto3 JSON mapping, in which 64-bit integers are JSON strings, and parsers MUST also accept JSON numbers. Go's `LBConfig` fields have no `,string` handling or custom unmarshaling, so a config produced by a standard proto3 JSON marshaler is rejected.
- **Evidence:** grpc-go cbf30c4130: [ringhash.go L34-L35](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/ringhash/ringhash.go#L34-L35), [config.go L37-L41](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/ringhash/config.go#L37-L41)
- **Spec:** Service Config (`04-client-channel/04-service-config.md`), Format; `ring_hash` LB Policy (`04-client-channel/lb-policies/ring_hash.md`), Configuration

### [low] `methodConfig` message size limits are not range-checked

- **Item:** audit (W1-B-009)
- **Summary:** Go accepts negative values and values above `2^32 - 1` for `maxRequestMessageBytes` and `maxResponseMessageBytes` instead of treating the service config as invalid.
- **Description:** In the spec these fields are uint32 and MUST be non-negative integers that fit in 32 bits. Go decodes them into `*int64` and only clamps values above `maxInt`. A negative value is accepted (and then rejects every message), and a value above `2^32 - 1` is accepted instead of making the config invalid.
- **Evidence:** grpc-go cbf30c4130: [service_config.go L152-L153](https://github.com/grpc/grpc-go/blob/cbf30c4130/service_config.go#L152-L153), [service_config.go L228-L241](https://github.com/grpc/grpc-go/blob/cbf30c4130/service_config.go#L228-L241)
- **Spec:** Service Config (`04-client-channel/04-service-config.md`), `methodConfig`

### [low] Client sends the application's `grpc-accept-encoding` and `grpc-previous-rpc-attempts` alongside its own

- **Item:** audit (W2-01-011)
- **Summary:** Go sets `grpc-accept-encoding` (and, on retry attempts, `grpc-previous-rpc-attempts`) itself, but does not filter those keys from outgoing application metadata, so the request carries both values.
- **Description:** The spec says that for a reserved key the implementation itself sets, the implementation's value MUST be sent and the application's value MUST NOT. The client's `isReservedHeader` filter covers `grpc-timeout`, `grpc-encoding`, `grpc-status`, `grpc-message`, `content-type`, `te`, and `user-agent`, but not `grpc-accept-encoding` or `grpc-previous-rpc-attempts` (the latter is left out on purpose so applications can set it). If an application puts either key in its outgoing metadata while Go also sets it, the request has two values for the key, and the server may use the application's value.
- **Evidence:** grpc-go cbf30c4130: [http2_client.go L613-L632](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L613-L632), [http2_client.go L649-L672](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L649-L672), [http_util.go L95-L115](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http_util.go#L95-L115)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), Reserved Keys

### [low] Server metadata set through `grpc.SetHeader` / `SendHeader` / `SetTrailer` is not validated

- **Item:** audit (W2-01-013)
- **Summary:** The package-level `grpc.SetHeader`, `grpc.SendHeader`, and `grpc.SetTrailer` (the only header APIs available to unary handlers) send metadata without validating keys or values, and `ServerStream.SetTrailer` logs invalid trailers but still sends them.
- **Description:** The spec says that if an application tries to send an invalid key or ASCII value, the implementation MUST NOT transmit it, and SHOULD report an error or MAY drop it. The server puts the raw transport stream in the handler context, so the package-level functions call `transport.ServerStream.SetHeader`/`SetTrailer`/`SendHeader` directly. Those functions only merge or write the metadata, and the header writer copies it onto the wire without checking it. The `grpc.ServerStream` methods `SetHeader` and `SendHeader` validate and return INTERNAL, but `SetTrailer` only logs the error and still sends the invalid metadata.
- **Evidence:** grpc-go cbf30c4130: [server.go L1309](https://github.com/grpc/grpc-go/blob/cbf30c4130/server.go#L1309), [server.go L1841-L1869](https://github.com/grpc/grpc-go/blob/cbf30c4130/server.go#L1841-L1869), [server.go L1931-L1941](https://github.com/grpc/grpc-go/blob/cbf30c4130/server.go#L1931-L1941), [server_stream.go L154-L181](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/server_stream.go#L154-L181), [stream.go L1844-L1852](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L1844-L1852)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), Reserved Keys

### [low] Malformed `xdstp:` names treated as old-style names, and context params re-emitted unescaped

- **Item:** audit (W2-15-004)
- **Summary:** `ParseName` treats any name without `://`, or one that fails `url.Parse`, as an old-style name, even if it starts with `xdstp:`. `Name.String()` rebuilds the query from decoded context parameters without percent-encoding them.
- **Description:** The spec says any name starting with `xdstp:` is a new-style name, and a new-style name that does not parse as a URI is invalid. Go instead turns `"xdstp:foo"` (no `//`), or an `xdstp://` name with a bad escape, into an old-style name, so it is watched on the top-level `xds_servers` instead of failing the watch. Separately, `ParseName` stores `parsed.Query()` values, which are already percent-decoded. `String()` then joins `k + "=" + v` into `RawQuery` without escaping. A context parameter whose key or value contains an encoded `&`, `=`, or `%` therefore produces a different name on the wire from the one the server uses. The spec only allows sorting the parameters as normalization.
- **Evidence:** grpc-go cbf30c4130: [name.go L56-L64](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/internal/xdsresource/name.go#L56-L64), [name.go L78-L87](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/internal/xdsresource/name.go#L78-L87), [name.go L97-L126](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/internal/xdsresource/name.go#L97-L126), [clientimpl_watchers.go L74-L89](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/clientimpl_watchers.go#L74-L89)
- **Spec:** XdsClient (`09-xds/03-xds-client.md`), Old-style and new-style names

### [low] Bootstrap `client_listener_resource_name_template` prefix check omits the trailing `/`

- **Item:** audit (W2-15-005)
- **Summary:** Bootstrap validation checks that an authority's `client_listener_resource_name_template` starts with `"xdstp://" + url.PathEscape(name)`, with no trailing `/`. A template for a different authority that has the configured name as a prefix is accepted.
- **Description:** The spec says a non-empty `client_listener_resource_name_template` MUST start with `xdstp://<authority_name>/`, or the bootstrap is invalid. Because Go leaves out the `/`, authority `"auth"` accepts a template starting with `"xdstp://auth2/..."`, which then resolves to a different authority. Go also builds both the check prefix and the default template with `url.PathEscape`. That escapes `;` and `,`, which RFC 3986 allows in an authority, so the default template for such names doesn't use authority percent-encoding as the spec says.
- **Evidence:** grpc-go cbf30c4130: [bootstrap.go L837-L849](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/bootstrap/bootstrap.go#L837-L849)
- **Spec:** Bootstrap (`09-xds/02-bootstrap.md`), Authority Object

### [low] CSDS sets `last_updated` for uncached resources and omits `error_state` for deletions and does-not-exist timeouts

- **Item:** audit (W2-15-014)
- **Summary:** Go's CSDS always fills `GenericXdsConfig.last_updated` from the cache metadata timestamp, so uncached entries report `0001-01-01T00:00:00Z`. LDS/CDS deletions and does-not-exist timer expiry clear the metadata and report no `error_state`.
- **Description:** The spec says `last_updated` is present only when a resource is cached. It also says `error_state` is present whenever the entry has an error, with `details` describing the deletion reason or the timer message (and, for deletions, the response's `version_info`). `authority.resourceConfig` calls `timestamppb.New(state.md.Timestamp)` unconditionally, so `REQUESTED`, `DOES_NOT_EXIST`, and uncached `NACKED` entries carry the zero time. When a resource is deleted from an LDS/CDS response, or the does-not-exist timer fires, Go sets `state.md = UpdateMetadata{Status: ServiceStatusNotExist}` with no `ErrState`, so CSDS shows `DOES_NOT_EXIST` without an `error_state`.
- **Evidence:** grpc-go cbf30c4130: [authority.go L495-L501](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/authority.go#L495-L501), [authority.go L544-L545](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/authority.go#L544-L545), [authority.go L876-L902](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/xdsclient/authority.go#L876-L902)
- **Spec:** Client Status Discovery Service (CSDS) (`09-xds/11-csds.md`), `GenericXdsConfig`; `error_state`

### [low] No API to send an individual message uncompressed on a compressed call

- **Item:** audit (W2-02-006); related: COMPRESSION-2
- **Summary:** Go sets compression only per call (`grpc.UseCompressor` on the client, `grpc.SetSendCompressor` on the server). It has no per-message option to send a single message with the compressed flag clear.
- **Description:** The spec requires the client and server call APIs to let the application send a single message uncompressed even when the call uses compression. The implementation MUST then send that message with the compressed flag clear. This matters for mitigating CRIME/BEAST-style attacks on sensitive messages in a compressed stream. `ClientStream.SendMsg(m any)` and `ServerStream.SendMsg(m any)` take no options. `prepareMsg` always compresses with the stream's compressor, and `PreparedMsg` uses the same compressor. C++ has `WriteOptions::set_no_compression()` and Java has `setMessageCompression(false)`.
- **Evidence:** grpc-go cbf30c4130: [stream.go L140](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L140) (`ClientStream.SendMsg`), [stream.go L1756](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L1756) (`ServerStream.SendMsg`), [stream.go L2030-L2047](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L2030-L2047) (`prepareMsg`)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), Configuration and Precedence; Client Call API; Server Call API

### [low] Entering IDLE keeps the previous service config, so an invalid config after leaving IDLE reuses it

- **Item:** audit (W2-04-012)
- **Summary:** When a `ClientConn` enters IDLE, Go closes the resolver and LB policy and resets `firstResolveEvent`, but keeps `cc.sc` and the installed ConfigSelector.
- **Description:** The spec says that when the idle timeout fires, the channel discards its current service config and ConfigSelector, so leaving IDLE waits for a fresh resolver result. Because `cc.sc` survives IDLE, `updateResolverStateAndUnlock` sees a previous valid config when the first resolver result after IDLE carries an invalid service config (`s.ServiceConfig.Err != nil`). It keeps using the pre-IDLE config instead of handling the result like a first result with an invalid config (`applyFailingLBLocked`).
- **Evidence:** grpc-go cbf30c4130: [clientconn.go L424-L466](https://github.com/grpc/grpc-go/blob/cbf30c4130/clientconn.go#L424-L466) (`initIdleStateLocked`, `enterIdleMode`), [clientconn.go L846-L858](https://github.com/grpc/grpc-go/blob/cbf30c4130/clientconn.go#L846-L858)
- **Spec:** Channel (`04-client-channel/02-channel.md`), Idle Timeout

### [low] DNS service config choice: empty `clientLanguage` or `clientHostname` list matches no client

- **Item:** audit (W2-04-017)
- **Summary:** In a DNS TXT `grpc_config` choice, an explicit empty `"clientLanguage": []` or `"clientHostname": []` makes the choice match no client, when it should match every client.
- **Description:** The spec says an absent or empty `clientLanguage` or `clientHostname` list matches every client. `rawChoice` decodes both fields as `*[]string`, and `containsString` returns true only when the pointer is nil. For `[]` the pointer is non-nil and the loop finds nothing, so `canaryingSC` skips the choice.
- **Evidence:** grpc-go cbf30c4130: [dns_resolver.go L419-L436](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/resolver/dns/dns_resolver.go#L419-L436), [dns_resolver.go L461-L468](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/resolver/dns/dns_resolver.go#L461-L468)
- **Spec:** Name Resolution (`04-client-channel/03-name-resolution.md`), Service Config Choices

### [low] Health check leaves the health state CONNECTING when the Watch stream fails to start

- **Item:** audit (W2-05-025)
- **Summary:** When `newStream` or `SendMsg` fails in `clientHealthCheck`, Go retries after backoff without reporting TRANSIENT_FAILURE, so the health state stays CONNECTING.
- **Description:** The spec says that when the `/grpc.health.v1.Health/Watch` call fails with any status other than `UNIMPLEMENTED`, the health state becomes TRANSIENT_FAILURE until the next attempt starts. `clientHealthCheck` sets CONNECTING before each attempt. If `newStream` returns an error, or `SendMsg` returns an error other than `io.EOF`, it goes straight to `continue retryConnection` and waits in `backoffFunc` without calling `setConnectivityState(connectivity.TransientFailure, ...)`. Only errors from `RecvMsg` report TRANSIENT_FAILURE.
- **Evidence:** grpc-go cbf30c4130: [client.go L62-L106](https://github.com/grpc/grpc-go/blob/cbf30c4130/health/client.go#L62-L106)
- **Spec:** Client-Side Health Checking (`04-client-channel/10-health-checking.md`), Client Workflow

### [low] weighted_round_robin does not rebuild the scheduler periodically with a single READY endpoint

- **Item:** audit (W2-07-010)
- **Summary:** Go starts the `weightUpdatePeriod` timer only when the picker has at least two READY endpoints. With one READY endpoint, the scheduler is never rebuilt periodically, so WRR metrics stop and weight expiration isn't observed.
- **Description:** The spec rebuilds the scheduler every `weightUpdatePeriod`, using a timer owned by the current picker, and records the WRR metrics on each build. `GetWeight()` resets `non_empty_since` when the weight has expired. `picker.start` returns early when `len(p.weightedPickers) == 1`. So with a single READY endpoint, no `grpc.lb.wrr.*` metrics are recorded after the picker is built. Also, `endpointWeight.weight()` never runs during that time, so `nonEmptySince` isn't cleared when the weight expires. If that endpoint stops reporting for longer than `weightExpirationPeriod`, then gets a fresh report just before a second endpoint becomes READY, its weight is used at once without the blackout period.
- **Evidence:** grpc-go cbf30c4130: [balancer.go L251-L309](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedroundrobin/balancer.go#L251-L309), [balancer.go L490-L509](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedroundrobin/balancer.go#L490-L509), [balancer.go L620-L655](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedroundrobin/balancer.go#L620-L655)
- **Spec:** `weighted_round_robin` LB Policy (`04-client-channel/lb-policies/weighted_round_robin.md`), Building the Scheduler; Blackout and Expiration; Metrics

### [low] least_request discards an endpoint's active-request counter when the endpoint leaves READY

- **Item:** audit (W2-07-016)
- **Summary:** `leastrequest` keeps counters only for currently READY endpoints. When an endpoint goes READY → non-READY → READY while still in the endpoint list, it gets a new counter starting at 0.
- **Description:** The spec keys each endpoint's `active_requests` counter by endpoint identity and keeps it across updates while the endpoint remains present. `leastRequestBalancer.UpdateState` builds its set from READY children only, and deletes the counter of any endpoint not in that set. If health checking or outlier detection marks an endpoint non-READY while long-lived streams are still open on its connection, the endpoint comes back with a counter of 0 and receives a burst of picks. The old trackers keep decrementing the discarded counter.
- **Evidence:** grpc-go cbf30c4130: [leastrequest.go L153-L209](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/leastrequest/leastrequest.go#L153-L209)
- **Spec:** `least_request` LB Policy (`04-client-channel/lb-policies/least_request.md`), Internal State; Outstanding Request Counters

### [low] `grpc-retry-pushback-ms` parsed as a 64-bit integer, and large values overflow to an immediate retry

- **Item:** audit (W2-09-007)
- **Summary:** Go parses `grpc-retry-pushback-ms` with `strconv.Atoi` and multiplies by `time.Millisecond` without a range check. Values outside 32-bit range are accepted, and values of 9223372036855 or more overflow to a negative duration and retry immediately.
- **Description:** The spec defines the value as an ASCII decimal signed 32-bit integer, and an unparseable value means "do not retry". `strconv.Atoi` accepts 64-bit values on 64-bit platforms (and a leading `+`). Values above `math.MaxInt32` are used as delays instead of being treated as unparseable. Once `time.Millisecond * time.Duration(pushback)` overflows `int64`, the timer fires at once and the RPC retries with no delay.
- **Evidence:** grpc-go cbf30c4130: [stream.go L846-L854](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L846-L854), [stream.go L883-L886](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L883-L886)
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), Server Pushback

### [low] Duplicate metadata keys from multiple channel-level call credentials overwrite each other

- **Item:** audit (W2-10-004)
- **Summary:** `http2Client.getTrAuthData` merges the metadata of all channel-level `PerRPCCredentials` into one `map[string]string`, so when two credentials return the same key only the last value is sent.
- **Description:** The spec says metadata from several call credentials (channel-level, per-call, or composite components) is combined, and duplicate keys keep all values. Go runs each channel-level credential in turn and does `authData[k] = v`, which drops earlier values for the same key. Channel-level and per-call metadata are kept separately and both sent, so only duplicates among channel-level credentials are affected.
- **Evidence:** grpc-go cbf30c4130: [http2_client.go L703-L731](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L703-L731), [http2_client.go L642-L647](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L642-L647)
- **Spec:** Security Model (`06-security/01-security-model.md`), Call Credentials; Call Credentials (`06-security/03-call-credentials.md`), Results

### [low] SPIFFE bundle map accepts non-`x509-svid` keys, and the peer SPIFFE ID rejects an empty path

- **Item:** audit (W2-10-017)
- **Summary:** `BundleMapFromBytes` uses go-spiffe's `spiffebundle.Parse`, which accepts `"use": "jwt-svid"` keys and silently skips unknown `use` values. `SPIFFEIDFromCert` returns no SPIFFE ID for a URI SAN with an empty path such as `spiffe://example.com`.
- **Description:** The spec requires every key in a trust domain's `keys` to have `"use": "x509-svid"`, and makes the whole map invalid if any entry is invalid. `spiffebundle.Parse` handles `x509-svid`, `jwt-svid`, and `wit-svid` and ignores other values, so Go loads bundle maps that the spec says are invalid. The spec also says a valid SPIFFE ID may have an empty path. Go's bundle verification accepts that (through `spiffeid.FromURI`), but `SPIFFEIDFromCert`, which fills `TLSInfo.SPIFFEID` for the TLS, xDS, and advancedtls credentials, rejects IDs with an empty path, so such peers have no SPIFFE identity.
- **Evidence:** grpc-go cbf30c4130: [spiffe/spiffe.go L43-L64](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/credentials/spiffe/spiffe.go#L43-L64), [spiffe.go L45-L75](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/credentials/spiffe.go#L45-L75)
- **Spec:** TLS (`06-security/02-tls.md`), SPIFFE Trust Bundle Map Verification; Bundle Map Format

### [low] Server span named `Recv.other` for unregistered or filtered methods

- **Item:** audit (W2-13-014)
- **Summary:** The OpenTelemetry server tracing handler names the server span from the metrics method name, which is `"other"` for unregistered methods and for methods the `MethodAttributeFilter` rejects. Those spans are named `Recv.other` instead of `Recv.<service>.<method>`.
- **Description:** The spec names the server span `Recv.<service>.<method>`, from the RPC's method path. The metrics cardinality rules (`other`) don't apply to span names. `serverTracingHandler.TagRPC` reuses `getOrCreateServerRPCInfo`, which replaces the method with `"other"` when `MethodAttributeFilter` returns false or the method isn't registered on the server (for example, RPCs served by an unknown-service handler). `traceTagRPC` then builds the span name from that value.
- **Evidence:** grpc-go cbf30c4130: [server_tracing.go L42-L46](https://github.com/grpc/grpc-go/blob/cbf30c4130/stats/opentelemetry/server_tracing.go#L42-L46), [server_tracing.go L55-L63](https://github.com/grpc/grpc-go/blob/cbf30c4130/stats/opentelemetry/server_tracing.go#L55-L63), [opentelemetry.go L240-L269](https://github.com/grpc/grpc-go/blob/cbf30c4130/stats/opentelemetry/opentelemetry.go#L240-L269)
- **Spec:** Tracing (`08-observability/05-tracing.md`), Span Structure

### [low] OpenTelemetry client tracing counts transparent retries in `previous-rpc-attempts`

- **Item:** audit (W2-13-015)
- **Summary:** The client tracing handler increments `previousRPCAttempts` on every attempt's `*stats.Begin` event, transparent retries included, so the `previous-rpc-attempts` attribute on attempt spans is too high after a transparent retry.
- **Description:** The spec defines `previous-rpc-attempts` as the number of earlier attempts on the call, not counting transparent retries. Go's own comment on `callInfo.previousRPCAttempts` says the same. However, `clientTracingHandler.HandleRPC` runs `ci.previousRPCAttempts.Add(1) - 1` for every `*stats.Begin` without checking `begin.IsTransparentRetryAttempt`.
- **Evidence:** grpc-go cbf30c4130: [opentelemetry.go L182-L184](https://github.com/grpc/grpc-go/blob/cbf30c4130/stats/opentelemetry/opentelemetry.go#L182-L184), [client_tracing.go L146-L152](https://github.com/grpc/grpc-go/blob/cbf30c4130/stats/opentelemetry/client_tracing.go#L146-L152)
- **Spec:** Tracing (`08-observability/05-tracing.md`), Client Attempt Span; Instrumentation Architecture (`08-observability/02-instrumentation.md`), Per-Attempt vs. Per-Call Accounting

### [low] Channelz reports unset `last_*_timestamp` fields as the Unix epoch

- **Item:** audit (W2-14-010)
- **Summary:** `channelz/internal/protoconv` converts zero-valued nanosecond counters with `timestamppb.New(time.Unix(0, v))` and checks `IsValid()`, which is true for the epoch. Timestamps for events that never happened are therefore reported as `1970-01-01T00:00:00Z` instead of being left unset.
- **Description:** `last_call_started_timestamp` (channels, subchannels, servers) and the socket fields `last_local_stream_created_timestamp`, `last_remote_stream_created_timestamp`, `last_message_sent_timestamp`, and `last_message_received_timestamp` have no value until the event occurs. The spec says the local-stream timestamp is normally unset on servers and the remote-stream timestamp is normally unset on clients. Go reports the epoch on idle entities, on every server socket's `last_local_stream_created_timestamp`, and on every client socket's `last_remote_stream_created_timestamp`.
- **Evidence:** grpc-go cbf30c4130: [channel.go L96-L98](https://github.com/grpc/grpc-go/blob/cbf30c4130/channelz/internal/protoconv/channel.go#L96-L98), [subchannel.go L43-L45](https://github.com/grpc/grpc-go/blob/cbf30c4130/channelz/internal/protoconv/subchannel.go#L43-L45), [server.go L42-L44](https://github.com/grpc/grpc-go/blob/cbf30c4130/channelz/internal/protoconv/server.go#L42-L44), [socket.go L91-L102](https://github.com/grpc/grpc-go/blob/cbf30c4130/channelz/internal/protoconv/socket.go#L91-L102)
- **Spec:** Channelz (`08-observability/06-channelz.md`), Channel and Subchannel Data; Server Data; `SocketData`

### [low] Binary logging sets `peer` on every client-side `EVENT_TYPE_SERVER_TRAILER`

- **Item:** audit (W2-14-020)
- **Summary:** `clientStream.finish` fills `ServerTrailer.PeerAddr` for every client RPC, not only for trailers-only responses (where no `ServerHeader` was logged).
- **Description:** On the client, `GrpcLogEntry.peer` is set only on `EVENT_TYPE_SERVER_HEADER`, or on `EVENT_TYPE_SERVER_TRAILER` for a trailers-only response. The `ServerTrailer` type's own comment says `PeerAddr` is needed only on the client for trailers-only RPCs, but `finish` sets it whenever the peer is known, without checking `cs.serverHeaderBinlogged`.
- **Evidence:** grpc-go cbf30c4130: [stream.go L1237-L1244](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L1237-L1244), [method_logger.go L333-L335](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/binarylog/method_logger.go#L333-L335)
- **Spec:** Binary Logging (`08-observability/07-binary-logging.md`), `GrpcLogEntry`

### [low] `HeaderPresentMatcher` treats a header with an empty value as absent

- **Item:** audit (W2-16-002, W2-11-021)
- **Summary:** `HeaderPresentMatcher.Match` computes `present := ok && len(vs) > 0` on the comma-joined value, so a header that is present with the value `""` counts as absent, both in xDS route matching and in xDS RBAC.
- **Description:** `present_match` tests whether the header is present, whatever its value. `valueFromMD` returns `("", true)` for a key whose only value is `""`, and the extra `len(vs) > 0` check (marked with a TODO in the code) turns that into "absent". As a result, `present_match: true` fails and `present_match: false` matches for such headers.
- **Evidence:** grpc-go cbf30c4130: [matcher_header.go L42-L48](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/matcher/matcher_header.go#L42-L48), [matcher_header.go L150-L154](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/matcher/matcher_header.go#L150-L154)
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), `HeaderMatcher`; xDS HTTP Filters (`09-xds/07-http-filters.md`), Mapping RBAC Fields to gRPC

### [low] Server Listener address and `envoy.config.core.v3.Address` metadata accept `port_value > 65535`; Listener `protocol` not checked

- **Item:** audit (W2-16-006, part of W2-18-013)
- **Summary:** The A86 `envoy.config.core.v3.Address` metadata converter accepts `port_value > 65535` (and rejects an explicit `0`). The server-side Listener parser checks neither `port_value <= 65535` nor `socket_address.protocol == TCP`.
- **Description:** Under Common Types: Addresses, an `Address` is valid only if its port is in `port_value` and at most 65535. `proxyAddressConverter.convert` rejects `GetPortValue() == 0` but has no upper bound. Under xDS-Enabled Servers: Listener Validation, a TCP Listener's `address` MUST have `protocol` `TCP` and `port_value` ≤ 65535, or the Listener is NACKed. `unmarshal_lds.go` reads only `address` and `port_value`.
- **Evidence:** grpc-go cbf30c4130: [metadata.go L122-L139](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/metadata.go#L122-L139), [unmarshal_lds.go L279-L292](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L279-L292)
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), Addresses; xDS-Enabled Servers (`09-xds/08-server.md`), Listener Validation

### [low] LDS and RDS parsers accept negative or malformed `max_stream_duration` / `grpc_timeout_header_max`

- **Item:** audit (W2-16-007)
- **Summary:** `unmarshal_lds.go` and `unmarshal_rds.go` call `AsDuration()` on `HttpConnectionManager.common_http_protocol_options.max_stream_duration` and on `RouteAction.max_stream_duration.{grpc_timeout_header_max,max_stream_duration}` without checking that the Duration is valid and non-negative.
- **Description:** Every `Duration` field gRPC reads MUST have `seconds` in [0, 315576000000] and `nanos` in [0, 999999999], or the resource is rejected. Go's CDS parser does these checks (`CheckValid()` and `< 0`, for example for outlier detection), but the LDS and RDS parsers accept negative or malformed values for these fields.
- **Evidence:** grpc-go cbf30c4130: [unmarshal_lds.go L121](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L121), [unmarshal_rds.go L357-L367](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_rds.go#L357-L367), [unmarshal_cds.go L691-L696](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L691-L696)
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), `google.protobuf.Duration`; Listener (Client Side) (`09-xds/04-resources/02-listener.md`), `HttpConnectionManager`; RouteConfiguration (`09-xds/04-resources/03-route-configuration.md`), Max Stream Duration

### [low] Aggregate Cluster parsing keys on `cluster_type.name` and does not check the `typed_config` type

- **Item:** audit (W2-16-015)
- **Summary:** Go recognizes an aggregate cluster by `cluster_type.name == "envoy.clusters.aggregate"`, then unmarshals `cluster_type.typed_config.value` as `ClusterConfig` without checking that `typed_config` is present or that its type is `envoy.extensions.clusters.aggregate.v3.ClusterConfig`.
- **Description:** The spec requires `cluster_type.typed_config` to be present, with type `envoy.extensions.clusters.aggregate.v3.ClusterConfig` (any other type is rejected), and says `cluster_type.name` is ignored. In Go, a Cluster with a different `name` but a valid `ClusterConfig` is rejected as an unsupported type. A missing `typed_config` decodes as an empty `ClusterConfig` and is rejected only because `clusters` is empty. A `typed_config` of another type whose field 1 happens to parse as strings is accepted.
- **Evidence:** grpc-go cbf30c4130: [unmarshal_cds.go L272-L282](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L272-L282)
- **Spec:** Cluster (`09-xds/04-resources/04-cluster.md`), Aggregate Clusters

### [low] Fault injection: `fixed_delay` not validated, and `max_active_faults` counts every RPC rather than injected faults

- **Item:** audit (W2-18-004, W2-18-005)
- **Summary:** The fault filter's config parser does not validate `delay.fixed_delay` as a Duration. The active-fault gauge counts every RPC that passes through a filter with `max_active_faults` set, and never counts faults injected by filters without that field.
- **Description:** The spec validates `delay.fixed_delay` as a `Duration` (non-negative, in range; else NACK). `parseConfig` only unmarshals the `HTTPFault`. The spec defines active faults as a single process-wide gauge: an RPC counts from the moment a delay or abort is injected until that fault finishes, and a fault is injected only if the gauge is below the effective `max_active_faults`. Go's `interceptor.NewStream` increments `activeFaults` before deciding whether to inject, for every RPC when `max_active_faults` is set, so non-faulted RPCs use up the limit. When `max_active_faults` is unset it skips the counter entirely, so those faults are invisible to filters that do set a limit.
- **Evidence:** grpc-go cbf30c4130: [fault.go L82-L95](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/fault/fault.go#L82-L95), [fault.go L152-L171](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/fault/fault.go#L152-L171), [fault.go L180-L186](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/fault/fault.go#L180-L186)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), Configuration (Fault Injection); Maximum Active Faults

### [low] LRS treats `send_all_clusters: false` with an empty `clusters` list as "send all clusters"

- **Item:** audit (W2-18-024)
- **Summary:** `recvFirstLoadStatsResponse` represents `send_all_clusters: true` as an empty cluster slice, and `LoadStore.stats` treats an empty slice as "report all clusters". A `LoadStatsResponse` with `send_all_clusters: false` and no `clusters` therefore gets load for every cluster instead of none.
- **Description:** When `send_all_clusters` is false, the client reports only clusters whose name is in `LoadStatsResponse.clusters`, which is none when the list is empty. Go merges both cases into `len(clusterNames) == 0`.
- **Evidence:** grpc-go cbf30c4130: [lrs_stream.go L226-L232](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/lrsclient/lrs_stream.go#L226-L232), [load_store.go L112-L122](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/lrsclient/load_store.go#L112-L122)
- **Spec:** Load Reporting (LRS) (`09-xds/10-load-reporting.md`), Responses

### [low] Client keepalive pings on wake from dormancy without checking the last read time

- **Item:** audit (W2-06-014)
- **Summary:** When keepalive is dormant (no active streams, `PermitWithoutStream` false) and a new stream wakes it, Go sends a keepalive PING right away, even if bytes were read on the connection within the last `KEEPALIVE_TIME`.
- **Description:** The spec sends a PING on a new stream created while dormant only if `now() - last_read_time >= KEEPALIVE_TIME`, and in either case resumes the timer. Go's `keepalive()` returns from `kpDormancyCond.Wait()` and pings unconditionally (`outstandingPing` was cleared before sleeping), without rereading `t.lastRead`. Dormancy starts only after a full `KEEPALIVE_TIME` with no reads, so the extra PING happens only when the peer sent data during dormancy (for example a server keepalive PING or SETTINGS).
- **Evidence:** grpc-go cbf30c4130: [http2_client.go L1857-L1880](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L1857-L1880)
- **Spec:** HTTP/2 Client Transport (`04-client-channel/08-transports/02-http2.md`), Keepalive

### [low] XdsClient builds every supported `channel_creds` entry, leaking unused credentials and validating entries after the selected one

- **Item:** audit (W2-15-002)
- **Summary:** `populateGRPCTransportConfigsFromServerConfig` calls `Build` on every `channel_creds` entry with a supported type, not only the selected (first supported) one. Cleanup functions are discarded, and an invalid later entry fails XdsClient creation.
- **Description:** gRPC uses the first `channel_creds` entry with a supported type, and entries after the selected one are not validated. The bootstrap parser does this correctly. But when the XdsClient config is built, `clientimpl.go` loops over all entries, builds a credentials bundle for each, and ignores the returned cleanup. For `tls` entries with certificate files, that leaves file-watcher providers that are never closed. It also returns an error if any later supported entry has an invalid config. The function also stores configs keyed by credential type (see the separate per-server overwrite bug).
- **Evidence:** grpc-go cbf30c4130: [clientimpl.go L262-L282](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/clientimpl.go#L262-L282), [bootstrap.go L536-L553](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/bootstrap/bootstrap.go#L536-L553)
- **Spec:** Bootstrap (`09-xds/02-bootstrap.md`), XdsServer Object

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

### [low] Go ignores healthCheckConfig changes until the subchannel reconnects

- **Item:** HEALTH-2
- **Summary:** Go reads the health-check service name only once, when pick_first registers its health listener after READY. A changed or removed `healthCheckConfig` takes effect only after the next reconnect.
- **Description:** `acBalancerWrapper.healthListenerRegFn` calls `cc.healthCheckConfig()` once and keeps `cfg.ServiceName` in the closure. pick_first calls `RegisterHealthListener` only on the READY transition. Nothing re-registers when the service config changes. Java and C++ restart or stop the stream on update. Checked on master.
- **Evidence:** [balancer_wrapper.go#L443-L463](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer_wrapper.go#L443-L463), [pickfirst.go#L642-L644](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/balancer/pickfirst/pickfirst.go#L642-L644)
- **Spec:** Health Checking: Client Workflow

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

### [low] Go: RST_STREAM FLOW_CONTROL_ERROR maps to RESOURCE_EXHAUSTED instead of INTERNAL

- **Item:** HTTP2-7
- **Summary:** `http2ErrConvTab` maps `http2.ErrCodeFlowControl` to `codes.ResourceExhausted`.
- **Description:** A received `RST_STREAM(FLOW_CONTROL_ERROR)` reports a flow-control protocol violation by the peer and should map to `INTERNAL`, as the spec, PROTOCOL-HTTP2.md, Java, and C++ do. Could be folded into the existing Go bug about unknown RST_STREAM codes, since it is the same table. Still present on master c2165f27.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/transport/http_util.go#L57
- **Spec:** gRPC over HTTP/2: 8.2 RST_STREAM

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

### [low] ring_hash does not canonicalize xDS IP strings before hashing

- **Item:** RING_HASH-4
- **Summary:** Go hashes `endpoint.Addresses[0].Addr` as given; for xDS this is `net.JoinHostPort` of the EDS address string as sent, so a non-canonical IPv6 spelling is not normalized.
- **Description:** The spec hashes the canonical `host:port` form of the first address. For DNS-resolved addresses Go's string is already canonical, but an EDS address such as "2001:db8:0:0::1" is hashed as written, giving ring positions that differ from C++ and Envoy. Still present on master c2165f27.
- **Evidence:** balancer/ringhash/ringhash.go (hashKey); internal/xds/xdsclient/xdsresource/unmarshal_eds.go (net.JoinHostPort of socketAddress.GetAddress()).
- **Spec:** `ring_hash` LB Policy: Ring Construction

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

### [low] Go: ORCA OOB and health-producer UNIMPLEMENTED are not recorded as subchannel trace events

- **Item:** CHANNELZ-2
- **Summary:** When the ORCA out-of-band stream, or a health-producer health-check stream, fails with `UNIMPLEMENTED`, Go only writes a grpclog error and records no channelz trace event.
- **Description:** A51 says the client records a channel trace event and logs at ERROR. C++ (`GRPC_CHANNELZ_LOG`) and Java (`subchannelLogger.log(ERROR, ...)`) do. Only Go's legacy health-check path (`addrConn.startHealthCheck`) uses `channelz.Error`. The health producer used by health-listener-based policies (`health/producer.go`) only calls `logger.Errorf` on `UNIMPLEMENTED`, as does the ORCA producer (audit; corrects the earlier note that Go's health path already records the event).
- **Evidence:** Go master c2165f27: [orca/producer.go L177-L179](https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/orca/producer.go#L177-L179); cbf30c4130: [health/producer.go L97-L105](https://github.com/grpc/grpc-go/blob/cbf30c4130/health/producer.go#L97-L105), [clientconn.go L1677-L1684](https://github.com/grpc/grpc-go/blob/cbf30c4130/clientconn.go#L1677-L1684)
- **Spec:** Channelz: Required Events

### [low] xDS retry max_interval < base_interval not rejected and 1ms floor not applied

- **Item:** XDS_ROUTING-8
- **Summary:** Go's `generateRetryConfig` does not check `max_interval >= base_interval` and does not raise sub-millisecond intervals to 1ms.
- **Description:** The spec (per A44) requires `max_interval` ≥ `base_interval` (else reject) and treats values below 1ms as 1ms. Go checks only `> 0` for each and passes the values through unchanged.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_rds.go#L202-L220
- **Spec:** RouteConfiguration: Retry Policy

### [low] Duplicate cluster specifier plugin names are accepted (last one wins)

- **Item:** XDS_ROUTING-3, R133
- **Summary:** Go stores cluster specifier plugins in a map by name without checking for duplicates; a later plugin silently replaces an earlier one.
- **Description:** The spec rejects a RouteConfiguration with two `cluster_specifier_plugins` of the same `extension.name` (the Envoy proto says the names must be unique). Go keeps the last one.
- **Evidence:** https://github.com/grpc/grpc-go/blob/c2165f27d8bbc81e75aa14b82d23540882ac5f02/internal/xds/xdsclient/xdsresource/unmarshal_rds.go#L140-L168
- **Spec:** RouteConfiguration: Cluster Specifier Plugins

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

### [low] outlier_detection max_ejection_percent checked before ejection instead of against the resulting percentage

- **Item:** R18
- **Summary:** max_ejection_percent is compared with the percentage already ejected, so ejection can exceed the limit.
- **Description:** The success-rate and failure-percentage loops skip ejection only when `ejected% >= MaxEjectionPercent`, comparing the percentage already ejected, so the last ejection can exceed the limit. The spec (gRFC A50 as updated, matching Envoy's default with `always_eject_one_host` off) ejects an endpoint only if `100 * (ejected + 1) / endpoints <= max_ejection_percent`, so the limit is never exceeded and 0 disables ejection. Impact: in small endpoint sets gRPC ejects endpoints that Envoy would not; e.g. with the default 10% and 3 endpoints, gRPC ejects one (33%) while Envoy ejects none.
- **Evidence:** grpc-go `internal/xds/balancer/outlierdetection/balancer.go` (~line 757 and the matching check in `failurePercentageAlgorithm`).
- **Spec:** 04-client-channel/lb-policies/outlier_detection.md, "Success-Rate Algorithm" / "Failure-Percentage Algorithm"

### [low] Client does not send SETTINGS_ENABLE_PUSH=0

- **Item:** R5
- **Summary:** Go clients do not advertise SETTINGS_ENABLE_PUSH=0, so the HTTP/2 default of 1 (push enabled) applies.
- **Description:** The spec says clients SHOULD send ENABLE_PUSH=0 because gRPC never uses server push. Go's client SETTINGS frame omits it. No gRPC server pushes, so interop impact is negligible, but a non-gRPC server or proxy could legally send PUSH_PROMISE.
- **Evidence:** grpc-go `internal/transport/http2_client.go` (initial SETTINGS frame has no SettingEnablePush).
- **Spec:** 04-client-channel/08-transports/02-http2.md "SETTINGS"

### [low] Server header-size handling and SETTINGS_MAX_HEADER_LIST_SIZE advertisement

- **Item:** R9
- **Summary:** Go advertises SETTINGS_MAX_HEADER_LIST_SIZE only when explicitly configured, although it enforces a default limit.
- **Description:** The spec says implementations SHOULD advertise the header list size limit they enforce. Go enforces a default limit but advertises it only when the user configures one, so peers cannot avoid sending oversized headers. (The status-code part of Go's header-size handling is recorded under R2.)
- **Evidence:** grpc-go `internal/transport/http2_client.go` / `http2_server.go` (SettingMaxHeaderListSize added only if maxHeaderListSize is set).
- **Spec:** 03-wire-protocol/01-http2.md "Header list size"; 04-client-channel/08-transports/02-http2.md "SETTINGS"

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
    - The backoff failure is a status error, so wait-for-ready RPCs fail (a drop) instead of waiting.
    - `x-google-rls-data` is added even when the header data is empty.
  - The first backoff delay is about 1.6 s instead of 1 s.
- **Evidence:** `balancer/rls/config.go` (`maxCacheSize`, `parseRLSProto`); `balancer/rls/internal/keys/builder.go` `MakeBuilderMap`; `balancer/rls/picker.go` (`Pick`, `delegateToChildPoliciesLocked`, `handleRouteLookupResponse`); `balancer/rls/balancer.go` `handleControlChannelUpdate`.
- **Spec:** `04-client-channel/lb-policies/rls.md`

### [low] LOGICAL_DNS cluster DNS error does not update the resolution note

- **Item:** XDS_RESOLVER-1
- **Summary:** On a DNS error after an earlier success, Go keeps the previous addresses (correct) but does not set the resolution note to the DNS error.
- **Description:** The spec requires that, on a DNS resolution failure for a LOGICAL_DNS cluster, the resolution note is set to the DNS resolver's note or to `DNS resolution failed for <host:port>: <status>`, whether or not previous endpoints are kept. Go keeps the previous addresses but leaves the note unchanged, so the failure is not surfaced in later RPC failure messages or debugging output.
- **Evidence:** grpc-go `internal/xds/xdsdepmgr/xds_dependency_manager.go` `onDNSError`.
- **Spec:** `09-xds/05-client.md`, "LOGICAL_DNS clusters"

### [low] HTTP/2 client accepts signed `grpc-status` values

- **Item:** audit (W2-03-007)
- **Summary:** The client parses `grpc-status` with `strconv.ParseInt(value, 10, 32)`. That accepts a leading `+` or `-`, so `grpc-status: +0` becomes `OK` and `grpc-status: -1` becomes code 4294967295, instead of `UNKNOWN`.
- **Description:** `grpc-status` is `1*DIGIT` (unsigned decimal). A client that receives a `grpc-status` it cannot parse MUST report `UNKNOWN`. `operateHeaders` treats signed values as parseable and converts them with `codes.Code(uint32(code))`.
- **Evidence:** grpc-go cbf30c4130: [http2_client.go L1572-L1579](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L1572-L1579)
- **Spec:** gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), Grammar (Responses); `grpc-status`

### [low] `EndpointMap` does not deduplicate repeated addresses when computing endpoint identity

- **Item:** audit (W2-05-004)
- **Summary:** `resolver.EndpointMap` keys an endpoint by its sorted address list without removing duplicates, so `Endpoint{[A, A]}` and `Endpoint{[A]}` are treated as different endpoints.
- **Description:** The spec identifies an endpoint by the unordered set of its addresses. `encodeEndpoint` base64-encodes each `Address.Addr`, sorts them, and joins them, but does not deduplicate. An endpoint whose address list gains or loses a duplicate entry is treated as a new endpoint, and its per-endpoint state (children, weights, ejection state) is lost.
- **Evidence:** grpc-go cbf30c4130: [map.go L199-L212](https://github.com/grpc/grpc-go/blob/cbf30c4130/resolver/map.go#L199-L212)
- **Spec:** Load Balancing (`04-client-channel/06-load-balancing.md`), Endpoint Identity

### [low] Proxy address without a port has no default 443 in `State.Addresses` when the proxy resolves to multiple IPs

- **Item:** audit (W2-05-021)
- **Summary:** When the proxy from `HTTPS_PROXY` has no port and its hostname resolves to more than one address, `delegatingResolver` puts the bare proxy host (no port) in every `State.Addresses` entry, and dialing it fails.
- **Description:** With multiple resolved proxy addresses, `updateClientConnStateLocked` sets the legacy `Addresses` entries to `resolver.Address{Addr: r.proxyURL.Host}` "and lets net.Dial handle the proxy host name resolution". `r.proxyURL` comes from `http.ProxyFromEnvironment`, which does not add a default port. `proxyDial` calls `DialContext("tcp", addr.Addr)`, which fails with "missing port in address". The `Endpoints` list is built from the DNS-resolved proxy addresses, which do have port 443, so built-in policies are not affected. Only LB policies that consume `State.Addresses` fail to connect.
- **Evidence:** grpc-go cbf30c4130: [delegatingresolver.go L286-L346](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/resolver/delegatingresolver/delegatingresolver.go#L286-L346), [delegatingresolver.go L86-L92](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/resolver/delegatingresolver/delegatingresolver.go#L86-L92), [proxy.go L102-L108](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/proxy.go#L102-L108)
- **Spec:** HTTP CONNECT Proxy Support (`04-client-channel/09-proxy.md`), Choosing the Proxy

### [low] `weighted_round_robin` discards an endpoint's unexpired weight when the endpoint becomes READY

- **Item:** audit (W2-07-012)
- **Summary:** When an endpoint becomes READY, Go resets `lastUpdated` as well as `nonEmptySince`. With `blackoutPeriod` 0, a previously reported, unexpired weight is not used until a new load report arrives.
- **Description:** The spec's `OnEndpointBecomesReady()` resets only `non_empty_since` and keeps `weight` and `last_updated`. When `blackout_period` is 0, `GetWeight()` therefore keeps returning the stored weight until it expires. Go also sets `lastUpdated = time.Time{}`, and `endpointWeight.weight()` returns 0 for a zero `lastUpdated`, so the endpoint gets the mean weight until its next report. When `blackoutPeriod > 0` the two behave the same.
- **Evidence:** grpc-go cbf30c4130: [balancer.go L374-L384](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedroundrobin/balancer.go#L374-L384), [balancer.go L630-L635](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedroundrobin/balancer.go#L630-L635)
- **Spec:** `weighted_round_robin` LB Policy (`04-client-channel/lb-policies/weighted_round_robin.md`), Blackout and Expiration

### [low] `weighted_target` ignores child update errors

- **Item:** audit (W2-08-019)
- **Summary:** `weightedTargetBalancer.UpdateClientConnState` discards the error returned by each child's update and always returns nil, so the resolver gets no signal to back off and re-resolve.
- **Description:** The `weighted_target` spec says the policy returns a status that combines its children's statuses. Go calls `b.bg.UpdateClientConnState` for each target, assigns the result to `_` (with a TODO, "How to aggregate errors and return?"), and returns nil. The same gap exists in `priority` (PRIORITY-3).
- **Evidence:** grpc-go cbf30c4130: [weightedtarget.go L143-L169](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedtarget/weightedtarget.go#L143-L169)
- **Spec:** `weighted_target` LB Policy (`04-client-channel/lb-policies/weighted_target.md`), Updates from the Parent

### [low] retryThrottling accepts a non-integer `maxTokens`

- **Item:** audit (W2-09-008, W2-04-020); related: RETRY-5
- **Summary:** Go parses `retryThrottling.maxTokens` into a `float64` and checks only the range, so a non-integer value such as `10.5` is accepted instead of making the service config invalid.
- **Description:** The spec (and gRFC A6) requires `maxTokens` to be a JSON integer in (0, 1000]. `retryThrottlingPolicy.MaxTokens` is a `float64`, and `parseServiceConfig` checks only `mt <= 0 || mt > 1000`. The fractional value is then used as the throttler's maximum and threshold.
- **Evidence:** grpc-go cbf30c4130: [service_config.go L109-L121](https://github.com/grpc/grpc-go/blob/cbf30c4130/service_config.go#L109-L121), [service_config.go L260-L267](https://github.com/grpc/grpc-go/blob/cbf30c4130/service_config.go#L260-L267)
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), Retry Throttling

### [low] Wrong units on `grpc.subchannel.open_connections` and `grpc.lb.wrr.endpoint_weights`

- **Item:** audit (W2-13-017)
- **Summary:** Go registers `grpc.subchannel.open_connections` with unit `{attempt}` instead of `{connection}`, and `grpc.lb.wrr.endpoint_weights` with unit `{endpoint}` instead of `{weight}`.
- **Description:** The Metric Catalog requires these non-per-call metrics to be registered with exactly the listed units (gRFC A94 and A78 list the same units). The two Go descriptors appear to have copied the unit from neighboring metrics.
- **Evidence:** grpc-go cbf30c4130: [clientconn.go L128-L135](https://github.com/grpc/grpc-go/blob/cbf30c4130/clientconn.go#L128-L135), [balancer.go L86-L93](https://github.com/grpc/grpc-go/blob/cbf30c4130/balancer/weightedroundrobin/balancer.go#L86-L93)
- **Spec:** Metric Catalog (`08-observability/04-metrics.md`), Subchannel Metrics; Weighted Round Robin LB Policy Metrics; API Requirements

### [low] Binary log `ClientHeader.authority` ignores a per-call `CallAuthority` override

- **Item:** audit (W2-14-022)
- **Summary:** When a call uses the `CallAuthority` call option, the client sends that value as `:authority`, but the binary log `ClientHeader.authority` still records the channel's default authority.
- **Description:** The spec defines `ClientHeader.authority` as the `:authority` of the call. In `newClientStreamWithParams`, `callHdr.Authority` is set from `callInfo.authority`, and the transport uses it as `:authority`. The binary log entry is built with `Authority: cs.cc.authority`, so logs for calls with an authority override show the wrong value.
- **Evidence:** grpc-go cbf30c4130: [stream.go L412-L417](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L412-L417), [stream.go L491-L498](https://github.com/grpc/grpc-go/blob/cbf30c4130/stream.go#L491-L498), [http2_client.go L812-L821](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/transport/http2_client.go#L812-L821)
- **Spec:** Binary Logging (`08-observability/07-binary-logging.md`), Payload Messages

### [low] `RouteMatch.runtime_fraction` uses `<=` instead of `<`, so a 0% fraction still matches

- **Item:** audit (W2-16-005)
- **Summary:** `fractionMatcher.match` evaluates `RandInt64n(1000000) <= fraction`, which matches `N + 1` out of 1,000,000 RPCs. A route with `runtime_fraction` 0 still matches about one RPC in a million.
- **Description:** The spec evaluates a fraction of `N` per million by drawing `r` uniformly from [0, 1000000) and matching when `r < N`. Go uses `<=`, which is off by one: a 0% route can be selected, and every other fraction is 1 ppm too high.
- **Evidence:** grpc-go cbf30c4130: [matcher.go L108-L111](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/matcher.go#L108-L111)
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), Fractional Percentages

### [low] Circuit-breaker request counters are never released

- **Item:** audit (W2-17-018)
- **Summary:** `GetClusterRequestsCounter` stores a counter per (cluster name, EDS service name) in a process-wide map with no reference counting, so entries are never removed.
- **Description:** The spec makes circuit-breaker counters process-wide, reference-counted, and released when the last `xds_cluster_impl` instance drops its reference. In Go, `clusterRequestsCounter.clusters` only grows. Processes that see many distinct or short-lived cluster names (for example through RLS or cluster specifier plugins) leak one entry per (cluster, EDS service name) for the life of the process.
- **Evidence:** grpc-go cbf30c4130: [requests_counter.go L36-L63](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/requests_counter.go#L36-L63)
- **Spec:** `xds_cluster_impl` LB Policy (`09-xds/lb-policies/xds_cluster_impl.md`), Circuit Breaking; Shutdown

### [low] `typed_per_filter_config` accepts an empty key, and an optional `FilterConfig` with no `config`

- **Item:** audit (W2-18-002)
- **Summary:** Go does not NACK a `typed_per_filter_config` entry with an empty key. It also silently ignores a `FilterConfig` with `is_optional: true` whose `config` is unset (empty type URL) instead of NACKing it.
- **Description:** The spec NACKs an override map entry whose key is empty, and NACKs any filter `Any` whose `type_url` is empty or malformed. `is_optional` only allows ignoring a well-formed type that no filter registers. `processHTTPFilterOverrides` does not check the key. When the `FilterConfig` wrapper has no `config`, `validateHTTPFilterConfig` looks up the filter for type URL `""`, finds none, and because the entry is optional returns no error, so the entry is dropped.
- **Evidence:** grpc-go cbf30c4130: [unmarshal_lds.go L152-L173](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L152-L173), [unmarshal_lds.go L175-L211](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L175-L211)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), Override Configuration (`typed_per_filter_config`); Extracting the Filter Type

### [low] `file_watcher` provider rejects certificate and key files in different directories

- **Item:** audit (W2-18-021)
- **Summary:** `pemfile` validation fails when `filepath.Dir(certificate_file) != filepath.Dir(private_key_file)`. This rule is not in the spec, so valid programmatic and xDS bootstrap configurations are rejected.
- **Description:** The spec's validation rules for the file-watcher provider are only that the identity certificate and key are both set or both unset, and that at least one file is set. Go adds a same-directory requirement, citing cross-language consistency with a C-core limitation. C++ has no such check. Because the xDS `file_watcher` builder calls the same `validate()`, a bootstrap with the key in a different directory is rejected.
- **Evidence:** grpc-go cbf30c4130: [watcher.go L80-L97](https://github.com/grpc/grpc-go/blob/cbf30c4130/credentials/tls/certprovider/pemfile/watcher.go#L80-L97), [builder.go L99-L101](https://github.com/grpc/grpc-go/blob/cbf30c4130/credentials/tls/certprovider/pemfile/builder.go#L99-L101)
- **Spec:** TLS (`06-security/02-tls.md`), File-Watcher Provider; xDS Security (`09-xds/09-security.md`), `file_watcher` Plugin

### [low] LRS load store never discards stats for released clusters

- **Item:** audit (W2-18-026)
- **Summary:** The LRS `LoadStore` adds a `PerClusterReporter` for each (cluster, EDS service name) and per-locality counters, and never removes them after the last user releases them.
- **Description:** The spec makes LRS stats objects reference-counted. When one is released, its final counts are included in the next report and then discarded. Go's `LoadStore.clusters` map only grows, as its own comment notes ("new entries are added to this map, but never removed"). Released entries report nothing once their counters are zero, so the effect is memory growth proportional to the number of distinct clusters and localities seen for the life of the `LRSClient`.
- **Evidence:** grpc-go cbf30c4130: [load_store.go L44-L53](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/lrsclient/load_store.go#L44-L53), [load_store.go L204-L266](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/clients/lrsclient/load_store.go#L204-L266)
- **Spec:** Load Reporting (`09-xds/10-load-reporting.md`), Stats Model

### [low] Go fault-injection filter treats an unrecognized `FractionalPercent.denominator` as out of 100 instead of NACKing

- **Item:** XDS_FAULT-20 (converted review item)
- **Summary:** An unrecognized `FractionalPercent.denominator` in `HTTPFault` `delay.percentage` or `abort.percentage` is accepted at parse time and, per RPC, treated as a denominator of 100.
- **Description:** `Common Types` §5 (Fractional Percentages) requires any `denominator` other than `HUNDRED`, `TEN_THOUSAND`, or `MILLION` to reject the resource, and xDS HTTP Filters §8.1 applies that rule to the fault filter's percentages (Envoy's `percent.proto` marks `DenominatorType` `defined_only`; Java NACKs). Go validates the denominator only per RPC in `splitPct`, which falls back to 100 on error; the code's own TODO says the config "must be NACKed if an unrecognized denominator is seen".
- **Evidence:** grpc-go cbf30c4130: [fault.go L266-L277](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/fault/fault.go#L266-L277) (`splitPct`, called at L181 and L219).
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), Fractional Percentages; xDS HTTP Filters (`09-xds/07-http-filters.md`), Fault Injection: Configuration

### [low] Go NACKs RBAC configs with `action: LOG` that contain CEL conditions or disallowed header matchers

- **Item:** XDS_RBAC-20 (converted review item)
- **Summary:** Go's RBAC filter parser rejects `Policy.condition`, `Policy.checked_condition`, and `grpc-`/`:scheme` header matchers before checking for `RBAC.rules.action == LOG`, so a `LOG` instance that the spec says is ignored can NACK the Listener or RouteConfiguration.
- **Description:** xDS HTTP Filters §9.1 says that if `RBAC.rules.action` is `LOG`, "the entire instance is ignored, as if RBAC were not configured", and `Common Types` §1 rule 4 says errors inside an ignored entry do not cause the resource to be rejected (gRFC A41: "the policy will be completely ignored, as if RBAC was not configurated"). C++ (`ParseXdsRbac`) and Java (`RbacFilter.parseRbacConfig`) return before parsing `policies` when the action is `LOG`. Go's `parseConfig` walks every policy first and returns errors for CEL conditions and disallowed header names, and only then returns the no-op config for `RBAC_LOG`. This matters for control planes that share Envoy `LOG`-mode policies (which may use CEL) with proxyless gRPC servers.
- **Evidence:** grpc-go cbf30c4130: [rbac.go L58-L101](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/rbac/rbac.go#L58-L101) (policy checks at L60-L91, `RBAC_LOG` early return at L99). Compare C++ [xds_http_rbac_filter.cc L872-L876](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/xds/grpc/xds_http_rbac_filter.cc#L872-L876) and Java [RbacFilter.java L147-L148](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RbacFilter.java#L147-L148).
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), RBAC: Configuration Validation; Common Types (`09-xds/04-resources/01-common-types.md`), Validation Conventions

### [low] Go xDS server does not perform configuration error logging for unusable RDS resources or non-`non_forwarding_action` routes

- **Item:** XDS_SERVER-20 (converted review item)
- **Summary:** Go logs RDS resource and ambient errors only at Info level, with no recovery message, and does not log when a RouteConfiguration contains a route whose action is not `non_forwarding_action` (it only fails matching RPCs, logging per RPC at Info).
- **Description:** xDS-Enabled Servers §9 (from gRFC A36 "configuration error logging") says the server SHOULD log a warning each time it receives an update while an unusable RDS resource or a non-`non_forwarding_action` route will cause RPC failures, and SHOULD log a single message once no such error remains.
- **Evidence:** grpc-go cbf30c4130: [rds_handler.go L147-L183](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/server/rds_handler.go#L147-L183), [routing.go L45-L85](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/server/routing.go#L45-L85).
- **Spec:** xDS-Enabled Servers (`09-xds/08-server.md`), Configuration Error Logging

### [low] Go rejects aggregate clusters whose `cluster_type.name` is not `envoy.clusters.aggregate`

- **Item:** XDS_CDS-20
- **Summary:** `validateClusterAndConstructClusterUpdate` takes the aggregate path only when `cluster_type.name == "envoy.clusters.aggregate"`. Any other name, even with a valid `ClusterConfig` `typed_config`, falls through to "unsupported cluster type" and the Cluster is NACKed.
- **Description:** The spec (following gRFC A37's validation rules, which check only `cluster_type.typed_config` and its `type_url`) says `cluster_type.name` is ignored and the aggregate cluster is identified by the `typed_config` type. Go selects by name instead (and, separately, does not check the `typed_config` type URL; see the existing medium bug). C++ ignores the name.
- **Evidence:** grpc-go cbf30c4130: [unmarshal_cds.go L272-L284](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L272-L284)
- **Spec:** Cluster (`09-xds/04-resources/04-cluster.md`), Aggregate Clusters

### [low] `weighted_round_robin` accepts negative or NaN `qps`, utilization, and `eps` from load reports

- **Item:** audit (lbpol follow-up)
- **Summary:** `OnLoadReport` ignores a report only when utilization or `rps_fractional` is exactly 0, so negative or NaN values produce a negative or NaN weight, which the scheduler then converts to `uint16` with undefined results.
- **Description:** The spec ignores a report unless `qps > 0` and `utilization > 0` (which also ignores NaN), adds the error penalty only when `eps > 0`, and drops a non-positive resulting weight. C++ and Java check `> 0`. Go checks only `== 0`. A misbehaving backend that reports a negative or NaN value makes `weightVal` negative or NaN; `newScheduler` then computes `uint16(math.Round(scalingFactor * w))` on it (an out-of-range float-to-integer conversion, which Go leaves implementation-defined), so that endpoint's share is arbitrary until the weight expires. Related to possible review item "WRR: non-finite qps/eps".
- **Evidence:** [balancer.go L546-L566](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/balancer/weightedroundrobin/balancer.go#L546-L566), [scheduler.go L46-L84](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/balancer/weightedroundrobin/scheduler.go#L46-L84); compare C++ `weighted_round_robin.cc` L504-L506 (`qps > 0 && utilization > 0`, `eps > 0`) and Java `WeightedRoundRobinLoadBalancer.java` L382.
- **Spec:** `weighted_round_robin` LB Policy: Weights (OnReport)

### [low] ORCA recorders accept non-finite metric values

- **Item:** ORCA_SVC-20
- **Summary:** The recorders accept `+Infinity` for `cpu_utilization`, `application_utilization`, `rps_fractional`, and `eps`, and accept `NaN` and `±Infinity` for `request_cost` and `named_metrics` values.
- **Description:** The spec's valid ranges contain only finite numbers (`[0, ∞)` means finite non-negative values; `request_cost` and `named_metrics` take any finite value), and recorders MUST ignore values outside the valid range. The `[0, ∞)` setters reject only `val < 0` (`NaN` acceptance on those setters is already part of the bug "ORCA recorders lose concurrent updates and accept NaN"), and `SetRequestCost` / `SetNamedMetric` check nothing. A non-finite value in a report can corrupt the client-side `weighted_round_robin` weight.
- **Evidence:** [server_metrics.go L196-L352](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/orca/server_metrics.go#L196-L352).
- **Spec:** Backend Metrics (ORCA): Data Model

### [low] priority selection runs against the old priority list when a child rejects its update

- **Item:** PRIORITY-5
- **Summary:** When a started child rejects its update, Go runs priority selection immediately, against the old priority list, before the update finishes.
- **Description:** The spec says picker updates from children are ignored for priority selection while the policy applies an update, and selection runs once at the end. Go's `UpdateClientConnState` updates each existing child, then sets `b.priorities`, and only then sets `inhibitPickerUpdates`. When a child returns an error, `childBalancer.sendUpdate` sets it to TRANSIENT_FAILURE and synchronously calls `handleChildStateUpdate` → `syncPriority`, which runs over the old `b.priorities` and partly updated children. For example, if P0 rejects its config, Go can switch to P1, report P1's state (a CONNECTING picker if P1 hadn't started), start P1, and stop lower priorities, then stop P1 again if the new list doesn't contain it. C++ (`update_in_progress_`) and Java (`handlingResolvedAddresses`) set their guard before updating any child. Fix: set `inhibitPickerUpdates` (and `b.priorities`) before updating children. Separate from the existing PRIORITY-3 bug (update errors not returned).
- **Evidence:** grpc-go cbf30c4130: [balancer_child.go L112-L129](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/balancer/priority/balancer_child.go#L112-L129), [balancer.go L117-L208](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/balancer/priority/balancer.go#L117-L208), [balancer_priority.go L84-L121](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/balancer/priority/balancer_priority.go#L84-L121)
- **Spec:** `priority` LB Policy: 3.3 Updates from the Parent

### [low] ALTS frame type check ignores the upper three bytes

- **Item:** ALTS-5
- **Summary:** Go accepts ALTS frames whose 4-byte type is not exactly 6 as long as its low byte is 6 (for example `0x00000106`).
- **Description:** The spec requires the little-endian frame type to be exactly `0x00000006` and treats any other value as an error. Go checks `msgType&0xff != altsRecordMsgType`, so the upper three bytes are ignored. C++ and Java compare the full value. No conforming sender sets the upper bytes, so fixing this has no compatibility risk, and exact matching keeps those values available for future frame types.
- **Evidence:** grpc-go cbf30c4130: [record.go L271-L275](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/credentials/alts/internal/conn/record.go#L271-L275)
- **Spec:** ALTS: 6.5.6.1 Frames and Encryption

### [low] Retry throttling does not count failures of committed attempts

- **Item:** RETRY-20
- **Summary:** Go records no `retryThrottling` failure when an attempt fails with a retryable status, or with a "do not retry" pushback, after the RPC is committed (by response headers or by overflowing the retry buffer).
- **Description:** The spec says a failure that counts (a retryable or non-fatal status code, or a "do not retry" pushback) subtracts 1 from `token_count` even if the RPC is already committed to the attempt, as gRFC A6's "Every failed RPC will decrement the `token_count` by 1" requires. `csAttempt.shouldRetry` returns `false, err` as soon as `cs.committed` is set, or when `!a.transportStream.TrailersOnly()` (response headers received), before any `cs.retryThrottler.throttle()` call. A method that always commits before failing (server streaming, or requests larger than the retry buffer) adds `tokenRatio` on `OK` but never subtracts on a retryable failure.
- **Evidence:** `stream.go` `csAttempt.shouldRetry` (https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/stream.go#L813-L878).
- **Spec:** Retries and Hedging: Behavior; Retries and Hedging: Token Accounting

### [low] Channelz reports an empty `Address` oneof for non-TCP/UDS socket addresses

- **Item:** CHANNELZ-7
- **Summary:** For a socket address that is neither TCP/IP nor UDS (for example `udp`, `bufconn`, or a custom `net.Addr`), Go Channelz returns an `Address` with no variant set, so the address isn't shown at all.
- **Description:** The spec (following channelz.proto `OtherAddress`, "An address type not included above") says such an address SHOULD be reported as `other_address` with `name` set to a human-readable form. `addrToProto` handles only `ip`, `ip+net`, `tcp`, and `unix*`. For `udp` (there is a TODO) and any other network, it returns `&channelzpb.Address{}`. Suggested fix: return `other_address{name: addr.String()}` (C++ and Java already do this).
- **Evidence:** `channelz/internal/protoconv/socket.go` `addrToProto` (https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/channelz/internal/protoconv/socket.go#L56-L77).
- **Spec:** Channelz: Addresses

### [low] Channel trace event added for every resolver update

- **Item:** CHANNELZ-6
- **Summary:** Go adds a channel trace event with the full resolver state as JSON on every resolver update, even when the update changes nothing.
- **Description:** The spec (following gRFC A3, which says resolution events are traced only when "interesting" so that push-based resolvers don't flood the trace buffer) says implementations SHOULD NOT add a trace event for a resolution result that causes none of the listed changes (service config change, address count zero ↔ non-zero, new LB policy). `addChannelzTraceEvent` runs on every `UpdateState`/`NewAddress` and always calls `channelz.Infof` with `pretty.ToJSON(s)`, even when its list of changes is empty. With watch-based resolvers (for example xDS) and Go's fixed 30-event buffer, this evicts useful events such as connectivity changes. Suggested fix: add the event only when the list of changes is non-empty.
- **Evidence:** `resolver_wrapper.go` `addChannelzTraceEvent` (https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/resolver_wrapper.go#L188-L212); `internal/channelz/trace.go` (https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/channelz/trace.go#L31-L34).
- **Spec:** Channelz: Required Events

### [low] RBAC matches binary headers on decoded bytes instead of base64

- **Item:** AUTHZ-2
- **Summary:** Go RBAC header matchers compare a `-bin` header's decoded binary value instead of its unpadded base64 form.
- **Description:** The spec (following gRFC A41) says `-bin` headers are matched in unpadded base64 form, each value encoded separately and then joined with `,`. The transport base64-decodes `-bin` values into metadata (`decodeMetadataHeader`), and the RBAC header matchers compare those decoded values, so value matchers written against the base64 form never match. Presence matchers are unaffected.
- **Evidence:** `internal/transport/http2_server.go` (https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/transport/http2_server.go); `internal/xds/matcher/matcher_header.go` (https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/matcher/matcher_header.go).
- **Spec:** Authorization: Header Matching Rules

### [low] xDS extension type URLs compared including the `type.googleapis.com/` prefix

- **Item:** XDS_COMMON-1
- **Summary:** Go compares the full `type_url` string at several extension points, so any prefix other than `type.googleapis.com/` makes a supported type unknown.
- **Description:** The spec says the type name is the part of the `type_url` after the last `/` and the prefix is not checked. Go's `IsHTTPConnManagerResource`, `httpfilter.Get`, the metadata converter registry, and the `UpstreamTlsContext` check compare or key on the full URL including `type.googleapis.com/`.
- **Evidence:** grpc-go cbf30c4130: [type.go L60](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/type.go#L60), [httpfilter.go L202-L204](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/httpfilter.go#L202-L204), [metadata.go L56-L62](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/metadata.go#L56-L62), [unmarshal_cds.go L361-L363](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L361-L363)
- **Spec:** Common Types: Extensions: `google.protobuf.Any` and `TypedStruct`

### [low] Empty `safe_regex.regex` accepted in `StringMatcher` and `HeaderMatcher`

- **Item:** XDS_COMMON-20
- **Summary:** Go rejects empty `prefix`, `suffix`, and `contains` but accepts an empty `safe_regex.regex` / `safe_regex_match.regex`.
- **Description:** The spec (following Envoy's `RegexMatcher.regex` `min_len: 1`) requires the regex to be non-empty, else the resource is rejected. Go compiles the empty regex, which matches only the empty string.
- **Evidence:** grpc-go cbf30c4130: [string_matcher.go L116-L122](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/matcher/string_matcher.go#L116-L122), [header.go L46-L53](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/matcher/header/header.go#L46-L53)
- **Spec:** Common Types: `StringMatcher`; Common Types: `HeaderMatcher`

### [low] Fault injection: out-of-range `http_status` and missing `error_type` accepted

- **Item:** XDS_FAULT-2
- **Summary:** Go accepts a `FaultAbort.http_status` outside [200, 600) (it never aborts) and a `FaultAbort` with no `error_type`.
- **Description:** The spec follows Envoy: `http_status` MUST be in [200, 600) and the `error_type` MUST be set, else NACK. Go validates neither at config time; `grpcFromHTTP` returns "no abort" for out-of-range values and `injectAbort` does nothing when no error type is set.
- **Evidence:** grpc-go cbf30c4130: [fault.go L218-L249](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/fault/fault.go#L218-L249), [fault.go L279-L291](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/httpfilter/fault/fault.go#L279-L291)
- **Spec:** xDS HTTP Filters: Fault Injection: Configuration

### [low] RBAC `CidrRange.prefix_len` above the address width NACKed instead of clamped

- **Item:** XDS_RBAC-22
- **Summary:** Go NACKs an RBAC `CidrRange` whose `prefix_len` exceeds the address width (for example 33–128 for IPv4).
- **Description:** The spec (following Envoy) treats a `prefix_len` above the address width, up to 128, as the address width. Go builds `"<address_prefix>/<prefix_len>"` and calls `netip.ParsePrefix`, which rejects a length above the width; the error NACKs the Listener.
- **Evidence:** grpc-go cbf30c41309983ce66c6a81abe569a75fd2b9dcd: [matchers.go L340-L375](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/rbac/matchers.go#L340-L375), [rbac.go L106](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/httpfilter/rbac/rbac.go#L106)
- **Spec:** xDS HTTP Filters: RBAC: Configuration Validation

### [low] CDS `transport_socket.name` other than `envoy.transport_sockets.tls` rejects the Cluster

- **Item:** XDS_CDS-3
- **Summary:** Go NACKs a Cluster whose `transport_socket.name` (or nested name inside `Http11ProxyUpstreamTransport`) is not `envoy.transport_sockets.tls`.
- **Description:** The spec ignores `transport_socket.name` on Clusters and selects behavior only by the `typed_config` type. Go's `securityConfigFromCluster` returns "transport_socket field has unexpected name".
- **Evidence:** grpc-go cbf30c4130: [unmarshal_cds.go L358-L360](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L358-L360)
- **Spec:** Cluster: Transport Socket; xDS Security: Locating the TLS Context

### [low] Empty `rds.route_config_name` NACKed

- **Item:** XDS_LDS-20
- **Summary:** Go rejects an `HttpConnectionManager` whose `rds.route_config_name` is `""`, on client and server Listeners.
- **Description:** The spec (and Envoy's `Rds` proto, which has no `min_len`) allows an empty `route_config_name`, which names the RDS resource `""`. Go returns "empty route_config_name" and NACKs the Listener.
- **Evidence:** grpc-go cbf30c4130: [unmarshal_lds.go L102-L105](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/unmarshal_lds.go#L102-L105), [filter_chain.go L149-L152](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/xdsclient/xdsresource/filter_chain.go#L149-L152)
- **Spec:** Listener (Client Side): `HttpConnectionManager`

### [low] Empty `GRPC_XDS_BOOTSTRAP` / `GRPC_XDS_BOOTSTRAP_CONFIG` treated as unset

- **Item:** XDS_BOOTSTRAP-11
- **Summary:** Go treats an environment variable set to `""` as unset and falls through to the next bootstrap source.
- **Description:** The spec says a defined variable counts as set even when empty, so `GRPC_XDS_BOOTSTRAP=""` makes XdsClient creation fail rather than falling through to `GRPC_XDS_BOOTSTRAP_CONFIG`. Go reads the variables with `os.Getenv` and checks `!= ""`, so an empty `GRPC_XDS_BOOTSTRAP` falls through to `GRPC_XDS_BOOTSTRAP_CONFIG` (or to "no bootstrap configured").
- **Evidence:** grpc-go cbf30c4130: [xds.go L46-L52](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/envconfig/xds.go#L46-L52), [bootstrap.go L865-L887](https://github.com/grpc/grpc-go/blob/cbf30c4130/internal/xds/bootstrap/bootstrap.go#L865-L887)
- **Spec:** Bootstrap: Locating the Bootstrap Configuration

### [low] Google default credentials send RPCs with no authorization metadata when ADC is missing

- **Item:** VENDOR-6
- **Summary:** When Application Default Credentials can't be found, Go's `NewDefaultCredentialsWithOptions` logs a warning and leaves the per-RPC credentials nil, so RPCs go out unauthenticated.
- **Description:** The spec says that when ADC isn't found, either credential creation fails or every RPC fails with `UNAUTHENTICATED`; gRPC MUST NOT send RPCs without call credentials. Go returns a bundle with nil `PerRPCCreds`, and the transport skips nil bundle per-RPC credentials, so RPCs are sent with no `authorization` metadata and fail at the server with a less useful error.
- **Evidence:** grpc-go cbf30c41309983ce66c6a81abe569a75fd2b9dcd: [google.go L50-L73](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/credentials/google/google.go#L50-L73), [http2_client.go L299-L306](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/transport/http2_client.go#L299-L306)
- **Spec:** Google Default Credentials: Application Default Credentials

### [low] `admin.Register` silently skips CSDS on custom `grpc.ServiceRegistrar`s

- **Item:** ADMIN-1
- **Summary:** Go's `admin.Register` accepts any `grpc.ServiceRegistrar`, but the xDS CSDS hook registers CSDS only on a `*grpc.Server` or an `*xds.GRPCServer`; for other registrars it logs an error and returns success without CSDS.
- **Description:** The spec requires the admin function to work on any server the application can build and add every currently relevant admin service. The type switch in the CSDS hook is left over from an older go-control-plane API; `RegisterClientStatusDiscoveryServiceServer` now takes a `grpc.ServiceRegistrar`, so the registrar can be passed straight through.
- **Evidence:** grpc-go cbf30c41309983ce66c6a81abe569a75fd2b9dcd: [admin.go L56-L58](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/admin/admin.go#L56-L58), [xds.go L56-L83](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/xds/xds.go#L56-L83)
- **Spec:** Admin Interface: API Requirements

### [low] Google default credentials exchange a service account key for an OAuth access token instead of using a self-signed JWT

- **Item:** VENDOR-7
- **Summary:** `NewDefaultCredentialsWithOptions` calls `newADC`, which calls `oauth.NewApplicationDefault` with the `cloud-platform` scope. Because a scope is set, the `golang.org/x/oauth2` token source is used, and it exchanges a signed JWT for an OAuth access token at Google's token endpoint.
- **Description:** The spec (following AIP-4111) says that a service account key found by ADC behaves as Service Account JWT Access Credentials (a self-signed JWT) unless the application requested OAuth scopes, and that scopes added by gRPC itself don't count. C++ and Java use a self-signed JWT. Go makes an extra network round trip and fails RPCs if the token endpoint can't be reached. Fix: drop the scope, or pass one only when the application supplies it.
- **Evidence:** grpc-go cbf30c4130: [google.go L50-L60](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/credentials/google/google.go#L50-L60), [L124-L126](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/credentials/google/google.go#L124-L126), [oauth.go L228-L243](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/credentials/oauth/oauth.go#L228-L243); golang.org/x/oauth2 v0.37.0 [google.go L169-L171](https://github.com/golang/oauth2/blob/v0.37.0/google/google.go#L169-L171)
- **Spec:** Google Call Credentials: Application Default Credentials (`10-vendor-specific/05-google-call-credentials.md`)

### [low] weighted_round_robin accepts negative Duration values in its config

- **Item:** WRR-22
- **Summary:** A negative `oobReportingPeriod`, `blackoutPeriod`, `weightExpirationPeriod`, or `weightUpdatePeriod` is accepted instead of making the config invalid.
- **Description:** The spec makes the `weighted_round_robin` config invalid if any of these four Duration fields is negative. Go's `ParseConfig` unmarshals them as `internal/serviceconfig.Duration`, whose `UnmarshalJSON` accepts a leading `-`. It checks only `errorUtilizationPenalty` for sign, and raises `weightUpdatePeriod` to 100 ms. As a result, a negative `weightExpirationPeriod` expires every weight immediately and a negative `oobReportingPeriod` is requested from servers.
- **Evidence:** grpc-go cbf30c4130: [balancer.go L120-L148](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/balancer/weightedroundrobin/balancer.go#L120-L148), [duration.go L61-L77](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/serviceconfig/duration.go#L61-L77)
- **Spec:** `weighted_round_robin` LB Policy: 2.2 Validation

### [low] xds_cluster_manager fails a pick for an unknown cluster with UNAVAILABLE instead of INTERNAL

- **Item:** XDS_LB-8
- **Summary:** When the cluster call attribute names no child, the picker returns `codes.Unavailable` ("unknown cluster selected for RPC") instead of INTERNAL.
- **Description:** The spec says a pick whose cluster attribute is missing or names no active child MUST fail with INTERNAL, because the case signals an internal bug. Go's cluster manager picker returns `status.Errorf(codes.Unavailable, "unknown cluster selected for RPC: %q", cluster)`. To the application this looks like a transient, retryable condition.
- **Evidence:** grpc-go cbf30c4130: [picker.go L50](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/balancer/clustermanager/picker.go#L50)
- **Spec:** `xds_cluster_manager` LB Policy: Picker Implementation

### [low] LOGICAL_DNS cluster accepts a `port_value` above 65535

- **Item:** XDS_CDS-21
- **Summary:** A `LOGICAL_DNS` Cluster whose `port_value` is greater than 65535 is accepted.
- **Description:** The spec says the `LOGICAL_DNS` `port_value` MUST be in 1–65535. Go's `dnsHostNameFromCluster` rejects only `port == 0` and accepts any other `uint32`, so the DNS name gets a port that no socket can use, and RPCs fail at connect time instead of the Cluster being NACKed.
- **Evidence:** grpc-go cbf30c4130: [unmarshal_cds.go L320-L324](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/xdsclient/xdsresource/unmarshal_cds.go#L320-L324)
- **Spec:** Cluster: Logical DNS Clusters

### [low] EDS rejects a LocalityLbEndpoints with no locality, including zero-weight entries

- **Item:** XDS_EDS-2
- **Summary:** A `LocalityLbEndpoints` entry whose `locality` field is unset makes the resource invalid ("locality without ID"). The check runs before zero-weight entries are skipped, so it applies to ignored entries too.
- **Description:** The spec, following Envoy, treats an unset `locality` as the empty locality, and says entries with unset or 0 weight are ignored without validation. `parseEDSRespProto` returns "EDS response contains a locality without ID" for any entry with a nil locality, before the `weight == 0` skip. Fix: treat a nil locality as the empty locality (the order relative to the weight skip then no longer matters).
- **Evidence:** grpc-go cbf30c4130: [unmarshal_eds.go L181-L189](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/xdsclient/xdsresource/unmarshal_eds.go#L181-L189)
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: LocalityLbEndpoints

### [low] EDS accepts a drop_overloads entry with an empty category

- **Item:** XDS_EDS-4
- **Summary:** A `DropOverload` with an empty `category` is accepted instead of NACKing the resource.
- **Description:** The spec, following Envoy's `category` validation rule (`min_len: 1`), requires a non-empty drop category, which is used as the category name in load reports. `parseDropPolicy` copies `dropPolicy.GetCategory()` with no check.
- **Evidence:** grpc-go cbf30c4130: [unmarshal_eds.go L79-L88](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/xdsclient/xdsresource/unmarshal_eds.go#L79-L88)
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: Drop Overloads

### [low] `weighted_target` ignores a child's TRANSIENT_FAILURE → CONNECTING transition when aggregating

- **Item:** WEIGHTED_TARGET-2
- **Summary:** The aggregator keeps a child in TRANSIENT_FAILURE when it reports CONNECTING after TRANSIENT_FAILURE.
- **Description:** The spec aggregates `weighted_target` children with the normal rules, using each child's current state; sticky TRANSIENT_FAILURE is handled by the `pick_first` children (gRFC A62). Go's weighted aggregator skips the TRANSIENT_FAILURE → CONNECTING update (but not TRANSIENT_FAILURE → IDLE), which predates A62.
- **Evidence:** [aggregator.go L204-L210](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/balancer/weightedtarget/weightedaggregator/aggregator.go#L204-L210).
- **Spec:** `weighted_target` LB Policy: Calls From Children

## Fixed upstream or withdrawn

Bugs found during the spec work that have since been fixed upstream. Not to be filed.

- **Go [high]: server-side binary logs include the authorization header** (BINARY_LOG-3). Fixed by 40ef73b4, [grpc/grpc-go#9412](https://github.com/grpc/grpc-go/pull/9412) ("binarylog: omit the \"authorization\" header from logged metadata"), first in v1.85.0. grpc-go v1.82.0 through v1.84.x are affected.
- **Go, Java, C++ [low]: endpoint weight product overflow** (XDS_LB-1). Withdrawn: the spec adopted gRFC A113 (PICK_FIRST-1), whose normalized UQ1.31 weights cannot overflow. Go and Java use A113 by default; the C++ case is superseded by the C++ PICK_FIRST-1 bug (A113 off by default).
