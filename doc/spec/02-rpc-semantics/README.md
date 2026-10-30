> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 2. Core RPC Semantics

<!-- Sources: doc/PROTOCOL-HTTP2.md, doc/statuscodes.md, doc/status_ordering.md, doc/wait-for-ready.md, doc/fail_fast.md, doc/compression.md, doc/compression_cookbook.md, doc/internationalization.md, doc/http-grpc-status-mapping.md, doc/service_config.md, grpc-proto grpc/service_config/service_config.proto, A6, A31, A54 -->

This section defines the semantics of gRPC RPCs independently of any
transport. The mapping of these concepts onto HTTP/2 is defined in
[gRPC over HTTP/2](../03-wire-protocol/01-http2.md). Implementations SHOULD
support the HTTP/2 transport, because it is the basis for interoperability.

## 1. Channels and Servers

Implementations have a **channel** concept and a **server** concept.

A **channel** is a virtual connection to an endpoint and is capable of sending
RPCs. It is "virtual" because it may have zero or many actual connections. A
channel decides which actual endpoint to use and MAY choose a different
endpoint for every RPC, which permits client-side load balancing. Channels
are specified in [Client Channel](../04-client-channel/README.md).

A **server** receives incoming connections and RPCs. Servers are specified in
[Server](../05-server/README.md).

A "connection" is not a gRPC semantic concept. Applications MUST NOT assume a
correlation between connections and RPCs. In practice, an RPC cannot outlive
the connection that carries it.

## 2. Methods and Services

An RPC is performed on a **method**. A method has a name and defines:

- the intended operation (documentation for developers; gRPC is not aware of
  it);
- a request message type and a separate response message type;
- the cardinality of the request and of the response.

A method does not define the endpoint to which an RPC is sent. The channel
handles that.

