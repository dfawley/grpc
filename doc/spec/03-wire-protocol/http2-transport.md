> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 3.2 HTTP/2 Transport Behavior

<!-- Sources: A8, A9, A18, A105 (transport/subchannel interaction), A6 (transparent retry), doc/keepalive.md, doc/PROTOCOL-HTTP2.md, doc/http2-interop-test-descriptions.md (informative) -->

This section covers HTTP/2 connection behavior that is not part of the
per-call exchange in [gRPC over HTTP/2](http2.md): SETTINGS, flow control, keepalive, ping
abuse enforcement, server connection management, and how a client reacts to
GOAWAY.

## 1. Connection Establishment and SETTINGS

### 1.1 Establishment

- A client connection is established when the transport handshake (TCP, plus
  TLS or other security if configured) and the HTTP/2 connection preface are
  done. The preface completes when the client has received the server's
  initial SETTINGS frame.
- A connection MUST NOT be reported as usable for RPCs (for example, the
  subchannel moving to READY; see
  [Subchannels](../04-client-channel/subchannels.md)) before then.
- The client MUST ACK the server's SETTINGS frame, as HTTP/2 requires.

### 1.2 SETTINGS sent

Implementations follow HTTP/2 SETTINGS semantics
([RFC 9113 §6.5](https://www.rfc-editor.org/rfc/rfc9113#section-6.5)). In
addition:

| Setting | Behavior |
| ------- | -------- |
| `SETTINGS_ENABLE_PUSH` | gRPC does not use server push. Clients SHOULD send 0, and servers MUST NOT send PUSH_PROMISE. |
| `SETTINGS_MAX_CONCURRENT_STREAMS` | Servers MAY advertise a limit and MAY change it during the connection. Clients MUST NOT exceed the limit the peer advertised (see [MAX_CONCURRENT_STREAMS](#2-max_concurrent_streams)). |
| `SETTINGS_INITIAL_WINDOW_SIZE` | Sets the stream-level flow-control window (see [Flow Control](#3-flow-control)). |
| `SETTINGS_MAX_HEADER_LIST_SIZE` | Implementations SHOULD advertise the header list size limit they enforce ([Header list size](http2.md#45-header-list-size)). |
| `SETTINGS_MAX_FRAME_SIZE` | Any value HTTP/2 allows. |
| `GRPC_ALLOW_TRUE_BINARY_METADATA` (0xfe03) | See [True Binary Metadata](true-binary-metadata.md). |

Unknown settings MUST be ignored, as HTTP/2 requires.

## 2. MAX_CONCURRENT_STREAMS

### 2.1 Reporting to the subchannel

A client transport MUST report the peer's `SETTINGS_MAX_CONCURRENT_STREAMS`
value to the subchannel that owns the connection, so the subchannel can decide
when to open more connections (see
[Subchannels](../04-client-channel/subchannels.md)):

- It MUST report the value right after receiving the peer's initial SETTINGS
  frame.
- It MUST send an update whenever it receives a SETTINGS frame that changes
  this value.
- If the peer never sets the value, it is unlimited. HTTP/2 defines no default
  limit.

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

### 2.2 RPCs beyond the limit

- The subchannel queues RPCs that cannot be sent because every connection is
  at its limit. Client transports therefore SHOULD NOT queue RPCs themselves.
- A transport can still get an RPC with no stream quota, when the server
  lowers `SETTINGS_MAX_CONCURRENT_STREAMS` after RPCs were dispatched. The
  transport SHOULD then fail the RPC with `UNAVAILABLE`, in a way that is
  eligible for transparent retry (no wire traffic was produced; see
  [Retries](../04-client-channel/retries.md)). It SHOULD NOT queue the RPC.
- Implementations MUST make sure this cannot loop forever: the transparent
  retry MUST NOT stop the subchannel from processing the transport's pending
  MAX_CONCURRENT_STREAMS update. No explicit synchronization is needed to
  delay the retry until the subchannel has seen the update.

## 3. Flow Control

gRPC uses HTTP/2 flow control
([RFC 9113 §5.2](https://www.rfc-editor.org/rfc/rfc9113#section-5.2)) at both
the connection and the stream level. Implementations MUST follow it exactly.
That includes counting DATA frame padding against the windows and returning
that credit (the `data_frame_padding` negative interop test exercises this).
gRPC adds no flow-control requirements of its own. Receive window sizes and
when to send WINDOW_UPDATE are up to each implementation, within HTTP/2's
rules.

## 4. Keepalive

Keepalive uses HTTP/2 PING frames to keep connections from being closed as
idle by intermediaries, and to detect dead connections. It is a per-hop
connection mechanism. It is separate from service health checking (see
[Health checking](../04-client-channel/health-checking.md)).

The service owner decides what keepalive traffic it accepts. Client authors
MUST coordinate client keepalive settings with the service owner. A client
that pings more often than the server allows gets its connection closed (see
[Server ping enforcement](#43-server-ping-enforcement)).

### 4.1 Client keepalive

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

### 4.2 Server keepalive

Server settings:

| Setting | Default | Rules |
| ------- | ------- | ----- |
| `KEEPALIVE_TIME` | 2 hours | Same meaning as on the client. |
| `KEEPALIVE_TIMEOUT` | 20 seconds | Same meaning as on the client. |

Server keepalive works like client keepalive
([Client keepalive](#41-client-keepalive)), except that the server sends keepalive
PINGs whether or not the connection has outstanding RPCs. When the watchdog
expires, the server closes the connection and cancels its calls on that
connection.

### 4.3 Server ping enforcement

Servers MUST protect themselves from clients that ping too often. Server
settings:

| Setting | Default | Meaning |
| ------- | ------- | ------- |
| `PERMIT_KEEPALIVE_TIME` | 5 minutes | Minimum interval between client PINGs that the server allows while the connection has active streams (or always, if the next setting is true). |
| `PERMIT_KEEPALIVE_WITHOUT_CALLS` | false | If false, the minimum interval with no active streams is 2 hours. If true, `PERMIT_KEEPALIVE_TIME` applies even with no active streams. |
| `MAX_PING_STRIKES` | 2 | Number of bad PINGs tolerated. A bad PING received after this many strikes (so strike number `MAX_PING_STRIKES + 1`) means the client is misbehaving. Implementations MAY make it configurable (see [API Requirements](#7-api-requirements)); if they do, a value of 0 SHOULD mean unlimited. |

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

### 4.4 TCP_USER_TIMEOUT

On platforms that support the `TCP_USER_TIMEOUT` socket option (Linux 2.6.37
and later):

- When keepalive is enabled (`KEEPALIVE_TIME` is not infinite), the
  implementation MUST set `TCP_USER_TIMEOUT` on the connection's socket to
  `KEEPALIVE_TIMEOUT`. With the default, that is 20 seconds. The timeout then
  bounds how long any sent data, not just a PING, may stay unacknowledged
  before the kernel closes the connection.
- When keepalive is disabled, `TCP_USER_TIMEOUT` is not set, and the system
  default applies.

This applies to clients and servers alike. Servers have keepalive enabled by
default (2 hours), so by default server sockets get a 20-second
`TCP_USER_TIMEOUT`. A connection closed this way is a connection failure
([Connection failure](http2.md#94-connection-failure)).

## 5. Server Connection Management

Server settings:

| Setting | Default | Meaning |
| ------- | ------- | ------- |
| `MAX_CONNECTION_IDLE` | infinite | Close a connection after it has been idle this long. Idle time is measured from the later of connection establishment and the last time the number of outstanding RPCs dropped to zero. |
| `MAX_CONNECTION_AGE` | infinite | Close a connection once it has existed this long. A random per-connection jitter of ±10% MUST be applied, to spread out reconnection storms. |
| `MAX_CONNECTION_AGE_GRACE` | infinite | After the age-triggered graceful shutdown starts, the longest time outstanding RPCs may run before the connection is forcibly closed. No jitter is applied. |

Procedure:

- When `MAX_CONNECTION_IDLE` is reached, the server sends GOAWAY with
  `NO_ERROR` and debug data `max_idle`, then continues the graceful shutdown
  ([GOAWAY](http2.md#92-goaway)).
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
[Channel](../04-client-channel/channel.md)), clients do not close
individual connections because they are idle (see
[Subchannels](../04-client-channel/subchannels.md)), so servers that want
idle connections cleaned up SHOULD set `MAX_CONNECTION_IDLE`.

These timers do not need to be precise. Implementations MAY implement them
coarsely. Server shutdown also uses graceful GOAWAY; see
[Server](../05-server/README.md).

## 6. Client Handling of GOAWAY

Wire-level GOAWAY handling is in [GOAWAY](http2.md#92-goaway). At the
connection-management level, when a client transport receives GOAWAY:

1. The connection MUST stop accepting new RPCs right away. The transport tells
   its owner (the subchannel) that the connection can no longer be used for
   new RPCs, even though existing streams may continue.
2. The subchannel treats the connection as closed for new RPCs: it removes the
   connection from those it dispatches to, and if no usable connection is
   left it leaves READY. The subchannel state machine is in
   [Subchannels](../04-client-channel/subchannels.md).
3. The load-balancing policy reacts to the subchannel state change, which
   typically includes asking for re-resolution. For example, pick_first moves
   the channel to IDLE when its selected subchannel's connection goes away.
   A new connection is made on the next RPC or when a connection is
   requested. See [Channel](../04-client-channel/channel.md) and
   [Load Balancing](../04-client-channel/load-balancing.md).
4. RPCs that raced with the GOAWAY (picked this connection, but their stream
   was refused or never created) are failed or re-queued so that they are
   transparently retried on another connection (see
   [Retries](../04-client-channel/retries.md)).
5. If the GOAWAY carries `ENHANCE_YOUR_CALM` and `too_many_pings`, the channel
   doubles its keepalive time for new connections
   ([Client keepalive](#41-client-keepalive)).
6. The GOAWAY error code and debug data SHOULD be kept as the disconnect
   reason for logging, channelz, and metrics (see
   [Observability](../08-observability/README.md)).

## 7. API Requirements

Client (channel) API:

- MUST provide a way to set `KEEPALIVE_TIME`, `KEEPALIVE_TIMEOUT`, and
  `KEEPALIVE_WITHOUT_CALLS`, with at least one-second precision.
- MUST provide a way to set the maximum header list size the client accepts.

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

Internal transport-to-subchannel API:

- The transport MUST provide a way to report the peer's current
  MAX_CONCURRENT_STREAMS value to the subchannel, with a completion signal so
  updates can be flow-controlled ([Reporting to the subchannel](#21-reporting-to-the-subchannel)).
- The transport MUST provide a way to tell the subchannel that the connection
  can no longer be used for new RPCs (GOAWAY received) and, separately, that
  the connection has closed.

