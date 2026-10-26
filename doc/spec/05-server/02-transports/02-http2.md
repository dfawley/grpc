> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 5.2.2 HTTP/2 Server Transport

<!-- Sources: A9, A18, doc/keepalive.md, doc/PROTOCOL-HTTP2.md, doc/http2-interop-test-descriptions.md (informative) -->

This document covers server-side HTTP/2 connection behavior that is not part
of the per-call exchange in
[gRPC over HTTP/2](../../03-wire-protocol/01-http2.md): SETTINGS, the
concurrent stream limit, graceful draining, server connection management,
keepalive, ping abuse enforcement, TCP_USER_TIMEOUT, and flow control. It
follows the structure of the [Server Transport Model](01-transport-model.md).
The client side is in
[HTTP/2 Client Transport](../../04-client-channel/08-transports/02-http2.md).

## 1. Overview

An HTTP/2 server transport is one HTTP/2 connection accepted on a TCP or Unix
domain socket listener and secured by the listening address's server
credentials. Each stream the client opens is one incoming call.

## 2. Listening and Connection Establishment

### 2.1 SETTINGS

Implementations follow HTTP/2 SETTINGS semantics
([RFC 9113 §6.5](https://www.rfc-editor.org/rfc/rfc9113#section-6.5)). In
addition:

| Setting | Behavior |
| ------- | -------- |
| `SETTINGS_ENABLE_PUSH` | gRPC does not use server push. Servers MUST NOT send PUSH_PROMISE. |
| `SETTINGS_MAX_CONCURRENT_STREAMS` | Servers MAY advertise a limit and MAY change it during the connection (see [Stream Limits](#4-stream-limits)). |
| `SETTINGS_INITIAL_WINDOW_SIZE` | Sets the stream-level flow-control window (see [Flow Control](#8-flow-control)). |
| `SETTINGS_MAX_HEADER_LIST_SIZE` | Implementations SHOULD advertise the header list size limit they enforce ([Header list size](../../03-wire-protocol/01-http2.md#45-header-list-size)). |
| `SETTINGS_MAX_FRAME_SIZE` | Any value HTTP/2 allows. |
| `GRPC_ALLOW_TRUE_BINARY_METADATA` (0xfe03) | See [True Binary Metadata](../../03-wire-protocol/02-true-binary-metadata.md). |

## 3. Streams

Each incoming call uses one client-initiated HTTP/2 stream. The mapping of
headers, messages, trailers, cancellation, and errors onto the stream is
specified in [gRPC over HTTP/2](../../03-wire-protocol/01-http2.md).

## 4. Stream Limits

Servers MAY advertise a limit with `SETTINGS_MAX_CONCURRENT_STREAMS` and MAY
change it during the connection; if it never sets the value, there is no limit
([RFC 9113 §6.5.2](https://www.rfc-editor.org/rfc/rfc9113#section-6.5.2)).
Streams above the limit are refused with `RST_STREAM(REFUSED_STREAM)`
([RFC 9113 §5.1.2](https://www.rfc-editor.org/rfc/rfc9113#section-5.1.2)),
and the client sees them as unprocessed (`UNAVAILABLE`, eligible for transparent retry). Clients report
the value to their subchannel to scale connections (see
[HTTP/2 Client Transport: Stream Limits](../../04-client-channel/08-transports/02-http2.md#4-stream-limits)).

## 5. Graceful Shutdown and Draining

The server drains a connection with the two-phase GOAWAY sequence specified in
[GOAWAY](../../03-wire-protocol/01-http2.md#92-goaway). Server shutdown uses
graceful GOAWAY; see
[Server Behavior: Graceful Shutdown](../01-server.md#13-graceful-shutdown).
Server connection management also uses it
([Connection Management](#6-connection-management)).

## 6. Connection Management

> **Introduced by:** [gRFC A9: Server-side Connection Management](https://github.com/grpc/proposal/blob/master/A9-server-side-conn-mgt.md)

Server settings:

| Setting | Default | Meaning |
| ------- | ------- | ------- |
| `MAX_CONNECTION_IDLE` | infinite | Close a connection after it has been idle this long. Idle time is measured from the later of connection establishment and the last time the number of outstanding RPCs dropped to zero. |
| `MAX_CONNECTION_AGE` | infinite | Close a connection once it has existed this long. A random per-connection jitter of ±10% MUST be applied, to spread out reconnection storms. |
| `MAX_CONNECTION_AGE_GRACE` | infinite | After the age-triggered graceful shutdown starts, the longest time outstanding RPCs may run before the connection is forcibly closed. No jitter is applied. |

Procedure:

- When `MAX_CONNECTION_IDLE` is reached, the server sends GOAWAY with
  `NO_ERROR` and debug data `max_idle`, then continues the graceful shutdown
  ([GOAWAY](../../03-wire-protocol/01-http2.md#92-goaway)).
- When `MAX_CONNECTION_AGE` (with jitter) is reached, the server sends GOAWAY
  with `NO_ERROR` and debug data `max_age`, then continues the graceful
  shutdown. Outstanding RPCs MUST be allowed to finish. The first GOAWAY
  SHOULD use last-stream-id 2^31-1 (two-phase GOAWAY).
- `MAX_CONNECTION_AGE_GRACE` SHOULD be measured from the second GOAWAY of the
  graceful shutdown. When it expires, the server closes the connection.
  RPCs still running on it fail (the client sees `UNAVAILABLE`, and the server
  application sees cancellation).
- Implementations SHOULD put an upper bound on the time between the first and
  second GOAWAY. The bound is implementation-defined.

`MAX_CONNECTION_AGE` makes clients reconnect from time to time, for example
so that an L4 load balancer can rebalance them. `MAX_CONNECTION_IDLE` frees
resources held by unused connections. Apart from channel idleness (the whole
channel going IDLE after its idle timeout with no RPCs; see
[Channel](../../04-client-channel/02-channel.md)), clients do not close
individual connections because they are idle (see
[Subchannels and Connections](../../04-client-channel/07-subchannels.md)), so
servers that want idle connections cleaned up SHOULD set
`MAX_CONNECTION_IDLE`.

These timers do not need to be precise. Implementations MAY implement them
coarsely.

## 7. Liveness and Enforcement

Keepalive uses HTTP/2 PING frames to keep connections from being closed as
idle by intermediaries, and to detect dead connections. It is a per-hop
connection mechanism. The service owner decides what keepalive traffic it
accepts ([Ping Enforcement](#72-ping-enforcement)).

### 7.1 Keepalive

> **Introduced by:** [gRFC A9: Server-side Connection Management](https://github.com/grpc/proposal/blob/master/A9-server-side-conn-mgt.md)

Server settings:

| Setting | Default | Rules |
| ------- | ------- | ----- |
| `KEEPALIVE_TIME` | 2 hours | Same meaning as on the client. |
| `KEEPALIVE_TIMEOUT` | 20 seconds | Same meaning as on the client. |

Server keepalive works like client keepalive
([HTTP/2 Client Transport: Keepalive](../../04-client-channel/08-transports/02-http2.md#61-keepalive)),
except that the server sends keepalive PINGs whether or not the connection has
outstanding RPCs. When the watchdog expires, the server closes the connection
and cancels its calls on that connection.

### 7.2 Ping Enforcement

Servers MUST protect themselves from clients that ping too often. Server
settings:

| Setting | Default | Meaning |
| ------- | ------- | ------- |
| `PERMIT_KEEPALIVE_TIME` | 5 minutes | Minimum interval between client PINGs that the server allows while the connection has active streams (or always, if the next setting is true). |
| `PERMIT_KEEPALIVE_WITHOUT_CALLS` | false | If false, the minimum interval with no active streams is 2 hours. If true, `PERMIT_KEEPALIVE_TIME` applies even with no active streams. |
| `MAX_PING_STRIKES` | 2 | Number of bad PINGs tolerated. A bad PING received after this many strikes (so strike number `MAX_PING_STRIKES + 1`) means the client is misbehaving. Implementations MAY make it configurable (see [API Requirements](#9-api-requirements)); if they do, a value of 0 SHOULD mean unlimited. |

PINGs also have legitimate uses besides keepalive, such as latency and
bandwidth estimation. Servers SHOULD therefore allow a PING after they send
HEADERS or DATA frames, and SHOULD generally be tolerant ("fuzzy") about PING
timing. Algorithm:

```
init:
  ping_strikes = 0
  last_valid_ping_time = epoch      # monotonic clock; >= 1s precision (ms encouraged)

on PING frame received (without the ACK flag):
  if active_streams == 0 and not PERMIT_KEEPALIVE_WITHOUT_CALLS:
    ok = last_valid_ping_time + 2 hours <= now()
  else:
    ok = last_valid_ping_time + PERMIT_KEEPALIVE_TIME <= now()
  if ok:
    last_valid_ping_time = now()
  else:
    ping_strikes += 1
    if ping_strikes > MAX_PING_STRIKES:
      client is misbehaving (see below)

on HEADERS or DATA frame sent:
  last_valid_ping_time = epoch
  ping_strikes = 0
```

The 2-hour value matches TCP keepalive, whose interval defaults to no less
than two hours
([RFC 1122 §4.2.3.6](https://www.rfc-editor.org/rfc/rfc1122#page-101)).

When a client is misbehaving, the server MUST send GOAWAY with error code
`ENHANCE_YOUR_CALM` and ASCII debug data `too_many_pings`, and then close the
connection right away. Closing right away fails in-progress RPCs, which makes
it more likely the client author notices the misconfiguration.

### 7.3 TCP_USER_TIMEOUT

> **Introduced by:** [gRFC A18: TCP User Timeout](https://github.com/grpc/proposal/blob/master/A18-tcp-user-timeout.md)

On platforms that support the `TCP_USER_TIMEOUT` socket option (Linux 2.6.37
and later):

- When keepalive is enabled (`KEEPALIVE_TIME` is not infinite), the
  implementation MUST set `TCP_USER_TIMEOUT` on the connection's socket to
  `KEEPALIVE_TIMEOUT`. With the default, that is 20 seconds. The timeout then
  bounds how long any sent data, not just a PING, may stay unacknowledged
  before the kernel closes the connection.
- When keepalive is disabled, `TCP_USER_TIMEOUT` is not set, and the system
  default applies.

This applies to clients and servers alike (see
[HTTP/2 Client Transport: TCP_USER_TIMEOUT](../../04-client-channel/08-transports/02-http2.md#62-tcp_user_timeout)).
Servers have keepalive enabled by default (2 hours), so by default server
sockets get a 20-second `TCP_USER_TIMEOUT`. A connection closed this way is a
connection failure
([Connection failure](../../03-wire-protocol/01-http2.md#94-connection-failure)).

## 8. Flow Control

gRPC uses HTTP/2 flow control at both the connection and the stream level
exactly as specified in
[RFC 9113 §5.2](https://www.rfc-editor.org/rfc/rfc9113#section-5.2) and
[§6.9](https://www.rfc-editor.org/rfc/rfc9113#section-6.9), including its
treatment of DATA frame padding (the `data_frame_padding` negative interop test
exercises this). gRPC adds no flow-control requirements of its own: receive
window sizes and when to send WINDOW_UPDATE are up to each implementation. The
same rules apply to clients (see
[HTTP/2 Client Transport: Flow Control](../../04-client-channel/08-transports/02-http2.md#7-flow-control)).

## 9. API Requirements

Server API:

- MUST provide a way to set the server's `KEEPALIVE_TIME` and
  `KEEPALIVE_TIMEOUT`.
- MUST provide a way to set `PERMIT_KEEPALIVE_TIME` and
  `PERMIT_KEEPALIVE_WITHOUT_CALLS`.
- MUST provide a way to set `MAX_CONNECTION_IDLE`, `MAX_CONNECTION_AGE`, and
  `MAX_CONNECTION_AGE_GRACE`.
- MUST provide a way to set `SETTINGS_MAX_CONCURRENT_STREAMS` and the maximum
  header list size the server accepts.
- SHOULD provide a way to set the initial flow-control window sizes.
- MAY provide a way to set `MAX_PING_STRIKES`.
