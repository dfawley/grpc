# gRPC Spec: Optionality Notes

Working notes for the [gRPC specification](spec/README.md).

The spec does not say which features are optional. Apart from the wire
protocol, almost everything in gRPC is optional in practice. This file records
features that we have noticed are missing from, or only partly provided by,
some implementations. If we later decide to define conformance levels or
mark features as optional, these notes are the starting point.

Format: `- <feature> (<spec section link>): <observation>`

## Core RPC semantics and API

- Per-call authority override ([Core RPC Semantics](spec/02-rpc-semantics/README.md), [Channel](spec/04-client-channel/02-channel.md)): doc/internationalization.md and gRFC A81 note that not every implementation exposes a per-call authority override.
- Compression algorithms ([Core RPC Semantics](spec/02-rpc-semantics/README.md)): the set of supported algorithms varies; `identity` and `gzip` are universal, `deflate` is not everywhere, and `snappy` appears only in the PROTOCOL-HTTP2.md grammar.

## Wire protocol

- Configurable `MAX_PING_STRIKES` ([HTTP/2 Server Transport: Ping Enforcement](spec/05-server/02-transports/02-http2.md#72-ping-enforcement)): only C++ makes it configurable; Java and Go hardcode 2.
- Server-side `TCP_USER_TIMEOUT` ([HTTP/2 Server Transport: TCP_USER_TIMEOUT](spec/05-server/02-transports/02-http2.md#73-tcp_user_timeout)): not implemented in Java. Java sets it only on client channels (Netty epoll, keepalive enabled).
- Rejecting unknown content-subtypes with `UNIMPLEMENTED` ([Core RPC Semantics](spec/02-rpc-semantics/README.md), [Server](spec/05-server/README.md)): not implemented in Java, Go, or C++; all three ignore the subtype and decode with the method's codec.
- Validating `grpc-status-details-bin` against `grpc-status` ([gRPC over HTTP/2](spec/03-wire-protocol/01-http2.md)): not implemented in C++; Java checks only in its protobuf status helper, not in the core library.

## Client channel

- Reading the channel's current service config ([Service Config](spec/04-client-channel/04-service-config.md)), per-channel resolver factories ([Name Resolution](spec/04-client-channel/03-name-resolution.md)), and waiting for a connectivity state with a deadline ([Channel](spec/04-client-channel/02-channel.md)): the drafts made these SHOULD/MAY; availability not yet surveyed.
- Changing the default target scheme process-wide ([Channel](spec/04-client-channel/02-channel.md)): not available in every implementation.
- Resetting connection backoff from the channel API ([Channel](spec/04-client-channel/02-channel.md)): was SHOULD in older docs; availability not yet surveyed.
- Separate default-LB-policy channel option ([Channel](spec/04-client-channel/02-channel.md)): some implementations have one; the spec uses the default service config instead.
- `ipv4:` / `ipv6:` target schemes ([Name Resolution](spec/04-client-channel/03-name-resolution.md)): doc/naming.md describes them only for some implementations.
- Address-mapping proxy environment variables (a proxy address plus the address ranges that use it) ([HTTP CONNECT Proxy Support](spec/04-client-channel/09-proxy.md)): provided by some implementations only; not in the spec.
- Private subchannel pool option ([Subchannels and Connections](spec/04-client-channel/07-subchannels.md)): only meaningful for implementations that share subchannels between channels.
- Per-channel retry buffer limit ([Retries and Hedging](spec/04-client-channel/12-retries.md#71-buffer-limits)): not implemented in Go or C++. Both have only a per-RPC limit (256 KiB default); Java has both.
- `connectionScaling` service config field ([Service Config](spec/04-client-channel/04-service-config.md)): not implemented in Java or Go (the field is ignored as unknown). None of the three implements the xDS `per_host_thresholds` max_connections part.
- `unix-abstract:` target scheme ([Name Resolution](spec/04-client-channel/03-name-resolution.md)): not implemented in Java.
- `vsock:` target scheme ([Name Resolution](spec/04-client-channel/03-name-resolution.md)): not implemented in Java or Go.
- Resolver-level option to disable service config lookup ([Name Resolution](spec/04-client-channel/03-name-resolution.md#3-channel-handling-of-resolver-results)): Java and Go apply the option at the channel level. The channel discards the service config (and config selector) from every resolver, which breaks xDS when the option is set. Only C++ limits it to resolvers that fetch a published config (DNS TXT).
- DNS-server authority in `dns:` targets ([Name Resolution](spec/04-client-channel/03-name-resolution.md)): not implemented in Java (silently ignored); C++ supports it only with c-ares (literal `IP:port`), and the native resolver ignores it.
- DNS TXT service config lookup ([Name Resolution](spec/04-client-channel/03-name-resolution.md)): off by default in Java and C++ (enabled by default in Go).
- Proxy environment variables ([HTTP CONNECT Proxy Support](spec/04-client-channel/09-proxy.md)): not implemented in Java, which uses the platform proxy selector instead. Go reads only `HTTPS_PROXY`/`https_proxy` and `NO_PROXY`/`no_proxy`.
- In-process transport ([In-Process Client Transport](spec/04-client-channel/08-transports/04-in-process.md), [In-Process Server Transport](spec/05-server/02-transports/04-in-process.md)): not implemented in Go (`test/bufconn` is an in-memory connection used with the HTTP/2 transport, not a separate transport).

## Server

- Server-side response cardinality check ([Server](spec/05-server/01-server.md#33-status-and-trailers)): not implemented in Go (a client-streaming handler can end with OK and no response) or C++ (APIs always send a response with OK; the generic API has no check). Java detects it but resets the stream instead of sending INTERNAL.

## Security

- Audit logging for authorization ([Authorization](spec/06-security/04-authorization.md), [xDS HTTP Filters](spec/09-xds/07-http-filters.md)): not implemented in Java. Neither the gRPC authorization policy `audit_logging_options` nor xDS RBAC `audit_logging_options` is supported, and there is no audit logger API.

## Standard services

- Client-side reflection descriptor utility ([Server Reflection](spec/07-services/02-reflection.md)): was SHOULD in the draft; availability not yet surveyed.
- Health status manager operations ([Health Service](spec/07-services/01-health.md)): "remove a service" and "leave shutdown" are not available in every implementation.
- Health `List` RPC ([Health Service](spec/07-services/01-health.md)): not implemented in Java, C++. Go implements it with the 100-entry limit.
- ORCA per-server recorder `setAllUtilization` bulk operation ([Backend Metrics (ORCA)](spec/07-services/03-orca.md#3-per-server-recorder)): not implemented in Go (only per-name set/delete).

## Observability

- Disabling Channelz tracking per channel or server ([Channelz](spec/08-observability/06-channelz.md)): was MAY in the draft; availability not yet surveyed.
- Custom binary log sink API ([Binary Logging](spec/08-observability/07-binary-logging.md)): was SHOULD in the draft; availability not yet surveyed.
- Binary logging ([Binary Logging](spec/08-observability/07-binary-logging.md)): not implemented in C++. Java enables it only through code (no automatic env-var activation).
- Stats plugin scoping ([Metrics Framework and OpenTelemetry Plugin](spec/08-observability/03-metrics-framework.md)): implementations provide a global scope predicate, per-channel registration, or both; the spec describes both.
- `grpc.client.call.duration` per-call metric ([Metric Catalog](spec/08-observability/04-metrics.md)): not implemented in C++ (its OpenTelemetry plugin's default set has the other 8 per-call metrics).
- Retry metrics ([Metric Catalog](spec/08-observability/04-metrics.md)): not implemented in Go. `grpc.client.call.hedges` is also not implemented in C++.
- Generic method attribute predicate ([Metrics Framework and OpenTelemetry Plugin](spec/08-observability/03-metrics-framework.md)): not implemented in Java. Go has one on the server only, applied to all methods.

## xDS

- Programmatic bootstrap configuration ([Bootstrap](spec/09-xds/02-bootstrap.md)): was SHOULD in the draft; availability not yet surveyed.
- Stateful session affinity xDS HTTP filter ([xDS HTTP Filters](spec/09-xds/07-http-filters.md)): not implemented in Java or Go.
- HttpFilter.disabled / FilterConfig.disabled ([xDS HTTP Filters](spec/09-xds/07-http-filters.md)): not in the spec; honored by C++, only behind experimental guards in Go, not implemented in Java.
- LbEndpointCollection (LEDS list collections) and `leds_cluster_locality_config` ([ClusterLoadAssignment and LbEndpointCollection](spec/09-xds/04-resources/05-endpoint.md)): not implemented in Java, Go, or C++. Behavior (validation, duplicate-address scope, locality proxy-address fallback) comes from gRFC A95 only.
- `xds_override_host` LB policy and stateful session affinity ([`xds_override_host` LB Policy](spec/09-xds/lb-policies/xds_override_host.md)): not implemented in Java and Go (only C++ registers `xds_override_host_experimental`).
- `VirtualHost.retry_policy` ([RouteConfiguration](spec/09-xds/04-resources/03-route-configuration.md)): not implemented in Java. Only the route-level `RouteAction.retry_policy` is parsed there, so a virtual-host retry policy is ignored.
- `xds.endpoint.supports_lb_endpoint_collection` client feature ([xDS / Proxyless Service Mesh Support](spec/09-xds/01-architecture.md#3-client-features)): not sent by Java, Go, or C++ (goes with the unimplemented LbEndpointCollection support from A95).
- `fail_on_data_errors` and `resource_timer_is_transient_error` server features and the A88 data-error handling ([Bootstrap](spec/09-xds/02-bootstrap.md#5-server-features)): not implemented in Go. Go still gives `ignore_resource_deletion` its older effect.
- Rejecting an unset `weighted_clusters` weight ([RouteConfiguration](spec/09-xds/04-resources/03-route-configuration.md)): SHOULD per the spec (matches Envoy); C++ rejects, but Java and Go treat an unset weight as 0. Known, allowed deviation.
