> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 3.1 gRPC over HTTP/2

<!-- Sources: doc/PROTOCOL-HTTP2.md, doc/http-grpc-status-mapping.md, doc/compression.md (wire parts), doc/statuscodes.md, doc/http2-interop-test-descriptions.md (informative), A6 (Response-Headers timing, transparent retry, retry headers), A41 (Host/:authority, Connection header), A9 (graceful GOAWAY), A8 (too_many_pings), G2 (deadline reset) -->

This section specifies how gRPC calls are carried over
[HTTP/2](https://www.rfc-editor.org/rfc/rfc9113) framing. It assumes the reader
knows HTTP/2. Transport behavior that is not about the per-call exchange
(SETTINGS, flow control, keepalive, connection management) is in
[HTTP/2 Client Transport](../04-client-channel/08-transports/02-http2.md) and [HTTP/2 Server Transport](../05-server/02-transports/02-http2.md).

## 1. Notation

Production rules use [ABNF](https://www.rfc-editor.org/rfc/rfc5234), with these
conventions:

- `"name" value` denotes one HTTP/2 header field whose name is `name` and
  whose value is `value`. Header fields are carried in HPACK-encoded header
  blocks, so no `:` or CRLF separators appear on the wire.
- `{text}` is a prose description of a value.
- `?(x)` is equivalent to `[x]`.
- `DIGIT`, `HEXDIG`, `OCTET`, `SP`, and `VCHAR` are the ABNF core rules.

## 2. Outline

```abnf
Request  = Request-Headers *Length-Prefixed-Message EOS
Response = (Response-Headers *Length-Prefixed-Message Trailers) / Trailers-Only
```

Each Call uses exactly one client-initiated HTTP/2 stream. The client sends the
Request on the stream. The server sends the Response on the same stream.

## 3. Requests

### 3.1 Grammar

```abnf
Request-Headers   = Call-Definition *Custom-Metadata
Call-Definition   = Method Scheme Path [Authority] TE [Timeout] Content-Type
                    [Message-Type] [Message-Encoding] [Message-Accept-Encoding]
                    [User-Agent]

Method            = ":method" "POST"
Scheme            = ":scheme" ("http" / "https")
Path              = ":path" "/" Service-Name "/" Method-Name
Service-Name      = {IDL-specific service name}
Method-Name       = {IDL-specific method name}
Authority         = ":authority" {virtual host name of the authority}
TE                = "te" "trailers"

Timeout           = "grpc-timeout" TimeoutValue TimeoutUnit
TimeoutValue      = 1*8DIGIT       ; positive integer, at most 8 digits
TimeoutUnit       = Hour / Minute / Second / Millisecond / Microsecond / Nanosecond
Hour              = %s"H"
Minute            = %s"M"
Second            = %s"S"
Millisecond       = %s"m"
Microsecond       = %s"u"
Nanosecond        = %s"n"

Content-Type      = "content-type" "application/grpc" [("+proto" / Custom-Subtype)]
Custom-Subtype    = "+" {custom content-subtype}

Content-Coding    = "identity" / "gzip" / "deflate" / "snappy" / {custom}
Message-Encoding  = "grpc-encoding" Content-Coding
Message-Accept-Encoding = "grpc-accept-encoding" Content-Coding *("," Content-Coding)

User-Agent        = "user-agent" {structured user-agent string}
Message-Type      = "grpc-message-type" {type name for message schema}

Custom-Metadata   = Binary-Header / ASCII-Header
Binary-Header     = Header-Name "-bin" {base64-encoded value}
ASCII-Header      = Header-Name ASCII-Value
Header-Name       = 1*( %x30-39 / %x61-7A / "_" / "-" / "." )   ; 0-9 a-z _ - .
ASCII-Value       = 1*( %x20-7E )                              ; space and printable ASCII
```

`Request-Headers` are sent as one HTTP/2 field block
([RFC 9113 §4.3](https://www.rfc-editor.org/rfc/rfc9113#section-4.3)).

### 3.2 Header ordering

Pseudo-headers come first, as required by
[RFC 9113 §8.3](https://www.rfc-editor.org/rfc/rfc9113#section-8.3). In
addition, implementations SHOULD send `grpc-timeout` immediately after the
pseudo-headers, and SHOULD send all `Call-Definition` headers before any
`Custom-Metadata`.

### 3.3 `:method`, `:scheme`, and `:path`

- `:method` MUST be `POST`.
- `:scheme` MUST be `https` when the connection is secured by TLS or another
  security protocol, and `http` otherwise.
  
- `:path` is case-sensitive. It carries the full method name (see
  [Core RPC Semantics](../02-rpc-semantics/README.md)) prefixed by `/`. For
  Protocol Buffers services, see [Protocol Buffers Mapping](04-protobuf.md).

Implementations MAY let applications override the `:path` format, but this is
strongly discouraged. Features keyed on service and method names (for
example, [service config](../04-client-channel/04-service-config.md) method
matching) do not work when the path does not have the form above.

### 3.4 `:authority` and `Host`

The client SHOULD send `:authority`. Its value is the channel's authority or a
per-call override; see [Channel](../04-client-channel/02-channel.md).

Servers MUST look at both `:authority` and `Host`, to get one unambiguous
authority for each request:

1. If more than one `:authority` header, or more than one `Host` header, is
   present, the server MUST reject the request with one of: HTTP status 400,
   gRPC status `INTERNAL`, or `RST_STREAM` with error code `PROTOCOL_ERROR`.
2. Otherwise, if `:authority` is absent and `Host` is present, the server MUST
   treat the `Host` value as `:authority` (rename `Host` to `:authority`).
3. Otherwise, if both are present, the server MUST discard `Host`.

The resulting `:authority` is what is shown to the server application and to
server-side authorization (see
[Authorization](../06-security/04-authorization.md)).

### 3.5 Hop-by-hop headers

Transports MUST enforce the prohibition on connection-specific header fields
(such as `Connection`) in
[RFC 9113 §8.2.2](https://www.rfc-editor.org/rfc/rfc9113#section-8.2.2),
whether or not any other feature is in use.

### 3.6 `te`

Clients MUST send `te: trailers`. It lets the server, and any intermediaries,
detect proxies that cannot forward trailers.

### 3.7 `grpc-timeout`

`grpc-timeout` carries the time remaining before the call's deadline (see
[Core RPC Semantics](../02-rpc-semantics/README.md)). A duration is sent rather
than an absolute time so that the client and server clocks do not need to be
synchronized.

- `TimeoutValue` is a positive decimal integer written as ASCII, with at most
  8 digits.
- The sender MUST choose a `TimeoutUnit` that lets the remaining time fit in
  8 digits. It SHOULD use the finest unit that fits, rounding up so that the
  encoded timeout is never shorter than the remaining time. For example,
  100 seconds can be sent as `100000000u` (9 digits, too long), so it is sent as
  `100000m`.
- If the client sends no `grpc-timeout`, the server MUST assume the call has
  no deadline. Clients MAY apply a default deadline based on their deployment
  needs.
- The server computes its own deadline as the time the request headers were
  received plus the decoded timeout.
- A server that receives a `grpc-timeout` value it cannot parse SHOULD fail
  the call with status `INTERNAL`.

Deadline expiry is described in [Deadline expiry and cancellation](#84-deadline-expiry-and-cancellation).

### 3.8 `content-type`

- The client MUST send `content-type` starting with `application/grpc`.
  Bare `application/grpc` and `application/grpc+proto` both mean Protocol
  Buffers encoding. Other content-subtypes (`+{custom}`) name other
  message encodings; see [Protocol Buffers Mapping](04-protobuf.md).
- If `content-type` does not start with `application/grpc`, a gRPC server
  SHOULD respond with HTTP status 415 (Unsupported Media Type). Then other
  HTTP/2 clients will not mistake a gRPC error response (which uses HTTP
  status 200) for success.
- If `content-type` starts with `application/grpc` but names a
  content-subtype for which the server has no codec, the server MAY fail
  the call with `UNIMPLEMENTED`, sent as a normal gRPC status (HTTP status
  200, `grpc-status` in `Trailers-Only`). Otherwise it processes the call
  with the method's default codec. HTTP 415 is used only for
  content-types that do not start with `application/grpc`. See
  [Core RPC Semantics](../02-rpc-semantics/README.md).

### 3.9 `grpc-encoding` and `grpc-accept-encoding`

- `grpc-encoding` names the compression algorithm used for messages whose
  Compressed-Flag is 1 (see [Length-Prefixed Messages](#5-length-prefixed-messages)). It
  applies to every message sent by that peer on the stream.
- `grpc-accept-encoding` lists the algorithms the sender can decode, in a
  comma-separated list. A peer MAY leave out algorithms it supports.
- `deflate` means the zlib format ([RFC 1950](https://www.rfc-editor.org/rfc/rfc1950))
  using the deflate algorithm ([RFC 1951](https://www.rfc-editor.org/rfc/rfc1951)).
  Peers MUST NOT send raw deflate data.
- `identity` means no compression.

Compression error handling:

| Situation | Behavior |
| --------- | -------- |
| The server gets a message compressed with an algorithm it does not support. | The server MUST fail the call with `UNIMPLEMENTED`. The status message SHOULD name the unsupported algorithm and the supported ones. The response MAY include `grpc-accept-encoding` listing what the server accepts. If it does, that list MUST NOT include the unsupported algorithm. |
| The server gets a message compressed with an algorithm it supports but did not list in `grpc-accept-encoding`. | The server decodes it and MUST include that algorithm in its response's `grpc-accept-encoding`. |
| The client gets a message compressed with an algorithm it does not support. | The client MUST fail the call with `INTERNAL`. |
| A message fails to decompress even though its algorithm is supported. | The receiver fails the call with `INTERNAL`. |
| The server is asked to compress a response with an algorithm that the client's most recent `grpc-accept-encoding` does not list. | The server MUST send that message uncompressed. |
| An `UNIMPLEMENTED` status arrives for a request compressed with an algorithm in the server's `grpc-accept-encoding`. | The status MUST NOT be caused by compression. |

The compression API (per-channel defaults, per-call and per-message settings)
is specified in [Core RPC Semantics](../02-rpc-semantics/README.md).

### 3.10 `user-agent`

The protocol works without a user-agent. Clients SHOULD still send a
structured user-agent that describes the calling library, its version, and the
platform, to help diagnose problems. Recommended format:

```abnf
User-Agent-Value   = "grpc-" Language ?("-" Variant) "/" Version
                     ?( " (" *(AdditionalProperty ";") ")" )
```

Examples:

```
grpc-mylang/1.2.3
grpc-mylang-myvariant/1.3.4
grpc-mylang-android/0.9.1 (gingerbread/1.2.4; nexus5; tmobile)
```

If the application provides its own user-agent string, it is placed before
the library's user-agent, separated by a space.

### 3.11 `grpc-message-type`

`grpc-message-type`, if present, names the schema type of the messages on the
stream (for Protocol Buffers, the fully qualified message name). It is
informational only.

### 3.12 Retry-related request headers

> **Introduced by:** [gRFC A6: gRPC Retry Design](https://github.com/grpc/proposal/blob/master/A6-client-retries.md)

- `grpc-previous-rpc-attempts`: an ASCII decimal integer. The client sets it on
  retry and hedging attempts to the number of earlier attempts for the same
  call. It is absent on the first attempt.

Its semantics, and those of the response header `grpc-retry-pushback-ms`
([Retry pushback](#66-retry-pushback)), are in
[Retries](../04-client-channel/12-retries.md).

## 4. Metadata Encoding

### 4.1 Header names

- Metadata keys are case-insensitive. Implementations MUST send them in
  lowercase, as HTTP/2 requires
  ([RFC 9113 §8.2.1](https://www.rfc-editor.org/rfc/rfc9113#section-8.2.1)).
- Custom metadata names MUST match `Header-Name` (plus the `-bin` suffix for
  binary metadata).
- Names starting with `grpc-` are reserved for gRPC. Applications MUST NOT use
  them as custom metadata. gRPC currently defines: `grpc-timeout`,
  `grpc-encoding`, `grpc-accept-encoding`, `grpc-message-type`, `grpc-status`,
  `grpc-message`, `grpc-status-details-bin`, `grpc-previous-rpc-attempts`,
  `grpc-retry-pushback-ms`, and `grpc-trace-bin` (see
  [Tracing](../08-observability/05-tracing.md)).
- Pseudo-headers, `te`, `content-type`, and `user-agent` are set by the gRPC
  library. They are not application metadata.
- A full list of metadata keys is in
  [Appendix A](../appendices/a-metadata-keys.md).

### 4.2 ASCII values

- An `ASCII-Value` SHOULD NOT have leading or trailing whitespace. If it does,
  the whitespace MAY be removed.
- The `ASCII-Value` character range is narrower than HTTP's `field-value`.
  Implementations MUST NOT fail a call because it received a value that is
  not a valid `ASCII-Value` but is a valid HTTP `field-value`. They MAY drop
  such a value or accept it. If they accept it, they MUST make sure the
  application can echo it back. For example, if request metadata is given to
  the application as a list, sending the same list back as response metadata
  must not cause an error.

### 4.3 Binary values

HTTP/2 header values cannot hold arbitrary bytes, so binary metadata (keys
ending in `-bin`) is base64-encoded with the standard alphabet
([RFC 4648 §4](https://www.rfc-editor.org/rfc/rfc4648#section-4)):

- Senders SHOULD send unpadded base64.
- Receivers MUST accept both padded and unpadded values.
- The gRPC library does the encoding and decoding. Applications see the raw
  bytes, and the `-bin` suffix tells the library which keys to treat this way.
- When the peer has enabled it,
  [True binary metadata](02-true-binary-metadata.md) allows sending the raw
  bytes instead.

### 4.4 Duplicate keys and ordering

- Implementations do not have to keep custom metadata in order, except that
  the values of one key MUST stay in order.
- Values with the same key MAY be joined into one header with `,` as the
  separator. The result is equivalent to the separate values.
- Before base64-decoding a `Binary-Header`, receivers MUST split it on `,`.
  Each part is decoded on its own and becomes one value.
- An ASCII value MUST NOT be split on `,` unless the key's definition allows
  it. Joining is lossy.

### 4.5 Header list size

- Servers MAY limit the size of `Request-Headers`, and clients MAY limit the
  size of `Response-Headers`, `Trailers`, and `Trailers-Only`.
  Implementations SHOULD provide a safe default limit for received header
  lists. The value of the default is up to the implementation.
- Implementations SHOULD compute header size as defined for
  `SETTINGS_MAX_HEADER_LIST_SIZE`
  ([RFC 9113 §6.5.2](https://www.rfc-editor.org/rfc/rfc9113#section-6.5.2)).
  The length of a binary value is its length after base64 encoding.
- Implementations SHOULD advertise their limit to the peer in
  `SETTINGS_MAX_HEADER_LIST_SIZE` (see
  [HTTP/2 Client Transport: SETTINGS](../04-client-channel/08-transports/02-http2.md#22-settings) and [HTTP/2 Server Transport: SETTINGS](../05-server/02-transports/02-http2.md#21-settings)).
- When the received headers exceed the limit, the receiver MUST fail the call.
  A server SHOULD respond with `RESOURCE_EXHAUSTED` in Trailers-Only, or reset
  the stream if it cannot. A client SHOULD report `RESOURCE_EXHAUSTED` to the
  application.

## 5. Length-Prefixed Messages

The request and response bodies are each a sequence of length-prefixed
messages carried in DATA frames:

```abnf
Length-Prefixed-Message = Compressed-Flag Message-Length Message
Compressed-Flag         = %x00 / %x01   ; 1-byte unsigned integer
Message-Length          = 4OCTET        ; length of Message, 32-bit unsigned, big-endian
Message                 = *OCTET
```

- A `Compressed-Flag` of 1 means `Message` is compressed with the algorithm in
  the sender's `grpc-encoding` header. A value of 0 means `Message` is not
  compressed.
- If the sender did not send `grpc-encoding`, or sent `identity`, every
  `Compressed-Flag` MUST be 0. A receiver that gets a flag of 1 in that case
  MUST fail the call with `INTERNAL`.
- A sender MAY send any message uncompressed (flag 0), even when
  `grpc-encoding` is set. For example, it can skip compression when the gain is
  small or when compression is turned off for that message.
- A `Compressed-Flag` other than 0 or 1 is a protocol error. The receiver
  MUST fail the call with `INTERNAL`.
- Compression contexts MUST NOT be kept across messages. Each message is
  compressed and decompressed on its own.
- `Message-Length` is the length of `Message` as sent (after compression).
  Zero-length messages are valid.
- Size limits on messages are checked against both the wire length and the
  decompressed length. A message over the limit fails the call with
  `RESOURCE_EXHAUSTED`. See [Core RPC Semantics](../02-rpc-semantics/README.md).

DATA frame boundaries have no relation to `Length-Prefixed-Message`
boundaries. One message MAY span many DATA frames, and one DATA frame MAY
hold parts of several messages. Implementations MUST NOT assume any alignment.
DATA frame padding
([RFC 9113 §6.1](https://www.rfc-editor.org/rfc/rfc9113#section-6.1)) is not
part of the message stream.

### 5.1 End of stream (EOS)

- For requests, EOS (Half Close) is the END_STREAM flag on the last DATA frame
  the client sends, or on the request HEADERS frame if there is no body. If the
  client needs to close the request stream and has no more data to send, it
  MUST send an empty DATA frame with END_STREAM set.
- For responses, EOS is the END_STREAM flag on the HEADERS frame that carries
  `Trailers` or `Trailers-Only`.
- If the request body ends partway through a `Length-Prefixed-Message`, the
  server MUST fail the call with `INTERNAL`. If the response body ends partway
  through a message, the client MUST fail the call with `INTERNAL`.

## 6. Responses

### 6.1 Grammar

```abnf
Response-Headers  = HTTP-Status [Message-Encoding] [Message-Accept-Encoding]
                    Content-Type *Custom-Metadata
Trailers-Only     = HTTP-Status Content-Type [Message-Accept-Encoding] Trailers
Trailers          = Status [Status-Message] [Status-Details] *Custom-Metadata

HTTP-Status       = ":status" "200"
Status            = "grpc-status" 1*DIGIT                 ; decimal, no leading zeros
Status-Message    = "grpc-message" Percent-Encoded
Status-Details    = "grpc-status-details-bin" {base64-encoded value}

Percent-Encoded        = 1*(Percent-Byte-Unencoded / Percent-Byte-Encoded)
Percent-Byte-Unencoded = %x20-24 / %x26-7E                ; space and VCHAR, except "%"
Percent-Byte-Encoded   = "%" 2HEXDIG
```

- `Response-Headers` and `Trailers-Only` are each sent as one HTTP/2 header
  block.
- `Trailers` is sent as one header block with END_STREAM set.
- Most responses have both headers and trailers. `Trailers-Only` is used when
  the call ends with no response headers and no messages (see
  [When to send Response-Headers](#62-when-to-send-response-headers)).
- `Status` MUST be sent in `Trailers` (or `Trailers-Only`) even when the code
  is `OK`.
- When a client gets `Trailers-Only`, it MUST give the application empty
  response headers. Any `Custom-Metadata` in the block is trailing metadata.

### 6.2 When to send Response-Headers

A client treats a call as committed once it receives `Response-Headers`, so it
cannot retry the call after that point (see
[Retries](../04-client-channel/12-retries.md)). To keep retries possible:

- Servers SHOULD hold back `Response-Headers` until the first response message
  is sent or the application explicitly sends headers, whichever comes first.
- If the application ends the call before headers or any message are sent,
  the server SHOULD send the status in `Trailers-Only`.

### 6.3 `grpc-status`

- The value is the status code as a decimal ASCII integer with no leading
  zeros. Codes are defined in [Core RPC Semantics](../02-rpc-semantics/README.md).
- A client that receives a value outside the defined range SHOULD pass it to
  the application unchanged if its API can represent it, and otherwise MUST
  convert it to `UNKNOWN` (see [Core RPC Semantics](../02-rpc-semantics/README.md)).
- A client that receives a `grpc-status` it cannot parse MUST report
  `UNKNOWN`.

### 6.4 `grpc-message`

The value of `Status-Message` is a Unicode string, encoded as UTF-8 and then
percent-encoded. The percent-encoding follows
[RFC 3986 §2.1](https://www.rfc-editor.org/rfc/rfc3986#section-2.1) but uses
different reserved characters:

- Encoding: every byte of the UTF-8 string that is outside
  `Percent-Byte-Unencoded` (that is, bytes outside `%x20-7E`, and the byte
  `%` itself) MUST be written as `%` plus two hex digits. Senders SHOULD
  use uppercase hex digits. Receivers MUST accept both cases.
- Decoding: on invalid input (for example a `%` not followed by two hex
  digits, or bytes that are not valid UTF-8 after decoding), implementations
  MUST NOT fail the call and MUST NOT throw away the message. Allowed
  behaviors are:
  - stop decoding and give the application the raw percent-encoded value; or
  - decode the valid parts and either leave broken `%` sequences as they are
    or replace them with a replacement character (such as `?` or U+FFFD).

### 6.5 `grpc-status-details-bin`

- `Status-Details` MAY be sent only when `Status` is not `OK`. It holds more
  information about the error, as a serialized message. For Protocol Buffers
  this is `google.rpc.Status` (see [Protocol Buffers Mapping](04-protobuf.md)).
- If the details contain a status code or message, they MUST match
  `grpc-status` and `grpc-message`. The sender is responsible for this. A
  receiving gRPC library MAY check it and MAY act on a mismatch, or on
  `Status-Details` that arrives with an `OK` status (for example by not
  presenting the parsed details as part of the call's status), but it is not
  required to.
- Whether or not the library checks, the application MUST be able to read the
  raw `grpc-status-details-bin` trailer value.

### 6.6 Retry pushback

> **Introduced by:** [gRFC A6: gRPC Retry Design](https://github.com/grpc/proposal/blob/master/A6-client-retries.md)

- `grpc-retry-pushback-ms` MAY appear in `Trailers` or `Trailers-Only`.
- Its value is an ASCII signed 32-bit decimal integer with no unnecessary
  leading zeros, giving how many milliseconds the client should wait before
  retrying.
- A negative or unparseable value means the server asks the client not to
  retry.
- See [Retries](../04-client-channel/12-retries.md).

### 6.7 Content-type in responses

Servers MUST send `content-type` in `Response-Headers` and `Trailers-Only`,
with the same structure as in requests. Normally its value is the request's
content-type.

## 7. Handling Non-gRPC and Broken Responses

Broken deployments and intermediaries (proxies, load balancers) may send
non-200 HTTP status codes, non-gRPC content-types, or responses without
`grpc-status`. Clients MUST be ready for this. When it happens, they MUST
make up a status code and message to give to the application, as follows.

### 7.1 Informational (1xx) responses

A 1xx response header block MUST be skipped entirely, and the client reads the
next header block as the response headers (see
[RFC 9113 §8.1](https://www.rfc-editor.org/rfc/rfc9113#section-8.1)).

### 7.2 Deriving the status

When a response ends, the client finds the call's status in this order:

1. If the response included `grpc-status`, the client MUST use it, whatever
   the HTTP status or content-type.
2. Otherwise, if the HTTP `:status` is not 200, the client MUST map it with the
   table below.
3. Otherwise (HTTP 200 with no `grpc-status`), the status is `UNKNOWN`, with
   one exception: if the stream ended with END_STREAM on a DATA frame (no
   trailer block at all), the status is `INTERNAL`, because a stream with no
   trailers violates the protocol.

The status message SHOULD include the HTTP status and, when the content-type
is not gRPC, a note saying so.

| HTTP status | gRPC status |
| ----------- | ----------- |
| 400 Bad Request | `INTERNAL` |
| 401 Unauthorized | `UNAUTHENTICATED` |
| 403 Forbidden | `PERMISSION_DENIED` |
| 404 Not Found | `UNIMPLEMENTED` |
| 429 Too Many Requests | `UNAVAILABLE` |
| 502 Bad Gateway | `UNAVAILABLE` |
| 503 Service Unavailable | `UNAVAILABLE` |
| 504 Gateway Timeout | `UNAVAILABLE` |
| All other codes | `UNKNOWN` |

- A 200 response with no `grpc-status` maps to `UNKNOWN` (or `INTERNAL` when
  it has no trailer block at all, as described above), because a truly
  successful gRPC response always carries `grpc-status`.
- Use this table only on clients, and only when `grpc-status` is missing.
- Servers MUST NOT use it to pick an HTTP status. The mapping is not
  symmetric and not one-to-one.
- gRPC servers always use HTTP status 200 for gRPC responses. The only
  exceptions are the cases in [`content-type`](#38-content-type) and
  [`:authority` and `Host`](#34-authority-and-host).

## 8. Errors, Cancellation, and RST_STREAM

### 8.1 Application and runtime errors

When an application or runtime error happens during a call, the server sends
the `Status` and `Status-Message` in `Trailers` (or `Trailers-Only`).

### 8.2 RST_STREAM

- Sometimes the framing of the message stream is corrupt, or a call must end
  abruptly. The runtime then uses `RST_STREAM`
  ([RFC 9113 §6.4](https://www.rfc-editor.org/rfc/rfc9113#section-6.4)) to
  tell its peer.
- A receiver of `RST_STREAM` MUST pass an error up to the application
  immediately. Inbound and outbound buffered data for the stream is
  discarded.

RST_STREAM error codes map to gRPC status codes as follows:

| HTTP/2 error code | gRPC status |
| ----------------- | ----------- |
| `NO_ERROR` (0x0) | `INTERNAL`. An explicit gRPC status of `OK` should have been sent instead. However, servers may use this to aggressively lame-duck in some cases. |
| `PROTOCOL_ERROR` (0x1) | `INTERNAL` |
| `INTERNAL_ERROR` (0x2) | `INTERNAL` |
| `FLOW_CONTROL_ERROR` (0x3) | `INTERNAL` |
| `SETTINGS_TIMEOUT` (0x4) | `INTERNAL` |
| `STREAM_CLOSED` (0x5) | No mapping, because there is no open stream to report to. Implementations SHOULD log it. |
| `FRAME_SIZE_ERROR` (0x6) | `INTERNAL` |
| `REFUSED_STREAM` (0x7) | `UNAVAILABLE`. No processing happened, and the request can be retried, possibly elsewhere. Eligible for transparent retry (see [Retries and Hedging](../04-client-channel/12-retries.md)). |
| `CANCEL` (0x8) | Sent by a client: the server treats the call as cancelled. Sent by a server: the client reports `CANCELLED`. Servers SHOULD use it only when they must cancel a call and cannot send a complete response (for example, because a message is only partly sent). |
| `COMPRESSION_ERROR` (0x9) | `INTERNAL` |
| `CONNECT_ERROR` (0xa) | `INTERNAL` |
| `ENHANCE_YOUR_CALM` (0xb) | `RESOURCE_EXHAUSTED`. The runtime adds detail saying that the exhausted resource is bandwidth. |
| `INADEQUATE_SECURITY` (0xc) | `PERMISSION_DENIED`. The runtime adds detail saying that the protocol is not secure enough for the call. |
| Any other code | `INTERNAL` |

`NO_ERROR` received before the complete `Trailers` MUST NOT be mapped to
`UNAVAILABLE` (or any other retryable code), because the server may already
have processed the call.

If a client receives `RST_STREAM` after it already received the complete
`Trailers` (END_STREAM) for the stream, the call's status is the one from
`Trailers`. The reset does not change it.

### 8.3 Server sending trailers before the request ends

- A server MAY send `Trailers` before it receives the client's EOS. Any request
  messages it has not processed, and the Half Close, are then lost.
- After sending `Trailers` with END_STREAM while the request stream is still
  open, the server SHOULD send `RST_STREAM` with `NO_ERROR`. This tells the
  client to stop sending
  ([RFC 9113 §8.1](https://www.rfc-editor.org/rfc/rfc9113#section-8.1)).

### 8.4 Deadline expiry and cancellation

- A client cancels a call (including when its deadline expires) by sending
  `RST_STREAM` with `CANCEL`, if the stream has not already closed. On deadline
  expiry, the client reports `DEADLINE_EXCEEDED`. On any other cancellation, it
  reports `CANCELLED`.
- When a call's deadline expires on the server, the server either resets the
  stream with `RST_STREAM` and `CANCEL`, or first sends `Trailers` with
  `DEADLINE_EXCEEDED`. If it sends `Trailers` and the request stream is still
  open, it then sends `RST_STREAM` as described in
  [Server sending trailers before the request ends](#83-server-sending-trailers-before-the-request-ends). If it
  does not send `Trailers`, it MUST send `RST_STREAM` with `CANCEL`, if the
  stream is not already closed.
  <!-- REVIEW(divergence) [SERVER-1]: Java: RST_STREAM(CANCEL) only, no trailers (ServerImpl.ServerStreamCancellationListener -> NettyServerStream.cancel -> CancelServerStreamCommand.withReset). Go: RST_STREAM(CANCEL) only, from a per-stream timer (http2_server.go closeStream(..., ErrCodeCancel)); a deadline already expired on arrival gets Trailers-Only DEADLINE_EXCEEDED. C++: DEADLINE_EXCEEDED trailers then RST_STREAM(NO_ERROR) (chttp2_transport.cc close_from_api). Spec previously required RST_STREAM(CANCEL) even after trailers, which C++ does not do; it now allows either: trailers followed by the [Server sending trailers before the request ends](#83-server-sending-trailers-before-the-request-ends) reset (NO_ERROR), or RST_STREAM(CANCEL) alone. [Core RPC Semantics: Communication and Enforcement](../02-rpc-semantics/README.md#82-communication-and-enforcement) and [Server: Deadlines](../05-server/01-server.md#25-deadlines) say the same. -->
- Clients and servers race to detect deadline expiry. When a client gets a
  cancellation (for example `RST_STREAM CANCEL`) on a call whose deadline has
  passed, it MUST report `DEADLINE_EXCEEDED`, not `CANCELLED`.

## 9. HTTP/2 Transport Mapping

### 9.1 Stream identification

Each call is identified by its HTTP/2 stream ID. Stream IDs only have meaning
within one HTTP/2 connection. They are not unique within a process that
handles more than one connection, and MUST NOT be used as global identifiers.

### 9.2 GOAWAY

Servers SHOULD shut down connections gracefully, with GOAWAY, as described in
[RFC 9113 §6.8](https://www.rfc-editor.org/rfc/rfc9113#section-6.8). gRPC
adds:

- The server SHOULD measure the round trip between the two GOAWAYs by sending
  a PING after the first GOAWAY and waiting for its ACK. It SHOULD also put an
  upper bound on the time between the two GOAWAYs.
- After the second GOAWAY, outstanding streams are allowed to finish. The
  server then closes the connection, possibly after a grace period (see
  [HTTP/2 Server Transport: Connection Management](../05-server/02-transports/02-http2.md#6-connection-management)).

Debug data: GOAWAY frames sent by gRPC SHOULD carry ASCII debug data that
gives the reason. These strings are defined:

| Debug data | Error code | Meaning |
| ---------- | ---------- | ------- |
| `max_idle` | `NO_ERROR` | The connection reached `MAX_CONNECTION_IDLE` ([HTTP/2 Server Transport: Connection Management](../05-server/02-transports/02-http2.md#6-connection-management)). |
| `max_age` | `NO_ERROR` | The connection reached `MAX_CONNECTION_AGE` ([HTTP/2 Server Transport: Connection Management](../05-server/02-transports/02-http2.md#6-connection-management)). |
| `too_many_pings` | `ENHANCE_YOUR_CALM` | The client broke the server's ping policy ([HTTP/2 Server Transport: Ping Enforcement](../05-server/02-transports/02-http2.md#72-ping-enforcement)). |

Clients handle GOAWAY as described in RFC 9113 §6.8. In addition:

- Streams with IDs above the last-stream-id were not processed. The client
  MUST fail them with `UNAVAILABLE`, and they are eligible for transparent
  retry (see [Retries and Hedging](../04-client-channel/12-retries.md)).
- If the connection closes while streams at or below the last-stream-id are
  still open, they fail as described in
  [Connection failure](#94-connection-failure).
- A GOAWAY with `ENHANCE_YOUR_CALM` and debug data `too_many_pings` makes the
  client raise its keepalive interval
  ([HTTP/2 Client Transport: Keepalive](../04-client-channel/08-transports/02-http2.md#61-keepalive)).
- The effect of GOAWAY on the subchannel and channel is in
  [HTTP/2 Client Transport: Handling GOAWAY](../04-client-channel/08-transports/02-http2.md#51-handling-goaway).

### 9.3 PING

- Both clients and servers can send PING frames
  ([RFC 9113 §6.7](https://www.rfc-editor.org/rfc/rfc9113#section-6.7)).
- gRPC uses PING to check that the connection is alive (keepalive), to
  estimate round-trip latency, and to estimate bandwidth-delay product.
- How often to ping depends heavily on the network. Implementations MAY adjust
  the frequency to fit network and application needs, within the limits in
  [HTTP/2 Client Transport: Liveness](../04-client-channel/08-transports/02-http2.md#6-liveness).

If a PING sent by the server gets no ACK within the expected time, the
server closes the connection, and all its outstanding calls on it end as
cancelled. If a PING sent by the client gets no ACK within the expected time,
the client closes the connection, and all calls on it fail with `UNAVAILABLE`.

### 9.4 Connection failure

If a client detects a connection failure (a transport error, an unexpected
close, a keepalive timeout, or a close after GOAWAY with streams still open),
all calls on the connection fail with `UNAVAILABLE`. Calls that produced no
wire traffic are eligible for transparent retry. If a server detects a
connection failure, its open calls on that connection are cancelled.

### 9.5 Transport security

- When TLS is used, the TLS requirements of
  [RFC 9113 §9.2](https://www.rfc-editor.org/rfc/rfc9113#section-9.2) apply
  (TLS 1.2 or later, cipher-suite restrictions, and SNI).
- When TLS is used, clients MUST offer the ALPN protocol ID `h2`
  ([RFC 9113 §3.2](https://www.rfc-editor.org/rfc/rfc9113#section-3.2)), and
  servers MUST select it. Both clients and servers MUST fail the connection if
  `h2` is not negotiated.
- Without TLS (plaintext), HTTP/2 is used with prior knowledge
  ([RFC 9113 §3.3](https://www.rfc-editor.org/rfc/rfc9113#section-3.3)). The
  HTTP/1.1 `Upgrade` mechanism is not used.
- HTTP/2 may also run over other transport security mechanisms. This
  specification makes no recommendation about them.
- Credentials and the security model are in
  [Security](../06-security/README.md) and [TLS](../06-security/02-tls.md).

## 10. Idempotency and Retries

Unless a call is explicitly defined to be idempotent, gRPC does not assume it
is. Specifically:

- A call that cannot be proven to have not started processing is not
  retried, except as allowed by a configured retry policy.
  
- There is no mechanism for duplicate suppression, and none is needed.
- A call MAY be sent more than once only when a configured retry or hedging
  policy allows it, or when it is transparently retried. gRPC has no other
  way to mark a method as idempotent (see
  [Core RPC Semantics](../02-rpc-semantics/README.md)).
  
The wire signals that prove a call was not processed are `REFUSED_STREAM`, and
GOAWAY with a last-stream-id below the stream's ID. The retry rules built on
them are in [Retries](../04-client-channel/12-retries.md).

## 11. Examples

### 11.1 Unary call

Request:

```
HEADERS (flags = END_HEADERS)
:method = POST
:scheme = http
:path = /google.pubsub.v2.PublisherService/CreateTopic
:authority = pubsub.googleapis.com
grpc-timeout = 1S
content-type = application/grpc+proto
grpc-encoding = gzip
authorization = Bearer y235.wef315yfh138vh31hv93hv8h3v

DATA (flags = END_STREAM)
<Length-Prefixed Message>
```

Response:

```
HEADERS (flags = END_HEADERS)
:status = 200
grpc-encoding = gzip
content-type = application/grpc+proto

DATA
<Length-Prefixed Message>

HEADERS (flags = END_STREAM, END_HEADERS)
grpc-status = 0 # OK
trace-proto-bin = jher831yy13JHy3hc
```

The request example leaves out `te: trailers` for brevity. Real clients MUST
send it ([`te`](#36-te)).

### 11.2 Immediate error (Trailers-Only)

```
HEADERS (flags = END_STREAM, END_HEADERS)
:status = 200
content-type = application/grpc+proto
grpc-status = 12
grpc-message = Method%20not%20found%3A%20Foo
```

## 12. API Requirements

- The channel and call APIs MUST let applications set custom request metadata
  (ASCII and binary) and read response headers and trailers. Binary values are
  given and received as raw bytes, with base64 handled by the library.
- The client API MUST let applications set a call deadline, which is sent as
  `grpc-timeout`.
- The client API MUST let applications override the authority for a call,
  subject to the checks in [Security](../06-security/README.md).
- The server API MUST let applications send response headers explicitly
  before the first message, and read the request's authority, metadata, and
  remaining deadline.
- The channel API SHOULD let applications add a user-agent string, which is
  combined with the library's user-agent.
- Servers and clients MUST provide a way to set the maximum received header
  list size ([Header list size](#45-header-list-size)).
- The compression API is in [Core RPC Semantics](../02-rpc-semantics/README.md).
