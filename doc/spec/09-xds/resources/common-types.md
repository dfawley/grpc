> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 9.3.1 Common Types

<!-- Sources: A27, A28, A30, A36, A39, A41, A42, A44, A50, A52, A63, A75, A76, A83, A86, A95, doc/grpc_xds_features.md -->

This section defines the validation rules and gRPC semantics for xDS message
types that appear in more than one resource type. The per-resource sections
([Listener](listener.md), [RouteConfiguration](route-configuration.md),
[Cluster](cluster.md), [ClusterLoadAssignment](endpoint.md)) refer to the rules
here.

Proto references are to the Envoy API (`envoy/...`) and the CNCF xDS API
(`xds/...`, `udpa/...`).

## 1. Validation Conventions

These conventions apply to every resource type that gRPC consumes.

1. **Unknown and unsupported fields are ignored.** gRPC reads only the fields
   that this specification names. Every other field, including fields added to
   the xDS API after this specification was written, MUST be ignored. gRPC does
   not log ignored fields.
2. **Unsupported values in supported fields are rejected.** When a field that
   gRPC supports has a value that gRPC cannot honor (an unsupported enum value,
   an unsupported extension type, a value out of range), the resource MUST be
   rejected, unless the field's rules below say otherwise. Rejecting a resource
   causes the XdsClient to NACK the response that contained it. The NACK
   behavior and the handling of the other resources in the same response are
   specified in [XdsClient](../xds-client.md).
3. **All errors are collected.** A validator SHOULD report all validation
   errors it finds in a resource, not just the first. The error message is
   used in the NACK's `error_detail` and in CSDS, and is surfaced to data plane
   RPCs that fail because of it.
4. **"Ignored" entries are not validated.** When a rule says that an entry
   (for example a route, a locality, or an endpoint) is ignored or skipped,
   the entry is left out of the parsed resource. Unless the rule says
   otherwise, an implementation need not validate the rest of an ignored
   entry, and errors inside it do not cause the resource to be rejected.
5. **Wrapper types.** For fields of a `google.protobuf` wrapper type
   (`UInt32Value`, `BoolValue`, and so on), "unset" means the wrapper message
   is absent; an explicitly present zero value is distinct from unset.
6. **Parsed resources.** Each resource type has a parsed representation that
   the XdsClient delivers to its watchers. The shapes described in these
   sections are abstract; implementations may use any equivalent
   representation. Two parsed resources that compare equal SHOULD be treated as
   an unchanged resource by the XdsClient (see
   [XdsClient](../xds-client.md)).

## 2. Extensions: `google.protobuf.Any` and `TypedStruct`

Many xDS fields are extension points of type `google.protobuf.Any` (for
example `HttpFilter.typed_config`, `Cluster.transport_socket.typed_config`,
`TypedExtensionConfig.typed_config`, `typed_filter_metadata` values, and
`typed_per_filter_config` values). gRPC extracts an extension from an `Any` as
follows:

1. If the `Any` field is required and absent, the resource is rejected.
2. **Type name.** The `type_url` MUST be non-empty and MUST contain a `/`
   followed by at least one character. The *type name* is the part of the
   `type_url` after the last `/`. The prefix before the last `/` (normally
   `type.googleapis.com`) is not checked. Otherwise the resource is rejected.
3. **TypedStruct unwrapping.** If the type name is `xds.type.v3.TypedStruct`
   or `udpa.type.v1.TypedStruct`, the `value` is parsed as a `TypedStruct`
   (both have the same wire format). If it cannot be parsed, the resource is
   rejected. The extension's type name is then taken from
   `TypedStruct.type_url`, using the rule in step 2, and the extension's
   configuration is the JSON form of `TypedStruct.value`
   (`google.protobuf.Struct`). If `TypedStruct.value` is absent, the
   configuration is an empty JSON object.
4. Otherwise, the extension's configuration is the serialized protobuf in
   `Any.value`.

Each extension point then looks up the type name in its own registry (the xDS
HTTP filter registry, the xDS LB policy registry, the metadata type registry
below, or a fixed list of supported types). An extension implementation
decides whether it accepts a JSON (TypedStruct) configuration, a serialized
protobuf, or both. If it gets a form it does not accept, the resource is
rejected. For example, the `HttpConnectionManager`, `UpstreamTlsContext`, and
the metadata types below accept only the serialized protobuf form, while
custom LB policies are configured only through `TypedStruct` (see
[xDS LB Policies](../lb-policies.md)).

