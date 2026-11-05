# Java implementation bugs

Bugs in grpc-java found while writing and reviewing the gRPC spec in this directory: **230** entries, ordered by severity. Other lists: [Go](bugs_go.md), [C++](bugs_cpp.md), [documentation](bugs_docs.md).

Severity:

- **critical:** crash, data corruption, or a security weakness
- **high:** interoperability failure, or wrong behavior that users commonly hit
- **medium:** spec non-conformance with limited impact
- **low:** cosmetic, or a rare edge case

Each bug lists the review item that identified it (an item ID such as `RLS-4`, an `R<n>` number from the original review list, or "incidental"/"audit"), a summary, a description, evidence (code locations), and the spec section it violates. Open questions are in [review_items.md](review_items.md). None of these bugs has been filed yet.

### [critical] `CertificateValidationContext.match_typed_subject_alt_names` is silently ignored (SAN verification fails open)

- **Item:** XDS_SECURITY-20
- **Summary:** CDS/LDS validation reads only `getMatchSubjectAltNamesCount()` (annotated "gRFC A29 predates match_typed_subject_alt_names") and never checks `getMatchTypedSubjectAltNamesCount()`, so a resource that sets the typed field is ACKed and its SAN matchers are not applied.
- **Description:** The spec requires a NACK when `match_typed_subject_alt_names` is non-empty, because ignoring it compromises security. A control plane that uses Envoy's non-deprecated SAN matcher field gets a client that skips peer SAN verification (unless `auto_sni_san_validation` is set). If both fields are set, gRPC checks the deprecated list, which Envoy ignores.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClusterResource.java L500-L532](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L500-L532) (also `CommonTlsContextUtil.java`)
- **Spec:** xDS Security: `CommonTlsContext` Validation (`09-xds/09-security.md`)

### [high] Bootstrap `"tls"` channel credentials ignore their `config`

