> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 9.3 XdsClient

<!-- Sources: A27, A28, A30, A40, A46, A47, A53, A57, A71, A78, A88, A95, A97, doc/grpc_xds_bootstrap_format.md, doc/grpc_xds_features.md -->

The **XdsClient** is the internal component that talks to xDS servers for
every xDS-enabled part of gRPC. It:

- reads the [bootstrap configuration](02-bootstrap.md),
- manages channels and ADS streams to xDS servers,
- subscribes to resources on behalf of *watchers*,
- validates the resources it receives, ACKs or NACKs responses, and caches the
  results,
- notifies watchers of new resources and of errors,
- falls back to lower-priority xDS servers when higher-priority ones are
  unreachable,
- exposes its state to [CSDS](11-csds.md) and to metrics.

The XdsClient is not part of the public API. Its interface to the rest of
gRPC is specified abstractly in this document.

## 1. XdsClient Instances

- There is one XdsClient instance per **data-plane target**. All client
  channels created with the same target string share one instance. The
  instance's *key* is the target string.
- All xDS-enabled servers in the process share one instance, with the
  reserved key **`#server`**.
- A channel or server that has its own programmatic bootstrap configuration
  (see [Bootstrap](02-bootstrap.md)) gets a dedicated instance that is not
  shared and is not listed in the process-wide instance map.
- An instance exists while at least one channel or server uses it. When the
  last user releases it, the instance is destroyed, along with its cache and
  its xDS channels.
- Each instance has its own cache, watchers, and xDS channels. Instances
  share no state, apart from the parsed process-wide bootstrap configuration
  and the certificate provider instances it defines.

The key is reported to CSDS as `client_scope` (see [CSDS](11-csds.md)) and
used as the `grpc.target` label on XdsClient metrics.

## 2. xDS Channels

