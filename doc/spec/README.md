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
- [3.1 gRPC over HTTP/2](03-wire-protocol/01-http2.md)
- [3.2 HTTP/2 Transport Behavior](03-wire-protocol/02-http2-transport.md):
  settings, flow control, keepalive, server connection management
- [3.3 True Binary Metadata](03-wire-protocol/03-true-binary-metadata.md)
- [3.4 gRPC over HTTP/3](03-wire-protocol/04-http3.md)
- [3.5 Protocol Buffers Mapping](03-wire-protocol/05-protobuf.md)

### [4. Client Channel](04-client-channel/README.md)
- [4.1 Channel](04-client-channel/01-channel.md): creation, targets, authority,
  connectivity state, idleness
- [4.2 Name Resolution](04-client-channel/02-name-resolution.md): resolver API,
  resolver results, `dns`/`unix`/`unix-abstract`/`vsock`/`ipv4`/`ipv6`
  resolvers
- [4.3 Service Config](04-client-channel/03-service-config.md)
- [4.4 Per-call Configuration and Call Flow](04-client-channel/04-call-dispatch.md)
- [4.5 Load Balancing](04-client-channel/05-load-balancing.md): LB policy, helper,
  picker, and subchannel APIs; state aggregation; backend metrics consumption
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
  - xDS-specific policies: see [xDS LB Policies](09-xds/05-lb-policies.md)
- [4.6 Subchannels and Connections](04-client-channel/06-subchannels.md):
  connection backoff, MAX_CONCURRENT_STREAMS connection scaling,
  connection-scoped watchers and streams (used by health checking and ORCA)
- [4.7 HTTP CONNECT Proxy Support](04-client-channel/07-proxy.md)
- [4.8 Client-side Health Checking](04-client-channel/08-health-checking.md)
- [4.9 Client-side Backend Metrics (ORCA)](04-client-channel/09-backend-metrics.md):
  per-call and out-of-band reports
- [4.10 Retries and Hedging](04-client-channel/10-retries.md)

### [5. Server](05-server/README.md)

### [6. Security](06-security/README.md)
Security model, channel and call credentials, security levels, AuthContext.
- [6.1 TLS](06-security/01-tls.md): certificate providers, revocation, SPIFFE,
  private key offloading, key exchange groups, authority checks
- [6.2 Call Credentials](06-security/02-call-credentials.md)
- [6.3 Authorization](06-security/03-authorization.md): RBAC engine, gRPC
  authorization policy, audit logging

### [7. Standard Services and Admin Interface](07-services/README.md)
- [7.1 Health Service](07-services/01-health.md)
- [7.2 Server Reflection](07-services/02-reflection.md)
- [7.3 Backend Metrics (ORCA)](07-services/03-orca.md)
- [7.4 Admin Interface](07-services/04-admin.md)

### [8. Observability](08-observability/README.md)
- [8.1 Instrumentation Architecture](08-observability/01-instrumentation.md)
- [8.2 Metrics Framework and OpenTelemetry Plugin](08-observability/02-metrics-framework.md)
- [8.3 Metric Catalog](08-observability/03-metrics.md)
- [8.4 Tracing](08-observability/04-tracing.md)
- [8.5 Channelz](08-observability/05-channelz.md)
- [8.6 Binary Logging](08-observability/06-binary-logging.md)

### [9. xDS / Proxyless Service Mesh Support](09-xds/README.md)
Overview, architecture, design principles, client and server features.
- [9.1 Bootstrap](09-xds/01-bootstrap.md)
- [9.2 XdsClient](09-xds/02-xds-client.md): transport, subscriptions, federation,
  caching, error handling, fallback
- 9.3 Resources and Validation
  - [9.3.1 Common Types](09-xds/03-resources/01-common-types.md)
  - [9.3.2 Listener](09-xds/03-resources/02-listener.md)
  - [9.3.3 RouteConfiguration](09-xds/03-resources/03-route-configuration.md)
  - [9.3.4 Cluster](09-xds/03-resources/04-cluster.md)
  - [9.3.5 ClusterLoadAssignment and LbEndpointCollection](09-xds/03-resources/05-endpoint.md)
- [9.4 Client Data Plane](09-xds/04-client.md): `xds` resolver, dependency
  management, routing
- [9.5 xDS LB Policies](09-xds/05-lb-policies.md): LB policy tree and the xDS
  LB policy registry
  - [`xds_cluster_manager`](09-xds/lb-policies/xds_cluster_manager.md)
  - [`cds`](09-xds/lb-policies/cds.md)
  - [`xds_cluster_impl`](09-xds/lb-policies/xds_cluster_impl.md)
  - [`xds_override_host`](09-xds/lb-policies/xds_override_host.md)
  - [`xds_wrr_locality`](09-xds/lb-policies/xds_wrr_locality.md)
- [9.6 xDS HTTP Filters](09-xds/06-http-filters.md): router, fault injection,
  RBAC, stateful session affinity, GCP authentication
- [9.7 xDS-Enabled Servers](09-xds/07-server.md)
- [9.8 xDS Security](09-xds/08-security.md)
- [9.9 Load Reporting (LRS)](09-xds/09-load-reporting.md)
- [9.10 Client Status Discovery Service (CSDS)](09-xds/10-csds.md)

### Appendices
- [A. Reserved Metadata Keys](appendices/a-metadata-keys.md)
- [B. Environment Variables](appendices/b-environment-variables.md)
- [C. Protocol Buffer and JSON Schema Index](appendices/c-schemas.md)
- [D. gRFC Traceability Matrix](appendices/d-traceability.md)
- [E. Historical and Superseded Behavior](appendices/e-historical.md)
- [F. Conformance and Interop Tests](appendices/f-conformance.md)
- [G. Glossary](appendices/g-glossary.md)
