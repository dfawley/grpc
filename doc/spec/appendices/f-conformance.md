> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# Appendix F. Conformance and Interoperability Tests (Informative)

<!-- Sources: doc/interop-test-descriptions.md, doc/http2-interop-test-descriptions.md, doc/xds-test-descriptions.md, doc/connection-backoff-interop-test-description.md, doc/connection-backoff.md -->

This appendix is informative. gRPC has no formal conformance certification.
Instead, implementations check that they interoperate by running shared test
suites against each other. Each suite is described in its own document in
`grpc/doc`. The descriptions there are the reference for test procedures and
assertions. This appendix summarizes what each suite covers and which parts
of this specification it exercises.

A test passing does not establish conformance with this specification, and
the suites do not cover every requirement. Where a test description and this
specification disagree, this specification describes the intended behavior.

All suites use the test service in `src/proto/grpc/testing/test.proto`, with
messages in `messages.proto` and `empty.proto`. The main services are
`grpc.testing.TestService` (`EmptyCall`, `UnaryCall`, `CacheableUnaryCall`,
`StreamingOutputCall`, `StreamingInputCall`, `FullDuplexCall`,
`HalfDuplexCall`, `UnimplementedCall`), `grpc.testing.UnimplementedService`,
`grpc.testing.ReconnectService`, `grpc.testing.LoadBalancerStatsService`, and
`grpc.testing.XdsUpdateClientConfigureService`.

## F.1 Core Interoperability Tests

Document: [interop-test-descriptions.md](../../interop-test-descriptions.md)

A test client and a test server, possibly from different implementations, run
named test cases over plaintext or TLS (with ALPN and certificate checking).
The client is given a test case name on the command line. The server
implements a fixed set of *server features*, which are behaviors of the test
service that clients depend on: empty calls, unary and streaming calls with
response parameters and payload sizes, compressed requests and responses,
echoing status, echoing metadata, response intervals, echoing
authentication information, backend metrics reports, filling in the peer
socket address, and a `MAX_CONCURRENT_STREAMS` limit.

