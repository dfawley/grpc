> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# Appendix C. Protocol Buffer and JSON Schema Index

<!-- Sources: doc/spec/** (all sections, by grep of proto/type references), grpc-proto grpc/**, Envoy API (envoyproxy/envoy api/), cncf/xds API -->

This appendix lists every protocol buffer file, message, and JSON schema that
this specification refers to, and links each one to the section that defines
how gRPC uses it. The linked sections are normative. This index is not.

Paths are repository-relative:

- **grpc-proto**: `grpc/...` files in the `grpc/grpc-proto` repository.
- **Envoy API**: `envoy/...` files under `api/` in the `envoyproxy/envoy`
  repository (also mirrored as `envoyproxy/data-plane-api`).
- **cncf/xds**: `xds/...` and `udpa/...` files in the `cncf/xds` repository.
- **googleapis**: `google/rpc/...` files in the `googleapis/googleapis`
  repository. `google/protobuf/...` well-known types ship with Protocol
  Buffers.

When a JSON form of a protobuf message is used, it follows the standard
protobuf JSON mapping (see [Introduction and Conventions](../00-introduction/README.md), 0.7).

## C.1 gRPC Protocol Buffer Definitions (grpc-proto)

| File | Messages / services | Used for | Defined in |
| --- | --- | --- | --- |
| `grpc/service_config/service_config.proto` | `ServiceConfig`, `MethodConfig` (with `Name`, `RetryPolicy`, `HedgingPolicy`), `RetryThrottlingPolicy`, `HealthCheckConfig`, `ConnectionScaling`, `LoadBalancingConfig` | Service config schema. The JSON form is the service config. | [Service Config](../04-client-channel/04-service-config.md); [Retries and Hedging](../04-client-channel/12-retries.md); [Client-Side Health Checking](../04-client-channel/10-health-checking.md); [Subchannels and Connections](../04-client-channel/07-subchannels.md) ([Subchannels and Connections: MAX_CONCURRENT_STREAMS Connection Scaling](../04-client-channel/07-subchannels.md#8-max_concurrent_streams-connection-scaling)) |
| `grpc/service_config/service_config.proto` | `PickFirstConfig`, `RoundRobinConfig`, `WeightedRoundRobinLbConfig`, `LeastRequestLocalityLoadBalancingPolicyConfig`, `RingHashLoadBalancingConfig`, `RandomSubsettingLoadBalancingConfig`, `OutlierDetectionLoadBalancingConfig`, `PriorityLoadBalancingPolicyConfig`, `WeightedTargetLoadBalancingPolicyConfig` | Configuration of the general-purpose LB policies | [Load Balancing](../04-client-channel/06-load-balancing.md) and the [policy documents](../04-client-channel/lb-policies/pick_first.md) under `04-client-channel/lb-policies/` |
| `grpc/service_config/service_config.proto` | `XdsClusterManagerLoadBalancingPolicyConfig`, `CdsConfig`, `XdsClusterImplLoadBalancingPolicyConfig`, `OverrideHostLoadBalancingPolicyConfig`, `XdsWrrLocalityLoadBalancingPolicyConfig` | Configuration of the xDS LB policies | [xDS LB Policies](../09-xds/06-lb-policies.md) |
| `grpc/service_config/service_config.proto` | `RlsLoadBalancingPolicyConfig` | Configuration of the `rls` LB policy | [`rls`](../04-client-channel/lb-policies/rls.md) |
| `grpc/lookup/v1/rls_config.proto` | `RouteLookupConfig`, `GrpcKeyBuilder`, `NameMatcher`, `HttpKeyBuilder` (ignored), `RouteLookupClusterSpecifier` | RLS policy configuration; the xDS RLS cluster specifier plugin | [`rls`](../04-client-channel/lb-policies/rls.md); [RouteConfiguration](../09-xds/04-resources/03-route-configuration.md) ([RLS Cluster Specifier Plugin](../09-xds/04-resources/03-route-configuration.md#53-rls-cluster-specifier-plugin)) |
| `grpc/lookup/v1/rls.proto` | `grpc.lookup.v1.RouteLookupService` (`RouteLookup`), `RouteLookupRequest`, `RouteLookupResponse` | Lookups sent by the `rls` policy to its lookup server | [`rls`](../04-client-channel/lb-policies/rls.md) ([`RouteLookup` RPC](../04-client-channel/lb-policies/rls.md#routelookup-rpc)) |
| `grpc/health/v1/health.proto` | `grpc.health.v1.Health` (`Check`, `Watch`, `List`), `HealthCheckRequest`, `HealthCheckResponse`, `HealthListRequest`, `HealthListResponse` | Health service and client-side health checking | [Health Service](../07-services/01-health.md); [Client-Side Health Checking](../04-client-channel/10-health-checking.md) |
| `grpc/reflection/v1/reflection.proto` | `grpc.reflection.v1.ServerReflection` (`ServerReflectionInfo`) and its request/response messages | Server reflection | [Server Reflection](../07-services/02-reflection.md) |
| `grpc/reflection/v1alpha/reflection.proto` | `grpc.reflection.v1alpha.ServerReflection` | Deprecated reflection version, wire-identical to v1. Servers SHOULD still serve it. | [Server Reflection](../07-services/02-reflection.md) ([Server Reflection: Versions](../07-services/02-reflection.md#6-versions)) |
| `grpc/channelz/v1/channelz.proto` | `grpc.channelz.v1.Channelz`, `Channel`, `Subchannel`, `Server`, `Socket`, `ChannelTrace`, `SocketData`, `Security`, and others | Channelz service and data model | [Channelz](../08-observability/06-channelz.md); [Admin Interface](../07-services/04-admin.md) |
| `grpc/binlog/v1/binarylog.proto` | `GrpcLogEntry`, `ClientHeader`, `ServerHeader`, `Trailer`, `Message`, `Metadata`, `MetadataEntry`, `Address` | Binary log record format | [Binary Logging](../08-observability/07-binary-logging.md) |

## C.2 Other Protocol Buffer Definitions Used by the Core Protocol

| File | Messages | Used for | Defined in |
| --- | --- | --- | --- |
| `google/rpc/status.proto` (googleapis) | `google.rpc.Status` | Value of `grpc-status-details-bin` (rich error details) | [Protocol Buffers Mapping](../03-wire-protocol/04-protobuf.md) ([Protocol Buffers Mapping: Rich Error Details](../03-wire-protocol/04-protobuf.md#4-rich-error-details)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Rich Error Details](../02-rpc-semantics/README.md#105-rich-error-details)) |
| `google/rpc/code.proto` (googleapis) | `google.rpc.Code` | Status code numbering, the same as gRPC status codes. Status codes in the service config JSON. | [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Status Codes](../02-rpc-semantics/README.md#101-status-codes)); [Service Config](../04-client-channel/04-service-config.md) ([Service Config: Format](../04-client-channel/04-service-config.md#1-format)); [Protocol Buffers Mapping](../03-wire-protocol/04-protobuf.md) ([Protocol Buffers Mapping: Rich Error Details](../03-wire-protocol/04-protobuf.md#4-rich-error-details)) |
| `google/rpc/error_details.proto` (googleapis) | Standard error detail messages | Recommended payloads for `google.rpc.Status.details` | [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Rich Error Details](../02-rpc-semantics/README.md#105-rich-error-details)) |
| `google/protobuf/descriptor.proto` | `FileDescriptorProto` | Payload of reflection responses | [Server Reflection](../07-services/02-reflection.md) |
| `google/protobuf/duration.proto`, `struct.proto`, `wrappers.proto`, `any.proto` | `Duration`, `Struct`, `BoolValue`, `UInt32Value`, `StringValue`, `Any` | Used throughout the service config and xDS resources | [Common Types](../09-xds/04-resources/01-common-types.md); [Service Config](../04-client-channel/04-service-config.md) |

## C.3 Backend Metrics (ORCA, cncf/xds)

| File | Messages / services | Used for | Defined in |
| --- | --- | --- | --- |
| `xds/data/orca/v3/orca_load_report.proto` | `xds.data.orca.v3.OrcaLoadReport` | Per-request reports (`endpoint-load-metrics-bin` trailer) and OOB reports | [Backend Metrics (ORCA)](../07-services/03-orca.md); [Load Balancing](../04-client-channel/06-load-balancing.md) ([Load Balancing: Consuming Backend Metrics](../04-client-channel/06-load-balancing.md#13-consuming-backend-metrics)) |
| `xds/service/orca/v3/orca.proto` | `xds.service.orca.v3.OpenRcaService` (`StreamCoreMetrics`), `OrcaLoadReportRequest` | Out-of-band backend metric reporting | [Backend Metrics (ORCA)](../07-services/03-orca.md) ([Backend Metrics (ORCA): Out-of-Band Reporting](../07-services/03-orca.md#4-out-of-band-reporting)); [`weighted_round_robin`](../04-client-channel/lb-policies/weighted_round_robin.md) |

## C.4 xDS Transport Protocols

| File | Messages / services | Used for | Defined in |
| --- | --- | --- | --- |
| `envoy/service/discovery/v3/ads.proto`, `envoy/service/discovery/v3/discovery.proto` | `envoy.service.discovery.v3.AggregatedDiscoveryService` (`StreamAggregatedResources`), `DiscoveryRequest`, `DiscoveryResponse`, `Resource` | ADS (state-of-the-world variant) | [XdsClient](../09-xds/03-xds-client.md) ([XdsClient: ADS Stream](../09-xds/03-xds-client.md#4-ads-stream)) |
| `envoy/service/load_stats/v3/lrs.proto` | `envoy.service.load_stats.v3.LoadReportingService` (`StreamLoadStats`), `LoadStatsRequest`, `LoadStatsResponse` | LRS | [Load Reporting (LRS)](../09-xds/10-load-reporting.md) |
| `envoy/config/endpoint/v3/load_report.proto` | `ClusterStats`, `UpstreamLocalityStats`, `EndpointLoadMetricStats`, `UnnamedEndpointLoadMetricStats` | LRS report contents | [Load Reporting (LRS)](../09-xds/10-load-reporting.md) ([Load Reporting (LRS): LRS Stream Protocol](../09-xds/10-load-reporting.md#3-lrs-stream-protocol), [Load Reporting (LRS): Backend Metrics from ORCA](../09-xds/10-load-reporting.md#4-backend-metrics-from-orca)) |
| `envoy/service/status/v3/csds.proto` | `envoy.service.status.v3.ClientStatusDiscoveryService` (`FetchClientStatus`, `StreamClientStatus`), `ClientStatusRequest`, `ClientStatusResponse`, `ClientConfig`, `ClientConfig.GenericXdsConfig` | CSDS | [CSDS](../09-xds/11-csds.md); [Admin Interface](../07-services/04-admin.md) |
| `envoy/admin/v3/config_dump_shared.proto` | `envoy.admin.v3.ClientResourceStatus`, `UpdateFailureState` | Per-resource status in CSDS | [Client Status Discovery Service (CSDS)](../09-xds/11-csds.md) ([Client Status Discovery Service (CSDS): Response Contents](../09-xds/11-csds.md#3-response-contents)) |
| `envoy/config/core/v3/base.proto` | `Node`, `Locality`, `Metadata`, `RuntimeFractionalPercent` | Client identification (`node` in the bootstrap and in requests), localities, and metadata | [Bootstrap](../09-xds/02-bootstrap.md) ([Node Object](../09-xds/02-bootstrap.md#42-node-object)); [Common Types](../09-xds/04-resources/01-common-types.md) |

## C.5 xDS Resources (Envoy API)

Each resource type is listed with its main files and the documents that
define its handling.

- `envoy.config.listener.v3.Listener` (client: API listener). Main files: `envoy/config/listener/v3/listener.proto`, `api_listener.proto`. Defined in: [Listener](../09-xds/04-resources/02-listener.md).
- `envoy.config.listener.v3.Listener` (server: `FilterChain`, `FilterChainMatch`). Main files: `envoy/config/listener/v3/listener.proto`, `listener_components.proto`. Defined in: [xDS-Enabled Servers](../09-xds/08-server.md).
- `envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager`. Main files: `envoy/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto`. Defined in: [Listener (Client Side)](../09-xds/04-resources/02-listener.md); [xDS HTTP Filters](../09-xds/07-http-filters.md) ([xDS HTTP Filters: Top-Level Configuration (`HttpConnectionManager.http_filters`)](../09-xds/07-http-filters.md#3-top-level-configuration-httpconnectionmanagerhttp_filters)); [xDS-Enabled Servers](../09-xds/08-server.md).
- `envoy.config.route.v3.RouteConfiguration` (`VirtualHost`, `Route`, `RouteMatch`, `RouteAction`, `WeightedCluster`, `RetryPolicy`, `HashPolicy`, `HeaderMatcher`, `FilterConfig`, `ClusterSpecifierPlugin`). Main files: `envoy/config/route/v3/route.proto`, `route_components.proto`. Defined in: [RouteConfiguration](../09-xds/04-resources/03-route-configuration.md); [Common Types](../09-xds/04-resources/01-common-types.md) ([`HeaderMatcher`](../09-xds/04-resources/01-common-types.md#8-headermatcher)).
- `envoy.config.cluster.v3.Cluster` (`CircuitBreakers`, `OutlierDetection`, `LoadBalancingPolicy`). Main files: `envoy/config/cluster/v3/cluster.proto`, `circuit_breaker.proto`, `outlier_detection.proto`. Defined in: [Cluster](../09-xds/04-resources/04-cluster.md).
- `envoy.extensions.clusters.aggregate.v3.ClusterConfig`. Main files: `envoy/extensions/clusters/aggregate/v3/cluster.proto`. Defined in: [Cluster](../09-xds/04-resources/04-cluster.md) ([Aggregate Clusters](../09-xds/04-resources/04-cluster.md#13-aggregate-clusters)); [Client Data Plane](../09-xds/05-client.md) ([Aggregate cluster graph](../09-xds/05-client.md#23-aggregate-cluster-graph)).
- `envoy.extensions.upstreams.http.v3.HttpProtocolOptions`. Main files: `envoy/extensions/upstreams/http/v3/http_protocol_options.proto`. Defined in: [Cluster](../09-xds/04-resources/04-cluster.md) ([Upstream Connection Options](../09-xds/04-resources/04-cluster.md#8-upstream-connection-options)).
- `envoy.config.endpoint.v3.ClusterLoadAssignment` (`LocalityLbEndpoints`, `LbEndpoint`, `Endpoint`, `DropOverload`, `LedsClusterLocalityConfig`). Main files: `envoy/config/endpoint/v3/endpoint.proto`, `endpoint_components.proto`. Defined in: [ClusterLoadAssignment and LbEndpointCollection](../09-xds/04-resources/05-endpoint.md).
- `envoy.config.endpoint.v3.LbEndpointCollection`, with entries of type `xds.core.v3.CollectionEntry`. Main files: Envoy `envoy.config.endpoint.v3` package; `xds/core/v3/collection_entry.proto` (cncf/xds). Defined in: [ClusterLoadAssignment and LbEndpointCollection](../09-xds/04-resources/05-endpoint.md) ([LbEndpointCollection (LEDS List Collections)](../09-xds/04-resources/05-endpoint.md#7-lbendpointcollection-leds-list-collections)).

## C.6 Common xDS Types

| Type | File | Defined in |
| --- | --- | --- |
| `envoy.config.core.v3.ConfigSource` | `envoy/config/core/v3/config_source.proto` | [Common Types](../09-xds/04-resources/01-common-types.md) ([`ConfigSource`](../09-xds/04-resources/01-common-types.md#3-configsource)) |
| `envoy.config.core.v3.Address`, `SocketAddress` | `envoy/config/core/v3/address.proto` | [Common Types](../09-xds/04-resources/01-common-types.md) ([Addresses](../09-xds/04-resources/01-common-types.md#6-addresses)) |
| `envoy.config.core.v3.HealthStatus`, `HealthStatusSet` | `envoy/config/core/v3/health_check.proto` | [Common Types](../09-xds/04-resources/01-common-types.md) ([Health Status](../09-xds/04-resources/01-common-types.md#10-health-status)); [Cluster](../09-xds/04-resources/04-cluster.md) ([Override Host Status](../09-xds/04-resources/04-cluster.md#5-override-host-status)) |
| `envoy.config.core.v3.TypedExtensionConfig` | `envoy/config/core/v3/extension.proto` | [Common Types](../09-xds/04-resources/01-common-types.md) ([Extensions: `google.protobuf.Any` and `TypedStruct`](../09-xds/04-resources/01-common-types.md#2-extensions-googleprotobufany-and-typedstruct)) |
| `envoy.type.matcher.v3.StringMatcher`, `RegexMatcher`; `xds.type.matcher.v3.StringMatcher` | `envoy/type/matcher/v3/string.proto`, `regex.proto`; `xds/type/matcher/v3/string.proto` | [Common Types](../09-xds/04-resources/01-common-types.md) ([`StringMatcher`](../09-xds/04-resources/01-common-types.md#7-stringmatcher)) |
| `envoy.type.v3.FractionalPercent` | `envoy/type/v3/percent.proto` | [Common Types](../09-xds/04-resources/01-common-types.md) ([Fractional Percentages](../09-xds/04-resources/01-common-types.md#5-fractional-percentages)) |
| `xds.type.v3.TypedStruct`, `udpa.type.v1.TypedStruct` | `xds/type/v3/typed_struct.proto`, `udpa/type/v1/typed_struct.proto` (cncf/xds) | [Common Types](../09-xds/04-resources/01-common-types.md) ([Extensions: `google.protobuf.Any` and `TypedStruct`](../09-xds/04-resources/01-common-types.md#2-extensions-googleprotobufany-and-typedstruct)); [xDS LB Policies](../09-xds/06-lb-policies.md) ([`load_balancing_policy`](../09-xds/06-lb-policies.md#21-load_balancing_policy)) |
| Metadata types `envoy.extensions.filters.http.gcp_authn.v3.Audience` and `envoy.config.core.v3.Address`. Metadata keys `envoy.lb` (`Struct`) and `envoy.http11_proxy_transport_socket.proxy_address`. | see the respective files | [Common Types](../09-xds/04-resources/01-common-types.md) ([Metadata](../09-xds/04-resources/01-common-types.md#9-metadata)) |

## C.7 xDS Security Types

Each type is listed with its file and the documents that define its
handling.

- `envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext`. File: `envoy/extensions/transport_sockets/tls/v3/tls.proto`. Defined in: [xDS Security](../09-xds/09-security.md) ([xDS Security: Client Side: `UpstreamTlsContext`](../09-xds/09-security.md#2-client-side-upstreamtlscontext)).
- `envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext`. File: `envoy/extensions/transport_sockets/tls/v3/tls.proto`. Defined in: [xDS Security](../09-xds/09-security.md) ([xDS Security: Server Side: `DownstreamTlsContext`](../09-xds/09-security.md#7-server-side-downstreamtlscontext)).
- `CommonTlsContext`. File: `envoy/extensions/transport_sockets/tls/v3/tls.proto`. Defined in: [xDS Security](../09-xds/09-security.md) ([xDS Security: `CommonTlsContext` Validation](../09-xds/09-security.md#4-commontlscontext-validation)).
- `CertificateValidationContext` (including `match_subject_alt_names` and `system_root_certs`), `CertificateProviderPluginInstance`. File: `envoy/extensions/transport_sockets/tls/v3/common.proto`. Defined in: [xDS Security](../09-xds/09-security.md) ([xDS Security: Server Identity Verification](../09-xds/09-security.md#3-server-identity-verification), [xDS Security: `CommonTlsContext` Validation](../09-xds/09-security.md#4-commontlscontext-validation), [xDS Security: Certificate Provider Instances](../09-xds/09-security.md#5-certificate-provider-instances)).
- `envoy.extensions.transport_sockets.http_11_proxy.v3.Http11ProxyUpstreamTransport`. File: `envoy/extensions/transport_sockets/http_11_proxy/v3/upstream_http_11_connect.proto`. Defined in: [Cluster](../09-xds/04-resources/04-cluster.md) ([Transport Socket](../09-xds/04-resources/04-cluster.md#6-transport-socket)); [xDS Security](../09-xds/09-security.md) ([xDS Security: HTTP CONNECT and TLS](../09-xds/09-security.md#6-http-connect-and-tls)); [HTTP CONNECT Proxy Support](../04-client-channel/09-proxy.md) ([HTTP CONNECT Proxy Support: xDS-Configured Proxies](../04-client-channel/09-proxy.md#5-xds-configured-proxies)).

## C.8 xDS HTTP Filter Types

Each filter is listed with its types, files, and the documents that
define its handling.

- **Router.** Types: `envoy.extensions.filters.http.router.v3.Router`. File(s): `envoy/extensions/filters/http/router/v3/router.proto`. Defined in: [xDS HTTP Filters](../09-xds/07-http-filters.md) ([xDS HTTP Filters: Router](../09-xds/07-http-filters.md#7-router)).
- **Fault injection.** Types: `envoy.extensions.filters.http.fault.v3.HTTPFault`, `envoy.extensions.filters.common.fault.v3.FaultDelay`, `FaultAbort`. File(s): `envoy/extensions/filters/http/fault/v3/fault.proto`, `envoy/extensions/filters/common/fault/v3/fault.proto`. Defined in: [xDS HTTP Filters](../09-xds/07-http-filters.md) ([xDS HTTP Filters: Fault Injection](../09-xds/07-http-filters.md#8-fault-injection)).
- **RBAC.** Types: `envoy.extensions.filters.http.rbac.v3.RBAC`, `RBACPerRoute`; `envoy.config.rbac.v3.RBAC` (`Policy`, `Permission`, `Principal`, `AuditLoggingOptions`). File(s): `envoy/extensions/filters/http/rbac/v3/rbac.proto`, `envoy/config/rbac/v3/rbac.proto`. Defined in: [xDS HTTP Filters](../09-xds/07-http-filters.md) ([xDS HTTP Filters: RBAC](../09-xds/07-http-filters.md#9-rbac)); [Authorization](../06-security/04-authorization.md).
- **RBAC audit logger.** Types: `envoy.extensions.rbac.audit_loggers.stream.v3.StdoutAuditLog`. File(s): `envoy/extensions/rbac/audit_loggers/stream/v3/stream.proto`. Defined in: [Authorization](../06-security/04-authorization.md) ([Built-in `stdout_logger`](../06-security/04-authorization.md#36-built-in-stdout_logger)); [xDS HTTP Filters](../09-xds/07-http-filters.md) ([Audit Logging Configuration](../09-xds/07-http-filters.md#93-audit-logging-configuration)).
- **Stateful session affinity.** Types: `envoy.extensions.filters.http.stateful_session.v3.StatefulSession`, `StatefulSessionPerRoute`; `envoy.extensions.http.stateful_session.cookie.v3.CookieBasedSessionState`; `envoy.type.http.v3.Cookie`. File(s): `envoy/extensions/filters/http/stateful_session/v3/stateful_session.proto`, `envoy/extensions/http/stateful_session/cookie/v3/cookie.proto`, `envoy/type/http/v3/cookie.proto`. Defined in: [xDS HTTP Filters](../09-xds/07-http-filters.md) ([xDS HTTP Filters: Stateful Session Affinity](../09-xds/07-http-filters.md#10-stateful-session-affinity)).
- **GCP authentication.** Types: `envoy.extensions.filters.http.gcp_authn.v3.GcpAuthnFilterConfig`, `Audience`. File(s): `envoy/extensions/filters/http/gcp_authn/v3/gcp_authn.proto`. Defined in: [xDS HTTP Filters](../09-xds/07-http-filters.md) ([xDS HTTP Filters: GCP Authentication](../09-xds/07-http-filters.md#11-gcp-authentication)).

## C.9 xDS LB Policy Extension Types

Each type is listed with the gRPC LB policy it is converted to and the
documents that define the conversion.

- `envoy.extensions.load_balancing_policies.round_robin.v3.RoundRobin` → `round_robin`. Defined in: [xDS LB Policies](../09-xds/06-lb-policies.md) ([`load_balancing_policy`](../09-xds/06-lb-policies.md#21-load_balancing_policy)).
- `envoy.extensions.load_balancing_policies.wrr_locality.v3.WrrLocality` → `xds_wrr_locality_experimental`. Defined in: [xDS LB Policies](../09-xds/06-lb-policies.md) ([`xds_wrr_locality`](../09-xds/lb-policies/xds_wrr_locality.md), [`load_balancing_policy`](../09-xds/06-lb-policies.md#21-load_balancing_policy)).
- `envoy.extensions.load_balancing_policies.ring_hash.v3.RingHash` → `ring_hash_experimental`. Defined in: [xDS LB Policies](../09-xds/06-lb-policies.md) ([`load_balancing_policy`](../09-xds/06-lb-policies.md#21-load_balancing_policy)); [`ring_hash`](../04-client-channel/lb-policies/ring_hash.md).
- `envoy.extensions.load_balancing_policies.least_request.v3.LeastRequest` → `least_request_experimental`. Defined in: [xDS LB Policies](../09-xds/06-lb-policies.md) ([`load_balancing_policy`](../09-xds/06-lb-policies.md#21-load_balancing_policy)); [`least_request`](../04-client-channel/lb-policies/least_request.md).
- `envoy.extensions.load_balancing_policies.client_side_weighted_round_robin.v3.ClientSideWeightedRoundRobin` → `weighted_round_robin`. Defined in: [xDS LB Policies](../09-xds/06-lb-policies.md) ([`load_balancing_policy`](../09-xds/06-lb-policies.md#21-load_balancing_policy)); [`weighted_round_robin`](../04-client-channel/lb-policies/weighted_round_robin.md).
- `envoy.extensions.load_balancing_policies.pick_first.v3.PickFirst` → `pick_first`. Defined in: [xDS LB Policies](../09-xds/06-lb-policies.md) ([`load_balancing_policy`](../09-xds/06-lb-policies.md#21-load_balancing_policy)); [`pick_first`](../04-client-channel/lb-policies/pick_first.md).
- `envoy.extensions.load_balancing_policies.random_subsetting.v3.RandomSubsetting` → `random_subsetting_experimental`. Defined in: [xDS LB Policies](../09-xds/06-lb-policies.md) ([`load_balancing_policy`](../09-xds/06-lb-policies.md#21-load_balancing_policy)); [`random_subsetting`](../04-client-channel/lb-policies/random_subsetting.md).
- `xds.type.v3.TypedStruct` / `udpa.type.v1.TypedStruct` → any policy in the gRPC LB policy registry (custom policies). Defined in: [xDS LB Policies](../09-xds/06-lb-policies.md) ([`load_balancing_policy`](../09-xds/06-lb-policies.md#21-load_balancing_policy)).

The Envoy files for these types are under
`envoy/extensions/load_balancing_policies/<name>/v3/`.

## C.10 JSON Schemas Defined by This Specification

| Schema | Where it appears | Defined in |
| --- | --- | --- |
| Service config | Resolver results, DNS TXT records, application default config | [Service Config](../04-client-channel/04-service-config.md) (schema of `grpc/service_config/service_config.proto`) |
| Service config choices (`clientLanguage`, `percentage`, `clientHostname`, `serviceConfig`) | DNS TXT records (`grpc_config=` prefix) | [Name Resolution](../04-client-channel/03-name-resolution.md) ([Service Config in DNS](../04-client-channel/03-name-resolution.md#72-service-config-in-dns)) |
| LB policy configs (`loadBalancingConfig` entries) | Service config, xDS LB policy registry output | [Load Balancing](../04-client-channel/06-load-balancing.md) ([Load Balancing: LB Policy Registry and Configuration](../04-client-channel/06-load-balancing.md#2-lb-policy-registry-and-configuration)); [Service Config](../04-client-channel/04-service-config.md) ([`loadBalancingConfig`](../04-client-channel/04-service-config.md#52-loadbalancingconfig)); [xDS LB Policies](../09-xds/06-lb-policies.md) |
| xDS bootstrap (top level, `XdsServer`, `Node`, `Authority`, certificate provider instances, `channel_creds` and `call_creds` types, `server_features`) | `GRPC_XDS_BOOTSTRAP` file, `GRPC_XDS_BOOTSTRAP_CONFIG`, programmatic config | [Bootstrap](../09-xds/02-bootstrap.md) |
| `file_watcher` certificate provider config (`certificate_file`, `private_key_file`, `ca_certificate_file`, `spiffe_trust_bundle_map_file`, `refresh_interval`) | Bootstrap `certificate_providers`. The same options apply to the file-watcher provider API. | [Bootstrap](../09-xds/02-bootstrap.md) ([Certificate Provider Instances](../09-xds/02-bootstrap.md#44-certificate-provider-instances)); [xDS Security](../09-xds/09-security.md) ([`file_watcher` Plugin](../09-xds/09-security.md#51-file_watcher-plugin)); [TLS](../06-security/02-tls.md) ([File-Watcher Provider](../06-security/02-tls.md#63-file-watcher-provider)) |
| `tls` channel credentials config in the bootstrap (`ca_certificate_file`, `certificate_file`, `private_key_file`, `refresh_interval`) | Bootstrap `channel_creds` | [Bootstrap](../09-xds/02-bootstrap.md) ([XdsServer Object](../09-xds/02-bootstrap.md#41-xdsserver-object)) |
| `jwt_token_file` call credentials config | Bootstrap `call_creds` | [Bootstrap](../09-xds/02-bootstrap.md) ([XdsServer Object](../09-xds/02-bootstrap.md#41-xdsserver-object)); [Call Credentials](../06-security/03-call-credentials.md) ([Call Credentials: JWT Token File Credentials](../06-security/03-call-credentials.md#5-jwt-token-file-credentials)) |
| SPIFFE trust bundle map (`trust_domains`, `spiffe_sequence`, `keys` with `kty`, `use`, `x5c`) | File named by `spiffe_trust_bundle_map_file` | [TLS](../06-security/02-tls.md) ([Bundle Map Format](../06-security/02-tls.md#101-bundle-map-format)) |
| gRPC authorization policy (`name`, `deny_rules`, `allow_rules`, `source`, `request`, `audit_logging_options`) | Static or file-watched authorization policy | [Authorization](../06-security/04-authorization.md) ([Schema](../06-security/04-authorization.md#21-schema)) |
| Audit logger config (`audit_condition`, `audit_loggers` with `name`, `config`, `is_optional`) | Authorization policy `audit_logging_options` | [Authorization](../06-security/04-authorization.md) ([Audit Options in the gRPC Authorization Policy](../06-security/04-authorization.md#33-audit-options-in-the-grpc-authorization-policy)) |
| `stdout_logger` output line (`grpc_audit_log` object) | Standard output | [Authorization](../06-security/04-authorization.md) ([Built-in `stdout_logger`](../06-security/04-authorization.md#36-built-in-stdout_logger)) |
| xDS cookie value (`<addresses>;<cluster>`, base64) | `cookie` / `set-cookie` headers | [xDS HTTP Filters](../09-xds/07-http-filters.md) ([Cookie Value Format](../09-xds/07-http-filters.md#102-cookie-value-format)) |

## C.11 Other Text Formats

| Format | Defined in |
| --- | --- |
| HTTP/2 request and response grammar (ABNF) | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) |
| Call ABNF | [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Call ABNF](../02-rpc-semantics/README.md#19-call-abnf)) |
| Binary log filter configuration string | [Binary Logging](../08-observability/07-binary-logging.md) ([Grammar](../08-observability/07-binary-logging.md#51-grammar)) |
| `grpc-trace-bin` binary format | [Tracing](../08-observability/05-tracing.md) ([Tracing: The `grpc-trace-bin` Propagator and Format](../08-observability/05-tracing.md#7-the-grpc-trace-bin-propagator-and-format)) |
| Channel target URIs (`dns:`, `unix:`, `unix-abstract:`, `vsock:`, `ipv4:`, `ipv6:`, `xds:`) | [Channel](../04-client-channel/02-channel.md) ([Channel: Target URI Parsing](../04-client-channel/02-channel.md#2-target-uri-parsing)); [Name Resolution](../04-client-channel/03-name-resolution.md) ([Name Resolution: Built-in Resolvers](../04-client-channel/03-name-resolution.md#7-built-in-resolvers)); [Client Data Plane](../09-xds/05-client.md) ([Target URI syntax](../09-xds/05-client.md#11-target-uri-syntax)) |
| xDS resource names (old-style, and `xdstp:` new-style) and Listener name templates | [XdsClient](../09-xds/03-xds-client.md) ([XdsClient: Resource Names](../09-xds/03-xds-client.md#3-resource-names)) |
