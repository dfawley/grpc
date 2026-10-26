> [!WARNING]
> This is a new, experimental gRPC specification. It was generated primarily
> by AI and has not yet been fully reviewed.

# gRPC Specification

This directory contains the specification of gRPC's cross-language behavior:
the wire protocol, the client channel, the server, security, the standard gRPC
services, observability, and xDS (proxyless service mesh) support. It describes
the *current* behavior that all gRPC implementations are expected to provide.

See [Introduction and Conventions](00-introduction/README.md) for scope,
requirements language, and how experimental features are marked.

## Table of Contents

### [0. Introduction and Conventions](00-introduction/README.md)

### [1. Architecture Overview](01-architecture/README.md)

### [2. Core RPC Semantics](02-rpc-semantics/README.md)
Channels and servers; methods, services, and RPC types; calls and
cancellation; flow control; metadata; deadlines; authority; status codes;
ordering of status and messages; message size limits; compression;
wait-for-ready; interceptors; codecs; API requirements.

### [3. Wire Protocol](03-wire-protocol/README.md)
- [3.1 gRPC over HTTP/2](03-wire-protocol/01-http2.md): request/response grammar, headers, metadata encoding, message framing, status and error mapping, non-gRPC responses, RST_STREAM/GOAWAY/PING, TLS
- [3.2 True Binary Metadata](03-wire-protocol/02-true-binary-metadata.md): HTTP/2 extension for sending `-bin` metadata without base64
- [3.3 gRPC over HTTP/3](03-wire-protocol/03-http3.md): HTTP/3 mapping: stream identification, error codes, stream reset, deadlines and cancellation
- [3.4 Protocol Buffers Mapping](03-wire-protocol/04-protobuf.md): services, methods, and messages on the wire; content-subtypes; rich status details

### [4. Client Channel](04-client-channel/README.md)
- [4.1 Client Channel Architecture](04-client-channel/01-architecture.md): components, architecture, connection establishment walkthrough
- [4.2 Channel](04-client-channel/02-channel.md): creation, targets, authority, connectivity state, idleness, shutdown
- [4.3 Name Resolution](04-client-channel/03-name-resolution.md): resolver registry, resolver API, resolver results, built-in resolvers
- [4.4 Service Config](04-client-channel/04-service-config.md): format, delivery, validation, field reference
- [4.5 Per-call Configuration and Call Flow](04-client-channel/05-call-dispatch.md): ConfigSelector, RPC dispatch
- [4.6 Load Balancing](04-client-channel/06-load-balancing.md): LB policy, helper, picker, and subchannel APIs; state aggregation; policy switching; backend metrics consumption
  - [`pick_first`](04-client-channel/lb-policies/pick_first.md)
  - [`round_robin`](04-client-channel/lb-policies/round_robin.md)
  - [`weighted_round_robin`](04-client-channel/lb-policies/weighted_round_robin.md)
  - [`least_request`](04-client-channel/lb-policies/least_request.md)
  - [`ring_hash`](04-client-channel/lb-policies/ring_hash.md)
  - [`random_subsetting`](04-client-channel/lb-policies/random_subsetting.md)
  - [`outlier_detection`](04-client-channel/lb-policies/outlier_detection.md)
  - [`priority`](04-client-channel/lb-policies/priority.md)
  - [`weighted_target`](04-client-channel/lb-policies/weighted_target.md)
  - [`rls`](04-client-channel/lb-policies/rls.md)
- [4.7 Subchannels and Connections](04-client-channel/07-subchannels.md): connection backoff, MAX_CONCURRENT_STREAMS connection scaling, connection-scoped watchers and streams
- 4.8 Client Transports
  - [4.8.1 Client Transport Model](04-client-channel/08-transports/01-transport-model.md): what any client transport provides to the subchannel
  - [4.8.2 HTTP/2 Client Transport](04-client-channel/08-transports/02-http2.md): settings, stream limits, flow control, keepalive, GOAWAY handling
  - [4.8.3 HTTP/3 Client Transport](04-client-channel/08-transports/03-http3.md)
  - [4.8.4 In-Process Client Transport](04-client-channel/08-transports/04-in-process.md)
- [4.9 HTTP CONNECT Proxy Support](04-client-channel/09-proxy.md): proxy mapping and the CONNECT handshake
- [4.10 Client-Side Health Checking](04-client-channel/10-health-checking.md): health checking using the health service
- [4.11 Client-Side Backend Metrics (ORCA)](04-client-channel/11-backend-metrics.md): per-call and out-of-band backend metric reports
- [4.12 Retries and Hedging](04-client-channel/12-retries.md): retry and hedging policies, throttling, transparent retries

### [5. Server](05-server/README.md)
- [5.1 Server Behavior](05-server/01-server.md): lifecycle, request handling, response semantics, interceptors, connection management
- 5.2 Server Transports
  - [5.2.1 Server Transport Model](05-server/02-transports/01-transport-model.md): what any server transport provides to the server
  - [5.2.2 HTTP/2 Server Transport](05-server/02-transports/02-http2.md): settings, stream limits, flow control, keepalive and ping enforcement, connection management
  - [5.2.3 HTTP/3 Server Transport](05-server/02-transports/03-http3.md)
  - [5.2.4 In-Process Server Transport](05-server/02-transports/04-in-process.md)

