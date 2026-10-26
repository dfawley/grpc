> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4.8.4 In-Process Client Transport

<!-- Sources: implementations (no gRFC or grpc/doc document specifies the in-process transport); doc/core/transport_explainer.md (informative) -->

The in-process transport connects a client channel to a server in the same
process without a network connection or a wire encoding. This document
specifies the client half. The server half is specified in
[In-Process Server Transport](../../05-server/02-transports/04-in-process.md).
The abstract behavior that every client transport provides is specified in
[Client Transport Model](01-transport-model.md).

## 1. Overview

An in-process connection is a pair of linked endpoints: a client transport,
owned by a subchannel, and a server transport, owned by the server. A stream
created on the client transport appears directly on the server transport. No
bytes are written to a socket, and there is no framing, header compression,
security handshake, or connection preface.

The in-process transport MUST preserve the
[Core RPC Semantics](../../02-rpc-semantics/README.md) as observed by
client and server applications: metadata, messages, half-close, status,
deadlines, cancellation, flow control, message size limits, and metadata size
limits behave as they do over a network transport, except where this document
says otherwise. Applications use it to test gRPC services end to end and to
call services hosted in the same process.

The following table summarizes how the in-process transport relates to a
network transport such as [HTTP/2 Client Transport](02-http2.md).

