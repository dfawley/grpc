> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 6.4 Authorization

<!-- Sources: A41, A43, A59 -->

gRPC servers can authorize each RPC against a policy. There are two ways to
configure policies, and both run on the same **RBAC engine**:

- the **gRPC authorization policy**, a JSON policy language that the
  application supplies ([gRPC Authorization Policy](#2-grpc-authorization-policy)); and
- the **xDS RBAC HTTP filter**, configured by an xDS control plane on
  xDS-enabled servers. Its xDS configuration details are in
  [xDS HTTP Filters](../09-xds/07-http-filters.md).

Both can be active on one server. An RPC proceeds only if every configured
authorization engine allows it.

Authorization runs on the server, per RPC, after the request headers arrive
and before the handler is invoked. gRPC applies it per RPC (for example,
through interceptors). This specification does not prescribe the mechanism.
A denied RPC fails with status `PERMISSION_DENIED`. The handler is not
invoked.

## 1. RBAC Engine

> **Introduced by:** [gRFC A41: xDS RBAC Support](https://github.com/grpc/proposal/blob/master/A41-xds-rbac.md)

The RBAC engine evaluates the semantics of the Envoy RBAC policy
(`envoy/config/rbac/v3/rbac.proto`) against a gRPC request. Shadow rules and
CEL conditions are not supported.

### 1.1 Engine Decision

An engine has an **action** (`ALLOW` or `DENY`) and a map of named
**policies**. Each policy has a list of permissions and a list of principals.
A policy matches a request when at least one of its permissions matches and
at least one of its principals matches.

| Action | Some policy matches | No policy matches |
|--------|---------------------|-------------------|
| `ALLOW` | Allow | Deny |
| `DENY` | Deny | Allow |

When an engine has several policies that match, the reported matched policy
name (used in audit logging) MAY be any one of them.

A chain of engines is evaluated in order. Evaluation stops at the first
engine that denies, and the RPC is denied. If every engine allows, the RPC is
allowed.

Permission and principal matchers can be combined with AND, OR, and NOT. So
every matcher MUST be evaluated as specified, including matchers that can
never match. They MUST NOT be optimized away.

### 1.2 Request Attributes

The engine sees these attributes of a gRPC request:

| Attribute | Value |
|-----------|-------|
| Path (`url_path`) | The full method name with leading slash, `/package.Service/Method`. This is the same as `:path`. |
| Headers | The request metadata, with the adjustments in [Header Matching Rules](#13-header-matching-rules). |
| Destination IP and port | The local address and port of the connection. |
| Source / direct remote / remote IP | The peer address of the connection. All three are the same: gRPC does not use PROXY protocol or trust `x-forwarded-for` for this. |
| Requested server name | Always the empty string. A matcher on it matches only if it accepts `""`. |
| Envoy dynamic metadata | Always an empty map. `metadata` matchers never match unless `MetadataMatcher.invert` is `true` (which inverts the non-match to a match). |
| Authenticated principal | Derived from the connection's TLS state ([Authenticated Principal Matching](#14-authenticated-principal-matching)). |

### 1.3 Header Matching Rules

- Header names are matched **case-insensitively** (HTTP/2 header names are
  lowercase on the wire).
- `:method`, `:authority`, and `:path` can be matched. They MUST match the
  values received on the wire, even if the implementation stores them outside
  the metadata. If `:method` is not available, it MAY be treated as `POST`,
  because the server rejects requests with any other method.
- `:authority` and `Host` are the same header for matching. A matcher behaves
  the same whichever of the two names it uses. On the transport side, if a
  request has no `:authority`, gRPC renames `Host` to `:authority`. If it has
  `:authority`, gRPC drops `Host`. A request with more than one `:authority`,
  or more than one `Host`, is rejected (see
  [gRPC over HTTP/2](../03-wire-protocol/01-http2.md)). So every request has
  exactly one authority.
- Hop-by-hop headers (RFC 9110 §7.6.1) are treated as absent. HTTP/2 requests
  that carry `Connection` never reach the engine (RFC 9113 §8.2.2). If the
  transport exposes `TE` in metadata, the engine MUST treat `TE` as absent.
- `Content-Type` is the value the client sent, not a fixed value.
- If a header has several values, they are joined with `,` (a comma, no
  added spaces) and matched as one value.
- Binary headers (`-bin` suffix) are matched in their unpadded base64-encoded
  form (RFC 4648 §4, with no `=` padding). Each value is encoded separately;
  multiple values are then joined as described above.
- If a header is absent, a header matcher does not match. The exception is a
  `present_match` whose value equals its `invert_match` flag, which does
  match. (`invert_match` inverts the comparison itself, so for example an
  inverted `exact_match` does not match an absent header.)
- Matchers on headers with the `grpc-` prefix, and on `:scheme`, are not
  allowed (names are compared case-insensitively). Configurations that contain
  them are invalid.

### 1.4 Authenticated Principal Matching

An `authenticated` principal matcher, with an optional string matcher on
`principal_name`, works like this:

```
match_authenticated(conn, principal_name_matcher):
  if conn is not TLS:
    return false
  if principal_name_matcher is unset:
    return true                       # any TLS connection, with or without client cert
  if conn has no client certificate:
    return principal_name_matcher.match("")
  cert = client leaf certificate
  return (any(principal_name_matcher.match(uri) for each URI SAN in cert) or
          any(principal_name_matcher.match(dns) for each DNS SAN in cert) or
          principal_name_matcher.match(cert.subject as RFC 2253 string))
```

The matcher matches if any URI SAN, any DNS SAN, or the subject (in RFC 2253
format) of the client certificate matches. All three are always checked, so a
certificate whose URI SANs do not match can still match on a DNS SAN or its
subject.

## 2. gRPC Authorization Policy

> **Introduced by:** [gRFC A43: gRPC authorization API](https://github.com/grpc/proposal/blob/master/A43-grpc-authorization-api.md)

The gRPC authorization policy is a JSON document. gRPC translates it into two
RBAC engines: a `DENY` engine built from `deny_rules` (if present and
non-empty), followed by an `ALLOW` engine built from `allow_rules`.

### 2.1 Schema

```json
{
  "name": "example_authz_policy",
  "deny_rules": [
    {
      "name": "deny_blocked_users",
      "source": {
        "principals": [ "spiffe://example.com/blocked/*" ]
      },
      "request": {
        "paths": [ "/pkg.Service/*" ],
        "headers": [
          { "key": "x-env", "values": [ "prod" ] }
        ]
      }
    }
  ],
  "allow_rules": [
    {
      "name": "allow_authenticated",
      "source": {
        "principals": [ "*" ]
      }
    }
  ],
  "audit_logging_options": {
    "audit_condition": "ON_DENY",
    "audit_loggers": [
      { "name": "stdout_logger", "config": {}, "is_optional": false }
    ]
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `name` | string | Yes | — | Policy name for monitoring, error messages, and audit logs. MUST NOT be empty. |
| `deny_rules` | list of object | No | `[]` | Deny rule objects. An empty array is the same as absent. |
| `allow_rules` | list of object | Yes | — | Allow rule objects. MUST NOT be empty. |
| `deny_rules[].name`, `allow_rules[].name` | string | Yes | — | Rule name; MUST be non-empty and SHOULD be unique within its list. |
| `deny_rules[].source`, `allow_rules[].source` | object | No | — | Peer matching criteria. If absent, matches any peer. |
| `deny_rules[].source.principals`, `allow_rules[].source.principals` | list of string | No | `[]` | OR: matches if any pattern ([Pattern Syntax](#22-pattern-syntax)) matches the authenticated principal ([Authenticated Principal Matching](#14-authenticated-principal-matching)). An empty array is the same as absent. |
| `deny_rules[].request`, `allow_rules[].request` | object | No | — | Request matching criteria. If absent, matches any request. |
| `deny_rules[].request.paths`, `allow_rules[].request.paths` | list of string | No | `[]` | OR: matches if any pattern matches the full method name `/package.Service/Method`. An empty array is the same as absent. |
| `deny_rules[].request.headers`, `allow_rules[].request.headers` | list of object | No | `[]` | AND: matches only if every entry matches. An empty array is the same as absent. |
| `deny_rules[].request.headers[].key`, `allow_rules[].request.headers[].key` | string | Yes | — | Header name; MUST NOT be a disallowed header (below). |
| `deny_rules[].request.headers[].values`, `allow_rules[].request.headers[].values` | list of string | Yes | — | MUST NOT be empty. OR: matches if any pattern matches the header value ([Header Matching Rules](#13-header-matching-rules)). |
| `audit_logging_options` | object | No | — | Audit logging configuration ([Audit Options in the gRPC Authorization Policy](#33-audit-options-in-the-grpc-authorization-policy)). |

If two rules in the same list have the same `name`, the policy is still valid.
The later rule replaces the earlier one, and the earlier rule is ignored.

Within a rule, `source` and `request` are ANDed. Within `request`, `paths`
and `headers` are ANDed. A rule with neither `source` nor `request` matches
every RPC.

**Disallowed header keys.** A policy is invalid if a header `key` is any of:
a name starting with `:` (pseudo-headers), a name starting with `grpc-`,
`host`, or a hop-by-hop header (`connection`, `keep-alive`,
`proxy-authenticate`, `proxy-authorization`, `te`, `trailer`,
`transfer-encoding`, `upgrade`). Names are compared case-insensitively.

**Unknown fields.** Any field the implementation does not recognize, at any
level, makes the policy invalid. New fields may be added in the future. A
version of gRPC that does not understand them MUST reject the policy, rather
than ignore restrictions it cannot evaluate. This rule doesn't cover the
contents of `audit_loggers[].config`, which the logger validates
([Audit Options in the gRPC Authorization Policy](#33-audit-options-in-the-grpc-authorization-policy)).

**Type errors.** A field with the wrong JSON type makes the policy invalid.

### 2.2 Pattern Syntax

`principals`, `paths`, and header `values` use the same pattern syntax:

| Pattern | Match type | Matches |
|---------|-----------|---------|
| `*` | Presence | Any non-empty value |
| `*abc` | Suffix | Values ending in `abc` (including `abc`) |
| `abc*` | Prefix | Values starting with `abc` (including `abc`) |
| `abc` | Exact | Exactly `abc` |

Matching is case-sensitive. The empty pattern `""` is an exact match on the
empty string. For example, the principal `""` matches a TLS connection with no
client certificate.

<!-- REVIEW(divergence) [AUTHZ-20]: Patterns with more than one `*` or an interior `*` are neither rejected nor interpreted consistently. C++ (`GetMatcherType`) and Java (`getStringMatcher`) test a leading `*` first, so `*abc*` becomes suffix `abc*` and `**` becomes suffix `*`. Go (`getStringMatcher`/`getHeaderMatcher`) tests a trailing `*` first, so `*abc*` becomes prefix `*abc` and `**` becomes prefix `*`. All three treat `a*b` as the exact string `a*b`. Decide whether such patterns make the policy invalid or which interpretation is specified. -->

### 2.3 Decision Logic

1. If any deny rule matches, the RPC is denied.
2. Otherwise, if any allow rule matches, the RPC is allowed.
3. Otherwise, the RPC is denied.

### 2.4 Translation to RBAC

| Policy element | RBAC equivalent |
|----------------|-----------------|
| `deny_rules` | Engine with action `DENY`. One policy per rule, keyed by rule name. |
| `allow_rules` | Engine with action `ALLOW`. One policy per rule, keyed by rule name. |
| `source.principals` | OR of `authenticated.principal_name` matchers. Absent or empty means `any`. |
| `request.paths` | OR of `url_path` matchers. |
| `request.headers` | AND of entries. Each entry is an OR of header matchers on `key`. |
| `request` absent or empty | Permission `any` |
| policy `name` | Engine name (reported as the audit policy name) |

### 2.5 Example

```json
{
  "name": "example-policy",
  "allow_rules": [
    {
      "name": "admin-access",
      "source": { "principals": ["spiffe://foo.com/sa/admin1", "spiffe://foo.com/sa/admin2"] },
      "request": { "paths": ["/pkg.service/*"] }
    },
    {
      "name": "dev-access",
      "source": { "principals": ["*", ""] },
      "request": {
        "paths": ["/pkg.service/foo", "/pkg.service/bar"],
        "headers": [ { "key": "dev-path", "values": ["/dev/path/*"] } ]
      }
    }
  ],
  "deny_rules": [
    { "name": "deny-access", "request": { "paths": ["*/secret"] } }
  ]
}
```

### 2.6 Policy Providers

The application gives the policy to the server through a *policy provider*:

- **Static provider:** created from a policy JSON string. If the policy is
  invalid, creation fails and returns the error to the application.
- **File-watcher provider:** created from a file path and a refresh interval.
  It reads the file when it is created, then once per refresh interval.
  - If the first read fails (I/O error or invalid policy), creation fails and
    returns the error. Typically the server then does not start.
  - If a later read fails, that reload is skipped. The error is logged, and
    the last valid policy stays in effect.
  - A valid new policy replaces the old one for RPCs that start after the
    swap.
  - The provider MUST provide a way to stop the periodic reload and release
    its resources.

A server SHOULD use at most one gRPC authorization policy. If several are
installed, each is evaluated in turn, and an RPC is allowed only if all allow
it. A policy written for one service then denies RPCs for other services by
default.

When a gRPC authorization policy is used on an xDS-enabled server that also
runs xDS RBAC, an RPC is allowed only if both allow it.

## 3. Audit Logging

> **Introduced by:** [gRFC A59: gRPC Audit Logging](https://github.com/grpc/proposal/blob/master/A59-audit-logging.md)

Audit logging records authorization decisions. It is configured per RBAC
engine with an **audit condition** and a list of **audit loggers**.

### 3.1 Audit Conditions

The condition refers to the engine's *decision*, not its action:

| Condition | Log when |
|-----------|----------|
| `NONE` | Never |
| `ON_DENY` | The engine denies the RPC |
| `ON_ALLOW` | The engine allows the RPC |
| `ON_DENY_AND_ALLOW` | Always |

A deny decision means either that a `DENY` engine matched or that an `ALLOW`
engine did not match. When an engine's condition is met, it invokes every one
of its configured loggers, in order, right after it decides. This happens
before the RPC continues or is rejected. If several engines in a chain each
meet their condition, each one logs. No de-duplication is done.

Setting a condition with no loggers, or loggers with condition `NONE`, is
valid. Nothing is logged.

### 3.2 Audit Context

Each logger invocation gets an audit context:

| Field | Value |
|-------|-------|
| RPC method | The full method name, for example `/pkg.Service/Foo` |
| Principal | The peer's SPIFFE ID if the client certificate has one (see the `peer_spiffe_id` property in [Security Model: Standard Properties](01-security-model.md#62-standard-properties)). Otherwise empty. |
| Policy name | For the gRPC authorization policy: the policy `name`. For xDS RBAC: empty. |
| Matched rule | The name of the matched rule or RBAC policy. Empty if nothing matched. |
| Authorized | `true` if the engine allowed the RPC, `false` if it denied it |

The context shows the engine's decision at that moment. It does not show the
RPC's final status.

### 3.3 Audit Options in the gRPC Authorization Policy

```json
{
  "audit_logging_options": {
    "audit_condition": "ON_DENY",
    "audit_loggers": [
      { "name": "stdout_logger", "config": {}, "is_optional": false }
    ]
  }
}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `audit_condition` | enum | No | `"NONE"` | One of `"NONE"`, `"ON_DENY"`, `"ON_ALLOW"`, `"ON_DENY_AND_ALLOW"`. Any other value is invalid. |
| `audit_loggers` | list of object | No | `[]` | Ordered list of audit loggers to invoke when `audit_condition` is met. |
| `audit_loggers[].name` | string | Yes | — | Registered logger type name. |
| `audit_loggers[].config` | object | No | `{}` | Configuration for that logger type; MUST be a JSON object. |
| `audit_loggers[].is_optional` | bool | No | `false` | If `true`, an unregistered logger type is ignored. Other configuration errors still make the policy invalid. |

Unknown fields are invalid, except inside `config`, whose contents the
logger validates. An unregistered logger type with `is_optional` false, or
a `config` the logger rejects, makes the policy invalid.

The single policy-level condition maps onto the two engines. Each RPC is
logged at most once:

| Policy `audit_condition` | `DENY` engine | `ALLOW` engine |
|--------------------------|---------------|----------------|
| `NONE` | `NONE` | `NONE` |
| `ON_DENY` | `ON_DENY` | `ON_DENY` |
| `ON_ALLOW` | `NONE` | `ON_ALLOW` |
| `ON_DENY_AND_ALLOW` | `ON_DENY` | `ON_DENY_AND_ALLOW` |

Both engines get the same logger list. If there are no deny rules, only the
`ALLOW` engine column applies.

### 3.4 xDS RBAC Audit Options

The xDS RBAC configuration has its own `audit_logging_options` (an audit
condition, plus logger configs that are typed extension configs, each with
`is_optional`). Its processing and validation are in
[xDS HTTP Filters](../09-xds/07-http-filters.md). Logger types are looked up
in the same registry ([Logger Registry and Plugin Contract](#35-logger-registry-and-plugin-contract)).

### 3.5 Logger Registry and Plugin Contract

Audit loggers are plugins. A process-wide **audit logger registry** maps a
logger type name to a **logger factory**.

A logger factory provides:

- `name()`: the logger type name it is registered under.
- `ParseConfig(json) → config | error`: parses and validates a logger
  configuration (a JSON object). Errors are reported when the policy or xDS
  resource is validated, before anything takes effect.
- `CreateLogger(config) → logger`: creates a logger from a config that
  `ParseConfig` accepted. This MUST succeed. Runtime problems, such as
  failing to open a file, are the logger's own responsibility.

A logger provides:

- `Log(audit_context)`: called synchronously on the RPC path when the audit
  condition is met. It returns nothing and cannot change the authorization
  decision. Implementations MUST NOT block. Slow work MUST be done
  asynchronously (copying any context data it needs, because the context is
  valid only during the call).

Factories SHOULD be registered during initialization, before servers start.
If two factories are registered under the same name, the last one wins.

<!-- REVIEW(divergence) [AUTHZ-6]: Go's RegisterLoggerBuilder overwrites the map entry, so the last registration wins. C++'s AuditLoggerRegistry::RegisterFactory does GRPC_CHECK(emplace(...).second), so a second registration under the same name, including an application factory named stdout_logger, aborts the process. Java has no audit logging. Spec says: If two factories are registered under the same name, the last one wins. -->

### 3.6 Built-in `stdout_logger`

gRPC provides a built-in logger type named `stdout_logger`. It defines no
configuration fields, and it ignores any fields in its `config`. In xDS, it
is selected with the typed config
`envoy.extensions.rbac.audit_loggers.stream.v3.StdoutAuditLog`.

Each event is written to standard output as one line of JSON:

```json
{"grpc_audit_log":{"timestamp":"2023-05-09T01:40:06.798505167Z","rpc_method":"/pkg.Service/Foo","principal":"spiffe://foo/user1","policy_name":"example_policy","matched_rule":"admin_access","authorized":true}}
```

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `grpc_audit_log` | object | Yes | — | Wrapper object for the audit log event. |
| `grpc_audit_log.timestamp` | string | Yes | — | Timestamp when the logger was invoked, in RFC 3339 format with nanosecond precision. |
| `grpc_audit_log.rpc_method` | string | Yes | — | Audit context RPC method. |
| `grpc_audit_log.principal` | string | Yes | — | Audit context principal. |
| `grpc_audit_log.policy_name` | string | Yes | — | Audit context policy name. |
| `grpc_audit_log.matched_rule` | string | Yes | — | Audit context matched rule (`""` when no rule matched). |
| `grpc_audit_log.authorized` | bool | Yes | — | Whether the RPC was allowed. |

Policy-language example:

```json
{
  "audit_logging_options": {
    "audit_condition": "ON_DENY",
    "audit_loggers": [ { "name": "stdout_logger" } ]
  }
}
```

## 4. API Requirements

- The server API MUST provide a way to enable gRPC authorization policy
  enforcement from a static policy string. Invalid policies MUST be reported
  to the application.
- It MUST provide a way to enable enforcement from a policy file with a
  configurable refresh interval. Errors in the first read MUST be reported to
  the application. There MUST be a way to stop refreshing.
- The authorization API MUST provide a way to register audit logger factories
  ([Logger Registry and Plugin Contract](#35-logger-registry-and-plugin-contract)), and a way for applications to implement loggers and
  factories.
- The audit context given to loggers MUST expose the fields in
  [Audit Context](#32-audit-context).
- The `stdout_logger` type MUST be registered by default.
