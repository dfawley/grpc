# xDS HTTP Filters

<!-- Sources: A39, A33, A41, A59, A55, A60, A61, A75, A83, A36, doc/http-grpc-status-mapping.md -->

This section specifies how gRPC supports the xDS concept of *HTTP filters*:
the ordered list of request-processing stages configured in the xDS
`HttpConnectionManager` (HCM). The term "xDS HTTP filter" is used here only
as the name of this xDS API concept. gRPC applies the behavior of each
configured xDS HTTP filter to each RPC: on the client, after name resolution
and route selection and before the load-balancing pick; on the server, after
route selection and before the RPC is dispatched to the application handler.
This specification does not prescribe the mechanism used to apply the behavior
(for example, interceptors or any other implementation-internal construct).

Related sections:

- Listener and HCM validation: [resources/listener.md](resources/listener.md).
- RouteConfiguration validation and routing: [resources/route-configuration.md](resources/route-configuration.md)
  and [client.md](client.md).
- Per-call configuration on the client (the ConfigSelector):
  [../04-client-channel/call-dispatch.md](../04-client-channel/call-dispatch.md).
- xDS-enabled servers: [server.md](server.md).

## 1. Model

An xDS HTTP filter *instance* is one entry of `HttpConnectionManager.http_filters`.
Each instance has:

- an **instance name** (`HttpFilter.name`), unique within the HCM;
- a **filter type**, identified by the protobuf message type of its
  configuration;
- a **top-level configuration** (from `HttpFilter.typed_config`); and
- zero or more **override configurations** (from `typed_per_filter_config` in
  `VirtualHost`, `Route`, and `WeightedCluster.ClusterWeight`), keyed by
  instance name.

The same filter type MAY appear multiple times in one HCM, each instance with
its own name and configuration (e.g., two RBAC instances). Overrides are
addressed by instance name, so each instance can be overridden independently.

gRPC does not provide any mechanism for an xDS HTTP filter to request that the
route be recomputed after it modifies the request.

gRPC supports xDS HTTP filters only with the xDS v3 API.

## 2. Filter Registry

gRPC maintains a registry of supported xDS HTTP filter types. Each entry is
registered under one or more protobuf message type names: every filter type
has a message type for its top-level configuration, and a filter type that
supports overrides also has a message type for its override configuration,
which may or may not be the same type as the top-level configuration.

Each registered filter type provides:

