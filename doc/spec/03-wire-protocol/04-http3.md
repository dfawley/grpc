> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 3.4 gRPC over HTTP/3

<!-- Sources: G2, doc/PROTOCOL-HTTP2.md -->

> **Introduced by:** [gRFC G2: gRPC over HTTP/3](https://github.com/grpc/proposal/blob/master/G2-http3-protocol.md)

This section covers how gRPC runs over
[HTTP/3](https://www.rfc-editor.org/rfc/rfc9114) on
[QUIC](https://www.rfc-editor.org/rfc/rfc9000). Compared with HTTP/2, HTTP/3
connects faster (fewer round trips), handles packet loss better, and supports
connection migration between networks.

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
  [true binary metadata](03-true-binary-metadata.md) extension does not apply.

## 2. Transport Mapping

The HTTP/2 transport mapping in [gRPC over HTTP/2: HTTP/2 Transport Mapping](01-http2.md#9-http2-transport-mapping)
also applies to HTTP/3, except as stated below.

### 2.1 Stream identification

HTTP/3 stream IDs (QUIC client-initiated bidirectional stream IDs) identify
calls in the same way HTTP/2 stream IDs do. They only have meaning within one
connection.

### 2.2 DATA frames

DATA frames relate to length-prefixed messages the same way as in HTTP/2:
frame boundaries have no relation to message boundaries.

### 2.3 Errors

HTTP/3 has its own error codes
([RFC 9114 §8.1](https://www.rfc-editor.org/rfc/rfc9114#section-8.1)), and they
are sent in QUIC frames, not in an HTTP-layer `RST_STREAM`. They are used in
three situations:

- abruptly terminating a stream (QUIC `RESET_STREAM`),
- aborting reading of a stream (QUIC `STOP_SENDING`),
- immediately closing the connection (QUIC `CONNECTION_CLOSE`).

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

### 2.4 Connection management

- HTTP/3 has `GOAWAY` frames, which serve the same purpose as in HTTP/2
  ([GOAWAY](01-http2.md#92-goaway)).
- Keepalive and connection management (idle timeout, max age, grace) have
  the same purpose and settings as in [HTTP/2 Transport Behavior](02-http2-transport.md). HTTP/3
  has no PING frame of its own. Keepalive MAY use QUIC PING frames
  ([RFC 9000 §19.2](https://www.rfc-editor.org/rfc/rfc9000#section-19.2)) or
  the QUIC idle timeout instead of HTTP/2 PING.

GOAWAY differs from HTTP/2 in one way. An HTTP/2 GOAWAY carries the *last*
stream ID the server accepted. An HTTP/3 GOAWAY carries an ID *greater than*
the last stream ID the server accepted. Requests on streams with an ID equal
to or greater than that value were not processed. The client MUST fail them
with `UNAVAILABLE`, and they are eligible for transparent retry.

A server shutting down gracefully SHOULD use a two-phase shutdown, as in
HTTP/2. The first GOAWAY carries the largest possible client-initiated
bidirectional stream ID (2^62-4), as
[RFC 9114 §5.2](https://www.rfc-editor.org/rfc/rfc9114#section-5.2)
suggests. After at least one round trip, a second GOAWAY carries the real
limit. As RFC 9114 requires, the ID in a later GOAWAY MUST NOT be greater than
the ID in an earlier one.

## 3. Deadline Expiry and Cancellation

When a call exceeds its deadline, the stream is reset. HTTP/3 has no
`RST_STREAM` frame, so the QUIC `RESET_STREAM` frame is used instead:

| Transport | Frame | Error code | Layer |
| --------- | ----- | ---------- | ----- |
| HTTP/2 | `RST_STREAM` | `CANCEL` (0x8) | HTTP |
| HTTP/3 | `RESET_STREAM` | `H3_REQUEST_CANCELLED` (0x010c) | QUIC |

- `RESET_STREAM` abruptly ends sending on one direction of a stream. QUIC can
  deliver frames out of order. So a `RESET_STREAM` sent after a complete
  response can still cause the peer to abort that response. Implementations
  SHOULD NOT reset a stream after its response has been fully sent.
- A server sends QUIC `STOP_SENDING` when a stream's response side finishes
  before its request side. `STOP_SENDING` alone is not enough for an exceeded
  deadline, because both directions must be aborted. If the deadline expires
  while the request side is still open, the server SHOULD send both
  `STOP_SENDING` and `RESET_STREAM` with `H3_REQUEST_CANCELLED`.
- Client-initiated cancellation uses the same frames and code.

## 4. Negotiating HTTP/3

Both client and server must support HTTP/3 for it to be used. There are two
ways to set up an HTTP/3 connection:

1. **Configured HTTP/3 only.** The client is set up in advance to use only
   HTTP/3. It opens a QUIC+HTTP/3 connection to the server. If the server does
   not support HTTP/3, the connection attempt fails.
2. **HTTP/2 with upgrade via Alt-Svc.** The client is set up to use HTTP/2 or
   later. It makes its first call over HTTP/2. If the server's response
   includes an `alt-svc` header
   ([RFC 7838](https://www.rfc-editor.org/rfc/rfc7838)) advertising HTTP/3
   (`h3`), the client replaces the HTTP/2 connection with a QUIC+HTTP/3
   connection, and later calls use HTTP/3. If the server does not advertise
   HTTP/3, or the HTTP/3 connection cannot be made, the client keeps using
   HTTP/2.

HTTP/3 requires TLS (TLS 1.3, as QUIC requires). It MUST NOT be used by a
channel with insecure credentials. The ALPN protocol ID is `h3`.

## 5. API Requirements

HTTP/3 support is optional. These requirements apply only to implementations
that support HTTP/3.

- The channel API MUST provide a way to choose how the HTTP version is
  negotiated, with at least these options: HTTP/2 only, HTTP/3 only, and
  HTTP/2 with upgrade to HTTP/3 via Alt-Svc. The form of this setting is up to
  each implementation.
- The server API MUST provide a way to enable HTTP/3 listeners. It SHOULD
  provide a way to advertise HTTP/3 through `alt-svc` on HTTP/2 responses,
  since without that advertisement the Alt-Svc upgrade mode cannot work.

