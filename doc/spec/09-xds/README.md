> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 9. xDS / Proxyless Service Mesh Support

<!-- Sources: A27, A28, A30, A36, A40, A46, A47, A53, A57, A71, A74, A81, A88, A95, doc/grpc_xds_features.md, doc/grpc_xds_bootstrap_format.md -->

> **Introduced by:** [gRFC A27: xDS-Based Global Load Balancing](https://github.com/grpc/proposal/blob/master/A27-xds-global-load-balancing.md)

gRPC can obtain its configuration from an xDS management server (also called a
*control plane*) using the xDS APIs. This lets gRPC clients and servers take
part in a service mesh without a sidecar proxy ("proxyless service mesh"). The
xDS APIs are a family of publish/subscribe APIs named "*x* Discovery Service".
gRPC uses the following resource types:

| API | Resource type (type URL suffix) | Purpose in gRPC |
| --- | --- | --- |
| LDS | `envoy.config.listener.v3.Listener` | Client: root of the channel's config (an HTTP API listener). Server: the listener for a serving address. |
| RDS | `envoy.config.route.v3.RouteConfiguration` | Virtual hosts and routes, used for per-RPC routing. |
| CDS | `envoy.config.cluster.v3.Cluster` | Cluster config: discovery type, LB policy, security, circuit breaking, outlier detection, load reporting. |
| EDS | `envoy.config.endpoint.v3.ClusterLoadAssignment` | Endpoints grouped by locality and priority; drop config. |
| (EDS list collection) | `envoy.config.endpoint.v3.LbEndpointCollection` | Endpoints for one locality, fetched separately from the EDS resource. |

Full type URLs have the form `type.googleapis.com/<resource type>`.

This section specifies how gRPC uses xDS. The xDS transport protocol itself is
defined by the Envoy and CNCF xDS documentation
(https://www.envoyproxy.io/docs/envoy/latest/api-docs/xds_protocol). This
section describes only gRPC's use of it and where gRPC differs from Envoy.

## Contents

- [9.1 Architecture and Design Principles](01-architecture.md): components, design principles, client features, server features
- [9.2 Bootstrap](02-bootstrap.md): bootstrap configuration
- [9.3 XdsClient](03-xds-client.md): transport, subscriptions, resource naming and federation, watchers, caching, error handling, fallback
- 9.4 Resources and Validation
  - [9.4.1 Common Types](04-resources/01-common-types.md)
  - [9.4.2 Listener](04-resources/02-listener.md)
  - [9.4.3 RouteConfiguration](04-resources/03-route-configuration.md)
  - [9.4.4 Cluster](04-resources/04-cluster.md)
  - [9.4.5 ClusterLoadAssignment and LbEndpointCollection](04-resources/05-endpoint.md)
- [9.5 Client Data Plane](05-client.md): `xds` resolver, XdsDependencyManager, XdsConfig, routing
- [9.6 xDS LB Policies](06-lb-policies.md): LB policy tree and the xDS LB policy registry
  - [`xds_cluster_manager`](lb-policies/xds_cluster_manager.md)
  - [`cds`](lb-policies/cds.md)
  - [`xds_cluster_impl`](lb-policies/xds_cluster_impl.md)
  - [`xds_override_host`](lb-policies/xds_override_host.md)
  - [`xds_wrr_locality`](lb-policies/xds_wrr_locality.md)
- [9.7 xDS HTTP Filters](07-http-filters.md): filter framework, router, fault injection, RBAC, stateful session affinity, GCP authentication
- [9.8 xDS-Enabled Servers](08-server.md): serving state, Listener handling, filter chain matching
- [9.9 xDS Security](09-security.md): xDS credentials and TLS configuration
- [9.10 Load Reporting (LRS)](10-load-reporting.md): load reporting to the control plane
- [9.11 Client Status Discovery Service (CSDS)](11-csds.md): exposing xDS configuration for debugging
