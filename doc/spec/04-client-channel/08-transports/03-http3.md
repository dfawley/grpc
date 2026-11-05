> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4.8.3 HTTP/3 Client Transport

<!-- Sources: G2 -->

> **Introduced by:** [gRFC G2: gRPC over HTTP/3](https://github.com/grpc/proposal/blob/master/G2-http3-protocol.md)

This document covers client-side connection behavior for gRPC over
[HTTP/3](https://www.rfc-editor.org/rfc/rfc9114) on
[QUIC](https://www.rfc-editor.org/rfc/rfc9000): negotiating HTTP/3, GOAWAY
handling, and keepalive. It follows the structure of the
[Client Transport Model](01-transport-model.md). The per-call wire mapping is
in [gRPC over HTTP/3](../../03-wire-protocol/03-http3.md), and the server
side is in
[HTTP/3 Server Transport](../../05-server/02-transports/03-http3.md).

These requirements apply to implementations that support HTTP/3.

## 1. Overview

An HTTP/3 client transport is one QUIC+HTTP/3 connection. Each call attempt
is one client-initiated bidirectional QUIC stream. Where this document does
not say otherwise, the client-side behavior in
[HTTP/2 Client Transport](02-http2.md) has the same purpose for HTTP/3.

## 2. Connection Establishment

### 2.1 Negotiating HTTP/3

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

HTTP/3 runs over QUIC, which always uses TLS 1.3
([RFC 9001](https://www.rfc-editor.org/rfc/rfc9001)), so HTTP/3 MUST NOT be
used by a channel with insecure credentials. The ALPN protocol ID is `h3`
([RFC 9114 §3.1](https://www.rfc-editor.org/rfc/rfc9114#section-3.1)).

## 3. Draining and Closure

HTTP/3 `GOAWAY` frames
([RFC 9114 §7.2.6](https://www.rfc-editor.org/rfc/rfc9114#section-7.2.6))
serve the same graceful-draining purpose as in HTTP/2, and the client reacts to
them at the subchannel and LB-policy level as described in
[HTTP/2 Client Transport: Handling GOAWAY](02-http2.md#51-handling-goaway),
with the following protocol differences:

- An HTTP/3 `GOAWAY` frame carries only a Stream ID, with no error code or
  debug data.
- Requests whose Stream ID is **greater than or equal to** the `GOAWAY` Stream
  ID were not processed by the server
  ([RFC 9114 §5.2](https://www.rfc-editor.org/rfc/rfc9114#section-5.2)). They
  MUST be failed with `UNAVAILABLE`, and they are eligible for transparent
  retry.
- Connection-level error codes (such as `H3_NO_ERROR` and `H3_EXCESSIVE_LOAD`)
  are carried in QUIC `CONNECTION_CLOSE` frames
  ([RFC 9000 §19.19](https://www.rfc-editor.org/rfc/rfc9000#section-19.19))
  rather than in `GOAWAY` (see
  [gRPC over HTTP/3: Errors](../../03-wire-protocol/03-http3.md#23-errors)).

## 4. Liveness

Keepalive has the same purpose and settings as in
[HTTP/2 Client Transport: Keepalive](02-http2.md#61-keepalive). HTTP/3 has
no PING frame of its own. Keepalive MAY use QUIC PING frames
([RFC 9000 §19.2](https://www.rfc-editor.org/rfc/rfc9000#section-19.2)) or
the QUIC idle timeout
([RFC 9000 §10.1](https://www.rfc-editor.org/rfc/rfc9000#section-10.1))
instead of HTTP/2 PING. `TCP_USER_TIMEOUT` does not apply to HTTP/3, because
QUIC runs over UDP and manages retransmission and loss detection itself.

## 5. API Requirements

- The channel API MUST provide a way to choose how the HTTP version is
  negotiated, with at least these options: HTTP/2 only, HTTP/3 only, and
  HTTP/2 with upgrade to HTTP/3 via Alt-Svc
  ([Negotiating HTTP/3](#21-negotiating-http3)). The form of this setting is
  up to each implementation.
