> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4.8.4 In-Process Client Transport

<!-- Sources: implementations (no gRFC or grpc/doc document specifies the in-process transport); doc/core/transport_explainer.md (informative) -->

## 1. Overview

An implementation MAY provide an in-process transport: a client transport and
a server transport that are connected to each other within one process,
without a network connection. The server side is described in
[In-Process Server Transport](../../05-server/02-transports/04-in-process.md).

The behavior of the in-process transport is entirely implementation-defined.
This includes how a channel addresses an in-process server, the channel's
default authority, the security and peer information that calls observe,
which message and metadata size limits are enforced, whether messages are
serialized or compressed, how cancellation and deadlines propagate, stream
limits, flow control, draining and closure, and which channel features
(such as name resolution, load balancing, retries, and keepalive) apply to
channels that use it. The [Client Transport Model](01-transport-model.md)
does not constrain the in-process transport.

## 2. API Requirements

- If an implementation provides an in-process transport, the channel API MUST
  provide a way to create a channel whose calls reach a server in the same
  process over that transport. The form of this API is implementation-defined.
