# gRPC Specification

This directory contains the specification of gRPC's cross-language behavior:
the wire protocol, the client channel, the server, security, the standard gRPC
services, observability, and xDS (proxyless service mesh) support. It describes
the *current* behavior that all gRPC implementations are expected to provide.

See [Introduction and Conventions](00-introduction.md) for scope,
requirements language, and how experimental features are marked.

## Table of Contents

### [Introduction and Conventions](00-introduction.md)

### [Architecture Overview](01-architecture.md)

### [Core RPC Semantics](02-rpc-semantics.md)
Channels and servers; methods, services, and RPC types; calls and
cancellation; flow control; metadata; deadlines; authority; status codes;
ordering of status and messages; message size limits; compression;
wait-for-ready; interceptors; codecs; API requirements.

### [Wire Protocol](03-wire-protocol/README.md)
- [gRPC over HTTP/2](03-wire-protocol/http2.md)
- [HTTP/2 Transport Behavior](03-wire-protocol/http2-transport.md):
  settings, flow control, keepalive, server connection management
- [True Binary Metadata](03-wire-protocol/true-binary-metadata.md)
- [gRPC over HTTP/3](03-wire-protocol/http3.md)
- [Protocol Buffers Mapping](03-wire-protocol/protobuf.md)

### [Client Channel](04-client-channel/README.md)
- [Channel](04-client-channel/channel.md): creation, targets, authority,
  connectivity state, idleness
- [Name Resolution](04-client-channel/name-resolution.md): resolver API,
  resolver results, `dns`/`unix`/`unix-abstract`/`vsock`/`ipv4`/`ipv6`
  resolvers
- [Service Config](04-client-channel/service-config.md)
- [Per-call Configuration and Call Flow](04-client-channel/call-dispatch.md)
- [Load Balancing](04-client-channel/load-balancing.md): LB policy, helper,
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
  - xDS-specific policies: see [xDS LB Policies](09-xds/lb-policies.md)
- [Subchannels and Connections](04-client-channel/subchannels.md):
  connection backoff, MAX_CONCURRENT_STREAMS connection scaling,
  connection-scoped watchers and streams (used by health checking and ORCA)
- [HTTP CONNECT Proxy Support](04-client-channel/proxy.md)
- [Client-side Health Checking](04-client-channel/health-checking.md)
- [Client-side Backend Metrics (ORCA)](04-client-channel/backend-metrics.md):
  per-call and out-of-band reports
- [Retries and Hedging](04-client-channel/retries.md)

### [Server](05-server.md)

### [Security](06-security/README.md)
Security model, channel and call credentials, security levels, AuthContext.
- [TLS](06-security/tls.md): certificate providers, revocation, SPIFFE,
  private key offloading, key exchange groups, authority checks
- [Call Credentials](06-security/call-credentials.md)
- [Authorization](06-security/authorization.md): RBAC engine, gRPC
  authorization policy, audit logging

### [Standard Services and Admin Interface](07-services/README.md)
- [Health Service](07-services/health.md)
- [Server Reflection](07-services/reflection.md)
- [Backend Metrics (ORCA)](07-services/orca.md)
- [Admin Interface](07-services/admin.md)

### [Observability](08-observability/README.md)
- [Instrumentation Architecture](08-observability/instrumentation.md)
- [Metrics Framework and OpenTelemetry Plugin](08-observability/metrics-framework.md)
- [Metric Catalog](08-observability/metrics.md)
- [Tracing](08-observability/tracing.md)
- [Channelz](08-observability/channelz.md)
- [Binary Logging](08-observability/binary-logging.md)

### [xDS / Proxyless Service Mesh Support](09-xds/README.md)
Overview, architecture, design principles, client and server features.
- [Bootstrap](09-xds/bootstrap.md)
- [XdsClient](09-xds/xds-client.md): transport, subscriptions, federation,
  caching, error handling, fallback
- Resources and Validation
  - [Common Types](09-xds/resources/common-types.md)
  - [Listener](09-xds/resources/listener.md)
  - [RouteConfiguration](09-xds/resources/route-configuration.md)
  - [Cluster](09-xds/resources/cluster.md)
  - [ClusterLoadAssignment and LbEndpointCollection](09-xds/resources/endpoint.md)
- [Client Data Plane](09-xds/client.md): `xds` resolver, dependency
  management, routing
- [xDS LB Policies](09-xds/lb-policies.md): LB policy tree and the xDS
  LB policy registry
  - [`xds_cluster_manager`](09-xds/lb-policies/xds_cluster_manager.md)
  - [`cds`](09-xds/lb-policies/cds.md)
  - [`xds_cluster_impl`](09-xds/lb-policies/xds_cluster_impl.md)
  - [`xds_override_host`](09-xds/lb-policies/xds_override_host.md)
  - [`xds_wrr_locality`](09-xds/lb-policies/xds_wrr_locality.md)
- [xDS HTTP Filters](09-xds/http-filters.md): router, fault injection,
  RBAC, stateful session affinity, GCP authentication
- [xDS-Enabled Servers](09-xds/server.md)
- [xDS Security](09-xds/security.md)
- [Load Reporting (LRS)](09-xds/load-reporting.md)
- [Client Status Discovery Service (CSDS)](09-xds/csds.md)

### Appendices
- [A. Reserved Metadata Keys](appendices/a-metadata-keys.md)
- [B. Environment Variables](appendices/b-environment-variables.md)
- [C. Protocol Buffer and JSON Schema Index](appendices/c-schemas.md)
- [D. gRFC Traceability Matrix](appendices/d-traceability.md)
- [E. Historical and Superseded Behavior](appendices/e-historical.md)
- [F. Conformance and Interop Tests](appendices/f-conformance.md)
- [G. Glossary](appendices/g-glossary.md)