Each XdsClient keeps a map of **xDS channels**, one for each distinct xDS
server it uses. The map key is the server identity defined in
[Bootstrap](02-bootstrap.md#41-xdsserver-object): `server_uri`, selected
channel credentials, call credentials, and recognized server features. As a
result:

- Authorities that list the same server share one xDS channel and one ADS
  stream.
- xDS channels are never shared between XdsClient instances.

An xDS channel is a normal gRPC channel to `server_uri`. It uses the
configured channel credentials, with the configured call credentials attached
to its RPCs. An xDS channel MUST NOT be connected unless it is in use. The
XdsClient MAY create the channel lazily, when an authority first needs that
server, or MAY create it up front and rely on channel idleness. In the same
way, when no authority uses an xDS channel any more, the XdsClient MAY shut
it down (for example, with reference counting) or MAY let idleness close its
connections.

The xDS channel to a server is also used for LRS when the LRS server is that
same server (see [Load Reporting](10-load-reporting.md)).

## 3. Resource Names

> **Introduced by:** [gRFC A47: xDS Federation](https://github.com/grpc/proposal/blob/master/A47-xds-federation.md)

### 3.1 Old-style and new-style names

A resource name that starts with `xdstp:` is a **new-style** name. Any other
name is an **old-style** name.

- **Old-style names** are opaque strings. They are compared as exact strings
  and fetched from the top-level `xds_servers` in the bootstrap.
- **New-style names** are URIs of the form
  `xdstp://[<authority>]/<resource type>/<id>[?<context params>]`, as defined by
  xRFC TP1 (https://github.com/cncf/xds/blob/main/proposals/TP1-xds-transport-next.md).
  The XdsClient parses them as follows:
  1. Parse the name as a URI. If it does not parse, the name is invalid.
  2. The URI authority (possibly empty) is the **authority**.
  3. Remove the leading `/` from the path, and split the rest at the first
     `/` into `<resource type>` and `<id>`. `<resource type>` MUST equal the
     type of the resource being watched or received (for example,
     `envoy.config.listener.v3.Listener`). If it does not, the name is invalid.
  4. The query parameters are the **context parameters**.
  5. **Normalize** the name: sort the context parameters by key in
     lexicographic order. If a key appears more than once, the last value
     wins.

  <!-- REVIEW(divergence) [XDS_CLIENT-1]: Duplicate context param keys. Java (XdsClient.canonifyResourceName) keeps every key=value pair and sorts the raw pairs; Go (internal/xds/clients/xdsclient/internal/xdsresource/name.go ParseName) keeps the first value; C++ (src/core/util/uri.cc query_parameter_map, used by xds_client.cc ParseXdsResourceName) keeps the last value. A47 calls this undefined and suggests "last value seen". Spec says: last value wins (C++, A47 suggestion). -->

  Two new-style names refer to the same resource if they have the same
  authority, resource type, id, and normalized context parameters. When the
  XdsClient puts a new-style name in a `DiscoveryRequest`, it uses the
  normalized form.

The cache is keyed by (authority, resource type, resource key). For old-style
names, the authority is a reserved value that cannot collide with any
`xdstp:` authority, and the key is the whole name. For new-style names, the
key is the id plus the normalized context parameters.

### 3.2 Authority to server mapping

To decide which servers to use for a resource:

- Old-style name: the top-level `xds_servers`.
- New-style name: look up the authority in the bootstrap `authorities` map.
  If it is not there, the watch fails (see [Watcher API](#5-watcher-api)). If the
  entry has a non-empty `xds_servers`, use that list. Otherwise use the
  top-level `xds_servers`.

The resulting ordered list is the authority's **server list** for fallback
(see [Fallback](#8-fallback)).

### 3.3 Building Listener names from templates

The xds resolver and the xDS-enabled server build Listener resource names
from the bootstrap templates (see [Bootstrap](02-bootstrap.md)) by
replacing every `%s` token. The exact algorithms are specified in
[Client](05-client.md) (client Listener names) and
[xDS-Enabled Servers](08-server.md) (server Listener names). In summary:

- If the template starts with `xdstp:`, the substituted value (the target's
  service name, or the listening address in `IP:port` form) is percent-encoded
  first. A non-`xdstp:` template gets no character handling.
- `PercentEncodePath(s)` leaves unchanged every character allowed in a URI
  path by RFC 3986 §3.3, including `/`, and percent-encodes (RFC 3986 §2.1)
  every other byte, including `%`. `PercentEncodeAuthority(s)` works the same
  way, using the characters allowed in a URI authority (RFC 3986 §3.2).
- The resulting name is then mapped to servers as in
  [Authority to server mapping](#32-authority-to-server-mapping).

### 3.4 References between resources

When one resource refers to another that gRPC fetches separately (an LDS
HttpConnectionManager to an RDS RouteConfiguration, a CDS EDS cluster to an
EDS resource, or an EDS locality to an `LbEndpointCollection`), the
`ConfigSource` in the reference MUST say to fetch from the same xDS server
over ADS: `ads` or `self` for RDS and EDS references, and `self` for
`LbEndpointCollection` references. Any other `ConfigSource` makes the
referring resource invalid. The referenced name is
watched as is, whether it is old-style or new-style, so a resource can refer
to a resource in a different authority. Rules for each resource are in
[Resources](04-resources/01-common-types.md).

## 4. ADS Stream

### 4.1 Stream lifecycle

- Each xDS channel has at most one active ADS stream. The stream is an RPC to
  `/envoy.service.discovery.v3.AggregatedDiscoveryService/StreamAggregatedResources`,
  using `envoy.service.discovery.v3.DiscoveryRequest` and
  `DiscoveryResponse` (`envoy/service/discovery/v3/discovery.proto`).
- The stream starts when the first subscription is made on the channel. The
  XdsClient MAY close the stream (and release the channel) when the channel
  has no subscriptions left.
- The XdsClient MUST monitor the xDS channel's connectivity state and take
  the connectivity failure status from the channel's TRANSIENT_FAILURE state
  (see [Specific cases](#73-specific-cases)). It MUST start the ADS stream with
  wait-for-ready, so that a channel in TRANSIENT_FAILURE does not cause
  repeated stream failures that needlessly grow the stream backoff delay.

  <!-- REVIEW(divergence) [XDS_CLIENT-2]: C++ monitors xDS channel connectivity (xds_transport_grpc.cc StateWatcher) and starts ADS/LRS with wait_for_ready (xds_client.cc, lrs_client.cc). Java (GrpcXdsTransportFactory: "TODO support waitForReady") and Go (internal/xds/clients/grpctransport/grpc_transport.go NewStream, no WFR, no state monitoring) learn of connectivity failures from ADS stream failures without wait-for-ready, as A57 allows. Spec says: connectivity monitoring + wait-for-ready (A57's preferred approach; Java/Go are the majority for the alternative). -->
- When the stream ends for any reason other than XdsClient shutdown, the
  XdsClient MUST start a new stream after a backoff delay. It uses the
  exponential backoff algorithm and parameters defined for connection backoff
  in [Subchannels](../04-client-channel/07-subchannels.md) (initial backoff
  1 s, multiplier 1.6, jitter 0.2, maximum backoff 120 s). The backoff state
  MUST be reset whenever a stream receives a response, so after a stream
  that received at least one response, the next attempt uses the initial
  backoff.
- On a new stream, the XdsClient sends one request for each resource type
  that has subscriptions on this channel. Each request lists all subscribed
  names of that type and carries the last accepted `version_info` for that
  type on this channel (see [Version, nonce, ACK, and NACK](#44-version-nonce-ack-and-nack)),
  with an empty `response_nonce`.

### 4.2 Requests

Each `DiscoveryRequest` has these fields:

| Field | Value |
| --- | --- |
| `node` | Set **only on the first request of each stream**. It holds the bootstrap `node` fields plus the gRPC-filled `user_agent_name`, `user_agent_version`, and `client_features` (see [Bootstrap](02-bootstrap.md#42-node-object) and [Client Features](01-architecture.md#3-client-features)). |
| `type_url` | `type.googleapis.com/<resource type>` (a v3 type). |
| `resource_names` | The full list of names of this type currently subscribed on this stream, with new-style names normalized. |
| `version_info` | The last accepted version for this type on this channel. Empty if none. |
| `response_nonce` | The `nonce` of the last response received for this type on this stream. Empty if none. |
| `error_detail` | Set only on a NACK (see [Version, nonce, ACK, and NACK](#44-version-nonce-ack-and-nack)). |

**Subscription management.** gRPC uses SotW with explicit resource names.
gRPC never sends a wildcard subscription.

- Watches share subscriptions. If a watch starts for a name that already has
  a watcher, no request is sent. If the resource is already cached, the new
  watcher is notified right away (see [Watcher API](#5-watcher-api)).
- When the first watch for a new name starts, the XdsClient sends a request
  for that type whose `resource_names` is the full updated list for the type.
- When the last watch for a name is cancelled, the XdsClient sends a request
  for that type with the name removed. If this leaves the list empty, the
  request has an empty `resource_names`. This is allowed because a previous
  request for that type has already been sent on the stream, and an empty
  list in a later request means "unsubscribe from everything of this type",
  not wildcard. The XdsClient MUST NOT send the *first* request for a type on
  a stream with an empty `resource_names`.
- The XdsClient MUST keep the cache entry for an unsubscribed name until the
  request removing it has actually been sent, or until there is no active
  stream. If a new watch for the same name starts before then, the existing
  entry is reused, so the client does not wait for a resource that the
  server believes it already sent.
- The XdsClient MAY coalesce requests. For example, it can keep at most one
  send outstanding per stream and, when that send completes, send only the
  latest state for each type that changed.
- The XdsClient MAY retain the per-type nonce for a type after all its
  subscriptions are removed, for use if a new subscription of that type
  starts on the same stream.

### 4.3 Processing a response

When a `DiscoveryResponse` arrives, the XdsClient processes it as follows:

```
on DiscoveryResponse r on stream S of xDS channel C:
  if r cannot be deserialized, or r.type_url is not a resource type the
     XdsClient knows:
    log the error; ignore r entirely (no ACK/NACK, and r does not count as
    "a response received on S")
    return
  mark S as having received a response; reset backoff
  mark C healthy (this may end fallback; see "Fallback")
  nonce[type] = r.nonce
  errors = []
  for each Any `a` in r.resources (index i):
    if a.type_url == "type.googleapis.com/envoy.service.discovery.v3.Resource":
      unwrap: name = wrapper.name; a = wrapper.resource
      (if the wrapper cannot be parsed or has no resource: record error, continue)
    if a.type_url != r.type_url: record error; continue
    decode and validate a as resource type r.type_url
    if the name is not known (not in the wrapper, and the resource does not
       parse far enough to give its name):
      record error; continue
    if decoding/validation failed: record error (but continue below)
    parse the name (see "Old-style and new-style names"); if invalid: record error; continue
    stop the does-not-exist timer for (type, name) on S, if running
    if no watch exists for (type, name): continue   # extra resources ignored
    note (type, name) as "seen in this response"
    if validation failed: apply NACK handling to the cache entry ("Error Handling")
    else if equal to the cached resource:
      set entry state ACKED; update version and timestamp; no notification
      (but if C had reported a connectivity error, clear the ambient error
       by calling OnAmbientError(OK))
    else:
      store resource (raw serialized form + parsed form); state ACKED;
      notify watchers OnResourceChanged(resource)
  for each ResourceError e in r.resource_errors (index j):
    if e.resource_name.name is empty or e.error_detail is OK: record error; continue
    parse the name; if invalid: record error; continue
    stop the does-not-exist timer for that name on S
    if no watch exists: continue
    note it as "seen in this response"
    apply server-reported error handling ("Error Handling")
  if type is Listener or Cluster:     # SotW: full set sent in every response
    for each watched resource of this type in every authority whose
       current channel is C ("Fallback"), not seen in this response:
      if the entry has a cached resource: apply deletion handling ("Error Handling")
      # entries without a cached resource are left to the timer, because r
      # may answer an earlier request that did not yet include the name
  if any resource was valid or errors is empty:
    version[C][type] = r.version_info
  send a DiscoveryRequest for this type: ACK if errors is empty, otherwise NACK
```

Notes:

- **Exact-name matching.** A resource matches a subscription only if its
  (normalized) name exactly equals the subscribed name. The server may send
  resources that were not requested. The client ignores them, except that
  validation errors in them are still reported in the NACK.
- **Per-resource validation.** A NACK rejects only the invalid resources.
  The XdsClient MUST still accept and use the valid resources in a NACKed
  response.
- Only LDS and CDS have deletion semantics in SotW. For RDS, EDS, and
  `LbEndpointCollection`, a response that leaves out a resource says nothing
  about it.
- The XdsClient SHOULD wait for watchers to finish handling notifications
  caused by one response before it reads the next response on the stream.
  This provides flow control.

### 4.4 Version, nonce, ACK, and NACK

- `version_info` is tracked **per xDS channel and per resource type**, and is
  kept across ADS stream restarts. It is updated to the response's
  `version_info` only when the response is ACKed (it had no errors). A NACK
  leaves it unchanged, even if some resources in the response were valid and
  accepted.
- `response_nonce` is tracked **per stream and per resource type**. It is
  set from every response that is processed.
- An **ACK** is a request with the current `version_info`, the response's
  nonce, the current `resource_names`, and no `error_detail`.
- A **NACK** is the same, but with `error_detail` set to a `google.rpc.Status`
  whose code is INVALID_ARGUMENT and whose message lists all errors recorded
  for the response. Each error is prefixed with the resource index and, if
  known, the resource name. Because `version_info` is not updated for a
  NACKed response, a NACK carries the previously accepted `version_info`.

### 4.5 Server-reported resource errors

> **Introduced by:** [gRFC A88: xDS Data Error Handling](https://github.com/grpc/proposal/blob/master/A88-xds-data-error-handling.md)

The server can report a per-resource error instead of sending a resource,
using the `resource_errors` field of `DiscoveryResponse` (xRFC TP3,
https://github.com/cncf/xds/blob/main/proposals/TP3-xds-error-propagation.md).
gRPC always honors these errors when they are present. No configuration
turns this on. Handling is in [Error Handling](#7-error-handling).

## 5. Watcher API

The XdsClient offers these internal operations:

- **Watch(resource type, name, watcher)**: start watching a resource. The
  name is the full resource name, old-style or new-style.
- **CancelWatch(resource type, name, watcher)**: stop watching. The caller
  MAY ask to *delay* the unsubscription, which lets an unsubscription and a
  new subscription that happen together go in one request.

A watcher has two callbacks:

- **`OnResourceChanged(StatusOr<Resource>)`**: called with a new version of
  the resource, or with an error explaining why the resource cannot be
  obtained. If a watcher that already has a valid resource receives an
  error, it MUST stop using that resource. In that case the XdsClient has
  already removed the resource from its cache.
- **`OnAmbientError(Status)`**: called for an error that does **not** change
  the watcher's use of the resource it already has, but that gives useful
  context (for example, lost contact with the xDS server). The watcher MUST
  keep using the resource it has. The error condition clears when
  `OnResourceChanged` is called, or when `OnAmbientError` is called with an
  OK status.

Rules:

- For each XdsClient, watcher callbacks MUST be called serially, never
  concurrently.
- When a watch starts for a resource that already has a cache entry, the new
  watcher gets the following, in order:
  1. `OnResourceChanged(resource)`, if a resource is cached;
  2. the entry's current error, if any: `OnAmbientError(error)` if a
     resource is cached, otherwise `OnResourceChanged(error)`;
  3. the current connectivity error of the authority's current xDS channel,
     if that channel is failing (delivered the same way).
- When a watch starts for a new cache entry, the entry is created in state
  `REQUESTED` and subscribed on every xDS channel the authority currently
  uses. If the authority's current channel is already failing, and no
  fallback server becomes usable (see [Fallback](#8-fallback)), the watcher
  immediately gets `OnResourceChanged(error)` with the connectivity error.
- If the name cannot be parsed, or names an authority that is not in the
  bootstrap, the watcher gets `OnResourceChanged(error)` right away and no
  subscription is made.
- Error messages delivered to watchers SHOULD include the xDS node ID from
  the bootstrap, to help debugging.

## 6. Cache

### 6.1 Cache entries

The cache holds one entry for each watched (authority, type, key). Entries
without watchers are removed as described in
[Requests](#42-requests). An entry holds:

- the current resource, if any, in both parsed form and the **raw serialized
  bytes** as received (after unwrapping any `Resource` wrapper), with its
  `version_info` and the time it was last updated;
- the most recent error, if any, with the `version_info` and time of the
  failed update when those apply;
- a state from the table below.

The data delivered to watchers MUST always match the cache, so that CSDS and
metrics show exactly the resources the client is using.

### 6.2 Cache entry states

| State | Resource present | Error present | Meaning |
| --- | --- | --- | --- |
| `REQUESTED` | No | No | Subscribed, but nothing received yet. |
| `DOES_NOT_EXIST` | Possibly | Yes (NOT_FOUND) | The does-not-exist timer fired (without `resource_timer_is_transient_error`), or the server deleted an LDS or CDS resource. After a deletion, the old resource stays cached unless `fail_on_data_errors` is set. |
| `ACKED` | Yes | No | The resource exists and is valid. |
| `NACKED` | Possibly | Yes | The most recent version received was invalid. The previous valid resource stays cached unless `fail_on_data_errors` is set. |
| `RECEIVED_ERROR` | Possibly | Yes (the server's status) | The server sent a per-resource error. The previous resource stays cached unless the status is NOT_FOUND or PERMISSION_DENIED and `fail_on_data_errors` is set. |
| `TIMEOUT` | No | Yes (UNAVAILABLE) | The does-not-exist timer fired while `resource_timer_is_transient_error` was set. |

These states map one-to-one to the CSDS `ClientResourceStatus` enum values
with the same names (see [CSDS](11-csds.md)). For the
`grpc.xds.cache_state` metric label, the states map to `requested`,
`does_not_exist`, `does_not_exist_but_cached`, `acked`, `nacked`,
`nacked_but_cached`, `received_error`, `received_error_but_cached`, and
`timeout`. The `*_but_cached` values are used when the entry still holds a
resource.

## 7. Error Handling

> **Introduced by:** [gRFC A88: xDS Data Error Handling](https://github.com/grpc/proposal/blob/master/A88-xds-data-error-handling.md)

### 7.1 Error categories

- **Transient errors**: connectivity problems with the xDS server. These are
  the xDS channel reporting TRANSIENT_FAILURE, an ADS stream ending without
  any response received, and a server-reported resource error with any
  status **other than** NOT_FOUND or PERMISSION_DENIED. The does-not-exist
  timer firing with `resource_timer_is_transient_error` set is also handled
  as transient.
- **Data errors**: a NACK (validation failure) of a resource, an LDS or CDS
  resource deletion, and a server-reported resource error with status
  NOT_FOUND or PERMISSION_DENIED.

### 7.2 General rule

When an error affects a cache entry:

1. If it is a data error, the server for the resource has the
   `fail_on_data_errors` server feature, and the entry has a cached
   resource, remove the cached resource from the entry.
2. Update the entry's state and error.
3. If the entry still has a cached resource, call `OnAmbientError(error)` on
   its watchers. Otherwise call `OnResourceChanged(error)`.

In practice, a transient error never discards a cached resource. A data
error discards one only when `fail_on_data_errors` is set. With no cached
resource, any error makes data-plane RPCs that depend on the resource fail.

### 7.3 Specific cases

- **NACK of a resource** (the resource fails validation): state `NACKED`. The
  error describes the validation failure (status code INVALID_ARGUMENT) and
  records the rejected `version_info` and time.
- **LDS/CDS deletion** (a cached Listener or Cluster is missing from a
  response from the authority's current server): state `DOES_NOT_EXIST`,
  error NOT_FOUND, records the response's `version_info` and time.
- **Server-reported resource error**: stop the does-not-exist timer, set
  state `RECEIVED_ERROR` with the server's status, then apply the general
  rule. The error is a data error if its code is NOT_FOUND or
  PERMISSION_DENIED and a transient error otherwise.
- **Connectivity error** (the xDS channel reports TRANSIENT_FAILURE, or the
  ADS stream ends before receiving any response): the XdsClient logs the
  error and records it as the xDS channel's status. For each authority whose
  current channel is that channel, it first tries fallback (see
  [Fallback](#8-fallback)). If fallback does not apply, or no fallback server
  is usable, it reports the error (UNAVAILABLE, with a message containing the
  server URI and the underlying reason) to the watchers of that authority's
  resources. Watchers of cached resources get `OnAmbientError`; others get
  `OnResourceChanged`. Cache entry states are not changed. An ADS stream that
  ends after receiving at least one response is **not** an error; the stream
  is simply restarted.

### 7.4 Does-not-exist timer

SotW gives the server no other way to say that a subscribed resource does
not exist, so the XdsClient runs a timer for each resource on each stream:

- **Duration**: 15 seconds. It is 30 seconds if the server serving the
  stream has `resource_timer_is_transient_error`.
- **Start**: the timer starts only when **both** of these are true:
  1. the first request on this stream that subscribes to the resource has
     been sent, and
  2. the stream is actually connected to the server, meaning the request has
     been handed to a connected transport. The XdsClient SHOULD detect this
     from a stream-level signal, such as completion of the send. It MAY
     instead treat the xDS channel reporting READY as connected.

  The timer MUST NOT start while the xDS channel is connecting or in
  connection backoff, or while a wait-for-ready stream is still queued.
- The timer is **not** started if the resource is already cached (for
  example, after a stream restart), or if the resource has already been seen
  on this stream, or if the timer is already running.
- **Stop**: when the resource, or a server-reported error for it, arrives on
  the stream, or when the stream ends. On a new stream, the timer starts
  again under the same rules if the resource is still not cached.
- **Expiry**: if the entry still has no cached resource when the timer
  fires:
  - without `resource_timer_is_transient_error`: state `DOES_NOT_EXIST`,
    error NOT_FOUND;
  - with `resource_timer_is_transient_error`: state `TIMEOUT`, error
    UNAVAILABLE, with a message naming the server.

  Either way, watchers get `OnResourceChanged(error)`. When the timer fires
  there is never a cached resource.

A timer expiry does **not** trigger fallback (see [Fallback](#8-fallback)).

### 7.5 Behavior summary

| Error | Resource cached | `fail_on_data_errors` | Watcher notification | Effect on data plane |
| --- | --- | --- | --- | --- |
| xDS channel TRANSIENT_FAILURE | no | any | `OnResourceChanged(error)` | Fail RPCs |
| xDS channel TRANSIENT_FAILURE | yes | any | `OnAmbientError(error)` | Keep using cached resource |
| ADS stream ended with no response | no | any | `OnResourceChanged(error)` | Fail RPCs |
| ADS stream ended with no response | yes | any | `OnAmbientError(error)` | Keep using cached resource |
| ADS stream ended after a response | any | any | none (stream restarted) | No change |
| NACK | no | any | `OnResourceChanged(error)` | Fail RPCs |
| NACK | yes | false | `OnAmbientError(error)` | Keep using cached resource |
| NACK | yes | true | `OnResourceChanged(error)` (resource dropped) | Fail RPCs |
| Does-not-exist timer | no (always) | any | `OnResourceChanged(NOT_FOUND)`, or `OnResourceChanged(UNAVAILABLE)` with `resource_timer_is_transient_error` | Fail RPCs |
| LDS/CDS deletion | yes | false | `OnAmbientError(NOT_FOUND)` | Keep using cached resource |
| LDS/CDS deletion | yes | true | `OnResourceChanged(NOT_FOUND)` (resource dropped) | Fail RPCs |
| LDS/CDS resource missing from response, never received | no | any | none (left to the timer) | none |
| Server-reported error, NOT_FOUND or PERMISSION_DENIED | no | any | `OnResourceChanged(status)` | Fail RPCs |
| Server-reported error, NOT_FOUND or PERMISSION_DENIED | yes | false | `OnAmbientError(status)` | Keep using cached resource |
| Server-reported error, NOT_FOUND or PERMISSION_DENIED | yes | true | `OnResourceChanged(status)` (resource dropped) | Fail RPCs |
| Server-reported error, other status | no | any | `OnResourceChanged(status)` | Fail RPCs |
| Server-reported error, other status | yes | any | `OnAmbientError(status)` | Keep using cached resource |

### 7.6 Status codes on data-plane RPCs

The status codes passed to watchers describe xDS conditions. They MUST NOT be
copied into the status of data-plane RPCs, on either the client or the
server. In particular, NOT_FOUND, PERMISSION_DENIED, and INVALID_ARGUMENT
from the XdsClient MUST NOT reach applications as RPC status codes. Data-plane
RPCs that fail because of xDS errors SHOULD use UNAVAILABLE. The watcher's
error message SHOULD be included in the RPC's status message. See the
restrictions on control-plane status codes in
[Core RPC Semantics](../02-rpc-semantics/README.md).

Ambient errors are passed to the LB policy tree as part of the resolution
note, so they can be included in RPC failure messages that happen for other
reasons (see [Client](05-client.md)).

## 8. Fallback

> **Introduced by:** [gRFC A71: xDS Fallback](https://github.com/grpc/proposal/blob/master/A71-xds-fallback.md), [gRFC A95: xDS Endpoint Fallback](https://github.com/grpc/proposal/blob/master/A95-xds-endpoint-fallback.md)

The resources from a higher-priority xDS server are always preferred. A
lower-priority (fallback) server is used only when needed, and the client
goes back to the higher-priority server as soon as it can.

### 8.1 State

For each authority, the XdsClient keeps an ordered list of **active xDS
channels**. This list is a prefix of the authority's server list (see
[Authority to server mapping](#32-authority-to-server-mapping)). The last channel in the list
is the authority's **current** channel. All watched resources of the
authority are subscribed on **every** channel in the list. Old-style names
form one more authority that uses the top-level server list.

### 8.2 Conditions

Fallback for an authority starts when **both** of these are true:

1. The authority's current channel has a connectivity failure: the xDS
   channel reports TRANSIENT_FAILURE, or its ADS stream ended before
   receiving any response.
2. Either at least one watched resource of the authority is **not cached**
   (state `REQUESTED`), or the authority sets
   `fallback_on_reachability_only: true` in the bootstrap.

A resource counts as cached if it has been received (whatever its validity),
or if it has been found not to exist. Only `REQUESTED` entries count as
uncached.

### 8.3 Process

```
on connectivity failure of channel C:
  C.status = failure
  for each authority A whose current channel is C:
    if MaybeFallback(A): continue           # a fallback server is usable
    report the error to A's watchers (see "Specific cases")

on Watch() creating a new cache entry in authority A:
  if A has no active channels, or A's current channel is failing:
    append channels from A's server list (starting after the last active
    one) until one is not failing or the list is exhausted

MaybeFallback(A):
  if not A.fallback_on_reachability_only and A has no uncached resources:
    return false
  for each server S in A's server list after the current channel:
    ch = get or create the xDS channel for S
    append ch to A's active channels
    subscribe all of A's watched resources on ch
    if ch is not failing: return true
  return false                               # all servers unreachable
```

- Opening a channel to a lower-priority server does **not** close the
  channels to higher-priority servers. Those keep trying to reconnect, and
  their ADS streams keep their subscriptions.
- Responses from any active channel update the cache. A resource received
  from the fallback server replaces the cached copy, and watchers are
  notified as usual.
- Watchers learn about connectivity errors only when **all** servers in the
  authority's list are unreachable.

### 8.4 Returning to a higher-priority server

When an active channel that is **not** the current one receives a response
(and so is marked healthy), every lower-priority channel is removed from
that authority's active list, and that channel becomes the current one. A
removed channel that no other authority uses is shut down. Resources from
the restored server overwrite the cache as they arrive.

Deletion detection for LDS and CDS (see [Processing a response](#43-processing-a-response))
uses only responses from the authority's current channel.

### 8.5 Considerations for control planes (informative)

- Each XdsClient instance and each authority falls back separately, so one
  channel's need to fall back does not affect channels for other targets.
- When the primary and fallback servers use the **same** resource names, a
  client might briefly use a mix of resources from both (a "config tear").
  Control planes can lower this risk by putting the RouteConfiguration
  inline in the Listener.
- `fallback_on_reachability_only` is for frequently changing data such as
  endpoints. A deployment can put EDS (or `LbEndpointCollection`) resources
  in a separate authority with this flag set, so endpoint data follows the
  reachable server while LDS, RDS, and CDS stay on cached primary data.

## 9. Metrics

> **Introduced by:** [gRFC A78: gRPC OTel Metrics for WRR, Pick First, and XdsClient](https://github.com/grpc/proposal/blob/master/A78-grpc-metrics-wrr-pf-xds.md)

The XdsClient reports the metrics defined in
[Metric Catalog](../08-observability/04-metrics.md): the `grpc.xds_client.*`
instruments for server connectivity, server failures, valid and invalid
resource updates, and resource counts per cache state. Their labels include
`grpc.target` (the XdsClient key), `grpc.xds.server`,
`grpc.xds.authority` (the value `#old` for old-style names),
`grpc.xds.resource_type`, and `grpc.xds.cache_state` (see
[Cache entry states](#62-cache-entry-states)).

## 10. API Requirements

The XdsClient is internal, so applications have no direct API to it. The
requirements that affect applications are:

- Bootstrap configuration as specified in [Bootstrap](02-bootstrap.md).
- The CSDS service ([CSDS](11-csds.md)), which exposes the state of every
  XdsClient instance in the process.
- Any channel API that resets connection backoff (see
  [Channel](../04-client-channel/02-channel.md)) SHOULD also reset the
  backoff of the XdsClient's ADS and LRS streams for the XdsClient instance
  that the channel uses.
