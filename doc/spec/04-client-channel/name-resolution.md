> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4.2 Name Resolution

<!-- Sources: doc/naming.md, doc/service_config.md, A2, A10, A21, A24, A31, A54, A61 (resolver result), A62 (address sorting background), A88 (resolution note), A79 (metrics recorder) -->

A **name resolver** turns the channel's target URI into the information the
channel needs to connect: a list of endpoints, an optional
[service config](service-config.md), attributes for the LB policy, and
optionally a ConfigSelector ([call-dispatch.md](call-dispatch.md)). This
section specifies the resolver registry, the resolver plugin API, what a
resolver result contains, how the channel handles results, and the built-in
resolvers.

## 1. Resolver Registry

gRPC keeps a registry of **resolver factories** keyed by URI scheme. Each
scheme has at most one factory. When a channel is created, it looks up the
target's scheme in the registry (applying the `dns:///` fallback in
[channel.md](channel.md)). The factory found there creates the resolver when
the channel first leaves `IDLE`, and again each time the channel leaves `IDLE`
after an idle timeout.

How the URI is interpreted depends on the scheme:

- The URI **authority** is interpreted by the scheme. Some schemes do not
  support an authority and MUST reject URIs that have a non-empty one.
- The URI **path** is the name to resolve. Most schemes ignore the leading
  `/`.
- The resolver factory provides the channel's **default authority** for a
  URI. Unless the factory overrides it, this is the path with its leading `/`
  removed, percent-encoded wherever the authority syntax requires (see
  [channel.md](channel.md)).

## 2. Resolver Results

A resolver delivers **results** to the channel. A result contains:

