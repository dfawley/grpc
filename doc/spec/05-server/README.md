> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 5. Server

<!-- Sources: doc/PROTOCOL-HTTP2.md, doc/statuscodes.md, doc/compression.md, doc/server_side_auth.md, doc/keepalive.md, A6, A8, A9, A51 -->

This section specifies server-side gRPC behavior: server lifecycle, listening
addresses, request validation and dispatch, response semantics, server
interceptors, connection management, and server transports.

## Contents

- [5.1 Server Behavior](01-server.md): lifecycle, request handling, response semantics, interceptors, connection management
- 5.2 Server Transports
  - [5.2.1 Server Transport Model](02-transports/01-transport-model.md)
  - [5.2.2 HTTP/2 Server Transport](02-transports/02-http2.md)
  - [5.2.3 HTTP/3 Server Transport](02-transports/03-http3.md)
  - [5.2.4 In-Process Server Transport](02-transports/04-in-process.md)
