> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 9.4.2 Listener (Client Side)

<!-- Sources: A27, A31, A36, A39, A41, A47, A88, doc/grpc_xds_features.md -->

> **Introduced by:** [gRFC A27: xDS-Based Global Load Balancing](https://github.com/grpc/proposal/blob/master/A27-xds-global-load-balancing.md)

The `envoy.config.listener.v3.Listener` resource is the root of a gRPC
client's xDS configuration. The `xds` resolver subscribes to the Listener
whose name is derived from the channel's target (see
[Client Data Plane](../05-client.md)). The Listener tells the client how to
get its routing configuration and which xDS HTTP filters to apply to each RPC.
(gRPC applies the behavior of each xDS HTTP filter per RPC, for example
through interceptors; this specification does not prescribe the mechanism.)

The same resource type is used by xDS-enabled servers. Server ("socket")
Listeners are validated under the rules in
[xDS-Enabled Servers](../08-server.md). This section covers client
("API") Listeners and the `HttpConnectionManager` they contain.

## 1. Listener Kinds

A Listener resource is classified when it is validated:

| Condition | Kind | Validation |
| --- | --- | --- |
| `api_listener` is set | API listener (client) | This section. `address` and all other Listener fields are ignored. |
| `api_listener` is unset and `address` is set | Socket listener (server) | [xDS-Enabled Servers](../08-server.md) |
| neither is set | invalid | The resource is rejected. |

Because Listener resources are validated without knowing who subscribed to
them, a socket listener that passes server-side validation is a valid
resource, even if a client channel subscribed to it. When the `xds` resolver
receives a valid Listener that is not an API listener, it MUST treat this as
an error for the channel (for example "not an API listener"), handled like any
other error that leaves the client without a usable Listener (see
[Client Data Plane](../05-client.md)). The resource is not NACKed.

## 2. API Listener

For an API listener:

- `api_listener.api_listener` is an `Any` ([Extensions: `google.protobuf.Any` and `TypedStruct`](01-common-types.md#2-extensions-googleprotobufany-and-typedstruct) in
  [Common Types](01-common-types.md)). It MUST be present, and its type name MUST
  be
  `envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager`.
  Any other type is rejected.
- The value MUST be a serialized `HttpConnectionManager` protobuf. A
  `TypedStruct`-wrapped value, or a value that cannot be parsed, is rejected.
- The `HttpConnectionManager` is validated as described below.

All other `Listener` fields (`address`, `filter_chains`, `listener_filters`,
`use_original_dst`, and so on) are ignored for an API listener.

## 3. `HttpConnectionManager`

`envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager`
fields read by the client:

| Field | Rule |
| --- | --- |
| `rds` | One of `rds` or `route_config` MUST be set (see [Route Configuration Source](#4-route-configuration-source)). If `rds` is set, `rds.config_source` MUST be present and have `ads` or `self` set. `rds.route_config_name` is the name of the `RouteConfiguration` resource to fetch. |
| `route_config` | An inline `RouteConfiguration`, validated exactly like an RDS resource (see [RouteConfiguration](03-route-configuration.md)). Errors in it reject the Listener. |
| `scoped_routes` | Not supported. If the route specifier is neither `rds` nor `route_config`, the resource is rejected. |
| `http_filters` | The ordered list of xDS HTTP filters. Validated as specified in [xDS HTTP Filters](../07-http-filters.md): each filter needs a non-empty name that is unique in the list; an unsupported filter type, or a filter that does not support clients, is rejected unless `is_optional` is true (then the filter is skipped); filter configs are validated by the filter implementation; at least one filter must remain; the last filter must be terminal (the router) and no other filter may be terminal. |
| `common_http_protocol_options.max_stream_duration` | Optional `Duration` ([`google.protobuf.Duration`](01-common-types.md#4-googleprotobufduration)). The default maximum RPC duration for routes that do not set their own `RouteAction.max_stream_duration` (see [RouteConfiguration](03-route-configuration.md) and [Client Data Plane](../05-client.md)). |
| `xff_num_trusted_hops` | MUST be zero. Otherwise the resource is rejected. |
| `original_ip_detection_extensions` | MUST be empty. Otherwise the resource is rejected. |

The `xff_num_trusted_hops` and `original_ip_detection_extensions` rules let
gRPC treat the RBAC fields `remote_ip` and `direct_remote_ip` as the same
thing. They apply to client and server Listeners alike.

All other `HttpConnectionManager` fields are ignored. This includes
`codec_type`, `stat_prefix`, `tracing`, `http2_protocol_options`, and every
other field of `common_http_protocol_options` (for example `idle_timeout`).

## 4. Route Configuration Source

The HCM gives the route configuration either by reference or inline:

- **By reference (`rds`).** The client subscribes to the `RouteConfiguration`
  named by `rds.route_config_name` on the same xDS server and authority rules
  as any resource (see [XdsClient](../03-xds-client.md)). If a later Listener
  update changes the name, the client stops watching the old name and starts
  watching the new one.
- **Inline (`route_config`).** The route configuration is part of the
  Listener resource. It is validated when the Listener is validated, and
  `trusted_xds_server` checks (for example for
  `RouteAction.auto_host_rewrite`) use the xDS server the Listener came from.

How the selected virtual host and routes are used is specified in
[Client Data Plane](../05-client.md).

## 5. Parsed Resource

A valid API listener produces:

```
ApiListener {
  http_connection_manager: HttpConnectionManager {
    // Exactly one of:
    route_config_name: string            // from rds.route_config_name
    route_config: RouteConfiguration     // parsed inline route_config ("RouteConfiguration")

    // From common_http_protocol_options.max_stream_duration; absent if unset.
    http_max_stream_duration: optional Duration

    // In list order; optional filters that were skipped are omitted.
    http_filters: list of HttpFilter {
      name: string                       // HttpFilter.name
      config_type: string                // filter config proto type name
      config: <filter-specific parsed config>
    }
  }
}
```

A socket listener produces the server-side parsed form defined in
[xDS-Enabled Servers](../08-server.md).

## 6. API Requirements

No public API is needed for client Listener handling. The Listener name the
client subscribes to is derived from the channel target and the bootstrap
configuration (see [Bootstrap](../02-bootstrap.md) and
[Client Data Plane](../05-client.md)).
