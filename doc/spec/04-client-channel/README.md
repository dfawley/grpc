# Client Channel

<!-- Sources: doc/load-balancing.md, doc/naming.md, doc/service_config.md, A31, A61 -->

From the application's point of view, a gRPC client **channel** is a logical
connection to a named service. The application identifies that service with a
**target** URI. The channel handles name resolution, connection management,
load balancing, per-method configuration, and retries, so the application can
create a channel and start sending RPCs on it right away. The channel MAY hold
zero, one, or many transport connections at any time, and the application
MUST NOT assume any relationship between RPCs and connections.

This section specifies the client channel's architecture, its public API, and
the internal plugin APIs between the channel and its components. It applies
to all gRPC implementations.

## 1. Components

The client channel has these main components:

| Component | Responsibility | Specified in |
| --- | --- | --- |
| **Channel** | The application-facing object. It parses the target, owns the other components, reports connectivity state, manages idleness, and dispatches RPCs. | [channel.md](channel.md) |
| **Name resolver** | Selected by the target URI scheme. It resolves the target into a list of endpoints (each with one or more addresses), an optional service config, attributes, and optionally a ConfigSelector. | [name-resolution.md](name-resolution.md) |
| **Service config** | Configuration published by the service owner, usually delivered by the resolver. It selects and configures the LB policy and supplies per-method settings such as timeouts and retry policies. | [service-config.md](service-config.md) |
| **ConfigSelector** | An internal per-RPC hook, supplied with each resolver result. It chooses the per-method configuration and per-call attributes for each RPC. | [call-dispatch.md](call-dispatch.md) |
| **Load balancing (LB) policy** | Creates and manages subchannels, sets the channel's connectivity state, and supplies a **picker** that chooses a subchannel for each RPC attempt. LB policies can form a tree. | [load-balancing.md](load-balancing.md), [lb-policies/](lb-policies/) |
| **Subchannel** | A potential or established connection (or a small set of connections) to one address. The channel implements it; the LB policy manages it. | [subchannels.md](subchannels.md) |
| **Retry layer** | Sits between the channel's per-call configuration and the LB pick. It runs transparent retries, configurable retries, and hedging. Every attempt is load-balanced independently. | [retries.md](retries.md) |

Supporting mechanisms: [HTTP CONNECT proxy support](proxy.md),
[client-side health checking](health-checking.md), and
[client-side backend metrics (ORCA)](backend-metrics.md). The last two run
connection-scoped streams on subchannels, using the common mechanism in
[Subchannels and Connections: Connection-Scoped Watchers and Streams](subchannels.md#9-connection-scoped-watchers-and-streams).

## 2. Architecture

```mermaid
flowchart TD
    App["Application"] -->|"RPCs"| Chan["Channel"]
    Chan -->|"target URI scheme"| Reg["Resolver registry"]
    Reg -->|"creates"| Res["Name resolver"]
    Res -->|"result: endpoints, service config, attributes, ConfigSelector"| Chan
    Chan -->|"per RPC: method + metadata"| CS["ConfigSelector"]
    CS -->|"method config, call attributes"| Retry["Retry layer"]
    Chan -->|"LB config, endpoints, attributes"| LB["LB policy"]
    LB -->|"creates and manages"| SC["Subchannels"]
    LB -->|"connectivity state + picker"| Chan
    Retry -->|"per attempt: Pick()"| Picker["Picker"]
    Picker -->|"chosen subchannel"| SC
    SC -->|"connection(s)"| Srv["Servers"]
    LB -->|"re-resolution request"| Res
```

## 3. Connection Establishment Walkthrough

Here is what a channel does from creation to sending its first RPC with a
typical LB policy:

1. The application creates the channel with a target, channel credentials,
   and options. The channel parses the target, looks up the resolver factory
   for the URI scheme (falling back to `dns:///` when needed), and computes
   the default authority. The channel starts in `IDLE`. No name resolution
   or connection attempt happens yet. See [channel.md](channel.md).
2. The application sends an RPC or asks the channel to connect. The channel
   leaves `IDLE`, creates the resolver, starts it, and reports `CONNECTING`.
   RPCs are queued until the first resolver result arrives.
3. The resolver returns a result: a list of endpoints and either a service
   config, a service config error, or no service config. It may also include
   attributes, a resolution note, and a ConfigSelector. See
   [name-resolution.md](name-resolution.md).
4. The channel picks the service config to use (the resolver's config, the
   previously used config, or the default service config), selects the LB
   policy from it, and creates the LB policy or updates the existing one with
   the endpoints, the parsed LB config, the attributes, and the resolution
   note. See [service-config.md](service-config.md).
5. The LB policy creates subchannels for the addresses it chooses to use and
   asks some or all of them to connect. It reports `CONNECTING` with a picker
   that queues picks. See [load-balancing.md](load-balancing.md) and
   [subchannels.md](subchannels.md).
6. After the LB policy update has been applied, the channel installs the new
   service config and ConfigSelector. It then re-processes the RPCs that were
   waiting for a resolver result. For each RPC, the ConfigSelector picks the
   method config, which sets the deadline, `wait_for_ready`, message size
   limits, and retry policy. The RPC then enters the retry layer, which
   starts an attempt and asks the current picker for a subchannel. See
   [call-dispatch.md](call-dispatch.md).
7. When a subchannel connects, the LB policy reports `READY` with a new
   picker. The channel re-runs the queued picks. Each completed pick yields a
   subchannel with a connection, and the attempt is started as a stream on
   that connection.
8. Later, when connections fail, the LB policy reconnects and may ask the
   resolver to re-resolve. When the channel has had no RPCs for the idle
   timeout, it returns to `IDLE` by shutting down the LB policy (and with it
   all subchannels) and the resolver.

## 4. Index

| Document | Content |
| --- | --- |
| [Channel](channel.md) | Creation, targets, authority, connectivity state, idleness, shutdown |
| [Name Resolution](name-resolution.md) | Resolver registry, resolver API, resolver results, built-in resolvers |
| [Service Config](service-config.md) | Format, delivery, validation, field reference |
| [Per-call Configuration and Call Flow](call-dispatch.md) | ConfigSelector, RPC dispatch |
| [Load Balancing](load-balancing.md) | LB policy, helper, picker, and subchannel APIs; aggregation; policy switching; list of provided LB policies |
| [`pick_first`](lb-policies/pick_first.md), [`round_robin`](lb-policies/round_robin.md), [`weighted_round_robin`](lb-policies/weighted_round_robin.md), [`least_request`](lb-policies/least_request.md), [`ring_hash`](lb-policies/ring_hash.md), [`random_subsetting`](lb-policies/random_subsetting.md), [`outlier_detection`](lb-policies/outlier_detection.md), [`priority`](lb-policies/priority.md), [`weighted_target`](lb-policies/weighted_target.md), [`rls`](lb-policies/rls.md) | The provided LB policies, one document each |
| [Subchannels and Connections](subchannels.md) | Subchannel model, connection backoff, connection scaling, connection-scoped streams |
| [HTTP CONNECT Proxy Support](proxy.md) | Proxy mapping and the CONNECT handshake |
| [Client-Side Health Checking](health-checking.md) | Health checking using the health service |
| [Client-Side Backend Metrics (ORCA)](backend-metrics.md) | Per-call and out-of-band backend metrics |
| [Retries and Hedging](retries.md) | Retry and hedging policies, throttling, transparent retries |

The xDS resolver, the xDS ConfigSelector, and the xDS LB policies are
specified in [xDS](../09-xds/README.md), especially
[client.md](../09-xds/client.md) and [lb-policies.md](../09-xds/lb-policies.md).
