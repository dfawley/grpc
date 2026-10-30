> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 9.3.3 RouteConfiguration

<!-- Sources: A27, A28, A31, A36, A39, A42, A44, A55, A60, A63, A74, A81, doc/grpc_xds_features.md, grpc-proto grpc/lookup/v1/rls_config.proto, implementations (cluster specifier plugins) -->

> **Introduced by:** [gRFC A27: xDS-Based Global Load Balancing](https://github.com/grpc/proposal/blob/master/A27-xds-global-load-balancing.md)

The `envoy.config.route.v3.RouteConfiguration` resource holds the routing
table: a list of virtual hosts, each with an ordered list of routes. A
RouteConfiguration is either fetched through RDS (named by
`HttpConnectionManager.rds.route_config_name`) or embedded in a Listener
(`HttpConnectionManager.route_config`); it is validated the same way in both
cases. RDS does not distinguish client from server use, so the same rules
apply to RouteConfigurations used by xDS-enabled servers
([xDS-Enabled Servers](../07-server.md)).

This section specifies which fields are read, when the resource is rejected,
and what the parsed resource contains. Virtual host selection, route matching
at RPC time, cluster selection, and the use of each route's settings are
specified in [Client Data Plane](../04-client.md).

## 1. RouteConfiguration Fields

| Field | Rule |
| --- | --- |
| `name` | The resource name. |
| `virtual_hosts` | Zero or more virtual hosts. **Every** virtual host is fully validated, whether or not any client will select it; an error in any virtual host rejects the resource. |
| `cluster_specifier_plugins` | Cluster specifier plugin definitions, validated as in [Cluster Specifier Plugins](#52-cluster-specifier-plugins). |

All other fields are ignored.

## 2. VirtualHost

| Field | Rule |
| --- | --- |
| `domains` | MUST be non-empty. Each entry MUST be a valid domain pattern (see below); otherwise the resource is rejected. |
| `routes` | Ordered list of routes ([Route](#3-route)). Routes that are ignored under the rules below are left out of the parsed list; the order of the others is kept. A virtual host may end up with no routes. |
| `retry_policy` | Optional virtual-host-level `RetryPolicy`, validated as in [Retry Policy](#8-retry-policy). It applies to each route in the virtual host whose `RouteAction` has no `retry_policy` of its own. |
| `typed_per_filter_config` | Per-virtual-host xDS HTTP filter config overrides. Validated as specified in [xDS HTTP Filters](../06-http-filters.md). |

All other fields (`require_tls`, `virtual_clusters`, `rate_limits`, `cors`,
header manipulation, `retry_policy_typed_config`, `hedge_policy`, and so on)
are ignored.

### 2.1 Domain Patterns

A domain pattern is one of:

| Kind | Form | Matches a host name `h` when |
| --- | --- | --- |
| Exact | no `*` | `h` equals the pattern |
| Suffix wildcard | starts with `*`, e.g. `*.foo.com`, `*-bar.foo.com` | `h` ends with the part after the `*`, and the `*` matches at least one character |
| Prefix wildcard | ends with `*`, e.g. `foo.*`, `foo-*` | `h` starts with the part before the `*`, and the `*` matches at least one character |
| Universal | exactly `*` | any `h` |

An empty pattern, or a pattern that contains `*` but is not one of the forms
above (for example `foo.*.com`), is invalid and rejects the resource.
Matching is case-insensitive.

When a host name is matched against a RouteConfiguration, the virtual host is
chosen by **most specific match**:

```
find_virtual_host(virtual_hosts, host):
  best = none; best_kind = none; best_len = 0
  for vh in virtual_hosts (in order):
    for pattern in vh.domains:
      kind = kind_of(pattern)          // EXACT < SUFFIX < PREFIX < UNIVERSAL
      if best != none and (kind > best_kind or
                           (kind == best_kind and len(pattern) <= best_len)):
        continue                       // cannot beat the current best
      if not domain_match(kind, pattern, host): continue
      best = vh; best_kind = kind; best_len = len(pattern)
  return best                          // none if nothing matched
```

That is: an exact match beats a suffix wildcard, which beats a prefix
wildcard, which beats `*`. Within a kind, the longest pattern wins. Between
equally good patterns, the first virtual host in list order wins. The host
name being matched is defined in [Client Data Plane](../04-client.md) for
clients and in [xDS-Enabled Servers](../07-server.md) for servers.

## 3. Route

| Field | Rule |
| --- | --- |
| `match` | MUST be present; otherwise the resource is rejected. Validated as in [RouteMatch](#4-routematch). |
| `route` | A `RouteAction` ([RouteAction](#6-routeaction)). |
| `non_forwarding_action` | Marks the route as non-forwarding (server-side routes). |
| other `action` values (`redirect`, `direct_response`, `filter_action`, unknown) | Accepted; the route's action is recorded as *unsupported*. |
| `typed_per_filter_config` | Per-route xDS HTTP filter config overrides. Validated as specified in [xDS HTTP Filters](../06-http-filters.md). |

All other fields (`name`, `metadata`, `decorator`, header manipulation,
`per_request_buffer_limit_bytes`, and so on) are ignored.

The `action` field is not checked against where the RouteConfiguration is
used. Client channels expect `route`; servers expect `non_forwarding_action`.
A route with an unexpected or unsupported action stays in the parsed
resource. An RPC that matches it, and has passed through the configured xDS
HTTP filters (which gRPC applies per RPC, for example through interceptors),
fails with status `UNAVAILABLE` (see [Client Data Plane](../04-client.md)
and [xDS-Enabled Servers](../07-server.md)). Routes with an unexpected action
are not skipped during matching: they still "win" if they match first.

## 4. RouteMatch

> **Introduced by:** [gRFC A28: gRPC xDS traffic splitting and routing](https://github.com/grpc/proposal/blob/master/A28-xds-traffic-splitting-and-routing.md)

| Field | Rule |
| --- | --- |
| path specifier | Exactly one of `prefix`, `path`, or `safe_regex` MUST be set. If the path specifier is unset or uses another option (`path_separated_prefix`, `connect_matcher`, `path_match_policy`, or an unknown field), the resource is rejected. |
| `prefix` | Matches if the RPC's path (`/service/method`) starts with the value. An empty prefix matches every path. |
| `path` | Matches if the RPC's path equals the value. |
| `safe_regex` | Matches if the RPC's path fully matches the regex (RE2 syntax; see `StringMatcher.safe_regex` in [Common Types](01-common-types.md)). The regex MUST compile. |
| `case_sensitive` | `BoolValue`, default true. If false, `prefix` and `path` compare case-insensitively. It has no effect on `safe_regex`. The server still dispatches methods case-sensitively. |
| `headers` | Zero or more `HeaderMatcher`s, validated and evaluated as specified in [Common Types](01-common-types.md) ([`HeaderMatcher`](01-common-types.md#8-headermatcher)). All must match. |
| `runtime_fraction` | Optional `RuntimeFractionalPercent`. Only `default_value` is used; it is normalized to a fraction per million ([Fractional Percentages](01-common-types.md#5-fractional-percentages)). An unknown denominator rejects the resource. When set, the route matches only for that fraction of RPCs, decided independently per RPC. |
| `query_parameters` | gRPC has no query parameters. If this list is non-empty, the route can never match, and it is ignored (left out of the parsed resource). |
| `grpc` | Ignored. The other matchers in the route are still evaluated. |
| `tls_context` | Ignored. The other matchers in the route are still evaluated. |

All other `RouteMatch` fields are ignored.

The validator MAY also leave out of the parsed resource any route whose
`prefix` or `path` cannot match a path of the form `/service/method` (for
example a `path` that does not have exactly two `/`-separated non-empty
components, or a `prefix` that does not start with `/`). Such a route can
never match an RPC, so leaving it out does not change routing behavior.

A route matches an RPC only if its path specifier, every header matcher, and
the runtime fraction (if any) all match. Routes are evaluated in order, and
the first match wins (see [Client Data Plane](../04-client.md)). Duplicate
matchers are allowed; a later duplicate is simply never chosen.

## 5. Cluster Specifier

The `RouteAction` `cluster_specifier` oneof picks the target cluster(s):

| Option | Handling |
| --- | --- |
| `cluster` | The cluster name. MUST be non-empty; otherwise the resource is rejected. |
| `weighted_clusters` | A weighted split across clusters (see below). |
| `cluster_header` | Not supported. The route is ignored. |
| `cluster_specifier_plugin` | The name of a plugin defined in `RouteConfiguration.cluster_specifier_plugins` (see [Cluster Specifier Plugins](#52-cluster-specifier-plugins)). MUST be non-empty and MUST name a defined plugin; otherwise the resource is rejected. If it names an optional plugin whose type the client does not support, the route is ignored. |
| `inline_cluster_specifier_plugin` | Not supported. The route is ignored. |
| unset, or an option unknown to the client | The route is ignored. |

Ignoring routes with an unknown cluster specifier is what lets the xDS API
add new cluster specifiers without breaking older clients: protobuf parses an
unknown member of a oneof as "oneof unset."

### 5.1 `weighted_clusters`

> **Introduced by:** [gRFC A28: gRPC xDS traffic splitting and routing](https://github.com/grpc/proposal/blob/master/A28-xds-traffic-splitting-and-routing.md)

| Field | Rule |
| --- | --- |
| `clusters` | List of `ClusterWeight`. |
| `clusters[].name` | MUST be non-empty. |
| `clusters[].weight` | `UInt32Value`. SHOULD be set; a resource with an unset weight SHOULD be rejected. Some implementations instead treat an unset weight as 0; this is a known deviation. An entry with weight 0 is left out of the parsed list. |
| `clusters[].typed_per_filter_config` | Per-cluster-weight xDS HTTP filter config overrides. Validated as specified in [xDS HTTP Filters](../06-http-filters.md). |
| `total_weight` | Ignored. The total is the sum of the weights of the listed clusters. |
| other fields (`runtime_key_prefix`, `header_name`, `random_value_specifier`, `cluster_header`, ...) | Ignored. |

After zero-weight entries are dropped, at least one entry MUST remain, and
the sum of the remaining weights MUST NOT exceed 4,294,967,295 (the uint32
max). Otherwise the resource is rejected. The same cluster name MAY appear
more than once.

### 5.2 Cluster Specifier Plugins

A cluster specifier plugin chooses the cluster for each RPC by some
mechanism other than a fixed name or weights. The client implements a
plugin by turning its configuration into an LB policy config. That config
becomes the child of `xds_cluster_manager` for every route that names the
plugin (see [Client Data Plane](../04-client.md)).

**Registry.** gRPC keeps a registry of supported plugins, keyed by the
fully-qualified proto message name of the plugin's configuration. Each
registered plugin converts a configuration message into a
`loadBalancingConfig` list. The only plugin gRPC provides is the RLS plugin
([RLS Cluster Specifier Plugin](#53-rls-cluster-specifier-plugin)).

`RouteConfiguration.cluster_specifier_plugins` is a list of
`envoy.config.route.v3.ClusterSpecifierPlugin`, each validated as follows:

| Field | Rule |
| --- | --- |
| `extension` | A `TypedExtensionConfig`. MUST be present; otherwise the resource is rejected. |
| `extension.name` | The plugin's name, used by `RouteAction.cluster_specifier_plugin`. Two plugins with the same name reject the resource. |
| `extension.typed_config` | The plugin type is the extension's type, extracted as specified in [Extensions](01-common-types.md#2-extensions-googleprotobufany-and-typedstruct) (a `TypedStruct` is unwrapped). If the type cannot be extracted, the resource is rejected. If the type is registered, the plugin converts the configuration to an LB policy config. A conversion error rejects the resource. The resulting config MUST also be accepted by the LB policy registry ([Load Balancing](../../04-client-channel/05-load-balancing.md)); otherwise the resource is rejected. |
| `is_optional` | Applies only when the type is not registered. If false, the resource is rejected. If true, the plugin is recorded as *optional and unsupported*, and every route that names it is ignored (see [Cluster Specifier](#5-cluster-specifier)). |

A configured plugin that no remaining route names is left out of the
parsed resource.

<!-- REVIEW(divergence) [XDS_ROUTING-3]: plugin list validation. Duplicate names: C++ rejects any duplicate; Java rejects duplicates among supported plugins only; Go keeps the last one. Converted config validation: C++ and Go validate the generated rls config with the LB policy parser and NACK errors; Java checks only that route_lookup_config is present, so a bad RLS config shows up later as a service config error. Also, Java generates the cds child config with the key "is_dynamic" (and its cds parser reads "is_dynamic") instead of the JSON name "isDynamic". Spec says: C++ (reject duplicates, validate the config when the resource is parsed), and "isDynamic". -->

### 5.3 RLS Cluster Specifier Plugin

The RLS plugin's configuration type is
`grpc.lookup.v1.RouteLookupClusterSpecifier`
(`grpc/lookup/v1/rls_config.proto`). The configuration MUST be the
serialized proto; a `TypedStruct` (JSON) form is rejected.

| Field | Rule |
| --- | --- |
| `route_lookup_config` | MUST be present; otherwise the resource is rejected. |

The plugin produces this LB policy config, where `<route_lookup_config>`
is the proto3 JSON form of `route_lookup_config` (camelCase field names,
fields with default values omitted, durations as strings such as `"10s"`):

```json
[ { "rls_experimental": {
      "routeLookupConfig": <route_lookup_config>,
      "childPolicy": [ { "cds_experimental": { "isDynamic": true } } ],
      "childPolicyConfigTargetFieldName": "cluster"
} } ]
```

The config does not set `routeLookupChannelServiceConfig`. The RLS policy
validates `routeLookupConfig` as specified in
[`rls`](../../04-client-channel/lb-policies/rls.md); an invalid
configuration rejects the resource. At run time, each target returned by
the lookup server is an xDS cluster name. The RLS policy creates a `cds`
child for it with `"cluster": "<target>"` and `"isDynamic": true`, which
subscribes to the cluster dynamically (see
[`cds`](../lb-policies/cds.md)).

## 6. RouteAction

Fields read from `envoy.config.route.v3.RouteAction`:

| Field | Rule |
| --- | --- |
| `cluster_specifier` | See [Cluster Specifier](#5-cluster-specifier). |
| `hash_policy` | See [Hash Policy](#7-hash-policy). |
| `retry_policy` | Optional; see [Retry Policy](#8-retry-policy). If absent, the virtual host's `retry_policy` (if any) is used. |
| `max_stream_duration` | Optional `MaxStreamDuration`; see [Max Stream Duration](#9-max-stream-duration). |
| `auto_host_rewrite` | `BoolValue`. Read **only** if the xDS server the resource came from has the `trusted_xds_server` server feature in the bootstrap (see [Bootstrap](../01-bootstrap.md)); otherwise it is treated as false. When true, the RPC's `:authority` is rewritten to the selected endpoint's host name (see [Client Data Plane](../04-client.md) and [xDS LB Policies](../05-lb-policies.md)). |
| `timeout` | Ignored. Its start point does not fit gRPC's deadline model. |
| `idle_timeout` | Ignored. |

All other fields (`prefix_rewrite`, `regex_rewrite`, `host_rewrite_literal`,
`host_rewrite_header`, `host_rewrite_path_regex`, `request_mirror_policies`,
`priority`, `rate_limits`, `hedge_policy`, `cluster_not_found_response_code`,
`metadata_match`, and so on) are ignored.

## 7. Hash Policy

> **Introduced by:** [gRFC A42: xDS Ring Hash LB Policy](https://github.com/grpc/proposal/blob/master/A42-xds-ring-hash-lb-policy.md)

`RouteAction.hash_policy` is an ordered list of policies that together
compute the request hash used by hash-based LB policies such as ring_hash.
Unsupported policy types are not errors: they are left out of the parsed list
and simply never produce a hash. (Envoy, by contrast, rejects them.)

| Policy type | Handling |
| --- | --- |
| `header` | Supported. `header_name` MUST be non-empty. The header value is found with the gRPC header semantics in [Common Types](01-common-types.md) ([`HeaderMatcher`](01-common-types.md#8-headermatcher)): `-bin` headers are absent, `content-type` is `application/grpc` if not yet set, multiple values are joined with `,`. If the header is absent, this policy produces no hash. |
| `header.regex_rewrite` | Optional. If present, `pattern` MUST be present, `pattern.regex` MUST be non-empty and MUST compile as RE2, otherwise the resource is rejected. Before hashing, every match of the regex in the header value is replaced with `substitution` (which may use RE2 capture-group references such as `\1`). |
| `filter_state` with `key` = `io.grpc.channel_id` | Supported. Produces a hash value that is the same for every RPC on a given channel. The value is chosen at random from a uniform distribution, once per channel (see [Client Data Plane](../04-client.md)). |
| `filter_state` with any other key | Ignored. |
| `cookie`, `connection_properties`, `query_parameter`, unknown | Ignored. |
| `terminal` | Read for every supported policy. |

This section is the canonical definition of request hash computation. The
xDS ConfigSelector evaluates the matched route's parsed hash policy list once
per RPC, as follows (the combination must be deterministic; this is the
algorithm Envoy uses):

```
hash = null
for policy in hash_policies:
  h = policy.compute(rpc)              // null if the policy yields no value
  if h != null:
    hash = (hash == null) ? h : (rotate_left(hash, 1) XOR h)
  if policy.terminal and hash != null:
    break                              // skip all subsequent policies
if hash == null:
  hash = random 64-bit value
```

A `header` policy's value is the XXH64 hash (seed 0) of the header value,
after any `regex_rewrite`. A `filter_state` (`io.grpc.channel_id`) policy's
value is the channel's random 64-bit channel ID. When no policy produces a
value, the random hash makes a hash-based LB policy pick a random endpoint.
The hash is computed once per RPC, so all LB picks for the RPC (including
retry attempts) use the same hash. It is passed to the LB policy in the
request hash call attribute (see [Client Data Plane](../04-client.md) and
[ring_hash](../../04-client-channel/lb-policies/ring_hash.md)).

## 8. Retry Policy

> **Introduced by:** [gRFC A44: gRPC xDS Retry Support](https://github.com/grpc/proposal/blob/master/A44-xds-retry.md)

A `RetryPolicy` (in `RouteAction.retry_policy` or `VirtualHost.retry_policy`)
is converted to a gRPC retry policy (see
[Retries and Hedging](../../04-client-channel/10-retries.md)):

| xDS field | Rule | gRPC retry policy |
| --- | --- | --- |
| `retry_on` | Comma-separated list of conditions. Only `cancelled`, `deadline-exceeded`, `internal`, `resource-exhausted`, and `unavailable` are recognized (mapping to the status codes of the same name). All other conditions are ignored. | `retryableStatusCodes` |
| `num_retries` | `UInt32Value`, default 1. MUST NOT be 0; otherwise the resource is rejected. | `maxAttempts = num_retries + 1`. As with any retry policy, values above the client's limit (5 attempts by default) are capped. |
| `retry_back_off` | Optional. If absent, `base_interval` = 25ms and `max_interval` = 250ms. | |
| `retry_back_off.base_interval` | MUST be present if `retry_back_off` is present. `Duration` ([`google.protobuf.Duration`](01-common-types.md#4-googleprotobufduration)); MUST be greater than 0. Values below 1ms are treated as 1ms. | `initialBackoff` |
| `retry_back_off.max_interval` | Optional, default `10 × base_interval`. `Duration`; MUST be greater than 0 and MUST NOT be less than `base_interval`. Values below 1ms are treated as 1ms. | `maxBackoff` |
| (none) | | `backoffMultiplier = 2` |

Violations of the rules above reject the resource. All other `RetryPolicy`
fields are ignored, including `per_try_timeout`, `per_try_idle_timeout`,
`retry_priority`, `retry_host_predicate`,
`host_selection_retry_max_attempts`, `retriable_status_codes`,
`retriable_headers`, `retriable_request_headers`,
`rate_limited_retry_back_off`, and `retry_options_predicates`.

A route-level `retry_policy` that is present always takes precedence over the
virtual host's, even if it yields no retryable status codes. If the resulting
`retryableStatusCodes` set is empty, the route has no retry policy, and RPCs
on it are not retried.

If the application has disabled retries on the channel, the retry policy is
still validated, but it is not used.

## 9. Max Stream Duration

> **Introduced by:** [gRFC A31: gRPC xDS Timeout Support and Config Selector Design](https://github.com/grpc/proposal/blob/master/A31-xds-timeout-support-and-config-selector.md)

`RouteAction.max_stream_duration` (`MaxStreamDuration`):

| Field | Rule |
| --- | --- |
| `grpc_timeout_header_max` | Optional `Duration` ([`google.protobuf.Duration`](01-common-types.md#4-googleprotobufduration)). If present, it is the route's maximum RPC timeout, and `max_stream_duration` is ignored. |
| `max_stream_duration` | Optional `Duration`. Used as the route's maximum RPC timeout only if `grpc_timeout_header_max` is absent. |
| `grpc_timeout_header_offset` | Ignored. |

The parsed route records at most one value: `grpc_timeout_header_max` if
present, else `max_stream_duration` if present, else nothing. If nothing is
recorded, the HCM's `common_http_protocol_options.max_stream_duration` (see
[Listener](02-listener.md)) is the fallback. A value of zero means no
limit. The effective timeout never exceeds the application's deadline. It is
computed as specified in [Client Data Plane](../04-client.md).

## 10. Parsed Resource

```
RouteConfiguration {
  virtual_hosts: list of VirtualHost {
    domains: list of string
    routes: list of Route {                 // ignored routes omitted
      matchers: {
        path_matcher: StringMatcher         // exact (path), prefix, or safe_regex,
                                            // with case sensitivity applied
        header_matchers: list of HeaderMatcher
        fraction_per_million: optional uint32
      }
      action: one of
        RouteAction {
          target: one of
            cluster_name: string
            weighted_clusters: list of { name: string, weight: uint32,
                                         typed_per_filter_config }
            cluster_specifier_plugin: string   // plugin name
          hash_policies: list of HashPolicy {
            terminal: bool
            kind: one of
              Header { header_name, regex: optional RE2, substitution }
              ChannelId
          }
          retry_policy: optional RetryPolicy {   // route's own, else vhost's
            retry_on: set of status codes
            num_retries: uint32
            base_interval: Duration
            max_interval: Duration
          }
          max_stream_duration: optional Duration
          auto_host_rewrite: bool
        }
        NonForwardingAction
        UnsupportedAction
      typed_per_filter_config: map<filter name, parsed override config>
    }
    typed_per_filter_config: map<filter name, parsed override config>
  }
  cluster_specifier_plugins: map<plugin name, LB policy config (JSON)>
                                            // only plugins named by a
                                            // parsed route
}
```

## 11. API Requirements

- The bootstrap MUST let the deployer mark an xDS server as trusted
  (`trusted_xds_server`); without that, `auto_host_rewrite` is never honored
  (see [Bootstrap](../01-bootstrap.md)).
- The channel API's existing way to disable retries (see
  [Retries and Hedging](../../04-client-channel/10-retries.md)) MUST also
  disable xDS-configured retries.
