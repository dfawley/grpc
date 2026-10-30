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

## Contents

- [3.1 gRPC over HTTP/2](01-http2.md): request/response grammar, headers, metadata encoding, message framing, status and error mapping, non-gRPC responses, RST_STREAM/GOAWAY/PING, TLS
- [3.2 True Binary Metadata](02-true-binary-metadata.md): HTTP/2 extension for sending `-bin` metadata without base64
- [3.3 gRPC over HTTP/3](03-http3.md): HTTP/3 mapping: stream identification, error codes, stream reset, deadlines and cancellation
- [3.4 Protocol Buffers Mapping](04-protobuf.md): services, methods, and messages on the wire; content-subtypes; rich status details

## Related sections

- Deadline, cancellation, metadata, and status semantics:
  [Core RPC Semantics](../02-rpc-semantics/README.md).
- How the client chooses the `:authority` value:
  [Channel](../04-client-channel/02-channel.md).
- Connections and their lifecycle inside the client:
  [Subchannels](../04-client-channel/07-subchannels.md).
- Transparent retries and the retry-related headers:
  [Retries](../04-client-channel/12-retries.md).
- Connection-level behavior of each transport (settings, stream limits, flow
  control, keepalive, connection management): [Client Transport Model](../04-client-channel/08-transports/01-transport-model.md)
  and [Server Transport Model](../05-server/02-transports/01-transport-model.md).
- HTTP CONNECT proxies: [Proxy support](../04-client-channel/09-proxy.md).
- Transport security: [Security](../06-security/README.md) and
  [TLS](../06-security/02-tls.md).
- Server-side behavior, including graceful shutdown: [Server](../05-server/README.md).
