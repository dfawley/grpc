> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 7.1 Health Service

<!-- Sources: doc/health-checking.md, grpc/health/v1/health.proto, A17, A90 -->

The health service lets a server report whether it can handle RPCs, both
overall and for each service. Clients use it for client-side health checking
([Client-side health checking](../04-client-channel/10-health-checking.md)),
and external systems such as load balancers and orchestrators use it for
centralized health checking. Because it is an ordinary gRPC service, it shares
the server's transport, security, quota, and access-control setup.

## 1. Service Definition

The service is defined in `grpc/health/v1/health.proto`:

```protobuf
syntax = "proto3";

package grpc.health.v1;

message HealthCheckRequest {
  string service = 1;
}

message HealthCheckResponse {
  enum ServingStatus {
    UNKNOWN = 0;
    SERVING = 1;
    NOT_SERVING = 2;
    SERVICE_UNKNOWN = 3;  // Used only by the Watch method.
  }
  ServingStatus status = 1;
}

message HealthListRequest {}

message HealthListResponse {
  // statuses contains all the services and their respective status.
  map<string, HealthCheckResponse> statuses = 1;
}

service Health {
  rpc Check(HealthCheckRequest) returns (HealthCheckResponse);
  rpc List(HealthListRequest) returns (HealthListResponse);
  rpc Watch(HealthCheckRequest) returns (stream HealthCheckResponse);
}
```

The full method names are `/grpc.health.v1.Health/Check`,
`/grpc.health.v1.Health/List`, and `/grpc.health.v1.Health/Watch`.

## 2. Health Status Registry

The server keeps a registry that maps a **service name** (a string) to a
`ServingStatus` (`SERVING` or `NOT_SERVING`).

* The **empty string** `""` stands for the **overall health of the server**, as
  opposed to any one service. Clients that don't care about a specific service
  query `""`.
* The other names are usually fully qualified gRPC service names (for example,
  `foo.v1.Bar`), but the registry treats them as opaque strings. Lookups are
  **exact string matches**. There is no wildcard or prefix matching. A server
  and its clients MAY agree on richer matching semantics for a custom
  implementation, but the standard implementation does exact matching only.
* A service name that is not in the registry is **unknown**.
* `UNKNOWN` (0) is the proto default. The server never stores it as a status
  and never returns it on purpose.

## 3. `Check`

`Check` returns the current status of the service named in `service`.

| Condition | Result |
| --- | --- |
| `service` is in the registry | Status `OK`. The response `status` is the registered `SERVING` or `NOT_SERVING`. |
| `service` is not in the registry | The RPC fails with status `NOT_FOUND`. |

Clients SHOULD set a deadline on `Check`. A client MAY treat the server as
unhealthy if it gets no response in time. Clients MUST cope with servers that
do not implement the health service, in which case `Check` fails with
`UNIMPLEMENTED`.

## 4. `Watch`

`Watch` is a server-streaming RPC that reports the status of one service as it
changes:

1. When the server receives the request, it MUST **immediately** send one
   response with the current status of the requested service. If the service
   is unknown, that status is `SERVICE_UNKNOWN`. The call is **not** ended in
   that case.
2. After that, the server sends a new response whenever the status of the
   service changes. This includes the service becoming known (`SERVING` or
   `NOT_SERVING`) and becoming unknown again because its entry was removed
   (`SERVICE_UNKNOWN`). The server SHOULD NOT send a response whose status is
   the same as the last one sent on that call. If the status changes several
   times quickly, the server MAY skip intermediate values, but it MUST
   eventually send the latest status.
3. The server does not end the call on its own while it is serving. The call
   ends when the client cancels it, or when the server or connection shuts
   down.

How clients react to the call ending:

* `UNIMPLEMENTED`: the client SHOULD assume the server does not support
  `Watch`, and MUST NOT retry it.
* Any other status, including `OK`: the client SHOULD retry the call with
  exponential backoff.

The client-side state machine built on `Watch` is specified in
[Client-side health checking](../04-client-channel/10-health-checking.md).

## 5. `List`

> **Introduced by:** [gRFC A90: Add List Method to gRPC Health Service](https://github.com/grpc/proposal/blob/master/A90-health-service-list-method.md)

`List` returns a snapshot of every entry in the registry, including `""`.

* `statuses` maps each registered service name to a `HealthCheckResponse`
  containing its status (`SERVING` or `NOT_SERVING`).
* The snapshot is **not atomic**. If the registry changes while the response
  is being built, the response can reflect some of the changes but not others.
* **Limit:** the response contains at most **100** services. If the registry
  holds more than 100 entries, the server MUST fail the RPC with
  `RESOURCE_EXHAUSTED` and not return a truncated list. The `""` entry counts
  toward the limit.
* `List` MUST be idempotent and free of side effects.
* Clients SHOULD set a deadline on `List`. Clients MUST NOT assume that the set
  of services stays the same over the life of the server.

## 6. Relationship to Client-Side Health Checking

> **Introduced by:** [gRFC A17: Client-Side Health Checking](https://github.com/grpc/proposal/blob/master/A17-client-side-health-checking.md)

Client-side health checking ([Client-Side Health Checking](../04-client-channel/10-health-checking.md))
opens one `Watch` call on each connection whose subchannel has health checking
enabled and at least one health watcher registered, using the service name
from the client's service config. By convention,
`""` lets one switch control health for all services on a host and port. The
server needs no special support beyond implementing `Watch` as specified above.
A server that does not implement `Watch` returns `UNIMPLEMENTED`, and clients
then treat the backend as healthy.

## 7. API Requirements

gRPC MUST provide a health service implementation that applications can
register on a server, along with a **health status manager** for updating the
registry. The manager's API MUST provide a way to:

1. **Set the status** (`SERVING` or `NOT_SERVING`) of a named service,
   including `""`. Setting a status for a name that is not registered adds it.
2. **Remove** the entry for a named service, which makes it unknown again.
   Active `Watch` calls for that name receive `SERVICE_UNKNOWN`.
3. **Enter shutdown**: set every registered service, including `""`, to
   `NOT_SERVING`, and ignore later status updates so that the server stays
   `NOT_SERVING` while it drains. This is meant to be called before graceful
   server shutdown ([Server: Graceful Shutdown](../05-server/README.md)), so that health-checking clients
   move traffic away before connections close.
4. **Leave shutdown**: accept status updates again.

When the health service is created, `""` SHOULD be registered as `SERVING`.
All manager operations MUST be safe to call concurrently with each other and
with in-progress health RPCs. Every status change MUST be delivered to all
active `Watch` calls for the affected names.
