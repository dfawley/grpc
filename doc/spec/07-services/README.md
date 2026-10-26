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

Applications protect these services the same way they protect any other
service on the server: with credentials on the listening address
([Security](../06-security/README.md)), authorization
([Authorization](../06-security/04-authorization.md)), and interceptors.

## Contents

- [7.1 Health Service](01-health.md): `grpc.health.v1.Health`: per-service and overall serving status
- [7.2 Server Reflection](02-reflection.md): `grpc.reflection.v1.ServerReflection`: services and protobuf descriptors at runtime
- [7.3 Backend Metrics (ORCA)](03-orca.md): `xds.service.orca.v3.OpenRcaService`: out-of-band backend metric reports
- [7.4 Admin Interface](04-admin.md): a single call that adds the admin services (channelz, CSDS) to a server