### [6. Security](06-security/README.md)
- [6.1 Security Model](06-security/01-security-model.md): channel, server, call, and composite credentials; security levels; AuthContext; authority override
- [6.2 TLS](06-security/02-tls.md): versions, ALPN, SNI, hostname and per-RPC authority verification, mTLS, certificate providers, custom verification, CRLs, SPIFFE, private key offloading, key exchange groups
- [6.3 Call Credentials](06-security/03-call-credentials.md): call credential behavior; access token, GCP service account identity, and JWT token file credentials
- [6.4 Authorization](06-security/04-authorization.md): RBAC engine, gRPC authorization policy, audit logging

### [7. Standard Services and Admin Interface](07-services/README.md)
- [7.1 Health Service](07-services/01-health.md): `grpc.health.v1.Health`: per-service and overall serving status
- [7.2 Server Reflection](07-services/02-reflection.md): `grpc.reflection.v1.ServerReflection`: services and protobuf descriptors at runtime
- [7.3 Backend Metrics (ORCA)](07-services/03-orca.md): `xds.service.orca.v3.OpenRcaService`: out-of-band backend metric reports
- [7.4 Admin Interface](07-services/04-admin.md): a single call that adds the admin services (channelz, CSDS) to a server

### [8. Observability](08-observability/README.md)
- [8.1 Overview and Common Principles](08-observability/01-overview.md): the observability facilities and the principles they share
- [8.2 Instrumentation Architecture](08-observability/02-instrumentation.md): call, attempt, and server tracers
- [8.3 Metrics Framework and OpenTelemetry Plugin](08-observability/03-metrics-framework.md): instrument registry, scoping, labels, the OpenTelemetry plugin
- [8.4 Metric Catalog](08-observability/04-metrics.md): every metric gRPC records
- [8.5 Tracing](08-observability/05-tracing.md): OpenTelemetry tracing and `grpc-trace-bin`
- [8.6 Channelz](08-observability/06-channelz.md): the channelz data model and service
- [8.7 Binary Logging](08-observability/07-binary-logging.md): binary log configuration, format, and sinks

### [9. xDS / Proxyless Service Mesh Support](09-xds/README.md)
- [9.1 Architecture and Design Principles](09-xds/01-architecture.md): components, design principles, client features, server features
- [9.2 Bootstrap](09-xds/02-bootstrap.md): bootstrap configuration
- [9.3 XdsClient](09-xds/03-xds-client.md): transport, subscriptions, resource naming and federation, watchers, caching, error handling, fallback
- 9.4 Resources and Validation
  - [9.4.1 Common Types](09-xds/04-resources/01-common-types.md)
  - [9.4.2 Listener](09-xds/04-resources/02-listener.md)
  - [9.4.3 RouteConfiguration](09-xds/04-resources/03-route-configuration.md)
  - [9.4.4 Cluster](09-xds/04-resources/04-cluster.md)
  - [9.4.5 ClusterLoadAssignment and LbEndpointCollection](09-xds/04-resources/05-endpoint.md)
- [9.5 Client Data Plane](09-xds/05-client.md): `xds` resolver, XdsDependencyManager, XdsConfig, routing
- [9.6 xDS LB Policies](09-xds/06-lb-policies.md): LB policy tree and the xDS LB policy registry
  - [`xds_cluster_manager`](09-xds/lb-policies/xds_cluster_manager.md)
  - [`cds`](09-xds/lb-policies/cds.md)
  - [`xds_cluster_impl`](09-xds/lb-policies/xds_cluster_impl.md)
  - [`xds_override_host`](09-xds/lb-policies/xds_override_host.md)
  - [`xds_wrr_locality`](09-xds/lb-policies/xds_wrr_locality.md)
- [9.7 xDS HTTP Filters](09-xds/07-http-filters.md): filter framework, router, fault injection, RBAC, stateful session affinity, GCP authentication
- [9.8 xDS-Enabled Servers](09-xds/08-server.md): serving state, Listener handling, filter chain matching
- [9.9 xDS Security](09-xds/09-security.md): xDS credentials and TLS configuration
- [9.10 Load Reporting (LRS)](09-xds/10-load-reporting.md): load reporting to the control plane
- [9.11 Client Status Discovery Service (CSDS)](09-xds/11-csds.md): exposing xDS configuration for debugging

### Appendices
- [A. Reserved Metadata Keys](appendices/a-metadata-keys.md)
- [B. Environment Variables](appendices/b-environment-variables.md)
- [C. Protocol Buffer and JSON Schema Index](appendices/c-schemas.md)
- [D. gRFC Traceability Matrix](appendices/d-traceability.md)
- [E. Historical and Superseded Behavior](appendices/e-historical.md)
- [F. Conformance and Interop Tests](appendices/f-conformance.md)
- [G. Glossary](appendices/g-glossary.md)
