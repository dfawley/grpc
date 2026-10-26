> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4. Client Channel

<!-- Sources: doc/load-balancing.md, doc/naming.md, doc/service_config.md, A31, A61 -->

From the application's point of view, a gRPC client **channel** is a logical
connection to a named service. The application identifies that service with a
**target** URI. The channel handles name resolution, connection management,
load balancing, per-method configuration, and retries, so the application can
create a channel and start sending RPCs on it right away. The channel MAY hold
zero, one, or many transport connections at any time, and the application
MUST NOT assume any relationship between RPCs and connections.

This section specifies the client channel's architecture, its public API, and
the internal plugin APIs between the channel and its components. It applies
to all gRPC implementations.

## Contents

- [4.1 Client Channel Architecture](01-architecture.md): components, architecture, connection establishment walkthrough
- [4.2 Channel](02-channel.md): creation, targets, authority, connectivity state, idleness, shutdown
- [4.3 Name Resolution](03-name-resolution.md): resolver registry, resolver API, resolver results, built-in resolvers
- [4.4 Service Config](04-service-config.md): format, delivery, validation, field reference
- [4.5 Per-call Configuration and Call Flow](05-call-dispatch.md): ConfigSelector, RPC dispatch
- [4.6 Load Balancing](06-load-balancing.md): LB policy, helper, picker, and subchannel APIs; state aggregation; policy switching; backend metrics consumption
  - [`pick_first`](lb-policies/pick_first.md)
  - [`round_robin`](lb-policies/round_robin.md)
  - [`weighted_round_robin`](lb-policies/weighted_round_robin.md)
  - [`least_request`](lb-policies/least_request.md)
  - [`ring_hash`](lb-policies/ring_hash.md)
  - [`random_subsetting`](lb-policies/random_subsetting.md)
  - [`outlier_detection`](lb-policies/outlier_detection.md)
  - [`priority`](lb-policies/priority.md)
  - [`weighted_target`](lb-policies/weighted_target.md)
  - [`rls`](lb-policies/rls.md)
- [4.7 Subchannels and Connections](07-subchannels.md): connection backoff, MAX_CONCURRENT_STREAMS connection scaling, connection-scoped watchers and streams
- 4.8 Client Transports
  - [4.8.1 Client Transport Model](08-transports/01-transport-model.md): what any client transport provides to the subchannel
  - [4.8.2 HTTP/2 Client Transport](08-transports/02-http2.md): settings, stream limits, flow control, keepalive, GOAWAY handling
  - [4.8.3 HTTP/3 Client Transport](08-transports/03-http3.md)
  - [4.8.4 In-Process Client Transport](08-transports/04-in-process.md)
- [4.9 HTTP CONNECT Proxy Support](09-proxy.md): proxy mapping and the CONNECT handshake
- [4.10 Client-Side Health Checking](10-health-checking.md): health checking using the health service
- [4.11 Client-Side Backend Metrics (ORCA)](11-backend-metrics.md): per-call and out-of-band backend metric reports
- [4.12 Retries and Hedging](12-retries.md): retry and hedging policies, throttling, transparent retries