## 3. `ConfigSource`

`envoy.config.core.v3.ConfigSource` tells the client where to get a dependent
resource. Since gRPC supports only the aggregated (ADS) protocol, a
`ConfigSource` is valid only if it says to use the same xDS server:

| Where | Rule |
| --- | --- |
| `HttpConnectionManager.rds.config_source` | MUST be present and have either `ads` or `self` set. |
| `Cluster.eds_cluster_config.eds_config` | MUST be present and have either `ads` or `self` set. |
| `Cluster.lrs_server` | If present, MUST have `self` set. |
| `LocalityLbEndpoints.leds_cluster_locality_config.leds_config` | MUST be present and have `self` set. |

Violations cause the resource to be rejected. All other `ConfigSource` fields
(`resource_api_version`, `initial_fetch_timeout`, `authorities`, and so on) are
ignored. The dependent resource is fetched from the same xDS server and
authority rules as any other resource name (see
[XdsClient](../xds-client.md)); for `xdstp:` names the authority comes from
the name itself.

## 4. `google.protobuf.Duration`

Every `Duration` field that gRPC reads is validated as follows. If it fails,
the resource is rejected:

- `seconds` MUST be in the range [0, 315576000000].
- `nanos` MUST be in the range [0, 999999999].

Negative durations are therefore never accepted. Fields that have more
specific rules (for example the retry back-off intervals in
[RouteConfiguration](route-configuration.md)) apply those rules in addition.

## 5. Fractional Percentages

`envoy.type.v3.FractionalPercent` is normalized to a numerator per million:

| `denominator` | Normalized value |
| --- | --- |
| `HUNDRED` | `numerator × 10000` |
| `TEN_THOUSAND` | `numerator × 100` |
| `MILLION` | `numerator` |
| any other value | resource is rejected |

The result is capped at 1,000,000 (100%).

`envoy.config.core.v3.RuntimeFractionalPercent` (used by
`RouteMatch.runtime_fraction`): gRPC has no runtime configuration system, so
`runtime_key` is ignored and only `default_value` is used. If `default_value`
is absent, the fraction is treated as unset (100%).

A fraction of `N` per million is evaluated by drawing a uniformly distributed
random integer `r` in [0, 1000000) and treating the fraction as satisfied when
`r < N`.

## 6. Addresses

`envoy.config.core.v3.Address` is used for endpoint addresses (in EDS and in
the `envoy.config.core.v3.Address` metadata type). Unless a section says
otherwise (for example `LOGICAL_DNS` clusters, which carry a DNS name, see
[Cluster](cluster.md)), an `Address` is valid only if:

- The `socket_address` field is set. Addresses of other kinds (`pipe`,
  `envoy_internal_address`) are rejected.
- `socket_address.address` is an IPv4 or IPv6 address literal. Host names
  are rejected.
- The port is given in `socket_address.port_value` and is at most 65535.
  `named_port` is not supported.

All other `SocketAddress` fields (`protocol`, `resolver_name`, `ipv4_compat`,
`network_namespace_filepath`) are ignored. The parsed form is a resolved socket
address (IP and port).

## 7. `StringMatcher`

`envoy.type.matcher.v3.StringMatcher` (and the identical
`xds.type.matcher.v3.StringMatcher`) matches a string value. Exactly one of
the following MUST be set; if none is set, the resource is rejected.

| Field | Matches when |
| --- | --- |
| `exact` | the value equals the string |
| `prefix` | the value starts with the string |
| `suffix` | the value ends with the string |
| `contains` | the value contains the string as a substring |
| `safe_regex` | the value fully matches `safe_regex.regex` |

