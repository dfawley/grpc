> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 5. Server

<!-- Sources: doc/PROTOCOL-HTTP2.md, doc/statuscodes.md, doc/compression.md, doc/server_side_auth.md, doc/keepalive.md, A6, A9, A51 -->

A gRPC **server** accepts incoming connections on one or more listening
addresses and dispatches the RPCs that arrive on those connections to
application-provided handlers. A server hosts a set of **services**. Each
service is a named group of **methods**. Each RPC names exactly one method by
its *full method name* (`/<service>/<method>`, see
[Core RPC Semantics](../02-rpc-semantics/README.md)). Only one server processes a given
RPC, even when several servers could have received it.

A connection is not a gRPC semantic concept on the server either. Handlers MUST
NOT assume any correlation between connections and RPCs, except that an RPC
cannot outlive the connection that carries it.

## Contents

- [5.1 Server Behavior](01-server.md): lifecycle, request handling, response semantics, interceptors, connection management
- 5.2 Server Transports
  - [5.2.1 Server Transport Model](02-transports/01-transport-model.md)
  - [5.2.2 HTTP/2 Server Transport](02-transports/02-http2.md)
  - [5.2.3 HTTP/3 Server Transport](02-transports/03-http3.md)
  - [5.2.4 In-Process Server Transport](02-transports/04-in-process.md)
