> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 5.2.3 HTTP/3 Server Transport

<!-- Sources: G2 -->

> **Introduced by:** [gRFC G2: gRPC over HTTP/3](https://github.com/grpc/proposal/blob/master/G2-http3-protocol.md)

This document covers server-side connection behavior for gRPC over
[HTTP/3](https://www.rfc-editor.org/rfc/rfc9114) on
[QUIC](https://www.rfc-editor.org/rfc/rfc9000): HTTP/3 listeners and
advertisement, graceful shutdown with GOAWAY, connection management, and
keepalive. It follows the structure of the
[Server Transport Model](01-transport-model.md). The per-call wire mapping is
in [gRPC over HTTP/3](../../03-wire-protocol/03-http3.md), and the client
side is in
[HTTP/3 Client Transport](../../04-client-channel/08-transports/03-http3.md).

These requirements apply to implementations that support HTTP/3.

## 1. Overview

An HTTP/3 server transport is one QUIC+HTTP/3 connection accepted on an
HTTP/3 listener. Each client-initiated bidirectional QUIC stream is one
incoming call. Where this document does not say otherwise, the server-side
behavior in [HTTP/2 Server Transport](02-http2.md) has the same purpose for
HTTP/3.

## 2. Listening and Connection Establishment

Both client and server must support HTTP/3 for it to be used. A client either
connects with HTTP/3 directly or upgrades from HTTP/2 after the server
advertises HTTP/3 (`h3`) in an `alt-svc` header
([RFC 7838](https://www.rfc-editor.org/rfc/rfc7838)) on an HTTP/2 response
(see
[HTTP/3 Client Transport: Negotiating HTTP/3](../../04-client-channel/08-transports/03-http3.md#21-negotiating-http3)).
Connection establishment, including TLS and the `h3` ALPN token, follows
[RFC 9114 §3](https://www.rfc-editor.org/rfc/rfc9114#section-3).

## 3. Graceful Shutdown and Draining

HTTP/3 `GOAWAY` frames serve the same purpose as in HTTP/2
([GOAWAY](../../03-wire-protocol/01-http2.md#92-goaway)). gRPC servers SHOULD
shut down gracefully as described in
[RFC 9114 §5.2](https://www.rfc-editor.org/rfc/rfc9114#section-5.2).

## 4. Connection Management

Connection management (idle timeout, max age, grace) has the same purpose and
settings as in
[HTTP/2 Server Transport: Connection Management](02-http2.md#6-connection-management).

## 5. Liveness and Enforcement

Keepalive has the same purpose and settings as in
[HTTP/2 Server Transport: Liveness and Enforcement](02-http2.md#7-liveness-and-enforcement).
HTTP/3 has no PING frame of its own. Keepalive MAY use QUIC PING frames
([RFC 9000 §19.2](https://www.rfc-editor.org/rfc/rfc9000#section-19.2)) or
the QUIC idle timeout instead of HTTP/2 PING.

## 6. API Requirements

- The server API MUST provide a way to enable HTTP/3 listeners.
- The server API SHOULD provide a way to advertise HTTP/3 through `alt-svc` on
  HTTP/2 responses, since without that advertisement the Alt-Svc upgrade mode
  cannot work.
