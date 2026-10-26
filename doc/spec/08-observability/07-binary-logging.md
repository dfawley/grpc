> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 8.7 Binary Logging

<!-- Sources: A16, doc/binary-logging.md, grpc-proto grpc/binlog/v1/binarylog.proto -->

> **Introduced by:** [gRFC A16: gRPC Binary Logging](https://github.com/grpc/proposal/blob/master/A16-binary-logging.md)

Binary logging records RPCs in a structured binary format, for
troubleshooting, load testing, and replaying production traffic. Each RPC
event (headers, messages, half-close, trailers, cancellation) becomes one
`GrpcLogEntry` message, as defined in `grpc/binlog/v1/binarylog.proto`.
Initial metadata, messages, and trailing metadata are logged as separate
entries, matching their representation on the wire.

## 1. Enabling Binary Logging

- Binary logging is **off by default**.
- It is enabled with a **configuration string** ([Configuration String](#5-configuration-string)) that selects
  which methods to log and how much of each header and message to keep. The
  string is supplied in either of these ways:
  - the `GRPC_BINARY_LOG_FILTER` environment variable, or
  - an equivalent API option or flag that accepts the same string.
- Enabling binary logging through the environment variable MUST NOT require
  code changes.
- An empty string means nothing is logged.
- If the configuration string is **malformed**, gRPC MUST NOT log with a
  partial configuration. When the string comes from the environment variable,
  gRPC SHOULD fail at initialization; if it does not fail, it MUST log
  nothing and SHOULD report the error in its own logs. When the string is
  passed to an API, the API MUST report an error.

Binary logging applies to both clients and servers. Entries record which side
produced them in the `logger` field.

## 2. What Is Logged

The logged events are the events that are, or may be, visible to the
application:

| `type` | Client side (`LOGGER_CLIENT`) | Server side (`LOGGER_SERVER`) |
| --- | --- | --- |
| `EVENT_TYPE_CLIENT_HEADER` | The application sends initial metadata | Initial metadata received from the client |
| `EVENT_TYPE_SERVER_HEADER` | Initial metadata received from the server | The application sends initial metadata |
| `EVENT_TYPE_CLIENT_MESSAGE` | The application sends a request message | A request message is received |
| `EVENT_TYPE_SERVER_MESSAGE` | A response message is received | The application sends a response message |
| `EVENT_TYPE_CLIENT_HALF_CLOSE` | The application half-closes | The client's half-close is received |
| `EVENT_TYPE_SERVER_TRAILER` | Trailers and status received from the network, **or** a status generated locally by gRPC to report a failure to the application | The server application requests to send trailers and status. A later `EVENT_TYPE_CANCEL` may still follow because of races. |
| `EVENT_TYPE_CANCEL` | The client application cancels the RPC | Cancellation of the RPC detected |

`EVENT_TYPE_SERVER_TRAILER` and `EVENT_TYPE_CANCEL` each mark the end of the
RPC. Because of races, further entries may follow them. For example, on the
client, trailers may arrive after the application cancelled.

A trailers-only response produces `EVENT_TYPE_SERVER_TRAILER` with no
preceding `EVENT_TYPE_SERVER_HEADER`.

**Retries and hedging.** Events of attempts that are never committed are
**not** logged (see [Retries and hedging](../04-client-channel/12-retries.md)).
Client-originated events (header, messages, half-close, cancel) are logged
once, when the application performs them, not once per attempt. Events
originating from the server are logged only for the committed attempt. The
`EVENT_TYPE_SERVER_TRAILER` entry for a locally generated status is logged
once, with the status delivered to the application.

## 3. Log Entry Format

### 3.1 `GrpcLogEntry`

| Field | Semantics |
| --- | --- |
| `timestamp` | When the event was logged. |
| `call_id` | Identifies the call. All entries of one call share it. MUST be non-zero, and MUST be unique across calls within one log instance ([Sinks and Call IDs](#6-sinks-and-call-ids)). Nothing else is guaranteed about its value. |
| `sequence_id_within_call` | Position of the entry within its call: 1 for the first entry, increasing by 1 for each entry after that. Lets readers detect missing or reordered entries when the sink does not guarantee durability or ordering. |
| `type` | `EventType` ([What Is Logged](#2-what-is-logged)). |
| `logger` | `LOGGER_CLIENT` or `LOGGER_SERVER`. |
| `payload` (oneof) | `client_header` for `EVENT_TYPE_CLIENT_HEADER`. `server_header` for `EVENT_TYPE_SERVER_HEADER`. `message` for the two message types. `trailer` for `EVENT_TYPE_SERVER_TRAILER`. Unset for half-close and cancel. |
| `payload_truncated` | True if the payload does not contain the full metadata or message because of the configured limits ([Truncation](#4-truncation)). |
| `peer` | Peer address ([Address](#34-address)). Set only on the first entry for an *incoming* event: |
| | – client: on `EVENT_TYPE_SERVER_HEADER`, or on `EVENT_TYPE_SERVER_TRAILER` for a trailers-only response; |
| | – server: always on `EVENT_TYPE_CLIENT_HEADER`. |

### 3.2 Payload Messages

| Message | Field | Semantics |
| --- | --- | --- |
| `ClientHeader` | `metadata` | Application metadata only ([Metadata](#33-metadata)). |
| | `method_name` | Full method name with a leading slash: `/<service>/<method>`. |
| | `authority` | The `:authority` of the call (`<host>` or `<host>:<port>`). |
| | `timeout` | The RPC's timeout (remaining deadline) when the header is sent or received. Absent if the RPC has no deadline. |
| `ServerHeader` | `metadata` | Application metadata only. |
| `Trailer` | `metadata` | Application trailing metadata only. |
| | `status_code` | The gRPC status code (numeric). |
| | `status_message` | The status message, as text, *before* any transport-specific encoding such as percent-encoding. |
| | `status_details` | The raw value of `grpc-status-details-bin`, if present: always a serialized `google.rpc.Status`. |
| `Message` | `length` | Length in bytes of the complete serialized message. |
| | `data` | The message bytes, possibly truncated to the configured limit or omitted entirely. |

### 3.3 Metadata

`Metadata` is a list of `MetadataEntry{key, value}` in order. It contains only
application-visible metadata. The following entries MUST NOT be logged, and
omitting them is **not** a truncation:

- entries that gRPC handles internally and that the application does not see:
  keys beginning with `grpc-` (except `grpc-trace-bin`);
- transport-specific entries, including `:path`, `:authority`,
  `content-encoding`, `user-agent`, `te`, and other HTTP/2 pseudo-headers and
  transport headers;
- entries added by call credentials. On the client side, all entries added by
  call credentials are excluded. On the server side, only the `authorization`
  header is excluded.

**`grpc-trace-bin` exception.** If `grpc-trace-bin` is present, it MUST
always be logged. It does not count toward the header size limit. In practice
it is visible only on the server, where it is ordinary metadata, because on
the client it is added by low-level mechanisms below the application.

### 3.4 Address

| Field | Semantics |
| --- | --- |
| `type` | `TYPE_IPV4`, `TYPE_IPV6`, `TYPE_UNIX`, or `TYPE_UNKNOWN`. |
| `address` | IPv4: dotted-quad (`1.2.3.4`). IPv6: canonical text form (RFC 5952 §4), **without** any scope ID. Unix: the socket path. |
| `ip_port` | The port. Set only for `TYPE_IPV4` and `TYPE_IPV6`. |

## 4. Truncation

The configuration string ([Configuration String](#5-configuration-string)) may set a header limit `h:<N>` and a message limit
`m:<N>` for each method:

- **No pattern configuration** (`{…}` omitted): headers and messages are
  logged in full.
- **Message limit.** `Message.data` contains at most the first `N` bytes of
  the message, while `length` still gives the full length. If bytes were
  dropped, `payload_truncated` is true. `m` without a number means no limit.
- **Header limit.** Metadata entries are omitted as needed so that the total
  size (key length plus value length) of the logged entries stays within `N`
  bytes. Which entries are omitted is implementation-defined: for example, an
  implementation may omit the first entry that would exceed the limit and
  every entry after it, or omit only the entries that do not fit. Logged
  entries keep their relative order. If any entry was omitted,
  `payload_truncated` is true. Excluded entries ([Metadata](#33-metadata))
  and `grpc-trace-bin` do not count toward the limit, and `grpc-trace-bin` is
  logged even when entries before or after it are omitted. `h` without a
  number means no limit. gRPC MAY exceed the header limit in order to log
  certain required headers.
- **Only one of `h` or `m` configured.** If only `h` is given, messages are
  not logged. If only `m` is given, headers are not logged. In both cases the
  entries for the unlogged kind are still emitted, with their payloads
  truncated to empty (`length` still set for messages). `payload_truncated`
  is true if any metadata entry or message byte was omitted. Status code,
  status message, method name, authority, timeout, and peer are always logged.

## 5. Configuration String

### 5.1 Grammar

A configuration string is a comma-separated list of patterns. Each pattern
matches full method names of the form `<service>/<method>`, without the
leading slash.

```abnf
config-string      = [ pattern *( "," pattern ) ]
pattern            = global-default / per-service / per-method / excluded-method

global-default     = "*" [ pattern-config ]
per-service        = service-name "/*" [ pattern-config ]
per-method         = service-name "/" method-name [ pattern-config ]
excluded-method    = "-" service-name "/" method-name

pattern-config     = "{" ( message-config / ( header-config [ ";" message-config ] ) ) "}"
header-config      = "h" [ ":" 1*DIGIT ]    ; header size limit in bytes; no number = unlimited
message-config     = "m" [ ":" 1*DIGIT ]    ; message size limit in bytes; no number = unlimited

service-name       = <IDL-specific fully-qualified service name>
method-name        = <method name>
```

### 5.2 Validation

The configuration is **malformed**, and is handled as specified in
[Enabling Binary Logging](#1-enabling-binary-logging), if any of the following holds:

- a pattern does not match the grammar;
- the wildcard is used in an unsupported position: `*/<method>` (method with a
  wildcard service), or `-<service>/*` (negated wildcard);
- more than one global `*` pattern is given;
- there are duplicate rules for the same target:
  - two `per-service` patterns for the same service;
  - two `per-method` patterns for the same method, even if identical (e.g.
    `S/M{h:1;m:2},S/M{h:1;m:2}`);
  - a `per-method` pattern and an `excluded-method` pattern for the same method
    (e.g. `S/M{h:12;m:23},-S/M`);
  - two `excluded-method` patterns for the same method.


### 5.3 Precedence

For an RPC whose full method name is `S/M`:

1. If an `excluded-method` pattern `-S/M` exists, the RPC is **not** logged.
2. Otherwise, if a `per-method` pattern `S/M` exists, its configuration is
   used.
3. Otherwise, if a `per-service` pattern `S/*` exists, its configuration is
   used.
4. Otherwise, if the global pattern `*` exists, its configuration is used.
5. Otherwise, the RPC is not logged.

The order of patterns in the string does not matter.

### 5.4 Examples

| `GRPC_BINARY_LOG_FILTER` | Effect |
| --- | --- |
| *(empty)* | Nothing is logged. |
| `*` | All headers and messages of all methods are logged in full. |
| `*{h}` | Headers are logged in full. Message contents are not logged. |
| `*{m:256}` | The first 256 bytes of each message are logged. Header contents are not logged. |
| `*{h:1024;m:256}` | Up to 1024 bytes of metadata per entry and the first 256 bytes of each message. |
| `Foo/*` | Every method of service `Foo` is logged in full. |
| `Foo/*,-Foo/Bar` | Every method of `Foo` except `Foo/Bar` is logged. |
| `Foo/*,Foo/Bar{m:256}` | `Foo/Bar`: the first 256 bytes of each message, without header contents. Every other method of `Foo`: logged in full. |
| `Foo/*{h},Foo/Bar{m:256}` | `Foo/Bar` uses `{m:256}` (exact method match). `Foo/Baz` uses `{h}` (service default). |
| `*,-Foo/Bar` | Everything except `Foo/Bar` is logged. |

## 6. Sinks and Call IDs

- **Sink.** Log entries are delivered to a pluggable **sink**. Examples are a
  local file and a remote logging service. The sink decides the storage and
  framing of the serialized `GrpcLogEntry` messages. A sink that writes a
  byte stream SHOULD frame each entry so that entries can be split apart again
  (for example, with a length prefix). Because sinks may not guarantee
  ordering or durability, readers use `call_id` and `sequence_id_within_call`
  to group and order entries.
- **Call ID generation** is separate from log generation and is provided
  through an interface. Call IDs MUST be non-zero and unique across the calls
  of a log instance. An atomically incremented counter starting at 1 is
  sufficient.
- Binary logging SHOULD be separable from the rest of gRPC, for example as a
  separate library or module that can be left out of a build. Other gRPC
  components MUST NOT depend on it.
- Failures in the sink MUST NOT affect the RPCs being logged.

## 7. API Requirements

- gRPC MUST provide a way to enable binary logging with a configuration
  string, through the `GRPC_BINARY_LOG_FILTER` environment variable and through
  an equivalent API option or flag. An invalid string MUST be rejected ([Enabling Binary Logging](#1-enabling-binary-logging)).
- The binary logging API MUST provide a way for the application to supply the
  sink that receives `GrpcLogEntry` messages.
- The binary logging API MUST provide a way for the application to supply the
  call ID generator.
- Binary logging MUST be configurable for both clients and servers, and
  globally. Implementations MAY also allow per-channel or per-server
  configuration.
