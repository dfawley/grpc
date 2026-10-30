> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# Appendix A. Reserved and Well-Known Metadata Keys

<!-- Sources: doc/spec/03-wire-protocol/01-http2.md, doc/spec/02-rpc-semantics/README.md, doc/spec/04-client-channel/10-retries.md, doc/spec/04-client-channel/07-proxy.md, doc/spec/03-wire-protocol/04-http3.md, doc/spec/06-security/02-call-credentials.md, doc/spec/07-services/03-orca.md, doc/spec/08-observability/04-tracing.md, doc/spec/08-observability/06-binary-logging.md, doc/spec/09-xds/06-http-filters.md, doc/spec/09-xds/03-resources/01-common-types.md, doc/PROTOCOL-HTTP2.md, A6, A33, A51, A55, A60, A72, A86, G2 -->

This appendix lists every metadata key and HTTP header name that this
specification gives a meaning to. It is an index. The linked sections are
normative. Where this table and a linked section disagree, the linked section
wins.

## A.1 Conventions

- **Direction** gives where the key can appear:
  - *Request headers*: the client's initial metadata (HTTP/2 `Request-Headers`).
  - *Response headers*: the server's initial metadata (HTTP/2
    `Response-Headers`).
  - *Trailers*: the server's trailing metadata (HTTP/2 `Trailers`, or the
    trailer part of `Trailers-Only`).
- **Set by** says who produces the key:
  - *gRPC*: the gRPC library. Applications MUST NOT set it as custom metadata.
  - *gRPC (plugin)*: a gRPC component that the application enables, such as
    call credentials, a tracing propagator, an ORCA recorder, or an xDS HTTP
    filter.
  - *Application*: application metadata whose meaning a gRPC feature defines.
  - *Peer*: an HTTP intermediary or a non-gRPC peer.
