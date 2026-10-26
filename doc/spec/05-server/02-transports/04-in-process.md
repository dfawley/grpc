> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 5.2.4 In-Process Server Transport

<!-- Sources: implementations (no gRFC or grpc/doc document specifies the in-process transport); doc/core/transport_explainer.md (informative) -->

The in-process transport lets a server accept connections from client
channels in the same process without a network connection or a wire
encoding. This document specifies the server half. The client half, including
the behavior of streams that both halves share, is specified in
[In-Process Client Transport](../../04-client-channel/08-transports/04-in-process.md).
The abstract behavior that every server transport provides is specified in
[Server Transport Model](01-transport-model.md).

## 1. Overview

An in-process connection is a pair of linked endpoints: a client transport,
owned by a client subchannel, and a server transport, owned by the server.
Each stream that the client creates appears directly on the server transport,
which hands it to the server for dispatch like a stream from any other
transport ([Server Behavior](../01-server.md)).

The server applies its normal configuration to in-process connections: its
services and handlers, server interceptors, message size limits,
received-metadata size limit, and the rest of the request handling in
[Request Handling](../01-server.md#2-request-handling). Behavior that exists
only because of the network or the wire protocol (security handshakes,
header encoding, connection management timers, keepalive, and byte-based flow
control) does not apply.

## 2. Listening and Connection Establishment

### 2.1 Registration

Instead of listening on a network address, a server accepts in-process
connections through an **in-process address** (see
[In-Process Server Addresses](../../04-client-channel/08-transports/04-in-process.md#21-in-process-server-addresses)):

- **Named.** When the server starts, it registers a name in a registry shared
  by the whole process. Names are unique: if another server already holds the
  name, starting the server fails. The server releases the name when it
  begins shutting down, after which the name can be registered again.
- **By direct reference.** The server is reachable through an address bound
  to that server instance alone, or through a channel created from a
  reference to the server. An address bound by direct reference MUST NOT be
  bound to more than one server.

A server MAY accept in-process connections in addition to listening on
network addresses. The server's configuration applies to calls from every
source alike.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-11]: C++: any started grpc::Server, with or without network listening ports, can create in-process channels (Server::InProcessChannel), and in-process connections share the server's configuration (server channel args minus max connection idle/age). Java: in-process acceptance is a separate server built with InProcessServerBuilder (one InProcessServer listening on one InProcessSocketAddress or AnonymousInProcessSocketAddress; InProcessServer.registerInstance throws IOException "name already registered"); a server built for network ports does not accept in-process connections. spec says: a server MAY do both. -->

### 2.2 Accepting Connections

When a client transport connects to the server's in-process address, the
server creates the matching server transport and starts treating it as an
open connection. There is no security handshake and no handshake timeout.
Server credentials configured on the server are not used for in-process
connections.

If the server has not started, or has begun shutting down, it accepts no new
in-process connections; the client's connection attempt fails with
`UNAVAILABLE` (see
[Connection Establishment](../../04-client-channel/08-transports/04-in-process.md#3-connection-establishment)).

An in-process connection has security level `PRIVACY_AND_INTEGRITY`, its
AuthContext has no peer identity and no properties set by transport
credentials, and the peer and local addresses reported for its calls are the
connection's in-process address (see
[Security](../../04-client-channel/08-transports/04-in-process.md#31-security)
and [Peer Information](../../04-client-channel/08-transports/04-in-process.md#32-peer-information)).
The connection has no socket and reports no socket data to
[Channelz](../../08-observability/06-channelz.md).

## 3. Streams

Each stream on the server transport corresponds to one client call attempt.
The server transport delivers the request headers, the method name, the
authority, and the deadline to the server, which dispatches the call
([Method Dispatch](../01-server.md#22-method-dispatch)). It then delivers the
client's messages and half-close in order, and passes the server's response
headers, messages, status, and trailers back to the client. How metadata,
messages, deadlines, status, cancellation, message size limits, metadata size
limits, and compression behave on an in-process stream is specified in
[Streams](../../04-client-channel/08-transports/04-in-process.md#4-streams).
The points below are specific to the server:

- **Request validation.** HTTP-specific request validation in
  [Request Validation](../01-server.md#21-request-validation) (`content-type`,
  `:method`) does not apply; the server MUST NOT reject an in-process stream
  because HTTP-specific headers are absent. The checks that are not
  HTTP-specific (the received-metadata size limit and unsupported
  `grpc-encoding`) apply.
- **Deadlines.** The server's deadline for the call is the client's deadline
  ([Deadlines](../01-server.md#25-deadlines)).
- **Status.** The status code, status message, and trailers that the server
  application sends reach the client unchanged. Information attached to a
  status object in the server process beyond the code and message (such as a
  local exception or cause) does not reach the client.
- **Cancellation.** When the client cancels, the server call is cancelled at
  once and the handler observes it as in
  [Cancellation](../01-server.md#26-cancellation). When the server cancels a
  stream without sending a status, the client call fails with `CANCELLED`.

## 4. Stream Limits

The server transport enforces no limit on concurrent streams on an in-process
connection. A configured maximum number of concurrent streams per connection
does not apply to in-process connections.

## 5. Graceful Shutdown and Draining

**Graceful shutdown.** When the server begins a graceful shutdown
([Graceful Shutdown](../01-server.md#13-graceful-shutdown)):

1. The server stops accepting in-process connections and releases its name,
   if it has one.
2. Every open in-process connection starts draining
   ([Graceful Shutdown and Draining](01-transport-model.md#5-graceful-shutdown-and-draining)).
   The client transport accepts no new streams; a stream that the client
   creates after this point never reaches the server and fails with
   `UNAVAILABLE` on the client. No `GOAWAY` sequence is needed, because the
   client learns of the drain at once.
3. Calls already delivered to the server continue normally.
4. When a connection has no calls left, it closes. When every connection has
   closed, the server can terminate.

**Forced shutdown.** When the server is shut down forcibly
([Forced Shutdown](../01-server.md#14-forced-shutdown)), every in-flight call
on an in-process connection is cancelled, the handlers observe the
cancellation, and the client calls fail with `UNAVAILABLE`. The connections
then close.

**Client closure.** When the client closes the connection, the server is
notified that the connection has closed once its last call completes. Calls
that the client cancels are cancelled on the server.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-12]: Java: ServerImpl.shutdown unregisters the name (InProcessServer.shutdown) and calls InProcessTransport.shutdown(), which stops new streams while existing streams finish; shutdownNow calls shutdownNow(UNAVAILABLE) on each transport, cancelling every stream. C++ legacy inproc (the default): the server's shutdown broadcasts a GOAWAY, which the legacy transport handles by closing the transport and cancelling every in-flight stream with UNAVAILABLE "Transport closed" (legacy_inproc_transport.cc close_transport_locked), so graceful shutdown is not graceful for in-process calls. C++ promise-based inproc: goaway is ignored and calls continue. See also TRANSPORT-INPROC-9. spec says: graceful drain. -->

## 6. Connection Management

The server's connection management limits
([Connection Management](../01-server.md#5-connection-management)),
`MAX_CONNECTION_IDLE`, `MAX_CONNECTION_AGE`, and `MAX_CONNECTION_AGE_GRACE`,
do not apply to in-process connections. The server never closes an
in-process connection because of its idle time or age.

## 7. Liveness and Enforcement

The server sends no keepalive pings on in-process connections, and server
keepalive configuration has no effect on them. Because the client sends no
pings, there is nothing for keepalive enforcement to limit.

## 8. Flow Control

Flow control on an in-process connection is based on message demand, not on
byte-based windows. The server is ready to send a response message only while
the client has requested a message that has not yet been delivered, and the
client is ready to send a request message only while the server has requested
one. See [Flow Control](../../04-client-channel/08-transports/04-in-process.md#8-flow-control).
Server flow control window settings have no effect on in-process connections.

## 9. API Requirements

- The server API MUST provide a way to make a server accept in-process
  connections under a name, and MUST report a failure to start if the name is
  already registered in the process.
- The server API MUST provide a way to make a server reachable by direct
  reference without registering a name (for example, by creating an
  in-process channel from the server or by binding an anonymous in-process
  address to it).
- The server configuration that applies to other transports (services,
  server interceptors, message size limits, and received-metadata size limit)
  MUST apply to calls on in-process connections.
- Graceful and forced server shutdown MUST apply to in-process connections as
  specified in [Graceful Shutdown and Draining](#5-graceful-shutdown-and-draining).
