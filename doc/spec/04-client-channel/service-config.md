# Service Config

<!-- Sources: doc/service_config.md, grpc-proto grpc/service_config/service_config.proto, A2, A6, A17, A21, A24, A105 -->

The **service config** lets a service owner publish settings that every client
of the service applies automatically. Examples are the LB policy and its
config, per-method timeouts and `wait_for_ready` defaults, message size
limits, and retry or hedging policies. The service config belongs to a
target (server name). It is normally delivered by the name resolver, so the
service owner can change it without touching each client.

## 1. Format

The schema is the `grpc.service_config.ServiceConfig` message in
`grpc/service_config/service_config.proto`. gRPC does not consume the proto
form. It consumes the **JSON** form, produced by the standard
[proto3 JSON mapping](https://protobuf.dev/programming-guides/proto3/#json). So:

- Field names are converted from `snake_case` to `lowerCamelCase`, for
  example `method_config` becomes `methodConfig`. Fields with an explicit
  `json_name` use that name. Parsers MUST accept the `lowerCamelCase`
  names.
- Strings, bools, and 32-bit integers become the corresponding JSON types.
  64-bit integers are JSON strings (for example `"251"`). Parsers MUST also
  accept JSON numbers for them.
- Repeated fields are JSON arrays. Maps are JSON objects.
- A `google.protobuf.Duration` is a JSON string holding a decimal number of
  seconds with an `s` suffix and at most 9 fractional digits, for example
  `"1.5s"` or `"0.000340012s"`.
- Wrapper types (`google.protobuf.BoolValue`, `UInt32Value`, `StringValue`,
  and so on) are the bare JSON value. An absent wrapper field means "not
  set".
- Status codes (`google.rpc.Code`) are given as the integer code or as the
  code name in any letter case, for example `14`, `"UNAVAILABLE"`, or
  `"unavailable"`.

The JSON form can also express LB policies that the proto does not define.
In the proto, each `LoadBalancingConfig` entry is a `oneof` over the policies
known to the proto. In JSON, each entry is an object whose single key is the
LB policy name. That key can be any string, so third-party and custom LB
policies can be named and configured ([`loadBalancingConfig`](#52-loadbalancingconfig)).

A service config delivered in DNS TXT records must be ASCII (see
[name-resolution.md](name-resolution.md)).

Example:

```json
{
  "loadBalancingConfig": [ { "round_robin": {} } ],
  "methodConfig": [
    {
      "name": [
        { "service": "foo.Foo", "method": "Bar" },
        { "service": "baz.Baz" }
      ],
      "timeout": "1.000000001s",
      "waitForReady": true,
      "retryPolicy": {
        "maxAttempts": 3,
        "initialBackoff": "0.1s",
        "maxBackoff": "1s",
        "backoffMultiplier": 2,
        "retryableStatusCodes": [ "UNAVAILABLE" ]
      }
    }
  ],
  "retryThrottling": { "maxTokens": 10, "tokenRatio": 0.1 }
}
```

## 2. Delivery

A channel gets its service config from one of these sources:

1. **The resolver.** This is the recommended way. The resolver parses the
   config with the channel's parse operation and returns the parsed config,
   an error, or nothing ([name-resolution.md](name-resolution.md)). For
   example, the `dns` resolver reads the config from TXT records and supports
   canary rollouts with *service config choices*. That mechanism is
   specified in [name-resolution.md](name-resolution.md#72-service-config-in-dns).
2. **The default service config**, a JSON string set through the channel API.
   It is used when the resolver returns no service config, or when service
   config lookup is disabled. If the application does not set it, the default
   service config is `{}`. The default service config is validated at channel
   creation, and an invalid one MUST cause channel creation to fail.
3. **Nothing.** With no resolver config and no default set, the channel uses
   the empty config `{}`, which is valid: `pick_first`, no method configs, no
   retries.

The application can disable service config lookup through the channel API
([channel.md](channel.md)). Resolvers then do not fetch a published config,
and the channel uses the default service config.

When a new service config is applied, RPCs started after that use it. RPCs
that have already been assigned a method config keep it for their whole life.
That includes their remaining retry and hedging attempts.

## 3. Validation and Error Handling

The rules in this section apply to every service config, whether it comes
from a resolver or from the default service config option.

1. The config MUST be well-formed JSON, and its top level MUST be a JSON
   object. Otherwise the config is invalid.
2. **Unknown fields are ignored**, at every level of the service config. They
   do not affect validation. This lets new fields be added without breaking
   older clients.
3. Every field the client recognizes is validated against its rules
   ([Field Reference](#5-field-reference)). If **any** recognized field fails
   validation, the **whole** service config is invalid. The client MUST NOT
   apply part of a config, ignore an invalid field, or substitute a default
   value for it.
4. When different clients may support different values for a field, the
   field is defined as a list that each client searches for the first value
   it supports. `loadBalancingConfig` is the main example.

Validation happens when the config is parsed, which is usually inside the
resolver. A parsed config that has been accepted never fails when it is
applied.

The scope of rule 2 is the service config itself. Inside the DNS service
config choice wrapper, unknown fields **invalidate** the whole result (see
[name-resolution.md](name-resolution.md#72-service-config-in-dns)).

How the channel reacts to an invalid config:

| Situation | Behavior |
| --- | --- |
| Resolver returns an invalid config, and the channel already has a valid config (from the resolver, or the default config used because the resolver returned none) | The channel keeps using the previous config. It still passes the new endpoints to the LB policy, configured from the previous config. |
| Resolver returns an invalid config, and the channel has never had a valid config | The channel reports `TRANSIENT_FAILURE`. RPCs without `wait_for_ready` that are waiting for a resolver result fail with the error status, after the control plane status restriction ([call-dispatch.md](call-dispatch.md)). The resolver is told the result was rejected, so a polling resolver retries with backoff. The default service config is **not** used as a fallback. |
| Resolver returns no config | The channel uses the default service config (`{}` if none is set). |
| Invalid default service config | Channel creation fails. |

The exact algorithm is in [name-resolution.md](name-resolution.md#3-channel-handling-of-resolver-results).

<!-- REVIEW(divergence) [SERVICE_CONFIG-3]: gRFC A21 conflicts with itself: step 5 says a client with no previous valid config "treats the resolution attempt as having failed" and stays in TRANSIENT_FAILURE; its "Service Config Channel Arguments" section says to fall back to the default service config if one is provided. C++: keeps saved config if any, else TRANSIENT_FAILURE, default ignored (client_channel.cc OnResolverResultChangedLocked). Go: same, applyFailingLBLocked with UNAVAILABLE, despite the WithDefaultServiceConfig godoc (clientconn.go updateResolverStateAndUnlock; test/resolver_update_test.go). Java: invalid config falls back to the default whenever one is set, even replacing a previous valid config; with no default it matches C++/Go (ManagedChannelImpl.onResult2). spec says: no fallback (matches C++ and Go). -->

## 4. Method Config Selection

For each RPC, the default ConfigSelector ([call-dispatch.md](call-dispatch.md))
looks up the `MethodConfig` for the RPC's full method name `/service/method`.
The most specific match wins:

1. An entry whose `name` has both `service` and `method` equal to the RPC's
   service and method.
2. Otherwise, an entry whose `name` has `service` equal to the RPC's service
   and an empty `method`. This is the default for all methods of that
   service.
3. Otherwise, an entry whose `name` has both `service` and `method` empty.
   This is the default for all methods.
4. Otherwise, the RPC has no method config.

Matching is exact and case-sensitive. `service` is the fully qualified service
name, including the proto package (for example `grpc.health.v1.Health`). The
RPC uses only the fields of the matched entry. It does not merge in fields
from less specific entries.

## 5. Field Reference

### 5.1 `ServiceConfig` (top level)

| JSON field | Type | Default | Description and validation |
| --- | --- | --- | --- |
| `loadBalancingConfig` | array of `LoadBalancingConfig` | unset | Selects and configures the LB policy ([`loadBalancingConfig`](#52-loadbalancingconfig)). |
| `loadBalancingPolicy` | string | unset | **Deprecated.** Names an LB policy that needs no config ([`loadBalancingPolicy` (deprecated)](#53-loadbalancingpolicy-deprecated)). Ignored if `loadBalancingConfig` is set. |
| `methodConfig` | array of `MethodConfig` | empty | Per-method settings ([`methodConfig`](#54-methodconfig)). |
| `retryThrottling` | `RetryThrottlingPolicy` | unset (no throttling) | Throttles retries and hedging for the channel. Fields `maxTokens` and `tokenRatio`. Validation and semantics are in [retries.md](retries.md). |
| `healthCheckConfig` | `HealthCheckConfig` | unset (no health checking) | Client-side health checking ([`healthCheckConfig`](#55-healthcheckconfig)). |
| `connectionScaling` | `ConnectionScaling` | unset | Dynamic connection scaling ([`connectionScaling`](#56-connectionscaling)). |

### 5.2 `loadBalancingConfig`

`loadBalancingConfig` is a JSON array. Each element is a JSON object with
**exactly one** key. The key is an LB policy name, and its value is that
policy's config object:

```json
"loadBalancingConfig": [
  { "my_custom_policy": { "someSetting": 5 } },
  { "round_robin": {} }
]
```

The client processes it as follows:

1. If the field is not an array, if any element is not an object with exactly
   one key, or if the array is empty, the service config is invalid.
2. The client walks the list in order and skips entries whose policy name is
   not registered in the LB policy registry (see
   [load-balancing.md](load-balancing.md)). Policy names are case-sensitive.
3. The first entry with a registered name is **selected**. Its config object
   is parsed and validated by that policy's config parser. If that fails,
   the service config is invalid. Entries after the selected one are not
   examined.
4. If no entry has a registered name, the service config is invalid.

<!-- REVIEW(divergence) [SERVICE_CONFIG-4]: C++: empty list is invalid, "No known policies in list" (lb_policy_registry.cc ParseLoadBalancingConfigHelper). Go: invalid, "no supported policies found" (service_config.go falls back to loadBalancingPolicy only when the field is nil; gracefulswitch/config.go). Java: empty list treated as unset, falls back to loadBalancingPolicy / pick_first (ServiceConfigUtil.getLoadBalancingConfigsFromServiceConfig). spec says: invalid (matches C++ and Go). -->

This lets a service owner list a new or custom policy first, with a
widely supported fallback after it. Clients that do not have the first policy
fall through to the next.

**Nested policies.** Many LB policies delegate to child policies. Their
configs contain fields (usually `childPolicy`) of the same
array-of-`LoadBalancingConfig` type, with the same semantics: the first
registered policy is selected, its config must be valid, and the list is
invalid if no policy is registered. The parent policy's parser validates them
recursively, so an invalid nested config makes the whole service config
invalid.

**Policy config schemas.** Each LB policy defines its own registered name and
config schema:

- [pick_first](lb-policies/pick_first.md)
- [round_robin](lb-policies/round_robin.md)
- [weighted_round_robin](lb-policies/weighted_round_robin.md)
- [least_request](lb-policies/least_request.md)
- [ring_hash](lb-policies/ring_hash.md)
- [random_subsetting](lb-policies/random_subsetting.md)
- [outlier_detection](lb-policies/outlier_detection.md)
- [priority](lb-policies/priority.md)
- [weighted_target](lb-policies/weighted_target.md)
- xDS LB policies: [lb-policies.md](../09-xds/lb-policies.md)

Some registered policies are internal. They need inputs that only another
gRPC component provides, for example the xDS policies. Their parsers MAY
reject configs that do not come from that component.

### 5.3 `loadBalancingPolicy` (deprecated)

- A JSON string naming an LB policy, matched **case-insensitively** against
  the registered policy names. For example, `"round_robin"` and
  `"ROUND_ROBIN"` both select `round_robin`.
- It is used only if `loadBalancingConfig` is unset. In that case the named
  policy is used with an empty config.
- If `loadBalancingConfig` is unset and `loadBalancingPolicy` names a policy
  that is not registered, or a policy that cannot run with an empty config,
  the service config is invalid.

### 5.4 `methodConfig`

`methodConfig` is a JSON array of `MethodConfig` objects:

| JSON field | Type | Default | Description and validation |
| --- | --- | --- | --- |
| `name` | array of `Name` | empty | The methods this entry applies to. See the rules below. |
| `waitForReady` | bool | unset | Default `wait_for_ready` for matching RPCs ([channel.md](channel.md#8-wait_for_ready)). Used only when the application did not set `wait_for_ready` on the RPC. A value the application sets explicitly always wins. |
| `timeout` | Duration | unset | Default timeout for matching RPCs. The RPC's deadline is the earlier of the application's deadline (if any) and the RPC's start time plus `timeout`. If neither is set, the RPC has no deadline. Must be a valid Duration and MUST NOT be negative; a negative value (including one with a zero seconds part, such as `"-0.5s"`) makes the service config invalid. |
| `maxRequestMessageBytes` | uint32 | unset | Largest request message, in bytes, the client may send on matching RPCs. The limit applies to each message after per-message compression. The effective limit is the smaller of this value and the channel's max send message size. Either one alone applies if the other is unset. `0` is valid and allows only empty messages. Must be a non-negative integer that fits in 32 bits. |
| `maxResponseMessageBytes` | uint32 | unset | Largest response message, in bytes, the client accepts on matching RPCs. Same rules as `maxRequestMessageBytes`, combined with the channel's max receive message size. |
| `retryPolicy` | `RetryPolicy` | unset | Retry policy for matching RPCs. Validation and semantics are in [retries.md](retries.md). |
| `hedgingPolicy` | `HedgingPolicy` | unset | Hedging policy for matching RPCs. Validation and semantics are in [retries.md](retries.md). |

If both `retryPolicy` and `hedgingPolicy` are set in the same entry, the
service config is invalid. If neither is set, matching RPCs get no
configurable retries or hedging. Transparent retries still apply (see
[retries.md](retries.md)).

An RPC that tries to send a message larger than its effective
`maxRequestMessageBytes` fails without sending it. An RPC that receives a
message larger than its effective `maxResponseMessageBytes` fails. Both
failures use status `RESOURCE_EXHAUSTED` (see
[Core RPC Semantics](../02-rpc-semantics.md)).

**`Name` objects** have two string fields, `service` and `method`. In JSON,
an absent field, `null`, and `""` all mean the same thing (empty). The rules
are:

- A `MethodConfig` whose `name` list is absent or empty applies to no RPCs
  and is skipped. Its other fields are still validated.
- If `service` is empty, `method` MUST also be empty. Such a `Name` is the
  default for all methods. A `Name` with an empty `service` and a non-empty
  `method` makes the service config invalid.
- If `service` is set and `method` is empty, the `Name` is the default for
  all methods of that service.
- If both are set, the `Name` matches exactly one method.
- Each `Name` MUST be unique across the **whole** service config, within one
  `MethodConfig` and across different ones. Two `Name` entries with the same
  (`service`, `method`) pair, after treating absent, `null`, and `""` as
  equal, make the service config invalid.

How an RPC is matched to an entry is in [Method Config Selection](#4-method-config-selection).

### 5.5 `healthCheckConfig`

| JSON field | Type | Default | Description and validation |
| --- | --- | --- | --- |
| `serviceName` | string | unset | Service name sent in client-side health checking requests. If it is unset, health checking is disabled. The empty string is a valid value and asks about the server's overall health. Must be a JSON string if present. |

Client-side health checking takes effect only under LB policies that use it.
The full behavior is in [health-checking.md](health-checking.md).

### 5.6 `connectionScaling`

| JSON field | Type | Default | Description and validation |
| --- | --- | --- | --- |
| `maxConnectionsPerSubchannel` | uint32 | unset (1) | Maximum number of connections gRPC keeps per subchannel on this channel. When every existing connection of a subchannel is at its `MAX_CONCURRENT_STREAMS` limit, gRPC opens more connections, up to this limit. Values above the channel's client-side limit (10 by default, configurable through the channel API) are clamped to that limit. A value of 0 is treated as unset (1). |

A change to this value applies to existing subchannels. Lowering it does not
close connections. The number of connections drops only as connections end
naturally. The behavior is specified in [subchannels.md](subchannels.md).

## 6. API Requirements

- The channel API MUST provide an option to set the default service config as
  a JSON string ([Delivery](#2-delivery)). Channel creation MUST fail if that
  config is invalid.
- The channel API MUST provide an option to disable service config lookup
  ([Delivery](#2-delivery)). In some implementations this option also makes
  the channel ignore the service config from every resolver, so it is not
  compatible with the xDS resolver there
  ([name-resolution.md](name-resolution.md)).
- The resolver API MUST give resolvers an operation that parses and validates
  a service config JSON string and returns either a parsed config or an error
  ([name-resolution.md](name-resolution.md)). This operation MUST apply
  exactly the rules in [Validation and Error Handling](#3-validation-and-error-handling) and
  [Field Reference](#5-field-reference), including the LB policy config parsers of
  all registered LB policies.
- The LB policy registration API MUST let each LB policy provide a parser for
  its JSON config, which the service config parser calls
  ([load-balancing.md](load-balancing.md)).
- gRPC MUST provide a way for the application to read the service config the
  channel is currently using, for debugging.
