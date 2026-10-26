> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# Appendix G. Glossary

<!-- Sources: all sections of doc/spec (definitions as introduced in each section) -->

This glossary collects the terms that have a specific meaning in this
specification. Each entry gives a short definition and links to the section
that defines the term normatively. If a definition here differs from the
linked section, the linked section wins. Terms are in alphabetical order,
ignoring case and punctuation.

## A

**ACK / NACK** — In ADS, a client request that accepts (ACK) or rejects
(NACK) a response for a resource type. The request carries the response's
nonce, and for a NACK, an error detail. gRPC NACKs per resource and still
uses the valid resources in a response. See
[XdsClient](../09-xds/xds-client.md) ([Version, nonce, ACK, and NACK](../09-xds/xds-client.md#44-version-nonce-ack-and-nack)).

**ADS (Aggregated Discovery Service)** — The xDS transport service
(`envoy.service.discovery.v3.AggregatedDiscoveryService`) that carries all
resource types on one bidirectional stream per xDS server. gRPC uses its
state-of-the-world variant. See [xDS](../09-xds/README.md) ([Transport protocol variant](../09-xds/README.md#21-transport-protocol-variant)) and
[XdsClient](../09-xds/xds-client.md) ([XdsClient: ADS Stream](../09-xds/xds-client.md#4-ads-stream)).

**Address** — A network address that a subchannel can connect to, such as an
IP address and port, or a Unix domain socket path. An endpoint has one or more
addresses. See [Load Balancing](../04-client-channel/load-balancing.md) ([Load Balancing: Resolver Updates: Endpoints, Addresses, and Attributes](../04-client-channel/load-balancing.md#3-resolver-updates-endpoints-addresses-and-attributes)).

**Admin interface** — A single API that registers the standard admin
services (channelz and CSDS) on a server. See
[Admin Interface](../07-services/admin.md).

**Aggregate cluster** — An xDS cluster whose endpoints come from an ordered
list of other clusters. Each underlying cluster becomes one priority. See
[Cluster](../09-xds/resources/cluster.md) ([Aggregate Clusters](../09-xds/resources/cluster.md#13-aggregate-clusters)) and
[Client Data Plane](../09-xds/client.md) ([Aggregate cluster graph](../09-xds/client.md#23-aggregate-cluster-graph)).

**Ambient error** — An error reported to an xDS watcher that does not change
the watcher's use of a resource it already has. Examples are losing contact
with the xDS server, or a NACK of an update to a cached resource. It is
delivered through `OnAmbientError`. Contrast with *resource error*. See
[XdsClient](../09-xds/xds-client.md) ([XdsClient: Watcher API](../09-xds/xds-client.md#5-watcher-api), [XdsClient: Error Handling](../09-xds/xds-client.md#7-error-handling)).

**API Requirements** — The subsection of each section that states what
gRPC's public API (or an internal plugin API) MUST let applications do,
in abstract form. See [Introduction and Conventions](../00-introduction/README.md) ([Introduction and Conventions: API Requirements](../00-introduction/README.md#5-api-requirements)).

**Attempt (call attempt)** — One transmission of a call to a server on one
transport stream. A call has one or more attempts: retries, hedging, and
transparent retries each create a new attempt. See
[Retries and Hedging](../04-client-channel/retries.md) and
[Instrumentation Architecture](../08-observability/instrumentation.md) ([Instrumentation Architecture: Concepts](../08-observability/instrumentation.md#1-concepts)).

**Audit logger** — A pluggable component that records authorization
decisions. It is configured by name and config in the gRPC authorization
policy or in xDS RBAC. The built-in logger is `stdout_logger`. See
[Authorization](../06-security/authorization.md) ([Authorization: Audit Logging](../06-security/authorization.md#3-audit-logging)).

**AuthContext** — A per-connection, read-only record of what the security
handshake learned about the peer. It holds auth properties and a peer
identity property name, and is available to every RPC on the connection. See
[Security](../06-security/README.md) ([Security: AuthContext and Peer Identity](../06-security/README.md#6-authcontext-and-peer-identity)).

**Authority** — The name by which the client identifies the service for a
call (`host` or `host:port`). It is sent as `:authority`, used for virtual
hosting, and checked against the server certificate. Each channel has a
*default authority*, normally derived from the target URI by the resolver.
It can be overridden per channel or per call, or by an LB policy (see
*authority rewriting*). See [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Authority](../02-rpc-semantics/README.md#9-authority)),
[Channel](../04-client-channel/channel.md) ([Channel: Authority](../04-client-channel/channel.md#3-authority)), and
[Security](../06-security/README.md) ([Security: Authority and Authority Override](../06-security/README.md#7-authority-and-authority-override)).

**Authority (xDS)** — The authority component of an `xdstp:` resource name.
It selects an entry in the bootstrap `authorities` map, which gives the xDS
servers for that authority. Old-style names use the top-level `xds_servers`.
See [XdsClient](../09-xds/xds-client.md) ([XdsClient: Resource Names](../09-xds/xds-client.md#3-resource-names)) and
[Bootstrap](../09-xds/bootstrap.md) ([Authority Object](../09-xds/bootstrap.md#43-authority-object)).

**Authority rewriting** — Replacing the authority of an RPC with a value
chosen by xDS (`auto_host_rewrite`). It is honored only for routes from
xDS servers marked `trusted_xds_server`. See
[Client Data Plane](../09-xds/client.md) ([Authority rewriting](../09-xds/client.md#59-authority-rewriting)) and
[xDS LB Policies](../09-xds/lb-policies.md) ([Authority rewriting](../09-xds/lb-policies/xds_cluster_impl.md#5-authority-rewriting)).

**Authorization policy (gRPC authorization policy)** — A JSON policy of
allow and deny rules, evaluated on the server for each RPC by the RBAC
engine. See [Authorization](../06-security/authorization.md) ([Authorization: gRPC Authorization Policy](../06-security/authorization.md#2-grpc-authorization-policy)).

## B

**Backend metrics** — Load and utilization data that a server reports to
clients through ORCA, either per request or out of band. See
[Backend Metrics (ORCA)](../07-services/orca.md) and
[Client-Side Backend Metrics (ORCA)](../04-client-channel/backend-metrics.md).

**Binary logging** — Structured logging of RPC headers, messages, and
trailers in the `GrpcLogEntry` format, selected by a filter configuration
string. See [Binary Logging](../08-observability/binary-logging.md).

**Binary metadata** — Metadata whose key ends in `-bin`. The value is
arbitrary bytes. It is base64-encoded on HTTP/2 unless true binary metadata
is negotiated. See [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Metadata](../02-rpc-semantics/README.md#7-metadata)) and
[True Binary Metadata](../03-wire-protocol/true-binary-metadata.md).

**Bootstrap configuration** — The local JSON configuration that tells gRPC's
xDS support which xDS servers to use, how to identify itself (`node`), the
authorities, the certificate provider instances, and the server features. See
[Bootstrap](../09-xds/bootstrap.md).

## C

**Call (RPC)** — One invocation of a method, from when the application
starts it until its final status is delivered. See
[Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Calls](../02-rpc-semantics/README.md#3-calls)).

**Call attributes** — Values that the ConfigSelector attaches to an RPC and
that the channel passes to the picker with every pick for that RPC. An
example is the cluster chosen by xDS routing. See
[Per-call Configuration and Call Flow](../04-client-channel/call-dispatch.md) ([Inputs and Outputs](../04-client-channel/call-dispatch.md#21-inputs-and-outputs)) and
[Client Data Plane](../09-xds/client.md) ([Call attributes](../09-xds/client.md#53-call-attributes)).

**Call credentials** — Credentials that add per-call security metadata
(for example, `authorization: Bearer …`) after a connection has been
chosen. They are sent only on connections whose security level is high
enough. See [Call Credentials](../06-security/call-credentials.md).

**Call tracer / call-attempt tracer / server call tracer** — The per-call,
per-attempt, and per-server-call observers through which instrumentation
plugins record metrics and traces. See
[Instrumentation Architecture](../08-observability/instrumentation.md).

**CDS (Cluster Discovery Service)** — The xDS resource type
`envoy.config.cluster.v3.Cluster`, and its discovery. See
[Cluster](../09-xds/resources/cluster.md).

**Channel** — A client-side virtual connection to a target, over which the
application starts RPCs. It owns a resolver, an LB policy, and subchannels.
See [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Channels and Servers](../02-rpc-semantics/README.md#1-channels-and-servers)) and
[Channel](../04-client-channel/channel.md).

**Channel credentials** — Credentials that secure the connections of a
channel (for example, TLS or insecure) and that set the connection's
security level. See [Security](../06-security/README.md).

**Channelz** — A service and data model that exposes runtime information
about channels, subchannels, servers, and sockets, including channel traces.
See [Channelz](../08-observability/channelz.md).

**Client feature (xDS)** — A string the client advertises in
`Node.client_features` to tell the control plane what it supports (for
example, `envoy.lb.does_not_support_overprovisioning`). See
[XdsClient](../09-xds/xds-client.md).

**Cluster** — In xDS, a named group of endpoints together with LB policy,
circuit breaking, outlier detection, and security settings. Its type is EDS,
LOGICAL_DNS, or aggregate. See [Cluster](../09-xds/resources/cluster.md).

**Cluster specifier plugin** — An xDS extension, defined in
`RouteConfiguration.cluster_specifier_plugins` and named by a route, that
chooses the cluster for each RPC at run time by producing an LB policy
config. gRPC provides one plugin, for RLS. See
[RouteConfiguration](../09-xds/resources/route-configuration.md) ([Cluster Specifier Plugins](../09-xds/resources/route-configuration.md#52-cluster-specifier-plugins)).

**Codec** — The component that serializes and deserializes messages for a
content-subtype (for example, `proto`). See
[Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Codecs and Content-Subtype](../02-rpc-semantics/README.md#17-codecs-and-content-subtype)).

**Committed** — The state of an RPC once the client has chosen the single
attempt whose outcome goes to the application. No more attempts, configured
or transparent, are started after that. Receiving response headers commits
the RPC. The ConfigSelector's on-commit callback runs at this point. See
[Retries and Hedging](../04-client-channel/retries.md) ([Retries and Hedging: Commit and Buffering](../04-client-channel/retries.md#7-commit-and-buffering)) and
[Per-call Configuration and Call Flow](../04-client-channel/call-dispatch.md) ([Inputs and Outputs](../04-client-channel/call-dispatch.md#21-inputs-and-outputs)).

**ConfigSelector** — An internal component, supplied by the resolver, that
runs once per RPC. It returns the RPC's method config, call attributes,
per-call interceptors, and an optional on-commit callback, or a status that
fails the RPC. The xDS resolver supplies the *xDS ConfigSelector*, which
performs xDS routing. See [Per-call Configuration and Call Flow](../04-client-channel/call-dispatch.md) ([Per-call Configuration and Call Flow: ConfigSelector](../04-client-channel/call-dispatch.md#2-configselector)) and
[Client Data Plane](../09-xds/client.md) ([Client Data Plane: xDS ConfigSelector](../09-xds/client.md#5-xds-configselector)).

**Connectivity state** — One of IDLE, CONNECTING, READY,
TRANSIENT_FAILURE, or SHUTDOWN. It is reported by channels, subchannels, and
LB policies. See [Channel](../04-client-channel/channel.md) ([Channel: Connectivity State](../04-client-channel/channel.md#4-connectivity-state)) and
[Subchannels and Connections](../04-client-channel/subchannels.md) ([Subchannels and Connections: Connectivity States](../04-client-channel/subchannels.md#2-connectivity-states)).

**Control plane / data plane** — Inside a client, the control plane is the
set of components that decide where and how RPCs are sent (resolvers, the
service config, LB policies). The data plane is the processing of individual
RPCs. In xDS deployments, "control plane" also means the remote xDS
management server. See [Introduction and Conventions](../00-introduction/README.md) ([Introduction and Conventions: Terminology](../00-introduction/README.md#8-terminology)).

**CSDS (Client Status Discovery Service)** — A service
(`envoy.service.status.v3.ClientStatusDiscoveryService`) that exposes the
xDS resources cached by a process's XdsClients, and their status. See
[CSDS](../09-xds/csds.md).

## D

**Data error** — An xDS error that concerns the content of a resource: a
NACK, the deletion of an LDS or CDS resource, or a server-reported resource
error with status NOT_FOUND or PERMISSION_DENIED. It discards a cached
resource only if the server has the `fail_on_data_errors` feature. Contrast
with *transient error*. See [XdsClient](../09-xds/xds-client.md) ([Error categories](../09-xds/xds-client.md#71-error-categories)).

**Deadline** — The absolute time by which a call must complete. It is sent
as the relative `grpc-timeout`, and is enforced by both the client and the
server. See [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Deadlines](../02-rpc-semantics/README.md#8-deadlines)).

**Does-not-exist timer** — A timer started when the XdsClient requests a
resource that it does not have cached. If the resource has not arrived when the timer fires, the
resource is treated as nonexistent (or, with
`resource_timer_is_transient_error`, as unavailable). See
[XdsClient](../09-xds/xds-client.md) ([Does-not-exist timer](../09-xds/xds-client.md#74-does-not-exist-timer)).

**Drop** — A pick result that fails an RPC immediately, with no retry of any
kind, for example because of xDS drop overloads or circuit breaking. See
[Load Balancing](../04-client-channel/load-balancing.md) ([Pick Results](../04-client-channel/load-balancing.md#62-pick-results)) and
[Retries and Hedging](../04-client-channel/retries.md) ([Retries and Hedging: Transparent Retries](../04-client-channel/retries.md#8-transparent-retries)).

## E

**EDS (Endpoint Discovery Service)** — The xDS resource type
`envoy.config.endpoint.v3.ClusterLoadAssignment`, which gives a cluster's
endpoints by priority and locality. See
[ClusterLoadAssignment and LbEndpointCollection](../09-xds/resources/endpoint.md).

**Endpoint** — A logical backend server, identified by an ordered list of
one or more addresses (for example, its IPv4 and IPv6 addresses) and carrying
per-endpoint attributes. LB policies balance load across endpoints. See
[Load Balancing](../04-client-channel/load-balancing.md) ([Load Balancing: Resolver Updates: Endpoints, Addresses, and Attributes](../04-client-channel/load-balancing.md#3-resolver-updates-endpoints-addresses-and-attributes)).

**Experimental** — Marks a feature whose configuration, API, metric names,
or wire details may change incompatibly. It is shown by an
`> **Experimental:**` line, for example on LB policies whose registered names
end in `_experimental`. See [Introduction and Conventions](../00-introduction/README.md) ([Introduction and Conventions: Experimental Features](../00-introduction/README.md#4-experimental-features)).

## F

**Fallback (xDS)** — Switching to a lower-priority xDS server in the
bootstrap list when the higher-priority server is unreachable, and switching
back when it recovers. See [XdsClient](../09-xds/xds-client.md) ([XdsClient: Fallback](../09-xds/xds-client.md#8-fallback)).

**Full method name** — `/<service>/<method>`, carried in `:path`. For
Protocol Buffers, the service part is the fully qualified service name. See
[Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Services and Full Method Names](../02-rpc-semantics/README.md#22-services-and-full-method-names)).

## H

**Half-close** — The client signaling that it will send no more request
messages (end of the request stream). See
[Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Calls](../02-rpc-semantics/README.md#3-calls)).

**Happy Eyeballs** — The connection algorithm of `pick_first`. Addresses
(with address families interleaved) are tried in order. A new attempt starts
whenever the Connection Attempt Delay passes without the current attempt
completing, and the first connection to succeed is selected. See
[`pick_first`](../04-client-channel/lb-policies/pick_first.md).

**Health state watch** — A subchannel watch through which `pick_first`, under
a petiole policy, learns the subchannel's health (from client-side health
checking or outlier detection) in addition to its connectivity state. See
[Load Balancing](../04-client-channel/load-balancing.md) ([Load Balancing: Generic Health Reporting](../04-client-channel/load-balancing.md#10-generic-health-reporting)) and
[Client-Side Health Checking](../04-client-channel/health-checking.md).

**Hedging** — Sending several attempts of a call in parallel, staggered by a
delay, and using the first successful result. Configured by
`hedgingPolicy`. See [Retries and Hedging](../04-client-channel/retries.md) ([Retries and Hedging: Hedging Policy](../04-client-channel/retries.md#3-hedging-policy)).

**Helper** — The interface through which the channel (or a parent policy)
gives an LB policy the ability to create subchannels, update its state and
picker, and request re-resolution. See
[Load Balancing](../04-client-channel/load-balancing.md) ([Load Balancing: Helper API](../04-client-channel/load-balancing.md#5-helper-api)).

## I

**Idle timeout** — The time after which a channel with no RPCs in progress
returns to IDLE and releases its resolver, LB policy, and connections. See
[Channel](../04-client-channel/channel.md) ([Channel: Idle Timeout](../04-client-channel/channel.md#6-idle-timeout)).

**Interceptor** — Application- or gRPC-provided code that can observe and
modify a call's metadata, messages, and status on the client or server. The
xDS ConfigSelector applies xDS HTTP filter behavior through per-call
interceptors. See [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Interceptors](../02-rpc-semantics/README.md#16-interceptors)).

## L

**LDS (Listener Discovery Service)** — The xDS resource type
`envoy.config.listener.v3.Listener`. It is an API listener on clients and a
socket listener on xDS-enabled servers. See
[Listener](../09-xds/resources/listener.md) and
[xDS-Enabled Servers](../09-xds/server.md).

**LB policy (load balancing policy)** — A pluggable component that receives
endpoints from the resolver, manages subchannels (directly or through child
policies), aggregates connectivity state, and provides a picker. Policies are
*leaf*, *parent*, or *petiole* policies. See
[Load Balancing](../04-client-channel/load-balancing.md).

**LEDS / LbEndpointCollection** — A resource
(`envoy.config.endpoint.v3.LbEndpointCollection`) that holds a locality's
endpoints separately from its EDS resource, possibly from another authority.
gRPC supports list collections only. See
[ClusterLoadAssignment and LbEndpointCollection](../09-xds/resources/endpoint.md) ([LbEndpointCollection (LEDS List Collections)](../09-xds/resources/endpoint.md#7-lbendpointcollection-leds-list-collections)).

**Locality** — A region, zone, and sub-zone grouping of endpoints in EDS.
Localities are weighted within a priority. See
[ClusterLoadAssignment and LbEndpointCollection](../09-xds/resources/endpoint.md) ([LocalityLbEndpoints](../09-xds/resources/endpoint.md#2-localitylbendpoints)).

**LOGICAL_DNS cluster** — An xDS cluster whose single endpoint is found by
resolving a DNS name in the client. See
[Cluster](../09-xds/resources/cluster.md) ([Logical DNS Clusters](../09-xds/resources/cluster.md#12-logical-dns-clusters)) and
[Client Data Plane](../09-xds/client.md) ([LOGICAL_DNS clusters](../09-xds/client.md#24-logical_dns-clusters)).

**LRS (Load Reporting Service)** — The xDS service
(`envoy.service.load_stats.v3.LoadReportingService`) through which the client
reports per-cluster and per-locality request counts, drops, and backend
metrics. See [Load Reporting (LRS)](../09-xds/load-reporting.md).

## M

**Metadata** — Key/value pairs sent with request headers, response headers,
or trailers. Keys are case-insensitive ASCII. Keys ending in `-bin` carry
binary values. Keys starting with `grpc-` are reserved. See
[Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Metadata](../02-rpc-semantics/README.md#7-metadata)) and
[Appendix A](a-metadata-keys.md).

**Method config** — The per-method settings from the service config (or
from the ConfigSelector): timeout, `waitForReady`, message size limits, and
retry or hedging policy. See
[Service Config](../04-client-channel/service-config.md) ([Service Config: Method Config Selection](../04-client-channel/service-config.md#4-method-config-selection), [`methodConfig`](../04-client-channel/service-config.md#54-methodconfig)).

## O

**ORCA (Open Request Cost Aggregation)** — The backend metrics protocol.
Servers report `OrcaLoadReport`s per request in the
`endpoint-load-metrics-bin` trailer, or out of band through
`OpenRcaService`. Clients use them for load balancing (for example,
`weighted_round_robin`) and for LRS. See
[Backend Metrics (ORCA)](../07-services/orca.md).

**Outlier detection** — Temporarily ejecting endpoints whose success rate
or failure percentage is abnormal. It is implemented by the
`outlier_detection` policy through the health state watch. See
[`outlier_detection`](../04-client-channel/lb-policies/outlier_detection.md).

## P

**Petiole policy** — An LB policy that balances across endpoints by
creating one `pick_first` child per endpoint and delegating each pick to the
chosen endpoint's child. Examples are `round_robin`,
`weighted_round_robin`, `least_request`, and `ring_hash`. A *leaf policy*
manages subchannels directly. `pick_first` is the universal leaf policy. A
*parent policy* delegates to one or more child policies. See
[Load Balancing](../04-client-channel/load-balancing.md) ([Leaf, Parent, and Petiole Policies](../04-client-channel/load-balancing.md#91-leaf-parent-and-petiole-policies)).

**Picker** — An immutable object, produced by an LB policy, that decides
each pick. The result is Complete (use this subchannel), Queue, Fail, or
Drop. See [Load Balancing](../04-client-channel/load-balancing.md) ([Load Balancing: Picker API](../04-client-channel/load-balancing.md#6-picker-api)).

**Priority (xDS)** — An ordered failover level of localities in EDS, or of
underlying clusters in an aggregate cluster. It is implemented by the
`priority` LB policy. See
[`priority`](../04-client-channel/lb-policies/priority.md).

**Propagator** — A tracing component that injects and extracts span context
in metadata (for example, the `grpc-trace-bin` propagator). See
[Tracing](../08-observability/tracing.md) ([Tracing: Context Propagation](../08-observability/tracing.md#6-context-propagation)).

**Proxy mapper** — The component that decides whether a channel connects
through an HTTP CONNECT proxy, and what it resolves. See
[HTTP CONNECT Proxy Support](../04-client-channel/proxy.md).

## R

**RBAC engine** — The server-side authorization engine that evaluates
allow and deny policies over request attributes. It is used both by the
gRPC authorization policy and by the xDS RBAC HTTP filter. See
[Authorization](../06-security/authorization.md) ([Authorization: RBAC Engine](../06-security/authorization.md#1-rbac-engine)).

**RDS (Route Discovery Service)** — The xDS resource type
`envoy.config.route.v3.RouteConfiguration`, which holds virtual hosts and
routes. See [RouteConfiguration](../09-xds/resources/route-configuration.md).

**Re-resolution** — An LB policy asking the resolver to resolve the target
again, for example after a connection failure. See
[Name Resolution](../04-client-channel/name-resolution.md) ([Re-resolution Requests](../04-client-channel/name-resolution.md#41-re-resolution-requests)).

**Resolution note** — A human-readable string in a resolver update that
gives context (for example, xDS errors being tolerated). It is included in
RPC failure messages. See [Name Resolution](../04-client-channel/name-resolution.md) and
[Load Balancing](../04-client-channel/load-balancing.md) ([Load Balancing: Resolver Updates: Endpoints, Addresses, and Attributes](../04-client-channel/load-balancing.md#3-resolver-updates-endpoints-addresses-and-attributes)).

**Resolver (name resolver)** — A pluggable component, selected by the
target URI scheme, that produces endpoints, a service config, attributes,
and optionally a ConfigSelector for a channel. See
[Name Resolution](../04-client-channel/name-resolution.md).

**Resource (xDS)** — A named, typed configuration object (Listener,
RouteConfiguration, Cluster, ClusterLoadAssignment, or LbEndpointCollection)
that the XdsClient fetches, validates, and caches. Resource names are either
old-style (opaque strings) or new-style (`xdstp:` URIs). See
[XdsClient](../09-xds/xds-client.md) ([XdsClient: Resource Names](../09-xds/xds-client.md#3-resource-names), [XdsClient: Cache](../09-xds/xds-client.md#6-cache)) and the resource sections
under 9.3.

**Resource error (xDS)** — An error delivered through
`OnResourceChanged(error)`, after which the watcher MUST stop using any
resource it has. Contrast with *ambient error*. See
[XdsClient](../09-xds/xds-client.md) ([XdsClient: Watcher API](../09-xds/xds-client.md#5-watcher-api)).

**RLS (Route Lookup Service)** — An external lookup server that the
[`rls`](../04-client-channel/lb-policies/rls.md) LB policy asks, through
the `grpc.lookup.v1.RouteLookupService/RouteLookup` RPC, which target an RPC
should go to, based on a key built from the RPC's method and headers. With
xDS, RLS is configured through the RLS cluster specifier plugin, and its
targets are cluster names. See [`rls`](../04-client-channel/lb-policies/rls.md).

**Retry throttling** — A per-channel token bucket that disables retries and
hedging when too many RPCs fail. See
[Retries and Hedging](../04-client-channel/retries.md) ([Retries and Hedging: Retry Throttling](../04-client-channel/retries.md#4-retry-throttling)).

## S

**Security level** — The protection a connection provides: `NONE`,
`INTEGRITY_ONLY`, or `PRIVACY_AND_INTEGRITY`. It is set by the channel
credentials. Call credentials declare a minimum level they need. See
[Security](../06-security/README.md) ([Security: Security Levels](../06-security/README.md#5-security-levels)).

**Server** — The component that listens for connections and dispatches
incoming RPCs to registered handlers. See [Server](../05-server/README.md).

**Server feature (xDS)** — A string in a bootstrap XdsServer's
`server_features` that changes how gRPC treats that server (for example,
`fail_on_data_errors` or `trusted_xds_server`). See
[Bootstrap](../09-xds/bootstrap.md) ([Bootstrap: Server Features](../09-xds/bootstrap.md#5-server-features)).

**Service config** — Per-target client configuration (JSON) that sets the
LB policy, method configs, retry throttling, health checking, and connection
scaling. It is supplied by the resolver or by the application as a default.
See [Service Config](../04-client-channel/service-config.md).

**Serving state** — Whether an xDS-enabled server's listening address is
*serving* or *not serving*, depending on whether it has a valid Listener.
See [xDS-Enabled Servers](../09-xds/server.md) ([xDS-Enabled Servers: Serving State](../09-xds/server.md#2-serving-state)).

**SNI / SAN** — Server Name Indication, the name the client sends in the TLS
handshake, and Subject Alternative Names, the identities in a certificate
that are checked against the expected name. See
[TLS](../06-security/tls.md) and
[xDS Security](../09-xds/security.md).

**SPIFFE trust bundle map** — A JSON map from SPIFFE trust domain to root
certificates. Peers with SPIFFE IDs are verified against the roots of their
own trust domain. See [TLS](../06-security/tls.md) ([TLS: SPIFFE Trust Bundle Map Verification](../06-security/tls.md#10-spiffe-trust-bundle-map-verification)).

**Stateful session affinity** — xDS-configured, cookie-based stickiness that
routes a session's RPCs to the same endpoint and cluster. See
[xDS HTTP Filters](../09-xds/http-filters.md) ([xDS HTTP Filters: Stateful Session Affinity](../09-xds/http-filters.md#10-stateful-session-affinity)) and
[xDS LB Policies](../09-xds/lb-policies.md) ([`xds_override_host`](../09-xds/lb-policies/xds_override_host.md)).

**Subchannel** — The channel's representation of one address (or the
connections to it), created by an LB policy. It has its own connectivity
state and connection backoff, and it may hold several connections when
connection scaling is enabled. See
[Subchannels and Connections](../04-client-channel/subchannels.md).

## T

**Target (target URI)** — The string an application gives when it creates a
channel. Its scheme selects the resolver (for example, `dns:///host:port` or
`xds:///service`). See [Channel](../04-client-channel/channel.md) ([Channel: Target URI Parsing](../04-client-channel/channel.md#2-target-uri-parsing)).

**Trailers-Only** — A response consisting of a single header block that
carries the status, with no response headers and no messages. It leaves the
RPC uncommitted, so it can still be retried. See
[gRPC over HTTP/2](../03-wire-protocol/http2.md) ([gRPC over HTTP/2: Responses](../03-wire-protocol/http2.md#6-responses)) and
[Server](../05-server/README.md) ([Server: Trailers-Only Responses](../05-server/README.md#32-trailers-only-responses)).

**Transient error (xDS)** — A connectivity problem with the xDS server: the
xDS channel in TRANSIENT_FAILURE, an ADS stream that ended without a
response, or a server-reported error other than NOT_FOUND or
PERMISSION_DENIED. It never discards a cached resource. See
[XdsClient](../09-xds/xds-client.md) ([Error categories](../09-xds/xds-client.md#71-error-categories)).

**Transparent retry** — A retry that gRPC performs without a retry policy,
when an attempt provably did not reach the server application. It is
unlimited when nothing reached the network, and allowed once when the
attempt reached the server's gRPC library but not the application. See
[Retries and Hedging](../04-client-channel/retries.md) ([Retries and Hedging: Transparent Retries](../04-client-channel/retries.md#8-transparent-retries)).

## W

**Wait-for-ready** — A per-call property. When it is set, a call waits
through TRANSIENT_FAILURE (until its deadline) instead of failing
immediately on connectivity failures. When it is not set ("fail fast"), such
a call fails right away. See [Core RPC Semantics](../02-rpc-semantics/README.md) ([Core RPC Semantics: Wait-for-Ready](../02-rpc-semantics/README.md#14-wait-for-ready)) and
[Channel](../04-client-channel/channel.md) ([Channel: wait_for_ready](../04-client-channel/channel.md#8-wait_for_ready)).

## X

**xDS** — The family of discovery APIs (from the Envoy project) through
which a control plane configures gRPC clients and servers: listeners,
routes, clusters, endpoints, security, and load reporting. See
[xDS](../09-xds/README.md).

**XdsChannelCredentials / XdsServerCredentials** — Channel and server
credentials that use the security configuration delivered through xDS, with
fallback credentials for when xDS supplies none. See
[xDS Security](../09-xds/security.md) ([xDS Security: XdsChannelCredentials and XdsServerCredentials](../09-xds/security.md#1-xdschannelcredentials-and-xdsservercredentials)).

**XdsClient** — The shared component that talks to xDS servers. It manages
ADS streams, watches, caching, error handling, and fallback for one
bootstrap configuration. See [XdsClient](../09-xds/xds-client.md).

**XdsConfig** — The resolver attribute that holds a complete, consistent
snapshot of the xDS resources a channel needs: the Listener, the
RouteConfiguration, and, for each cluster, its Cluster and endpoints. It is
built by the XdsDependencyManager. See [Client Data Plane](../09-xds/client.md) ([Client Data Plane: XdsConfig](../09-xds/client.md#3-xdsconfig)).

**XdsDependencyManager** — The component of the `xds` resolver that watches
all resources reachable from the Listener, and delivers an `XdsConfig` only
when they are all available, avoiding configuration tears. See
[Client Data Plane](../09-xds/client.md) ([Client Data Plane: XdsDependencyManager](../09-xds/client.md#2-xdsdependencymanager)).

**xDS-enabled server** — A gRPC server that gets its listener configuration
(filter chains, security, routing, and xDS HTTP filters) from xDS. See
[xDS-Enabled Servers](../09-xds/server.md).

**xDS HTTP filter** — An xDS API concept: an entry in
`HttpConnectionManager.http_filters` (such as router, fault injection, RBAC,
stateful session, or GCP authentication) with optional per-route overrides.
gRPC applies each filter's behavior per RPC, for example through
interceptors. This specification does not prescribe how. See
[xDS HTTP Filters](../09-xds/http-filters.md).

**`xds` resolver** — The resolver for `xds:` targets. It uses an XdsClient to
obtain the Listener and the resources it depends on, and produces the
XdsConfig, the generated service config, and the xDS ConfigSelector. See
[Client Data Plane](../09-xds/client.md) ([Client Data Plane: The `xds` Resolver](../09-xds/client.md#1-the-xds-resolver)).

**xdstp** — The URI scheme of new-style xDS resource names:
`xdstp://[<authority>]/<resource type>/<id>[?<context params>]`. See
[XdsClient](../09-xds/xds-client.md) ([Old-style and new-style names](../09-xds/xds-client.md#31-old-style-and-new-style-names)).
