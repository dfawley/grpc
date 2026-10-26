> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 5.2.4 In-Process Server Transport

<!-- Sources: implementations (no gRFC or grpc/doc document specifies the in-process transport); doc/core/transport_explainer.md (informative) -->

## 1. Overview

An implementation MAY provide an in-process transport: a client transport and
a server transport that are connected to each other within one process,
without a network connection. The client side is described in
[In-Process Client Transport](../../04-client-channel/08-transports/04-in-process.md).

The behavior of the in-process transport is entirely implementation-defined.
This includes how a server is made reachable by in-process clients (for
example, by registering a name or by direct reference), the security and peer
information that handlers observe, which server limits and connection
management settings apply, stream limits, flow control, keepalive, and the
behavior of in-process connections during graceful and forced server
shutdown. The [Server Transport Model](01-transport-model.md) does not
constrain the in-process transport.

## 2. API Requirements

- If an implementation provides an in-process transport, the server API MUST
  provide a way to make a server reachable by in-process clients. The form of
  this API is implementation-defined.