| Area | Test cases | Spec sections exercised |
| --- | --- | --- |
| Basic RPC types | `empty_unary`, `large_unary`, `client_streaming`, `server_streaming`, `ping_pong`, `empty_stream` | [Core RPC Semantics](../02-rpc-semantics/README.md); [gRPC over HTTP/2](../03-wire-protocol/http2.md); [Protocol Buffers Mapping](../03-wire-protocol/protobuf.md) |
| Caching hint | `cacheable_unary` | [gRPC over HTTP/2](../03-wire-protocol/http2.md) |
| Compression | `client_compressed_unary`, `server_compressed_unary`, `client_compressed_streaming`, `server_compressed_streaming` (per-message compression flags, compression with feature probing) | [Compression](../02-rpc-semantics/README.md); [gRPC over HTTP/2](../03-wire-protocol/http2.md) ([`grpc-encoding` and `grpc-accept-encoding`](../03-wire-protocol/http2.md#39-grpc-encoding-and-grpc-accept-encoding), [gRPC over HTTP/2: Length-Prefixed Messages](../03-wire-protocol/http2.md#5-length-prefixed-messages)); [Server](../05-server/README.md) ([Server: Compression](../05-server/README.md#34-compression)) |
| Call credentials | `oauth2_auth_token`, `per_rpc_creds`, `jwt_token_creds`, `compute_engine_creds` (the server echoes the authenticated user and OAuth scope) | [Call Credentials](../06-security/call-credentials.md); [Security](../06-security/README.md) |
| Metadata | `custom_metadata` (initial and trailing metadata echo, including binary values) | [Metadata](../02-rpc-semantics/README.md); [gRPC over HTTP/2](../03-wire-protocol/http2.md) ([gRPC over HTTP/2: Metadata Encoding](../03-wire-protocol/http2.md#4-metadata-encoding)) |
| Status | `status_code_and_message`, `special_status_message` (percent-encoding of non-ASCII and special characters in `grpc-message`), `unimplemented_method`, `unimplemented_service` | [Status](../02-rpc-semantics/README.md); [gRPC over HTTP/2](../03-wire-protocol/http2.md) ([`grpc-status`](../03-wire-protocol/http2.md#63-grpc-status), [`grpc-message`](../03-wire-protocol/http2.md#64-grpc-message)); [Server](../05-server/README.md) ([Server: Method Dispatch](../05-server/README.md#22-method-dispatch)) |
| Cancellation and deadlines | `cancel_after_begin`, `cancel_after_first_response`, `timeout_on_sleeping_server` | [Cancellation](../02-rpc-semantics/README.md); [Deadlines](../02-rpc-semantics/README.md); [gRPC over HTTP/2](../03-wire-protocol/http2.md) ([`grpc-timeout`](../03-wire-protocol/http2.md#37-grpc-timeout), [gRPC over HTTP/2: Errors, Cancellation, and RST_STREAM](../03-wire-protocol/http2.md#8-errors-cancellation-and-rst_stream)) |
| Stability | `rpc_soak` (many RPCs on one channel), `channel_soak` (a new channel for each RPC), with latency and failure thresholds | [Channel](../04-client-channel/channel.md); [Subchannels and Connections](../04-client-channel/subchannels.md) |
| Backend metrics (ORCA) | `orca_per_rpc` and `orca_oob`: a custom test LB policy, selected by service config, receives per-call reports (`endpoint-load-metrics-bin`) and out-of-band reports | [Backend Metrics (ORCA)](../07-services/orca.md); [Load Balancing](../04-client-channel/load-balancing.md) (backend metrics consumption) |
| Connection scaling | `max_concurrent_streams_connection_scaling`: with `connectionScaling.maxConnectionsPerSubchannel` = 2 and a server stream limit of 2, the third concurrent stream uses a new connection | [Subchannels and Connections](../04-client-channel/subchannels.md) ([Subchannels and Connections: MAX_CONCURRENT_STREAMS Connection Scaling](../04-client-channel/subchannels.md#8-max_concurrent_streams-connection-scaling)); [Service Config](../04-client-channel/service-config.md) ([`connectionScaling`](../04-client-channel/service-config.md#56-connectionscaling)) |

Test cases for Google-specific credentials (`google_default_credentials`,
`compute_engine_channel_credentials`) are also in this document. They
exercise features that this specification excludes. The document also lists
experimental and to-do tests (for example `long_lived_channel`), which are
not part of the standard interop matrix.

## F.2 HTTP/2 Transport Tests

Document: [http2-interop-test-descriptions.md](../../http2-interop-test-descriptions.md)

A purpose-built HTTP/2 test server sends deliberately unusual frame
sequences, and a regular gRPC client must handle them. The server and client
run the same named test case.

| Test case | What it checks | Spec sections exercised |
| --- | --- | --- |
| `goaway` | The client moves new RPCs to a new connection after GOAWAY, without application involvement. | [gRPC over HTTP/2](../03-wire-protocol/http2.md) ([GOAWAY](../03-wire-protocol/http2.md#92-goaway)); [HTTP/2 Transport Behavior](../03-wire-protocol/http2-transport.md) ([HTTP/2 Transport Behavior: Client Handling of GOAWAY](../03-wire-protocol/http2-transport.md#6-client-handling-of-goaway)); [Channel](../04-client-channel/channel.md) |
| `rst_after_header`, `rst_during_data`, `rst_after_data` | The client fails the RPC correctly when the server resets the stream after headers, partway through data, or after all data. | [gRPC over HTTP/2](../03-wire-protocol/http2.md) ([RST_STREAM](../03-wire-protocol/http2.md#82-rst_stream)) |
| `ping` | The client acknowledges every PING. | [gRPC over HTTP/2](../03-wire-protocol/http2.md) ([PING](../03-wire-protocol/http2.md#93-ping)); [HTTP/2 Transport Behavior](../03-wire-protocol/http2-transport.md) ([HTTP/2 Transport Behavior: Keepalive](../03-wire-protocol/http2-transport.md#4-keepalive)) |
| `max_streams` | The client respects the server's `SETTINGS_MAX_CONCURRENT_STREAMS`, queuing RPCs beyond the limit instead of failing them. | [HTTP/2 Transport Behavior](../03-wire-protocol/http2-transport.md) ([SETTINGS sent](../03-wire-protocol/http2-transport.md#12-settings-sent), [HTTP/2 Transport Behavior: MAX_CONCURRENT_STREAMS](../03-wire-protocol/http2-transport.md#2-max_concurrent_streams)) |
| `data_frame_padding`, `no_df_padding_sanity_test` | The client handles padded and many small DATA frames, including correct flow-control accounting for padding. | [gRPC over HTTP/2](../03-wire-protocol/http2.md) ([gRPC over HTTP/2: Length-Prefixed Messages](../03-wire-protocol/http2.md#5-length-prefixed-messages)); [HTTP/2 Transport Behavior](../03-wire-protocol/http2-transport.md) ([HTTP/2 Transport Behavior: Flow Control](../03-wire-protocol/http2-transport.md#3-flow-control)) |

## F.3 Connection Backoff Test

Document: [connection-backoff-interop-test-description.md](../../connection-backoff-interop-test-description.md)

The client calls `ReconnectService.Start` on a plaintext control port. It then
connects with TLS to a retry port where the test server closes every incoming
TCP connection. The client keeps reconnecting for about 540 seconds (roughly
13 attempts). It then calls `Stop`. The server records the time of each
reconnection attempt, compares the backoff intervals with the connection
backoff algorithm, and returns the intervals and a pass/fail verdict. The
client may also check the intervals itself.

Spec sections exercised: [Subchannels and Connections](../04-client-channel/subchannels.md) ([Subchannels and Connections: Connection Backoff](../04-client-channel/subchannels.md#7-connection-backoff), connection backoff).

## F.4 xDS Interoperability Tests

Document: [xds-test-descriptions.md](../../xds-test-descriptions.md)

These tests run real gRPC xDS clients and servers against a real xDS control
plane. Unlike the other suites, the client and server do not know which
scenario is being tested. A separate test driver configures the control plane
and the backends. It then queries the client's `LoadBalancerStatsService`
(`GetClientStats` for the next N RPCs, and `GetClientAccumulatedStats`) to
check how RPCs were distributed across peers, and what statuses they
returned. The driver can change the client's RPC types, metadata, and timeout
during a test through `XdsUpdateClientConfigureService`.

- The **test server** serves the test service on one port and runs health,
  channelz, and admin (CSDS) services on a maintenance port. In secure mode it
  uses xDS server credentials.
- The test server honors an `rpc-behavior` request header (sleep, keep the
  stream open, return an error code, succeed on a given retry attempt using
  `grpc-previous-rpc-attempts`, or apply only on a given host name). The
  test server can also report ORCA metrics in-band or out-of-band for WRR
  testing.
- The **test client** sends a constant rate of unary RPCs over one or more
  channels. In secure mode it uses xDS channel credentials.

| Test case | What it checks | Spec sections exercised |
| --- | --- | --- |
| `ping_pong`, `round_robin` | Every backend gets traffic. Traffic is spread evenly. | [Client Data Plane](../09-xds/client.md); [xDS LB Policies](../09-xds/lb-policies.md); [`round_robin`](../04-client-channel/lb-policies/round_robin.md) |
| `backends_restart` | Traffic resumes after all backends stop and restart. | [Subchannels and Connections](../04-client-channel/subchannels.md); [`round_robin`](../04-client-channel/lb-policies/round_robin.md) |
| `secondary_locality_gets_requests_on_primary_failure`, `secondary_locality_gets_no_requests_on_partial_primary_failure`, `gentle_failover`, `load_based_failover` | Priority and locality failover. | [`priority`](../04-client-channel/lb-policies/priority.md); [ClusterLoadAssignment](../09-xds/resources/endpoint.md); [xDS LB Policies](../09-xds/lb-policies.md) ([`cds`](../09-xds/lb-policies/cds.md)) |
| `remove_instance_group`, `change_backend_service` | Endpoint and cluster changes take effect without failures. | [XdsClient](../09-xds/xds-client.md); [Client Data Plane](../09-xds/client.md) ([Client Data Plane: XdsDependencyManager](../09-xds/client.md#2-xdsdependencymanager), [Cluster references and two-phase removal](../09-xds/client.md#54-cluster-references-and-two-phase-removal)) |
| `traffic_splitting`, `path_matching`, `header_matching` | Weighted clusters, and route matching on path and headers. | [RouteConfiguration](../09-xds/resources/route-configuration.md); [Client Data Plane](../09-xds/client.md) ([Client Data Plane: xDS ConfigSelector](../09-xds/client.md#5-xds-configselector)) |
| `circuit_breaking` | Outstanding requests to a cluster are limited by `max_requests`. | [Cluster](../09-xds/resources/cluster.md) ([Circuit Breakers](../09-xds/resources/cluster.md#3-circuit-breakers)); [xDS LB Policies](../09-xds/lb-policies.md) ([Circuit breaking](../09-xds/lb-policies/xds_cluster_impl.md#2-circuit-breaking)) |
| `timeout` | `max_stream_duration` on a route makes RPCs fail with `DEADLINE_EXCEEDED`. | [RouteConfiguration](../09-xds/resources/route-configuration.md) ([Max Stream Duration](../09-xds/resources/route-configuration.md#9-max-stream-duration)); [Client Data Plane](../09-xds/client.md) ([Timeout](../09-xds/client.md#56-timeout)) |
| `api_listener` | Replacing the API listener under the same name keeps working. | [Listener](../09-xds/resources/listener.md); [XdsClient](../09-xds/xds-client.md) |
| `metadata_filter`, `forwarding_rule_port_match`, `forwarding_rule_default_port` | Control-plane matching on node metadata and on the target port. | [Bootstrap](../09-xds/bootstrap.md) ([Node Object](../09-xds/bootstrap.md#42-node-object)); [Client Data Plane](../09-xds/client.md) ([Client Data Plane: The `xds` Resolver](../09-xds/client.md#1-the-xds-resolver)) |
| `outlier_detection` | A failing backend is temporarily ejected. | [`outlier_detection`](../04-client-channel/lb-policies/outlier_detection.md); [Cluster](../09-xds/resources/cluster.md) ([Outlier Detection](../09-xds/resources/cluster.md#4-outlier-detection)) |
| `custom_lb` | A custom LB policy is selected through `TypedStruct`. An unsupported policy in the list is skipped. | [xDS LB Policies](../09-xds/lb-policies.md) ([xDS LB Policies: xDS LB Policy Registry](../09-xds/lb-policies.md#2-xds-lb-policy-registry)) |

Some cases (`metadata_filter` and the forwarding-rule cases) test behavior of
a particular control plane as much as of the gRPC client.

## F.5 Coverage Gaps

The suites above do not exercise many parts of this specification, for
example:

- retries and hedging beyond the `rpc-behavior` hooks;
- the service config delivered through DNS;
- keepalive enforcement;
- true binary metadata and HTTP/3;
- xDS security, RBAC, fault injection, and stateful session affinity;
- channelz, binary logging, and OpenTelemetry metrics and tracing.

Implementations are expected to test these with their own unit and
end-to-end tests.