- **Item:** audit (W1-B-002, W2-15-003)
- **Summary:** `TlsXdsCredentialsProvider.newChannelCredentials` ignores its `jsonConfig` argument and always returns a default `TlsChannelCredentials`, so `ca_certificate_file`, `certificate_file`, `private_key_file`, and `refresh_interval` have no effect and invalid values are never rejected.
- **Description:** gRFC A65 and the spec let a `"tls"` `channel_creds` entry set custom root CAs, an identity certificate for mTLS, and a refresh interval. Java uses the system roots and no client certificate no matter what the config says. As a result, Java cannot connect to an xDS server that requires mTLS or uses a private CA. A config that should make the bootstrap invalid is accepted too. C++ and Go parse and validate these fields.
- **Evidence:** grpc-java ed3bf6b76b: [TlsXdsCredentialsProvider.java L31-L34](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/TlsXdsCredentialsProvider.java#L31-L34)
- **Spec:** Bootstrap (`09-xds/02-bootstrap.md`), XdsServer Object

### [high] `GrpcService.initial_metadata` from untrusted xDS servers is honored

- **Item:** audit (W2-15-001)
- **Summary:** `GrpcServiceConfigParser.parse` always copies `GrpcService.initial_metadata` into the parsed config, even when the xDS server does not have the `trusted_xds_server` server feature.
- **Description:** gRFC A102 and the spec require gRPC to ignore `initial_metadata` (and the credentials) in a `GrpcService` from an untrusted xDS server and use the matching `allowed_grpc_services` entry instead. Java does apply that rule to target and credentials in `parseGoogleGrpcConfig`, but parses `initial_metadata` without checking trust. The headers are then attached to side-channel calls (for example by `ExternalProcessorClientInterceptor`). An untrusted control plane can therefore add arbitrary headers to those calls. C++ enforces the check.
- **Evidence:** grpc-java ed3bf6b76b: [GrpcServiceConfigParser.java L96-L115](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/GrpcServiceConfigParser.java#L96-L115), [GrpcServiceConfigParser.java L148-L184](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/GrpcServiceConfigParser.java#L148-L184), [ExternalProcessorClientInterceptor.java L211-L214](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ExternalProcessorClientInterceptor.java#L211-L214)
- **Spec:** Bootstrap (`09-xds/02-bootstrap.md`), Allowed gRPC Service Object

### [high] outlier_detection config updates postpone the first ejection sweep and reset call counters

- **Item:** OUTLIER_DETECTION-3
- **Summary:** Java records the detection timer start time only when the timer first fires, so every config update before the first sweep restarts a full `interval`. When a timer exists it also resets all call counters on every update.
- **Description:** Per gRFC A50 and the spec, the start time is recorded when the timer is first started, later updates restart the timer for the remaining time, and counters are reset only when the start time was unset. With xDS, every EDS/CDS change pushes a new config to the policy; updates more frequent than `interval` (default 10 s) keep postponing the first sweep, and each update discards collected data, so outlier detection can be silently disabled.
- **Evidence:** util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java (acceptResolvedAddresses: detectionTimerStartNanos handling and resetCallCounters(); DetectionTimer.run sets detectionTimerStartNanos).
- **Spec:** `outlier_detection` LB Policy: Updates from the Parent

### [high] Java: authorization policy translator silently ignores unknown fields

- **Item:** AUTHZ-3
- **Summary:** Java's `AuthorizationPolicyTranslator` never rejects unrecognized fields, so a typo such as `"deny_rule"` or an unimplemented field such as `"audit_logging_options"` is dropped and the policy is accepted with fewer restrictions.
- **Description:** `translate` reads only `name`, `deny_rules`, `allow_rules` and, inside them, only known keys; it never checks for extra keys at any level. A43 calls rejection of policies with unknown fields a security requirement. C++ and Go reject them. Java should also reject `audit_logging_options` until it implements audit logging.
- **Evidence:** [AuthorizationPolicyTranslator.java L165-L198](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/authz/src/main/java/io/grpc/authz/AuthorizationPolicyTranslator.java#L165-L198)
- **Spec:** Authorization: Schema

### [high] Circuit breaking (max_concurrent_requests) not enforced when the cluster has no LRS server

- **Item:** XDS_LB-7; audit (W2-17-016)
- **Summary:** Java increments `inFlights` only in `CountingStreamTracerFactory`, and that tracer is attached only when locality stats exist, i.e. only when `lrs_load_reporting_server` is set.
- **Description:** For any cluster without LRS, which is the common case, the counter never increases, so `max_requests` circuit breaking is silently ignored. gRFC A32 does not tie circuit breaking to LRS. C++ and Go count every completed pick. Also, `RequestLimitingSubchannelPicker` checks `inFlights >= maxConcurrentRequests` only after `delegate.pickSubchannel(args)` returns a completed pick, while the spec checks the circuit breaker before calling the child picker; the counter is incremented later, when the stream is created (`CountingStreamTracerFactory.newClientStreamTracer`), not in the picker on the completed pick.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L438-L455, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L331-L337, [ClusterImplLoadBalancer.java L421-L437](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L421-L437), [ClusterImplLoadBalancer.java L489-L491](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L489-L491)
- **Spec:** `xds_cluster_impl` LB Policy: Features (Circuit Breaking)

### [high] Java server-side binary logs include the authorization header

- **Item:** BINARY_LOG-3
- **Summary:** Java's server-side binary log records the `authorization` header, leaking bearer tokens into logs.
- **Description:** The spec (and the binarylog.proto `Metadata` comment) requires the server side to exclude the `authorization` header from logged metadata. Java's BinlogHelper only excludes `grpc-status-details-bin` (and other internal keys), so server-side `EVENT_TYPE_CLIENT_HEADER` entries contain credentials.
- **Evidence:** grpc-java `services/src/main/java/io/grpc/protobuf/services/BinlogHelper.java` (`createMetadataProto`, excluded-key set)
- **Spec:** Binary Logging: Metadata

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

### [high] RLS policy shuts down its cache, control channel, and children on a resolver error

- **Item:** audit (W2-09-015)
- **Summary:** `RlsLoadBalancer.handleNameResolutionError` closes the `CachingRlsLbClient` (RLS cache, control channel, and every child policy), forgets its config, and reports `TRANSIENT_FAILURE` with a picker that fails every RPC, even when it had a working config.
- **Description:** The spec says a policy with a previously accepted endpoint list should keep using it on an endpoint error and should not close working connections or report `TRANSIENT_FAILURE`. Java's RLS policy discards all of its state on any resolver error. A transient resolver failure therefore fails all traffic through the policy until the next good resolver result, and the cache and connections must then be rebuilt from scratch.
- **Evidence:** grpc-java ed3bf6b76b: [RlsLoadBalancer.java L93-L103](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/rls/src/main/java/io/grpc/rls/RlsLoadBalancer.java#L93-L103)
- **Spec:** Load Balancing (`04-client-channel/06-load-balancing.md`), Endpoint Errors

### [high] xDS server filter chain matching fails connections when a `raw_buffer` or specific `source_type` chain coexists with a less specific one

- **Item:** audit (W2-18-012)
- **Summary:** At the `transport_protocol` and `source_type` steps, the server's filter chain selector keeps every matching chain instead of only the most specific ones. When a Listener has both a `"raw_buffer"` chain and one with no `transport_protocol`, or both an `EXTERNAL`/`SAME_IP_OR_LOOPBACK` chain and an `ANY` chain, more than one chain can survive. `select` then throws `IllegalStateException` and the connection is dropped. Also, `EXTERNAL` matches a peer whose IP equals the local IP.
- **Description:** The spec selects the most specific match at each step: `"raw_buffer"` beats an unset `transport_protocol`, and `SAME_IP_OR_LOOPBACK`/`EXTERNAL` beat `ANY`. `EXTERNAL` matches only peers that are neither loopback nor the local IP. Java's listener validation treats these chains as distinct and accepts them. At connection time, `filterOnTransportProtocol` and `filterOnSourceType` keep all of them, so a valid Listener can make the server reject every matching connection with "Found more than one matching filter chains". Because `EXTERNAL` checks only loopback and wildcard addresses, a same-host connection on a non-loopback IP matches both `EXTERNAL` and `SAME_IP_OR_LOOPBACK` chains.
- **Evidence:** grpc-java ed3bf6b76b: [FilterChainMatchingProtocolNegotiators.java L176-L201](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FilterChainMatchingProtocolNegotiators.java#L176-L201), [FilterChainMatchingProtocolNegotiators.java L218-L230](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FilterChainMatchingProtocolNegotiators.java#L218-L230), [FilterChainMatchingProtocolNegotiators.java L279-L304](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FilterChainMatchingProtocolNegotiators.java#L279-L304), [XdsListenerResource.java L350-L357](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L350-L357)
- **Spec:** xDS-Enabled Servers (`09-xds/08-server.md`), Matching Algorithm

### [high] xDS SAN matching treats the matcher, not the certificate SAN, as the wildcard pattern

- **Item:** audit (W2-18-017)
- **Summary:** For `exact` SAN matchers and `auto_sni_san_validation`, Java applies wildcard matching only when the configured matcher (or the SNI) contains `*`, and uses the matcher as the pattern. A server certificate with a wildcard DNS SAN such as `*.example.com` therefore never matches `exact: "api.example.com"` or the SNI `api.example.com`. Also, `auto_sni_san_validation` compares the SNI against URI and IP SANs as well as DNS SANs.
- **Description:** In `XdsX509TrustManager.verifyDnsNameExact`, the check is `sanToVerifyExact.contains("*")`, and `verifyDnsNameWildcard` splits the matcher value as the pattern and the certificate SAN as the name. The spec puts the wildcard on the other side: a wildcard DNS SAN in the certificate matches an `exact` value (RFC 9525 §6.3). In Java, wildcard server certificates fail SAN verification when they should pass. In the other direction, an `exact` matcher containing `*` matches certificate names it should not, because `exact` has no wildcard meaning for the matcher value. Separately, `getAutoSniSanMatchers` builds a plain `exact` matcher that `verifyOneSanInList` applies to DNS, URI and IP SANs, but for the SNI check the spec considers DNS SANs only.
- **Evidence:** grpc-java ed3bf6b76b: [XdsX509TrustManager.java L153-L164](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/security/trust/XdsX509TrustManager.java#L153-L164), [XdsX509TrustManager.java L186-L193](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/security/trust/XdsX509TrustManager.java#L186-L193), [XdsX509TrustManager.java L303-L318](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/security/trust/XdsX509TrustManager.java#L303-L318), [XdsX509TrustManager.java L350-L369](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/security/trust/XdsX509TrustManager.java#L350-L369)
- **Spec:** xDS Security (`09-xds/09-security.md`), Server Identity Verification

### [high] `file_watcher` certificate provider rejects root-only and identity-only configs

- **Item:** audit (W2-18-021)
- **Summary:** `FileWatcherCertificateProviderProvider` requires both `certificate_file`/`private_key_file` and a root source (`ca_certificate_file`, or `spiffe_trust_bundle_map_file` when SPIFFE is enabled). A `file_watcher` instance with only trust roots, or only an identity, fails.
- **Description:** The spec requires only that `certificate_file` and `private_key_file` be set together, and that at least one of `certificate_file`, `ca_certificate_file`, and `spiffe_trust_bundle_map_file` be set. Typical one-way TLS setups use a root-only instance on the client and an identity-only instance on the server. When an xDS resource first uses such an instance, Java throws `NullPointerException` ("'certificate_file' is required in the config" or "'ca_certificate_file' is required in the config"), so the security configuration cannot be used. C++ and Go accept these configs.
- **Evidence:** grpc-java ed3bf6b76b: [FileWatcherCertificateProviderProvider.java L97-L121](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/security/certprovider/FileWatcherCertificateProviderProvider.java#L97-L121)
- **Spec:** xDS Security (`09-xds/09-security.md`), `file_watcher` Plugin

### [high] xDS RBAC NACKs `authenticated` principals that have no `principal_name`

- **Item:** audit (W2-11-016, W2-18-007)
- **Summary:** `RbacFilter.parseAuthenticatedMatcher` parses `principal_name` without checking whether it is set. An `authenticated` principal with no `principal_name` throws `IllegalArgumentException`, and the resource that contains the RBAC config is NACKed.
- **Description:** In the spec, an `authenticated` principal with no `principal_name` is valid and matches any TLS connection. `GrpcAuthorizationEngine.AuthenticatedMatcher` already handles a null delegate for this case. The parser, however, passes the default `StringMatcher` to `MatcherParser.parseStringMatcher`, which rejects `MATCHPATTERN_NOT_SET`. Policies such as "allow any authenticated peer" are therefore rejected outright.
- **Evidence:** grpc-java ed3bf6b76b: [RbacFilter.java L335-L339](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RbacFilter.java#L335-L339), [MatcherParser.java L91-L109](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/MatcherParser.java#L91-L109), [GrpcAuthorizationEngine.java L145-L175](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/rbac/engine/GrpcAuthorizationEngine.java#L145-L175)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), Mapping RBAC Fields to gRPC; Authorization (`06-security/04-authorization.md`), Authenticated Principal Matching

### [high] CIDR ranges with prefix length 0 match only half of the address space

- **Item:** audit (W2-11-017, W2-18-007)
- **Summary:** `Matchers.CidrMatcher.matches` converts addresses with the signed `BigInteger(byte[])` constructor and an arithmetic right shift. With `prefix_len` 0, `0.0.0.0/0` does not match `128.0.0.0`–`255.255.255.255`, and `::/0` does not match `8000::` and above.
- **Description:** `new BigInteger(byte[])` reads the first bit as a sign bit, so addresses with the high bit set are negative. Shifting right by the full address width gives `-1` for them and `0` for the all-zero prefix, so the comparison fails. Prefixes of length 1 or more compare correctly. The same matcher is used for xDS RBAC `source_ip`/`destination_ip`/`direct_remote_ip`/`remote_ip` and for server `FilterChainMatch` `prefix_ranges`/`source_prefix_ranges`. A catch-all RBAC rule (for example a DENY on `0.0.0.0/0`) does not apply to half of all peers, and a filter chain with a `/0` range is skipped for those addresses.
- **Evidence:** grpc-java ed3bf6b76b: [Matchers.java L313-L330](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/Matchers.java#L313-L330), [FilterChainMatchingProtocolNegotiators.java L306-L331](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FilterChainMatchingProtocolNegotiators.java#L306-L331), [RbacFilter.java L349-L357](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RbacFilter.java#L349-L357)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), RBAC: Configuration Validation; xDS-Enabled Servers (`09-xds/08-server.md`), Filter Chain Selection

### [medium] `xdstp:` names are not normalized when a watch starts, so updates for names with unsorted context parameters are dropped

- **Item:** audit (W2-15-004)
- **Summary:** `XdsClientImpl` keys subscriptions and builds requests with the watched name exactly as given. Response parsing normalizes `xdstp:` names (sorted context parameters). A watched name whose context parameters are not already sorted therefore never matches a received resource.
- **Description:** Only the client Listener name is canonicalized, in `XdsNameResolver`. RDS, CDS, and EDS names come from other resources and go to `watchXdsResource` unchanged. Say a Listener refers to `xdstp://auth/envoy.config.route.v3.RouteConfiguration/r?b=2&a=1`. The subscriber is keyed and requested as `?b=2&a=1`. If the server returns the resource under that name, `XdsResourceType.parseResources` stores it as `?a=1&b=2`, and the lookup `parsedResources.containsKey(resourceName)` misses, so the update is never delivered. If the server returns the normalized name, the resource is skipped because it is not in the raw subscribed set. Two watches on differently ordered forms of one name also become two subscriptions. Minor: `canonifyResourceName` sorts whole `key=value` strings instead of keys, and rebuilds the name with `String.replace(rawQuery, …)`, which can also change an earlier part of the URI that contains the same text.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClientImpl.java L263-L269](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L263-L269), [XdsClientImpl.java L606-L611](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L606-L611), [XdsResourceType.java L169-L173](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsResourceType.java#L169-L173), [XdsClient.java L85-L107](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClient.java#L85-L107), [XdsNameResolver.java L250](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L250)
- **Spec:** XdsClient (`09-xds/03-xds-client.md`), Old-style and new-style names

### [medium] After channel idle, an invalid service config leaves RPCs queued instead of failing them

- **Item:** audit (W2-04-011)
- **Summary:** `ManagedChannelImpl.enterIdleMode()` resets the ConfigSelector to the initial pending selector but keeps `lastServiceConfig` and `serviceConfigUpdated`. If the first resolver result after leaving idle has a service config error and there is no default service config, the channel treats the old config as still valid and never installs a ConfigSelector. RPCs stay queued until their deadline or a later resolver result.
- **Description:** The spec says the channel discards its service config and ConfigSelector when it goes idle. A service config error with no valid config should then put the channel in `TRANSIENT_FAILURE` and fail queued RPCs that lack `wait_for_ready`. In Java, `NameResolverListener.onResult2` sees `serviceConfigUpdated == true` and sets `effectiveServiceConfig = lastServiceConfig`. That branch never calls `realChannel.updateConfigSelector(...)`, so the selector stays `INITIAL_PENDING_SELECTOR` and new calls keep going into `pendingCalls`. The LB policy also gets the config from before idle. Nothing releases the calls until a later result carries a valid config or the resolver reports an error. The DNS resolver may not re-resolve unless the LB policy asks it to.
- **Evidence:** grpc-java ed3bf6b76b: [ManagedChannelImpl.java L291-L296](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L291-L296), [ManagedChannelImpl.java L429-L445](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L429-L445), [ManagedChannelImpl.java L1733-L1759](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1733-L1759)
- **Spec:** Channel (`04-client-channel/02-channel.md`), Idle Timeout; Per-call Configuration and Call Flow (`04-client-channel/05-call-dispatch.md`), Starting an RPC and Waiting for a Resolver Result

### [medium] weighted_round_robin picks never return when an endpoint weight is infinite or exceeds the `float` range

- **Item:** audit (W2-07-009)
- **Summary:** `WeightedRoundRobinLoadBalancer` does not check that a computed weight is finite before casting it to `float`. If a backend's metrics produce a weight above `Float.MAX_VALUE` or an infinite one (for example infinite `qps`, or `qps` divided by a tiny utilization), every scaled weight becomes 0 and `StaticStrideScheduler.pick()` loops forever.
- **Description:** `onLoadReport` computes the weight as a `double`, and `updateWeight` casts it with `(float) newWeight`, which turns large values into `+Infinity`. The `StaticStrideScheduler` constructor then computes a mean of `Infinity` and a scaling factor of 0. Every scaled weight is rounded to 0, including the lower bound, because `0 * Infinity` is NaN. In `pick()`, a weight of 0 always takes the `continue` branch, so with at least two weighted endpoints a pick never completes. A single misbehaving backend's load reports can thus hang every RPC on the channel.
- **Evidence:** grpc-java ed3bf6b76b: [WeightedRoundRobinLoadBalancer.java L263](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L263), [WeightedRoundRobinLoadBalancer.java L378-L397](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L378-L397), [WeightedRoundRobinLoadBalancer.java L663-L712](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L663-L712), [WeightedRoundRobinLoadBalancer.java L756-L768](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L756-L768)
- **Spec:** `weighted_round_robin` LB Policy (`04-client-channel/lb-policies/weighted_round_robin.md`), Features

### [medium] outlier_detection picker attaches a null endpoint tracker to untracked subchannels, causing `NullPointerException` at stream close

- **Item:** audit (W2-08-009)
- **Summary:** `OutlierDetectionPicker` always wraps the pick in a `ResultCountingClientStreamTracerFactory`, even when the subchannel has no `EndpointTracker`. When the stream closes, `tracker.incrementCallCount(...)` throws `NullPointerException`.
- **Description:** The spec attaches a call tracker only when the picked subchannel's endpoint is in the endpoint map. Java reads `ENDPOINT_TRACKER_KEY` from the subchannel's attributes, which can be null, and passes it on without checking. Untracked subchannels include those created with more than one address. Those are never added to a tracker, which affects every RPC when the old `pick_first` is in use. Subchannels shut down while an old picker can still select them are another case: `shutdown()` clears the tracker at once, while the channel delays the real shutdown by 5 seconds. RPCs on such subchannels hit a `NullPointerException` in the stream tracer when they finish.
- **Evidence:** grpc-java ed3bf6b76b: [OutlierDetectionLoadBalancer.java L241-L251](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java#L241-L251), [OutlierDetectionLoadBalancer.java L300-L315](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java#L300-L315), [OutlierDetectionLoadBalancer.java L439-L499](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java#L439-L499)
- **Spec:** `outlier_detection` LB Policy (`04-client-channel/lb-policies/outlier_detection.md`), Picker Implementation

### [medium] Hash policy `regex_rewrite` substitution uses Java `$N` syntax instead of RE2 `\N`

- **Item:** audit (W2-16-010, W2-17-006)
- **Summary:** `XdsNameResolver` applies `hash_policy` `header.regex_rewrite.substitution` with re2j `Matcher.replaceAll`, which uses `$N` for capture groups and `\` as an escape character. RE2 `\1` references become a literal `1`, and substitutions containing `$<digit>` beyond the group count or an unterminated `${` throw at RPC time.
- **Description:** The spec and Envoy define the substitution with RE2 capture-group references (`\0`–`\9`). With re2j semantics, `\1` is an escaped `1`, so the rewritten value and the request hash differ from C++ and Envoy, breaking session affinity that relies on the rewrite. A literal `$1` in the substitution is treated as a group reference instead of plain text. Strings such as `"$5"` with fewer groups, or `"${x"`, make `replaceAll` throw `IndexOutOfBoundsException` or `IllegalArgumentException` during config selection for every matching RPC. The substitution is not validated when the RDS resource is parsed.
- **Evidence:** grpc-java ed3bf6b76b: [XdsNameResolver.java L598-L600](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L598-L600), [XdsRouteConfigureResource.java L439-L442](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L439-L442)
- **Spec:** RouteConfiguration (`09-xds/04-resources/03-route-configuration.md`), Hash Policy

### [medium] CDS ignores the TLS context nested in `Http11ProxyUpstreamTransport` unless its name is `envoy.transport_sockets.tls`

- **Item:** audit (W2-16-017, W2-18-020)
- **Summary:** After unwrapping `Http11ProxyUpstreamTransport`, `XdsClusterResource` parses the nested `transport_socket` only if its name is `envoy.transport_sockets.tls`. Any other nested socket is ignored without an error, whether it is an `UpstreamTlsContext` or an unsupported type.
- **Description:** The spec requires the nested `typed_config` to be an `UpstreamTlsContext`, used exactly as if it were the cluster's own transport socket, and requires any other type to reject the resource. For an unwrapped `transport_socket`, Java NACKs a name other than `envoy.transport_sockets.tls`. For the nested socket, it instead accepts the Cluster with no TLS context. With XdsChannelCredentials, connections through the proxy then use the fallback credentials (often plaintext) instead of the configured TLS. The code is reachable only when `GRPC_EXPERIMENTAL_XDS_HTTP_CONNECT` is enabled.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClusterResource.java L69-L70](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L69-L70), [XdsClusterResource.java L257-L296](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L257-L296)
- **Spec:** Cluster (`09-xds/04-resources/04-cluster.md`), `Http11ProxyUpstreamTransport`; xDS Security (`09-xds/09-security.md`), HTTP CONNECT and TLS

### [medium] Authority rewriting (`auto_host_rewrite`) is off by default in `xds_cluster_impl`, and an empty endpoint hostname overrides `:authority` with `""`

- **Item:** audit (W2-05-006, W2-17-010)
- **Summary:** The two halves of gRFC A81 read `GRPC_EXPERIMENTAL_XDS_AUTHORITY_REWRITE` with different defaults. RDS parsing honors `auto_host_rewrite` by default, but `ClusterImplLoadBalancer` stores the endpoint hostname only when the flag is explicitly set, so by default no rewrite happens. With the flag set, an endpoint with no hostname gets `:authority` overridden to `""`.
- **Description:** `XdsRouteConfigureResource` defaults the flag to `true`, and `XdsNameResolver` passes `auto_host_rewrite` routes to the picker. `ClusterImplLoadBalancer.createSubchannel` defaults the same flag to `false` and so never sets `ATTR_SUBCHANNEL_ADDRESS_NAME`. The picker then returns a null authority override, and routes from trusted servers with `auto_host_rewrite` get no rewrite. When the flag is enabled, the hostname comes from `Endpoint.hostname` via protobuf `getHostname()`, which returns `""` when unset. `createSubchannel` checks only `hostname != null`, so the picker returns an override of `""`. The transport then sets the RPC's `:authority` to the empty string instead of leaving it unchanged.
- **Evidence:** grpc-java ed3bf6b76b: [XdsRouteConfigureResource.java L71-L72](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L71-L72), [ClusterImplLoadBalancer.java L241-L247](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L241-L247), [ClusterImplLoadBalancer.java L456-L461](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L456-L461), [XdsEndpointResource.java L241](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L241), [CdsLoadBalancer2.java L419](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/CdsLoadBalancer2.java#L419)
- **Spec:** `xds_cluster_impl` LB Policy (`09-xds/lb-policies/xds_cluster_impl.md`), Authority Rewriting; xDS Client (`09-xds/05-client.md`), Authority rewriting

### [medium] Identical xDS servers listed under different authorities do not share an xDS channel

- **Item:** audit (W2-15-002)
- **Summary:** `GrpcBootstrapperImpl` stores a newly created `ChannelCredentials` object in each `ServerInfo.implSpecificConfig()`. `ChannelCredentials` uses identity equality, so two separately parsed `xds_servers` entries with the same `server_uri` and credentials are different `ServerInfo` keys, and `XdsClientImpl` opens a separate channel and ADS stream for each.
- **Description:** The spec keys xDS channels by server identity (`server_uri`, channel credentials, call credentials, server features), so authorities that list the same server share one channel and ADS stream. In Java, every `xds_servers` list that is parsed separately (top-level and each authority with its own list) creates new credential objects through `XdsCredentialsProvider.newChannelCredentials`. This applies to `insecure`, `tls`, and `google_default` alike, because none of these credential classes overrides `equals`. The result is duplicate connections and duplicate subscriptions to the same control plane.
- **Evidence:** grpc-java ed3bf6b76b: [GrpcBootstrapperImpl.java L104-L108](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/GrpcBootstrapperImpl.java#L104-L108), [GrpcBootstrapperImpl.java L157-L171](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/GrpcBootstrapperImpl.java#L157-L171), [Bootstrapper.java L58-L86](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/Bootstrapper.java#L58-L86), [XdsClientImpl.java L497-L501](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L497-L501)
- **Spec:** XdsClient (`09-xds/03-xds-client.md`), xDS Channels

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

### [medium] Java ring_hash does not validate requestHashHeader at parse time

- **Item:** RING_HASH-5
- **Summary:** Java accepts an invalid or `-bin` `requestHashHeader` when it parses the config. Later, `Metadata.Key.of` throws inside `acceptResolvedAddresses`.
- **Description:** `RingHashLoadBalancerProvider.parseLoadBalancingPolicyConfig` reads the field only when `GRPC_EXPERIMENTAL_RING_HASH_SET_REQUEST_HASH_KEY` is set, and it never validates it. gRFC A76 requires the config to be rejected.
- **Evidence:** [RingHashLoadBalancerProvider.java#L82-L110](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RingHashLoadBalancerProvider.java#L82-L110), [RingHashLoadBalancer.java#L109-L112](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java#L109-L112)
- **Spec:** `ring_hash` LB Policy: Configuration

### [medium] Java subchannel reconnects after backoff and on ResetBackoff instead of reporting IDLE

- **Item:** SUBCHANNEL-1
- **Summary:** By default `InternalSubchannel` goes from TRANSIENT_FAILURE straight to CONNECTING when backoff ends or on `resetConnectBackoff()`, so it makes connection attempts the LB policy never asked for.
- **Description:** `EndOfCurrentBackoff.run()` and `resetConnectBackoff()` both call `gotoNonErrorState(CONNECTING)` and `startNewTransport()`. Only pick_first with the off-by-default `GRPC_SERIALIZE_RETRIES` sets `DISABLE_SUBCHANNEL_RECONNECT_KEY`. C++ and Go go to IDLE and wait for `RequestConnection()`, and LB policies such as pick_first (Happy Eyeballs) and ring_hash (lazy connect) count on that.
- **Evidence:** [InternalSubchannel.java#L296-L306](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L296-L306), [InternalSubchannel.java#L336-L349](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L336-L349)
- **Spec:** Subchannels and Connections: Connectivity States

### [medium] Java does not support xDS server call_creds (gRFC A97)

- **Item:** XDS_BOOTSTRAP-8
- **Summary:** Java ignores `call_creds` in bootstrap `xds_servers` entries, so `jwt_token_file` is silently dropped and the xDS channel sends no token.
- **Description:** `BootstrapperImpl.parseServerInfos` never reads `call_creds`. The only call-credentials parser (for `allowed_grpc_services`) returns empty ("Currently no xDS call credentials providers are implemented"). Deployments that rely on JWT auth to the control plane cannot authenticate from Java, and no error is reported. C++ and Go implement `jwt_token_file`.
- **Evidence:** [BootstrapperImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/BootstrapperImpl.java#L267-L304), [GrpcBootstrapperImpl.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/GrpcBootstrapperImpl.java#L211-L220)
- **Spec:** xDS Bootstrap: XdsServer Object

### [medium] Java does not reset LRS stats for unrequested clusters

- **Item:** XDS_LRS-2
- **Summary:** Stats for clusters the LRS server did not ask for keep building up and appear in the first report after the server asks for that cluster.
- **Description:** When `send_all_clusters` is false, `sendLoadReport` snapshots only `clusterNames`. Other clusters' counters are never reset, so a later request for them reports load from earlier intervals as current, which skews server load decisions. C++ snapshots and resets every cluster and discards the unrequested ones.
- **Evidence:** [LoadReportClient.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/LoadReportClient.java#L250-L265)
- **Spec:** xDS Load Reporting: Responses

### [medium] Java: service config waitForReady overrides the application's explicit wait-for-ready

- **Item:** WAIT_FOR_READY-1
- **Summary:** `ClientCallImpl.applyMethodConfig` replaces the call's wait-for-ready with the method config's value even when the application set it explicitly.
- **Description:** Whenever the method config sets `waitForReady`, Java does `callOptions = info.waitForReady ? withWaitForReady() : withoutWaitForReady()`, ignoring that `CallOptions` records (tri-state `Boolean`) whether the application set it. A service owner can silently flip an application's fail-fast or wait-for-ready choice, changing how RPCs fail during outages. Fix: apply the method config only when the application left it unset.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ClientCallImpl.java#L308-L311, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/CallOptions.java#L78
- **Spec:** 2. Core RPC Semantics: 14 Wait-for-Ready; Service Config: 5.4 `methodConfig`

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

### [medium] outlier_detection JSON parser reads `maxEjectionPercentage` and skips range/sign validation

- **Item:** OUTLIER_DETECTION-2
- **Summary:** Java's service-config parser for `outlier_detection_experimental` reads the key `maxEjectionPercentage` instead of `maxEjectionPercent`, so the configured value is silently ignored and 10 is used. It also does not reject `maxEjectionPercent` > 100 or negative `interval`/`baseEjectionTime`/`maxEjectionTime`.
- **Description:** The proto JSON name is `maxEjectionPercent` (used by C++ and Go). gRFC A50 requires values above 100 to be a parse error, and the spec makes negative durations invalid. In Java, a negative interval reaches `scheduleWithFixedDelay` and throws inside `acceptResolvedAddresses`. Fix: read `maxEjectionPercent` (optionally also accept the old key), validate it is at most 100, and reject negative durations. The xDS path builds the config object directly and is unaffected.
- **Evidence:** util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancerProvider.java (parseLoadBalancingPolicyConfig); util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java (acceptResolvedAddresses timer scheduling).
- **Spec:** `outlier_detection` LB Policy: Validation

### [medium] pick_first Happy Eyeballs and address-family interleaving disabled by default

- **Item:** PICK_FIRST-2
- **Summary:** Java's `pick_first` uses Happy Eyeballs only when `GRPC_PF_USE_HAPPY_EYEBALLS` is set (default false); by default it tries addresses strictly one at a time with no Connection Attempt Delay and no address-family interleaving.
- **Description:** gRFC A61 and the spec require Happy Eyeballs on the pass through the address list (250 ms default Connection Attempt Delay) and RFC 8305 §4 family interleaving. With Java's default, a dead first address costs a full connect timeout instead of 250 ms, and dual-stack backends connect slowly. Sub-item (low): when enabled, Java interleaves only two groups (IPv4 and everything else), so non-IP families are grouped with IPv6 instead of forming their own group in first-appearance order.
- **Evidence:** core/src/main/java/io/grpc/internal/PickFirstLeafLoadBalancer.java (enableHappyEyeballs, scheduleNextConnection, address flattening/interleaving); core/src/main/java/io/grpc/internal/PickFirstLoadBalancerProvider.java (GRPC_PF_USE_HAPPY_EYEBALLS default).
- **Spec:** `pick_first` LB Policy: Happy Eyeballs Connection Algorithm; Address List Processing

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

### [medium] Java: per-RPC authority check is not enforced by default

- **Item:** TLS-6
- **Summary:** Java computes the TLS per-RPC authority check but only logs a failure unless `GRPC_ENABLE_PER_RPC_AUTHORITY_CHECK=true` (default false), so RPCs are sent to servers whose certificate does not cover the RPC's authority.
- **Description:** `NettyClientHandler` reads `enablePerRpcAuthorityCheck = GrpcUtil.getFlag("GRPC_ENABLE_PER_RPC_AUTHORITY_CHECK", false)`. When the flag is off, a failed check logs "This will be an error in the future." and the RPC is sent anyway. OkHttp has the same flag. The spec (and A81) say TLS credentials MUST do the check by default and fail the RPC on mismatch. This flag is a temporary rollout guard, but the default is security-relevant.
- **Evidence:** [NettyClientHandler.java L107-L108](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyClientHandler.java#L107-L108), [L683-L700](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/NettyClientHandler.java#L683-L700); OkHttp transport uses the same flag.
- **Spec:** TLS: Per-RPC Authority Verification

### [medium] Java: xDS server's XdsClient uses a no-op MetricRecorder

- **Item:** METRICS-8
- **Summary:** `XdsServerWrapper` creates the `#server` XdsClient with `new MetricRecorder() {}`, so xDS-enabled Java servers record no `grpc.xds_client.*` metrics.
- **Description:** A78 defines `grpc.target="#server"` for the server XdsClient's metrics, and the spec says server-scoped non-per-call metrics, including the server XdsClient, are recorded on the server's stats plugins. C++ (`GetStatsPluginsForServer`) and Go (`MetricsRecorderForServer`) do this.
- **Evidence:** [XdsServerWrapper.java L221](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsServerWrapper.java#L221)
- **Spec:** Metrics Framework and OpenTelemetry Plugin: Server Scoping

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

### [medium] CertificateValidationContext NACK checks skipped when system_root_certs is used (SPKI/hash pinning ignored)

- **Item:** XDS_SECURITY-4
- **Summary:** Java runs the NACK checks for `verify_certificate_spki`, `verify_certificate_hash`, `require_signed_certificate_timestamp`, `crl`, and `custom_validator_config` only inside the `ca_certificate_provider_instance` branch of `validateCommonTlsContext`.
- **Description:** A client using `system_root_certs`, or a server with no CA instance, accepts these fields and silently ignores them. So certificate pinning that the control plane asked for is not enforced. gRFC A29: "If any of the other fields (listed below) are present, the update is NACKed because ignoring these fields compromises security". C++ and Go run the checks regardless of the CA source.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L481-L531
- **Spec:** xDS Security: `CommonTlsContext` Validation

### [medium] Top-level ORCA utilization reported as named load_metric_stats instead of UpstreamLocalityStats fields, and zero values not counted

- **Item:** XDS_LRS-3
- **Summary:** Java `LoadStatsManager2.recordTopLevelMetrics` stores propagated cpu/mem/application utilization in the named-metric map, and only when the value is > 0. `LoadReportClient.buildClusterStats` fills only `load_metric_stats`.
- **Description:** gRFC A85: these values "will be propagated to the new LRS fields of the same names in the `UpstreamLocalityStats` message." A control plane that reads the dedicated fields sees no utilization from Java clients, and skipping zero values undercounts `num_requests_finished_with_metric`. C++ and Go fill the dedicated fields.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/LoadStatsManager2.java#L417-L428, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/client/LoadReportClient.java#L337-L358
- **Spec:** Load Reporting (LRS): Locality stats

### [medium] Per-RPC authority mismatch fails with UNAVAILABLE instead of UNAUTHENTICATED

- **Item:** TLS-2
- **Summary:** When an RPC's authority does not match the server certificate, Java fails the RPC with `UNAVAILABLE` instead of `UNAUTHENTICATED`. This applies only when `GRPC_ENABLE_PER_RPC_AUTHORITY_CHECK=true`; by default the check is not enforced (a warning is logged and the RPC is sent), which is tracked separately as open item TLS-6.
- **Description:** The per-RPC authority check (authority override / xDS authority rewrite) is an authentication failure, not a transient one. `UNAVAILABLE` is retryable (including transparent/configured retries and wait-for-ready style handling), so the call may be retried pointlessly against the same server. The spec requires `UNAUTHENTICATED`.
- **Evidence:** grpc-java `netty/src/main/java/io/grpc/netty/X509AuthorityVerifier.java` / `NettyClientHandler` (authority verification failure status); `okhttp/src/main/java/io/grpc/okhttp/OkHttpClientTransport.java` (`verifyAuthority`).
- **Spec:** TLS: Per-RPC Authority Verification

### [medium] Java records a synthetic attempt for calls that fail before any attempt is created

- **Item:** METRICS-1
- **Summary:** Java increments `grpc.client.attempt.started` at call creation and records a synthetic attempt at call end when no stream was ever created.
- **Description:** When a call fails before any attempt is created (for example, a non-wait-for-ready call failing because the resolver reports an error), the spec says no attempt events are generated and only call-level metrics are recorded. Java increments `grpc.client.attempt.started` when the call is created and, if no stream was created, records `grpc.client.attempt.duration` (elapsed call time), attempt message sizes of 0, and the call's status as a synthetic attempt. This inflates attempt counts and skews attempt-duration histograms. Fixing it changes Java's metric values (release note advisable).
- **Evidence:** grpc-java `opentelemetry/src/main/java/io/grpc/opentelemetry/OpenTelemetryMetricsModule.java` (`CallAttemptsTracerFactory` constructor; `recordFinishedCall`, `attemptsPerCall.get() == 0` branch)
- **Spec:** Instrumentation Architecture: Call-Attempt Tracer Event Points

### [medium] Java subchannel metrics use the raw target string for grpc.target

- **Item:** METRICS-4
- **Summary:** Java labels subchannel metrics with the raw target string passed to the channel builder instead of the canonical target URI.
- **Description:** The spec requires `grpc.target` on `grpc.subchannel.*` metrics to be the creating channel's canonical target URI (scheme included), the same value as per-call metrics, so subchannel and call metrics can be joined. Java uses the raw builder target string.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/InternalSubchannel.java` (`target` used for metric labels), `ManagedChannelImpl` (target passed to subchannels)
- **Spec:** Metric Catalog: Subchannel Metrics

### [medium] Java binary logging reads GRPC_BINARY_LOG_CONFIG and requires code to enable

- **Item:** BINARY_LOG-2
- **Summary:** Java reads `GRPC_BINARY_LOG_CONFIG` instead of `GRPC_BINARY_LOG_FILTER`, and only after the application installs a binary log in code.
- **Description:** The spec requires binary logging to be enabled through the `GRPC_BINARY_LOG_FILTER` environment variable without code changes. Java reads `GRPC_BINARY_LOG_CONFIG` (matching its vendored copy of binarylog.proto, not the canonical grpc-proto file), and only when the application calls `BinaryLogs.createBinaryLog()` and installs it on a channel/server builder. Java should also accept `GRPC_BINARY_LOG_FILTER` and enable logging without code changes. (Its malformed-string handling — throwing at creation — conforms.)
- **Evidence:** grpc-java `services/src/main/java/io/grpc/protobuf/services/BinaryLogProviderImpl.java`, `BinlogHelper.FactoryImpl`, `services/src/main/proto/grpc/binlog/v1/binarylog.proto` (comment says GRPC_BINARY_LOG_CONFIG)
- **Spec:** Binary Logging: Enabling Binary Logging

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

### [medium] Servers never set TCP_USER_TIMEOUT

- **Item:** R7
- **Summary:** Java servers do not set TCP_USER_TIMEOUT to KEEPALIVE_TIMEOUT when keepalive is enabled (which is the default).
- **Description:** The spec requires clients and servers to set TCP_USER_TIMEOUT to KEEPALIVE_TIMEOUT (20s by default) when keepalive is enabled, on platforms that support it. Java sets it only on Netty epoll client channels with keepalive enabled, and never on servers. As a result, Java servers take much longer to detect dead peers when sent data goes unacknowledged.
- **Evidence:** grpc-java `NettyClientTransport` sets it (epoll only); `NettyServer` / `NettyServerTransport` do not.
- **Spec:** 05-server/02-transports/02-http2.md "TCP_USER_TIMEOUT"

### [medium] Netty client maps RST_STREAM(NO_ERROR) before trailers to UNAVAILABLE

- **Item:** R12
- **Summary:** grpc-java's Netty transport reports UNAVAILABLE for RST_STREAM(NO_ERROR) received before trailers; the spec requires INTERNAL and forbids a retryable code.
- **Description:** When the server resets a stream with NO_ERROR before sending complete trailers, Netty reports UNAVAILABLE (OkHttp correctly reports INTERNAL). UNAVAILABLE is retryable by retry policies and commonly by applications, but the server may already have processed the call, so retrying can duplicate non-idempotent work. The spec maps NO_ERROR to INTERNAL, as Go and C++ do.
- **Evidence:** grpc-java netty NettyClientHandler / Utils status mapping for RST_STREAM (NO_ERROR -> UNAVAILABLE); okhttp maps to INTERNAL.
- **Spec:** gRPC over HTTP/2 (03-wire-protocol/01-http2.md), "RST_STREAM"

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
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), "Token Accounting".

### [medium] Disabling retries also disables transparent retries

- **Item:** R45
- **Summary:** `disableRetry()` bypasses `RetriableStream`, so transparent retries stop too, but the spec says they SHOULD continue.
- **Description:** With retries disabled on the channel, Java creates streams without the retry layer, so failures that never reached the server application (for example `REFUSED_STREAM` or a stream above a GOAWAY's last-stream-id) go straight to the application. The spec says transparent retries SHOULD still happen when retries are disabled, because they are safe and avoid spurious errors. Applications or wrapper libraries that disable retries to avoid duplicating configured retries see extra `UNAVAILABLE` errors, for example during server graceful shutdown.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/ManagedChannelImpl.java` (`ChannelStreamProvider`); grpc-java#7947.
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), "Transparent Retries" and "Limits and Disabling Retries".

### [medium] Custom call credentials cannot declare a minimum security level

- **Item:** R126
- **Summary:** Java's `CallCredentials` API has no way to declare a minimum security level, so custom call credentials default to no check instead of `PRIVACY_AND_INTEGRITY`.
- **Description:** In Java, a custom `CallCredentials` must itself call `allowedSecurityLevel(requestInfo, minSecurity)` (or inspect `RequestInfo.getSecurityLevel()`) inside `applyRequestMetadata`; gRPC performs no check before invoking it. The spec requires application-defined call credentials to be able to declare a minimum level, with a default of `PRIVACY_AND_INTEGRITY` when none is declared, and requires gRPC to skip invoking the credential and fail the RPC with `UNAUTHENTICATED` when the connection's level is too low. As a result, custom credentials that forget the check can send bearer tokens over insecure connections. Fixing this needs an API addition (e.g. a declared minimum level checked by the channel) and has a compatibility risk for existing credentials that rely on running on insecure connections.
- **Evidence:** grpc-java `api/src/main/java/io/grpc/CallCredentials.java` (`allowedSecurityLevel`, `RequestInfo.getSecurityLevel`); `core/src/main/java/io/grpc/internal/CallCredentialsApplyingTransportFactory.java` (no pre-invocation check); `auth/src/main/java/io/grpc/auth/GoogleAuthLibraryCallCredentials.java` (checks inside the credential).
- **Spec:** Security Model (`06-security/01-security-model.md`), Call Credential Minimum Security Level

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

- **Item:** R133, XDS_ROUTING-3
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

### [medium] Client fails calls with `CANCELLED`, or does not fail them, when a sent message exceeds the send size limit

- **Item:** audit (W2-02-004)
- **Summary:** When a request message exceeds `maxOutboundMessageSize`, the client cancels the call with `CANCELLED` instead of failing it with `RESOURCE_EXHAUSTED`. If the write was queued (stream waiting for an LB pick, or a buffered retry replay), the `RESOURCE_EXHAUSTED` exception escapes on another thread and the call is not failed at all. The GET framer ignores the limit.
- **Description:** (1) `MessageFramer` throws `Status.RESOURCE_EXHAUSTED.asRuntimeException()`, but `ClientCallImpl.sendMessageInternal` catches every `RuntimeException` and cancels the stream with `Status.CANCELLED.withCause(e)`, so the application sees `CANCELLED` (with the real status only as the cause). (2) When the message is written before the real stream exists, the write is queued in `DelayedStream` (or in the `RetriableStream` buffer for a new attempt) and runs later in `DelayedStream.drainPendingCalls` / `RetriableStream.drain`, outside that try/catch. The `StatusRuntimeException` propagates out of the drain (the code has `TODO(ejona): exception handling`), the remaining queued operations such as half-close are skipped, and the call is never failed with `RESOURCE_EXHAUSTED`; it typically waits until its deadline. (3) `AbstractClientStream.GetFramer.setMaxOutboundMessageSize` is empty (`TODO(zsurocking)`), so calls sent with GET are never size-checked.
- **Evidence:** grpc-java ed3bf6b76b: [ClientCallImpl.java L515-L529](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ClientCallImpl.java#L515-L529), [MessageFramer.java L237-L244](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/MessageFramer.java#L237-L244), [DelayedStream.java L190-L194](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/DelayedStream.java#L190-L194), [RetriableStream.java L346-L348](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/RetriableStream.java#L346-L348), [RetriableStream.java L595-L603](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/RetriableStream.java#L595-L603), [AbstractClientStream.java L542-L544](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/AbstractClientStream.java#L542-L544)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), Message Size Limits

### [medium] Initial resolution failure releases wait-for-ready RPCs from the resolver queue without a service config

- **Item:** audit (W2-04-014)
- **Summary:** If the first resolution attempt fails, the channel installs the default service config (or no config) and releases every RPC waiting for a resolver result, including wait-for-ready RPCs, so they run without the method config that a later successful resolution provides.
- **Description:** On a resolver error (`Listener2.onError`, or a result whose addresses are an error), `NameResolverListener.handleErrorInSyncContext` calls `RealChannel.onConfigError()`. While the config selector is still `INITIAL_PENDING_SELECTOR`, it installs the default service config's selector, or `null` if there is no default, and `updateConfigSelector` reprocesses all `pendingCalls`. Wait-for-ready RPCs therefore leave the resolver queue and go on to the LB pick with no method config (no timeout, retry or hedging policy, or message limits from the service config), and they never get the config that the resolver returns once resolution succeeds. Per the spec, they stay queued until a valid config is applied.
- **Evidence:** grpc-java ed3bf6b76b: [ManagedChannelImpl.java L936-L960](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L936-L960), [ManagedChannelImpl.java L1812-L1816](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1812-L1816)
- **Spec:** Per-call Configuration and Call Flow (`04-client-channel/05-call-dispatch.md`), Starting an RPC and Waiting for a Resolver Result

### [medium] least_request's active-request counter can go negative

- **Item:** audit (W2-07-015)
- **Summary:** least_request increments an endpoint's counter in `ClientStreamTracer.streamCreated()` but decrements it in `streamClosed()`. A stream that fails after the pick but before the transport creates it gets only `streamClosed()`, so the counter goes below zero and that endpoint attracts more picks.
- **Description:** `OutstandingRequestsTracingFactory` increments `inFlights` in `streamCreated` and decrements it in `streamClosed`. After the pick, the stream can fail before the transport calls `streamCreated`: `FailingClientStream.start` calls only `streamClosed`. This happens, for example, when call credentials fail (`MetadataApplierImpl.fail`) or the chosen transport is already shut down. Each such failure lowers the counter by one with no matching increment. Because the picker chooses the candidate with the fewest active requests, an endpoint whose calls repeatedly fail this way gets a negative count and receives a larger share of traffic. The spec increments when the pick completes (or synchronously when the tracker is created or started) so that the increment and decrement always pair up.
- **Evidence:** grpc-java ed3bf6b76b: [LeastRequestLoadBalancer.java L273-L295](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/LeastRequestLoadBalancer.java#L273-L295), [FailingClientStream.java L54-L61](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/FailingClientStream.java#L54-L61), [MetadataApplierImpl.java L82-L87](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/MetadataApplierImpl.java#L82-L87), [NettyClientTransport.java L207-L211](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/NettyClientTransport.java#L207-L211)
- **Spec:** `least_request` LB Policy (`04-client-channel/lb-policies/least_request.md`), Outstanding Request Counters

### [medium] `priority_experimental` cannot be configured through JSON

- **Item:** audit (W2-08-012, W2-08-013)
- **Summary:** `PriorityLoadBalancerProvider.parseLoadBalancingPolicyConfig` always returns an error ("cannot be used from service config"), so `priority_experimental` can't be selected in a service config's `loadBalancingConfig` or used as a child of another policy configured through JSON.
- **Description:** Java builds `PriorityLbConfig` objects only in memory (from `cds`) and fails all JSON config parsing. The spec requires the policy to be selectable through `loadBalancingConfig` and usable by custom parent policies. When JSON parsing is added, note that the `PriorityLbConfig` constructor also rejects an empty `priorities` list (`checkArgument(!priorities.isEmpty(), ...)`), which the spec says is valid (it makes the policy report TRANSIENT_FAILURE with `UNAVAILABLE`). `cds` avoids building an empty config today, so that check has no visible effect yet. See also PRIORITY-4 (JSON field naming).
- **Evidence:** grpc-java ed3bf6b76b: [PriorityLoadBalancerProvider.java L58-L62](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/PriorityLoadBalancerProvider.java#L58-L62), [PriorityLoadBalancerProvider.java L68-L81](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/PriorityLoadBalancerProvider.java#L68-L81)
- **Spec:** `priority` LB Policy (`04-client-channel/lb-policies/priority.md`), Configuration, Validation, and API Requirements

### [medium] weighted_target picker throws when the sum of child weights exceeds the uint32 maximum

- **Item:** audit (W2-08-021)
- **Summary:** `WeightedRandomPicker` rejects a total weight above 4,294,967,295 with `IllegalArgumentException`, even though each child weight is a valid `uint32` and the total is kept in a `long`.
- **Description:** The spec types `targets{}.weight` as `uint32` and puts no limit on the sum, and the picker accumulates `total += c.weight`. Java checks `totalWeight <= UnsignedInteger.MAX_VALUE` in the `WeightedRandomPicker` constructor. That constructor runs in `WeightedTargetLoadBalancer.updateOverallBalancingState` inside the synchronization context, so the exception reaches the channel's uncaught-exception handler and the channel enters panic mode. Java's JSON parser limits each weight to `Integer.MAX_VALUE`, so this takes three or more large weights. It can also come from xDS, because Java's EDS parser does not reject a priority whose locality weights sum above the uint32 maximum.
- **Evidence:** grpc-java ed3bf6b76b: [WeightedRandomPicker.java L92-L110](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRandomPicker.java#L92-L110), [WeightedTargetLoadBalancer.java L146-L173](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedTargetLoadBalancer.java#L146-L173), [ManagedChannelImpl.java L190-L198](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L190-L198)
- **Spec:** `weighted_target` LB Policy (`04-client-channel/lb-policies/weighted_target.md`), Picker Implementation

### [medium] OkHttp TLS hostname verification never matches compressed IPv6 target names

- **Item:** audit (W2-10-008)
- **Summary:** `OkHostnameVerifier.verifyIpAddress` compares the target IP literal with `iPAddress` SANs as strings (`equalsIgnoreCase`), so an IPv6 target written in compressed form (for example `[::1]`) never matches the certificate's IPv6 SAN.
- **Description:** The spec matches an IP-address target name against IP-address SANs per RFC 9525 §6, which compares the address octets. The OkHttp transport strips only the brackets from the authority (`OkHttpTlsUpgrader.canonicalizeHost`) and compares that string with the SAN strings from `X509Certificate.getSubjectAlternativeNames()`, which the JDK renders for IPv6 in full uncompressed form (`0:0:0:0:0:0:0:1`). TLS handshakes to IPv6 literal targets therefore fail hostname verification on the OkHttp transport unless the target is written in that exact form.
- **Evidence:** grpc-java ed3bf6b76b: [OkHostnameVerifier.java L93-L101](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/third_party/okhttp/main/java/io/grpc/okhttp/internal/OkHostnameVerifier.java#L93-L101), [OkHttpTlsUpgrader.java L70](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/src/main/java/io/grpc/okhttp/OkHttpTlsUpgrader.java#L70), [OkHttpTlsUpgrader.java L88-L93](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/src/main/java/io/grpc/okhttp/OkHttpTlsUpgrader.java#L88-L93)
- **Spec:** TLS (`06-security/02-tls.md`), Server Certificate Verification

### [medium] Reflection `file_containing_symbol` returns `NOT_FOUND` for enums, extensions, fields, and enum values

- **Item:** audit (W2-12-010)
- **Summary:** The reflection service's symbol index contains only services, methods, and message types, so `file_containing_symbol` for an enum, an extension, a field, or an enum value answers `NOT_FOUND`.
- **Description:** The spec says `file_containing_symbol` accepts a fully qualified service, method, message, enum, or extension name, including nested types and their members, and that `NOT_FOUND` is for symbols the server does not know. `FileDescriptorIndex` adds only service, method, and message (including nested message) names to `fileDescriptorsBySymbol`. Extensions are indexed only by containing type and field number (for `file_containing_extension`), not by name. Enums, enum values, and fields are not indexed at all. Both the v1 and v1alpha services use this index (`ProtoReflectionService` delegates to `ProtoReflectionServiceV1`).
- **Evidence:** grpc-java ed3bf6b76b: [ProtoReflectionServiceV1.java L233](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ProtoReflectionServiceV1.java#L233), [ProtoReflectionServiceV1.java L479-L537](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ProtoReflectionServiceV1.java#L479-L537)
- **Spec:** Server Reflection (`07-services/02-reflection.md`), Requests; Errors

### [medium] Subchannel metrics leak `open_connections` on subchannel shutdown and always report `grpc.security_level` as `none`

- **Item:** audit (W2-05-016, W2-13-018)
- **Summary:** When a subchannel shuts down or drops its connection because of an address update, `InternalSubchannel` never records the disconnection, so `grpc.subchannel.open_connections` is never decremented and `subchannel shutdown` is never counted. `grpc.security_level` is read from the resolver's address attributes instead of the connected transport, so it is always `none`.
- **Description:** `InternalSubchannel.shutdown()` clears `activeTransport` and moves to SHUTDOWN before shutting down the transport. `updateAddresses()` clears `activeTransport` and shuts down the old transport later. When `transportShutdown()` then runs, it returns early (state is SHUTDOWN) or finds `activeTransport != transport`, so `recordDisconnection` is skipped. `recordDisconnection` holds the only `open_connections` decrement and the only `grpc.subchannel.disconnections` increment, so every subchannel shutdown (including channel idle and shutdown) leaves `open_connections` permanently one too high and never records `subchannel shutdown`. Separately, `recordConnectionAttemptSucceeded` and `recordDisconnection` take the security level from `addressIndex.getCurrentEagAttributes().get(ATTR_SECURITY_LEVEL)`. Transports set `ATTR_SECURITY_LEVEL` only on their own attributes after the handshake, so the label is always `none`, even on TLS and ALTS connections. On disconnection, `addressIndex.reset()` also runs before the labels are read, so with several addresses the decrement can use different `grpc.lb.backend_service`/`grpc.lb.locality` labels than the increment.
- **Evidence:** grpc-java ed3bf6b76b: [InternalSubchannel.java L387-L432](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L387-L432), [InternalSubchannel.java L438-L472](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L438-L472), [InternalSubchannel.java L604-L615](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L604-L615), [InternalSubchannel.java L634-L648](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L634-L648), [SubchannelMetrics.java L78-L107](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/SubchannelMetrics.java#L78-L107), [ProtocolNegotiators.java L736](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/ProtocolNegotiators.java#L736)
- **Spec:** Metric Catalog (`08-observability/04-metrics.md`), Common Attributes (`grpc.security_level`), Subchannel Metrics

### [medium] Channels created by LB policies are listed as top channels in Channelz

- **Item:** audit (W2-14-006)
- **Summary:** Channels created through the LB helper (`createOobChannel`, `createResolvingOobChannelBuilder`, used for example by RLS and grpclb) are `ManagedChannelImpl` instances that register themselves as Channelz root channels, so `GetTopChannels` returns them. They are never linked to their parent through `channel_ref`.
- **Description:** The spec defines a top channel as one the application created directly, and `GetTopChannels` excludes child channels. Internal channels used by a component of the parent belong under the parent as child channels. Java's `ManagedChannelImpl` constructor always calls `channelz.addRootChannel(this)`, including for helper-created channels (a TODO in `createResolvingOobChannelBuilder` notes the missing parent registration). `InternalChannelz.ChannelStats` has no child-channel list, so `ChannelzProtoUtil.toChannel` never sets `Channel.channel_ref`.
- **Evidence:** grpc-java ed3bf6b76b: [ManagedChannelImpl.java L674](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L674), [ManagedChannelImpl.java L1447-L1472](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1447-L1472), [ManagedChannelImpl.java L1489-L1491](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1489-L1491), [InternalChannelz.java L369-L378](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/api/src/main/java/io/grpc/InternalChannelz.java#L369-L378), [ChannelzProtoUtil.java L341-L352](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ChannelzProtoUtil.java#L341-L352)
- **Spec:** Channelz (`08-observability/06-channelz.md`), Terminology, Entity Graph, The Channelz Service

### [medium] HeaderMatcher `range_match` includes the range end

- **Item:** audit (W2-16-001, W2-11-020)
- **Summary:** `Matchers.HeaderMatcher.matches` tests `numValue >= range().start() && numValue <= range().end()`, so a header value equal to `end` matches, in both xDS route matching and xDS RBAC.
- **Description:** The spec defines `range_match` as the half-open range `[start, end)`: it matches when `start <= v < end`, as in Envoy's `Int64Range`. Java's closed range matches one extra value, so routes and RBAC policies that use `range_match` behave differently at the boundary from C++, Go, and Envoy.
- **Evidence:** grpc-java ed3bf6b76b: [Matchers.java L158-L166](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/Matchers.java#L158-L166)
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), `HeaderMatcher`; xDS HTTP Filters (`09-xds/07-http-filters.md`), Mapping RBAC Fields to gRPC

### [medium] VirtualHost selection prefers longer prefix wildcards over suffix wildcards and throws on host names or domains with a leading or trailing `.`

- **Item:** audit (W2-16-009)
- **Summary:** `RoutingUtils.findVirtualHostForHostName` compares wildcard pattern lengths without first comparing the kind (suffix vs prefix), and for duplicate suffix patterns the last virtual host wins. `matchHostName` throws `IllegalArgumentException` when the host name or a domain pattern starts or ends with `.`.
- **Description:** The spec ranks matches by kind first (exact, then suffix wildcard, then prefix wildcard, then `*`), then by length within a kind, and uses the first virtual host for ties. Java picks the longest wildcard of either kind, so for host `foo.bar.com` a virtual host with `foo.bar.*` beats one with `*.com`. When the same suffix pattern appears in two virtual hosts, Java picks the later one. Separately, a domain pattern such as `example.com.` is accepted at parse time, but matching against it (or any request `:authority` ending in `.`) throws instead of comparing. On the server this happens per RPC; on the client it happens while building the xDS config.
- **Evidence:** grpc-java ed3bf6b76b: [RoutingUtils.java L44-L80](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RoutingUtils.java#L44-L80), [RoutingUtils.java L94-L98](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RoutingUtils.java#L94-L98), [XdsServerWrapper.java L923-L924](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsServerWrapper.java#L923-L924), [XdsDependencyManager.java L262-L263](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L262-L263)
- **Spec:** RouteConfiguration (`09-xds/04-resources/03-route-configuration.md`), Domain Patterns

### [medium] ring_hash validates ring sizes after clamping to the local cap

- **Item:** R23, audit (W2-16-013)
- **Summary:** `RingHashLoadBalancerProvider.parseLoadBalancingPolicyConfigInternal` clamps `minRingSize` and `maxRingSize` to `RingHashOptions.getRingSizeCap()` (default 4096) before validating them, and never checks the 8388608 upper bound.
- **Description:** Values above 8388608 are clamped instead of rejected, and an inverted range such as `minRingSize: 8000, maxRingSize: 5000` passes once both are clamped to 4096. This applies both to service config JSON and to xDS clusters, whose converted config is validated by the same provider. The spec requires validating the configured values before applying the local cap, so that all clients accept and reject the same configs.
- **Evidence:** grpc-java ed3bf6b76b: [RingHashLoadBalancerProvider.java L89-L108](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RingHashLoadBalancerProvider.java#L89-L108)
- **Spec:** ring_hash (`04-client-channel/lb-policies/ring_hash.md`), Validation

### [medium] EDS `additional_addresses` (dualstack endpoints) ignored by default

- **Item:** audit (W2-16-020)
- **Summary:** `XdsEndpointResource` reads `Endpoint.additional_addresses` only when `GRPC_EXPERIMENTAL_XDS_DUALSTACK_ENDPOINTS` is set (default false). By default it drops every address after the first and does not validate the additional addresses.
- **Description:** The spec makes an endpoint's address list `endpoint.address` followed by `additional_addresses`, each validated like `endpoint.address` (gRFC A61). With Java's default, dual-stack backends get only one address, so the other address family is never tried, and invalid `additional_addresses` entries are not rejected. C++ and Go enable this by default.
- **Evidence:** grpc-java ed3bf6b76b: [XdsEndpointResource.java L111-L113](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L111-L113), [XdsEndpointResource.java L226-L236](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L226-L236)
- **Spec:** ClusterLoadAssignment and LbEndpointCollection (`09-xds/04-resources/05-endpoint.md`), LbEndpoint

### [medium] xds_cluster_impl ignores EDS service name and LRS server changes after the first update

- **Item:** audit (W2-17-016)
- **Summary:** `ClusterImplLoadBalancer.acceptResolvedAddresses` sets `edsServiceName`, the circuit-breaker counter, `lrsServerInfo`, and the drop stats object only inside `if (cluster == null)`, on the first update. Later updates that change `eds_service_name` or `lrs_load_reporting_server` keep the old counter and LRS objects.
- **Description:** The spec requires the policy to replace its circuit-breaker counter, keyed by (cluster, EDS service name), and its drop and locality stats objects, keyed by (LRS server, cluster, EDS service name), when those keys change. In Java, enabling LRS on an existing cluster never starts drop or load reporting for it (`dropStats` stays null and `lrsServerInfo` is final in `ClusterImplLbHelper`). Changing the LRS server or EDS service name keeps reporting under the old key and keeps sharing the old circuit-breaker counter. Recreating the policy, for example after a priority child is removed, picks up the new values.
- **Evidence:** grpc-java ed3bf6b76b: [ClusterImplLoadBalancer.java L135-L146](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L135-L146), [ClusterImplLoadBalancer.java L207-L214](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L207-L214), [ClusterImplLoadBalancer.java L330-L336](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L330-L336)
- **Spec:** `xds_cluster_impl` LB Policy (`09-xds/lb-policies/xds_cluster_impl.md`), Updates from the Parent; Load Reporting; Circuit Breaking

### [medium] Server Listener validation NACKs `use_original_dst: false` and misses several required checks

- **Item:** audit (W2-18-013)
- **Summary:** `XdsListenerResource.parseServerSideListener` checks `proto.hasUseOriginalDst()` instead of its value, so it NACKs an explicit `use_original_dst: false`. It accepts a Listener with neither `filter_chains` nor `default_filter_chain`, accepts a missing or non-TCP `socket_address`, and runs the FilterChainMatch uniqueness check on CIDR ranges that were not normalized.
- **Description:** The spec NACKs `use_original_dst` only when it is `true`, which means a control plane that sets the wrapper to `false` cannot configure Java servers. It also requires NACKing a Listener with no filter chains at all, and one whose `address` is not a TCP `socket_address`. Java accepts both, and the second only makes the server not serving (an "address mismatch" in `XdsServerWrapper`). Before checking for duplicate matchers, the spec clamps `prefix_len` to 32/128 and zeroes the host bits. Java compares raw `CidrRange` values, so chains such as `10.0.0.1/8` and `10.0.0.0/8` are not detected as duplicates.
- **Evidence:** grpc-java ed3bf6b76b: [XdsListenerResource.java L159-L162](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L159-L162), [XdsListenerResource.java L164-L216](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L164-L216), [XdsListenerResource.java L449-L467](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L449-L467), [XdsServerWrapper.java L449-L457](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsServerWrapper.java#L449-L457)
- **Spec:** xDS-Enabled Servers (`09-xds/08-server.md`), Listener Validation; Normalization and Uniqueness

### [medium] Email SANs are never matched against `match_subject_alt_names`

- **Item:** audit (W2-18-018)
- **Summary:** `XdsX509TrustManager.verifyOneSanInList` considers only DNS (`2`), URI (`6`), and IP address (`7`) SAN entries and returns `false` for email (`rfc822Name`, `1`) SANs.
- **Description:** The spec considers SAN entries of type DNS, URI, email, and IP address when checking `match_subject_alt_names`. Java skips email SANs, so a server whose certificate is identified only by an email SAN always fails the SAN check and the handshake fails.
- **Evidence:** grpc-java ed3bf6b76b: [XdsX509TrustManager.java L59-L61](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/security/trust/XdsX509TrustManager.java#L59-L61), [XdsX509TrustManager.java L176-L194](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/security/trust/XdsX509TrustManager.java#L176-L194)
- **Spec:** xDS Security (`09-xds/09-security.md`), Server Identity Verification

### [medium] Invalid `match_subject_alt_names` matchers are not NACKed and fail at handshake time

- **Item:** audit (W2-18-020)
- **Summary:** CDS validation does not check the `StringMatcher` entries in `match_subject_alt_names`, so a matcher with no pattern set or with a `safe_regex` that does not compile is accepted, and every handshake on the cluster then fails with an exception from `XdsX509TrustManager`.
- **Description:** The spec requires each `match_subject_alt_names` entry to be a valid `StringMatcher` (exactly one pattern set, and a `safe_regex` that compiles), and otherwise the resource is NACKed. `XdsClusterResource.validateCommonTlsContext` only checks that the list is empty on servers. With no pattern, `verifyDnsNameInPattern` throws `IllegalArgumentException` during the handshake; an invalid regex is compiled only during the handshake, where it throws `PatternSyntaxException`. The control plane never sees a NACK, and the cluster's connections fail.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClusterResource.java L500-L532](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L500-L532), [XdsX509TrustManager.java L108-L118](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/security/trust/XdsX509TrustManager.java#L108-L118)
- **Spec:** xDS Security (`09-xds/09-security.md`), `CommonTlsContext` Validation; Common Types (`09-xds/04-resources/01-common-types.md`), `StringMatcher`

### [medium] RBAC `metadata` matchers with `invert: true` never match

- **Item:** audit (W2-11-018, W2-18-007)
- **Summary:** `RbacFilter` converts every `Permission.metadata` and `Principal.metadata` into a matcher that never matches, without reading `MetadataMatcher.invert`.
- **Description:** gRPC treats Envoy dynamic metadata as an empty map, so the spec says a `MetadataMatcher` matches if and only if `invert` is `true`. Java never matches. As a result, a policy that uses `metadata: {invert: true}` behaves the opposite way: such a rule in a DENY policy never denies, and in an ALLOW policy it never allows. Go reads `invert`.
- **Evidence:** grpc-java ed3bf6b76b: [RbacFilter.java L246-L247](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RbacFilter.java#L246-L247), [RbacFilter.java L296-L297](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RbacFilter.java#L296-L297)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), Mapping RBAC Fields to gRPC

### [medium] A non-string `healthCheckConfig.serviceName` passes service config parsing and later panics the channel

- **Item:** audit (W2-04-020)
- **Summary:** Java doesn't check `healthCheckConfig.serviceName` when it parses the service config. A non-string value such as `123` is accepted, and under `round_robin` the health-checking wrapper throws `ClassCastException` while handling the resolver update. That puts the channel in panic mode for good.
- **Description:** `ManagedChannelServiceConfig.fromServiceConfig` stores the `healthCheckConfig` object from `ServiceConfigUtil.getHealthCheckedService` without checking `serviceName`. When the policy is the health-checking `round_robin`, `HealthCheckingLoadBalancerFactory`'s `acceptResolvedAddresses` calls `ServiceConfigUtil.getHealthCheckedServiceName` → `JsonUtil.getString`, which throws `ClassCastException` for a non-string. The exception escapes into the channel's `SynchronizationContext`, whose handler calls `panic()`: the channel moves to TRANSIENT_FAILURE for good and fails every RPC with `INTERNAL`. The spec says the config is invalid, so it must be rejected at parse time (the channel would keep its previous config). Under policies that don't read `healthCheckConfig`, the invalid config is accepted silently.
- **Evidence:** grpc-java ed3bf6b76b: [ManagedChannelServiceConfig.java L101-L102](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelServiceConfig.java#L101-L102), [ServiceConfigUtil.java L77-L83](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ServiceConfigUtil.java#L77-L83), [HealthCheckingLoadBalancerFactory.java L225-L233](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/HealthCheckingLoadBalancerFactory.java#L225-L233), [ManagedChannelImpl.java L188-L199](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L188-L199), [ManagedChannelImpl.java L779-L795](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L779-L795)
- **Spec:** Service Config (`04-client-channel/04-service-config.md`), Validation and Error Handling; `healthCheckConfig`

### [medium] No channel option to disable client-side health checking

- **Item:** audit (W2-05-023)
- **Summary:** Java has no channel-builder option that disables client-side health checking when the service config sets `healthCheckConfig`.
- **Description:** gRFC A17 and the spec require a channel option that disables health checking for a channel even if the service config enables it (C++ `GRPC_ARG_INHIBIT_HEALTH_CHECKING`, Go `grpc.WithDisableHealthCheck()`). `ManagedChannelBuilder` has no such option. The only ways around it are `disableServiceConfigLookUp()`, which drops the whole resolver-provided service config, or leaving the health-checking `round_robin` provider off the classpath.
- **Evidence:** grpc-java ed3bf6b76b: [ManagedChannelBuilder.java L628-L642](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/api/src/main/java/io/grpc/ManagedChannelBuilder.java#L628-L642) (service-config options; no health-checking option anywhere in the builder)
- **Spec:** Client-Side Health Checking (`04-client-channel/10-health-checking.md`), API Requirements

### [medium] xDS RBAC accepts host names, empty strings, and prefix lengths above 128 in CIDR ranges

- **Item:** audit (W2-11-017, W2-18-007); XDS_RBAC-22
- **Summary:** `RbacFilter` parses `CidrRange.address_prefix` with `InetAddress.getByName` and never checks `prefix_len`, so host names, empty strings, and `prefix_len` > 128 are accepted instead of NACKed. (Replaces the existing entry "xDS RBAC accepts hostnames, empty strings, and out-of-range prefix lengths in CIDR ranges".)
- **Description:** The spec requires `address_prefix` to be an IPv4 or IPv6 literal and `prefix_len` to be at most 128, else NACK; a `prefix_len` above the address width (but ≤ 128) is clamped to the width. `InetAddress.getByName` maps an empty string to the loopback address and resolves host names with a blocking DNS lookup during resource parsing; it only NACKs on `UnknownHostException`. `prefix_len` is never checked. (`CidrMatcher` with a prefix above the width shifts by a negative amount, which `BigInteger` treats as a left shift and so effectively compares the full address, matching the clamping rule.) `XdsListenerResource` already uses `InetAddresses.forString` for filter-chain CIDRs.
- **Evidence:** grpc-java ed3bf6b76b65fc76c1669ef70b71765844eb8a50: [RbacFilter.java L349-L365](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RbacFilter.java#L349-L365), [RbacFilter.java L169-L171](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RbacFilter.java#L169-L171)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), RBAC: Configuration Validation

### [medium] Aggregate cluster on a cycle fails with INTERNAL even when it has leaf clusters

- **Item:** XDS_DEPMGR-3
- **Summary:** When a cluster is reached again through a cycle, it gets an INTERNAL "Aggregate cluster cycle detected" entry that can't be overwritten later, so an aggregate on a cycle fails even when the cycle has reachable leaf clusters.
- **Description:** The spec says cycles just end the traversal: a cluster already visited contributes its leaves and is not expanded again, so a cyclic graph with leaf clusters is valid. C++ has a test for this (DependencyLoopWithLeafClusters). Java instead fails such aggregates.
- **Evidence:** grpc-java ed3bf6b76b: [XdsDependencyManager.java L306-L311](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L306-L311), [L384-L388](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L384-L388)
- **Spec:** Client Data Plane: Aggregate cluster graph (`09-xds/05-client.md`)

### [medium] Ambient xDS errors are not added to cluster resolution notes and don't trigger a new config

- **Item:** XDS_DEPMGR-4
- **Summary:** `XdsWatcherBase.onAmbientError` stores the error in a field marked `@SuppressWarnings("unused")` that is never read, and doesn't republish the config. `EndpointConfig` holds only a `StatusOr<EdsUpdate>` and has no resolution note.
- **Description:** The spec (following gRFC A88 "Handling Ambient Errors") says each EDS/LOGICAL_DNS cluster's resolution note joins the ambient errors for the Listener, the RouteConfiguration, the cluster's CDS resource, and its endpoint note, or is `xDS node ID:<id>` when all are empty. Ambient errors cause a new config to be delivered. Java drops ambient errors, so a lost xDS stream never shows up in RPC failure messages. The node ID is appended to error statuses instead of being used as a note.
- **Evidence:** grpc-java ed3bf6b76b: [XdsDependencyManager.java L666-L677](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L666-L677)
- **Spec:** Client Data Plane: Error handling (`09-xds/05-client.md`)

### [low] ring_hash maps request hashes above the largest ring hash to the last ring entry instead of wrapping to the first

- **Item:** audit (W2-08-001)
- **Summary:** `RingHashPicker.getTargetIndex` returns `ring.size() - 1` instead of wrapping to index 0 when the request hash is greater than every ring entry's hash.
- **Description:** Java sorts the ring and searches it with signed `long` comparisons. Because a signed ordering is a rotation of the unsigned circle, this alone would select the same entries, as long as the search wraps. But when the binary search runs off the high end (`low == ring.size()`), the method returns `mid = ring.size() - 1`, the entry just before the wrap point, instead of index 0. Hashes in the arc between the largest ring hash and `Long.MAX_VALUE` (about 1/ring_size of all hashes) start the endpoint search at the wrong entry. Those requests can therefore go to a different endpoint than in other implementations.
- **Evidence:** grpc-java ed3bf6b76b: [RingHashLoadBalancer.java L393-L416](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java#L393-L416), [RingHashLoadBalancer.java L530-L531](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java#L530-L531)
- **Spec:** `ring_hash` LB Policy (`04-client-channel/lb-policies/ring_hash.md`), Features

### [low] `xds_cluster_manager_experimental` config uses `childPolicy`/`lbPolicy` instead of `children`/`childPolicy`

- **Item:** audit (W1-B-003)
- **Summary:** `ClusterManagerLoadBalancerProvider.parseLoadBalancingPolicyConfig` reads the children map from the key `childPolicy` and each child's policy list from `lbPolicy`. The spec names them `children` and `childPolicy`.
- **Description:** `XdsNameResolver` generates the config with the same non-standard names, so the policy works when the xds resolver creates it. A config that uses the spec field names (for example in a service config written by hand) fails with "No child policy provided for cluster_manager LB policy". C++ and Go parse `children.<name>.childPolicy`.
- **Evidence:** grpc-java ed3bf6b76b: [ClusterManagerLoadBalancerProvider.java L71-L99](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ClusterManagerLoadBalancerProvider.java#L71-L99), [XdsNameResolver.java L324-L333](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L324-L333)
- **Spec:** `xds_cluster_manager` LB Policy (`09-xds/lb-policies/xds_cluster_manager.md`), Configuration

### [low] `grpc-timeout` parser accepts a leading `+` or `-` sign

- **Item:** audit (W2-01-014)
- **Summary:** `GrpcUtil.TimeoutMarshaller.parseAsciiString` uses `Long.parseLong` on the digits before the unit, so a signed value such as `-5S` or `+10m` is accepted, but `TimeoutValue` allows only `1*8DIGIT`.
- **Description:** A negative value is turned into an already-expired deadline instead of being treated as unparseable, which the spec says SHOULD fail the call with `INTERNAL`.
- **Evidence:** grpc-java ed3bf6b76b: [GrpcUtil.java L683-L704](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/GrpcUtil.java#L683-L704)
- **Spec:** gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), `grpc-timeout`

### [low] `StatusProto` lets applications send rich error details with an `OK` status

- **Item:** audit (W2-01-015)
- **Summary:** `StatusProto.toStatusException` and `toStatusRuntimeException` accept a `com.google.rpc.Status` with `code` 0 (`OK`) and attach it as `grpc-status-details-bin`. If a server passes the result to `onError`, the call ends with `OK` and the details trailer is sent.
- **Description:** The spec forbids sending details with an `OK` status. `StatusProto.toStatus` checks only that the code is a known value. Go's `status.WithDetails` returns an error for `OK`.
- **Evidence:** grpc-java ed3bf6b76b: [StatusProto.java L51-L53](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/protobuf/src/main/java/io/grpc/protobuf/StatusProto.java#L51-L53), [StatusProto.java L125-L142](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/protobuf/src/main/java/io/grpc/protobuf/StatusProto.java#L125-L142)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), Rich Error Details

### [low] xDS fallback treats a NACKed resource with no cached value as uncached

- **Item:** audit (W2-15-011)
- **Summary:** `ResourceSubscriber.hasResult()` returns `data != null || absent`, which is `false` for a resource that was NACKed with no previously accepted value. When an ADS stream later fails without a response, `handleStreamClosed` counts that resource as uncached and falls back to the next server.
- **Description:** For fallback purposes the spec counts a resource as cached once it has been received, valid or not, and treats only `REQUESTED` entries as uncached. In Java, an authority whose only missing resources were NACKed by the primary server still falls back to a lower-priority server when the primary becomes unreachable, unless `fallback_on_reachability_only` is set. The same applies after a NACK that clears cached data under `fail_on_data_errors`.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClientImpl.java L837-L839](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L837-L839), [XdsClientImpl.java L1017-L1021](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L1017-L1021), [XdsClientImpl.java L1076-L1088](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L1076-L1088)
- **Spec:** XdsClient (`09-xds/03-xds-client.md`), Fallback

### [low] CSDS reports `UNKNOWN` for watched resources until a request is sent on a ready stream

- **Item:** audit (W2-15-014)
- **Summary:** `XdsClientImpl.ResourceSubscriber` starts in `ResourceMetadataStatus.UNKNOWN` and moves to `REQUESTED` only when a `DiscoveryRequest` naming it is sent on a ready ADS stream. While the xDS channel is connecting or in backoff, CSDS reports `client_status: UNKNOWN`.
- **Description:** The spec creates a new cache entry in state `REQUESTED` when the watch starts, and CSDS maps `REQUESTED` to `ClientResourceStatus.REQUESTED`. `UNKNOWN` is not a cache entry state in the spec. The difference shows up in CSDS output and in tools that read it.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClientImpl.java L724-L726](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L724-L726), [XdsClientImpl.java L774-L803](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L774-L803), [ControlPlaneClient.java L191-L192](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/ControlPlaneClient.java#L191-L192), [CsdsService.java L240-L243](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/CsdsService.java#L240-L243)
- **Spec:** Client Status Discovery Service (CSDS) (`09-xds/11-csds.md`), `GenericXdsConfig`; XdsClient (`09-xds/03-xds-client.md`), Watcher API

### [low] CSDS can recreate a released XdsClient and remove a newer one from the shared map

- **Item:** audit (W2-15-014)
- **Summary:** `CsdsService` gets the pool for each target from `SharedXdsClientPoolProvider.get()` and then calls `getObject()`/`returnObject()` on it. If the last channel releases that pool in between, `getObject()` creates a new `XdsClientImpl` for a pool that is no longer in the map, and the following `returnObject()` unconditionally runs `targetToXdsClientMap.remove(target)`.
- **Description:** The spec destroys an XdsClient instance when its last user releases it, and keeps one shared instance per target. In this race, CSDS briefly creates an extra XdsClient after the instance was destroyed. If a new channel for the same target created a fresh pool in the meantime, the stale pool's `returnObject()` removes the fresh pool from the map. Later channels for that target then create yet another XdsClient instead of sharing the existing one.
- **Evidence:** grpc-java ed3bf6b76b: [CsdsService.java L164-L179](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/CsdsService.java#L164-L179), [SharedXdsClientPoolProvider.java L82-L84](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/SharedXdsClientPoolProvider.java#L82-L84), [SharedXdsClientPoolProvider.java L182-L229](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/SharedXdsClientPoolProvider.java#L182-L229)
- **Spec:** XdsClient (`09-xds/03-xds-client.md`), XdsClient Instances

### [low] OkHttp CONNECT target uses a reverse-DNS hostname instead of the IP literal for resolved addresses

- **Item:** audit (W2-05-020)
- **Summary:** OkHttp builds the CONNECT target with `InetSocketAddress.getHostName()`, which does a blocking reverse DNS lookup for an address that has no hostname (such as an xDS endpoint behind an HTTP CONNECT proxy) and sends the PTR hostname instead of `ip:port`.
- **Description:** `OkHttpClientTransport.createHttpProxyRequest` sets the tunnel host from `address.getHostName()`. For name mapping, the target is an unresolved `InetSocketAddress` and no lookup happens. For xDS-configured proxies, the target is the endpoint address built from an IP literal without a hostname, so `getHostName()` performs a reverse lookup on the connect path and, if a PTR record exists, the `CONNECT` request line and `Host` header carry that hostname rather than the IP literal. Netty uses `getHostString()` semantics and is not affected.
- **Evidence:** grpc-java ed3bf6b76b: [OkHttpClientTransport.java L917-L923](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/src/main/java/io/grpc/okhttp/OkHttpClientTransport.java#L917-L923), [OkHttpClientTransport.java L864-L867](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/src/main/java/io/grpc/okhttp/OkHttpClientTransport.java#L864-L867), [CdsLoadBalancer2.java L484-L487](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/CdsLoadBalancer2.java#L484-L487), [XdsEndpointResource.java L249-L258](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L249-L258)
- **Spec:** HTTP CONNECT Proxy Support (`04-client-channel/09-proxy.md`), CONNECT Handshake

### [low] weighted_round_robin counts endpoints that never reported a load as `endpoint_weight_stale`

- **Item:** audit (W2-07-008)
- **Summary:** An endpoint's `lastUpdated` starts at 0 instead of unset, so an endpoint that has never received a load report is counted in `grpc.lb.wrr.endpoint_weight_stale` instead of `grpc.lb.wrr.endpoint_weight_not_yet_usable`.
- **Description:** `WeightedChildLbState.lastUpdated` and `nonEmptySince` both default to 0 (the spec starts `non_empty_since` at infinity and `last_updated` unset). `getWeight` first checks `now - lastUpdated >= weightExpirationPeriodNanos`, and has no case for "no report yet". Because `ticker.nanoTime()` is usually far above the 180 s default expiration, every new endpoint is reported as stale on each scheduler build until its first load report. The weight used is 0 either way, so only the metrics are wrong.
- **Evidence:** grpc-java ed3bf6b76b: [WeightedRoundRobinLoadBalancer.java L298-L300](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L298-L300), [WeightedRoundRobinLoadBalancer.java L313-L329](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L313-L329)
- **Spec:** `weighted_round_robin` LB Policy (`04-client-channel/lb-policies/weighted_round_robin.md`), Blackout and Expiration

### [low] weighted_round_robin records WRR metrics while in TRANSIENT_FAILURE

- **Item:** audit (W2-07-011)
- **Summary:** When no child is READY and none is connecting, Java reports TRANSIENT_FAILURE with a `WeightedRoundRobinPicker` built over the failing children, so each picker build and each weight-update tick records `endpoint_weights`, `endpoint_weight_stale`/`not_yet_usable`, and `rr_fallback` for endpoints that are not READY.
- **Description:** `updateOverallBalancingState` calls `createReadyPicker(getChildLbStates())` for the TRANSIENT_FAILURE picker, which runs `updateWeight` and builds a scheduler over the failing children. The periodic `UpdateWeightTask` keeps doing this every `weightUpdatePeriod` while the channel is in TRANSIENT_FAILURE. Picks still fail with a child's error, so routing is not affected. The spec puts only READY children in the scheduler and records the metrics on each scheduler build, so these extra metrics should not be recorded.
- **Evidence:** grpc-java ed3bf6b76b: [WeightedRoundRobinLoadBalancer.java L213-L249](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L213-L249), [WeightedRoundRobinLoadBalancer.java L439-L448](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L439-L448)
- **Spec:** `weighted_round_robin` LB Policy (`04-client-channel/lb-policies/weighted_round_robin.md`), Picker Implementation and Metrics

### [low] weighted_round_robin ignores a change to `metricNamesForComputingUtilization` until the picker otherwise changes

- **Item:** audit (W2-07-011)
- **Summary:** `WeightedRoundRobinPicker.equals` and its hash code ignore the metric names, so a config update that changes only `metricNamesForComputingUtilization` produces a picker that compares equal and is not published. Per-call load reports keep being converted with the old metric names.
- **Description:** The picker holds per-child `OrcaPerRequestReportListener`s created with the config's metric names. `updateBalancingState` publishes a new picker only if the state changed or `!picker.equals(currentPicker)`. `equals` compares the child pickers, `sequence`, `enableOobLoadReport`, and `errorUtilizationPenalty`, but not the metric names, so the old picker, with listeners using the old names, stays in use until some other change (a child state change or another config field) produces a different picker.
- **Evidence:** grpc-java ed3bf6b76b: [WeightedRoundRobinLoadBalancer.java L286-L292](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L286-L292), [WeightedRoundRobinLoadBalancer.java L525-L568](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L525-L568), [WeightedRoundRobinLoadBalancer.java L601-L616](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L601-L616)
- **Spec:** `weighted_round_robin` LB Policy (`04-client-channel/lb-policies/weighted_round_robin.md`), Updates from the Parent

### [low] ring_hash rejects updates whose endpoint weights sum above the uint32 maximum

- **Item:** audit (W2-08-003)
- **Summary:** `RingHashLoadBalancer.validateAddrList` fails the whole update with `UNAVAILABLE` if the endpoint weights add up to more than 4294967295.
- **Description:** The ring is built from normalized weights (`weight / total`), and the spec rejects an update only when the endpoint list is empty or is an error. Java also rejects an update whose total weight exceeds `UnsignedInteger.MAX_VALUE`. With xDS and the default A113 weight normalization, a priority's weights sum to about 2^31, so this is reached only through a custom resolver that sets large endpoint weights, or with `GRPC_EXPERIMENTAL_PF_WEIGHTED_SHUFFLING=false` (locality weight × endpoint weight).
- **Evidence:** grpc-java ed3bf6b76b: [RingHashLoadBalancer.java L265-L297](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RingHashLoadBalancer.java#L265-L297)
- **Spec:** `ring_hash` LB Policy (`04-client-channel/lb-policies/ring_hash.md`), Updates from the Parent

### [low] priority ignores failover-timer events from a deactivated child

- **Item:** audit (W2-08-015)
- **Summary:** When a deactivated child (deletion timer pending) reports a new state, `PriorityLoadBalancer` records it but skips the failover-timer logic, so a stale pending timer or a stale "READY/IDLE seen since TRANSIENT_FAILURE" flag carries over if the child is reactivated.
- **Description:** In `ChildLbState.ChildHelper.updateBalancingState`, the early `return` for a pending `deletionTimer` comes before the code that cancels `failOverTimer` on READY, IDLE, or TRANSIENT_FAILURE, restarts it on CONNECTING, and updates `seenReadyOrIdleSinceTransientFailure`. A child deactivated while its failover timer was pending keeps that timer running even after it reports TRANSIENT_FAILURE. If it is reactivated before the timer fires, priority selection treats it as still trying to connect. Likewise, a deactivated child that went from READY to TRANSIENT_FAILURE keeps the flag set, so on reactivation a CONNECTING report wrongly restarts the failover timer.
- **Evidence:** grpc-java ed3bf6b76b: [PriorityLoadBalancer.java L327-L355](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/PriorityLoadBalancer.java#L327-L355)
- **Spec:** `priority` LB Policy (`04-client-channel/lb-policies/priority.md`), Failover Timer and Calls From Children

### [low] weighted_target JSON parser rejects a missing or empty `targets` and weights of 2^31 or more

- **Item:** audit (W2-08-020)
- **Summary:** `WeightedTargetLoadBalancerProvider.parseLoadBalancingPolicyConfig` rejects a config whose `targets` is absent or `{}`, and parses `weight` as a signed 32-bit integer, so valid `uint32` weights in `[2^31, 2^32 - 1]` make the config invalid.
- **Description:** The spec gives `targets` a default of `{}` (the policy then reports TRANSIENT_FAILURE) and types `weight` as `uint32` greater than 0. Java returns an error for a missing or empty `targets`, and `JsonUtil.getNumberAsInteger` throws for any weight above `Integer.MAX_VALUE`, which also makes the config invalid. Only JSON configs are affected, since xDS builds `WeightedTargetConfig` in memory. See also "Java weighted_target reports no state when targets is empty" for the runtime behavior with no targets.
- **Evidence:** grpc-java ed3bf6b76b: [WeightedTargetLoadBalancerProvider.java L79-L114](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/WeightedTargetLoadBalancerProvider.java#L79-L114), [JsonUtil.java L129-L142](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/JsonUtil.java#L129-L142)
- **Spec:** `weighted_target` LB Policy (`04-client-channel/lb-policies/weighted_target.md`), Configuration

### [low] Retry policy with empty `retryableStatusCodes` is accepted when `perAttemptRecvTimeout` is present

- **Item:** audit (W2-09-009)
- **Summary:** Java accepts `"retryableStatusCodes": []` in a `retryPolicy` whenever the JSON also contains `"perAttemptRecvTimeout"`, instead of rejecting the service config.
- **Description:** The spec requires `retryableStatusCodes` to be a non-empty JSON array and does not define `perAttemptRecvTimeout`. Java skips the non-empty check when `perAttemptRecvTimeout` is set, although nothing outside `RetryPolicy` uses the parsed value. Go always rejects an empty list. C++ relaxes the check only when its experimental hedging channel argument is enabled.
- **Evidence:** grpc-java ed3bf6b76b: [ManagedChannelServiceConfig.java L362-L373](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelServiceConfig.java#L362-L373)
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), Fields and Validation

### [low] SPIFFE bundle map loader rejects an empty `trust_domains` map and accepts invalid trust domains, missing `keys`, and bad `x5c` arrays

- **Item:** audit (W2-10-017)
- **Summary:** `SpiffeUtil.loadTrustBundleFromFile` rejects `"trust_domains": {}`, does not validate trust domain names, accepts a trust domain with no `keys`, and accepts `x5c` arrays that are missing, empty, or have more than one element.
- **Description:** The spec says an empty `trust_domains` map is valid and rejects every peer, each map key MUST be a valid trust domain (non-empty, at most 255 characters, only `a-z`, `0-9`, `.`, `-`, `_`), `keys` is required, and `x5c` MUST have exactly one element. If any entry is invalid, the whole map is invalid. Java throws on an empty map. It never checks the map keys. It maps a trust domain that is `{}` or has no `keys` to an empty root set. It silently skips a key entry whose `x5c` is missing or empty, and uses only `x5c[0]` when there are more.
- **Evidence:** grpc-java ed3bf6b76b: [SpiffeUtil.java L172-L186](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/SpiffeUtil.java#L172-L186), [SpiffeUtil.java L201-L203](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/SpiffeUtil.java#L201-L203), [SpiffeUtil.java L228-L250](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/SpiffeUtil.java#L228-L250)
- **Spec:** TLS (`06-security/02-tls.md`), Bundle Map Format

### [low] Reflection `all_extension_numbers_of_type` returns `NOT_FOUND` for a known message type with no extensions

- **Item:** audit (W2-12-011)
- **Summary:** For a message type the server knows but that has no extensions, `all_extension_numbers_of_type` answers `NOT_FOUND` ("Type not found.") instead of an `all_extension_numbers_response` with an empty `extension_number` list.
- **Description:** `FileDescriptorIndex.getExtensionNumbersOfType` looks the type up only in `fileDescriptorsByExtensionAndNumber`, which has an entry only for types that are extended at least once. The spec reserves `NOT_FOUND` for types the server does not know. A known type with no extensions should get a response that lists no numbers.
- **Evidence:** grpc-java ed3bf6b76b: [ProtoReflectionServiceV1.java L250-L267](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ProtoReflectionServiceV1.java#L250-L267), [ProtoReflectionServiceV1.java L384-L391](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ProtoReflectionServiceV1.java#L384-L391), [ProtoReflectionServiceV1.java L471-L477](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ProtoReflectionServiceV1.java#L471-L477), [ProtoReflectionServiceV1.java L524-L537](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ProtoReflectionServiceV1.java#L524-L537)
- **Spec:** Server Reflection (`07-services/02-reflection.md`), Requests; Errors

### [low] Channelz reports unset timestamps as the Unix epoch, unknown flow-control windows as -1, and fails `GetSocket` for in-process sockets

- **Item:** audit (W2-14-011)
- **Summary:** `ChannelzProtoUtil` always sets `last_call_started_timestamp` and the four `SocketData` timestamps (giving `1970-01-01T00:00:00Z` when nothing happened yet), sets the flow-control windows to `-1` when the transport has no flow-control reader, and answers `GetSocket` with `UNIMPLEMENTED` for in-process transport sockets.
- **Description:** The spec says these timestamps are unset until the event first happens, and the flow-control windows are unset when the transport has no flow control or the value is unknown. Java converts the raw nanosecond fields with `Timestamps.fromNanos` without checking for 0, and serializes `TransportTracer`'s `-1` placeholder as `Int64Value.of(-1)`. In-process transports are registered in Channelz as client sockets (subchannel `socket_ref`) and server sockets, but `InProcessTransport.getStats()` returns null. `ChannelzProtoUtil.getFuture` turns that into `UNIMPLEMENTED`, while the spec says `GetSocket` returns the socket or `NOT_FOUND`.
- **Evidence:** grpc-java ed3bf6b76b: [ChannelzProtoUtil.java L143](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ChannelzProtoUtil.java#L143), [ChannelzProtoUtil.java L228-L239](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ChannelzProtoUtil.java#L228-L239), [ChannelzProtoUtil.java L361](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ChannelzProtoUtil.java#L361), [ChannelzProtoUtil.java L481-L488](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/ChannelzProtoUtil.java#L481-L488), [TransportTracer.java L59-L62](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/TransportTracer.java#L59-L62), [InProcessTransport.java L320-L324](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/inprocess/src/main/java/io/grpc/inprocess/InProcessTransport.java#L320-L324), [InternalSubchannel.java L281](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L281), [ServerImpl.java L435](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ServerImpl.java#L435)
- **Spec:** Channelz (`08-observability/06-channelz.md`), Channel and Subchannel Data, Server Data, `SocketData`, The Channelz Service

### [low] FractionalPercent numerators above 100% can wrap around instead of being capped at 100%

- **Item:** audit (W2-16-005)
- **Summary:** Java reads the `uint32` `FractionalPercent.numerator` into a signed `int` and scales it with 32-bit arithmetic. A route `runtime_fraction` numerator of 2^31 or more is negative and never matches, and the EDS drop-overload and fault-injection per-million conversions can overflow to a small value that passes the cap.
- **Description:** The spec normalizes `FractionalPercent` to a per-million value (`numerator × 10000` for `HUNDRED`, `× 100` for `TEN_THOUSAND`) and caps the result at 1,000,000 (100%). In `RoutingUtils.matchRoute`, `random.nextInt(denominator) < numerator` is always false once the numerator reads as negative, giving 0% instead of 100%. `XdsEndpointResource.getRatePerMillion` and `FaultFilter.getRatePerMillion` multiply in `int` before capping, so for example 429497 with `HUNDRED` wraps to 2704 per million (about 0.27%) instead of 100%. Scaling in `long` from `Integer.toUnsignedLong(numerator)` before capping fixes all three.
- **Evidence:** grpc-java ed3bf6b76b: [MatcherParser.java L163](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/MatcherParser.java#L163), [RoutingUtils.java L156-L157](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RoutingUtils.java#L156-L157), [XdsEndpointResource.java L168-L188](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L168-L188), [FaultFilter.java L387-L404](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FaultFilter.java#L387-L404)
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), Fractional Percentages

### [low] EDS and `envoy.config.core.v3.Address` metadata accept `named_port` as port 0

- **Item:** audit (W2-16-006)
- **Summary:** `XdsEndpointResource.getInetSocketAddress` (EDS `endpoint.address` and `additional_addresses`) and `AddressMetadataParser.parse` (the `envoy.config.core.v3.Address` metadata type) read `socketAddress.getPortValue()` without checking `getPortSpecifierCase() == PORT_VALUE`. An address that sets `named_port`, or sets no port at all, is accepted with port 0 when it should reject the resource.
- **Description:** Common Types requires the port to come from `socket_address.port_value` and does not support `named_port`. Java builds an `InetSocketAddress` on port 0 instead, so the endpoint is unusable instead of being NACKed. (Addresses with no `socket_address` are already rejected because their address is the empty string.)
- **Evidence:** grpc-java ed3bf6b76b: [XdsEndpointResource.java L249-L259](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L249-L259), [XdsEndpointResource.java L313-L341](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L313-L341)
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), Addresses; ClusterLoadAssignment and LbEndpointCollection (`09-xds/04-resources/05-endpoint.md`), LbEndpoint

### [low] Negative `Duration` values in Listener and RouteConfiguration fields are accepted instead of NACKed

- **Item:** audit (W2-16-007, W2-18-004)
- **Summary:** The HCM `common_http_protocol_options.max_stream_duration`, `RouteAction.max_stream_duration.grpc_timeout_header_max` / `max_stream_duration`, and fault-injection `FaultDelay.fixed_delay` are converted with `Durations.toNanos(...)` without a sign check. Negative Durations are accepted when the resource should be rejected.
- **Description:** `Durations.toNanos` accepts any valid protobuf `Duration`, including negative ones. A negative max stream duration is later treated as "no timeout" (`timeoutNanos <= 0` becomes `null`), and a negative fixed delay is treated as no delay. Common Types requires every `Duration` gRPC reads to have non-negative `seconds` and `nanos`, and a violation rejects the resource. Cluster durations (outlier detection) are checked correctly.
- **Evidence:** grpc-java ed3bf6b76b: [XdsListenerResource.java L510-L512](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L510-L512), [XdsRouteConfigureResource.java L409-L417](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L409-L417), [FaultFilter.java L154-L161](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FaultFilter.java#L154-L161), [XdsNameResolver.java L479-L487](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L479-L487)
- **Spec:** Common Types (`09-xds/04-resources/01-common-types.md`), `google.protobuf.Duration`; xDS HTTP Filters (`09-xds/07-http-filters.md`), Fault Injection

### [low] LOGICAL_DNS cluster accepts an empty address and does not bracket IPv6 literals in `host:port`

- **Item:** audit (W2-16-014)
- **Summary:** For `LOGICAL_DNS` clusters, `XdsClusterResource` builds the DNS name with `String.format("%s:%d", address, portValue)`. It does not reject an empty `socket_address.address` and does not put an IPv6 literal in brackets (`::1` becomes `"::1:8080"`, not `"[::1]:8080"`).
- **Description:** The spec requires a non-empty `socket_address.address` (else the resource is rejected) and records the name as `host:port` with IPv6 hosts in brackets. Java accepts an empty host, so the error appears only later at DNS resolution. For an IPv6 literal, the unbracketed string is ambiguous and fails to resolve, and it is also used as the endpoint `hostname` attribute for authority rewriting.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClusterResource.java L344-L366](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L344-L366)
- **Spec:** Cluster (`09-xds/04-resources/04-cluster.md`), Logical DNS Clusters

### [low] xds resolver reports INVALID_ARGUMENT when the target authority is not in the bootstrap

- **Item:** audit (W2-17-014)
- **Summary:** `XdsNameResolver.start` calls `listener.onError(Status.INVALID_ARGUMENT)` when the target URI names an authority that is missing from the bootstrap `authorities` map. It also does this when the expanded Listener resource name is invalid.
- **Description:** The spec requires a missing authority to produce an UNAVAILABLE error (`Invalid target URI -- authority not found for <authority>`), and gRPC must never generate INVALID_ARGUMENT itself. Java's channel passes the resolver error to the LB policy, so RPCs fail with INVALID_ARGUMENT, which an application would read as a problem with its request.
- **Evidence:** grpc-java ed3bf6b76b: [XdsNameResolver.java L226-L249](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L226-L249)
- **Spec:** xDS Client Data Plane (`09-xds/05-client.md`), Listener resource name; Core RPC Semantics (`02-rpc-semantics/README.md`), Status Codes Generated by gRPC

### [low] xDS ring_hash conversion omits the default `maxRingSize`, and LB policy conversion allows 17 recursion levels

- **Item:** audit (W2-17-017)
- **Summary:** `LoadBalancerConfigFactory.buildRingHashConfig` omits `maxRingSize` when the xDS `RingHash` or `Cluster.RingHashLbConfig` leaves `maximum_ring_size` unset, so `ring_hash` uses its JSON default of 4096 instead of the xDS default 8388608. `LoadBalancingPolicyConverter.convertToServiceConfig` fails only when `recursionDepth > 16` instead of `>= 16`.
- **Description:** The spec requires the converted config to always carry `maxRingSize`, 8388608 when unset, so that only the local ring size cap limits it. With the default cap (4096) the result is the same. If an application raises the cap through `RingHashOptions.setRingSizeCap`, Java's effective maximum stays at 4096, and a cluster with `minimum_ring_size` above 4096 and no `maximum_ring_size` is NACKed (`minRingSize > maxRingSize`). The recursion limit allows one more level of `load_balancing_policy` nesting than the spec's 16.
- **Evidence:** grpc-java ed3bf6b76b: [LoadBalancerConfigFactory.java L122-L131](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/LoadBalancerConfigFactory.java#L122-L131), [LoadBalancerConfigFactory.java L284-L286](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/LoadBalancerConfigFactory.java#L284-L286), [LoadBalancerConfigFactory.java L441-L443](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/LoadBalancerConfigFactory.java#L441-L443), [LoadBalancerConfigFactory.java L212-L222](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/LoadBalancerConfigFactory.java#L212-L222), [RingHashLoadBalancerProvider.java L44](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RingHashLoadBalancerProvider.java#L44)
- **Spec:** xDS LB Policies (`09-xds/06-lb-policies.md`), `load_balancing_policy`; Cluster (`09-xds/04-resources/04-cluster.md`), LB Policy

### [low] Fault injection treats a zero or negative delay as an injected delay

- **Item:** audit (W2-18-004, W2-18-006)
- **Summary:** `FaultFilter` creates a `DelayInjectedCall` whenever the delay roll succeeds, even if the delay is 0 or negative. This happens with `fixed_delay` 0, or with an `x-envoy-fault-delay-request` header of `0` or a negative number, which `Integer.parseInt` accepts.
- **Description:** The spec injects a delay only when `delay > 0`, and treats a negative `x-envoy-fault-delay-request` value as invalid (ignored). Java counts such an RPC as an active fault (`activeFaultCounter`), routes it through the scheduler, and then applies the abort regardless of the active-fault limit (as if a delay had been injected), when the RPC should proceed with no delay fault.
- **Evidence:** grpc-java ed3bf6b76b: [FaultFilter.java L264-L271](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FaultFilter.java#L264-L271), [FaultFilter.java L323-L348](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FaultFilter.java#L323-L348), [FaultFilter.java L407-L418](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FaultFilter.java#L407-L418)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), Fault Injection

### [low] LRS locality stats are not keyed by the backend metric propagation config

- **Item:** audit (W2-18-025)
- **Summary:** `LoadStatsManager2.getClusterLocalityStats` keys locality stats only by `(cluster, edsServiceName, locality)`. If an entry already exists, it returns that entry and ignores the `backendMetricPropagation` argument.
- **Description:** The spec makes the backend metric propagation config part of the locality stats key. In Java, once a stats object exists for a locality, callers with a different propagation config share it. For example, after a CDS update changes `lrs_report_endpoint_metrics`, newly created subchannels in that locality keep reporting ORCA metrics under the old config. This lasts until every reference to the old object is released.
- **Evidence:** grpc-java ed3bf6b76b: [LoadStatsManager2.java L58-L59](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/LoadStatsManager2.java#L58-L59), [LoadStatsManager2.java L115-L140](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/LoadStatsManager2.java#L115-L140)
- **Spec:** Load Reporting (`09-xds/10-load-reporting.md`), Stats Model

### [low] RBAC accepts header matchers for `:scheme` or `grpc-` headers written in mixed case

- **Item:** audit (W2-11-019, W2-18-007)
- **Summary:** `RbacFilter.parseHeaderMatcher` rejects only the exact lowercase names `:scheme` and `grpc-*`, so names such as `":Scheme"` or `"GRPC-timeout"` are accepted. At runtime they match the lowercase headers, because header lookup lowercases the name.
- **Description:** The spec requires a NACK for an RBAC header matcher whose name equals `:scheme` or starts with `grpc-` when compared case-insensitively. Java compares case-sensitively, so a mixed-case name passes validation and then matches the reserved header. Go lowercases the name before checking.
- **Evidence:** grpc-java ed3bf6b76b: [RbacFilter.java L324-L331](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/RbacFilter.java#L324-L331), [GrpcAuthorizationEngine.java L350](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/rbac/engine/GrpcAuthorizationEngine.java#L350)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), Configuration Validation

### [low] Service config rejects `maxRequestMessageBytes` / `maxResponseMessageBytes` values of 2^31 or more

- **Item:** audit (W1-B-009)
- **Summary:** `ServiceConfigUtil` reads `maxRequestMessageBytes` and `maxResponseMessageBytes` with `JsonUtil.getNumberAsInteger`. That function fails on values above `Integer.MAX_VALUE` (`2147483647`), so the whole service config is rejected.
- **Description:** The spec defines both fields as uint32 (`0` to `4294967295`). Java parses them as signed 32-bit integers, so a valid value in `[2^31, 2^32 - 1]` makes the service config invalid. C++ accepts it.
- **Evidence:** grpc-java ed3bf6b76b: [ServiceConfigUtil.java L252-L259](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ServiceConfigUtil.java#L252-L259), [JsonUtil.java L129-L153](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/JsonUtil.java#L129-L153)
- **Spec:** Service Config (`04-client-channel/04-service-config.md`), `methodConfig`

### [low] Service config rejects `OK` in `retryableStatusCodes` and `nonFatalStatusCodes`

- **Item:** audit (W1-B-011)
- **Summary:** `ServiceConfigUtil.getRetryableStatusCodesFromRetryPolicy` and `getNonFatalStatusCodesFromHedgingPolicy` reject a service config that lists `"OK"` or `0` in `retryableStatusCodes` or `nonFatalStatusCodes`.
- **Description:** The spec requires each element to be a valid gRPC status code, and `OK` is one. Listing it has no effect, because an `OK` attempt commits. Java instead treats the whole service config as invalid.
- **Evidence:** grpc-java ed3bf6b76b: [ServiceConfigUtil.java L182-L188](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ServiceConfigUtil.java#L182-L188), [ServiceConfigUtil.java L200-L208](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ServiceConfigUtil.java#L200-L208)
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), Fields and Validation

### [low] Received `grpc-timeout` and `grpc-encoding` (and client-side `grpc-accept-encoding`) are passed to the application as metadata

- **Item:** audit (W2-01-012)
- **Summary:** The server delivers `grpc-timeout` and `grpc-encoding` to `ServerCallHandler`/interceptors in the request `Metadata` (whether the request's `grpc-accept-encoding` is visible is implementation-defined; METADATA-3). The client delivers `grpc-encoding` and `grpc-accept-encoding` in the response headers given to `ClientCall.Listener.onHeaders`.
- **Description:** The spec says implementations SHOULD NOT pass reserved keys that they use themselves to the application as metadata. Java removes only `:status`, `grpc-status`, and `grpc-message` from received headers and trailers. The server reads `grpc-timeout` and `grpc-encoding` but leaves them in the `Metadata` given to the application.
- **Evidence:** grpc-java ed3bf6b76b: [Http2ClientStreamTransportState.java L255-L259](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/Http2ClientStreamTransportState.java#L255-L259), [ServerImpl.java L485-L486](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ServerImpl.java#L485-L486), [ServerImpl.java L641](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ServerImpl.java#L641), [Utils.java L192-L198](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/Utils.java#L192-L198)
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), Reserved Keys

### [low] Default authority `client_listener_resource_name_template` does not percent-encode the authority name

- **Item:** audit (W2-15-005)
- **Summary:** When an `authorities` entry has no `client_listener_resource_name_template`, `BootstrapperImpl` builds the default as `"xdstp://" + name + "/envoy.config.listener.v3.Listener/%s"` with the raw authority name.
- **Description:** The spec says the default template contains `<authority_name>` percent-encoded as a URI authority (C++ does this). For an authority name containing characters that must be percent-encoded in a URI authority, Java builds a Listener resource name that differs from what the spec and C++ produce, and the resulting `xdstp:` name is not a valid URI.
- **Evidence:** grpc-java ed3bf6b76b: [BootstrapperImpl.java L226-L233](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/BootstrapperImpl.java#L226-L233)
- **Spec:** Bootstrap (`09-xds/02-bootstrap.md`), Authority Object

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

### [low] Java DNS service config choices validated only up to the selected choice

- **Item:** DNS-2; audit (W2-04-019)
- **Summary:** Java rejects unknown keys and an out-of-range `percentage`, but it checks only the choices up to and including the first one that matches.
- **Description:** `DnsNameResolver` loops over the choices and stops at the first match. `maybeChooseServiceConfig` does the key check (`Verify` "Bad key") and the percentage check per choice, so the choices after the selected one are never checked. A malformed record is therefore accepted or rejected depending on the client's language, hostname, and random draw. The percentage check also converts the value to an `int` before the range check (`percentage.intValue()`), so a non-integer such as `50.9` (used as 50) or `-0.5` (used as 0) is accepted instead of being a service config error.
- **Evidence:** [DnsNameResolver.java#L469-L492](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/DnsNameResolver.java#L469-L492), caller loop around L340-L355, [DnsNameResolver.java L488-L491](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/DnsNameResolver.java#L488-L491)
- **Spec:** Name Resolution: Service Config in DNS › Service Config Choices

### [low] Java weighted_target reports no state when targets is empty

- **Item:** WEIGHTED_TARGET-3
- **Summary:** With an empty `targets` map, `updateOverallBalancingState` never calls `updateBalancingState`, so RPCs can queue forever.
- **Description:** `overallState` starts as null and stays null when there are no targets. The update is skipped, and the parent keeps its previous picker (at first, a queueing picker). C++ and Go report TRANSIENT_FAILURE with an UNAVAILABLE "no children/targets" error.
- **Evidence:** [WeightedTargetLoadBalancer.java#L146-L177](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/WeightedTargetLoadBalancer.java#L146-L177)
- **Spec:** `weighted_target` LB Policy: Picker Implementation

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

### [low] random_subsetting does not forward requestConnection to its child

- **Item:** RANDOM_SUBSETTING-3
- **Summary:** `RandomSubsettingLoadBalancer` does not override `requestConnection()`, so it inherits the no-op from `LoadBalancer` and never forwards ExitIdle to its child.
- **Description:** The spec requires ExitIdle to be forwarded to the child. In Java, `ManagedChannel.getState(true)` calls `lb.requestConnection()`, which does nothing under `random_subsetting`, so an explicit connect request does not leave IDLE. RPCs still connect because Java `pick_first`'s IDLE picker requests a connection itself.
- **Evidence:** util/src/main/java/io/grpc/util/RandomSubsettingLoadBalancer.java (only acceptResolvedAddresses, handleNameResolutionError, shutdown overridden); api/src/main/java/io/grpc/LoadBalancer.java (requestConnection default no-op).
- **Spec:** `random_subsetting` LB Policy: ExitIdle

### [low] Java: outlier detection metrics (A91) not implemented

- **Item:** METRICS-5
- **Summary:** Java's `outlier_detection` policy registers and records neither `grpc.lb.outlier_detection.ejections_enforced` nor `grpc.lb.outlier_detection.ejections_unenforced`.
- **Description:** gRFC A91 (merged) defines two experimental, off-by-default counters recorded when an ejection algorithm detects an outlier. C++ and Go implement them. Java has no reference to them in its sources.
- **Evidence:** grpc-java ed3bf6b7: no `ejections_enforced` anywhere; [OutlierDetectionLoadBalancer.java](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java) has no metric recording.
- **Spec:** Metric Catalog: Outlier Detection LB Policy Metrics; `outlier_detection` LB Policy: Metrics

### [low] Circuit breaker uses the last DEFAULT thresholds entry instead of the first

- **Item:** XDS_CDS-4
- **Summary:** Java loops over all `circuit_breakers.thresholds` entries without stopping, so a later `DEFAULT` entry with `max_requests` overrides the first.
- **Description:** The spec (per A32) says gRPC uses only the first entry whose `priority` is `DEFAULT`. Java does not break after the first DEFAULT entry; the last DEFAULT entry that sets `max_requests` wins. C++ and Go use the first.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L239-L249
- **Spec:** Cluster: Circuit Breakers

### [low] cds LB policy config uses JSON key "is_dynamic" instead of "isDynamic"

- **Item:** XDS_ROUTING-3
- **Summary:** Java generates and parses the cds config field as `is_dynamic` rather than the proto-JSON name `isDynamic`.
- **Description:** `CdsConfig.is_dynamic` (A74, `grpc/service_config/service_config.proto`) maps to JSON `isDynamic` under the standard proto-to-JSON rules used for service config. Java's xDS resolver emits `is_dynamic` and its cds parser reads only `is_dynamic`, so a config using the correct `isDynamic` key is not honored.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsNameResolver.java#L1046-L1047, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/CdsLoadBalancerProvider.java#L88
- **Spec:** `cds` LB Policy: Configuration

### [low] grpc.lb.locality label set only when load reporting is enabled

- **Item:** XDS_LB-7
- **Summary:** Java calls `addOptionalLabel("grpc.lb.locality", ...)` only in the `stats != null` branch, so the label is missing for clusters without an LRS server.
- **Description:** The spec says the picker sets the label for every completed pick, using the empty string when there is no locality. C++ and Go do this whether or not LRS is configured.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterImplLoadBalancer.java#L489-L514
- **Spec:** `xds_cluster_impl` LB Policy: Picker Labels

### [low] Any unparseable fault header disables the header-controlled fault

- **Item:** XDS_FAULT-1; audit (W2-18-006)
- **Summary:** Java `FaultFilter.determineFaultAbortStatus` parses all three abort headers in one try block and returns null (no abort) on any `NumberFormatException`.
- **Description:** The spec (A33: "the invalid headers will be ignored") says only the invalid header is ignored. In Java, an invalid percentage header or an invalid HTTP header stops a valid abort header from applying, and an invalid gRPC header stops a valid HTTP header from applying. `determineFaultDelayNanos` has the same pattern for delays: `x-envoy-fault-delay-request` and `x-envoy-fault-delay-request-percentage` are parsed in one try block that returns null on any `NumberFormatException`, so an invalid percentage header disables a valid delay header instead of being ignored in favor of the configured `delay.percentage`.
- **Evidence:** https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/FaultFilter.java#L351-L377, [FaultFilter.java L326-L340](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/FaultFilter.java#L326-L340)
- **Spec:** xDS HTTP Filters: Header-Controlled Faults

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

### [low] dns resolver returns the TXT service config when the address lookup fails

- **Item:** DNS-1
- **Summary:** When the A/AAAA lookup fails or is empty, Java's DNS resolver puts the `UNAVAILABLE` error only in the addresses and still looks up and returns the TXT service config.
- **Description:** The visible outcome before the first success is still TRANSIENT_FAILURE, but the service config field holds a (possibly valid, possibly invalid) config instead of the error, which can interact with the "keep the last valid service config" logic differently from other implementations. The spec requires both fields to hold an `UNAVAILABLE` error naming the host.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/DnsNameResolver.java` (`doResolve` / `Resolve.run`: address error set on the result while the TXT config is still resolved and attached).
- **Spec:** Name Resolution: `dns`

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

### [low] Java client records inbound message trace events on the call span

- **Item:** TRACING-1
- **Summary:** On the client, Java adds the "Inbound message" event to the call span rather than the attempt span.
- **Description:** The spec says message events are recorded on the client attempt span and on the server span, never on the client call span. Java's client emits the inbound "Inbound message" event (the uncompressed-size half of its split inbound events) on the call span, so the inbound compressed and uncompressed events end up on different spans.
- **Evidence:** grpc-java `opentelemetry/src/main/java/io/grpc/opentelemetry/OpenTelemetryTracingModule.java` (client inbound message handling)
- **Spec:** Tracing: Message Events

### [low] Empty authority client_listener_resource_name_template rejects the bootstrap

- **Item:** XDS_BOOTSTRAP-3
- **Summary:** Java treats `"client_listener_resource_name_template": ""` in an authority as a non-empty value, so it fails the prefix check and the bootstrap is rejected.
- **Description:** An empty template is the same as an unset one and means the default `xdstp://<authority_name>/envoy.config.listener.v3.Listener/%s`. Java uses the default only when the field is absent. With `""`, the `xdstp://<authority_name>/` prefix check fails. Go and C++ treat `""` as unset.
- **Evidence:** xds/src/main/java/io/grpc/xds/client/BootstrapperImpl.java (authority parsing)
- **Spec:** xDS Bootstrap: Authority Object

### [low] outlier_detection max_ejection_percent checked before ejection instead of against the resulting percentage

- **Item:** R18
- **Summary:** max_ejection_percent is compared with the percentage already ejected, so ejection can exceed the limit.
- **Description:** Both algorithms return when `trackerMap.ejectionPercentage() >= config.maxEjectionPercent`, comparing the percentage already ejected, so the last ejection can exceed the limit (the code comment says so and claims this matches Envoy, which is no longer true). The spec (gRFC A50 as updated, matching Envoy's default with `always_eject_one_host` off) ejects an endpoint only if `100 * (ejected + 1) / endpoints <= max_ejection_percent`, so the limit is never exceeded and 0 disables ejection. Impact: in small endpoint sets gRPC ejects endpoints that Envoy would not; e.g. with the default 10% and 3 endpoints, gRPC ejects one (33%) while Envoy ejects none.
- **Evidence:** grpc-java `util/src/main/java/io/grpc/util/OutlierDetectionLoadBalancer.java` (~lines 828-835 and 904-910).
- **Spec:** 04-client-channel/lb-policies/outlier_detection.md, "Success-Rate Algorithm" / "Failure-Percentage Algorithm"

### [low] Headers over the Netty hard header-list limit fail with INTERNAL or a bare HTTP 431 instead of RESOURCE_EXHAUSTED

- **Item:** R2, R50
- **Summary:** Over the Netty hard header-list limit, the Java server sends HTTP 431 with no `grpc-status` plus `RST_STREAM(PROTOCOL_ERROR)`, and a Java client that receives oversized response headers reports `INTERNAL`.
- **Description:** Over the soft limit, Java behaves as specified (`RESOURCE_EXHAUSTED` both ways). Over the hard limit, Netty's header decoder fails the stream. The server then sends HTTP 431 without `grpc-status` and resets the stream, and the client maps the `Http2Exception` to `INTERNAL`. A Java client that receives the 431 also reports `INTERNAL` (see the separate 431-mapping bug). The hard limit defaults to the soft limit, so this is the path normally taken when the limit is hit. The spec says the server SHOULD send `RESOURCE_EXHAUSTED` (resetting the stream only if it cannot) and the client SHOULD report `RESOURCE_EXHAUSTED`.
- **Evidence:** grpc-java ed3bf6b76b: [GrpcHttp2HeadersUtils.java L60-L82](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/GrpcHttp2HeadersUtils.java#L60-L82), [NettyServerHandler.java L637-L656](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/NettyServerHandler.java#L637-L656), [NettyClientHandler.java L615-L627](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/NettyClientHandler.java#L615-L627), [Utils.java L358-L360](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/Utils.java#L358-L360), [NettyServerBuilder.java L115-L116](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/NettyServerBuilder.java#L115-L116)
- **Spec:** gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), Header list size; Server (`05-server/01-server.md`), Request Validation; Core RPC Semantics (`02-rpc-semantics/README.md`), Size Limits

### [low] Default per-RPC retry buffer limit is not 256 KiB

- **Item:** R44
- **Summary:** Java's default per-RPC retry buffer limit is 1 MiB, but the spec recommends (SHOULD) 256 KiB.
- **Description:** `ManagedChannelImplBuilder` defaults `perRpcBufferLimit` to 1 MiB (and also has a 16 MiB per-channel limit, which the spec allows). The spec recommends a 256 KiB per-RPC default, so retry behavior for large requests is consistent across languages. The deviation is allowed, but a Java client can still retry requests that other languages would commit without retrying.
- **Evidence:** grpc-java `core/src/main/java/io/grpc/internal/ManagedChannelImplBuilder.java` (`perRpcBufferLimit`, `retryBufferSize`).
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), "Buffer Limits".

### [low] Async stub does not fail unary calls that receive zero responses

- **Item:** R98
- **Summary:** The Java async stub reports a unary call that ends OK with no response message as a successful completion instead of failing it with `INTERNAL`.
- **Description:** Java's blocking and future stubs fail a unary call that ends OK with no response message with `INTERNAL` ("No value received for unary call"), but the async (StreamObserver) stub just calls `onCompleted()` without `onNext()`. The spec requires the client to fail the call with `INTERNAL`. Applications using the async stub may treat a missing response as success. (Also, more than one response surfaces as `CANCELLED` with an `INTERNAL` cause rather than as `INTERNAL`.)
- **Evidence:** `stub/src/main/java/io/grpc/stub/ClientCalls.java` (`UnaryStreamToFuture` ~L620-633 handles both cases; the StreamObserver adapter for `asyncUnaryCall` does not check cardinality).
- **Spec:** Core RPC Semantics (`02-rpc-semantics/README.md`), "Unary Calls".

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

- **Item:** R133, RLS-8
- **Summary:** Smaller differences in target choice, child config errors, state reporting, and control-channel reconnect handling.
- **Description:**
  - When all targets are in TRANSIENT_FAILURE, the first target is used (spec: the last).
  - A child config parse error passes a null config to the child instead of putting the child in TRANSIENT_FAILURE.
  - With no children, the policy reports CONNECTING (spec: IDLE).
  - Children destroyed by refcount stay in the aggregate-state map.
  - Backoff policies (`BackoffCacheEntry.backoffPolicy`) are not reset when the control channel returns to READY (only the timer is cancelled, so the next failure continues the backoff sequence), and Java RLS has no `ResetBackoff` hook.
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

### [low] HTTP 431 without `grpc-status` is mapped to INTERNAL instead of UNKNOWN

- **Item:** audit (W2-03-010)
- **Summary:** When a response has no `grpc-status` and HTTP `:status` 431 (Request Header Fields Too Large), Java reports `INTERNAL` instead of `UNKNOWN`.
- **Description:** `GrpcUtil.httpStatusToGrpcCode` groups `431` with `400` and returns `INTERNAL`. In the spec's HTTP-to-gRPC mapping table, `400` maps to `INTERNAL` and every code not listed (including `431`) maps to `UNKNOWN`. This is what clients see when a server (including a Java server over its hard header limit) rejects request headers with a bare 431.
- **Evidence:** grpc-java ed3bf6b76b: [GrpcUtil.java L305-L329](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/GrpcUtil.java#L305-L329)
- **Spec:** gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), Deriving the status

### [low] Netty client maps `RST_STREAM(HTTP_1_1_REQUIRED)` to `UNKNOWN` instead of `INTERNAL`

- **Item:** audit (W2-03-011); related: R12
- **Summary:** `GrpcUtil.Http2Error` maps `HTTP_1_1_REQUIRED` (0xd) to `Status.UNKNOWN`, so a Netty client call reset with that code fails with `UNKNOWN` instead of `INTERNAL`.
- **Description:** `NettyClientHandler.onRstStreamRead` maps the error code through `GrpcUtil.Http2Error.statusForCode`. Every other HTTP/2 error code, including unrecognized ones, maps as the spec's table says, but the `HTTP_1_1_REQUIRED` entry is explicitly `Status.UNKNOWN`. The spec maps `HTTP_1_1_REQUIRED` to `INTERNAL`.
- **Evidence:** grpc-java ed3bf6b76b: [GrpcUtil.java L354](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/GrpcUtil.java#L354), [GrpcUtil.java L422-L432](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/GrpcUtil.java#L422-L432), [NettyClientHandler.java L495-L499](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/NettyClientHandler.java#L495-L499)
- **Spec:** gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), RST_STREAM

### [low] OkHttp client closes the whole connection on `RST_STREAM` or `GOAWAY` with an unrecognized error code

- **Item:** audit (W2-03-011); related: R12
- **Summary:** OkHttp's frame reader treats an `RST_STREAM` or `GOAWAY` carrying an error code it doesn't know (`SETTINGS_TIMEOUT` 0x4, `HTTP_1_1_REQUIRED` 0xd, or any unassigned code) as a connection error. It closes the connection and fails every call on it with `INTERNAL`.
- **Description:** `Http2.Reader.readRstStream` and `readGoAway` throw an `IOException` when `ErrorCode.fromHttp2` returns null. `ClientFrameHandler.run` catches it and calls `startGoAway(0, PROTOCOL_ERROR, INTERNAL "error in frame handler")`, which ends all streams on the connection. The spec maps these codes to `INTERNAL` for the stream that was reset only. RFC 9113 §7 says unknown error codes MUST NOT trigger any special behavior. (`OkHttpClientTransport.toGrpcStatus` has an `UNKNOWN` fallback, but no code can reach it.)
- **Evidence:** grpc-java ed3bf6b76b: [Http2.java L256-L265](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/third_party/okhttp/main/java/io/grpc/okhttp/internal/framed/Http2.java#L256-L265), [Http2.java L349-L354](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/third_party/okhttp/main/java/io/grpc/okhttp/internal/framed/Http2.java#L349-L354), [ErrorCode.java L82-L87](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/third_party/okhttp/main/java/io/grpc/okhttp/internal/framed/ErrorCode.java#L82-L87), [OkHttpClientTransport.java L1347-L1352](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/src/main/java/io/grpc/okhttp/OkHttpClientTransport.java#L1347-L1352)
- **Spec:** gRPC over HTTP/2 (`03-wire-protocol/01-http2.md`), RST_STREAM

### [low] Petiole endpoint identity counts duplicate addresses within an endpoint

- **Item:** audit (W2-05-005)
- **Summary:** `MultiChildLoadBalancer.Endpoint` treats an endpoint with addresses `[A, A]` as different from one with `[A]`, so the child and its connections are recreated when duplication within an endpoint changes between updates.
- **Description:** The spec identifies an endpoint by the unordered set of its addresses. `Endpoint` keeps the address list as-is (it switches to a `HashSet` only at 10 or more addresses), `equals` requires equal sizes, and `hashCode` sums the hash codes of every address, duplicates included. Endpoints whose address lists contain the same set of addresses with different duplication are therefore unequal, and `round_robin`, `least_request`, `weighted_round_robin` and other `MultiChildLoadBalancer` subclasses replace the child instead of keeping it.
- **Evidence:** grpc-java ed3bf6b76b: [MultiChildLoadBalancer.java L367-L412](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/util/src/main/java/io/grpc/util/MultiChildLoadBalancer.java#L367-L412)
- **Spec:** Load Balancing (`04-client-channel/06-load-balancing.md`), Endpoint Identity

### [low] Subchannel ResetBackoff during a connection attempt does not reset the backoff

- **Item:** audit (W2-05-013)
- **Summary:** `InternalSubchannel.resetConnectBackoff()` does nothing unless the subchannel is in TRANSIENT_FAILURE. If it is called while an attempt is in progress (CONNECTING) and that attempt fails, the next delay continues the old backoff sequence instead of starting from the initial backoff.
- **Description:** The spec says `ResetBackoff()` resets the subchannel's backoff state, and in addition ends a TRANSIENT_FAILURE backoff right away. In Java, `resetConnectBackoff()` returns early when the state isn't TRANSIENT_FAILURE. The backoff policy is cleared only by `cancelReconnectTask()` (when a reconnect timer is pending) or on READY. So `ManagedChannel.resetConnectBackoff()` called during a slow attempt has no effect, and if the attempt fails, `reconnectPolicy.nextBackoffNanos()` keeps growing.
- **Evidence:** grpc-java ed3bf6b76b: [InternalSubchannel.java L336-L349](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L336-L349), [InternalSubchannel.java L523-L531](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L523-L531), [InternalSubchannel.java L315-L319](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/InternalSubchannel.java#L315-L319)
- **Spec:** Subchannels and Connections (`04-client-channel/07-subchannels.md`), Connection Backoff

### [low] pick_first weighted shuffle does not treat an endpoint weight of 0 or less as 1

- **Item:** audit (W2-07-001)
- **Summary:** With `shuffleAddressList`, `PickFirstLeafLoadBalancer` uses an endpoint weight of 0 or less as-is. A weight of 0 always sorts the endpoint last, and a negative weight always sorts it first.
- **Description:** `eagToWeight` defaults a missing `ATTR_WEIGHT` to 1 but doesn't treat 0 or negative values as 1 as the spec requires. The shuffle key is `Math.pow(u, 1.0 / weight)`: with weight 0 the exponent is +∞ and the key is 0, and with a negative weight the key is above 1. Either way the endpoint is pinned to one end of the order instead of being shuffled with weight 1. The weight attribute can come from a custom resolver (xDS maps EDS weight 0 to 1 before this point).
- **Evidence:** grpc-java ed3bf6b76b: [PickFirstLeafLoadBalancer.java L236-L257](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/PickFirstLeafLoadBalancer.java#L236-L257)
- **Spec:** `pick_first` LB Policy (`04-client-channel/lb-policies/pick_first.md`), Validation; Address List Processing

### [low] least_request and random_subsetting config parsing deviates from the uint32 ranges and accepts JSON strings

- **Item:** audit (W2-07-017)
- **Summary:** `least_request` rejects `choiceCount` values in `[2^31, 2^32 - 1]`. `random_subsetting` accepts `subsetSize` values above `4294967295`. Both accept a JSON string such as `"2"` in place of a JSON integer.
- **Description:** The spec says each config is invalid unless the field is a JSON integer in `[2, 4294967295]` (`choiceCount`) or `[1, 4294967295]` (`subsetSize`). `LeastRequestLoadBalancerProvider` reads `choiceCount` with `JsonUtil.getNumberAsInteger`, which fails for values above `Integer.MAX_VALUE` (these should be accepted and capped at 10). `RandomSubsettingLoadBalancerProvider` reads `subsetSize` with `JsonUtil.getNumberAsLong` and checks only `> 0`, so values above the uint32 maximum are accepted (and saturated to `Integer.MAX_VALUE`). Both `JsonUtil` helpers also parse JSON strings with `Integer.parseInt` / `Long.parseLong`, so `"choiceCount": "3"` is accepted.
- **Evidence:** grpc-java ed3bf6b76b: [LeastRequestLoadBalancerProvider.java L63-L73](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/LeastRequestLoadBalancerProvider.java#L63-L73), [RandomSubsettingLoadBalancerProvider.java L63-L69](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/util/src/main/java/io/grpc/util/RandomSubsettingLoadBalancerProvider.java#L63-L69), [RandomSubsettingLoadBalancer.java L141-L146](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/util/src/main/java/io/grpc/util/RandomSubsettingLoadBalancer.java#L141-L146), [JsonUtil.java L129-L184](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/JsonUtil.java#L129-L184)
- **Spec:** `least_request` LB Policy (`04-client-channel/lb-policies/least_request.md`), Validation; `random_subsetting` LB Policy (`04-client-channel/lb-policies/random_subsetting.md`), Validation

### [low] priority keeps a child's original `ignoreReresolutionRequests` after config updates

- **Item:** audit (W2-08-014)
- **Summary:** `PriorityLoadBalancer` fixes a child's `ignoreReresolutionRequests` setting when the child is created. Later updates that change it for the same child name have no effect.
- **Description:** The spec updates existing children in place with their new config, and re-resolution requests are ignored according to the child's current `ignoreReresolutionRequests`. In Java the flag is passed to the `ChildLbState` constructor and stored in a final field of its `ChildHelper`. `updateResolvedAddresses` sends the child only its new policy config, and children brought back from the child-policy cache keep the flag they were created with.
- **Evidence:** grpc-java ed3bf6b76b: [PriorityLoadBalancer.java L158-L170](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/PriorityLoadBalancer.java#L158-L170), [PriorityLoadBalancer.java L231-L233](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/PriorityLoadBalancer.java#L231-L233), [PriorityLoadBalancer.java L302-L325](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/PriorityLoadBalancer.java#L302-L325)
- **Spec:** `priority` LB Policy (`04-client-channel/lb-policies/priority.md`), Updates from the Parent; Calls From Children

### [low] retryThrottling `tokenRatio` loses a millitoken for some 3-decimal values

- **Item:** audit (W2-09-009)
- **Summary:** Java narrows `tokenRatio` to `float` before scaling it by 1000 and truncating, so some values with 3 decimal places come out 0.001 too low (for example `0.251` becomes 0.250 and `1.004` becomes 1.003).
- **Description:** The spec uses only the first 3 decimal places of `tokenRatio`. `ServiceConfigUtil.getThrottlePolicy` reads it as a double and calls `floatValue()`, and the `Throttle` constructor computes `(int) (tokenRatio * 1000)` in float arithmetic. When the nearest float lies just below the decimal value, the product truncates to one less millitoken. Using the double value (or rounding to 3 places) would avoid this.
- **Evidence:** grpc-java ed3bf6b76b: [ServiceConfigUtil.java L116-L120](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ServiceConfigUtil.java#L116-L120), [RetriableStream.java L1503-L1509](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/RetriableStream.java#L1503-L1509)
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), Retry Throttling: Fields and Validation

### [low] Transparent retries of attempts that never reached the network stop after 1,000

- **Item:** audit (W2-09-009)
- **Summary:** After 1,000 transparent retries of attempts that failed before anything reached the network (`MISCARRIED`), Java fails the RPC with `INTERNAL` ("Too many transparent retries"). The spec allows any number until the deadline.
- **Description:** `RetriableStream.Sublistener.closed` counts `MISCARRIED` attempts in `localOnlyTransparentRetries` and commits with `INTERNAL` once the count exceeds 1,000. It's a guard against busy loops, but the spec says such attempts are transparently retried any number of times, bounded only by the RPC's deadline.
- **Evidence:** grpc-java ed3bf6b76b: [RetriableStream.java L951-L960](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/RetriableStream.java#L951-L960)
- **Spec:** Retries and Hedging (`04-client-channel/12-retries.md`), Transparent Retries

### [low] Netty TLS with Conscrypt as the JDK provider caps the protocol at TLS 1.2

- **Item:** audit (W2-10-005)
- **Summary:** `GrpcSslContexts.configure` calls `builder.protocols("TLSv1.2")` when the JDK TLS provider is Conscrypt, so TLS 1.3 is never negotiated on those connections.
- **Description:** The spec makes TLS 1.3 the default maximum version. Java restricts Conscrypt-backed Netty contexts to TLS 1.2 only, as a workaround for a Conscrypt TrustManager issue (grpc-java#7765), and the application has to override the protocols to get TLS 1.3.
- **Evidence:** grpc-java ed3bf6b76b: [GrpcSslContexts.java L221-L225](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/GrpcSslContexts.java#L221-L225)
- **Spec:** TLS (`06-security/02-tls.md`), Protocol Requirements

### [low] File-watcher `refresh_interval` under 1 second is rejected, and the advanced TLS file refresh raises intervals under 1 minute

- **Item:** audit (W2-10-012)
- **Summary:** `FileWatcherCertificateProviderProvider` truncates `refresh_interval` to whole seconds and fails config parsing when the result is 0 (for example `"0.5s"`), instead of raising it to 1 second. `AdvancedTlsX509TrustManager.updateTrustCredentials` and `AdvancedTlsX509KeyManager.updateIdentityCredentials` raise any period below 1 minute to 1 minute.
- **Description:** The spec says refresh intervals under 1 second are raised to 1 second, and that the interval is otherwise the time between reads. Java's xDS `file_watcher` plugin turns a sub-second interval into a configuration error, and the programmatic file-refreshing key and trust managers ignore any period between 1 second and 1 minute.
- **Evidence:** grpc-java ed3bf6b76b: [FileWatcherCertificateProviderProvider.java L125-L127](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/internal/security/certprovider/FileWatcherCertificateProviderProvider.java#L125-L127), [AdvancedTlsX509TrustManager.java L259-L265](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/util/src/main/java/io/grpc/util/AdvancedTlsX509TrustManager.java#L259-L265), [AdvancedTlsX509KeyManager.java L176-L182](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/util/src/main/java/io/grpc/util/AdvancedTlsX509KeyManager.java#L176-L182)
- **Spec:** TLS (`06-security/02-tls.md`), File-Watcher Provider

### [low] Recording 0 for a per-call ORCA scalar metric does not override the per-server value

- **Item:** audit (W2-12-016)
- **Summary:** `CallMetricRecorder` stores its scalar metrics as `0` when unset, and `OrcaMetricReportingServerInterceptor.mergeMetrics` copies a per-call scalar over the per-server value only if it is non-zero. An explicitly recorded `0` (for example 0% CPU) therefore leaves the per-server value in the report.
- **Description:** The spec says a per-call value takes precedence over the per-server value, including a recorded `0`. Java cannot tell an explicitly recorded `0` from an unset metric. Separately, the five scalar fields of `CallMetricRecorder` are plain `double` fields, not `volatile`, although the class is `@ThreadSafe` and the spec allows recording from any thread, so a value recorded on another thread is not guaranteed to be visible when the report is built.
- **Evidence:** grpc-java ed3bf6b76b: [CallMetricRecorder.java L46-L50](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/services/CallMetricRecorder.java#L46-L50), [OrcaMetricReportingServerInterceptor.java L132-L164](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/orca/OrcaMetricReportingServerInterceptor.java#L132-L164)
- **Spec:** Backend Metrics (ORCA) (`07-services/03-orca.md`), Data Model, Per-Call Recorder, Merging with the Per-Server Recorder

### [low] XdsClient metrics include the `type.googleapis.com/` prefix in `grpc.xds.resource_type`

- **Item:** audit (W2-13-019)
- **Summary:** Java uses the full type URL (for example `type.googleapis.com/envoy.config.listener.v3.Listener`) as the `grpc.xds.resource_type` label of `grpc.xds_client.resource_updates_valid`, `grpc.xds_client.resource_updates_invalid`, and `grpc.xds_client.resources`.
- **Description:** gRFC A78 and the spec define the label as the resource type name without the prefix (for example `envoy.config.listener.v3.Listener`), which is what C++ emits. Dashboards and queries written for the specified values do not match Java's metrics.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClientImpl.java L588-L590](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/XdsClientImpl.java#L588-L590), [XdsClientMetricReporterImpl.java L187](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsClientMetricReporterImpl.java#L187), [XdsListenerResource.java L55-L56](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsListenerResource.java#L55-L56)
- **Spec:** Metric Catalog (`08-observability/04-metrics.md`), Common Attributes, XdsClient Metrics

### [low] Client tracing adds "Delayed name resolution complete" to the call span once per attempt

- **Item:** audit (W2-13-020)
- **Summary:** `CallAttemptsTracerFactory.newClientStreamTracer` adds the `Delayed name resolution complete` event to the call span every time an attempt is created for a call that waited for name resolution, so retried and hedged calls get duplicate events.
- **Description:** gRFC A72 and the spec define this as a single event on the `Sent.<service>.<method>` span, added when the call's wait for name resolution ends. `ManagedChannelImpl` puts `NAME_RESOLUTION_DELAYED` in the call options when the delayed call proceeds, and every attempt of that call sees it, so the event is repeated for each attempt.
- **Evidence:** grpc-java ed3bf6b76b: [OpenTelemetryTracingModule.java L170-L172](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/opentelemetry/src/main/java/io/grpc/opentelemetry/OpenTelemetryTracingModule.java#L170-L172), [ManagedChannelImpl.java L1056-L1058](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1056-L1058)
- **Spec:** Instrumentation Architecture (`08-observability/02-instrumentation.md`), Client Call Tracer Event Points; Tracing (`08-observability/05-tracing.md`), Client Call Span

### [low] Non-per-call histograms ignore the instrument's recommended bucket boundaries

- **Item:** audit (W2-13-021)
- **Summary:** `OpenTelemetryMetricSink` creates OpenTelemetry histograms for registered (non-per-call) histogram instruments without passing `instrument.getBucketBoundaries()` as explicit bucket boundary advice.
- **Description:** The spec says that where the OpenTelemetry API supports instrument advice, the plugin SHOULD supply the recommended boundaries as advice. Java does this for its per-call histograms, but the sink ignores the boundaries stored in `DoubleHistogramMetricInstrument` / `LongHistogramMetricInstrument`, so for example the ext_proc duration histograms, which register `LATENCY_BUCKETS`, get the SDK default buckets.
- **Evidence:** grpc-java ed3bf6b76b: [OpenTelemetryMetricSink.java L260-L270](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/opentelemetry/src/main/java/io/grpc/opentelemetry/OpenTelemetryMetricSink.java#L260-L270), [ExternalProcessorClientInterceptor.java L128-L136](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/ExternalProcessorClientInterceptor.java#L128-L136)
- **Spec:** Metrics Framework and OpenTelemetry Plugin (`08-observability/03-metrics-framework.md`), Instrument Descriptor, Default Histogram Buckets

### [low] Channelz removes a terminated subchannel while the parent's trace events still reference it

- **Item:** audit (W2-14-009)
- **Summary:** When a subchannel terminates, `ManagedChannelImpl` immediately removes it from `InternalChannelz`, even though the parent channel's retained "Child Subchannel started" trace event still carries its `subchannel_ref`.
- **Description:** gRFC A3 and the spec require an entity referenced by a `child_ref` in a retained trace event to stay queryable until no retained event refers to it. In Java, with channel trace enabled (`maxTraceEvents > 0`), a client that follows the `subchannel_ref` in the parent's trace gets `NOT_FOUND` from `GetSubchannel` once the subchannel has terminated.
- **Evidence:** grpc-java ed3bf6b76b: [ManagedChannelImpl.java L1866-L1869](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1866-L1869), [ManagedChannelImpl.java L1907-L1912](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1907-L1912), [InternalChannelz.java L120-L122](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/api/src/main/java/io/grpc/InternalChannelz.java#L120-L122)
- **Spec:** Channelz (`08-observability/06-channelz.md`), Memory Bound

### [low] Channel trace omits address-count changes between zero and non-zero after the first resolution

- **Item:** audit (W2-14-013)
- **Summary:** `NameResolverListener.onResult2` adds a channel trace event ("Address resolved") only for the first successful result after startup or an error. Later results are logged at `DEBUG`, which is not recorded in the channel trace.
- **Description:** gRFC A3 and the spec require a trace event when name resolution changes the number of addresses from zero to non-zero or from non-zero to zero. In Java, once a result has succeeded, a later result whose address list becomes empty, or becomes non-empty again, produces no trace event.
- **Evidence:** grpc-java ed3bf6b76b: [ManagedChannelImpl.java L1676-L1686](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L1676-L1686), [ChannelLoggerImpl.java L71-L73](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/core/src/main/java/io/grpc/internal/ChannelLoggerImpl.java#L71-L73)
- **Spec:** Channelz (`08-observability/06-channelz.md`), Required Events

### [low] Client binary log records the channel authority instead of the call's authority override

- **Item:** audit (W2-14-023)
- **Summary:** `BinlogHelper.getClientInterceptor` logs `next.authority()` as `ClientHeader.authority` and ignores `callOptions.getAuthority()`, so calls that override `:authority` are logged with the channel's default authority.
- **Description:** The spec defines `ClientHeader.authority` as the `:authority` of the call. The server side logs `call.getAuthority()`, but the client side always logs the channel's default authority, even when the call sets a per-call authority.
- **Evidence:** grpc-java ed3bf6b76b: [BinlogHelper.java L403](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/BinlogHelper.java#L403), [BinlogHelper.java L509](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/services/src/main/java/io/grpc/protobuf/services/BinlogHelper.java#L509)
- **Spec:** Binary Logging (`08-observability/07-binary-logging.md`), Payload Messages

### [low] `typed_per_filter_config` accepts an empty key and an `is_optional` `FilterConfig` with no `config`

- **Item:** audit (W2-18-002)
- **Summary:** `XdsRouteConfigureResource.parseOverrideFilterConfigs` does not reject an empty `typed_per_filter_config` map key. When a `FilterConfig` wrapper has `is_optional: true` and no `config`, the empty type URL is treated as an unsupported filter type and the entry is skipped instead of NACKed.
- **Description:** The spec requires a NACK for an empty map key, and for an empty `type_url`, which includes the unwrapped `FilterConfig.config` when it is absent, whatever `is_optional` is set to. `is_optional` only covers override types that are not registered.
- **Evidence:** grpc-java ed3bf6b76b: [XdsRouteConfigureResource.java L219-L258](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L219-L258)
- **Spec:** xDS HTTP Filters (`09-xds/07-http-filters.md`), Extracting the Filter Type, Override Configuration (`typed_per_filter_config`)

### [low] LRS client restarts the report timer on every response and never skips all-zero reports

- **Item:** audit (W2-18-026)
- **Summary:** `LoadReportClient.handleRpcResponse` cancels and restarts the report timer on every `LoadStatsResponse`, even when `send_all_clusters`, `clusters`, and `load_reporting_interval` are unchanged. `sendLoadReport` sends a `LoadStatsRequest` every interval, even when it and the previous report are all zero.
- **Description:** The spec says a response identical to the current parameters is ignored and the timer is restarted only when the interval changes. It also says the client SHOULD skip a report whose counters are all zero when the previous one was also all zero. With Java, a server that resends the same response more often than the interval keeps postponing the next report, and idle clients send empty reports every interval.
- **Evidence:** grpc-java ed3bf6b76b: [LoadReportClient.java L229-L277](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/client/LoadReportClient.java#L229-L277)
- **Spec:** Load Reporting (`09-xds/10-load-reporting.md`), Responses, Load reports

### [low] Java pick_first stays in TRANSIENT_FAILURE while the selected subchannel's health watch is CONNECTING

- **Item:** audit (PICK_FIRST-20)
- **Summary:** Under a petiole policy, after `pick_first` has reported TRANSIENT_FAILURE, a newly READY subchannel whose health watch reports CONNECTING leaves `pick_first` in TRANSIENT_FAILURE with the old failing picker. It should report CONNECTING with a queueing picker.
- **Description:** `PickFirstLeafLoadBalancer.updateHealthCheckedState` reports READY or TRANSIENT_FAILURE from the health state, but reports any other health state only `if (concludedState != TRANSIENT_FAILURE)`. So once `pick_first` is in TRANSIENT_FAILURE (from connection failures or an unhealthy `Watch` response), a selected READY subchannel whose `Health/Watch` hasn't responded yet (or is retrying) keeps the old error picker, and non-`wait_for_ready` RPCs fail instead of queueing until `SERVING` arrives. The spec ends sticky TRANSIENT_FAILURE when a subchannel becomes READY, and then reports the health state, with Health CONNECTING reported as CONNECTING. gRFC A61 says the same ("the connectivity state reported by that watch is the state that pick_first will report to its parent"), and C++ and Go do this. (Possible argument for the Java behavior: it keeps the petiole in TRANSIENT_FAILURE while backends flap during an all-unhealthy outage. That would need a spec change.)
- **Evidence:** [PickFirstLeafLoadBalancer.java#L438-L454](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/PickFirstLeafLoadBalancer.java#L438-L454), [PickFirstLeafLoadBalancer.java#L625-L645](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/PickFirstLeafLoadBalancer.java#L625-L645)
- **Spec:** `pick_first` LB Policy: Health Reporting Under Petiole Policies; Connectivity State

### [low] Java weighted_round_robin accepts a negative `errorUtilizationPenalty`

- **Item:** audit (WRR-22)
- **Summary:** A negative `errorUtilizationPenalty` is accepted instead of making the config invalid.
- **Description:** `WeightedRoundRobinLoadBalancerProvider.parseLoadBalancingPolicyConfigInternal` passes `errorUtilizationPenalty` straight to the config builder, and neither the provider nor `WeightedRoundRobinLoadBalancerConfig.Builder.build()` checks the sign. The spec (`weighted_round_robin` 2.2 Validation) and gRFC A58 ("Configuration is rejected if this value is negative") require rejecting it; C++ and Go do.
- **Evidence:** [WeightedRoundRobinLoadBalancerProvider.java#L75-L114](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancerProvider.java#L75-L114), [WeightedRoundRobinLoadBalancer.java#L887-L903](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancer.java#L887-L903)
- **Spec:** `weighted_round_robin` LB Policy: Validation

### [low] Java xDS server does not log a warning for routes whose action is not `non_forwarding_action`

- **Item:** XDS_SERVER-20 (converted review item)
- **Summary:** Java logs RDS unavailability and recovery at WARNING, but does not log when a received RouteConfiguration contains a route whose action is not `non_forwarding_action`; such routes only fail matching RPCs with `UNAVAILABLE`.
- **Description:** xDS-Enabled Servers §9 (from gRFC A36 "configuration error logging") says the server SHOULD log a warning each time it receives an update containing a route whose action is not `non_forwarding_action`, and SHOULD log a single message once no such route remains.
- **Evidence:** grpc-java ed3bf6b76b: [XdsServerWrapper.java L824-L845](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsServerWrapper.java#L824-L845) (RDS logging present), [L940-L950](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/xds/src/main/java/io/grpc/xds/XdsServerWrapper.java#L940-L950) (per-RPC failure only).
- **Spec:** xDS-Enabled Servers (`09-xds/08-server.md`), Configuration Error Logging

### [low] Java rejects aggregate clusters whose `cluster_type.name` is not `envoy.clusters.aggregate`

- **Item:** XDS_CDS-20
- **Summary:** `XdsClusterResource.parseAggregateCluster` NACKs a Cluster unless `cluster_type.name` equals `"envoy.clusters.aggregate"`, even when `cluster_type.typed_config` is a valid `ClusterConfig`.
- **Description:** The spec (following gRFC A37's validation rules, which check only `cluster_type.typed_config` and its `type_url`) says `cluster_type.name` is ignored and the aggregate cluster is identified by the `typed_config` type. Java returns "unsupported custom cluster type" for any other name before looking at `typed_config`. C++ ignores the name.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClusterResource.java L193-L206](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L193-L206)
- **Spec:** Cluster (`09-xds/04-resources/04-cluster.md`), Aggregate Clusters

### [low] `pick_first` weighted shuffle doesn't treat an endpoint weight of 0 (or less) as 1

- **Item:** audit (lbpol follow-up)
- **Summary:** With weighted shuffling on (the default), an endpoint whose weight attribute is 0 gets the sort key `u^(1/0) = 0` and is always placed last; a negative weight gets a key above 1 and is always placed first.
- **Description:** The spec says an endpoint weight of 0 (or less, where signed) MUST be treated as 1. C++ (`weight_arg <= 0 ? 1.0 : weight_arg`) and Go (`weightAttribute` returns 1 for 0) do this. Java's `eagToWeight` uses the attribute value as-is (defaulting only when absent), so a zero-weight endpoint is never tried first and a negative-weight endpoint always is. xDS never produces these values (`cds` clamps the normalized weight to at least 1), so this only affects custom resolvers that set `ATTR_WEIGHT`.
- **Evidence:** [PickFirstLeafLoadBalancer.java L251-L257](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/PickFirstLeafLoadBalancer.java#L251-L257); compare C++ [pick_first.cc L555-L558](https://github.com/grpc/grpc/blob/515aaa1743ec9a318e7e22d11a5bfaa835d5fa81/src/core/load_balancing/pick_first/pick_first.cc#L555-L558) and Go [pickfirst.go L915-L921](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/balancer/pickfirst/pickfirst.go#L915-L921).
- **Spec:** `pick_first` LB Policy: Validation

### [low] EDS parser doesn't reject a priority whose locality weights sum above the uint32 maximum, and misreads weights of 2^31 or more

- **Item:** audit (bugs-java follow-up)
- **Summary:** Java never checks the per-priority sum of locality weights, and because protobuf `UInt32Value.getValue()` returns a signed `int`, a locality weight of 2^31 or more reads as negative and the locality is silently dropped as if its weight were 0.
- **Description:** gRFC A27 and the spec require the resource to be rejected when the sum of locality weights within a priority exceeds 4,294,967,295. C++ and Go check this. Java's `XdsEndpointResource` has no such check. Separately, `parseLocalityLbEndpoints` filters localities with `getLoadBalancingWeight().getValue() < 1`; a valid uint32 weight ≥ 2^31 is negative as a Java `int`, so that locality is dropped instead of used (endpoint weights at L240 have the same signedness problem). Both only matter for very large weights.
- **Evidence:** [XdsEndpointResource.java L195-L200](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L195-L200), [L240-L245](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L240-L245) (no sum check anywhere in the file); compare Go [unmarshal_eds.go L178-L193](https://github.com/grpc/grpc-go/blob/cbf30c41309983ce66c6a81abe569a75fd2b9dcd/internal/xds/xdsclient/xdsresource/unmarshal_eds.go#L178-L193) and C++ `xds_endpoint_parser.cc` (sum of locality weights per priority).
- **Spec:** ClusterLoadAssignment: LocalityLbEndpoints (Weight sum)

### [low] ORCA recorders accept non-finite metric values

- **Item:** ORCA_SVC-20
- **Summary:** The recorders accept `+Infinity` for `cpu_utilization`, `application_utilization`, `rps_fractional`, and `eps`, and accept `NaN` and `±Infinity` for `request_cost` and `named_metrics` values.
- **Description:** The spec's valid ranges contain only finite numbers (`[0, ∞)` means finite non-negative values; `request_cost` and `named_metrics` take any finite value), and recorders MUST ignore values outside the valid range. `MetricRecorderHelper.isCpuOrApplicationUtilizationValid` and `isRateValid` check only `value >= 0.0`, and the request-cost and named-metric recorders check nothing. A non-finite value in a report can corrupt the client-side `weighted_round_robin` weight.
- **Evidence:** [MetricRecorderHelper.java L28-L48](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/services/src/main/java/io/grpc/services/MetricRecorderHelper.java#L28-L48).
- **Spec:** Backend Metrics (ORCA): Data Model

### [low] Authorization policy translator checks the `grpc-` header-key prefix case-sensitively

- **Item:** AUTHZ-4
- **Summary:** Java accepts a policy header key such as `GRPC-foo`, and because `Metadata.Key` lowercases names, the rule then matches the reserved `grpc-foo` header.
- **Description:** The spec makes a policy invalid if a header `key` starts with `grpc-`, compared case-insensitively. `AuthorizationPolicyTranslator` compares the prefix case-sensitively, so `GRPC-foo` passes validation. The key is lowercased when it becomes a `Metadata.Key`, so the policy can match a `grpc-` header that policies are not allowed to match. Go lowercases the key before checking.
- **Evidence:** grpc-java ed3bf6b76b: [AuthorizationPolicyTranslator.java L175-L187](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/authz/src/main/java/io/grpc/authz/AuthorizationPolicyTranslator.java#L175-L187)
- **Spec:** gRPC Authorization: 2.1 Schema

### [low] No channel- or server-level maximum send message size

- **Item:** MESSAGE_SIZE-1
- **Summary:** Java can limit outgoing message size only per call or through the method config on the client, and not at all on the server.
- **Description:** The spec requires implementations to support a maximum send message size configured through the channel API and the server API. `ManagedChannelBuilder` and `ServerBuilder` offer only `maxInboundMessageSize`. On the client the send limit can be set only with `CallOptions.withMaxOutboundMessageSize` or `maxRequestMessageBytes` in the method config; the server never limits outgoing messages. C++ (`GRPC_ARG_MAX_SEND_MESSAGE_LENGTH`, `ServerBuilder::SetMaxSendMessageSize`) and Go (`MaxCallSendMsgSize` default call option, `MaxSendMsgSize` server option) support both.
- **Evidence:** grpc-java ed3bf6b76b: [ManagedChannelBuilder.java L348](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/ManagedChannelBuilder.java#L348), [ServerBuilder.java L390](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/ServerBuilder.java#L390), [CallOptions.java L482](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/CallOptions.java#L482)
- **Spec:** Core RPC Semantics: 2.12 Message Size Limits

### [low] Streams refused by a non-NO_ERROR GOAWAY fail with a mapped status and are not transparently retried

- **Item:** HTTP2-8
- **Summary:** For a `GOAWAY` with an error code other than `NO_ERROR`, Java fails streams above the last-stream-id with a status derived from the HTTP/2 error code (for example `INTERNAL` for `PROTOCOL_ERROR`, `RESOURCE_EXHAUSTED` for `ENHANCE_YOUR_CALM`) instead of `UNAVAILABLE`, and Netty marks them processed so they are not transparently retried.
- **Description:** The spec requires streams above the `GOAWAY` last-stream-id to fail with `UNAVAILABLE` whatever the error code, and makes them eligible for transparent retry (gRFC A6). Netty's `goingAway` uses `statusFromH2Error` → `Http2Error.statusForCode(errorCode)` and, for non-`NO_ERROR` codes, reports `RpcProgress.PROCESSED` (a workaround for netty/netty#10670); streams still open when the connection later closes use the same mapped status. OkHttp's `goAway`/`startGoAway` likewise builds the status with `Http2Error.statusForCode`. C++ and Go use `UNAVAILABLE` and mark the streams unprocessed.
- **Evidence:** grpc-java ed3bf6b76b: [NettyClientHandler.java L975-L1056](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/netty/src/main/java/io/grpc/netty/NettyClientHandler.java#L975-L1056), [OkHttpClientTransport.java L1575-L1593](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/src/main/java/io/grpc/okhttp/OkHttpClientTransport.java#L1575-L1593), [OkHttpClientTransport.java L1100-L1139](https://github.com/grpc/grpc-java/blob/ed3bf6b76b/okhttp/src/main/java/io/grpc/okhttp/OkHttpClientTransport.java#L1100-L1139)
- **Spec:** gRPC over HTTP/2: 3.1.9.2 GOAWAY; HTTP/2 Client Transport: 4.8.2.5.1 Handling GOAWAY

### [low] Retry throttling does not count failures of committed attempts

- **Item:** RETRY-20
- **Summary:** Java records no `retryThrottling` failure when an attempt fails with a retryable status, or with a "do not retry" pushback, after the RPC is committed (by response headers or by overflowing the retry buffer).
- **Description:** The spec says a failure that counts (a retryable or non-fatal status code, or a "do not retry" pushback) subtracts 1 from `token_count` even if the RPC is already committed to the attempt, as gRFC A6's "Every failed RPC will decrement the `token_count` by 1" requires. Java returns early for committed attempts: through `commitAndRun` when `substream.bufferLimitExceeded`, and it reaches the retry decision (and `throttle.onQualifiedFailureThenCheckIsAboveThreshold()`) only when `state.winningSubstream == null`. A method that always commits before failing (server streaming, or requests larger than `perRpcBufferLimit`) adds `tokenRatio` on `OK` but never subtracts on a retryable failure, so throttling never kicks in for it.
- **Evidence:** `core/src/main/java/io/grpc/internal/RetriableStream.java` `Sublistener.closed` (https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L942-L963) and `makeRetryDecision` (https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L1083-L1089).
- **Spec:** Retries and Hedging: Behavior; Retries and Hedging: Token Accounting

### [low] Trailing dot of the default authority passed to the TLS engine

- **Item:** TLS-22
- **Summary:** For a default authority with a trailing dot, Java (Netty) passes the host with the dot to the `SSLEngine` as the peer host, which is used for SNI and HTTPS endpoint identification.
- **Description:** The spec says one trailing `.` is removed before the name is used as SNI (RFC 6066 §3) and as the hostname-verification target name. `ProtocolNegotiators.parseAuthority` takes `URI.getHost()`, which keeps the trailing dot, and `ClientTlsHandler` passes it to `sslContext.newEngine(alloc, host, port)` with HTTPS endpoint identification. Depending on Netty/JDK behavior, the dot is sent in SNI, SNI is dropped, or verification fails. The Netty behavior (`SslUtils.isValidHostNameForSNI`) and the JDK hostname checker weren't checked; confirm when filing.
- **Evidence:** `netty/src/main/java/io/grpc/netty/ProtocolNegotiators.java` (https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/ProtocolNegotiators.java#L661-L664, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/ProtocolNegotiators.java#L676-L687, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/netty/src/main/java/io/grpc/netty/ProtocolNegotiators.java#L749-L770).
- **Spec:** TLS: Server Name Indication (SNI); TLS: Server Certificate Verification

### [low] "Don't retry" pushback not counted by retry throttling for RPCs without a retry policy

- **Item:** RETRY-1
- **Summary:** When an RPC's method has no retry policy, Java does not record a `retryThrottling` failure for a response that carries a "do not retry" (negative or unparseable) `grpc-retry-pushback-ms`.
- **Description:** The spec (following gRFC A6) says a "do not retry" pushback subtracts 1 from `token_count` for every RPC on the channel, whether or not it has a retry or hedging policy. With retries enabled (the default), every RPC goes through `RetriableStream`, possibly with a null policy, and `makeRetryDecision` returns before any throttle accounting when `retryPolicy == null`.
- **Evidence:** `core/src/main/java/io/grpc/internal/RetriableStream.java` `makeRetryDecision` (https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/RetriableStream.java#L1076-L1079); `ManagedChannelImpl.java` (https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ManagedChannelImpl.java#L482-L509).
- **Spec:** Retries and Hedging: Behavior; Retries and Hedging: Token Accounting

### [low] Send message size limit also applied to the uncompressed size

- **Item:** MESSAGE_SIZE-20
- **Summary:** Java fails a compressed outbound message with `RESOURCE_EXHAUSTED` if its uncompressed size exceeds `maxOutboundMessageSize`, even when the compressed size fits.
- **Description:** The spec says the send limit is checked against the message as framed (after compression) and MUST NOT be applied to the uncompressed size of a message the sender compresses. `MessageFramer.writeCompressed` checks the uncompressed byte count against `maxOutboundMessageSize`, and `writeBufferChain` then checks the compressed length too. Only the second check should remain.
- **Evidence:** `core/src/main/java/io/grpc/internal/MessageFramer.java` (https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/MessageFramer.java#L184-L203, https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/MessageFramer.java#L237-L245).
- **Spec:** Core RPC Semantics: Message Size Limits

### [low] xDS extension type URLs compared including the `type.googleapis.com/` prefix

- **Item:** XDS_COMMON-1
- **Summary:** Java looks up xDS extensions (HTTP filters, metadata types, transport sockets, and so on) by the full `type_url`, so any prefix other than `type.googleapis.com/` makes a supported type unknown.
- **Description:** The spec says the type name is the part of the `type_url` after the last `/` and the prefix is not checked (matching protobuf `Any` semantics and Envoy). Java's registries and checks use full URLs, for example the Router filter's `type.googleapis.com/envoy.extensions.filters.http.router.v3.Router`, looked up by the raw `typeUrl`. A control plane that uses another prefix gets the resource rejected (or the extension ignored where unknown types are ignored).
- **Evidence:** grpc-java ed3bf6b76b65fc76c1669ef70b71765844eb8a50: [RouterFilter.java L30](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/RouterFilter.java#L30), [XdsRouteConfigureResource.java L236-L252](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsRouteConfigureResource.java#L236-L252)
- **Spec:** Common Types: Extensions: `google.protobuf.Any` and `TypedStruct`

### [low] Empty `prefix`, `suffix`, `contains`, and regex accepted in `envoy.type.matcher.v3.StringMatcher` and `HeaderMatcher`

- **Item:** XDS_COMMON-20
- **Summary:** Java accepts `""` for all fields of `envoy.type.matcher.v3.StringMatcher` and `envoy.config.route.v3.HeaderMatcher`, while it rejects them for `xds.type.matcher.v3.StringMatcher`.
- **Description:** The spec requires `prefix`, `suffix`, `contains`, and `safe_regex.regex` (and the legacy `*_match` equivalents) to be non-empty, else the resource is rejected, and treats the `envoy` and `xds` `StringMatcher` types identically. Java's `xds` parser already calls `checkNonEmpty`; the `envoy` `StringMatcher` and `HeaderMatcher` parsers don't.
- **Evidence:** grpc-java ed3bf6b76b65fc76c1669ef70b71765844eb8a50: [MatcherParser.java L36-L143](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/internal/MatcherParser.java#L36-L143)
- **Spec:** Common Types: `StringMatcher`; Common Types: `HeaderMatcher`

### [low] Fault injection: out-of-range `http_status` accepted

- **Item:** XDS_FAULT-2
- **Summary:** Java maps any `FaultAbort.http_status`, including values outside [200, 600), instead of NACKing.
- **Description:** The spec follows Envoy: `http_status` MUST be in [200, 600), else NACK. Java's `parseFaultAbort` passes any value to `GrpcUtil.httpStatusToGrpcStatus`.
- **Evidence:** grpc-java ed3bf6b76b65fc76c1669ef70b71765844eb8a50: [FaultFilter.java L163-L181](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/FaultFilter.java#L163-L181)
- **Spec:** xDS HTTP Filters: Fault Injection: Configuration

### [low] CDS `transport_socket.name` other than `envoy.transport_sockets.tls` rejects the Cluster

- **Item:** XDS_CDS-3
- **Summary:** Java NACKs a Cluster whose `transport_socket.name` is not `envoy.transport_sockets.tls` (unless the `typed_config` is `Http11ProxyUpstreamTransport`).
- **Description:** The spec ignores `transport_socket.name` on Clusters and selects behavior only by the `typed_config` type (as Envoy does). Java checks the name and rejects the Cluster with "transport-socket with name … not supported".
- **Evidence:** grpc-java ed3bf6b76b65fc76c1669ef70b71765844eb8a50: [XdsClusterResource.java L250-L262](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L250-L262)
- **Spec:** Cluster: Transport Socket; xDS Security: Locating the TLS Context

### [low] cds, xds_cluster_manager, and xds_wrr_locality don't forward ExitIdle (`requestConnection`)

- **Item:** XDS_LB-9
- **Summary:** `ClusterManagerLoadBalancer`, `CdsLoadBalancer2`, and `WrrLocalityLoadBalancer` don't override `requestConnection()`, so ExitIdle stops at these policies.
- **Description:** The spec says `xds_cluster_manager` forwards ExitIdle to every child (including deactivated ones) and `cds` and `xds_wrr_locality` forward it to their child. These Java policies (and `MultiChildLoadBalancer`, which `ClusterManagerLoadBalancer` extends) inherit `LoadBalancer`'s no-op `requestConnection()`.
- **Evidence:** grpc-java ed3bf6b76b65fc76c1669ef70b71765844eb8a50: [LoadBalancer.java L444](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/api/src/main/java/io/grpc/LoadBalancer.java#L444), `xds/src/main/java/io/grpc/xds/ClusterManagerLoadBalancer.java`, `CdsLoadBalancer2.java`, `WrrLocalityLoadBalancer.java` (no `requestConnection` override)
- **Spec:** `xds_cluster_manager` LB Policy: ExitIdle; `cds` LB Policy: ExitIdle; `xds_wrr_locality` LB Policy: ExitIdle

### [low] `google-c2p` targets with a non-empty authority are accepted

- **Item:** VENDOR-1
- **Summary:** Java's `google-c2p` resolver doesn't reject a target authority; on the DNS path the authority becomes the DNS server, and on the xDS path it is replaced.
- **Description:** The spec says the authority MUST be empty and a non-empty authority makes resolver creation fail. Java has no authority check; the child target keeps the original URI with the scheme changed, so the DNS path resolves `dns://<authority>/<name>`, while the xDS path silently overwrites the authority with `traffic-director-c2p.xds.googleapis.com`.
- **Evidence:** grpc-java ed3bf6b76b65fc76c1669ef70b71765844eb8a50: [GoogleCloudToProdNameResolverProvider.java L52-L67](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/googleapis/src/main/java/io/grpc/googleapis/GoogleCloudToProdNameResolverProvider.java#L52-L67), [GoogleCloudToProdNameResolver.java L149-L154](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/googleapis/src/main/java/io/grpc/googleapis/GoogleCloudToProdNameResolver.java#L149-L154), [L196-L211](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/googleapis/src/main/java/io/grpc/googleapis/GoogleCloudToProdNameResolver.java#L196-L211)
- **Spec:** `google-c2p` Resolver: Target URI

### [low] `google-c2p` fails resolution on a metadata-query I/O error and sets no connect timeout

- **Item:** VENDOR-4
- **Summary:** Java's `google-c2p` resolver reports `INTERNAL` "Unable to get metadata" when a metadata-server query hits an `IOException` (connect failure, read timeout), and its metadata connections have no connect timeout.
- **Description:** The spec says each metadata query has a 10-second timeout and that a failed query (including one that cannot be sent or completed) yields an empty zone or "not IPv6-capable" without failing resolution. Java handles a non-200 status that way but lets an `IOException` propagate, failing resolution until the next `refresh()`. The `HttpURLConnection` sets only a 10 s read timeout.
- **Evidence:** grpc-java ed3bf6b76b65fc76c1669ef70b71765844eb8a50: [GoogleCloudToProdNameResolver.java L257-L262](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/googleapis/src/main/java/io/grpc/googleapis/GoogleCloudToProdNameResolver.java#L257-L262), [L349-L385](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/googleapis/src/main/java/io/grpc/googleapis/GoogleCloudToProdNameResolver.java#L349-L385), [L412-L422](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/googleapis/src/main/java/io/grpc/googleapis/GoogleCloudToProdNameResolver.java#L412-L422)
- **Spec:** `google-c2p` Resolver: Metadata Server Queries

### [low] Aggregate cluster depth limit allows 17 levels, uses INTERNAL, and is not passed up to ancestors

- **Item:** XDS_DEPMGR-3
- **Summary:** The depth check is `ancestors.size() > 16` with status INTERNAL. It sets the error only on the too-deep cluster, which ancestors then treat as a failing leaf.
- **Description:** The spec (following gRFC A37's depth limit of 16) says that when expansion reaches depth 16, the aggregate at the root of that branch and every aggregate above it get UNAVAILABLE `aggregate cluster graph exceeds max depth`. Java allows one more level, uses a different code, and doesn't pass the error up.
- **Evidence:** grpc-java ed3bf6b76b: [XdsDependencyManager.java L312-L316](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsDependencyManager.java#L312-L316)
- **Spec:** Client Data Plane: Aggregate cluster graph (`09-xds/05-client.md`)

### [low] weighted_round_robin accepts negative Duration values in its config

- **Item:** WRR-22
- **Summary:** A negative `oobReportingPeriod`, `blackoutPeriod`, `weightExpirationPeriod`, or `weightUpdatePeriod` is accepted instead of making the config invalid.
- **Description:** The spec makes the `weighted_round_robin` config invalid if any of these four Duration fields is negative. Java parses them with `JsonUtil.getStringAsDuration`, whose `parseDuration` accepts a leading `-`. `parseLoadBalancingPolicyConfigInternal` has no sign check: it only raises `weightUpdatePeriod` to 100 ms. As a result, a negative `weightExpirationPeriod` expires every weight immediately and a negative `oobReportingPeriod` is sent in `OrcaLoadReportRequest`.
- **Evidence:** grpc-java ed3bf6b76b: [WeightedRoundRobinLoadBalancerProvider.java L75-L114](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/WeightedRoundRobinLoadBalancerProvider.java#L75-L114), [JsonUtil.java L282-L305](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/JsonUtil.java#L282-L305)
- **Spec:** `weighted_round_robin` LB Policy: 2.2 Validation

### [low] xds_cluster_manager fails a pick for an unknown cluster with UNAVAILABLE instead of INTERNAL

- **Item:** XDS_LB-8
- **Summary:** When the cluster call attribute names no child, the picker fails the pick with UNAVAILABLE, and wait_for_ready RPCs queue.
- **Description:** The spec says a pick whose cluster attribute is missing or names no active child MUST fail with INTERNAL. That case signals an internal bug, since two-phase cluster removal means it should never happen. Java's `ClusterManagerLoadBalancer` picker returns `PickResult.withError(Status.UNAVAILABLE ... "CDS encountered error: unable to find available subchannel for cluster ...")`. Because this is an error result with UNAVAILABLE, wait_for_ready RPCs queue and could hang instead of failing.
- **Evidence:** grpc-java ed3bf6b76b: [ClusterManagerLoadBalancer.java L147-L151](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/ClusterManagerLoadBalancer.java#L147-L151)
- **Spec:** `xds_cluster_manager` LB Policy: Picker Implementation

### [low] LOGICAL_DNS cluster accepts a `port_value` of 0 or above 65535

- **Item:** XDS_CDS-21
- **Summary:** A `LOGICAL_DNS` Cluster with `port_value` 0 (set explicitly) or greater than 65535 is accepted, and values of 2^31 or more come out negative in the DNS name.
- **Description:** The spec says the `LOGICAL_DNS` `port_value` MUST be in 1–65535. `XdsClusterResource` checks only `getPortSpecifierCase() == PORT_VALUE`, then formats `getPortValue()` (a Java `int`) with `%d` and no range check. So `host:0`, `host:70000`, or `host:-1` is passed to the DNS resolver instead of the Cluster being NACKed.
- **Evidence:** grpc-java ed3bf6b76b: [XdsClusterResource.java L358-L364](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsClusterResource.java#L358-L364)
- **Spec:** Cluster: Logical DNS Clusters

### [low] EDS accepts a drop_overloads entry with an empty category

- **Item:** XDS_EDS-4
- **Summary:** A `DropOverload` with an empty `category` is accepted instead of NACKing the resource.
- **Description:** The spec, following Envoy's `category` validation rule (`min_len: 1`), requires a non-empty drop category, which is used as the category name in load reports. `XdsEndpointResource.parseDropOverload` passes `proto.getCategory()` through with no check.
- **Evidence:** grpc-java ed3bf6b76b: [XdsEndpointResource.java L163-L166](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L163-L166)
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: Drop Overloads

### [low] EDS drop rate normalization can wrap in `int` and escape the 100% cap

- **Item:** XDS_EDS-4
- **Summary:** `getRatePerMillion` multiplies the numerator by 10,000 (HUNDRED) or 100 (TEN_THOUSAND) in a Java `int`. An oversized numerator can wrap to a small positive value that passes the `> 1_000_000 || < 0` cap check.
- **Description:** The spec caps the normalized drop rate at 1,000,000 per million. For example, a HUNDRED numerator of 429,497 gives 4,294,970,000, which wraps to 2,704 in 32 bits, so the drop rate becomes about 0.27% instead of 100%. The cap check only catches results that are negative or above 1,000,000. Fix: clamp the numerator to the denominator before multiplying, or compute in `long`.
- **Evidence:** grpc-java ed3bf6b76b: [XdsEndpointResource.java L168-L189](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/xds/src/main/java/io/grpc/xds/XdsEndpointResource.java#L168-L189)
- **Spec:** ClusterLoadAssignment and LbEndpointCollection: Drop Overloads

### [low] A JSON `null` field value makes the service config invalid

- **Item:** SERVICE_CONFIG-10
- **Summary:** A service config field whose value is JSON `null` makes the whole service config invalid, instead of being treated as absent.
- **Description:** The spec says a field whose value is JSON `null` means the same as an absent field (C++ and Go do this, and doc/service_config.md defines the JSON form through the protobuf JSON mapping, which treats `null` as the default). Java's `JsonUtil` getters return null only for a missing key; a present key with a `null` value fails the type check and throws, and `ScParser` turns that into an invalid config. This includes `methodConfig[].name[].service`/`method`, which the spec explicitly allows to be `null`.
- **Evidence:** [JsonUtil.java L85-L96](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/JsonUtil.java#L85-L96), [ScParser.java L71-L78](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ScParser.java#L71-L78), [ServiceConfigUtil.java L211-L218](https://github.com/grpc/grpc-java/blob/ed3bf6b76b65fc76c1669ef70b71765844eb8a50/core/src/main/java/io/grpc/internal/ServiceConfigUtil.java#L211-L218).
- **Spec:** Service Config: Format