- **`ignore_case`**: if true, `exact`, `prefix`, `suffix`, and `contains`
  compare case-insensitively (ASCII case folding). `ignore_case` has no effect
  on `safe_regex`.
  <!-- REVIEW(divergence) [XDS_ROUTING-2]: Java: ignore_case ignored for safe_regex
  (xds/internal/MatcherParser.java). Go: ignored (internal/xds/matcher/string_matcher.go).
  C++: rejects safe_regex with ignore_case=true ("not supported for regex
  matcher", src/core/xds/grpc/xds_common_types_parser.cc). spec says: ignored,
  per gRFC A63 and the Java/Go majority. -->
- **`safe_regex`**: the regex uses [RE2 syntax](https://github.com/google/re2/wiki/Syntax).
  It MUST compile; otherwise the resource is rejected. The match is a full
  match: the whole value must match, as if the pattern were anchored with
  `^...$`. `RegexMatcher.engine` (`google_re2`) and the deprecated
  `max_program_size` are ignored.

## 8. `HeaderMatcher`

`envoy.config.route.v3.HeaderMatcher` matches one request header. It is used
in `RouteMatch.headers` (see [RouteConfiguration](route-configuration.md)).
Header matching in other places, such as the RBAC xDS HTTP filter, has
different header semantics, which are given in
[Authorization](../../06-security/authorization.md) (see also
[xDS HTTP Filters](../http-filters.md)).

### 8.1 Fields

| Field | Rule |
| --- | --- |
| `name` | The name of the header to match. gRPC metadata keys are lowercase, so control planes should use lowercase names. |
| `string_match` | A `StringMatcher` ([`StringMatcher`](#7-stringmatcher)), including its `ignore_case` option. |
| `exact_match` | Legacy. Equivalent to `string_match` with `exact` and `ignore_case = false`. |
| `prefix_match` | Legacy. Equivalent to `string_match` with `prefix`. |
| `suffix_match` | Legacy. Equivalent to `string_match` with `suffix`. |
| `contains_match` | Legacy. Equivalent to `string_match` with `contains`. |
| `safe_regex_match` | Legacy. Equivalent to `string_match` with `safe_regex`. The regex MUST compile. |
| `range_match` | An `Int64Range` `[start, end)`. Matches if the header value parses as a base-10 signed 64-bit integer `v` with `start <= v < end`. If `start > end`, the resource is rejected. A value that does not parse as an integer does not match. |
| `present_match` | Matches if the presence of the header equals the boolean value: `true` matches when the header is present, `false` when it is absent. |
| `invert_match` | Inverts the result of the match, subject to the absent-header rule below. |
| `treat_missing_header_as_empty` | Ignored. |

Exactly one of the match specifiers (`string_match`, the legacy fields,
`range_match`, `present_match`) MUST be set. If none is set, the resource is
rejected. The legacy fields are always case-sensitive. They are deprecated in
the xDS API, but gRPC MUST continue to support them.

### 8.2 Evaluation

```
match(header_matcher, request):
  value = header_value(request, header_matcher.name)   // see below; may be ABSENT
  if header_matcher is present_match:
    result = (value != ABSENT) == present_match
  else if value == ABSENT:
    return false              // never matches, even with invert_match
  else if header_matcher is range_match:
    result = value parses as int64 v and start <= v < end
  else:
    result = string_matcher.match(value)
  return result != invert_match
```

So a missing header never matches a value-based matcher, whether or not
`invert_match` is set. A `present_match` matcher with
`present_match == invert_match` matches a missing header.

### 8.3 gRPC Header Semantics

Client-side routing runs above the transport, before load balancing, so it
sees the RPC's metadata rather than HTTP/2 header frames. `header_value()` is
defined as follows:

1. **Binary headers.** If the name ends in `-bin`, the header is treated as
   absent, even if the RPC has metadata with that name.
2. **`content-type`.** The value is the content type that will be sent on the
   wire. If the implementation has not set it when routing happens, the value
   is the fixed string `application/grpc`.
3. **Pseudo-headers** (names starting with `:`, such as `:authority`,
   `:path`, `:method`, `:scheme`) are treated as absent. The method name is
   matched by `RouteMatch`'s path specifier instead.
   <!-- REVIEW(divergence) [XDS_ROUTING-1]: Java: content-type is "application/grpc", -bin and
   any name that is not a valid metadata key (all pseudo-headers) are absent
   (xds/RoutingUtils.java getHeaderValue). Go: matches against outgoing
   metadata plus the extra content-type metadata, -bin removed; no
   :authority/host special case (internal/xds/resolver/serviceconfig.go).
   C++: ":authority" and "host" are aliases for the call's authority; other
   names are looked up in the metadata batch (src/core/xds/grpc/xds_routing.cc
   GetHeaderValue). spec says: all pseudo-headers absent and "host" is ordinary
   metadata, per gRFC A28 and the Java/Go majority (previously chose the C++
   aliasing). -->
4. **Multiple values.** If the metadata has more than one value for the name,
   the values are joined in order with `,` (a comma with no added space), and
   the matcher is applied to the joined string.
5. Otherwise the value is the application-supplied metadata value, or absent
   if there is none.

The same `header_value()` definition is used by the `header` hash policy in
`RouteAction.hash_policy` (see [RouteConfiguration](route-configuration.md)).

## 9. Metadata

`envoy.config.core.v3.Metadata` attaches typed or untyped data to a resource.
gRPC parses metadata in these places:

| Field | Consumers |
| --- | --- |
| `Cluster.metadata` | GCP authentication xDS HTTP filter (audience) |
| `LbEndpoint.metadata` | ring_hash endpoint hash key; HTTP CONNECT proxy address |
| `LocalityLbEndpoints.metadata` | HTTP CONNECT proxy address |

A `Metadata` message contains two maps, both keyed by a string (normally a
filter or extension name):

- `filter_metadata`: `map<string, google.protobuf.Struct>`.
- `typed_filter_metadata`: `map<string, google.protobuf.Any>`.

### 9.1 Parsing

The parsed form is a single map from key to a *metadata value*. Each value
records the protobuf type it came from and a parsed form of its content. An
absent `Metadata` message parses to an empty map.

```
parse_metadata(metadata):
  parsed = {}
  for key, any in metadata.typed_filter_metadata:
    ext = extract_extension(any)        // see "Extensions"; failure rejects the resource
    parser = metadata_registry.find(ext.type_name)
    if parser is null:
      continue                          // unknown type: ignored
    value = parser.parse(ext)
    if value is error:
      reject resource
    parsed[key] = value
  for key, struct in metadata.filter_metadata:
    if key not in parsed:
      parsed[key] = { type: "google.protobuf.Struct", json: to_json(struct) }
  return parsed
```

For a given key, the value comes from exactly one of the two maps.
`typed_filter_metadata` takes precedence. The `filter_metadata` entry is used
only when the key is absent from `typed_filter_metadata` or its value has a
type that is not in the registry.

### 9.2 Metadata Type Registry

The metadata type registry maps a protobuf type name to a parser. It is
internal to gRPC: it may be a real registry or simply code that knows the
supported types. The following types MUST be supported:

| Type name | Validation | Parsed form |
| --- | --- | --- |
| `envoy.extensions.filters.http.gcp_authn.v3.Audience` | `url` MUST be non-empty. | The `url` string. |
| `envoy.config.core.v3.Address` | `socket_address` MUST be set. Inside it, `address` MUST be an IPv4 or IPv6 literal and `port_value` MUST be set ([Addresses](#6-addresses)). | The socket address (IP and port). |

The registered parsers accept only the serialized protobuf form of the `Any`.
A `TypedStruct` whose inner type is a registered type is rejected.

### 9.3 Lookups

Consumers look up a metadata value by key and expected type. A value with a
different type is treated as not found, except where a consumer says
otherwise:

| Key | Expected type | Used for | Defined in |
| --- | --- | --- | --- |
| the `HttpFilter.name` of a GCP authentication filter instance | `Audience` | Audience for the identity token. A value of the wrong type fails RPCs. | [xDS HTTP Filters](../http-filters.md) |
| `envoy.lb` | `google.protobuf.Struct` | String field `hash_key`: endpoint hash key for ring_hash | [ClusterLoadAssignment](endpoint.md) |
| `envoy.http11_proxy_transport_socket.proxy_address` | `Address` | HTTP CONNECT proxy for the endpoint | [ClusterLoadAssignment](endpoint.md), [Cluster](cluster.md) |

## 10. Health Status

`envoy.config.core.v3.HealthStatus` values that gRPC understands, as used in
`LbEndpoint.health_status` and `Cluster.common_lb_config.override_host_status`:

| Value | gRPC handling |
| --- | --- |
| `UNKNOWN` | Usable endpoint. |
| `HEALTHY` | Usable endpoint. |
| `DRAINING` | Kept in the parsed resource. Not used for new load-balancing decisions, but may still be used for stateful session affinity (see [xDS LB Policies](../lb-policies.md)). |
| `UNHEALTHY`, `TIMEOUT`, `DEGRADED`, any other value | Not supported. In EDS the endpoint is ignored; in `override_host_status` the value is ignored. |

## 11. API Requirements

The types in this section are internal to gRPC's xDS support. No public API
is required for them. In particular, the metadata type registry is not
extensible by applications.