| Aspect | Network transport | In-process transport |
| --- | --- | --- |
| Connection establishment | Socket connect, security handshake, protocol setup | Lookup of a server in the same process ([Connection Establishment](#3-connection-establishment)) |
| Security | Channel credentials handshake | None; security level `PRIVACY_AND_INTEGRITY` ([Security](#31-security)) |
| Metadata | Encoded as header fields | Passed as structured metadata ([Metadata](#41-metadata)) |
| Messages | Serialized and length-prefixed | Passed as messages; serialization is not required ([Messages](#42-messages)) |
| Compression | Per message | Not applied ([Compression](#48-compression)) |
| Stream limits | Peer-advertised concurrent stream limit | None ([Stream Limits](#5-stream-limits)) |
| Draining | Peer sends `GOAWAY` | Server shutdown drains the connection ([Draining and Closure](#6-draining-and-closure)) |
| Liveness | Keepalive pings | Not needed ([Liveness](#7-liveness)) |
| Flow control | Byte-based windows | Message demand ([Flow Control](#8-flow-control)) |

## 2. Addressing

### 2.1 In-Process Server Addresses

A client reaches an in-process server through an **in-process address**. An
in-process address identifies one server in the same process in one of two
ways:

- **By name.** A server that accepts in-process connections registers a name
  that is unique within the process (see
  [Registration](../../05-server/02-transports/04-in-process.md#21-registration)).
  An address that carries a name refers to whichever server currently holds
  that name.
- **By direct reference.** An address is bound to exactly one server
  instance, without a name. A channel created from a reference to a server
  object is equivalent to a channel whose single address is bound to that
  server.

An in-process address is an ordinary resolved address. A channel created with
an in-process address uses it as its only address, without name resolution.
A resolver MAY return in-process addresses in its results (see
[Name Resolution](../03-name-resolution.md)), in which case they are
balanced and connected like any other address. The subchannel creates an
in-process client transport for an in-process address, and the transport
follows the [Client Transport Model](01-transport-model.md) like any other
transport.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-1]: C++: an in-process channel can only be created from a direct reference to a started server (grpc::Server::InProcessChannel / grpc_inproc_channel_create); it is a "direct channel" (GRPC_CLIENT_DIRECT_CHANNEL) bound to a single pre-created transport pair, with no resolver, LB policy, subchannel, or reconnection; there are no names. Java: InProcessChannelBuilder.forName (InProcessSocketAddress, looked up in a process-wide registry), forAddress(AnonymousInProcessSocketAddress) (bound to one server), and forTarget (custom resolver returning in-process addresses); all go through a normal ManagedChannel with resolver, LB policy, and subchannels that reconnect. spec says: both by name and by direct reference, as ordinary addresses handled by subchannels (Java model). -->

A channel that is created from an in-process address or a server reference
has no target URI. Where a target URI is needed (for example, for metrics),
the implementation synthesizes one.

### 2.2 Default Authority

For a channel created from an in-process address or a server reference, the
default authority is `localhost`. For a channel created from a target URI
whose resolver returns in-process addresses, the default authority follows the
normal rule ([Default Authority](../02-channel.md#31-default-authority)).
Authority overrides apply as they do for any channel. The authority of each
call is passed to the server unchanged and is visible to the server
application.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-2]: C++: default authority "inproc.authority" (GRPC_ARG_DEFAULT_AUTHORITY set in inproc_transport.cc / legacy_inproc_transport.cc). Java: "localhost" for forName/forAddress (ManagedChannelImplBuilder(directAddress, "localhost", ...)); target-derived for forTarget. spec says: "localhost". -->

## 3. Connection Establishment

A connection attempt on an in-process address does no I/O and runs no
security handshake. It replaces all steps of
[Connection Establishment](../07-subchannels.md#6-connection-establishment)
with a single lookup:

1. The transport finds the server that the address identifies.
2. If the server exists and is accepting connections, the server creates the
   matching server transport for the connection, and the client transport
   reports that it is ready. The attempt succeeds immediately; the subchannel
   becomes READY and its backoff is reset.
3. If no server holds the name, the server bound to the address has not
   started, or the server has begun shutting down, the attempt fails with
   status `UNAVAILABLE` and a message that identifies the address. The
   subchannel handles the failure like any other connection failure,
   including [Connection Backoff](../07-subchannels.md#7-connection-backoff).

A later attempt succeeds once a server holds the name. Proxy mapping and HTTP
CONNECT ([HTTP CONNECT Proxy Support](../09-proxy.md)) do not apply to
in-process addresses.

### 3.1 Security

The in-process transport runs no channel credentials handshake. Channel
credentials configured on the channel are not used for in-process
connections, and a channel MUST be creatable for in-process use without
channel credentials.

Because data never leaves the process, an in-process connection has security
level `PRIVACY_AND_INTEGRITY` ([Security Levels](../../06-security/01-security-model.md#5-security-levels)).
Call credentials are therefore applied to calls on in-process connections, and
their metadata reaches the server application like any other request
metadata. The connection's AuthContext
([AuthContext and Peer Identity](../../06-security/01-security-model.md#6-authcontext-and-peer-identity))
has no peer identity and no properties set by transport credentials.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-3]: Java: the client transport attributes set ATTR_SECURITY_LEVEL = PRIVACY_AND_INTEGRITY (InProcessTransport constructor), so call credentials requiring privacy are applied. C++: the in-process channel is created without a security connector, so ClientAuthFilter is not installed (registered only IfHasChannelArg(GRPC_ARG_SECURITY_CONNECTOR) in lib/surface/init.cc) and there is no AuthContext or security level on either side. spec says: PRIVACY_AND_INTEGRITY and call credentials applied. -->

### 3.2 Peer Information

On both sides, the peer address that gRPC reports to applications (and to
interceptors and observability plugins) is the in-process address of the
connection: for a named server, the server's name; for a server bound by
direct reference, a representation that identifies the connection as
in-process. The local address is the same in-process address.

The in-process transport has no socket. It reports no socket data to
[Channelz](../../08-observability/06-channelz.md).

<!-- REVIEW(divergence) [TRANSPORT-INPROC-4]: Java: TRANSPORT_ATTR_REMOTE_ADDR and TRANSPORT_ATTR_LOCAL_ADDR are the InProcessSocketAddress (or AnonymousInProcessSocketAddress) on both client and server (InProcessTransport constructor and start()). C++: the inproc transports never set PeerString, so the peer is empty/unknown on both sides. spec says: the in-process address on both sides (Java). Both report no channelz socket (C++ GetSocketNode() returns nullptr; Java getStats() returns null). -->

## 4. Streams

Each call attempt uses one stream, as in the
[Client Transport Model](01-transport-model.md#3-streams). Creating a stream
on the client transport delivers the request headers to the server transport,
which creates the matching server stream and hands it to the server for
dispatch. There is no round trip: messages and half-close sent by the client
after the headers are delivered in order behind them.

### 4.1 Metadata

Request headers, response headers, and trailers are passed between client and
server as structured metadata. They are not encoded as header fields: there
is no header compression, and binary metadata values are passed as bytes
without base64 encoding. Every key and value that the sender's gRPC library
passes to the transport arrives at the receiver's gRPC library unchanged, and
the values of a key keep their order.

The method name and authority of the call are carried with the request
headers. The client includes a `user-agent` as it does on other transports.
HTTP-specific request headers (`:method`, `:scheme`, `te`, and
`content-type`) have no meaning on an in-process stream; the server MUST NOT
reject an in-process stream because they are absent.

### 4.2 Messages

Each message is delivered to the receiver intact and in order. Messages are
not length-prefixed. The transport is not required to serialize messages: it
MAY hand the receiver the sender's message object, without serializing it, if
the message is immutable and the receiver decodes it with the same codec and
message type. Otherwise the transport passes the serialized message. Either
way, the message that the receiving application gets MUST be equal to the
message that the sending application sent.

### 4.3 Deadlines

The client passes the call's deadline to the server with the request headers.
Because client and server share a clock, the transport MAY pass it as an
absolute time instead of a timeout. The server's deadline for the call MUST be
the client's deadline. Both sides track and enforce the deadline as specified
in [Communication and Enforcement](../../02-rpc-semantics/README.md#82-communication-and-enforcement).

### 4.4 Status and Trailers

The status code, status message, and trailers that the server sends (including
`grpc-status-details-bin`) reach the client unchanged. The transport does not
map statuses through HTTP status codes. Only the status code, the message, and
the trailers are passed; any other information attached to a status object in
the server process (such as a local exception or cause) is not passed to the
client.

A server MAY send trailers without response headers; the client observes this
as it observes a Trailers-Only response on a network transport. The client
receives the status only after every message that the server sent before it,
as required by
[Ordering of Status, Reads, and Writes](../../02-rpc-semantics/README.md#11-ordering-of-status-reads-and-writes).

### 4.5 Cancellation

When the client cancels a stream, the server stream is cancelled at once, and
the server application is told that the call was cancelled
([Cancellation](../../02-rpc-semantics/README.md#4-cancellation)).
Messages that were sent but not yet delivered, in either direction, are
discarded.

When the server cancels a stream without sending a status (for example, when
the server's deadline for the call expires and it does not send trailers), the
client call fails with `CANCELLED`, as it does when an HTTP/2 server resets a
stream. When the whole connection is closed abruptly, open streams fail as
described in [Draining and Closure](#6-draining-and-closure).

<!-- REVIEW(divergence) [TRANSPORT-INPROC-5]: Java: server-side ServerStream.cancel() completes the client stream with CANCELLED "server cancelled stream" (InProcessServerStream.cancel). C++ (legacy inproc, the default): cancel_stream_locked passes the server's own cancellation error to the client side (other->cancel_other_error), so the client sees that error's status (for example DEADLINE_EXCEEDED). spec says: CANCELLED, matching RST_STREAM(CANCEL) on HTTP/2. -->

### 4.6 Message Size Limits

[Message Size Limits](../../02-rpc-semantics/README.md#12-message-size-limits)
apply to calls on in-process connections exactly as on other transports, with
the same defaults, configuration, and status codes. A message's size is its
serialized size, also when the transport passes the message without
serializing it.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-6]: C++: enforced, because the message size interceptor (ClientMessageSizeFilter on GRPC_CLIENT_DIRECT_CHANNEL, ServerMessageSizeFilter on GRPC_SERVER_CHANNEL; ext/filters/message_size/message_size_filter.cc) runs on in-process channels and the server. Java: not enforced; InProcessStream setMaxInboundMessageSize/setMaxOutboundMessageSize are no-ops and InProcessChannelBuilder.maxInboundMessageSize notes the limit is not enforced. spec says: enforced (core semantics require it). -->

### 4.7 Metadata Size Limits

The received-metadata size limits of
[Size Limits](../../02-rpc-semantics/README.md#76-size-limits) apply, with the
size computed by the same formula (the sum over all entries of key length plus
value length plus 32, binary values measured in base64 form):

- **Request headers** larger than the server's limit: the call fails with
  `RESOURCE_EXHAUSTED` and a message giving the limit and the size. The
  server does not dispatch the call. The check MAY be made by the client
  transport before the stream is delivered to the server.
- **Response headers** larger than the client's limit: the client call fails
  with `RESOURCE_EXHAUSTED`, and the server stream is cancelled.
- **Trailers** (with the status message counted toward their size) larger
  than the client's limit: the client call fails with `RESOURCE_EXHAUSTED`
  and receives no trailers. The server's view of the call is not changed.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-7]: Java: enforced in InProcessTransport (newStream checks request headers against the server's maxInboundMetadataSize; writeHeaders and close check response headers/trailers against the client's maxInboundMetadataSize; RESOURCE_EXHAUSTED; server sees CANCELLED for oversized response headers). C++: not enforced; the metadata size limit (GRPC_ARG_MAX_METADATA_SIZE) is enforced only by the HTTP/2 transport. spec says: enforced (Java). -->

### 4.8 Compression

A sender SHOULD NOT compress messages on an in-process stream, whatever
compression is configured for the channel, call, or server. This is allowed
by [Compression](../../02-rpc-semantics/README.md#13-compression), which lets
a sender send any message uncompressed. If a sender does compress a message,
the receiver MUST decompress it as on any other transport.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-8]: Java: compression is never applied; InProcessStream setCompressor/setDecompressor/setMessageCompression are no-ops, so messages are passed uncompressed. C++: the compression interceptors (ClientCompressionFilter on GRPC_CLIENT_DIRECT_CHANNEL, ServerCompressionFilter on the server; ext/filters/http/http_filters_plugin.cc) run on in-process channels, so configured compression is applied and undone. spec says: SHOULD NOT compress; receivers still decompress. -->

## 5. Stream Limits

The in-process transport has no limit on concurrent streams. It reports an
unlimited stream limit to the subchannel
([Stream Limits](01-transport-model.md#4-stream-limits)) and never queues a
stream for lack of capacity.

## 6. Draining and Closure

**Graceful.** When the server begins a graceful shutdown, the in-process
connection starts draining. The client transport reports this to the
subchannel as it reports a `GOAWAY` on a network transport
([Draining and Closure](01-transport-model.md#5-draining-and-closure)):

- The transport accepts no new streams. A stream created on it after it
  starts draining is not delivered to the server and fails with
  `UNAVAILABLE`.
- Streams already delivered to the server continue normally until they
  complete.
- When the last stream completes, the connection closes. The subchannel then
  leaves READY, and a later connection attempt fails while no server accepts
  connections for the address ([Connection Establishment](#3-connection-establishment)).

**Forced.** When the server is shut down forcibly, every open stream fails.
The client receives the status that the server's forced shutdown chooses
(`UNAVAILABLE`), and the connection closes
([Forced Shutdown](../../05-server/01-server.md#14-forced-shutdown)).

**Client-initiated.** When the channel closes the transport gracefully, open
streams continue and the server is notified that the connection has closed
when the last one completes. When the channel closes the transport forcibly,
every open stream is cancelled, and the server application sees each call
cancelled.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-9]: Java: server shutdown calls InProcessTransport.shutdown(UNAVAILABLE), which reports transportShutdown to the client (no new streams; new streams fail with the shutdown status) while existing streams finish, then transportTerminated; shutdownNow cancels every stream with the reason. C++ legacy inproc (the default): a GOAWAY or disconnect op calls close_transport_locked, which cancels every open stream with UNAVAILABLE "Transport closed", so server graceful shutdown aborts in-flight in-process calls. C++ promise-based inproc (experiment promise_based_inproc_transport): goaway is ignored by the transport, so existing calls continue and the server rejects new calls. spec says: graceful drain (Java, C++ promise-based). -->

## 7. Liveness

An in-process connection cannot fail silently, so the transport sends no
keepalive pings. Keepalive configuration on the channel has no effect on
in-process connections, and the transport never closes a connection for lack
of a ping response.

## 8. Flow Control

The in-process transport has no byte-based flow control windows. Flow control
([Flow Control](../../02-rpc-semantics/README.md#5-flow-control)) is based on
message demand: in each direction, the sender is ready to send only while the
receiver has requested a message that has not yet been delivered. A message
sent while the sender is not ready is held by the transport until the receiver
requests it. Half-close and trailers are delivered after any held messages on
the same stream. Flow control on one stream does not affect other streams.

## 9. Channel Features

Retries and hedging ([Retries and Hedging](../12-retries.md)) are disabled by
default on a channel created for in-process use, because retry buffer limits
are measured on serialized message sizes that an in-process channel does not
always know. The application MAY enable them through the channel API.
Interceptors, the service config, and wait-for-ready apply as on any channel.

<!-- REVIEW(divergence) [TRANSPORT-INPROC-10]: Java: InProcessChannelBuilder calls disableRetry() unless message-size tracing is enabled; applications can call enableRetry(). C++: the in-process direct channel has no client channel and so never retries (retries live in the client channel). spec says: disabled by default, application MAY enable (Java). -->

## 10. API Requirements

- The channel API MUST provide a way to create a channel to an in-process
  server identified by name.
- The channel API MUST provide a way to create a channel to a specific server
  instance by direct reference (for example, from the server object or from an
  address bound to that server).
- The channel API MUST allow creating a channel for in-process use without
  channel credentials.
- The resolver API MUST allow a resolver to return in-process addresses.
- The channel configuration that applies to other transports (interceptors,
  message size limits, received-metadata size limit, authority override, and
  service config) MUST apply to in-process channels.