| Property | Description |
|---|---|
| Config message types | Top-level config type; optional override config type. |
| Validation | Validation of top-level and override configuration protos when an xDS resource is parsed. A validation failure NACKs the containing resource. |
| Client support | Whether the filter type may be used on gRPC clients (in an HCM inside a Listener `api_listener`). |
| Server support | Whether the filter type may be used on gRPC servers (in an HCM inside a TCP Listener's filter chain). |
| Terminal | Whether the filter type is terminal, i.e., MUST be the last entry in `http_filters`. |
| Data-plane behavior | The per-RPC behavior to apply, given the effective configuration ([Applying xDS HTTP Filters to RPCs](#5-applying-xds-http-filters-to-rpcs)). |

Because client and server behaviors are inverses of each other (e.g., client
fault injection acts on outgoing requests whereas a server-side equivalent
would act on incoming ones), support on the client and server sides is
independent: a filter type supported on the client is not implied to be
supported on the server, or vice versa. Effectively there are two registries:

- The **client registry** is consulted when the HCM is inside an HTTP API
  Listener (`Listener.api_listener`).
- The **server registry** is consulted when the HCM is inside a TCP Listener
  (a Listener with `address` and `filter_chains`).

The following filter types are currently registered:

| Filter type | Top-level config type | Override config type | Client | Server | Terminal | Section |
|---|---|---|---|---|---|---|
| Router | `envoy.extensions.filters.http.router.v3.Router` | — | yes | yes | yes | [Router](#7-router) |
| Fault injection | `envoy.extensions.filters.http.fault.v3.HTTPFault` | `envoy.extensions.filters.http.fault.v3.HTTPFault` | yes | no | no | [Fault Injection](#8-fault-injection) |
| RBAC | `envoy.extensions.filters.http.rbac.v3.RBAC` | `envoy.extensions.filters.http.rbac.v3.RBACPerRoute` | no | yes | no | [RBAC](#9-rbac) |
| Stateful session | `envoy.extensions.filters.http.stateful_session.v3.StatefulSession` | `envoy.extensions.filters.http.stateful_session.v3.StatefulSessionPerRoute` | yes | no | no | [Stateful Session Affinity](#10-stateful-session-affinity) |
| GCP authentication | `envoy.extensions.filters.http.gcp_authn.v3.GcpAuthnFilterConfig` | — (see [Configuration Validation](#111-configuration-validation)) | yes | no | no | [GCP Authentication](#11-gcp-authentication) |

The router is the only terminal filter type. Implementations MAY hard-code
the requirement that the router is the last filter instead of implementing a
general "terminal" property.

### 2.1 Extracting the Filter Type

Wherever a `google.protobuf.Any` carries an xDS HTTP filter configuration, the
filter type is determined as follows:

1. The type is the message name obtained from the `Any.type_url` (the portion
   after the last `/`). An empty or malformed `type_url` NACKs the resource.
2. If the type is `udpa.type.v1.TypedStruct` or `xds.type.v3.TypedStruct`, the
   actual type is taken from the `TypedStruct.type_url` field (same
   extraction rule), and the configuration is the `TypedStruct.value`
   (`google.protobuf.Struct`, treated as a JSON object; absent means an empty
   object). This allows third-party configurations to be expressed without a
   concrete proto message type.
3. For override configurations only: if the type is
   `envoy.config.route.v3.FilterConfig`, the actual configuration is the
   `FilterConfig.config` field (to which step 1 and 2 are then applied), and
   `FilterConfig.is_optional` controls the handling of unknown types
   ([Override Configuration (`typed_per_filter_config`)](#4-override-configuration-typed_per_filter_config)).

<!-- REVIEW(divergence) [XDS_FILTERS-1]: HttpFilter.disabled / FilterConfig.disabled (no merged
gRFC specifies them). Java: not implemented (fields ignored). Go: honored only
behind the ext_proc/ext_authz env-var guards (internal/xds/xdsclient/xdsresource/unmarshal_lds.go;
most specific override wins, any non-disabled override re-enables).
C++: honored unconditionally (src/core/xds/grpc/xds_routing.cc IsFilterDisabled:
ClusterWeight > Route > VirtualHost > HCM). Spec says: fields omitted (ignored).
Specify once A92/A93 or similar lands? -->

## 3. Top-Level Configuration (`HttpConnectionManager.http_filters`)

`http_filters` is an ordered list. For each entry gRPC uses the fields `name`,
`typed_config`, and `is_optional`. When the HCM is validated (as part of a
Listener resource), the list is validated as follows; any failure NACKs the
Listener resource:

| Rule | Behavior |
|---|---|
| `name` empty | NACK. |
| `name` duplicates the name of an earlier entry | NACK. |
| `typed_config` absent or type cannot be extracted | NACK. |
| Filter type not in the applicable registry (client registry for an API Listener, server registry for a TCP Listener), or registered but not supported on that side | If `is_optional` is true, the entry is ignored (dropped from the list). Otherwise NACK. |
| Filter type known | The filter implementation validates the configuration, including that it is of the filter's top-level config type. Validation failure → NACK. |
| After dropping ignored entries, the list is empty | NACK. |
| A terminal filter is not the last entry, or the last entry is not a terminal filter | NACK. |

The terminal-placement check is applied to the list after optional unknown
entries are dropped.

## 4. Override Configuration (`typed_per_filter_config`)

The `typed_per_filter_config` map appears in `VirtualHost`, `Route`, and
`WeightedCluster.ClusterWeight`. Each map entry is interpreted as follows:

- The **key** is the instance name of the HCM filter instance to which the
  override applies.
- The **value** is an `Any` containing the override configuration. The filter
  type is extracted per [Extracting the Filter Type](#21-extracting-the-filter-type), including unwrapping of
  `envoy.config.route.v3.FilterConfig` and `TypedStruct`.

When a RouteConfiguration is validated (whether received via RDS or inline in
an HCM), each map is validated as follows; any failure NACKs the resource
containing the RouteConfiguration:

| Rule | Behavior |
|---|---|
| Key empty | NACK. |
| Value type cannot be extracted (including an unparseable `FilterConfig` or `TypedStruct`) | NACK. |
| Override config type not registered by any filter type | If `FilterConfig.is_optional` is true (only possible when the `FilterConfig` wrapper is used), the entry is ignored. Otherwise NACK. |
| Type known | The filter implementation validates the configuration as an override. It fails validation if the value is the filter's top-level config type and the filter either does not support overrides or uses a different override type. Failure → NACK. |
| Key names no instance in the HCM | Not an error (the validator cannot know which HCM will use the RouteConfiguration). |
| Filter type is supported only on the other side (client vs. server) | Not an error (the validator cannot know whether the RouteConfiguration will be used by a client or a server). |

Validation of override configurations uses the union of client and server
filter types, because RouteConfiguration resources are not side-specific.

### 4.1 Effective Configuration and Precedence

For a given RPC and filter instance, the effective configuration is computed
from the instance's top-level configuration and **at most one** override: the
most specific override present, in this order of precedence:

1. the `typed_per_filter_config` entry in the selected `ClusterWeight` (only
   when the route uses weighted clusters);
2. otherwise the entry in the selected `Route`;
3. otherwise the entry in the selected `VirtualHost`;
4. otherwise no override.

An override entry is used only if its config type is the override type of the
filter type of the instance with that name; otherwise it is ignored for that
instance. Each filter type defines how its top-level configuration and the
selected override combine ([Router](#7-router)–[GCP Authentication](#11-gcp-authentication)). Overrides do not merge across
levels.

Implementations SHOULD compute the effective configuration for each
(virtual host, route, cluster weight) combination when the xDS configuration
is applied, rather than per RPC. This is an implementation strategy, not an
observable requirement.

## 5. Applying xDS HTTP Filters to RPCs

### 5.1 Client

On a client channel using the xds resolver ([client.md](client.md)), the
ConfigSelector returned by the resolver
([../04-client-channel/call-dispatch.md](../04-client-channel/call-dispatch.md))
performs xDS routing for each RPC. For each RPC, the ConfigSelector:

1. selects the virtual host and route, and, for weighted-cluster routes, the
   cluster weight entry;
2. determines the ordered list of filter instances from the current HCM
   (excluding the router) together with each instance's effective
   configuration ([Effective Configuration and Precedence](#41-effective-configuration-and-precedence)); and
3. causes the behaviors of those instances to be applied to the RPC, in list
   order, before the RPC reaches the load-balancing pick.

The router's behavior is the routing and load balancing itself ([Router](#7-router)). If no
route matches, the ConfigSelector fails the RPC with `UNAVAILABLE` and no xDS
HTTP filter behavior runs. The same applies if the matched route's action is
not `route` (for example `non_forwarding_action`): the ConfigSelector fails
the RPC with `UNAVAILABLE` and no xDS HTTP filter behavior runs (see
[client.md](client.md)).

The following per-call state established by the ConfigSelector is available to
xDS HTTP filter behaviors (exact representation is implementation-defined):

- the selected cluster name (mutable; see [Stateful Session Affinity](#10-stateful-session-affinity));
- the selected route, including the set of clusters it can target;
- the full current RouteConfiguration and cluster set, held such that a
  cluster selected or reselected by an xDS HTTP filter remains valid for the
  RPC even if a concurrent xDS update removes it; and
- the current `XdsConfig` ([client.md](client.md)), including the parsed CDS
  resource of each cluster.

**Cluster selection finalization.** Because an xDS HTTP filter (stateful
session affinity, [Stateful Session Affinity](#10-stateful-session-affinity)) may change the selected cluster, the final cluster
for the RPC is committed only after all non-router xDS HTTP filter behaviors
have run and immediately before the RPC is handed to load balancing. At that
point gRPC retains a reference to the selected cluster for the duration of the
RPC and releases its reference to the overall cluster set and
RouteConfiguration.

### 5.2 Server

On an xDS-enabled server ([server.md](server.md)), for each RPC the server
selects the filter chain for the connection, then the virtual host (by
`:authority`) and route from the HCM's RouteConfiguration. It then applies the
behaviors of the HCM's filter instances, in list order, using each instance's
effective configuration for the selected virtual host and route. After all
non-router filter behaviors have run, the router behavior checks the route
action: `non_forwarding_action` dispatches the RPC to the application; any
other action fails the RPC with `UNAVAILABLE` (see [server.md](server.md)).

### 5.3 Configuration Updates

When a new Listener or RouteConfiguration is applied, RPCs started afterwards
use the new list of filter instances and effective configurations. RPCs
already in progress continue to use the configuration that was in effect when
they started.

## 6. Filter State Retention Across Updates

Some filter types maintain state that SHOULD survive configuration updates
(e.g., the GCP authentication call-credentials cache, [Call Credentials Cache](#114-call-credentials-cache)). gRPC
provides a general mechanism for this:

- Retained state is scoped to a **filter instance**, identified by the pair
  (instance name, filter type).
- When a new configuration is applied (an LDS or RDS update), each filter
  instance in the new configuration whose (instance name, filter type) matches
  an instance in the previous configuration MAY obtain and reuse that
  instance's retained state. State of instances not present in the new
  configuration is released once no in-progress RPC still uses it.
- A filter type MAY further key its state (e.g., by a configuration value),
  but MUST NOT share state between two different instance names unless its
  specification says so.
- Changing the configuration of a retained instance (e.g., a cache size) is
  applied to the retained state; because the state is shared with RPCs still
  using the previous configuration, such a change MAY also affect those RPCs.
- On the client, the channel has exactly one HCM, so there is one set of
  retained filter state per channel.
- On the server, an implementation MAY scope retained state to one L4 filter
  chain (matched across updates by filter-chain name), to one Listener (all
  filter chains of that Listener), or to the whole server. Filter types MUST
  NOT depend on any particular scope. Because retention is a MAY, an
  implementation MAY skip retention for filter chains that have no name.

## 7. Router

- **Config type:** `envoy.extensions.filters.http.router.v3.Router`.
- **Sides:** client and server. **Terminal:** yes. **Overrides:** not
  supported.
- **Validation:** all fields of `Router` are ignored; any `Router` message is
  valid.
- **Behavior:** the router has no discrete per-RPC behavior of its own. On the
  client, it denotes gRPC's built-in xDS routing and load balancing
  ([client.md](client.md), [xDS LB Policies](lb-policies.md)): if the matched
  route's action is `route`, the RPC proceeds to cluster selection and load
  balancing; any other action (for example `non_forwarding_action`, or an
  unsupported action) makes the ConfigSelector fail the RPC with
  `UNAVAILABLE` before any xDS HTTP filter behavior runs
  ([Client](#51-client)). On the server, it
  denotes dispatch of the RPC to the application according to the route
  action ([Server](#52-server)).

## 8. Fault Injection

- **Config type (top-level and override):**
  `envoy.extensions.filters.http.fault.v3.HTTPFault`.
- **Sides:** client only. **Terminal:** no.
- **Override semantics:** if an override is selected ([Effective Configuration and Precedence](#41-effective-configuration-and-precedence)), it
  **replaces** the top-level configuration entirely.

### 8.1 Configuration

| Field | Handling |
|---|---|
| `delay` (`envoy.extensions.filters.common.fault.v3.FaultDelay`) | Optional. See below. |
| `delay.fixed_delay` | `google.protobuf.Duration`; validated as a Duration (`seconds` in [0, 315576000000], `nanos` in [0, 999999999], else NACK). The delay to inject. |
| `delay.header_delay` | If set, the delay is taken from request headers ([Header-Controlled Faults](#83-header-controlled-faults)). |
| `delay.percentage` | `envoy.type.v3.FractionalPercent`: `numerator` and `denominator` (`HUNDRED` = 100, `TEN_THOUSAND` = 10000, `MILLION` = 1000000; default `HUNDRED`). If unset, the probability is 0. |
| `abort` (`FaultAbort`) | Optional. See below. |
| `abort.http_status` | An HTTP status code. Converted to a gRPC status code using the HTTP-to-gRPC status mapping (`400`→`INTERNAL`, `401`→`UNAUTHENTICATED`, `403`→`PERMISSION_DENIED`, `404`→`UNIMPLEMENTED`, `429`/`502`/`503`/`504`→`UNAVAILABLE`, any other→`UNKNOWN`). In particular `200` maps to `UNKNOWN` (as if an HTTP 200 response arrived without `grpc-status`). |
| `abort.grpc_status` | A gRPC status code number. MUST be a valid code (0–16), else NACK. `0` (`OK`) is allowed ([`OK` and HTTP 200 Aborts](#84-ok-and-http-200-aborts)). |
| `abort.header_abort` | If set, the abort status is taken from request headers ([Header-Controlled Faults](#83-header-controlled-faults)). |
| `abort.percentage` | As `delay.percentage`. |
| `max_active_faults` | `google.protobuf.UInt32Value`. If set, the maximum number of concurrently active faults process-wide ([Maximum Active Faults](#85-maximum-active-faults)). If unset, unlimited. |
| `response_rate_limit` | Not supported; ignored. |
| `downstream_nodes`, `upstream_cluster`, `headers` | Not supported; ignored. |
| Runtime-key fields (`delay_percent_runtime`, `abort_percent_runtime`, etc.) | Not supported (gRPC has no runtime); ignored. |

### 8.2 Per-RPC Algorithm

When an RPC starts, before any traffic for the RPC is sent:

```
delay = config.delay.fixed_delay (or 0 if unset)
delay_num = config.delay.percentage.numerator (0 if unset)
abort_status = config.abort status (none if abort unset)
abort_num = config.abort.percentage.numerator (0 if unset)
apply header overrides (see "Header-Controlled Faults")

inject_delay = delay > 0 && Roll(delay_num, delay_denominator)
inject_abort = abort_status set && Roll(abort_num, abort_denominator)

Roll(num, den): if num == 0 return false
                if num >= den return true
                return uniform_random_int in [0, den) < num
```

Each decision MUST use an independent random draw. (With a 20% delay and a 5%
abort probability, 24% of RPCs are affected.)

Then:

1. If `inject_delay` and the active-fault limit permits ([Maximum Active Faults](#85-maximum-active-faults)): the RPC
   becomes an active fault, and nothing is sent for the RPC until `delay`
   has elapsed. The RPC's deadline and cancellation continue to apply during
   the delay.
2. If `inject_abort` and either a delay was injected in step 1 or the
   active-fault limit permits: the RPC is failed with the abort status, before
   sending any traffic. This applies to unary and streaming RPCs alike.
3. Otherwise the RPC proceeds normally.

The status message of an injected abort is implementation-defined.

### 8.3 Header-Controlled Faults

If `header_delay` or `header_abort` is configured, the corresponding values are
read from the RPC's request metadata. These headers are consulted only for a
fault type configured with `header_delay`/`header_abort`, so they never
conflict with fixed values in the configuration.

| Header | Applies when | Meaning |
|---|---|---|
| `x-envoy-fault-delay-request` | `header_delay` | Delay in milliseconds (non-negative integer). |
| `x-envoy-fault-delay-request-percentage` | `header_delay` | Numerator of the delay probability; the denominator is that of `delay.percentage`. The effective numerator is `min(header value, configured numerator)`. |
| `x-envoy-fault-abort-grpc-request` | `header_abort` | gRPC status code number to abort with. |
| `x-envoy-fault-abort-request` | `header_abort` | HTTP status code, mapped to a gRPC status code as for `abort.http_status`. |
| `x-envoy-fault-abort-request-percentage` | `header_abort` | Numerator of the abort probability, capped by the configured `abort.percentage` numerator, as for delay. |
| `x-envoy-fault-throughput-response`, `x-envoy-fault-throughput-response-percentage` | — | Not supported; ignored. |

Rules:

- A header whose value is invalid (e.g., non-numeric, out of range) is ignored.
- If a header has multiple values, the implementation MAY use any one of them.
- If both `x-envoy-fault-abort-request` and `x-envoy-fault-abort-grpc-request`
  are present, `x-envoy-fault-abort-request` takes precedence.

<!-- REVIEW(divergence) [XDS_FAULT-1]: abort-header precedence and names (A33 silent on
precedence). Java: reads both; HTTP header wins (FaultFilter.java
determineFaultAbortStatus); any unparseable header => no abort. Go: HTTP header
wins if present at all, gRPC header ignored even if HTTP value is invalid
(internal/xds/httpfilter/fault/fault.go injectAbort). C++: reads only
x-envoy-fault-abort-grpc-request and takes the percentage from
`x-envoy-fault-abort-percentage` (src/core/xds/grpc/xds_http_fault_filter.cc);
Java/Go use A33's `x-envoy-fault-abort-request-percentage`. Spec says: A33 names,
HTTP header wins (switched from gRPC-wins to match Java/Go majority). -->

### 8.4 `OK` and HTTP 200 Aborts

- `http_status: 200` aborts the RPC with `UNKNOWN`.
- `grpc_status: 0` (`OK`): gRPC behaves as if it had immediately received
  trailing metadata from the server with status `OK` and no messages. The
  status the application observes depends on the RPC type: for unary and
  client-streaming RPCs, the client may report a non-`OK` status because the
  single expected response message never arrived; for server-streaming and
  bidirectional-streaming RPCs, the client may report `OK` with no response
  messages.

### 8.5 Maximum Active Faults

The number of *active faults* is a single process-wide gauge shared by all
channels and all fault-injection instances. It MUST be updated in a
thread-safe manner. An RPC counts as one active fault from the moment a fault
(delay or abort) is injected into it until that fault finishes: a delay
finishes when the delay elapses (or the RPC ends during the delay); an abort
finishes when the RPC has been aborted. A fault is injected only if the
current gauge value is less than the effective configuration's
`max_active_faults`.

## 9. RBAC

- **Config types:** top-level `envoy.extensions.filters.http.rbac.v3.RBAC`;
  override `envoy.extensions.filters.http.rbac.v3.RBACPerRoute`.
- **Sides:** server only. **Terminal:** no.
- **Override semantics:** a selected `RBACPerRoute` replaces the top-level
  configuration. If `RBACPerRoute.rbac` is unset, RBAC is disabled for that
  RPC (no policy enforced).

The policy-matching semantics (the *RBAC engine*), audit-logging semantics,
and the audit logger plugin API are shared with gRPC's non-xDS authorization
policy and are specified in
[../06-security/authorization.md](../06-security/authorization.md). This
section specifies the xDS-specific configuration handling and the mapping of
RBAC fields onto gRPC concepts. RBAC enforces authorization, not
authentication, so it applies whether or not the server uses
XdsServerCredentials ([security.md](security.md)).

The RBAC *network* filter (`envoy.extensions.filters.network.rbac.v3.RBAC`) is
not supported.

### 9.1 Configuration Validation

| Field | Handling |
|---|---|
| `RBAC.rules` | Optional. If unset, no policy is enforced (all RPCs are allowed by this instance). |
| `RBAC.rules.action` | `ALLOW` or `DENY`. If `LOG`, the entire instance is ignored, as if RBAC were not configured. |
| `RBAC.rules.policies` | Map of policy name → `Policy`. Each `Policy` has `permissions` and `principals` (see [Mapping RBAC Fields to gRPC](#92-mapping-rbac-fields-to-grpc)). |
| `Policy.condition`, `Policy.checked_condition` | CEL is not supported; presence → NACK. |
| `header` matcher (in any `Permission` or `Principal`) naming a header that starts with `grpc-`, or `:scheme` | NACK. |
| Nesting of `and_rules`/`or_rules`/`not_rule` | Validated recursively; implementations MAY impose a maximum recursion depth, exceeding which → NACK. |
| String, path, header, CIDR, and metadata matchers | Validated as in [resources/common-types.md](resources/common-types.md); invalid → NACK. |
| `RBAC.shadow_rules`, `shadow_rules_stat_prefix`, `rules_stat_prefix` | Not supported; ignored. |
| `RBAC.rules.audit_logging_options` | See [Audit Logging Configuration](#93-audit-logging-configuration). |
| `RBACPerRoute.rbac` | If set, validated exactly as a top-level `RBAC`. |

In addition, the HCM containing the RBAC instance is subject to the following
rule, which applies to every HCM (client and server) so that RBAC's
`remote_ip` and `direct_remote_ip` are equivalent: `xff_num_trusted_hops` MUST
be 0 and `original_ip_detection_extensions` MUST be empty, else the Listener
is NACKed (see [resources/listener.md](resources/listener.md)).

All failures above NACK the resource containing the configuration (the
Listener for top-level configuration; the resource containing the
RouteConfiguration for overrides).

### 9.2 Mapping RBAC Fields to gRPC

`Permission` fields that need interpretation:

| Permission field | gRPC equivalent |
|---|---|
| `header` | Request metadata, with the rules below. |
| `url_path` | The fully-qualified method name with leading slash (the `:path` value), e.g. `/pkg.Service/Method`. |
| `destination_ip` | Local IP address of the connection. |
| `destination_port` | Local port of the connection. |
| `metadata` | Envoy dynamic metadata, which gRPC treats as an empty map; therefore never matches (a `ValueMatcher` requires a value to be present). |
| `requested_server_name` | Treated as the empty string; matches only if the matcher accepts `""`. |

`Principal` fields that need interpretation:

| Principal field | gRPC equivalent |
|---|---|
| `authenticated.principal_name` | Matched against the peer certificate as described below. |
| `source_ip` | Peer IP address of the connection. |
| `direct_remote_ip` | Peer IP address of the connection. |
| `remote_ip` | Peer IP address of the connection. |
| `header`, `url_path`, `metadata` | As in `Permission`. |

Because rules can be negated (`not_rule`), rules that reference values gRPC
hard-codes (such as `metadata` or `requested_server_name`) MUST still be
evaluated; they cannot be optimized away.

**Header matching.** RBAC header matchers use the server-side header
semantics of the shared RBAC engine, specified in
[../06-security/authorization.md](../06-security/authorization.md)
(Header Matching Rules). In summary: `:method`, `:authority`, and `:path`
can be matched with their on-the-wire values; `Host` and `:authority` are
aliases; hop-by-hop headers (including `te`) are absent; the client-sent
`content-type` is used; multiple values are joined with `,`; `-bin` headers
are matched in base64-encoded form; and an absent header does not match
except for a `present_match` whose value equals `invert_match`. These differ
from the client-side routing semantics in
[resources/common-types.md](resources/common-types.md).

**`authenticated` principal.** Matching of `authenticated.principal_name`
against the peer's TLS state (URI SANs, then DNS SANs, then the RFC 2253
subject; no match on non-TLS connections) is specified in
[../06-security/authorization.md](../06-security/authorization.md)
(Authenticated Principal Matching).


### 9.3 Audit Logging Configuration

`RBAC.rules.audit_logging_options` (`envoy.config.rbac.v3.RBAC.AuditLoggingOptions`):

| Field | Handling |
|---|---|
| `audit_condition` | `NONE` (default), `ON_DENY`, `ON_ALLOW`, or `ON_DENY_AND_ALLOW`. Any other value → NACK. "Allow"/"deny" refer to this instance's decision, not its action: a DENY decision is a match in a `DENY` instance or no match in an `ALLOW` instance. |
| `logger_configs[].audit_logger` | `TypedExtensionConfig`; required (absent → NACK). The logger type is extracted from `typed_config` per [Extracting the Filter Type](#21-extracting-the-filter-type) (so a third-party logger is configured with a `TypedStruct` whose `type_url` names the registered logger type, and whose `value` is passed to the logger's config parser as JSON). |
| `logger_configs[].is_optional` | If the logger type is not supported, the entry is ignored when true; NACK when false. A config that fails the logger's own validation NACKs regardless of `is_optional`. |

Built-in logger type: `envoy.extensions.rbac.audit_loggers.stream.v3.StdoutAuditLog`
(the `stdout_logger`), which has no configuration fields and writes JSON
entries to standard output, as specified in
[../06-security/authorization.md](../06-security/authorization.md).
Applications MAY register additional logger types through the audit logger
API specified there.

Setting an `audit_condition` with no loggers, or loggers with `NONE`, is valid
and results in no audit logging.

When this instance's decision meets `audit_condition`, every configured logger
is invoked synchronously, immediately after the decision, with an audit
context containing the RPC method, the peer principal, the policy name, the
matched rule (the matched policy name, empty if none), and whether the RPC was
authorized. For xDS RBAC, the policy name is empty.
Multiple RBAC instances may each log for the same RPC; no de-duplication is
performed.

### 9.4 Behavior

For each RPC, using the effective configuration: if no policy is enforced, the
RPC proceeds. Otherwise the engine evaluates the policies; with action
`ALLOW` the RPC proceeds only if some policy matches, and with action `DENY`
the RPC proceeds only if no policy matches. A denied RPC fails with
`PERMISSION_DENIED`. Audit logging ([Audit Logging Configuration](#93-audit-logging-configuration)) happens before the RPC proceeds
or fails.

## 10. Stateful Session Affinity

Stateful session affinity (SSA) routes all RPCs of an application-defined
"session" to the same endpoint (and cluster) using an HTTP cookie. The
application is responsible for storing the cookie returned in a response
(`set-cookie`) and sending it on later RPCs of the session (`cookie`). It
works together with the `xds_override_host` LB policy
([`xds_override_host`](lb-policies/xds_override_host.md)) and the CDS
`common_lb_config.override_host_status` field
([resources/cluster.md](resources/cluster.md)).

- **Config types:** top-level
  `envoy.extensions.filters.http.stateful_session.v3.StatefulSession`; override
  `envoy.extensions.filters.http.stateful_session.v3.StatefulSessionPerRoute`.
- **Sides:** client only. **Terminal:** no.
- **Override semantics:** a selected `StatefulSessionPerRoute` replaces the
  top-level configuration. If `StatefulSessionPerRoute.disabled` is true, or
  `stateful_session` is unset, SSA is disabled for that RPC.

### 10.1 Configuration Validation

| Field | Handling |
|---|---|
| `StatefulSession.session_state` | `TypedExtensionConfig`. If unset, the instance is a no-op. |
| `session_state.typed_config` | MUST be `envoy.extensions.http.stateful_session.cookie.v3.CookieBasedSessionState` (after `TypedStruct` unwrapping); any other type or an unparseable message → NACK. |
| `CookieBasedSessionState.cookie` | Required (`envoy.type.http.v3.Cookie`); absent → NACK. |
| `cookie.name` | Required, non-empty; empty → NACK. |
| `cookie.path` | Optional. If empty, all request paths match. |
| `cookie.ttl` | Optional `Duration`; validated as a Duration (negative or out-of-range → NACK). Default 0. Placed in the cookie but not enforced by gRPC. |
| `cookie.attributes` and other fields | Ignored. |
| `StatefulSession.strict` | Ignored. |
| `StatefulSessionPerRoute.disabled` | See override semantics. |
| `StatefulSessionPerRoute.stateful_session` | If set (and `disabled` is false), validated exactly as a top-level `StatefulSession`. |

### 10.2 Cookie Value Format

The cookie value is the standard base64 encoding of the string:

```
<address_1>[,<address_2>...];<cluster>
```

- `<address_i>` are the addresses of one endpoint, each in `IP:port` form
  (IPv6 addresses in brackets), separated by `,`. The address actually used
  for the RPC that produced the cookie is first.
- `<cluster>` is the name of the cluster that served the RPC (without any
  prefix or quoting).

When parsing, the decoded value is split at the first `;`: the part before is
the address list (may be empty), the part after is the cluster (may be empty
or absent).

### 10.3 Request Processing

For each RPC with an enabled effective configuration (non-empty cookie name):

1. **Path check.** If `cookie.path` is non-empty and does not path-match the
   RPC's `:path` per RFC 6265 [Server: Forced Shutdown](../05-server.md#14-forced-shutdown), SSA is skipped entirely for this RPC
   (including response processing). Path-match: the cookie path is a prefix
   of the request path, and either they are identical, or the cookie path ends
   with `/`, or the first request-path character after the prefix is `/`.
   (If the cookie path does not match the paths of the RPCs routed to this
   configuration, the cookie is never set.)
2. **Cookie extraction.** Parse the `cookie` request header as a list of
   `name=value` pairs separated by `"; "`. Take the value of the first pair
   whose name equals `cookie.name`. If there is none, or the value is not
   valid base64, treat the cookie as absent (empty address list and cluster).
3. **Override-host attribute.** Attach to the RPC an *override-host call
   attribute* carrying the cookie's address list (possibly empty). This
   attribute is read by `xds_override_host` at pick time, which uses it to
   prefer one of the listed endpoints and reports back, via the same
   attribute, the full address list of the endpoint actually picked (see
   [`xds_override_host`](lb-policies/xds_override_host.md)). Addresses in the list that are not
   syntactically valid `IP:port` values simply never match an endpoint.
4. **Cluster override.** If the cookie names a cluster and that cluster is one
   the selected route can target (the route's single `cluster`, or one of its
   `weighted_clusters`), replace the RPC's selected cluster with it.
   Otherwise keep the cluster selected by the ConfigSelector. Cluster
   selection is finalized after this step ([Client](#51-client)), so load balancing,
   including the per-cluster LB policy and `xds_override_host`, operates on
   the cookie's cluster.

The attribute is attached whenever SSA is not skipped, even if no cookie was
present, so that `xds_override_host` reports the picked endpoint; when present
it also signals that the endpoint is being used for a session (affecting
subchannel retention in `xds_override_host`).

If retries are configured, all attempts of the RPC carry the same attribute
and therefore prefer the same endpoint.

### 10.4 Response Processing

When the server's response headers are received (or, for a Trailers-Only
response, when the trailers are received), if SSA was not skipped for the RPC:

- Let `actual_list` be the address list reported by `xds_override_host` for
  the picked endpoint, and `actual_cluster` be the finalized cluster.
- If `actual_list` equals the cookie's address list and `actual_cluster`
  equals the cookie's cluster, do nothing.
- Otherwise, add a `set-cookie` header to the response headers (or trailers,
  for Trailers-Only) delivered to the application:

  ```
  <cookie.name>=<base64(actual_list + ";" + actual_cluster)>; HttpOnly[; Path=<cookie.path>][; Max-Age=<ttl seconds>]
  ```

  `Path` is included only if `cookie.path` is non-empty; `Max-Age` (whole
  seconds of `cookie.ttl`) only if `ttl` is greater than 0.

## 11. GCP Authentication

The GCP authentication filter attaches a GCP service-account identity JWT to
RPCs, as call credentials, with a per-cluster audience.

- **Config type:** `envoy.extensions.filters.http.gcp_authn.v3.GcpAuthnFilterConfig`.
- **Sides:** client only. **Terminal:** no.

### 11.1 Configuration Validation

| Field | Handling |
|---|---|
| `cache_config` | Optional. |
| `cache_config.cache_size` | Optional `UInt64Value`. If set, MUST be > 0, else NACK. Default 10. Implementations MAY cap it at their maximum supported size. |
| `http_uri`, `token_header`, `retry_policy`, `cluster`, `timeout` | Ignored. |

Per-route overrides are not supported. If a `GcpAuthnFilterConfig` appears in a
`typed_per_filter_config` map, it is validated as part of normal resource
validation (as a top-level config), but it is never used.

<!-- REVIEW(divergence) [XDS_GCP_AUTHN-1]: A83 says an override is "validated ... but will not
actually be used". Java: override parsed/validated as top-level config, then
ignored (GcpAuthenticationFilter.java parseFilterConfigOverride). Go: same
(internal/xds/httpfilter/gcpauthn/gcp_authn_filter.go). C++: no override type
registered (OverrideConfigProtoName() == ""), so an override NACKs unless
is_optional (src/core/xds/grpc/xds_http_gcp_authn_filter.cc). Spec says: follow
A83 (validate, ignore). -->

### 11.2 Audience from Cluster Metadata

The audience comes from the CDS resource of the RPC's cluster. CDS
`Cluster.metadata` is parsed into a metadata map as described in
[resources/cluster.md](resources/cluster.md) and
[resources/common-types.md](resources/common-types.md); the registered metadata
type `envoy.extensions.filters.http.gcp_authn.v3.Audience` (whose `url` MUST be
non-empty, else the CDS resource is NACKed) parses to an audience string.

The metadata key looked up is the xDS HTTP filter **instance name**
(`HttpFilter.name`), not a fixed key.

### 11.3 Per-RPC Behavior

When the RPC's request headers are processed, using the RPC's finalized
cluster and the `XdsConfig` ([Client](#51-client)):

1. If the CDS resource for the cluster is not available in the current
   `XdsConfig` (e.g., an error was received with no previously valid resource,
   or the resource does not exist), fail the RPC with `UNAVAILABLE`. (The RPC
   is failed even if it is wait-for-ready, because it cannot be re-processed
   with a later configuration.)
2. Look up the instance name in the cluster's metadata map. If absent, do
   nothing.
3. If the entry is not of type `Audience`, fail the RPC with `UNAVAILABLE`.
4. Otherwise, obtain from the instance's cache ([Call Credentials Cache](#114-call-credentials-cache)) the GCP
   service-account identity call credentials for the audience `url`, creating
   and inserting them if absent, and attach them to the RPC.


The token is not added by this step directly, because the connection is not
yet known. The attached call credentials add the token after a connection has
been chosen, and MUST NOT send it on connections whose security level does
not permit call credentials (e.g., insecure connections). The GCP
service-account identity call credentials (token fetch from the metadata
server, caching, refresh, backoff, error-to-status mapping, and the
`authorization: Bearer <token>` header) are specified in
[../06-security/call-credentials.md](../06-security/call-credentials.md).

### 11.4 Call Credentials Cache

Each filter instance maintains an LRU cache mapping audience → call
credentials object:

- Using an entry moves it to the most-recently-used position. Inserting into a
  full cache evicts the least-recently-used entry.
- The maximum size is `cache_config.cache_size`. The cache is channel-wide:
  shared by all routes.
- The cache is retained across LDS and RDS updates using the mechanism of
  [Filter State Retention Across Updates](#6-filter-state-retention-across-updates), keyed by instance name, so two instances never share a cache and the
  same instance keeps its cache across updates.
- If an update changes `cache_size`, the new size is applied to the retained
  cache, evicting least-recently-used entries as needed.

## 12. API Requirements

- gRPC is not required to provide a public API for registering third-party xDS
  HTTP filter types. The set of supported filter types is defined by this
  section.
- The server API MUST allow applications to register audit logger types for
  use by xDS RBAC audit logging, using the audit logger API defined in
  [../06-security/authorization.md](../06-security/authorization.md).
- The client API MUST allow applications to read `set-cookie` values from
  response headers (and from trailers for Trailers-Only responses) and to send
  `cookie` request headers, so that applications can implement the cookie
  handling required by stateful session affinity.
