> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 7. Standard Services and Admin Interface

<!-- Sources: doc/health-checking.md, doc/server-reflection.md, A15, A17, A38, A51, A90 -->

gRPC defines a set of standard services that applications can register on their
servers. Each one is an ordinary gRPC service defined in protobuf. Each is
served by an implementation that gRPC provides and is called like any other
RPC. None of them is registered or exposed unless the application asks for it.

| Section | Service | Proto | Purpose |
| --- | --- | --- | --- |
| [Health service](01-health.md) | `grpc.health.v1.Health` | `grpc/health/v1/health.proto` | Reports per-service and overall serving status. Used by client-side health checking and external health checkers. |
| [Server reflection](02-reflection.md) | `grpc.reflection.v1.ServerReflection` (also `grpc.reflection.v1alpha.ServerReflection`) | `grpc/reflection/v1/reflection.proto` | Lets tools find services and protobuf descriptors at runtime. |
| [Backend Metrics (ORCA)](03-orca.md) | `xds.service.orca.v3.OpenRcaService` | `xds/service/orca/v3/orca.proto` (cncf/xds) | Out-of-band backend metric reports. Per-call metrics are carried in trailers. |
| [Admin interface](04-admin.md) | Channelz, CSDS | `grpc/channelz/v1/channelz.proto`, `envoy/service/status/v3/csds.proto` | A single call adds all admin services to a server. |

Applications protect these services the same way they protect any other
service on the server: with credentials on the listening address
([Security](../06-security/README.md)), authorization
([Authorization](../06-security/03-authorization.md)), and interceptors.