| Field | Contents |
| --- | --- |
| **Endpoints** | Either an error status or an ordered list of endpoints. Each endpoint has an ordered list of **one or more addresses** and a set of per-endpoint attributes (key/value pairs). Each address MAY also have per-address attributes. |
| **Service config** | One of: a parsed [service config](service-config.md); an error (the resolver found a service config but it failed to parse or validate, or the lookup failed in a way the resolver treats as an error); or nothing (the resolver has no service config to return). |
| **Attributes** | Top-level key/value pairs passed to the LB policy, for example a shared client object that the resolver gives to the LB policies. |
| **Resolution note** | A human-readable string that gives context for failures. LB policies MUST include it in the status message of every pick failure they generate. For example, the xDS resolver uses it to report xDS errors that did not invalidate cached resources. |
| **ConfigSelector** | Optional. An internal object that picks per-RPC configuration ([call-dispatch.md](call-dispatch.md)). It is not part of the public resolver API. Only built-in resolvers such as the xDS resolver provide one. |
| **Result status callback** | Optional. The channel invokes it with a status saying whether the result was accepted ([Channel Handling of Resolver Results](#3-channel-handling-of-resolver-results)). An implementation MAY return this status to the resolver synchronously from the call that reports the result instead of using a callback. |

### 2.1 Ordering

The endpoint list and each endpoint's address list are both ordered, and the
order may matter to the LB policy. For example, `pick_first` tries addresses
in order (see [lb-policies/pick_first.md](lb-policies/pick_first.md)).
Resolvers that want to spread client load across servers SHOULD randomize the
endpoint order, unless the name service already does so (as DNS servers often
do).

### 2.2 Attributes

Per-endpoint and top-level attributes are how resolvers pass information to
LB policies. The resolver API MUST support per-endpoint attributes and
top-level attributes. Per-address attributes MAY be supported. The keys and
meanings of specific attributes belong to the components that define them,
for example hierarchical path attributes in [load-balancing.md](load-balancing.md).
Attributes not defined there are implementation-internal.

### 2.3 Service Config Parsing

The channel gives the resolver an operation that parses and validates a
service config from JSON (see [service-config.md](service-config.md)). It
returns either a parsed service config or an error. A resolver that supports
service configs MUST parse every config it returns with this operation and put
the outcome (parsed config or error) in its result. A resolver that does not
support service configs leaves the field empty.

## 3. Channel Handling of Resolver Results

The channel handles each resolver result as follows:

```
OnResolverResult(result):
  result_status = OK
  service_config = null
  config_selector = null

  if (result.service_config.IsEmpty()):
    // No service config from the resolver: use the channel's default.
    service_config = channel.default_service_config    // "{}" if not set
  else if (result.service_config.IsError()):
    if (channel.service_config != null):
      // Keep using the last valid config (and its ConfigSelector).
      service_config = channel.service_config
      config_selector = channel.config_selector
    else:
      // No valid config yet: the channel cannot proceed.
      status = RewriteControlPlaneStatus(result.service_config.error)
      channel.SetConnectivityState(TRANSIENT_FAILURE, status)
      channel.FailQueuedRpcsWithoutWaitForReady(status)   // see call-dispatch.md
      result_status = UNAVAILABLE("no valid service config")
  else:
    service_config = result.service_config

  if (service_config != null):
    lb_config = ChooseLbPolicy(service_config)
    // Returns only after the LB policy has handled the update and published
    // its new picker.
    result_status = channel.CreateOrUpdateLbPolicy(
        lb_config, result.endpoints, result.resolution_note, result.attributes)
    if (config_selector == null):
      config_selector = result.config_selector
                        ?? DefaultConfigSelector(service_config)
    if (service_config != channel.service_config ||
        config_selector != channel.config_selector):
      channel.service_config = service_config
      channel.config_selector = config_selector
      channel.ReprocessQueuedRpcs()   // RPCs waiting for a resolver result

  if (result.result_status_callback != null):
    result.result_status_callback(result_status)
```

Notes:

- The channel does not use the endpoint list itself. It passes the list, or
  the endpoints error, to the LB policy. The LB policy decides how to handle
  an endpoints error. Typically it keeps using the endpoints it already has
  and, if it has none, reports `TRANSIENT_FAILURE` with a picker that fails
  picks with that error.
- The LB update returns a status. A non-OK status means the LB policy
  rejected the update, for example because the endpoint list is empty. That
  status is what the channel reports to the resolver through the result
  status callback.
- The new ConfigSelector MUST NOT be used for any RPC until the LB policy
  has handled the update and published its new picker
  ([call-dispatch.md](call-dispatch.md)).
- `RewriteControlPlaneStatus` applies the status-code restriction in
  [call-dispatch.md](call-dispatch.md#43-control-plane-status-restriction).
  It rewrites codes that gRPC must not generate, such as `NOT_FOUND`, to
  `INTERNAL`.
- When the channel uses the default service config because the resolver
  returned none, that is a valid config. A later service config error then
  keeps using the default config.
- The option that disables service config lookup is passed to the resolver.
  A resolver that fetches a service config published by the service owner,
  such as the `dns` resolver's TXT lookup, MUST NOT fetch it when the option
  is set, and reports no service config. The channel then uses its default
  service config. The option does not affect a resolver that builds the
  service config itself as part of its job: the xDS resolver builds its LB
  policy config from xDS resources (see [client.md](../09-xds/client.md)).

  > **Note:** In some implementations this option also makes the channel
  > ignore the service config from every resolver, not only a published one.
  > With those implementations the option is not compatible with the xDS
  > resolver, and applications that use xDS should not set it.

<!-- REVIEW(divergence) [SERVICE_CONFIG-2]: Same question as service-config.md [Service Config: Validation and Error Handling](service-config.md#3-validation-and-error-handling) (see the comment there). C++ and Go: invalid config with no previous valid config -> TRANSIENT_FAILURE, default config not used. Java: falls back to the default config whenever one is set. gRFC A21 says both in different sections. spec says: no fallback. -->

### 3.1 LB Policy Selection

`ChooseLbPolicy` takes the first of these that applies:

1. If the service config sets `loadBalancingConfig`, use the policy selected
   from it at parse time (the first policy in the list that is registered;
   see [service-config.md](service-config.md)).
2. Otherwise, if the service config sets the deprecated
   `loadBalancingPolicy`, use that policy with an empty config.
3. Otherwise, if the application set a default LB policy through the channel
   API ([channel.md](channel.md)), use it with an empty config.
4. Otherwise, use `pick_first` with an empty config.

How the channel creates, updates, or gracefully swaps the LB policy is
specified in [load-balancing.md](load-balancing.md).

## 4. Watch-based and Polling Resolvers

The resolver API supports two kinds of resolver:

- **Watch-based** resolvers subscribe to their data source when they start
  and report a new result whenever the data changes. The xDS resolver is an
  example.
- **Polling** resolvers send a query to get data. After a query succeeds,
  they do not query again until the channel asks them to. The `dns` resolver
  is an example.

Any resolver MAY report a new result at any time. A resolver MUST report an
initial result (or an error) promptly after it starts. Results from one
resolver are delivered to the channel one at a time, never concurrently.

### 4.1 Re-resolution Requests

The resolver API has an operation to **request re-resolution**. The channel
calls it when an LB policy asks for re-resolution through its helper (see
[load-balancing.md](load-balancing.md)), usually because a connection or
connection attempt failed.

- For a watch-based resolver, the request is a no-op.
- For a polling resolver, the request asks for a new query. The resolver
  need not query right away. It MUST protect its name service from excessive
  load. It MAY rely on caching in the underlying resolution mechanism, or it
  MAY enforce a minimum interval between queries. A request that arrives
  during the minimum interval MUST NOT be dropped. The query runs when the
  interval expires.
- When a query fails, or the result status for a polling resolver's result
  is not OK (for example the LB policy rejected an empty endpoint list), the
  resolver MUST query again with exponential backoff. It SHOULD use the
  connection backoff parameters defined in [subchannels.md](subchannels.md).
  The backoff state resets after an accepted result.
- The resolver API MUST have an operation to reset this backoff. The channel
  invokes it when the application resets connection backoff
  ([channel.md](channel.md)).

## 5. Resolver Errors

A resolver reports errors through the result fields:

- An **endpoints error** says the resolver could not get endpoints, for
  example because the DNS lookup failed. The error is passed to the LB
  policy. If the LB policy fails picks because of it, the pick failure
  status is subject to the control plane status restriction
  ([call-dispatch.md](call-dispatch.md)).
- A **service config error** is handled as in
  [Channel Handling of Resolver Results](#3-channel-handling-of-resolver-results). If the channel has no
  previously valid service config, it reports `TRANSIENT_FAILURE`. RPCs
  without `wait_for_ready` that are waiting for a resolver result fail with
  the error status, after the control plane status restriction: codes such
  as `INVALID_ARGUMENT`, `NOT_FOUND`, and `DATA_LOSS` are rewritten to
  `INTERNAL`.

Resolvers SHOULD use `UNAVAILABLE` for name resolution failures. They MUST
NOT copy status codes from a control plane (for example a status returned by
a remote naming service RPC) into resolver errors without translating them.
Their status messages SHOULD include enough context, such as the name being
resolved and the underlying error, to diagnose the failure.

## 6. Resolver API

The resolver plugin API has three parts. They are specified abstractly here.

**Resolver factory** (registered in the resolver registry):

| Operation | Description |
| --- | --- |
| `Scheme()` | Returns the URI scheme this factory handles. |
| `IsValidUri(uri)` | Reports whether the URI is valid for this scheme, for example whether it has a usable path and whether its authority is supported. Used at channel creation. |
| `DefaultAuthority(uri)` | Returns the default authority for the URI ([Resolver Registry](#1-resolver-registry)). |
| `CreateResolver(args)` | Creates a resolver. `args` contains at least the target URI, the channel's options, the channel-side result handler, and the channel's metrics recorder (stats plugin group) for recording non-per-call metrics ([metrics-framework.md](../08-observability/metrics-framework.md)). |

**Resolver** (created by the factory and owned by the channel):

| Operation | Description |
| --- | --- |
| `Start()` | Starts resolution. Called once. |
| `RequestReresolution()` | Requests a new resolution ([Re-resolution Requests](#41-re-resolution-requests)). |
| `ResetBackoff()` | Resets any re-resolution backoff and minimum-interval state, so a pending re-resolution runs right away. |
| `Shutdown()` | Stops the resolver. After it returns, the resolver MUST NOT deliver any more results. |

**Result handler** (implemented by the channel and passed to the resolver):

| Operation | Description |
| --- | --- |
| `ReportResult(result)` | Delivers a result ([Resolver Results](#2-resolver-results)). The channel reports whether it accepted the result through the result status callback or the return value. |
| `ParseServiceConfig(json)` | Parses and validates a service config ([service-config.md](service-config.md)). Returns a parsed config or an error. |

The channel calls a resolver's operations one at a time, never concurrently.
A resolver may deliver results from any context, and the channel MUST
serialize result handling with its other control plane work.

## 7. Built-in Resolvers

gRPC MUST provide the resolvers in this section. The xDS resolver (scheme
`xds`) is specified in [client.md](../09-xds/client.md).

### 7.1 `dns`

**Syntax:** `dns:[//authority/]host[:port]`

| Part | Meaning |
| --- | --- |
| `host` | The DNS name to resolve, or an IPv4 or IPv6 literal. An IPv6 literal MUST be in square brackets when a port is present, for example `dns:///[2001:db8::1]:8443`. |
| `port` | The port used for every returned address. Defaults to **443**. |
| `authority` | Optional. Names the DNS server to query. Whether the authority is supported, its accepted forms, and its default port are implementation-defined (see below). If the authority is empty, the system's DNS configuration is used. |

How a non-empty authority is handled is implementation-defined. A resolver
may honor it (for example in `ip[:port]` form, with DNS port 53 by default),
reject the URI ([Resolver API](#6-resolver-api)), or ignore it and use the
system's DNS configuration. Portable applications SHOULD NOT rely on the
authority.

**Default authority:** `host[:port]` exactly as written in the target (the
path without its leading `/`). The default port is not appended.

**Address resolution:**

- If `host` is an IP literal, the resolver returns that address without any
  DNS query.
- Otherwise the resolver looks up both A and AAAA records for `host`.
- Each resolved address is returned as its own endpoint with one address,
  because DNS cannot express which addresses belong to the same endpoint.
- The resolver MUST sort the addresses with the destination address selection
  rules of [RFC 6724](https://www.rfc-editor.org/rfc/rfc6724), unless the
  underlying resolution mechanism already does so.
- If the lookup fails, or returns no addresses, the resolver reports a result
  whose endpoints field and service config field both hold an `UNAVAILABLE`
  error naming the host. So the channel stays in `TRANSIENT_FAILURE` until
  the first successful resolution. After that, the last valid service config
  stays in use and the LB policy decides how to handle the endpoints error.
  <!-- REVIEW(divergence) [DNS-1]: All three end up in TRANSIENT_FAILURE before the first success. C++: an empty or failed lookup returns UNAVAILABLE for both addresses and service config (dns_resolver.cc OnResolvedLocked). Go: temporary errors go to ReportError (both fields); NXDOMAIN-type errors are turned into an update with zero addresses, which pick_first rejects (internal/resolver/dns handleDNSError). Java: only the addresses carry the UNAVAILABLE error; the TXT service config is still looked up and returned (DnsNameResolver.doResolve). spec says: both fields hold the error (matches C++). -->

**Service config:** Unless service config lookup is disabled
([channel.md](channel.md)), the resolver also looks up the service config in
DNS TXT records ([Service Config in DNS](#72-service-config-in-dns)). It MUST NOT look up
TXT records when `host` is `localhost` or an IP literal. In those cases it
reports no service config. This avoids slow, needless lookups for local and
literal targets.

**Re-resolution:** The `dns` resolver is a polling resolver. It MUST enforce
a minimum time between resolutions. The default is 30 seconds. gRPC MUST
provide a way for the application to configure it, per channel or for the
whole process. A re-resolution request that arrives before the minimum time
has passed is delayed until then, not dropped. Failed resolutions are retried
with backoff as in [Re-resolution Requests](#41-re-resolution-requests).

### 7.2 Service Config in DNS

#### TXT Record Format

For target host `H`, the service config is published as a DNS TXT record on
the name `_grpc_config.H`. The record uses the attribute format of
[RFC 1464](https://tools.ietf.org/html/rfc1464), with the attribute name
`grpc_config`:

```
_grpc_config.myserver  3600  TXT "grpc_config=[{\"serviceConfig\":{\"loadBalancingConfig\":[{\"round_robin\":{}}],\"methodConfig\":[{\"name\":[{\"service\":\"MyService\",\"method\":\"Foo\"}],\"waitForReady\":true}]}}]"
```

- A single TXT string holds at most 255 bytes
  ([RFC 1035 §3.3](https://tools.ietf.org/html/rfc1035#section-3.3)). A
  record can hold several strings, and the resolver MUST concatenate a
  record's strings with no separator
  ([RFC 4408 §3.1.3](https://tools.ietf.org/html/rfc4408#section-3.1.3)).
  The whole DNS response cannot be larger than 65535 bytes.
- The resolver uses the first TXT record whose concatenated value starts
  with `grpc_config=`. Everything after that prefix is the config value.
  Records without the prefix are ignored, and so are any later records with
  the prefix. Strings from different records are never concatenated.
- TXT records are ASCII, so the service config published this way (service
  names, method names, LB policy names, and so on) must be ASCII.
- If the TXT lookup fails or finds no matching record, the resolver reports
  no service config, and the address result is unaffected. A TXT failure
  MUST NOT fail resolution.

#### Service Config Choices

The config value is a JSON **array of service config choices**. This format
lets service config changes be canary tested. The client uses the **first**
choice whose criteria all match it:

```
[
  {
    "clientLanguage": [string],
    "percentage": number,
    "clientHostname": [string],
    "serviceConfig": object
  },
  ...
]
```

| Field | Type | Matching rule | Validation |
| --- | --- | --- | --- |
| `clientLanguage` | array of strings | Matches if the client's gRPC language name is in the list, compared case-insensitively. Examples of names: `c++`, `java`, `go`, `python`. Absent or empty matches every client. | Must be an array of strings. |
| `percentage` | integer | Matches if the client's random draw ([below](#percentage-draw)) is less than `percentage`. Absent matches every client. | Must be an integer from 0 to 100 inclusive. |
| `clientHostname` | array of strings | Matches if the client's hostname, as reported by the system, equals an entry exactly (case-sensitive). Absent or empty matches every client. | Must be an array of strings. |
| `serviceConfig` | object | — | Required. Must be a JSON object holding a service config ([service-config.md](service-config.md)). |

<a id="percentage-draw"></a>
**Percentage draw.** To evaluate `percentage` for a choice, the client draws
a fresh uniformly random integer in `[0, 99]`. Each choice that has a
`percentage` gets its own draw, made each time a resolution result is
processed. The choice matches when that integer is less than `percentage`.
So `0` never matches and `100` always matches.

**Validation and error handling.** The resolver reports a **service config
error** if any of these is true:

- The value is not valid JSON, or is not a JSON array.
- Any choice is not a JSON object.
- Any choice has a field other than the four above. This rule is stricter
  than the service config's own rule that unknown fields are ignored. The
  stricter rule applies only to the choice wrapper.
- Any criterion field has the wrong type or an invalid value.
- The **selected** choice's `serviceConfig` is missing, is not an object, or
  fails service config validation ([service-config.md](service-config.md)).

Only the selected choice's `serviceConfig` is validated as a service config.
An invalid `serviceConfig` in a choice that is not selected does not make the
result invalid. A valid `serviceConfig` in a choice that is not selected does
not rescue an invalid selected one.

If the array is valid but no choice matches, the resolver reports **no
service config**, and the channel uses its default service config.

### 7.3 `unix`

**Syntax:** `unix:path` or `unix:///absolute_path` (Unix-like systems only).

- `path` is the filesystem path of a Unix domain socket. In the first form
  the path may be relative or absolute. In the second form the path is
  absolute: the last of the three slashes is part of the path, so the URI
  path is `/absolute_path`.
- The URI MUST NOT have an authority (for example `unix://host/path` is
  invalid).
- The result has one endpoint with one address.
- **Default authority:** `localhost`.

### 7.4 `unix-abstract`

**Syntax:** `unix-abstract:abstract_path` (Linux only).

- `abstract_path` is a name in the abstract socket namespace. It is not
  related to filesystem paths, and no filesystem permissions apply: any
  process or user can connect to the socket.
- The implementation adds the leading null byte (`\0`) that abstract socket
  addresses require. The target MUST NOT include it.
- The result has one endpoint with one address.
- **Default authority:** `localhost`.

### 7.5 `vsock`

**Syntax:** `vsock:cid:port` (Linux only).

- `cid` is the 32-bit VSOCK Context Identifier. It identifies a virtual
  machine or the host.
- `port` is a 32-bit port number that tells apart the services on that
  machine.
- The result has one endpoint with one address.
- **Default authority:** `cid:port`, the URI path as written in the target.

### 7.6 `ipv4` and `ipv6`

**Syntax:**

- `ipv4:address[:port][,address[:port],...]`
- `ipv6:address[:port][,address[:port],...]`

- Each comma-separated element is one address and becomes its own endpoint,
  in the order given.
- `port` defaults to **443**.
- For `ipv6`, an address with a port MUST be in square brackets, for example
  `ipv6:[2607:f8b0:400e:c00::ef]:443` or `ipv6:[::]:1234`.
- No DNS lookup is done, no service config is returned, and the result never
  changes. Re-resolution requests are no-ops.
- **Default authority:** the default rule ([Resolver Registry](#1-resolver-registry)).

## 8. API Requirements

- gRPC MUST provide a public API for registering custom resolver factories
  under a URI scheme. The factory and resolver interfaces are those in
  [Resolver API](#6-resolver-api), except that the ConfigSelector field is not
  part of the public API. Registering a scheme that is already registered
  MUST either replace the existing factory or be rejected. Implementations
  MUST document which.
- gRPC MUST provide a way to supply a resolver factory for one channel
  without registering it globally.
- The custom resolver API MUST give resolvers the service config parsing
  operation and the result status reporting described in [Resolver API](#6-resolver-api).
- The resolver creation arguments MUST give resolvers, including custom
  ones, access to the channel's metrics recorder (stats plugin group) for
  recording non-per-call metrics and registering gauge callbacks (see
  [metrics-framework.md](../08-observability/metrics-framework.md)).
- The channel API MUST provide options to:
  - disable service config lookup by the resolver ([channel.md](channel.md));
  - set the minimum time between `dns` resolutions
    ([`dns`](#71-dns)).
- gRPC MUST provide a process-wide way to change the default scheme used in
  the target fallback ([channel.md](channel.md)).
