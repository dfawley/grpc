> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4.8.2 HTTP/2 Client Transport

<!-- Sources: A8, A18, A105 (transport/subchannel interaction), A6 (transparent retry), doc/keepalive.md, doc/PROTOCOL-HTTP2.md, doc/http2-interop-test-descriptions.md (informative) -->

This document covers client-side HTTP/2 connection behavior that is not part
of the per-call exchange in
[gRPC over HTTP/2](../../03-wire-protocol/01-http2.md): connection
establishment and SETTINGS, reporting MAX_CONCURRENT_STREAMS to the
subchannel, how a client reacts to GOAWAY, keepalive, TCP_USER_TIMEOUT, and
flow control. It follows the structure of the
[Client Transport Model](01-transport-model.md). The server side is in
[HTTP/2 Server Transport](../../05-server/02-transports/02-http2.md).

## 1. Overview

An HTTP/2 client transport is one HTTP/2 connection, over TCP or a Unix
domain socket, possibly through an
[HTTP CONNECT proxy](../09-proxy.md), and secured by the channel
credentials' handshake. Each call attempt is one HTTP/2 stream.

## 2. Connection Establishment

### 2.1 Establishment

- A client connection is established when the transport handshake (TCP, plus
  TLS or other security if configured) is done and the client has received
  the server's initial SETTINGS frame as part of the HTTP/2 connection
  preface ([RFC 9113 §3.4](https://www.rfc-editor.org/rfc/rfc9113#section-3.4)).
- A connection MUST NOT be reported as usable for RPCs (for example, the
  subchannel moving to READY; see
  [Subchannels and Connections](../07-subchannels.md)) before then.

### 2.2 SETTINGS

Implementations follow HTTP/2 SETTINGS semantics
([RFC 9113 §6.5](https://www.rfc-editor.org/rfc/rfc9113#section-6.5)). In
addition:

| Setting | Behavior |
| ------- | -------- |
| `SETTINGS_ENABLE_PUSH` | gRPC does not use server push. Clients SHOULD send 0. |
| `SETTINGS_MAX_CONCURRENT_STREAMS` | Advertised and enforced as in [RFC 9113 §5.1.2](https://www.rfc-editor.org/rfc/rfc9113#section-5.1.2). How the client reports and applies it is in [Stream Limits](#4-stream-limits). |
| `SETTINGS_INITIAL_WINDOW_SIZE` | Sets the stream-level flow-control window (see [Flow Control](#7-flow-control)). |
| `SETTINGS_MAX_HEADER_LIST_SIZE` | Implementations SHOULD advertise the header list size limit they enforce ([Header list size](../../03-wire-protocol/01-http2.md#45-header-list-size)). |
| `SETTINGS_MAX_FRAME_SIZE` | Any value HTTP/2 allows. |
| `GRPC_ALLOW_TRUE_BINARY_METADATA` (0xfe03) | See [True Binary Metadata](../../03-wire-protocol/02-true-binary-metadata.md). |

## 3. Streams

Each call attempt uses one client-initiated HTTP/2 stream. The mapping of
headers, messages, trailers, cancellation, and errors onto the stream is
specified in [gRPC over HTTP/2](../../03-wire-protocol/01-http2.md).

## 4. Stream Limits

> **Introduced by:** [gRFC A105: MAX_CONCURRENT_STREAMS Connection Scaling](https://github.com/grpc/proposal/blob/master/A105-max_concurrent_streams-connection-scaling.md)

### 4.1 Reporting to the Subchannel

A client transport MUST report the peer's `SETTINGS_MAX_CONCURRENT_STREAMS`
value to the subchannel that owns the connection, so the subchannel can decide
when to open more connections (see
[Subchannels and Connections: MAX_CONCURRENT_STREAMS Connection Scaling](../07-subchannels.md#8-max_concurrent_streams-connection-scaling)):

- It MUST report the value right after receiving the peer's initial SETTINGS
  frame.
- It MUST send an update whenever it receives a SETTINGS frame that changes
  this value.
- If the peer never sets the value, it is reported as unlimited
  ([RFC 9113 §6.5.2](https://www.rfc-editor.org/rfc/rfc9113#section-6.5.2)).

Implementations SHOULD apply flow control to these updates so the subchannel
is not sent updates faster than it can handle them. A simple approach that
keeps at most one update in flight:

```
on_peer_max_concurrent_streams_changed(value):
  current = value
  if not update_in_flight:
    send_update(current)

send_update(value):
  update_in_flight = true
  reported = value
  subchannel.report_max_concurrent_streams(value, on_done = on_update_processed)

on_update_processed():
  update_in_flight = false
  if current != reported:
    send_update(current)
```

So the subchannel may see an update some time after the transport does. With
an increase, the worst case is an unneeded extra connection. With a decrease,
the subchannel may send RPCs that exceed the new limit; see below.

### 4.2 RPCs Beyond the Limit

- The subchannel queues RPCs that cannot be sent because every connection is
  at its limit. Client transports therefore SHOULD NOT queue RPCs themselves.
- A transport can still get an RPC with no stream quota, when the server
  lowers `SETTINGS_MAX_CONCURRENT_STREAMS` after RPCs were dispatched. The
  transport SHOULD then fail the RPC with `UNAVAILABLE`, in a way that is
  eligible for transparent retry (no wire traffic was produced; see
  [Retries and Hedging](../12-retries.md)). It SHOULD NOT queue the RPC.
- Implementations MUST make sure this cannot loop forever: the transparent
  retry MUST NOT stop the subchannel from processing the transport's pending
  MAX_CONCURRENT_STREAMS update. No explicit synchronization is needed to
  delay the retry until the subchannel has seen the update.

## 5. Draining and Closure

### 5.1 Handling GOAWAY

Wire-level GOAWAY handling is in
[GOAWAY](../../03-wire-protocol/01-http2.md#92-goaway). At the
connection-management level, when a client transport receives GOAWAY:

1. The connection MUST stop accepting new RPCs right away. The transport tells
   its owner (the subchannel) that the connection can no longer be used for
   new RPCs, even though existing streams may continue.
2. The subchannel treats the connection as closed for new RPCs: it removes the
   connection from those it dispatches to, and if no usable connection is
   left it leaves READY. The subchannel state machine is in
   [Subchannels and Connections](../07-subchannels.md).
3. The load-balancing policy reacts to the subchannel state change, which
   typically includes asking for re-resolution. For example, pick_first moves
   the channel to IDLE when its selected subchannel's connection goes away.
   A new connection is made on the next RPC or when a connection is
   requested. See [Channel](../02-channel.md) and
   [Load Balancing](../06-load-balancing.md).
4. RPCs that raced with the GOAWAY (picked this connection, but their stream
   was refused or never created) are failed or re-queued so that they are
   transparently retried on another connection (see
   [Retries and Hedging](../12-retries.md)).
5. If the GOAWAY carries `ENHANCE_YOUR_CALM` and `too_many_pings`, the channel
   doubles its keepalive time for new connections
   ([Keepalive](#61-keepalive)).
6. The GOAWAY error code and debug data SHOULD be kept as the disconnect
   reason for logging, channelz, and metrics (see
   [Observability](../../08-observability/README.md)).

### 5.2 Connection Failure

How calls fail when the connection fails or closes with streams still open
is specified in
[Connection failure](../../03-wire-protocol/01-http2.md#94-connection-failure).
The transport tells the subchannel that the connection has closed, separately
from the GOAWAY notification in [Handling GOAWAY](#51-handling-goaway).

## 6. Liveness

Keepalive uses HTTP/2 PING frames to keep connections from being closed as
idle by intermediaries, and to detect dead connections. It is a per-hop
connection mechanism. It is separate from service health checking (see
[Client-Side Health Checking](../10-health-checking.md)).

The service owner decides what keepalive traffic it accepts. Client authors
MUST coordinate client keepalive settings with the service owner. A client
that pings more often than the server allows gets its connection closed (see
[HTTP/2 Server Transport: Ping Enforcement](../../05-server/02-transports/02-http2.md#72-ping-enforcement)).

### 6.1 Keepalive

> **Introduced by:** [gRFC A8: Client-side Keepalive](https://github.com/grpc/proposal/blob/master/A8-client-side-keepalive.md)

Client settings (per channel):

| Setting | Default | Rules |
| ------- | ------- | ----- |
| `KEEPALIVE_TIME` | infinite (disabled) | Time with no bytes read on the connection before the client sends a keepalive PING. Values below 10 seconds MUST be raised to 10 seconds. |
| `KEEPALIVE_TIMEOUT` | 20 seconds | After sending a keepalive PING, the time to wait for any bytes from the peer before declaring the connection dead. |
| `KEEPALIVE_WITHOUT_CALLS` | false | If true, keepalive PINGs are sent even when the connection has no active streams. |

Durations MUST support at least one-second precision. Applications SHOULD
set `KEEPALIVE_TIMEOUT` to several times the round-trip time, to allow for
lost packets and TCP retransmits, and possibly more to allow for long pauses
such as garbage collection. Implementations MAY adjust the timeout based on
observed network latency.

Behavior when `KEEPALIVE_TIME` is not infinite:

```
on connection established:
  last_read_time = now()
  arm keepalive timer for last_read_time + KEEPALIVE_TIME

on any bytes read from the connection:
  last_read_time = now()
  if ping outstanding: ping is satisfied (cancel watchdog)

on keepalive timer:
  if now() - last_read_time < KEEPALIVE_TIME:
    re-arm for last_read_time + KEEPALIVE_TIME
  else if active_streams == 0 and not KEEPALIVE_WITHOUT_CALLS:
    mark keepalive dormant (do not ping, do not re-arm)
  else:
    send PING; arm watchdog for now() + KEEPALIVE_TIMEOUT

on new stream created while dormant:
  if now() - last_read_time >= KEEPALIVE_TIME:
    send PING (ideally before the stream's HEADERS frame)
    arm watchdog for now() + KEEPALIVE_TIMEOUT
  resume the keepalive timer

on watchdog expiry (no bytes read since PING sent):
  close the connection; all calls on it fail with UNAVAILABLE
```

Rules:

- `KEEPALIVE_TIME` SHOULD be measured from the last byte read. An
  implementation MAY instead measure it from the last keepalive PING ACK
  (polling). If it does, it SHOULD guard against delay added by outbound
  buffering, for example by limiting outbound buffer size and using a larger
  `KEEPALIVE_TIMEOUT`.
- Implementations MUST NOT measure `KEEPALIVE_TIME` from the last PING sent.
  Doing so can trip abuse detection on servers configured to exactly match
  the client.
- A connection becoming active MUST NOT reset the keepalive timer. If a new
  stream is created and more than `KEEPALIVE_TIME` has passed since the last
  read, a PING is sent right away. Then a broken connection is detected
  within `KEEPALIVE_TIMEOUT`, not within `KEEPALIVE_TIME + KEEPALIVE_TIMEOUT`.
- When `KEEPALIVE_TIMEOUT` expires, an implementation MAY start a new
  connection before killing the old one. If the new connection becomes ready
  and the old one has still received no bytes, it closes the old one. If the
  old connection receives bytes first, it abandons the new connection during
  startup.

Receiving `too_many_pings`: when a client receives GOAWAY with error code
`ENHANCE_YOUR_CALM` and debug data `too_many_pings`, it:

1. MUST log the event at a log level that is enabled by default.
2. MUST double the `KEEPALIVE_TIME` the channel uses for new connections (if
   it is not infinite). The new value is twice the `KEEPALIVE_TIME` that the
   connection receiving the GOAWAY was using, and it replaces the channel's
   value only if it is larger. Doubling therefore repeats each time this
   happens and applies to all later connections the channel creates. No upper
   bound is defined beyond protecting against overflow.

### 6.2 TCP_USER_TIMEOUT

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
[HTTP/2 Server Transport: TCP_USER_TIMEOUT](../../05-server/02-transports/02-http2.md#73-tcp_user_timeout)).
A connection closed this way is a connection failure
([Connection failure](../../03-wire-protocol/01-http2.md#94-connection-failure)).

## 7. Flow Control

gRPC uses HTTP/2 flow control
([RFC 9113 §5.2](https://www.rfc-editor.org/rfc/rfc9113#section-5.2)) at both
the connection and the stream level, and implementations MUST implement it
as specified there, including the accounting of DATA frame padding
([RFC 9113 §6.1](https://www.rfc-editor.org/rfc/rfc9113#section-6.1); the
`data_frame_padding` negative interop test exercises this). gRPC adds no
flow-control requirements of its own: receive window sizes and when to send
WINDOW_UPDATE are up to each implementation. The same rules apply to servers
(see
[HTTP/2 Server Transport: Flow Control](../../05-server/02-transports/02-http2.md#8-flow-control)).

## 8. API Requirements

Client (channel) API:

- MUST provide a way to set `KEEPALIVE_TIME`, `KEEPALIVE_TIMEOUT`, and
  `KEEPALIVE_WITHOUT_CALLS`, with at least one-second precision.
- MUST provide a way to set the maximum header list size the client accepts.

Internal transport-to-subchannel API:

- The transport MUST provide a way to report the peer's current
  MAX_CONCURRENT_STREAMS value to the subchannel, with a completion signal so
  updates can be flow-controlled ([Reporting to the Subchannel](#41-reporting-to-the-subchannel)).
- The transport MUST provide a way to tell the subchannel that the connection
  can no longer be used for new RPCs (GOAWAY received) and, separately, that
  the connection has closed.