gRPC knows the request and response types only well enough to serialize and
deserialize them through a codec (see [Codecs and Content-Subtype](#17-codecs-and-content-subtype)).
To gRPC, a message is an opaque byte sequence of known length. Zero-length
messages are valid.

### 2.1 RPC Types

The request and the response each have a cardinality: exactly one message
("unary") or zero or more messages ("streaming"). The four combinations have
names:

|                       | **Unary response** | **Streaming response** |
| --------------------- | ------------------ | ---------------------- |
| **Unary request**     | unary              | server-streaming       |
| **Streaming request** | client-streaming   | bidirectional streaming (bidi) |

A method is not object-oriented. Apart from the destination server, there is
no "receiver" (no `this`). gRPC is based on message passing.

### 2.2 Services and Full Method Names

Related methods are grouped into a **service**. A service is a group of
methods that are usually implemented together and that share the service's
namespace. A service may not be explicitly represented in every API, but its
namespace is part of each method's identity: two methods with the same name in
different services are distinct and MUST NOT be confused.

The **full method name** is the full service name, a `/`, and the method
name:

```
full-method-name = full-service-name "/" short-method-name
```

The **full service name** is defined by the IDL. For Protocol Buffers it is
the package name, a `.`, and the service name, or only the service name if
there is no package (see [Protocol Buffers Mapping](../03-wire-protocol/04-protobuf.md)). Full method
names are case-sensitive. They MUST consist only of ASCII characters that are
valid in HTTP/2 header values (see [Internationalization](#77-internationalization)). The
short method name MUST NOT contain `/`. On HTTP/2 the full method name appears
in the `:path` header as `/` + full method name. Features that match on method
names, such as service config method matching, assume this form.

## 3. Calls

RPCs, or **calls**, are started by a client to a server, usually through a
channel. Several servers might be able to receive a call (for example, behind
a load balancer), but only one server processes any one call. Call attempts
created by retries or hedging are a separate concept; see
[Retries and Hedging](../04-client-channel/12-retries.md).

### 3.1 Two Independent Streams

A call consists of two independent, unidirectional streams that run in
parallel (full duplex):

- The **request stream** (client to server) starts with **request headers**,
  carries zero or more **request messages**, and ends with **half-close**.
- The **response stream** (server to client) starts with **response headers**,
  carries zero or more **response messages**, and ends with **trailers**. A
  response stream MAY consist of trailers only (**trailers-only**), with no
  response headers and no messages.

Request headers, response headers, messages, half-close, and trailers are the
units of communication. Unless the call terminates, each unit is communicated
to the remote side without the sender needing to send further units on that
stream. The permitted unary optimizations in [Unary Calls](#6-unary-calls) are an
exception.

The contents of the units are:

| Unit | Contents |
|------|----------|
| Request headers | Full method name and metadata. The deadline (as a timeout), authority, message encoding, accepted encodings, and content-subtype also travel here. |
| Request message | One message payload. |
| Half-close | Nothing. Indicates the client will send no more messages. |
| Response headers | Metadata, plus the response message encoding and accepted encodings. |
| Response message | One message payload. |
| Trailers | Status (code, message, and optional details) and metadata. |

This list is not exhaustive. gRPC features MAY add fields to request headers,
response headers, and trailers.

When the response is trailers-only, the trailers take the place of the response
headers too. The client application MUST still be able to ask for response
headers. In this case they are empty (contain no application metadata).

Units within one stream are delivered in order. The two streams are not
ordered with respect to each other, except that nothing is delivered after
the call completes.

### 3.2 Initiation and Graceful Completion

A client starts a call by sending request headers, which name the method by its
full method name.

A call **completes gracefully** when the server sends trailers. The status in
the trailers reports whether the RPC succeeded. If the server sends trailers
before it has received the client's half-close, any client messages and
half-close that the server has not processed are lost.

On the server, time passes between the server application supplying trailers
and the trailers actually being sent. The call is complete on the server only
when the trailers are sent. On the client, time passes between the
implementation receiving trailers and the application receiving them. The
call is complete on the client only when the application receives the
trailers.

### 3.3 Server Response Headers

A server SHOULD delay sending response headers until the first response message
is sent or the server application explicitly asks for headers to be sent. If the
server application completes the call with a status before headers or any
response message are sent, the server SHOULD send trailers-only.

Note: Receiving response headers commits a call on the client, so it can no
longer be retried (see [Retries and Hedging](../04-client-channel/12-retries.md)). Delaying headers
keeps calls retryable for longer.

## 4. Cancellation

A call MAY terminate early by being **cancelled**. Implementations MUST allow
client applications to cancel calls. Cancellation also happens for other
reasons, such as deadline expiry, I/O failure, or connection loss.

- To the client application, cancellation appears as trailers with status code
  `CANCELLED` (or another status describing the cause, for example
  `DEADLINE_EXCEEDED`, see [Deadline Expiry and Cancellation Races](#84-deadline-expiry-and-cancellation-races),
  or `UNAVAILABLE` for a lost connection).
- To the server application, cancellation is a distinct state. It is not a
  status. The server application MUST be able to find out that the call was
  cancelled (see [Server Call API](#182-server-call-api)).

Cancellation abruptly ends the call. Inbound and outbound buffered data SHOULD
be discarded. Cancellation signals between client and server carry no extra
information.

Cancellation takes priority over graceful completion. If the client
implementation has received trailers but the client application has not yet
received them when the call is cancelled, cancellation SHOULD win, and the
application SHOULD see the cancellation status.

A server implementation MAY fail a call by sending trailers with a non-OK
status while telling the server application that the call was cancelled (for
example, when it exceeds a server limit).

Cancelling a call that has already completed has no effect.

## 5. Flow Control

Each stream carries information in one direction only, except for **flow
control**. Flow control is a signal from the receiver to the sender to pause
sending more messages for a while, so that the receiver does not have to buffer
too much.

- Flow control applies only to messages. Because a stream is in order,
  half-close or trailers may be delayed behind messages that are waiting for
  flow control on the same stream.
- Flow control does not acknowledge receipt of messages. Applications that need
  acknowledgement can send messages for it; a response naturally acknowledges
  its request.
- In particular, a server application cannot know whether the client
  application received a unary call's response or a streaming call's status.

Flow control is local to each call and is not visible on other calls. Transport
flow control (for example HTTP/2 stream and connection windows) is specified in
[HTTP/2 Client Transport: Flow Control](../04-client-channel/08-transports/02-http2.md#7-flow-control) and
[HTTP/2 Server Transport: Flow Control](../05-server/02-transports/02-http2.md#8-flow-control).

## 6. Unary Calls

A call whose request is unary MAY be treated as half-duplex, with each
direction as a single unit:

- On the client, sending the request headers MAY be delayed until the request
  message and half-close are ready to be sent.
- On the server, sending the response headers and message MAY be delayed until
  the trailers are ready.

A call whose response is unary and that ends with status `OK` MUST contain
exactly one response message. A call whose response is unary and that ends
with a non-OK status does not need a response message. If one is present, the
implementation MAY discard it.

A call whose request is unary MUST contain exactly one request message.

Violations are handled as follows:

| Violation | Detected by | Result |
|-----------|-------------|--------|
| Client sends zero or more than one message on a unary-request method | Server | Server fails the call with `INTERNAL`. |
| Server sends zero messages with status `OK`, or more than one message, on a unary-response method | Client | Client fails the call with `INTERNAL`. |

## 7. Metadata

**Metadata** is a multimap of keys to values. It is carried in request
headers, response headers, and trailers.

### 7.1 Keys

- Keys are case-insensitive. Implementations MUST canonicalize keys by
  converting them to lowercase before they are sent. APIs MAY require
  applications to supply keys in canonical (lowercase) form.
- Keys MUST consist only of the characters `0`-`9`, `a`-`z`, `_`, `-`, and
  `.` (after canonicalization). Keys MUST NOT be empty.
- A key whose name ends in `-bin` is a **binary** key. All other keys are
  **ASCII** keys.
- Keys are unordered with respect to each other. The order of values for one
  key is preserved.

### 7.2 Values

- **ASCII values** consist of printable ASCII characters and space (`%x20`-`%x7E`).
  Values SHOULD NOT have leading or trailing whitespace. If a value has leading
  or trailing whitespace, implementations MAY strip it.
- **Binary values** are arbitrary byte sequences. The wire encoding (for
  example, base64 on HTTP/2) is handled by the implementation and is
  transparent to applications. See [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) and
  [True Binary Metadata](../03-wire-protocol/02-true-binary-metadata.md).
- If an implementation receives an ASCII value outside the gRPC character range
  but valid as an HTTP field value, it MUST NOT fail the call. It MAY discard
  the value or accept it. If it accepts the value, it MUST allow the application
  to send that same value back as metadata without error (for example, by
  echoing received metadata into a response).

### 7.3 Multiple Values

A key MAY have multiple values. For ASCII keys, multiple values MAY be joined
into one value with `,` as the delimiter, and the result is semantically
equivalent to the multi-valued form. The reverse does not hold in general: an
arbitrary ASCII value MUST NOT be split on `,` and assumed equivalent to a
multi-valued form, unless the key's definition says so.

For binary keys, implementations MUST split a received value on `,` before
decoding each part, and MUST present the parts to the application as separate
values.

### 7.4 Headers versus Trailers

Whether metadata is in headers or in trailers is semantically significant.
Metadata in headers MUST NOT be moved to trailers, or the other way around,
unless the semantics of the specific key are known to allow it. For a
trailers-only response, the metadata is trailing metadata.

### 7.5 Reserved Keys

- Keys beginning with `grpc-` are reserved for gRPC. Applications MUST NOT use
  `grpc-` keys as custom metadata, except for keys that this specification
  explicitly allows applications to set. Implementations SHOULD NOT pass
  reserved keys used by the implementation itself (for example `grpc-timeout`,
  `grpc-encoding`, `grpc-status`, `grpc-message`) to the application as
  metadata.
- Transport-level headers (for example HTTP/2 pseudo-headers, `content-type`,
  `te`, and connection-specific headers) are not application metadata. The
  rules for them are in [gRPC over HTTP/2](../03-wire-protocol/01-http2.md).
- Every key with a gRPC-defined meaning is listed in
  [Appendix A](../appendices/a-metadata-keys.md).

If an application tries to send a key or ASCII value that is invalid under
[Keys](#71-keys) or [Values](#72-values), the implementation MUST NOT
transmit it. It SHOULD report an error to the application (for example, by
failing the call or the metadata operation). It MAY instead drop the entry.

If an application supplies a reserved key that the implementation itself
sets (for example `content-type`, `te`, `grpc-encoding`, `grpc-status` and
`grpc-message` in trailers, or `grpc-timeout` when the call has a deadline),
the implementation's value MUST be sent and the application's value MUST NOT
be sent. Applications MUST NOT rely on any other reserved key being either
transmitted or dropped.

### 7.6 Size Limits

Implementations MAY limit the total size of the metadata in request headers,
response headers, and trailers. The total is computed as defined for HTTP/2's
`SETTINGS_MAX_HEADER_LIST_SIZE`
([RFC 9113 §6.5.2](https://www.rfc-editor.org/rfc/rfc9113#section-6.5.2)),
with binary values measured in their encoded (base64) form. Implementations
SHOULD provide a safe default limit for received metadata. The value of the
default is up to the implementation. The limit MUST be configurable through
the channel and server APIs.

A server that receives request headers over its limit SHOULD fail the call with
`RESOURCE_EXHAUSTED`. A client that receives response headers or trailers over
its limit SHOULD fail the call with `RESOURCE_EXHAUSTED`. Transport-level
enforcement is specified in [HTTP/2 Client Transport: SETTINGS](../04-client-channel/08-transports/02-http2.md#22-settings) and
[HTTP/2 Server Transport: SETTINGS](../05-server/02-transports/02-http2.md#21-settings).

### 7.7 Internationalization

| Element | Allowed content | Notes |
|---------|-----------------|-------|
| Method name | ASCII only; characters allowed in HTTP/2 header values | No encoding or decoding is applied. |
| Host name / authority | ASCII; internationalized names in punycode | The application is responsible for punycode-encoding an internationalized host name. |
| Status message | Any Unicode string | Encoded on the wire as UTF-8 followed by percent-encoding (see [gRPC over HTTP/2](../03-wire-protocol/01-http2.md)). APIs SHOULD represent it as a Unicode string. |
| Metadata key | As defined in [Keys](#71-keys) | |
| ASCII metadata value | As defined in [Values](#72-values) | Non-ASCII data MUST be sent with a binary (`-bin`) key or encoded by the application. |
| Binary metadata value | Arbitrary bytes | |

## 8. Deadlines

A **deadline** is the point in time by which a call must complete before the
client gives up. A call is not required to have a deadline. A call without a
deadline does not complete until it fails or finishes successfully.

### 8.1 Effective Deadline

The deadline used for a call is the earliest of:

- the deadline set by the client application, if any;
- the timeout from the call's per-call configuration, applied from the start of
  the call. This configuration is either the matching method config's
  `timeout` field in the service config (`grpc/service_config/service_config.proto`,
  a `google.protobuf.Duration`, JSON string such as `"1.5s"`) or a timeout
  supplied by a ConfigSelector, such as the xDS route `max_stream_duration`
  (see [Per-call Configuration and Call Flow](../04-client-channel/05-call-dispatch.md) and [Client Data Plane](../09-xds/05-client.md)).

If only one is set, that one is used. If neither is set, the call has no
deadline.

The deadline covers the entire call, including name resolution, waiting for a
connection, every retry or hedging attempt, and backoff between attempts.

### 8.2 Communication and Enforcement

If a call has a deadline, the client MUST include it in the request headers.
It is sent as a **timeout**: the time remaining until the deadline when the
headers are sent. A duration avoids the need for synchronized clocks. The
encoding (`grpc-timeout`) is defined in [gRPC over HTTP/2](../03-wire-protocol/01-http2.md). A
server that receives no timeout MUST treat the call as having no deadline.

Both client and server MUST track the deadline:

- When the deadline passes on the client, the client MUST cancel the call and
  complete it with status `DEADLINE_EXCEEDED`.
- When the deadline passes on the server, the server MUST cancel the call and
  tell the server application that the call is cancelled. If it has not
  already sent trailers, the server MAY send trailers with status
  `DEADLINE_EXCEEDED`. If it does not, it MUST abort the stream (on HTTP/2,
  `RST_STREAM` with `CANCEL`) if the stream is not already closed. See
  [gRPC over HTTP/2](../03-wire-protocol/01-http2.md).
- If the deadline has already passed when the client application starts the
  call, the client MUST fail the call with `DEADLINE_EXCEEDED` without sending
  it.

### 8.3 Deadline Propagation

A server application often makes outgoing calls while serving an incoming
call. The incoming call's deadline SHOULD apply to those outgoing calls, and
cancellation of the incoming call SHOULD cancel them.
The API MUST provide a way to propagate an incoming call's deadline and
cancellation to outgoing calls. Propagation SHOULD be the default behavior
when an outgoing call is made in the context of an incoming call, provided
the language API has a way to express that context.

### 8.4 Deadline Expiry and Cancellation Races

Client and server deadlines differ slightly, and their detection of expiry
races. If a client receives a cancellation from the server (for example, an
HTTP/2 `RST_STREAM` with `CANCEL`) on a call that has a deadline, it MUST check
whether the deadline has passed. If it has, the client MUST report status
`DEADLINE_EXCEEDED` instead of the cancellation status.

## 9. Authority

Virtual hosting lets a server have several identities and serve different
services depending on the identity. An identity is a server name in `host` or
`host:port` form, as used in the authority component of a URI.

Each call has an **authority**: the name by which the client identifies the
service. Transports that support virtual hosting MUST send the authority, and
the server MUST make it available to the server application as part of the
request headers. On HTTP/2 this is the `:authority` pseudo-header.

By default the channel chooses the authority from the target (see
[Channel](../04-client-channel/02-channel.md)). The client API MUST provide a way to
override the authority per call. When the connection is secured, the
overriding authority MUST, by default, be validated against the server's
identity before the call is sent (credentials may provide an option to disable
this check). If validation fails, the call fails with `UNAVAILABLE`. See
[TLS](../06-security/02-tls.md).

## 10. Status

Every call completes with a **status**. A status has:

- a **code** from the fixed list in [Status Codes](#101-status-codes);
- a **message**: a human-readable Unicode string intended for developers. It
  MAY be empty;
- optional **details** (see [Rich Error Details](#105-rich-error-details)).

Status codes are best shown to users by name. Internally they are commonly
handled as integers, so each code has a number.

### 10.1 Status Codes

| Code | Number | Meaning |
|------|--------|---------|
| `OK` | 0 | Not an error; returned on success. |
| `CANCELLED` | 1 | The operation was cancelled, typically by the caller. |
| `UNKNOWN` | 2 | Unknown error. For example, this error may be returned when a status received from another address space belongs to an error space that is not known in this address space. Errors raised by APIs that do not return enough error information may also be converted to this error. |
| `INVALID_ARGUMENT` | 3 | The client specified an invalid argument. This differs from `FAILED_PRECONDITION`: `INVALID_ARGUMENT` indicates arguments that are problematic regardless of the state of the system (for example, a malformed file name). |
| `DEADLINE_EXCEEDED` | 4 | The deadline expired before the operation could complete. For operations that change the state of the system, this error may be returned even if the operation has completed successfully; for example, a successful response from a server could have been delayed long enough for the deadline to expire. |
| `NOT_FOUND` | 5 | Some requested entity (for example, a file or directory) was not found. If a request is denied for an entire class of users, such as during a gradual feature rollout or by an undocumented allowlist, `NOT_FOUND` may be used. If a request is denied for some users within a class of users, such as by user-based access control, `PERMISSION_DENIED` must be used. |
| `ALREADY_EXISTS` | 6 | The entity that a client attempted to create (for example, a file or directory) already exists. |
| `PERMISSION_DENIED` | 7 | The caller does not have permission to execute the specified operation. It must not be used for rejections caused by exhausting some resource (use `RESOURCE_EXHAUSTED`), or if the caller cannot be identified (use `UNAUTHENTICATED`). It does not imply that the request is valid, that the requested entity exists, or that other preconditions are satisfied. |
| `RESOURCE_EXHAUSTED` | 8 | Some resource has been exhausted, perhaps a per-user quota, or perhaps the entire file system is out of space. |
| `FAILED_PRECONDITION` | 9 | The operation was rejected because the system is not in a state required for the operation's execution. For example, the directory to be deleted is non-empty, or an rmdir operation is applied to a non-directory. To choose between `FAILED_PRECONDITION`, `ABORTED`, and `UNAVAILABLE`: (a) use `UNAVAILABLE` if the client can retry just the failing call; (b) use `ABORTED` if the client should retry at a higher level (for example, when a client-specified test-and-set fails, so the client should restart a read-modify-write sequence); (c) use `FAILED_PRECONDITION` if the client should not retry until the system state has been explicitly fixed. |
| `ABORTED` | 10 | The operation was aborted, typically due to a concurrency issue such as a sequencer check failure or transaction abort. See the guidance under `FAILED_PRECONDITION`. |
| `OUT_OF_RANGE` | 11 | The operation was attempted past the valid range, for example seeking or reading past end-of-file. Unlike `INVALID_ARGUMENT`, this error indicates a problem that may be fixed if the system state changes. `OUT_OF_RANGE` is recommended over `FAILED_PRECONDITION` when it applies, so that callers iterating through a space can easily detect when they are done. |
| `UNIMPLEMENTED` | 12 | The operation is not implemented or is not supported or enabled in this service. |
| `INTERNAL` | 13 | Internal errors. Some invariants expected by the underlying system have been broken. This code is reserved for serious errors. |
| `UNAVAILABLE` | 14 | The service is currently unavailable. This is most likely a transient condition that can be corrected by retrying with a backoff. It is not always safe to retry non-idempotent operations. |
| `DATA_LOSS` | 15 | Unrecoverable data loss or corruption. |
| `UNAUTHENTICATED` | 16 | The request does not have valid authentication credentials for the operation. |

Applications SHOULD use only the codes defined above. If an implementation
receives a code outside this range, it SHOULD pass it to the application
unchanged if its API can represent it, and otherwise MUST convert it to
`UNKNOWN`.

### 10.2 OK Is Decided by the Server Application

Only the server application decides that a call ends with `OK`. Implementations
MUST NOT fabricate an `OK` status. They may only pass on an `OK` status that was
given to them. For example, a client that receives a response without a status
MUST NOT report `OK` (see [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) for how such
responses are mapped).

### 10.3 Status Codes Generated by gRPC

The server application chooses the status it returns. The client and server
implementations also generate statuses themselves when errors occur. They use
only a subset of the codes, so an application can be sure that any other code
came from the server application. A server application MAY also return the
codes that gRPC generates.

gRPC implementations generate the following codes in the following cases:

| Case | Code | Generated at |
|------|------|--------------|
| Client application cancelled the call | `CANCELLED` | Both |
| Deadline expired before the server returned a status | `DEADLINE_EXCEEDED` | Both |
| No response received before the deadline expired; either the client could not send the request or the server did not respond in time | `DEADLINE_EXCEEDED` | Both |
| Method not found at the server | `UNIMPLEMENTED` | Server |
| Server shutting down | `UNAVAILABLE` | Server |
| Server application threw an exception or otherwise ended the call without supplying a status | `UNKNOWN` | Server |
| Some data was sent (for example, request metadata written to the connection) before the connection broke | `UNAVAILABLE` | Client |
| Could not decompress, although the compression algorithm is supported (client to server) | `INTERNAL` | Server |
| Could not decompress, although the compression algorithm is supported (server to client) | `INTERNAL` | Client |
| Compression algorithm used by the client is not supported by the server | `UNIMPLEMENTED` | Server |
| Compression algorithm used by the server is not supported by the client | `INTERNAL` | Client |
| Server temporarily out of resources (for example, flow-control resource limits reached) | `RESOURCE_EXHAUSTED` | Server |
| Client does not have enough memory to hold the server response | `RESOURCE_EXHAUSTED` | Client |
| Flow-control protocol violation | `INTERNAL` | Both |
| Error parsing the returned status | `UNKNOWN` | Client |
| Incorrect authentication metadata (credentials failed to get metadata, incompatible credentials set on channel and call, invalid host in `:authority`, and so on) | `UNAUTHENTICATED` | Both |
| Request cardinality violation (method requires exactly one request message, but the client sent a different number) | `INTERNAL` | Server |
| Response cardinality violation (method requires exactly one response message, but the server sent a different number) | `INTERNAL` | Client |
| Error parsing (deserializing) a response message | `INTERNAL` | Client |
| Error parsing (deserializing) a request message | `INTERNAL` | Server |
| Sent or received message was larger than the configured limit | `RESOURCE_EXHAUSTED` | Both |
| Keepalive watchdog timed out | `UNAVAILABLE` | Both |
| Connection failure, or failure to establish a connection, for a call that is not wait-for-ready | `UNAVAILABLE` | Client |

gRPC implementations MUST NOT generate the following codes:

- `INVALID_ARGUMENT`
- `NOT_FOUND`
- `ALREADY_EXISTS`
- `FAILED_PRECONDITION`
- `ABORTED`
- `OUT_OF_RANGE`
- `DATA_LOSS`

Interceptors are application code (even when gRPC supplies them, as for xDS
fault injection), so these restrictions do not apply to them. Status codes
from the control plane are restricted further in [Status Codes from the Control Plane](#106-status-codes-from-the-control-plane).

The mapping from HTTP/2 stream errors and HTTP status codes to gRPC status
codes is defined in [gRPC over HTTP/2](../03-wire-protocol/01-http2.md).

### 10.4 Status Message

The status message is a Unicode string. It is meant for developer debugging,
not for display to end users or for programmatic interpretation. On the wire it
is UTF-8 encoded and then percent-encoded (see [gRPC over HTTP/2](../03-wire-protocol/01-http2.md)).
A receiver that decodes an invalid encoded message MUST NOT fail the call or
discard the status because of it. At worst, it gives the application the raw
encoded form.

### 10.5 Rich Error Details

A non-OK status MAY carry structured details as a serialized `google.rpc.Status`
message (`google/rpc/status.proto` in the googleapis repository) in the
`grpc-status-details-bin` trailer. The `details` field of that message holds
arbitrary `google.protobuf.Any` payloads, for example the standard error
payloads in `google/rpc/error_details.proto`.

- Details MUST NOT be sent with an `OK` status.
- The `code` field of the `google.rpc.Status` MUST equal the call's status code.
  A receiver MUST check this. If the codes differ, the receiver MUST NOT present
  the details as part of the call's status.
- The `message` field SHOULD equal the status message.

### 10.6 Status Codes from the Control Plane

Control-plane components (name resolvers, the service config, ConfigSelectors,
LB policies, and call credentials) often talk to external services. Their
errors MUST NOT be copied unchanged onto RPCs, because a code such as
`NOT_FOUND` from a control-plane lookup would mislead the application about
its own RPC. Control-plane failures SHOULD normally be reported as
`UNAVAILABLE` with added context in the message.

As a safeguard, the channel MUST check the status at each of the following
points, which are where control-plane statuses reach the data plane:

1. When a call fails because the resolver returned an invalid service config
   (and there is no earlier valid config).
2. When a call fails because the resolver returned a failed ConfigSelector
   result.
3. When a call fails because the picker returned a Fail or Drop result.
4. When call credentials fail a call.

Any future interface that passes a status from the control plane to the data
plane MUST add an equivalent check.

The following codes are **inappropriate** at these points:

- `OK` (some control-plane APIs use it, but it MUST NOT be applied to an RPC)
- `INVALID_ARGUMENT`
- `NOT_FOUND`
- `ALREADY_EXISTS`
- `FAILED_PRECONDITION`
- `ABORTED`
- `OUT_OF_RANGE`
- `DATA_LOSS`

If the status has an inappropriate code, the channel MUST rewrite it as follows:

- The code becomes `INTERNAL`.
- The message makes clear that a bug occurred, and includes the original code
  and message so no information is lost.

For picker failures and call-credential failures, retry-policy status matching
(`retryableStatusCodes`, `nonFatalStatusCodes`) MUST use the rewritten status.
Transparent retries do not apply to pick failures. Service-config and
ConfigSelector failures happen before a retry policy is known, so retries do
not apply to them.

Interceptors are not subject to this check.

Example: A picker returns Fail with
`NOT_FOUND: "cluster foo not found"`. The RPC fails with code `INTERNAL` and a
message such as
`"Illegal status code from LB pick; original status: NOT_FOUND: cluster foo not found"`.

### 10.7 Choosing Status Codes to Retry (Informative)

The same code can be generated by gRPC for different reasons and can also come
from server applications. No fixed list of codes is safe to retry for every
application. Service owners choose retryable codes for their methods; see
[Retries and Hedging](../04-client-channel/12-retries.md).

## 11. Ordering of Status, Reads, and Writes

In this subsection, a "read" is the delivery of a response message to the client
application (or of a request message to the server application). A "write" is
the application sending a message. Implementations MUST follow these rules:

1. Reads and writes MUST NOT succeed after the status has been delivered to the
   application.
2. The status MUST be delivered only after all buffered messages have been read,
   except as permitted by rule 5.
3. Reads MAY continue to succeed after a write has failed. Once a write fails,
   all later writes MUST fail. Once a read fails, all later reads MUST fail.
4. A non-OK status received from the server is not an error status for the
   purpose of rule 5. Messages that arrived before it are delivered normally.
5. When the implementation knows of a locally generated error status (for
   example, cancellation, deadline expiry, or a transport failure):
   - if the application asks for the status, the implementation SHOULD discard
     messages that have been received but not yet delivered, and deliver the
     status;
   - if the application keeps reading instead, the implementation SHOULD
     deliver buffered messages before delivering the status.

   An implementation MAY instead discard all buffered messages when such an
   error occurs.

## 12. Message Size Limits

Implementations MUST enforce a maximum size for received messages and MUST
support a maximum size for sent messages.

| Limit | Default | Configured by |
|-------|---------|---------------|
| Maximum receive message size | 4 MiB (4194304 bytes) | Channel API and server API. On the client, also `maxResponseMessageBytes` in the method config. |
| Maximum send message size | No limit | Channel API and server API. On the client, also `maxRequestMessageBytes` in the method config. |

On the client, when both the API and the method config (`grpc/service_config/service_config.proto`,
`MethodConfig.max_request_message_bytes` / `max_response_message_bytes`, JSON
`maxRequestMessageBytes` / `maxResponseMessageBytes`, `google.protobuf.UInt32Value`)
set a limit, the smaller value applies. If only one is set, it applies. If
neither is set, the default applies. A value of 0 is valid and allows only
empty messages.

Sizes are measured on the serialized message. The limit is checked against the
message as framed (after compression, if it is compressed). A receiver MUST
also enforce the receive limit on the decompressed size of a compressed
message, and MUST stop decompressing once the limit is exceeded.

When a limit is exceeded:

- **Sending, either side:** the message MUST NOT be sent. The call fails with
  `RESOURCE_EXHAUSTED`. On the server, the client receives a
  `RESOURCE_EXHAUSTED` status.
- **Receiving, client:** the client MUST cancel the call and complete it with
  `RESOURCE_EXHAUSTED`.
- **Receiving, server:** the server MUST fail the call with `RESOURCE_EXHAUSTED`
  and SHOULD tell the server application that the call was cancelled.

## 13. Compression

Compression in gRPC applies **per message**. Each message is compressed on its
own, and no compression context carries over between messages. Compression
reduces bandwidth. Per-call and per-message control of compression also lets
applications avoid compression-based attacks such as CRIME and BEAST, and
allows the two directions of a call to be compressed differently.

Wire details (`grpc-encoding`, `grpc-accept-encoding`, and the per-message
compressed flag) are defined in [gRPC over HTTP/2](../03-wire-protocol/01-http2.md).

### 13.1 Algorithms

| Name (`grpc-encoding` value) | Algorithm | Notes |
|------------------------------|-----------|-------|
| `identity` | No compression | Always accepted. |
| `gzip` | gzip ([RFC 1952](https://www.rfc-editor.org/rfc/rfc1952)) | |
| `deflate` | The zlib format ([RFC 1950](https://www.rfc-editor.org/rfc/rfc1950)) with the deflate algorithm ([RFC 1951](https://www.rfc-editor.org/rfc/rfc1951)) | Raw deflate data without the zlib wrapper MUST NOT be sent. |

Other algorithms are identified by other content-coding names. Applications
MAY register custom compressors.

### 13.2 Negotiation

- A sender that compresses messages on a stream declares the algorithm in that
  stream's headers (request headers for the client, response headers for the
  server). Each message's compressed flag says whether that message is
  compressed. If the headers declare no algorithm (or `identity`), every
  message MUST have the compressed flag clear.
- Each side SHOULD list the algorithms it can decompress in
  `grpc-accept-encoding`. A peer MAY leave some supported algorithms out of the
  list. If it then receives a message compressed with an unlisted algorithm
  that it does support, it MUST decompress it and MUST include that algorithm
  in the `grpc-accept-encoding` of its response.
- The client does not know in advance which algorithms the server supports. It
  compresses with the algorithm configured for the call or channel.
- The server knows which algorithms the client accepts from the most recent
  `grpc-accept-encoding` it received. For every message the server is asked to
  compress with an algorithm the client does not accept, the server MUST send
  the message uncompressed.

### 13.3 Asymmetry

A peer MAY respond with a different algorithm than the request used, or with
no compression, regardless of channel and call settings (for example, when
compression would give little or negative benefit). The request and response
directions are configured independently.

### 13.4 Configuration and Precedence

- **Channel default (client):** an algorithm set when the channel is created.
  It is used for calls that do not set their own.
- **Server default:** an algorithm or compression level set when the server is
  created.
- **Per call:** the client application MAY set the algorithm for the request
  stream of a call. The server application MAY set the algorithm, or a
  compression level, for the response stream.
- **Per message:** either application MAY ask for a single message to be sent
  uncompressed. The implementation MUST then send that message uncompressed (the
  compressed flag is clear), even if the stream declared an algorithm. This
  applies to both unary and streaming calls.

Per-message settings override per-call settings, which override the channel
or server default. With no configuration at any level, messages MUST NOT be
compressed.

A **compression level** (for example "none", "low", "medium", "high") is an
abstract setting that the implementation maps to an algorithm and its
parameters (for example "low" to gzip level 3 and "high" to gzip level 9),
choosing among the algorithms the peer accepts. Levels are used on the server,
which knows the client's accepted algorithms from `grpc-accept-encoding`.
Clients select algorithms.

Implementations MUST let applications restrict the set of algorithms enabled
for decompression. Messages compressed with an algorithm that is not enabled
are treated as unsupported.

Whether outgoing calls made while handling an incoming call inherit its
compression settings depends on the implementation. If nothing is inherited,
the outgoing channel's configuration applies.

### 13.5 Errors

| Condition | Result |
|-----------|--------|
| Server receives a message compressed with an algorithm it does not support or has not enabled | Server fails the call with `UNIMPLEMENTED`. The status message says the algorithm is unsupported and lists the supported ones. The response MAY include `grpc-accept-encoding` listing the server's supported algorithms. If it does, the list MUST NOT include the one used. |
| Client receives a message compressed with an algorithm it does not support or has not enabled | Client fails the call with `INTERNAL`. The status message says the algorithm is unsupported and lists the supported ones. |
| A message has its compressed flag set, but the stream declared no algorithm other than `identity` | The receiver fails the call with `INTERNAL`. The status message describes the invalid compressed flag. |
| Decompression fails although the algorithm is supported | The receiver fails the call with `INTERNAL`. |

If a client compresses with an algorithm listed in the server's
`grpc-accept-encoding` and gets `UNIMPLEMENTED`, the cause is not compression.

## 14. Wait-for-Ready

Every call has a boolean **wait-for-ready** property. It controls what happens
when the call cannot be sent because of a connectivity failure.

- **Wait-for-ready disabled (the default, also called "fail fast"):** the call
  MUST fail immediately when:
  - it is waiting for the channel's first resolver result, and name resolution
    fails, so the channel is in `TRANSIENT_FAILURE`; or
  - it is waiting for a pick, and the picker returns Fail (normally because
    the LB policy is in `TRANSIENT_FAILURE`, for example because no connection
    can be made to any address).

  The call fails with the status from the failure, subject to
  [Status Codes from the Control Plane](#106-status-codes-from-the-control-plane). The status is usually
  `UNAVAILABLE`.
- **Wait-for-ready enabled:** in those cases the call stays queued in the
  channel while the channel retries (re-resolving the name or reconnecting).
  It proceeds when resolution succeeds or a pick completes.

In both modes:

- Calls MUST NOT fail because the channel is in `IDLE`, `CONNECTING`, or
  `READY`. In those states calls are queued or sent.
- Calls MUST fail when the channel is shut down, when the deadline expires, or
  when the picker returns Drop, regardless of wait-for-ready.
- Wait-for-ready covers only these connectivity cases. A call can still fail
  for other client-side reasons, can be failed by the server, and can fail
  because of a network failure while it is in flight.

The value is set from these sources, highest precedence first:

1. The value set by the client application for the call.
2. The `waitForReady` field (`google.protobuf.BoolValue`) of the matching
   method config in the service config.
3. Default: `false`.

Note: A value from the service config cannot affect a call that is waiting for
the first resolver result, because the service config comes from that result.
Only the application-set value affects that case.

The behavior of each channel state is specified in
[Channel](../04-client-channel/02-channel.md) and of each pick result in
[Load Balancing](../04-client-channel/06-load-balancing.md).

## 15. Idempotency and Retries

Calls are assumed to be **non-idempotent**. gRPC MUST NOT replay a call unless
it knows that doing so is safe. Specifically:

- gRPC MAY transparently retry an attempt that certainly did not reach the
  server application: one that never left the client, or one that the server
  transport refused before the application saw it. See
  [Retries and Hedging](../04-client-channel/12-retries.md).
- Any other retry or hedge happens only when the service owner configures a
  retry or hedging policy for the method (in the service config or through
  xDS). A retry policy lists which status codes are retryable. Hedging can make a
  method run more than once on servers, so a hedging policy SHOULD be
  configured only for idempotent methods.
- gRPC has no separate mechanism for marking a method as idempotent, and no
  duplicate-suppression mechanism.
- Once a call is **committed** (the client received response headers, or the
  buffer for replaying messages overflowed), it is not retried.

Retries and hedging are specified in [Retries and Hedging](../04-client-channel/12-retries.md).

## 16. Interceptors

An **interceptor** is code that sits in a call's processing path. It can
observe and modify the call's operations. Interceptors are the extension point
for cross-cutting behavior such as authentication, logging, metrics, fault
injection, and authorization.

### 16.1 Client Interceptors

A client interceptor wraps a call. It sees each operation the application
performs on the call before passing it on (or not), and each event from the
next layer before passing it to the application (or not). A client
interceptor can:

- read and modify the call's method, deadline, metadata, call credentials,
  compression, and wait-for-ready settings before the call starts;
- read, modify, add, or suppress outgoing messages and half-close;
- read and modify incoming response headers, messages, trailers, and status;
- cancel the call;
- fail the call with any status without passing it to the next layer, or
  complete it with a synthesized response;
- delay operations (for example, to fetch credentials).

Application-registered client interceptors are attached to a channel (see
[Ordering](#163-ordering)). They apply to every call on that channel and operate on the
**call**, not on individual attempts: they run above the retry layer, so they
run once per call regardless of retries.

The ConfigSelector MAY also supply per-call interceptors (for example, to apply
xDS HTTP filters). They run after the per-call configuration is chosen and
before the retry layer. See [Per-call Configuration and Call Flow](../04-client-channel/05-call-dispatch.md) and
[xDS HTTP Filters](../09-xds/07-http-filters.md).

Per-attempt observation is provided by attempt tracers rather than by
interceptors. See [Instrumentation Architecture](../08-observability/02-instrumentation.md).

### 16.2 Server Interceptors

A server interceptor wraps the handling of an incoming call before it reaches
the handler. It can:

- read the call's method, metadata, deadline, peer, authority, and
  authentication context;
- reject the call with a status before the handler runs;
- read and modify incoming metadata and request messages;
- read and modify outgoing response headers, messages, trailers, and status;
- detect cancellation.

Server interceptors apply to every call the server handles, including calls
for unknown methods that are routed to a fallback handler.

### 16.3 Ordering

Interceptors on a channel or server are nested: each one wraps the
interceptors inside it. On a client, the **outermost** interceptor is the first
to see outgoing operations and the last to see incoming events. On a server,
the outermost interceptor is the first to see the incoming call and the last
to see outgoing operations. The **innermost** interceptor is the one closest to
the transport on a client and closest to the handler on a server.

How the order in which an application registers interceptors maps to their
nesting is implementation-defined.

Interceptors are not restricted to the status codes in
[Status Codes Generated by gRPC](#103-status-codes-generated-by-grpc) or
[Status Codes from the Control Plane](#106-status-codes-from-the-control-plane). They are application-level
code and MAY fail calls with any status code.

## 17. Codecs and Content-Subtype

A **codec** serializes and deserializes messages. Every call uses one codec,
identified by its **content-subtype**, a lowercase token. On HTTP/2 the
content-subtype is carried in the `content-type` header as
`application/grpc+<subtype>` (see [gRPC over HTTP/2](../03-wire-protocol/01-http2.md)).

- The `proto` subtype is the Protocol Buffers binary encoding
  ([Protocol Buffers Mapping](../03-wire-protocol/04-protobuf.md)). It is the default. A `content-type` of
  plain `application/grpc` MUST be treated as `application/grpc+proto`.
- Other subtypes identify other codecs. Implementations MAY
  let applications register codecs by subtype.
- A server MUST use the codec named by the request's content-subtype to read
  requests and write responses, and SHOULD respond with the same
  content-subtype.
- A server that receives a content-subtype it has no codec for MAY fail the
  call with `UNIMPLEMENTED` (on HTTP/2, a gRPC status in the trailers, not an
  HTTP error status; see [gRPC over HTTP/2](../03-wire-protocol/01-http2.md)). A
  server that does not fail the call processes it with the method's default
  codec, as if no content-subtype had been sent.
- Failures to deserialize a received message are `INTERNAL`
  ([Status Codes Generated by gRPC](#103-status-codes-generated-by-grpc)). If a message cannot be
  serialized for sending, the sender fails the call with `INTERNAL`.

## 18. API Requirements

### 18.1 Client Call API

The client API MUST provide a way to:

1. Start a call on a channel, identified by its full method name, with any of
   the following per-call options:
   - a deadline (absolute time) or timeout;
   - metadata to send in request headers;
   - call credentials (see [Call Credentials](../06-security/03-call-credentials.md));
   - the compression algorithm for request messages;
   - wait-for-ready;
   - an authority override ([Authority](#9-authority));
   - the codec or content-subtype (or the codec can be bound to the method
     definition).
2. Send request messages. The API MUST expose flow control, for example by
   blocking, by a readiness notification, or by completion callbacks, so that
   the application can avoid unbounded buffering.
3. Send a single message uncompressed even when compression is enabled for the
   call.
4. Half-close the request stream.
5. Receive the response headers (response metadata), separately from and before
   the response messages. For a trailers-only response they are empty.
6. Receive response messages one at a time. The application controls the pace,
   which provides inbound flow control.
7. Receive the final status (code, message, and details if present) and the
   trailing metadata.
8. Cancel the call at any time. If the call has not completed, it completes
   with `CANCELLED`.
9. Offer convenience forms for each RPC type ([RPC Types](#21-rpc-types)), for
   example a unary call that takes one request and returns one response or a
   status.
10. Find out the peer of the call once the call has been assigned to a transport.

### 18.2 Server Call API

The server API MUST provide a way for a handler to:

1. Get the call's full method name, request metadata, deadline (if any),
   authority, peer address, and authentication context
   ([Security](../06-security/README.md)).
2. Receive request messages one at a time, with application-controlled pacing,
   and find out when the client has half-closed.
3. Send response headers with metadata, either explicitly or implicitly with
   the first response message or with the status
   ([Server Response Headers](#33-server-response-headers)).
4. Send response messages, with flow control exposed as on the client.
5. Choose the compression algorithm or level for response messages, and send a
   single message uncompressed.
6. End the call with a status (code, message, and optional details) and
   trailing metadata.
7. Find out that the call was cancelled (by the client, by deadline expiry, or
   by a transport failure), both by polling and by asynchronous notification.
8. Propagate the call's deadline and cancellation to outgoing calls
   ([Deadline Propagation](#83-deadline-propagation)).

The server API MUST also provide a way to register handlers by service and
method, and to register a fallback handler for methods that are not
registered. See [Server](../05-server/README.md).

### 18.3 Metadata API

The metadata API MUST provide a way to:

1. Add multiple values for one key and read all values for a key in order.
2. Use binary (`-bin`) keys with raw byte values, without the application doing
   any wire encoding.
3. Iterate over all entries.

### 18.4 Configuration API

The channel and server APIs MUST provide a way to set:

1. The maximum receive and send message sizes ([Message Size Limits](#12-message-size-limits)).
2. The maximum received metadata size ([Size Limits](#76-size-limits)).
3. The default compression algorithm (channel and server) and the default
   compression level (server) ([Configuration and Precedence](#134-configuration-and-precedence)).
4. The set of compression algorithms enabled for decompression.
5. Client interceptors (channel) and server interceptors (server)
   ([Interceptors](#16-interceptors)).

### 18.5 Status API

The status API MUST provide a way for:

1. Server applications to supply rich error details
   ([Rich Error Details](#105-rich-error-details)) with a non-OK status.
2. Client applications to read rich error details from a received status,
   including the raw `grpc-status-details-bin` trailer value.

## 19. Call ABNF

The following [ABNF](https://www.rfc-editor.org/rfc/rfc5234) describes the
abstract structure of a call, ignoring cancellation. It is not a wire format;
for the HTTP/2 encoding see [gRPC over HTTP/2](../03-wire-protocol/01-http2.md).

```abnf
call              = request-stream response-stream ; in parallel
request-stream    = request-headers *request [half-close]
response-stream   = [response-headers *response] trailers

request-headers   = full-method-name metadata
request           = message
half-close        = ""                 ; no content
response-headers  = metadata
response          = message
trailers          = status metadata

full-method-name  = full-service-name "/" short-method-name
full-service-name = 1*name-char        ; e.g. "package.Service"
short-method-name = 1*name-char
name-char         = %x21-2E / %x30-7E  ; VCHAR except "/"

metadata          = *(ascii-metadata / binary-metadata)
metadata-key-char = DIGIT / %x61-7A / "_" / "-" / "."  ; 0-9 a-z _ - .
ascii-metadata    = ascii-key ascii-value
binary-metadata   = binary-key binary-value
ascii-key         = 1*metadata-key-char ; MUST NOT end in "-bin"
ascii-value       = *(SP / VCHAR)
binary-key        = 1*metadata-key-char "-bin"
binary-value      = *OCTET

message           = message-payload
message-payload   = *OCTET             ; zero-length payloads are valid

status            = status-code [status-message] [status-details]
status-code       = <one of the codes in "Status Codes" above>
status-message    = 1*<Unicode character>
status-details    = <serialized google.rpc.Status>
```

Notes:

- A response with no response headers and no messages consists of trailers
  only. On HTTP/2 this is sent as a `Trailers-Only` response
  ([gRPC over HTTP/2](../03-wire-protocol/01-http2.md)).
- Senders SHOULD produce full method names and metadata that match this
  grammar. Receivers MAY be more lenient than the grammar. For example, a
  receiver may accept metadata values that contain bytes outside `SP / VCHAR`.
- A server matches the full method name against its registered methods
  exactly and case-sensitively, without percent-decoding. A call whose full
  method name is malformed (for example, missing the leading `/` on the wire,
  or missing the `/` between the service and method names) or matches no
  registered method fails with `UNIMPLEMENTED`.
