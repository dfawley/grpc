> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4.2 Channel

<!-- Sources: doc/naming.md, doc/connectivity-semantics-and-api.md, doc/wait-for-ready.md, doc/service_config.md, A6, A21, A54, A62, A81, A105 -->

This section covers how a client channel is created, how it interprets its
target, how it picks the authority, how it reports connectivity state, how it
enters and leaves idleness, and how it shuts down. The components the channel
owns are covered in [Name Resolution](03-name-resolution.md),
[Service Config](04-service-config.md), [Per-call Configuration and Call Flow](05-call-dispatch.md),
[Load Balancing](06-load-balancing.md), and [Subchannels and Connections](07-subchannels.md).

## 1. Channel Creation

Creating a channel takes these inputs:

- **Target**: a string naming the service, normally in URI form
  ([Target URI Parsing](#2-target-uri-parsing)).
- **Channel credentials**: they set the transport security for every
  connection the channel makes, for example TLS credentials or insecure
  (plaintext) credentials. See [Security](../06-security/README.md).
- **Options**: optional settings that control the channel's behavior. Each
  option is listed under [API Requirements](#10-api-requirements) or in the
  section that defines the behavior it controls.

Creating a channel is cheap. It MUST NOT do any network I/O: no name
resolution and no connection attempts. The new channel starts in `IDLE`
([Leaving IDLE and Starting Name Resolution](#5-leaving-idle-and-starting-name-resolution)).

Applications SHOULD create a channel for a target when they first need it and
reuse it for as long as they need it. Creating a separate channel for each RPC
is an anti-pattern. It defeats connection reuse and load balancing, and it
adds name resolution and connection setup latency to every RPC.

## 2. Target URI Parsing

The target is parsed as a URI according to
[RFC 3986](https://tools.ietf.org/html/rfc3986). The URI **scheme** selects
the resolver factory from the resolver registry. How the **authority** and
**path** are interpreted depends on the scheme
([Name Resolution](03-name-resolution.md)).

The channel finds a resolver factory as follows:

```
ResolverFactory FindResolverFactory(string target, out Uri uri):
  uri = ParseUri(target)
  if (uri.ok() && registry.Lookup(uri.scheme) != null):
    return registry.Lookup(uri.scheme)
  // Fallback: treat the target as a name for the default scheme.
  uri = ParseUri(default_scheme + ":///" + target)   // default_scheme is "dns"
  if (uri.ok() && registry.Lookup(uri.scheme) != null):
    return registry.Lookup(uri.scheme)
  return null   // error: creation fails, or every RPC fails
```

The fallback lets applications write `server.example.com:443` instead of
`dns:///server.example.com:443`. The fallback applies both when the target is
not a valid URI and when it parses but its scheme has no registered resolver.
For example, `localhost:50051` parses as scheme `localhost` with path
`50051`. No resolver is registered for `localhost`, so the channel uses
`dns:///localhost:50051`. Likewise, `[::1]:50051` is not a valid URI, so the
channel uses `dns:///[::1]:50051`.

The default scheme is `dns`. The application can change the default scheme
process-wide (see [API Requirements](#10-api-requirements)).

If no resolver factory is found, or the factory rejects the URI as invalid for
its scheme, the error MUST reach the application. The implementation does this
in one of two ways: channel creation fails with the error, or creation returns
a channel on which every RPC fails with that error.

## 3. Authority

Every RPC carries an authority, sent as the HTTP/2 `:authority` pseudo-header
(see [gRPC over HTTP/2](../03-wire-protocol/01-http2.md)). It names the virtual host the
client is talking to. By default, channel credentials also use the authority
as the name to verify against the server's identity, for example the TLS
server certificate (see [TLS](../06-security/02-tls.md)).

### 3.1 Default Authority

The resolver factory provides the channel's default authority for a target
URI. The default rule is: the URI path with its leading `/` removed,
percent-encoded wherever the URI authority syntax
([RFC 3986 §3.2](https://tools.ietf.org/html/rfc3986#section-3.2)) requires
it. A resolver
factory MAY override the default rule. For example, the `unix` resolver uses
`localhost` (see [Name Resolution](03-name-resolution.md) for each built-in
resolver's default authority).

### 3.2 Authority Overrides

Each RPC's authority is the first one found in this order (highest precedence
first):

1. An authority the application sets explicitly for that RPC.
2. An authority set for the RPC by the LB policy's picker, for example xDS
   authority rewriting (see [Client Data Plane](../09-xds/05-client.md)).
3. An authority attached to the chosen address or endpoint as a resolver
   attribute.
4. The channel's default-authority override option, if the application set
   one.
5. The resolver factory's default authority
   ([Default Authority](#31-default-authority)).

When TLS credentials are in use, the RPC's final authority MUST, by default,
pass a per-RPC check that it matches the identity in the server's certificate.
If the check fails, the RPC fails with `UNAVAILABLE`. TLS credentials provide
an option to turn this check off (see [TLS](../06-security/02-tls.md)).

## 4. Connectivity State

The channel exposes a connectivity state with one of these values:

| State | Meaning |
| --- | --- |
| `IDLE` | The channel is not trying to connect. This is the initial state and the state after the idle timeout. Some LB policies (for example `pick_first`) also report `IDLE` after a working connection closes and they are waiting for a reason to reconnect. RPCs are not failed because the channel is in `IDLE`. Starting an RPC causes the channel to start connecting. |
| `CONNECTING` | The channel is resolving the target name or establishing connections. RPCs are generally queued until a connection is available. |
| `READY` | The LB policy has at least one connection it can use. RPCs can generally be sent right away. |
| `TRANSIENT_FAILURE` | The channel is currently unable to connect, because name resolution failed or because the LB policy could not establish any usable connection. RPCs generally fail right away unless they use `wait_for_ready` ([wait_for_ready](#8-wait_for_ready)). The channel keeps trying to recover in the background. |
| `SHUTDOWN` | The application has shut the channel down ([Channel Shutdown](#7-channel-shutdown)). New RPCs fail right away. This state is final. |

### 4.1 Who Sets the State

The channel sets the state itself in these cases:

- `IDLE`, when the channel is created and when it enters idleness
  ([Idle Timeout](#6-idle-timeout)).
- `CONNECTING`, when it leaves channel-level idleness and starts name
  resolution.
- `TRANSIENT_FAILURE`, when the resolver reports a service config error and
  the channel has no previously valid service config (see
  [Name Resolution](03-name-resolution.md)).
- `SHUTDOWN`.

At all other times, the LB policy sets the state. It usually derives the state
by aggregating its subchannels' states (see
[Load Balancing](06-load-balancing.md)).

### 4.2 Generally Expected Semantics

Because the LB policy sets the state, hard rules cannot cover every policy.
The following table shows what to expect from the built-in policies. LB
policies SHOULD follow it unless they have a specific reason not to.

| State | Typical situation | Typical next states |
| --- | --- | --- |
| `IDLE` | After creation or the idle timeout: no resolver is running, no LB policy exists, and there are no subchannels. With a lazily-connecting LB policy such as `pick_first`, also after a working connection closes: the resolver and LB policy still exist, but no connection is being attempted. In this case the picker asks the LB policy to exit idle and queues the pick. | `CONNECTING`, when the application starts an RPC or asks the channel to connect. |
| `CONNECTING` | The channel is resolving the name or the LB policy is connecting subchannels. The picker queues picks. | `READY` if a usable connection is established. `TRANSIENT_FAILURE` if name resolution fails or the LB policy cannot connect to any subchannel. `IDLE` on the idle timeout. |
| `READY` | The LB policy has a usable connection on at least one subchannel. The picker completes picks. | `IDLE` when the connection closes (for policies like `pick_first`) or on the idle timeout. `CONNECTING` or `TRANSIENT_FAILURE` with some policies when the usable connections fail. |
| `TRANSIENT_FAILURE` | Name resolution failed, or the LB policy cannot connect to any subchannel. The picker fails picks. The LB policy keeps trying to reconnect, with backoff. | `READY` once connectivity is restored. LB policies SHOULD stay in `TRANSIENT_FAILURE` ("sticky TRANSIENT_FAILURE") instead of passing through `CONNECTING` while they retry. Some cases still show `CONNECTING` in between. `IDLE` on the idle timeout. |
| `SHUTDOWN` | The application has shut the channel down. | None. |

These transition rules MUST hold for every channel:

- The initial state is `IDLE`.
- Any state can move to `SHUTDOWN`. `SHUTDOWN` is final.
- When the channel leaves channel-level idleness (after creation or after the
  idle timeout), the next state is `CONNECTING`.
- A transition is reported only when the state actually changes. Each
  notification is for a change from one state to a *different* state.

### 4.3 Races and Anti-patterns

The state can change quickly, and every report of it races with further
changes. An application MUST assume that the state it reads may already be
stale. A state-change notification only says that the state differs from the
state the application supplied. The application then reads the current state,
and that state may differ from both. Notifications can therefore look
spurious: an application watching for a change away from `CONNECTING` may
read `CONNECTING` again, because the channel briefly passed through another
state.

Checking for `READY` before sending RPCs is an anti-pattern. It gives no
assurance that an RPC will succeed, because the state can change between the
check and the RPC. RPCs need no such check: the channel queues them while it
connects. The connectivity state is meant mainly for health reporting and
monitoring. For example, a server might report itself unhealthy while its
channels to critical dependencies are not `READY`.

## 5. Leaving IDLE and Starting Name Resolution

A channel in channel-level `IDLE` has no resolver, no LB policy, and no
subchannels. It leaves `IDLE` when either of these happens:

- The application starts an RPC on the channel.
- The application reads the connectivity state with `try_to_connect` set to
  true ([API Requirements](#10-api-requirements)).

When either happens, the channel creates the resolver, starts it, and reports
`CONNECTING`. RPCs started before the first resolver result is applied are
queued. The rest of startup is covered in [Connection Establishment Walkthrough](01-architecture.md#3-connection-establishment-walkthrough)
and [Name Resolution](03-name-resolution.md).

When the LB policy itself reports `IDLE` (for example `pick_first` after a
connection closes), the resolver and LB policy keep running. A new RPC causes
the picker to ask the LB policy to exit idle. A `try_to_connect` request
causes the channel to call the LB policy's exit-idle operation directly (see
[Load Balancing](06-load-balancing.md)).

## 6. Idle Timeout

The channel has an **idle timeout**. If the channel has had no active RPCs for
the whole timeout, it enters `IDLE`.

- The idle timeout MUST be enabled by default. The RECOMMENDED default is
  **30 minutes**.
- The application MUST be able to change the idle timeout and to disable it.
  Implementations MAY enforce a minimum value (for example 1 second) and
  clamp smaller values up to it.
- An RPC counts as active from the moment the application starts it until it
  completes. That includes time spent queued waiting for a resolver result or
  an LB pick. The timer starts when the number of active RPCs drops to zero
  and is canceled when a new RPC starts. A `try_to_connect` request counts as
  activity and restarts the timer.
- The idle timeout applies in `CONNECTING`, `READY`, and `TRANSIENT_FAILURE`.

When the idle timeout fires, the channel returns to its initial state:

1. It shuts down the LB policy. That releases all of the LB policy's
   subchannels and closes their connections (subject to subchannel sharing;
   see [Subchannels and Connections](07-subchannels.md)).
2. It shuts down the resolver.
3. It discards the current service config and ConfigSelector, so the next
   exit from idleness waits for a fresh resolver result.
4. It reports `IDLE`.

The next RPC or `try_to_connect` request leaves idleness as described in
[Leaving IDLE and Starting Name Resolution](#5-leaving-idle-and-starting-name-resolution).

The idle timeout also lets an LB policy that is stuck in `TRANSIENT_FAILURE`
(for example `pick_first`, which retries indefinitely) stop reconnecting
once nobody is using the channel.

## 7. Channel Shutdown

The application can shut a channel down. Once shutdown starts:

- The channel immediately reports `SHUTDOWN` and stays in that state.
- New RPCs fail right away, whatever their `wait_for_ready` setting.
- Once no RPCs remain, the channel shuts down its resolver, LB policy, and
  subchannels and releases its resources.

The exact semantics of how shutdown interacts with RPCs that are in flight
or queued are language-specific. This includes RPCs queued for a resolver
result or an LB pick, and RPCs already sent on a connection. A language may
let them continue until they complete, fail, or reach their deadline. It may
fail queued RPCs and let only RPCs already on a connection continue. It may
cancel all of them. It may offer more than one shutdown operation with
different behaviors (for example, a graceful one and an immediate one). The
status code given to RPCs that fail because of shutdown is also
language-specific. `UNAVAILABLE` is typical.

## 8. wait_for_ready

Every RPC has a boolean `wait_for_ready` attribute. It controls what happens
when an RPC hits one of these connectivity failures:

1. The RPC is waiting for the first usable resolver result, and the channel
   reports `TRANSIENT_FAILURE` because the resolver returned an error and no
   valid service config was ever received.
2. The RPC's LB pick returns **Fail**, which LB policies typically do while
   in `TRANSIENT_FAILURE`.

If `wait_for_ready` is false (the default, sometimes called "fail fast"), the
RPC fails right away with the status the resolver or picker provided, after
the rewrite rules in [Per-call Configuration and Call Flow](05-call-dispatch.md). If it is true, the
RPC stays queued while the channel retries: it re-resolves the name or
reconnects. The RPC is processed again when there is a new resolver result or
a new picker.

`wait_for_ready` does not protect against anything else. A `wait_for_ready`
RPC still fails when its deadline expires, when it is canceled, when the
channel shuts down, when the picker returns **Drop**, or when the RPC fails
for any reason after it has been sent, for example because the server failed
it or the connection was lost. RPCs MUST NOT fail just because the channel is
in `IDLE`, `CONNECTING`, or `READY`.

The application can set `wait_for_ready` per RPC. The service config can set
a per-method default (`waitForReady`; see
[Service Config](04-service-config.md)). The value set by the application wins
over the service config. The service config cannot affect the first case
above, because no service config exists yet. Only the application's setting
applies there.

## 9. Connection Loss and GOAWAY

When a connection breaks or the server sends a GOAWAY (see
[HTTP/2 Client Transport: Draining and Closure](08-transports/02-http2.md#5-draining-and-closure)):

- The connection stops accepting new streams.
- RPCs in flight on streams the server may still process
  ([RFC 9113 §6.8](https://www.rfc-editor.org/rfc/rfc9113#section-6.8)) run
  to completion. RPCs the server is known not to have processed are eligible
  for transparent retry (see [Retries and Hedging](12-retries.md)).
- The subchannel reports the loss to the LB policy (see
  [Subchannels and Connections](07-subchannels.md)), and the LB policy decides whether and
  when to reconnect.

With the default `pick_first` policy, losing the selected connection makes the
channel report `IDLE`, and it does not reconnect until there is a new RPC or a
`try_to_connect` request. So a channel that gets a GOAWAY while it has no
active RPCs goes to `IDLE` instead of reconnecting right away. That avoids
overloading servers that are trying to shed connections. LB policies that keep
connections to all endpoints, such as `round_robin`, reconnect right away
(with backoff).

## 10. API Requirements

**Channel creation**

- The channel API MUST provide a way to create a channel from a target
  string, channel credentials, and a set of options.
- Channel creation MUST NOT block on name resolution or connection setup.
- The API MUST provide a process-wide way to change the default scheme used
  for targets that do not parse as a URI with a registered scheme
  ([Target URI Parsing](#2-target-uri-parsing)).

**Connectivity state**

- The channel API MUST provide a way to read the current connectivity state.
  That operation MUST accept a `try_to_connect` flag. When the flag is set:
  if the channel is in channel-level `IDLE`, it leaves idleness
  ([Leaving IDLE and Starting Name Resolution](#5-leaving-idle-and-starting-name-resolution)); if the LB policy
  reports `IDLE`, the channel asks the LB policy to exit idle. In both cases
  the idle timer is restarted.
- The channel API MUST provide a way to be notified when the connectivity
  state differs from a state the application supplies, with a deadline or
  cancellation. Blocking variants return true when the state has changed and
  false when the deadline expires. Asynchronous or future-based variants
  MUST also be provided wherever the language's idioms call for them.
- The channel API MUST provide a way to reset the connection backoff of
  all subchannels, so the next connection attempt can start right away (see
  [Subchannels and Connections](07-subchannels.md)). It also resets the resolver's
  re-resolution backoff ([Name Resolution](03-name-resolution.md)).

**Shutdown**

- The channel API MUST provide a way to shut the channel down, as described
  in [Channel Shutdown](#7-channel-shutdown).
- The channel API MUST provide a way to wait, with a deadline, until a
  shut-down channel has finished terminating.

**Authority**

- The channel API MUST provide an option to override the channel's default
  authority.
- The call API MUST provide a way to set the authority for an individual RPC.

**Service config and LB policy**

- The channel API MUST provide an option to set a default service config in
  JSON form. It is used when the resolver returns no service config, and it
  defaults to `{}` (see [Service Config](04-service-config.md)). An invalid
  default service config MUST cause channel creation to fail.
- The channel API MUST provide an option to disable service config lookup by
  the resolver. When it is set, resolvers do not fetch a published service
  config, and the channel uses its default service config (see
  [Name Resolution](03-name-resolution.md)). In some implementations the
  option also makes the channel ignore the service config from every
  resolver, which makes it incompatible with the xDS resolver; applications
  that use xDS should not set it.
- Applications select a default LB policy, used when the resolver provides
  no service config, with `loadBalancingConfig` in the default service config
  (see [Name Resolution](03-name-resolution.md)).

**Idleness**

- The channel API MUST provide an option to set the idle timeout and to
  disable it ([Idle Timeout](#6-idle-timeout)).

**Messages and metadata**

- The channel API MUST provide options to set the maximum size of a received
  message (default 4 MiB) and of a sent message (default unlimited). The
  effective per-RPC limits also take the service config into account (see
  [Service Config](04-service-config.md)).
- The channel API MUST provide an option to set a user-agent prefix (and MAY
  provide a suffix). gRPC adds these to its own user-agent string (see
  [gRPC over HTTP/2](../03-wire-protocol/01-http2.md)).

**Retries**

- The channel API MUST provide options to disable configurable retries and
  hedging, to change the client-side limit on `maxAttempts`, and to set the
  retry buffer limits (see [Retries and Hedging](12-retries.md)).

**Per-RPC options**

- The call API MUST provide a way to set a deadline and `wait_for_ready` on
  each RPC. The API MUST distinguish an explicit `wait_for_ready=false` from
  "not set", so that the service config's `waitForReady` applies only when
  the application did not set a value.

**Other options**, specified in the sections that define the behavior:

- DNS resolver minimum time between resolutions
  ([Name Resolution](03-name-resolution.md)).
- Connection backoff parameters and the maximum number of connections per
  subchannel ([Subchannels and Connections](07-subchannels.md)).
- Proxy configuration ([HTTP CONNECT Proxy Support](09-proxy.md)).
- Keepalive and other transport settings
  ([HTTP/2 Client Transport](08-transports/02-http2.md)).
