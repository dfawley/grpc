# Metrics Framework and OpenTelemetry Plugin

<!-- Sources: A79, A66, A72, A78, A94, A96, A108 -->

This section specifies how metrics are defined, registered, recorded, scoped,
and exported. Per-call metrics are driven by the call tracers in
[Instrumentation Architecture](instrumentation.md). Non-per-call metrics, such as LB policy, XdsClient,
subchannel, and TLS metrics, are recorded directly by gRPC components through
the framework below. The complete list of metrics is in [Metric Catalog](metrics.md).

## 1. Goals

- gRPC components, and third-party plugins such as custom LB policies and
  resolvers, own the definitions of the metrics they record, independent of the
  stats plugin that exports them.
- Applications can register several stats plugins, each scoped to a subset of
  channels.
- Stats plugins let users enable and disable individual metrics and choose
  which optional labels to record.

## 2. Instrument Registry

gRPC MUST maintain a process-wide **instrument registry**. Every non-per-call
metric MUST be registered there before it can be recorded.

### 2.1 Instrument Descriptor

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | Instrument name. MUST follow the naming conventions in [Naming Conventions](#5-naming-conventions). |
| `description` | string | Human-readable description. |
| `unit` | string | Unit of the recorded values, using OpenTelemetry/UCUM conventions ([Units](#7-units)). |
| `type` | enum | Instrument kind and value type. Kinds: **Counter** (monotonic sum), **UpDownCounter** (non-monotonic sum), **Histogram**, and **Gauge**. Gauges are normally *callback* gauges ([Callback Gauges](#4-callback-gauges)). Value types are integer (int64 or uint64) and double. |
| `label_keys` | ordered list of strings | **Required labels.** A value for each MUST be supplied with every measurement. |
| `optional_label_keys` | ordered list of strings | **Optional labels.** A value for each MUST be supplied with every measurement. Each stats plugin records or discards each one according to its configuration. Optional labels are not recorded unless configured. |
| `enabled_by_default` | bool | Hint from the metric's author on whether stats plugins should record the metric when the user has not configured it explicitly. MUST be false for experimental metrics. |
| `bucket_boundaries` (histograms only) | list of numbers, optional | Recommended histogram bucket boundaries (see [Default Histogram Buckets](#8-default-histogram-buckets)). |

gRPC reserves the right to add optional labels, including existing optional
labels, to existing metrics. Adding an optional label is not a breaking change.

### 2.2 Registration Rules

- Registering an instrument returns a **handle**, for example a dense index,
  that components use to record measurements and that plugins use to look up
  their backing instrument quickly.
- Instruments SHOULD be registered during static initialization, before the
  application's main entry point runs. Implementations MAY support dynamic
  registration afterwards. If they do, they MAY limit newly registered
  instruments to stats plugins created after the registration.
- **Duplicate names.** Registering two descriptors with the same name is a
  programming error and MUST fail fatally (for example, a panic or abort at
  registration).
- The registry MUST allow stats plugins to enumerate all registered
  descriptors.

## 3. Stats Plugin Registry and Scoping

### 3.1 Global Stats Plugin Registry

gRPC MUST maintain a process-wide **stats plugin registry** of globally
registered stats plugins. When a stats plugin is created, it reads the
instrument registry and creates a backing instrument (for example, an
OpenTelemetry instrument) for each descriptor that its configuration enables.
It MAY create them lazily. Global registration applies to channels and servers
created *after* the registration.

### 3.2 Channel Scoping

The set of stats plugins that applies to a channel, called the channel's
**stats plugin group**, is fixed when the channel is created:

```
group(channel) =
    { p in global_registry : p.IsEnabledForChannel(scope) }
  ∪ { plugins registered directly on this channel }

where scope = ChannelScope {
    target:    the channel's canonical target URI,
    authority: the channel's default authority (derived from the target
               unless the channel overrides it)
}
```

- **Scope predicate.** A stats plugin MAY be configured with a channel scope
  predicate over `ChannelScope` that decides whether the plugin applies to a
  given channel. Without a predicate, the plugin applies to all channels. The
  predicate affects channels only. It does not affect server-side recording.
- **Per-channel plugins.** A stats plugin MAY also be registered directly on a
  single channel at creation time, without being registered globally.
- The group is used both for per-call metrics (through the call tracers it
  installs) and for all non-per-call metrics recorded by components owned by
  the channel (resolver, LB policies, subchannels, transports).


### 3.3 Server Scoping

A server's stats plugins are those global plugins that report themselves
enabled for the server, given the server's configuration, plus any plugins
registered directly on the server. Server-side per-call metrics and
server-scoped non-per-call metrics (for example, server TLS handshake metrics
and the XdsClient used by xDS-enabled servers) are recorded on this set.

### 3.4 Shared Components

Some components are not owned by a single channel. Examples are the XdsClient,
which is shared by all channels with the same xDS target (see
[XdsClient](../09-xds/xds-client.md)), and subchannels that are shared across
channels. Such a component MUST use the stats plugin group of the **first**
channel (or server) that caused it to be created, for its whole lifetime. The
groups of later channels that share it are ignored for that component's
metrics.

### 3.5 Recording

Components record through the stats plugin group. The group fans each
measurement out to every plugin in it:

```
AddCounter(handle, value, label_values[], optional_label_values[])
RecordHistogram(handle, value, label_values[], optional_label_values[])
// UpDownCounter: Add(handle, delta, ...) where delta may be negative
```

`label_values` and `optional_label_values` MUST be given in the same order as
the descriptor's `label_keys` and `optional_label_keys`. Each plugin drops the
measurement if the metric is disabled in that plugin, and drops the optional
label values that it is not configured to record.

LB policies, resolvers, and transports get access to the group through their
helper or creation arguments (see
[Load balancing](../04-client-channel/load-balancing.md) and
[Name resolution](../04-client-channel/name-resolution.md)).

## 4. Callback Gauges

Gauges whose value is sampled rather than event-driven use **callbacks**:

- A component registers a callback with the stats plugin group, together with
  the list of gauge handles that the callback reports and a **minimum
  interval**. The default minimum interval is **5 seconds**.
- Each plugin invokes the callback when it collects metrics, but no more often
  than the minimum interval. The callback reports
  `(handle, value, label_values[], optional_label_values[])` tuples through a
  reporter object.
- Several callbacks MAY report the same gauge, provided no two of them report
  the same label-value set. If two do, the behavior is undefined.
- Registration returns a handle that controls the callback's lifetime.
  Releasing the handle unregisters the callback. The handle MUST NOT outlive
  the stats plugin group that issued it.

## 5. Naming Conventions

Metric names follow the general OpenTelemetry semantic-convention guidelines,
with these additional rules:

| Rule | Example |
| --- | --- |
| Metrics defined by gRPC MUST be in the `grpc.` namespace. | `grpc.client.attempt.duration` |
| Third-party plugins MUST NOT use the `grpc.` namespace. | |
| Metrics from LB policies MUST be under `grpc.lb.<policy>.` | `grpc.lb.wrr.rr_fallback` |
| Metrics from resolvers MUST be under `grpc.resolver.<name>.` | `grpc.resolver.dns.…` |
| Metrics from transports MUST be under `grpc.transport.<name>.` | `grpc.transport.http2.…` |
| New metrics SHOULD follow the style of existing metrics: `.` separators and lowercase snake_case components. | |

Label names follow the same `grpc.` namespace rule (for example,
`grpc.method` and `grpc.lb.locality`).

## 6. Stability Tiers

Every metric, and every label of a metric, is in exactly one of these tiers:

| Tier | Default | Guarantees |
| --- | --- | --- |
| Experimental | **Always off by default** | May change or be removed at any time. |
| Stable, off by default | Off | Stable name, type, unit, and labels. Used for metrics that are useful but too expensive to collect by default. |
| Stable, on by default | On | Stable. |

- New metrics MUST start as experimental. Once stable, a metric MAY be made
  on by default.
- A metric's documentation says whether it is experimental. The name does not
  encode it: there is no `experimental` namespace, so that
  de-experimentalizing a metric does not break its time series.
- Users MAY enable experimental metrics explicitly ([Enabling and Disabling Metrics](#94-enabling-and-disabling-metrics)).

## 7. Units

Units follow the OpenTelemetry/UCUM conventions:

| Quantity | Unit |
| --- | --- |
| Latency and durations | `s` (seconds, recorded as double) |
| Sizes | `By` (bytes) |
| Counts | Annotated dimensionless units in braces, naming the counted thing: `{call}`, `{attempt}`, `{retry}`, `{hedge}`, `{transparent_retry}`, `{update}`, `{endpoint}`, `{weight}`, `{resource}`, `{failure}`, `{disconnection}`, `{connection}`, `{handshake}`, `{bool}` |

## 8. Default Histogram Buckets

The following bucket boundaries are the defaults for gRPC histograms:

| Bucket set | Boundaries |
| --- | --- |
| **Latency** (`s`) | 0, 0.00001, 0.00005, 0.0001, 0.0003, 0.0006, 0.0008, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.008, 0.01, 0.013, 0.016, 0.02, 0.025, 0.03, 0.04, 0.05, 0.065, 0.08, 0.1, 0.13, 0.16, 0.2, 0.25, 0.3, 0.4, 0.5, 0.65, 0.8, 1, 2, 5, 10, 20, 50, 100 |
| **Size** (`By`) | 0, 1024, 2048, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864, 268435456, 1073741824, 4294967296 |
| **Count** | 0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536 |

Individual metrics MAY recommend other boundaries (see [Metric Catalog](metrics.md)).
Where the OpenTelemetry API supports instrument advice, the plugin SHOULD
supply the recommended boundaries as advice. Otherwise, choosing boundaries
is the user's responsibility, through OpenTelemetry SDK views. Changing
bucket boundaries is not considered a breaking change.

## 9. OpenTelemetry Plugin

gRPC MUST provide an OpenTelemetry plugin that implements both a stats plugin
(this section) and a tracing plugin ([Tracing](tracing.md)).

### 9.1 General Requirements

1. **Multiple plugins.** Applications MUST be able to install more than one
   OpenTelemetry plugin, globally and/or per channel or server. Each plugin is
   configured independently.
2. **MeterProvider per plugin.** Each plugin MUST accept its own
   MeterProvider. If no MeterProvider is set, the plugin records no metrics:
   it is a no-op for metrics.
3. **No global fallback.** The plugin MUST NOT fall back to the
   OpenTelemetry global MeterProvider or TracerProvider.
4. **API-only dependency.** The plugin SHOULD depend only on the OpenTelemetry
   API, not the SDK. Users control views, aggregation, and export through the
   SDK MeterProvider that they supply.
5. **Meter identity.** The plugin creates its Meter with a `name` that
   identifies the gRPC library (for example `grpc-<implementation>`) and a
   `version` equal to the gRPC library's release version (for example
   `1.57.1`). All gRPC instruments are created from this Meter.
6. Registering the same plugin instance both globally and on a channel or
   server may record duplicate data. Applications SHOULD avoid doing so.

### 9.2 Per-Call Instruments

The plugin creates the per-call instruments of [Metric Catalog](metrics.md) (client
attempt and call metrics, retry metrics, and server metrics) itself and
records them from its call tracers. It creates the non-per-call instruments
from the instrument registry.

### 9.3 Optional Labels

The plugin MUST provide a way to configure a set of optional label keys to
record. A configured key is recorded on every metric that lists it among its
optional labels, both per-call and non-per-call. Unconfigured optional labels
are discarded. One suitable implementation is a per-instrument bit set over the
positions of the descriptor's optional labels.

### 9.4 Enabling and Disabling Metrics

The plugin MUST let users override each metric's default:

- **enable** a set of metrics by name, in addition to those enabled by default
  (this is how experimental and off-by-default metrics are turned on);
- **disable** a set of metrics by name;
- **disable all** metrics, including the defaults, so that only explicitly
  enabled metrics are recorded.

Enabling a metric name that is not registered has no effect.

### 9.5 Generic Method Names

Servers may receive arbitrary method names, and applications may handle
methods that were not registered in advance (generic methods). Recording such
names verbatim would allow an unbounded number of
`grpc.method` values. Therefore:

- For a **registered** method, the plugin records the full method name in
  `grpc.method`.
- For a **generic** method (on the server, one not registered with the
  server; on the client, one invoked without a known method descriptor), the
  plugin records `grpc.method` as **`"other"`** by default.
- The plugin MUST accept an optional **generic method attribute predicate**
  that receives the generic method name and returns true to record it
  verbatim or false to record `"other"`. The predicate is never consulted for
  registered methods.

<!-- REVIEW(divergence) [METRICS-2]: The "other" default for generic methods is uniform: all three record "other" on both client and server (Java: unless MethodDescriptor.isSampledToLocalTracing(), set by generated code; Go client: unless grpc.StaticMethod call option; Go server: unless registered; C++: unless registered). The predicate differs: Java: no generic-method predicate at all; Go: MethodAttributeFilter on server only, and it is applied to all methods (it can turn a registered method into "other" but never records an unregistered one verbatim); C++: GenericMethodAttributeFilter consulted only for non-registered methods, on both client and server (otel_client_call_tracer.cc, otel_server_call_tracer.cc); spec says: C++ behavior (predicate on both sides, generic methods only). -->

### 9.6 Target Attribute

`grpc.target` is the channel's **canonical target URI**. If the application
omitted the scheme, the canonical form includes the scheme that was applied:
`scheme://[authority]/path`, for example `dns:///pubsub.googleapis.com:443` or
`xds:///helloworld-gke:8000`. See [Channel](../04-client-channel/channel.md).
For channels that have no target URI, such as in-process channels, the
implementation MUST synthesize a target URI.

### 9.7 Channel Scope

The plugin MUST support a channel scope predicate ([Channel Scoping](#32-channel-scoping)) and per-channel and
per-server registration.

### 9.8 Tracing Configuration

The plugin MUST accept:

- a **TracerProvider**. If none is set, the plugin produces no traces.
- a **TextMapPropagator**, possibly a composite of several, used to inject and
  extract trace context in metadata. Client and server MAY be configured with
  different propagators.

See [Tracing](tracing.md).

## 10. API Requirements

- gRPC MUST provide an instrument registry API through which gRPC components
  register instruments with all descriptor fields in [Instrument Descriptor](#21-instrument-descriptor), and through which
  stats plugins enumerate descriptors. Exposing this API to third-party
  plugins is RECOMMENDED. It MAY be marked experimental.
- gRPC MUST provide an API to register a stats plugin globally, and APIs to
  register stats plugins on an individual channel and on an individual server.
- The stats plugin interface MUST support: an applicability decision for a
  channel given `ChannelScope` (target and authority) and for a server; adding
  to counters and up-down counters; recording histograms; and adding and
  removing gauge callbacks.
- The LB policy helper and the resolver creation arguments MUST give access to
  the channel's stats plugin group (a "metrics recorder") for recording
  non-per-call metrics and registering gauge callbacks.
- The OpenTelemetry plugin API MUST provide: setting a MeterProvider, setting a
  TracerProvider, setting a TextMapPropagator, adding optional label keys,
  enabling metrics, disabling metrics, disabling all metrics, setting a channel
  scope predicate, setting a generic method attribute predicate, and registering the
  plugin globally, on a channel, or on a server.
