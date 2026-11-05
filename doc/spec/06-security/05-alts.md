> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 6.5 ALTS

<!-- Sources: L62, grpc-proto grpc/gcp/handshaker.proto, grpc-proto grpc/gcp/transport_security_common.proto, grpc-proto grpc/gcp/altscontext.proto, Google Cloud "Application Layer Transport Security" whitepaper -->

Application Layer Transport Security (ALTS) is a mutual authentication and
transport encryption system in which each workload is identified by a
service account rather than by an X.509 certificate chain. Peers do not
implement the ALTS handshake themselves: each side relays handshake bytes
to a local **handshaker service**, which holds the workload's credentials,
runs the handshake, and returns the peer's identity and the session keys.
gRPC then protects the connection with the ALTS record protocol.

The design of ALTS, including its handshake protocol, is described in the
[Application Layer Transport Security](https://cloud.google.com/docs/security/encryption-in-transit/application-layer-transport-security)
whitepaper. This section specifies what gRPC does: how it uses the
handshaker service, which parameters it negotiates, how it frames protected
data, and what it exposes to applications.

Implementations MAY provide ALTS channel and server credentials. An
implementation that provides them MUST implement them as specified here.

## 1. Credentials

- **ALTS channel credentials** secure every connection a channel makes with
  an ALTS client handshake. They take a list, possibly empty, of **target
  service accounts** ([Target Service Accounts and Peer Identity](#5-target-service-accounts-and-peer-identity)).
- **ALTS server credentials** secure every connection accepted on a
  listening port with an ALTS server handshake. They take no identity
  configuration: the server's identity is the one the handshaker service
  holds.
- An ALTS connection has security level `PRIVACY_AND_INTEGRITY` (see
  [Security Model: Security Levels](01-security-model.md#5-security-levels)).
- ALTS credentials do no hostname verification and no per-RPC authority
  check: any RPC authority may use an ALTS connection (see
  [Security Model: Per-RPC Authority Verification](01-security-model.md#71-per-rpc-authority-verification)).
  Authorization of the peer is based on its service account.
- Both kinds of credentials MAY be composed and used like any other channel
  or server credentials (see [Security Model](01-security-model.md)).

ALTS is available only where a trusted handshaker service runs (on Google
Cloud Platform). ALTS credentials MUST NOT perform handshakes when the
process is not running on Google Cloud Platform. Whether this makes creating
the credentials fail or makes every handshake fail is implementation-defined.
Whether the process runs on Google Cloud Platform is determined from the
platform, without network access, as for the `google-c2p` resolver (see
[Google Cloud-to-Prod (`google-c2p`) Resolver: Choosing the Path](../10-vendor-specific/02-google-c2p-resolver.md#2-choosing-the-path)).
Implementations MAY provide a testing-only way to turn this check off.

## 2. Handshaker Service

The handshaker service is a gRPC service defined in
[`grpc/gcp/handshaker.proto`](https://github.com/grpc/grpc-proto/blob/master/grpc/gcp/handshaker.proto):

```proto
service HandshakerService {
  rpc DoHandshake(stream HandshakerReq) returns (stream HandshakerResp) {}
}
```

- **Address.** By default the handshaker service is reached at the target
  `dns:///metadata.google.internal.:8080`. Implementations MAY provide a way
  to set a different address; whether and how the address can be overridden
  (for example through the API, or by taking the host from the
  `GCE_METADATA_HOST` environment variable) is implementation-defined.
- **Channel.** gRPC reaches the handshaker service over a channel with
  insecure credentials. The channel MAY be shared by all ALTS handshakes in
  the process. Retries and service config resolution SHOULD be turned off on
  it.
- **One stream per handshake.** Each ALTS handshake (one per connection) uses
  one `DoHandshake` stream. The stream is half-closed when the handshake
  completes or fails.
- **Concurrency.** An implementation SHOULD limit the number of handshakes
  that have a `DoHandshake` stream open at the same time. Handshakes over
  the limit wait for one to finish. The limit is set by the environment
  variable `GRPC_ALTS_MAX_CONCURRENT_HANDSHAKES` (a positive integer). The
  default, any upper bound on the configured value, and whether client and
  server handshakes share one limit are implementation-defined. The default
  SHOULD be 100, and client and server handshakes SHOULD be limited
  separately.
- **Deadline.** The handshake, including the `DoHandshake` stream, is bounded
  by the connection attempt's deadline (see
  [Subchannels and Connections](../04-client-channel/07-subchannels.md)). An
  implementation MAY also set its own deadline on the stream.

## 3. Handshake

### 3.1 Message Flow

Each side drives its handshake by exchanging `HandshakerReq` and
`HandshakerResp` messages on its `DoHandshake` stream. The handshaker
service returns bytes to send to the peer (`out_frames`), reports how many
of the bytes it was given it consumed (`bytes_consumed`), and finally
returns a `HandshakerResult`. gRPC relays bytes between the peer connection
and the stream without interpreting them.

1. The **client** sends `client_start` (a `StartClientHandshakeReq`) as soon
   as the TCP connection is established, writes the response's `out_frames`
   to the peer, and then, each time it reads bytes from the peer, sends them
   in `next.in_bytes` (a `NextHandshakeMessageReq`) and writes the response's
   `out_frames` to the peer.
2. The **server** waits until it has read the first bytes from the client,
   sends them in `server_start.in_bytes` (a `StartServerHandshakeReq`), and
   then continues like the client.
3. A response with `result` set ends the handshake. Any `out_frames` in it
   are still written to the peer. Bytes read from the peer that the
   handshaker service did not consume (beyond `bytes_consumed`) are the
   start of the protected data stream and are passed to the record protocol.
4. A response whose `status.code` is not 0 (OK) fails the handshake with
   `status.details`. If the stream itself fails, or if the peer closes the
   connection before the handshake completes, the handshake fails.

A failed handshake fails the connection attempt (see
[Security Model: Channel and Server Credentials](01-security-model.md#2-channel-and-server-credentials)).

### 3.2 Start Requests

`StartClientHandshakeReq`:

| Field | Value |
| --- | --- |
| `handshake_security_protocol` | `ALTS` |
| `application_protocols` | `["grpc"]` |
| `record_protocols` | `["ALTSRP_GCM_AES128_REKEY"]` |
| `target_identities` | One `Identity` with `service_account` set for each target service account, in order. Empty if none were configured. |
| `target_name` | The authority of the channel's target (the channel's default authority). |
| `rpc_versions` | The local RPC protocol versions ([RPC Protocol Versions](#4-rpc-protocol-versions)). |
| `max_frame_size` | The largest frame the client will accept. SHOULD be set ([Frame Size](#62-frame-size)). |

`StartServerHandshakeReq`:

| Field | Value |
| --- | --- |
| `application_protocols` | `["grpc"]` |
| `handshake_parameters` | One entry keyed by `ALTS` (2) whose `record_protocols` is `["ALTSRP_GCM_AES128_REKEY"]`. |
| `in_bytes` | The bytes read from the client so far. |
| `rpc_versions` | The local RPC protocol versions. |
| `max_frame_size` | The largest frame the server will accept. SHOULD be set ([Frame Size](#62-frame-size)). |

Other fields of both messages (`local_identity`, endpoints, `access_token`,
`transport_protocol_preferences`, and so on) are not set by gRPC ALTS
credentials.

### 3.3 Handshake Result

The `HandshakerResult` is used as follows:

| Field | Use |
| --- | --- |
| `application_protocol` | Recorded in the AltsContext. |
| `record_protocol` | MUST be `ALTSRP_GCM_AES128_REKEY` (the only protocol offered); otherwise the handshake fails. |
| `key_data` | MUST be at least 44 bytes; otherwise the handshake fails. The first 44 bytes are the record protocol key material ([Record Protocol](#6-record-protocol)). |
| `peer_identity.service_account` | The peer's service account ([Target Service Accounts and Peer Identity](#5-target-service-accounts-and-peer-identity)). |
| `local_identity.service_account` | The local service account, recorded in the AltsContext. |
| `peer_rpc_versions` | Checked against the local versions ([RPC Protocol Versions](#4-rpc-protocol-versions)). |
| `max_frame_size` | The largest frame the peer accepts ([Frame Size](#62-frame-size)). |
| `keep_channel_open` | Ignored. |

<!-- REVIEW(divergence) [ALTS-3]: Validation of the ALTS handshaker response. C++ (src/core/tsi/alts/handshaker/alts_handshaker_client.cc L257-L264; alts_tsi_handshaker.cc L298-L427) fails a HandshakerResp with no status (TSI_DATA_CORRUPTED) and a result with no peer identity, empty peer service account, empty application or record protocol, no local identity, no peer_rpc_versions, or key_data < 44 bytes; but it does not check the record_protocol value: any non-empty name is accepted, and "ALTSRP_GMAC_128" switches to integrity-only protection (alts_tsi_handshaker.cc L161, L224). Go (credentials/alts/internal/handshaker/handshaker.go L268-L300) treats a missing status as OK, fails a record_protocol other than ALTSRP_GCM_AES128_REKEY, and slices key_data to 44 bytes without a length check (a shorter key panics). Java (AltsHandshakerClient.java L137-L164; AltsTsiHandshaker.java L190-L205) treats a missing status as OK and checks only key_data >= 44 (it never checks record_protocol). Spec says: record_protocol MUST be ALTSRP_GCM_AES128_REKEY and key_data at least 44 bytes; nothing about a missing status or empty identities. -->

## 4. RPC Protocol Versions

Each side advertises the range of RPC protocol versions it supports, as an
`RpcProtocolVersions` message
([`grpc/gcp/transport_security_common.proto`](https://github.com/grpc/grpc-proto/blob/master/grpc/gcp/transport_security_common.proto))
with `max_rpc_version` and `min_rpc_version`. gRPC's local range is
maximum 2.1 and minimum 2.1.

After the handshake, each side checks its local range against the peer's
range (`peer_rpc_versions`). Versions are compared by major, then minor:

```
max_common = min(local.max_rpc_version, peer.max_rpc_version)
min_common = max(local.min_rpc_version, peer.min_rpc_version)
compatible = max_common >= min_common
```

If the ranges are not compatible (including when `peer_rpc_versions` is
absent, which is treated as the range 0.0 to 0.0), the handshake fails.
The highest common version is `max_common`; it does not change gRPC's
behavior.

## 5. Target Service Accounts and Peer Identity

- **Client.** The client sends its target service accounts in
  `target_identities`. The handshaker service fails the handshake if the
  list is non-empty and the server's service account is not in it. gRPC does
  not repeat the check. With an empty list, any server service account is
  accepted.
- **Server.** ALTS server credentials do not restrict client identities.
  Servers authorize clients per RPC, using the AuthContext
  ([AuthContext](#7-authcontext)), for example with an authorization policy
  (see [Authorization](04-authorization.md)) or a service-account check
  ([API Requirements](#8-api-requirements)).

## 6. Record Protocol

### 6.1 Frames and Encryption

After the handshake, all HTTP/2 bytes in each direction are carried in
frames of the ALTS record protocol `ALTSRP_GCM_AES128_REKEY`:

```
+-------------------+-------------------+-----------------------------+
| length (4 bytes)  | type (4 bytes)    | ciphertext + 16-byte tag    |
+-------------------+-------------------+-----------------------------+
```

- `length` is a little-endian unsigned integer: the number of bytes after
  the `length` field (type, ciphertext, and tag).
- `type` is a little-endian unsigned integer and MUST be `0x00000006`
  (protected data). A frame with any other type is an error.
- The payload is encrypted with AES-128-GCM. The tag is the 16-byte GCM tag.
  There is no additional authenticated data.
- **Keys.** The 44 bytes of key material are a 32-byte key-derivation key
  followed by a 12-byte nonce mask. Each frame uses a 12-byte counter,
  little-endian, starting at 0 and incremented per frame, with the high
  bit of the last byte set on frames sent by the server. The GCM nonce is
  the counter XOR the nonce mask. The AES key is the first 16 bytes of
  HMAC-SHA256(key-derivation key, counter bytes 2 through 7 followed by the
  byte `0x01`), so it changes every 2^16 frames.
- If the counter would overflow its low 8 bytes, the connection fails.
- Any decryption or framing error fails the connection.

### 6.2 Frame Size

Each side SHOULD advertise the largest frame it will accept in
`max_frame_size` of its start request. Whatever it advertises, a receiver
MUST accept frames up to 1 MiB. A sender's frames are at most:

- an implementation-defined size of at most 1 MiB if the peer advertised no
  `max_frame_size` (0); 16 KiB is RECOMMENDED;
- otherwise, the smaller of the peer's value and the local value, but not
  less than 16 KiB.

The local value (the value a side advertises) is implementation-defined and
MUST be at least 16 KiB and at most 1 MiB.

## 7. AuthContext

An ALTS connection's AuthContext (see
[Security Model: AuthContext and Peer Identity](01-security-model.md#6-authcontext-and-peer-identity))
has these properties:

| Property name | Value |
| --- | --- |
| `transport_security_type` | `alts` |
| `security_level` | `PRIVACY_AND_INTEGRITY` |
| `service_account` | The peer's service account (`peer_identity.service_account`). |
| `alts_context` | A serialized `grpc.gcp.AltsContext` message ([`grpc/gcp/altscontext.proto`](https://github.com/grpc/grpc-proto/blob/master/grpc/gcp/altscontext.proto)). |

The peer identity property name is `service_account`.

The `AltsContext` holds `application_protocol`, `record_protocol`,
`peer_service_account`, `local_service_account`, `peer_rpc_versions`, and
`peer_attributes`, copied from the `HandshakerResult` (`peer_attributes`
from `peer_identity.attributes`), and `security_level`
`INTEGRITY_AND_PRIVACY`.

## 8. API Requirements

- The credentials API MAY provide ALTS channel credentials and ALTS server
  credentials. If it provides them:
  - The channel credentials MUST let applications set the list of target
    service accounts.
  - The client and server call APIs MUST give access to the ALTS context of
    the connection an RPC used: at least the peer service account, the local
    service account, the security level, the application and record
    protocols, and the peer's RPC protocol versions.
  - The API SHOULD provide a server-side helper that checks whether the
    client's service account is one of a given list. Service accounts are
    compared exactly (case-sensitively). If the check fails, the helper's
    result is `PERMISSION_DENIED`.

<!-- REVIEW(divergence) [ALTS-6]: Case sensitivity of the ALTS client authorization helper. Go alts.ClientAuthorizationCheck (credentials/alts/utils.go L58-L70) compares with strings.EqualFold (case-insensitive); C++ AltsClientAuthzCheck (src/cpp/common/alts_util.cc L66-L84) and Java AuthorizationUtil.clientAuthorizationCheck (alts/.../AuthorizationUtil.java L35-L47) compare exactly. Also, Java's public AltsContext exposes only security level and peer/local service account (AltsContext.java L26-L91), and Go's AuthInfo interface lacks PeerAttributes. Spec says: exact comparison; the context API exposes peer/local service account, security level, application and record protocols, and peer RPC versions. -->
