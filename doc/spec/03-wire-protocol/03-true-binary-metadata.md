> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 3.3 True Binary Metadata

<!-- Sources: G1, doc/PROTOCOL-HTTP2.md (binary header encoding) -->

> **Introduced by:** [gRFC G1: True Binary Metadata](https://github.com/grpc/proposal/blob/master/G1-true-binary-metadata.md)

Binary metadata (keys ending in `-bin`) is normally base64-encoded on the wire
([Binary values](01-http2.md#43-binary-values)), and HPACK then Huffman-codes the
result. Encoding and decoding this way costs CPU, and for some workloads it is
the bottleneck. This HTTP/2 extension lets peers send binary metadata values
as raw bytes.

## 1. Setting

| Name | Identifier | Values |
| ---- | ---------- | ------ |
| `GRPC_ALLOW_TRUE_BINARY_METADATA` | `0xfe03` | `0` (default): the sender of the setting accepts only base64-encoded binary metadata. `1`: the sender of the setting also accepts true-binary-encoded binary metadata. |

- The identifier is in the HTTP/2 experimental settings range
  ([RFC 9113 §11.3](https://www.rfc-editor.org/rfc/rfc9113#section-11.3)). It
  was chosen at random to avoid collisions with other extensions.
- An endpoint advertises the setting to say what it is willing to *receive*.
- Endpoints SHOULD send the setting only once, in their first SETTINGS frame.
- Values other than 0 and 1 MUST be treated as 0. They MUST NOT be treated
  as a connection error, because another extension may use the same
  identifier.
- Peers that do not know the setting ignore it, as HTTP/2 requires. They
  never receive true-binary values, because those are sent only to a peer that
  advertised `1`.

## 2. Encoding

On a connection where the peer has advertised
`GRPC_ALLOW_TRUE_BINARY_METADATA = 1`, a sender MAY encode the value of any
binary (`-bin`) header like this instead of with base64:

```abnf
True-Binary-Value = %x00 *OCTET   ; a NUL byte, then the raw value bytes
```

The sender MAY choose per header whether to use base64 or true binary.

The receiver tells the two encodings apart by the first byte:

- A value starting with `0x00` is true binary. The receiver removes the first
  byte, and the remaining bytes are the metadata value.
- Any other value is base64 and is decoded as described in
  [Binary values](01-http2.md#43-binary-values). The base64 alphabet has no NUL
  byte, so the two cannot be confused.

The encoding applies only to keys ending in `-bin`. Values of ASCII metadata
are never sent this way.

When true-binary values are sent, `,` joining of duplicate keys
([Duplicate keys and ordering](01-http2.md#44-duplicate-keys-and-ordering)) MUST NOT be used,
because `,` may occur in the raw bytes. Each value MUST be sent as its own
header field.

Header list size limits ([Header list size](01-http2.md#45-header-list-size)) count the
length of the value as sent, including the NUL prefix.

Example: sending the metadata element `foo-bin` with the single byte `0x01`.

| Encoding | Header value on the wire |
| -------- | ------------------------ |
| base64 | `AQ` |
| true binary | `0x00 0x01` |

## 3. Misconfiguration Fallback

Another extension might use the same setting identifier, so a peer could
advertise `0xfe03 = 1` without supporting this extension. To such a peer, a
header value containing a NUL byte is malformed, and HTTP/2 requires it to
reset the stream with `RST_STREAM` and `PROTOCOL_ERROR`
([RFC 9113 §8.2.1](https://www.rfc-editor.org/rfc/rfc9113#section-8.2.1)).

Suppose a client sent true-binary metadata on a stream, and it then receives
`RST_STREAM` with `PROTOCOL_ERROR` on that stream before any response
headers. The client:

1. SHOULD retry the request using base64 encoding. The server application has
   not seen the request, so this retry does not count as a retry attempt for
   retry policy purposes.
2. SHOULD stop using true-binary encoding for later requests on that
   connection.
3. SHOULD log the event verbosely.

## 4. Interaction with Other Transports

`GRPC_ALLOW_TRUE_BINARY_METADATA` is an HTTP/2 setting. On other transports,
such as [HTTP/3](04-http3.md), binary metadata is always base64-encoded.

## 5. API Requirements

Applications always give and receive binary metadata as raw bytes. Whether
true-binary encoding is used is not visible to applications.
