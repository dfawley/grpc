> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4.10 Client-Side Health Checking

<!-- Sources: A17, A61, doc/health-checking.md, grpc/service_config/service_config.proto (HealthCheckConfig) -->

> **Introduced by:** [gRFC A17: Client-Side Health Checking](https://github.com/grpc/proposal/blob/master/A17-client-side-health-checking.md)

Client-side health checking lets a client stop sending calls to a backend
that reports itself unhealthy, without closing the connection to it. The
client watches each connected backend's health with the
`grpc.health.v1.Health/Watch` streaming method. The server side of that
service is specified in [Health Service](../07-services/01-health.md).

## 1. Configuration

Health checking is disabled by default. Service owners enable it with the
`healthCheckConfig` field of the [service config](04-service-config.md):

```json
{ "healthCheckConfig": { "serviceName": "foo" } }
```

| Field (JSON) | Type | Description |
| --- | --- | --- |
| `healthCheckConfig.serviceName` | string (`google.protobuf.StringValue`) | The service name to send in health-check requests. If unset, health checking is disabled. The empty string is valid, and means the overall health of the server. |

Proto: `ServiceConfig.HealthCheckConfig` in
`grpc/service_config/service_config.proto`. If `serviceName` is present
but not a JSON string, the service config is invalid.

The client channel API provides an option that disables health checking
for a channel, even if the service config enables it (see
[API Requirements](#6-api-requirements)).

## 2. Where Health Checking Applies

Health checking is one of the signals that feed the subchannel's generic
health state ([Load Balancing](06-load-balancing.md)). It affects
routing only through that health state:

- A health-check stream runs on a subchannel only while health checking
  is enabled for the channel (configured, and not disabled by the
  client), and at least one health watcher is registered on that
  subchannel.
- In the provided policies, only `pick_first` registers health watchers,
  and only when a petiole policy (such as `round_robin`) has enabled its
  internal health-reporting option. The watcher is registered on the
  subchannel `pick_first` has selected.
- So health checking has **no effect** when `pick_first` is the top-level
  policy, or when it is used directly by any parent other than a petiole.
  A `pick_first` that treated unhealthiness as a connection failure would
  close a working connection for no reason, and might not choose a
  different backend afterward.
- Health state never affects connection management. The subchannel's
  raw connectivity state stays READY while it is unhealthy, and the
  connection is kept open.

## 3. Client Workflow

The health-check stream is a connection-scoped stream, managed by the
mechanism in [Subchannels and Connections: Connection-Scoped Watchers and Streams](07-subchannels.md#9-connection-scoped-watchers-and-streams).
That section specifies when the stream runs, which connection it uses,
backoff, and cancellation. The steps below restate those rules where
needed and add the behavior specific to health checking. Producers are
keyed by service name: watchers that need different service names (for
example, on a subchannel shared by two channels) get separate streams.

For each subchannel that has an established connection and at least one
health watcher, while health checking is enabled:

1. **Start.** As soon as the connection is established (or a watcher is
   registered, if the connection already exists), the client starts a
   `/grpc.health.v1.Health/Watch` call on that connection. The request is
   `HealthCheckRequest{service: <serviceName>}`. The call goes directly
   on the subchannel's connection, bypassing load balancing.
2. **Initial state.** Until the first response arrives, the health state
   is CONNECTING. The subchannel is not reported healthy until the
   backend says so. This prevents a burst of queued calls from going to a
   backend that is about to report itself unhealthy.
3. **Responses.** Each `HealthCheckResponse` sets the health state:

   | `status` in response | Health state |
   | --- | --- |
   | `SERVING` | READY |
   | `NOT_SERVING`, `SERVICE_UNKNOWN`, `UNKNOWN`, or any other value | TRANSIENT_FAILURE, with an `UNAVAILABLE` status whose message says that the backend reported itself unhealthy |

   A transition from unhealthy to healthy goes from TRANSIENT_FAILURE
   directly to READY.
4. **`UNIMPLEMENTED`.** If the call ends with `UNIMPLEMENTED`, the client
   treats the backend as healthy (health state READY), and MUST NOT
   retry the call on that connection. It records a channel trace event
   and logs an error.
5. **Other call failures.** If the call ends with any other status, the
   health state becomes TRANSIENT_FAILURE, and the client retries the
   call with backoff as specified in
   [Stream Lifecycle](07-subchannels.md#92-stream-lifecycle). When a message is received on a call,
   the backoff is reset: the next attempt after that call ends starts
   immediately, and later attempts back off. When a retry attempt starts,
   the health state becomes CONNECTING.
6. **Cancellation.** The client cancels the call, without waiting for a
   final status, when the connection receives a GOAWAY, when the
   connection closes, when the last health watcher is removed, when health
   checking is disabled by a config update, or when the subchannel shuts
   down. If the service name changes, the call is cancelled and restarted
   with the new name.


When health checking is disabled, or no watcher is registered, the health
state equals the raw connectivity state.

## 4. Other Requirements

The common rules for connection-scoped streams in
[Stream Lifecycle](07-subchannels.md#92-stream-lifecycle) apply. In particular, the
health-check stream carries the channel's call credentials (there is no way
to set separate call credentials for health checking), it MUST NOT count as
application activity for the channel's idle timeout, and it uses one stream
of the server's `MAX_CONCURRENT_STREAMS`.

## 5. Interaction With Outlier Detection

[Outlier detection](lb-policies/outlier_detection.md) also feeds the
health state. It wraps the health watch, and reports TRANSIENT_FAILURE
for an ejected endpoint whatever the health-check result. When the
endpoint is un-ejected, the health-check result shows through again.

## 6. API Requirements

- The channel API MUST provide an option to disable client-side health
  checking for a channel, even when the service config enables it.
- Health checking MUST be configurable through the service config
  `healthCheckConfig.serviceName` field, including through a default
  service config supplied by the application.
- The LB policy API MUST give custom LB policies the generic health watch
  ([Load Balancing](06-load-balancing.md)), so that health checking works
  for them.
