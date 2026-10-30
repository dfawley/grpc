> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 3. Wire Protocol

<!-- Sources: doc/PROTOCOL-HTTP2.md, G1, G2, doc/keepalive.md, A8, A9, A18, A105 -->

This section specifies how the abstract RPC model of
[Core RPC Semantics](../02-rpc-semantics/README.md) is carried over the network.

gRPC is defined on top of HTTP semantics. A Call maps onto one HTTP request
and its response, carried on a single HTTP stream:

| Abstract concept ([Core RPC Semantics](../02-rpc-semantics/README.md)) | HTTP mapping |
| ---------------------------- | ------------ |
| Request Headers (full method name, metadata, deadline) | Request header block (`:path`, custom headers, `grpc-timeout`) |
| Request message | Length-prefixed message in the request body |
| Half Close | End of the request body (END_STREAM) |
| Response Headers (metadata) | Response header block |
| Response message | Length-prefixed message in the response body |
| Trailers (status, metadata) | Trailer block (`grpc-status`, `grpc-message`, custom trailers), or a single Trailers-Only header block |
| Cancellation | Abrupt stream reset (HTTP/2 `RST_STREAM`, QUIC `RESET_STREAM`) |

HTTP/2 is the primary, interoperable transport. Every gRPC implementation
SHOULD support it. HTTP/3 is also defined. Both use the same request and
response shape, so an HTTP/3 implementation adds only the transport mapping.

## 1. Contents

| Document | Content |
| -------- | ------- |
| [gRPC over HTTP/2](01-http2.md) | Request/response grammar (ABNF), headers, metadata encoding, message framing, status and error mapping, handling non-gRPC responses, RST_STREAM/GOAWAY/PING semantics, TLS. |
| [HTTP/2 transport behavior](02-http2-transport.md) | SETTINGS, MAX_CONCURRENT_STREAMS reporting, flow control, client and server keepalive, ping abuse enforcement, TCP_USER_TIMEOUT, server connection management (idle/age), GOAWAY handling. |
| [True binary metadata](03-true-binary-metadata.md) | HTTP/2 extension for sending `-bin` metadata without base64. |
| [gRPC over HTTP/3](04-http3.md) | Differences from HTTP/2: error codes, GOAWAY, stream reset, negotiation. |
| [Protocol Buffers mapping](05-protobuf.md) | How protobuf services, methods, and messages map to the wire; the `+proto` content-subtype and other content-subtypes; rich status details. |

## 2. Related sections

- Deadline, cancellation, metadata, and status semantics:
  [Core RPC Semantics](../02-rpc-semantics/README.md).
- How the client chooses the `:authority` value:
  [Channel](../04-client-channel/01-channel.md).
- Connections and their lifecycle inside the client:
  [Subchannels](../04-client-channel/06-subchannels.md).
- Transparent retries and the retry-related headers:
  [Retries](../04-client-channel/10-retries.md).
- HTTP CONNECT proxies: [Proxy support](../04-client-channel/07-proxy.md).
- Transport security: [Security](../06-security/README.md) and
  [TLS](../06-security/01-tls.md).
- Server-side behavior, including graceful shutdown: [Server](../05-server/README.md).
