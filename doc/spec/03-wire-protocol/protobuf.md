> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 3.5 Protocol Buffers Mapping

<!-- Sources: doc/PROTOCOL-HTTP2.md (Appendix A, content-type), doc/statuscodes.md, L44 (background on status details consistency) -->

gRPC does not depend on any IDL or message format. Protocol Buffers is the
default and best-supported IDL. Code generators (protoc plugins) produce
client stubs and server bases from `service` definitions. This section
defines how a Protocol Buffers service maps onto the wire protocol in
[gRPC over HTTP/2](http2.md).

## 1. Services and Methods

```abnf
Service-Name     = ?( {proto package name} "." ) {service name}
Method-Name      = {method name as declared in the service}
Message-Type     = {fully qualified proto message name}
Content-Type     = "application/grpc+proto"     ; "application/grpc" is equivalent
Status-Details   = {serialized google.rpc.Status message}
```

- `Service-Name` is the service's fully qualified protobuf name: the package
  (if any), a `.`, then the service name. Example: `google.pubsub.v2.PublisherService`.
  It does not start with a `.`.
- `Method-Name` is the `rpc` name exactly as declared. Example: `CreateTopic`.
- The `:path` is `/` + `Service-Name` + `/` + `Method-Name`. Example:
  `/google.pubsub.v2.PublisherService/CreateTopic`. Matching is
  case-sensitive.
- The method's cardinality comes from the `stream` keyword:

  | Declaration | Cardinality |
  | ----------- | ----------- |
  | `rpc M(Req) returns (Resp)` | unary |
  | `rpc M(Req) returns (stream Resp)` | server-streaming |
  | `rpc M(stream Req) returns (Resp)` | client-streaming |
  | `rpc M(stream Req) returns (stream Resp)` | bidirectional streaming |

- Cardinality is not sent on the wire. Both peers know it from the method
  definition.
- The rules for cardinality violations (for example, a unary method receiving
  zero or two request messages) are in
  [Core RPC Semantics](../02-rpc-semantics/README.md).
- If `grpc-message-type` is sent, its value is the fully qualified name of
  the message type sent in that direction (without a leading `.`).

## 2. Message Encoding (`+proto`)

- Each `Message` in a `Length-Prefixed-Message` is the protobuf binary
  serialization of one request or response message. It is then compressed if
  the Compressed-Flag is 1.
- An empty message serializes to zero bytes, which is valid.
- `content-type: application/grpc` with no content-subtype means `+proto`.
- If a received message cannot be parsed, the call fails with `INTERNAL`.
  This applies to the client parsing a response and to the server parsing a
  request.

## 3. Other Content-Subtypes

Other content-subtypes (`content-type: application/grpc+{name}`) MAY be used
for other message encodings, by agreement between client and server.
Everything else is unchanged: the length prefix, compression, metadata, and
status.

A server that does not support a received content-subtype MAY fail the call
with `UNIMPLEMENTED`, sent as a gRPC status
([`content-type`](http2.md#38-content-type)). Otherwise it processes the call
with the method's default codec.

## 4. Rich Error Details

- When the status is not `OK`, a server MAY send rich error details in the
  `grpc-status-details-bin` trailer. Its value is a serialized
  `google.rpc.Status` message (`google/rpc/status.proto` in googleapis):

  ```proto
  message Status {
    int32 code = 1;                          // google.rpc.Code; same numbering as gRPC status codes
    string message = 2;                      // developer-facing error message
    repeated google.protobuf.Any details = 3; // e.g. google.rpc.ErrorInfo, RetryInfo, BadRequest
  }
  ```

  It is binary metadata, so it is base64-encoded on the wire
  ([Binary values](http2.md#43-binary-values)).
- Senders MUST set `Status.code` to the same value as `grpc-status`, and
  `Status.message` to the same string as the (decoded) `grpc-message`.
- Receivers MAY check that the details match `grpc-status` and
  `grpc-message`, and MAY act on a mismatch or on details that cannot be
  parsed (for example by not presenting the parsed details as part of the
  call's status). They are not required to check. Whatever the receiver does,
  applications MUST be able to read the raw `grpc-status-details-bin` trailer
  value (see [`grpc-status-details-bin`](http2.md#65-grpc-status-details-bin)).
- `grpc-status-details-bin` MUST NOT be sent with status `OK`.

## 5. Related Services

- Generated code publishes the service's descriptors, so services can be
  discovered at runtime through server reflection
  ([Server reflection](../07-services/reflection.md)).
- The standard services ([Standard services](../07-services/README.md)) are
  defined in protobuf in grpc-proto, for example `grpc/health/v1/health.proto`.

## 6. API Requirements

- Generated client stubs MUST provide one method per `rpc`, with the
  cardinality given by the `stream` keywords. They send the full method name
  in the `:path` form above.
- Generated server code MUST register handlers under the same full method
  names.
- The status API MUST let server applications attach `google.rpc.Status`
  details to a non-OK status. It MUST let client applications read them. If
  the library checks consistency as described in
  [Rich Error Details](#4-rich-error-details), it MAY withhold parsed details
  that fail the check, but the raw `grpc-status-details-bin` trailer value
  MUST remain readable.