- Names are lowercase on the wire (see [gRPC over HTTP/2](../03-wire-protocol/01-http2.md), [Header names](../03-wire-protocol/01-http2.md#41-header-names)).
  Keys ending in `-bin` carry binary values. They are base64-encoded on the
  wire unless [true binary metadata](../03-wire-protocol/03-true-binary-metadata.md)
  is in use.
- All keys that begin with `grpc-` are reserved for gRPC, whether or not they
  appear below. Applications MUST NOT send them as custom metadata (see
  [Core RPC Semantics](../02-rpc-semantics/README.md), [Core RPC Semantics: Reserved Keys](../02-rpc-semantics/README.md#75-reserved-keys)).

## A.2 HTTP/2 Headers

| Name | Direction | Set by | Format | Defined in |
| --- | --- | --- | --- | --- |
| `:method` | Request headers | gRPC | Always `POST`. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`:method`, `:scheme`, and `:path`](../03-wire-protocol/01-http2.md#33-method-scheme-and-path)) |
| `:scheme` | Request headers | gRPC | `http` or `https`, according to whether the connection is secured. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`:method`, `:scheme`, and `:path`](../03-wire-protocol/01-http2.md#33-method-scheme-and-path)) |
| `:path` | Request headers | gRPC | `/` + full method name (`/<service>/<method>`). Case-sensitive. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`:method`, `:scheme`, and `:path`](../03-wire-protocol/01-http2.md#33-method-scheme-and-path)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Services and Full Method Names](../02-rpc-semantics/README.md#22-services-and-full-method-names)); [Protocol Buffers Mapping](../03-wire-protocol/05-protobuf.md) |
| `:authority` | Request headers | gRPC | The call's authority (`host` or `host:port`): the channel default or a per-call override. Servers treat `host` as an alias (see `host` below). | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`:authority` and `Host`](../03-wire-protocol/01-http2.md#34-authority-and-host)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Authority](../02-rpc-semantics/README.md#9-authority)); [Channel](../04-client-channel/01-channel.md) ([Channel: Authority](../04-client-channel/01-channel.md#3-authority)) |
| `:status` | Response headers (`Response-Headers` and `Trailers-Only`) | gRPC | Always `200` for a gRPC response. Other values are mapped to a gRPC status. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([Grammar](../03-wire-protocol/01-http2.md#61-grammar), [gRPC over HTTP/2: Handling Non-gRPC and Broken Responses](../03-wire-protocol/01-http2.md#7-handling-non-grpc-and-broken-responses)) |
| `te` | Request headers | gRPC | Always `trailers`. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`te`](../03-wire-protocol/01-http2.md#36-te)) |
| `content-type` | Request headers; Response headers (and `Trailers-Only`) | gRPC | `application/grpc` with an optional content-subtype: `+proto` or `+<custom>`. Bare `application/grpc` means Protocol Buffers. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`content-type`](../03-wire-protocol/01-http2.md#38-content-type), [Content-type in responses](../03-wire-protocol/01-http2.md#67-content-type-in-responses)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Codecs and Content-Subtype](../02-rpc-semantics/README.md#17-codecs-and-content-subtype)); [Protocol Buffers Mapping](../03-wire-protocol/05-protobuf.md) |
| `user-agent` | Request headers | gRPC (the application may prepend its own) | Recommended form `grpc-<language>[-<variant>]/<version> [(<properties>)]`. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`user-agent`](../03-wire-protocol/01-http2.md#310-user-agent)) |
| `host` | HTTP/2 request headers | Peer | Alias of `:authority`. Servers reject duplicates, rename `host` to `:authority` when `:authority` is absent, and discard `host` when both are present. xDS header matching treats the two names as aliases. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`:authority` and `Host`](../03-wire-protocol/01-http2.md#34-authority-and-host)); [Common Types](../09-xds/03-resources/01-common-types.md) ([`HeaderMatcher`](../09-xds/03-resources/01-common-types.md#8-headermatcher)) |
| `Host` | HTTP/1.1 CONNECT request to a proxy | gRPC | `<host>:<port>` of the CONNECT target. | [HTTP CONNECT Proxy Support](../04-client-channel/07-proxy.md) ([HTTP CONNECT Proxy Support: CONNECT Handshake](../04-client-channel/07-proxy.md#4-connect-handshake)) |
| `Proxy-Authorization` | HTTP/1.1 CONNECT request to a proxy | gRPC | `Basic <base64(username:password)>`. Sent only when proxy credentials are configured. | [HTTP CONNECT Proxy Support](../04-client-channel/07-proxy.md) ([HTTP CONNECT Proxy Support: CONNECT Handshake](../04-client-channel/07-proxy.md#4-connect-handshake)) |
| `connection` (and other hop-by-hop headers) | HTTP/2 request headers | Peer | A request that contains `connection` is malformed (stream error `PROTOCOL_ERROR`). Hop-by-hop headers cannot be used in authorization header matching. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([Hop-by-hop headers](../03-wire-protocol/01-http2.md#35-hop-by-hop-headers)); [Authorization](../06-security/03-authorization.md) |
| `alt-svc` | HTTP/2 response headers | gRPC | A server can advertise HTTP/3 (`h3`). A client configured to upgrade then switches to HTTP/3. | [gRPC over HTTP/3](../03-wire-protocol/04-http3.md) ([gRPC over HTTP/3: Negotiating HTTP/3](../03-wire-protocol/04-http3.md#4-negotiating-http3)) |
| `content-encoding`, other transport headers | — | — | Not used by gRPC. HTTP-level compression is not part of the protocol. Like pseudo-headers, these are never recorded by binary logging. | [Binary Logging](../08-observability/06-binary-logging.md) ([Metadata](../08-observability/06-binary-logging.md#33-metadata)) |

The xDS header-matching rules also treat pseudo-headers specially (for
example, `:path` and `:method` are matchable). See
[Common Types](../09-xds/03-resources/01-common-types.md) ([`HeaderMatcher`](../09-xds/03-resources/01-common-types.md#8-headermatcher)).

## A.3 gRPC Protocol Headers

| Name | Direction | Set by | Format | Defined in |
| --- | --- | --- | --- | --- |
| `grpc-timeout` | Request headers | gRPC | `1*8DIGIT` followed by a unit: `H`, `M`, `S`, `m`, `u`, or `n`. The time left until the call's deadline. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`grpc-timeout`](../03-wire-protocol/01-http2.md#37-grpc-timeout)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Deadlines](../02-rpc-semantics/README.md#8-deadlines)) |
| `grpc-encoding` | Request headers; Response headers | gRPC | One content coding: `identity`, `gzip`, `deflate`, `snappy`, or a custom name. Applies to messages whose Compressed-Flag is 1. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`grpc-encoding` and `grpc-accept-encoding`](../03-wire-protocol/01-http2.md#39-grpc-encoding-and-grpc-accept-encoding), [gRPC over HTTP/2: Length-Prefixed Messages](../03-wire-protocol/01-http2.md#5-length-prefixed-messages)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Compression](../02-rpc-semantics/README.md#13-compression)) |
| `grpc-accept-encoding` | Request headers; Response headers (MAY also appear in an `UNIMPLEMENTED` response to an unsupported compression algorithm) | gRPC | Comma-separated list of content codings the sender can decode. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`grpc-encoding` and `grpc-accept-encoding`](../03-wire-protocol/01-http2.md#39-grpc-encoding-and-grpc-accept-encoding)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Negotiation](../02-rpc-semantics/README.md#132-negotiation)); [Server](../05-server/README.md) ([Server: Compression](../05-server/README.md#34-compression)) |
| `grpc-message-type` | Request headers | gRPC | Schema type name of the stream's messages (for Protocol Buffers, the fully qualified message name). Informational only. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`grpc-message-type`](../03-wire-protocol/01-http2.md#311-grpc-message-type)) |
| `grpc-status` | Trailers | gRPC | Status code as a decimal integer with no leading zeros. Always present, including for `OK`. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`grpc-status`](../03-wire-protocol/01-http2.md#63-grpc-status)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Status](../02-rpc-semantics/README.md#10-status)) |
| `grpc-message` | Trailers | gRPC | Status message: UTF-8, then percent-encoded (bytes outside `%x20-7E`, and `%` itself, are encoded). | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`grpc-message`](../03-wire-protocol/01-http2.md#64-grpc-message)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Status Message](../02-rpc-semantics/README.md#104-status-message)) |
| `grpc-status-details-bin` | Trailers | gRPC (value from the application) | Binary. A serialized `google.rpc.Status` whose `code` and `message` MUST match `grpc-status` and `grpc-message`; the gRPC library MAY check this but is not required to. Applications MUST be able to read the raw value. MUST NOT be sent with `OK`. | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([`grpc-status-details-bin`](../03-wire-protocol/01-http2.md#65-grpc-status-details-bin)); [Protocol Buffers Mapping](../03-wire-protocol/05-protobuf.md) ([Protocol Buffers Mapping: Rich Error Details](../03-wire-protocol/05-protobuf.md#4-rich-error-details)); [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Rich Error Details](../02-rpc-semantics/README.md#105-rich-error-details)) |
| `grpc-previous-rpc-attempts` | Request headers | gRPC | Decimal integer: the number of earlier attempts of the same call. Sent on retry and hedging attempts. Absent on the first attempt. | [Retries and Hedging](../04-client-channel/10-retries.md) ([Retries and Hedging: `grpc-previous-rpc-attempts`](../04-client-channel/10-retries.md#9-grpc-previous-rpc-attempts)); [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([Retry-related request headers](../03-wire-protocol/01-http2.md#312-retry-related-request-headers)) |
| `grpc-retry-pushback-ms` | Trailers | gRPC (value from the server application or library) | Signed 32-bit decimal integer, in milliseconds. A negative or unparseable value means "do not retry". | [Retries and Hedging](../04-client-channel/10-retries.md) ([Retries and Hedging: Server Pushback](../04-client-channel/10-retries.md#5-server-pushback)); [gRPC over HTTP/2](../03-wire-protocol/01-http2.md) ([Retry pushback](../03-wire-protocol/01-http2.md#66-retry-pushback)) |

## A.4 Keys Defined by gRPC Features

| Name | Direction | Set by | Format | Defined in |
| --- | --- | --- | --- | --- |
| `authorization` | Request headers | gRPC (plugin): call credentials, including the xDS GCP authentication and JWT call credentials | `Bearer <token>` for the built-in token credentials. Other call credentials may set other keys. Not recorded by server-side binary logging. | [Call Credentials](../06-security/02-call-credentials.md); [xDS HTTP Filters](../09-xds/06-http-filters.md) ([xDS HTTP Filters: GCP Authentication](../09-xds/06-http-filters.md#11-gcp-authentication)); [Binary Logging](../08-observability/06-binary-logging.md) ([Metadata](../08-observability/06-binary-logging.md#33-metadata)) |
| `grpc-trace-bin` | Request headers | gRPC (plugin): the `grpc-trace-bin` tracing propagator | Binary, 29 bytes: version 0, then trace ID (field 0, 16 bytes), span ID (field 1, 8 bytes), and trace options (field 2, 1 byte). At most one per RPC. Always recorded by binary logging. | [Tracing](../08-observability/04-tracing.md) ([Tracing: Context Propagation](../08-observability/04-tracing.md#6-context-propagation), [Tracing: The `grpc-trace-bin` Propagator and Format](../08-observability/04-tracing.md#7-the-grpc-trace-bin-propagator-and-format)); [Binary Logging](../08-observability/06-binary-logging.md) ([Metadata](../08-observability/06-binary-logging.md#33-metadata)) |
| `endpoint-load-metrics-bin` | Trailers only (never Response headers) | gRPC (plugin): the server's per-call ORCA recorder | Binary. A serialized `xds.data.orca.v3.OrcaLoadReport`. Omitted when nothing was recorded. | [Backend Metrics (ORCA)](../07-services/03-orca.md) ([Wire Format](../07-services/03-orca.md#21-wire-format)); [Load Balancing](../04-client-channel/05-load-balancing.md) (4.5.13.1) |
| `cookie` | Request headers | Application | HTTP cookie list. The xDS stateful session affinity behavior reads the cookie named by its configuration. The value is base64 of `<address>[,<address>...];<cluster>`. | [xDS HTTP Filters](../09-xds/06-http-filters.md) ([Cookie Value Format](../09-xds/06-http-filters.md#102-cookie-value-format), [Request Processing](../09-xds/06-http-filters.md#103-request-processing)) |
| `set-cookie` | Response headers (Trailers, for a `Trailers-Only` response) | gRPC (plugin): xDS stateful session affinity | `<name>=<base64 value>; HttpOnly[; Path=<path>][; Max-Age=<seconds>]`. Delivered to the client application, not sent by the server. | [xDS HTTP Filters](../09-xds/06-http-filters.md) ([Response Processing](../09-xds/06-http-filters.md#104-response-processing)) |
| `x-envoy-fault-delay-request` | Request headers | Application (or an upstream proxy) | Delay in milliseconds. Honored only when the xDS fault injection config enables `header_delay`. | [xDS HTTP Filters](../09-xds/06-http-filters.md) ([Header-Controlled Faults](../09-xds/06-http-filters.md#83-header-controlled-faults)) |
| `x-envoy-fault-delay-request-percentage` | Request headers | Application | Numerator of the delay probability, capped by the configured numerator. | [xDS HTTP Filters](../09-xds/06-http-filters.md) ([Header-Controlled Faults](../09-xds/06-http-filters.md#83-header-controlled-faults)) |
| `x-envoy-fault-abort-grpc-request` | Request headers | Application | gRPC status code to abort with. Honored only when `header_abort` is enabled. Takes precedence over `x-envoy-fault-abort-request`. | [xDS HTTP Filters](../09-xds/06-http-filters.md) ([Header-Controlled Faults](../09-xds/06-http-filters.md#83-header-controlled-faults)) |
| `x-envoy-fault-abort-request` | Request headers | Application | HTTP status code, mapped to a gRPC status. Honored only when `header_abort` is enabled. | [xDS HTTP Filters](../09-xds/06-http-filters.md) ([Header-Controlled Faults](../09-xds/06-http-filters.md#83-header-controlled-faults)) |
| `x-envoy-fault-abort-request-percentage` | Request headers | Application | Numerator of the abort probability, capped by the configured numerator. | [xDS HTTP Filters](../09-xds/06-http-filters.md) ([Header-Controlled Faults](../09-xds/06-http-filters.md#83-header-controlled-faults)) |
| `x-envoy-fault-throughput-response`, `x-envoy-fault-throughput-response-percentage` | Request headers | — | Not supported. Ignored. | [xDS HTTP Filters](../09-xds/06-http-filters.md) ([Header-Controlled Faults](../09-xds/06-http-filters.md#83-header-controlled-faults)) |

Configuration can also name arbitrary application headers for gRPC to read.
These names are not reserved:

- xDS route matching on headers, and RBAC header matching. See
  [RouteConfiguration](../09-xds/03-resources/03-route-configuration.md) and
  [Authorization](../06-security/03-authorization.md).
- The header named by an xDS `hash_policy`, or by the `ring_hash`
  `request_hash_header` setting. See
  [RouteConfiguration](../09-xds/03-resources/03-route-configuration.md) ([Hash Policy](../09-xds/03-resources/03-route-configuration.md#7-hash-policy)) and
  [`ring_hash`](../04-client-channel/lb-policies/ring_hash.md).
