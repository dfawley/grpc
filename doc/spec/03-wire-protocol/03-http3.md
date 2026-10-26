> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 3.3 gRPC over HTTP/3

<!-- Sources: G2, doc/PROTOCOL-HTTP2.md -->

> **Introduced by:** [gRFC G2: gRPC over HTTP/3](https://github.com/grpc/proposal/blob/master/G2-http3-protocol.md)

This section covers how gRPC runs over
[HTTP/3](https://www.rfc-editor.org/rfc/rfc9114) on
[QUIC](https://www.rfc-editor.org/rfc/rfc9000). Compared with HTTP/2, HTTP/3
connects faster (fewer round trips), handles packet loss better, and supports
connection migration between networks.

This document specifies the per-call mapping. Connection-level behavior
(negotiating HTTP/3, GOAWAY and graceful shutdown, keepalive, and connection
management) is specified in
[HTTP/3 Client Transport](../04-client-channel/08-transports/03-http3.md) and
[HTTP/3 Server Transport](../05-server/02-transports/03-http3.md).

## 1. HTTP Semantics

gRPC requests and responses have the same shape over HTTP/3 as over HTTP/2.
Everything in [gRPC over HTTP/2](01-http2.md) about requests, responses, headers, metadata
encoding, length-prefixed messages, status, and handling non-gRPC responses
applies unchanged. In particular:

- The content-type is still `application/grpc` (with or without a
  content-subtype). It does not change for HTTP/3.
- `Response-Headers`, `Trailers`, and `Trailers-Only` are sent as HTTP/3
  HEADERS frames. EOS is the end of the QUIC stream (the FIN bit), not an
  END_STREAM flag.
- Binary metadata is base64-encoded. The HTTP/2
  [true binary metadata](02-true-binary-metadata.md) extension does not apply.

## 2. Transport Mapping

The HTTP/2 transport mapping in [gRPC over HTTP/2: HTTP/2 Transport Mapping](01-http2.md#9-http2-transport-mapping)
also applies to HTTP/3, except as stated below. How GOAWAY and keepalive
differ from HTTP/2 is specified in
[HTTP/3 Client Transport](../04-client-channel/08-transports/03-http3.md) and
[HTTP/3 Server Transport](../05-server/02-transports/03-http3.md).

### 2.1 Stream identification

HTTP/3 stream IDs (QUIC client-initiated bidirectional stream IDs) identify
calls in the same way HTTP/2 stream IDs do. They only have meaning within one
connection.

### 2.2 DATA frames

DATA frames relate to length-prefixed messages the same way as in HTTP/2:
frame boundaries have no relation to message boundaries.

### 2.3 Errors

HTTP/3 error codes
([RFC 9114 §8.1](https://www.rfc-editor.org/rfc/rfc9114#section-8.1)) are
carried in QUIC `RESET_STREAM`, `STOP_SENDING`, and `CONNECTION_CLOSE` frames
([RFC 9114 §8](https://www.rfc-editor.org/rfc/rfc9114#section-8)), not in an
HTTP-layer `RST_STREAM`.

A client that receives one of these codes for a call maps it to a gRPC status
as follows. The HTTP/2 column shows the matching code in the
[HTTP/2 mapping](01-http2.md#82-rst_stream).

| HTTP/3 error code | HTTP/2 equivalent | gRPC status |
| ----------------- | ----------------- | ----------- |
| `H3_NO_ERROR` (0x0100) | `NO_ERROR` (0x0) | `INTERNAL`. An explicit gRPC status of `OK` should have been sent instead. However, servers may use this to aggressively lame-duck in some cases. |
| `H3_GENERAL_PROTOCOL_ERROR` (0x0101) | `PROTOCOL_ERROR` (0x1) | `INTERNAL` |
| `H3_INTERNAL_ERROR` (0x0102) | `INTERNAL_ERROR` (0x2) | `INTERNAL` |
| `H3_STREAM_CREATION_ERROR` (0x0103) | none | `INTERNAL` |
| `H3_CLOSED_CRITICAL_STREAM` (0x0104) | none | `INTERNAL` |
| `H3_FRAME_UNEXPECTED` (0x0105) | `FRAME_SIZE_ERROR` | `INTERNAL` |
| `H3_FRAME_ERROR` (0x0106) | `FRAME_SIZE_ERROR` | `INTERNAL` |
| `H3_EXCESSIVE_LOAD` (0x0107) | `ENHANCE_YOUR_CALM` | `RESOURCE_EXHAUSTED`. The runtime adds detail saying that the exhausted resource is bandwidth. |
| `H3_ID_ERROR` (0x0108) | none | `INTERNAL` |
| `H3_SETTINGS_ERROR` (0x0109) | `SETTINGS_TIMEOUT` (0x4) | `INTERNAL` |
| `H3_MISSING_SETTINGS` (0x010a) | `SETTINGS_TIMEOUT` (0x4) | `INTERNAL` |
| `H3_REQUEST_REJECTED` (0x010b) | `REFUSED_STREAM` | `UNAVAILABLE`. No processing happened, and the request can be retried, possibly elsewhere. Eligible for transparent retry. |
| `H3_REQUEST_CANCELLED` (0x010c) | `CANCEL` (0x8) | Sent by a client: the server treats the call as cancelled. Sent by a server: the client reports `CANCELLED`. Servers SHOULD use it only when they must cancel a call and cannot send a complete response. |
| `H3_REQUEST_INCOMPLETE` (0x010d) | none | `INTERNAL` |
| `H3_MESSAGE_ERROR` (0x010e) | none | `INTERNAL` |
| `H3_CONNECT_ERROR` (0x010f) | `CONNECT_ERROR` | `INTERNAL` |
| `H3_VERSION_FALLBACK` (0x0110) | none | `INTERNAL` |
| Any other code | none | `INTERNAL` |

HTTP/2 codes that have no HTTP/3 equivalent (`FLOW_CONTROL_ERROR`,
`STREAM_CLOSED`, `COMPRESSION_ERROR`, `INADEQUATE_SECURITY`) do not occur on
HTTP/3. QUIC handles flow control and security itself.

## 3. Deadline Expiry and Cancellation

When a call exceeds its deadline, the stream is reset. HTTP/3 has no
`RST_STREAM` frame, so the QUIC `RESET_STREAM` frame is used instead:

| Transport | Frame | Error code | Layer |
| --------- | ----- | ---------- | ----- |
| HTTP/2 | `RST_STREAM` | `CANCEL` (0x8) | HTTP |
| HTTP/3 | `RESET_STREAM` | `H3_REQUEST_CANCELLED` (0x010c) | QUIC |

- A `RESET_STREAM` can cause the peer to discard data already sent on the
  stream ([RFC 9000 §3.2](https://www.rfc-editor.org/rfc/rfc9000#section-3.2)),
  including a complete response. Implementations SHOULD NOT reset a stream
  after its response has been fully sent.
- When the response finishes before the request, the server stops the request
  side with `STOP_SENDING` as described in
  [RFC 9114 §4.1](https://www.rfc-editor.org/rfc/rfc9114#section-4.1). That
  alone is not enough for an exceeded deadline, because both directions must
  be aborted: if the deadline expires while the request side is still open,
  the server SHOULD send both `STOP_SENDING` and `RESET_STREAM` with
  `H3_REQUEST_CANCELLED`.
- Client-initiated cancellation uses the same frames and code.

## 4. API Requirements

This document adds no API requirements. The API requirements for HTTP/3 are in
[HTTP/3 Client Transport: API Requirements](../04-client-channel/08-transports/03-http3.md#5-api-requirements)
and
[HTTP/3 Server Transport: API Requirements](../05-server/02-transports/03-http3.md#6-api-requirements).
