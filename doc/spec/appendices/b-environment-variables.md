> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# Appendix B. Environment Variables

<!-- Sources: doc/spec/09-xds/02-bootstrap.md, doc/spec/04-client-channel/09-proxy.md, doc/spec/08-observability/07-binary-logging.md, doc/spec/00-introduction/README.md, A1, A16, A27, A47, doc/core/default_http_proxy_mapper.md, doc/environment_variables.md, doc/grpc_xds_bootstrap_format.md, doc/spec/06-security/05-alts.md, doc/spec/10-vendor-specific/01-google-default-credentials.md -->

This appendix lists the environment variables that are part of this
specification. Each one is permanent configuration. Its semantics are defined
normatively in the linked section.

> [!NOTE]
> Implementations also use temporary environment variables. Some guard
> features under development, and some opt out of a behavior change for
> backward compatibility. Those variables are **not** part of this
> specification. Their names and existence
> can change at any time, and conforming behavior MUST NOT depend on them.
> Implementations MAY also define implementation-specific runtime or debugging
> environment variables (for example, log verbosity, tracing of internal
> components, polling or DNS backend selection, or TLS root-certificate file
> overrides). Those are outside this specification as well.

## B.1 xDS Bootstrap

| Variable | Value | Semantics | Defined in |
| --- | --- | --- | --- |
| `GRPC_XDS_BOOTSTRAP` | Path of a file | The file contains the xDS bootstrap configuration as JSON. It takes precedence over `GRPC_XDS_BOOTSTRAP_CONFIG`. If the file cannot be read or is invalid, creating the XdsClient fails. An empty value counts as set (and fails). | [Bootstrap](../09-xds/02-bootstrap.md) ([Bootstrap: Locating the Bootstrap Configuration](../09-xds/02-bootstrap.md#1-locating-the-bootstrap-configuration)) |
| `GRPC_XDS_BOOTSTRAP_CONFIG` | JSON text | The bootstrap configuration itself. Used only if `GRPC_XDS_BOOTSTRAP` is not set. An empty value counts as set (and fails). The precedence of any programmatic configuration is implementation-defined. | [Bootstrap](../09-xds/02-bootstrap.md) ([Bootstrap: Locating the Bootstrap Configuration](../09-xds/02-bootstrap.md#1-locating-the-bootstrap-configuration)) |

The process-wide bootstrap configuration MAY be read only once, when the first
XdsClient that needs it is created. Changing these variables after that might
have no effect.

## B.2 HTTP CONNECT Proxy

These variables are an example of the platform proxy configuration that the
default proxy mapper may read. Which proxy configuration sources are consulted
is implementation-defined and follows platform conventions (see
[Choosing the Proxy](../04-client-channel/09-proxy.md#31-choosing-the-proxy)), so
an implementation might honor only some of these variables, or none. A
per-channel proxy setting from the application takes precedence over all of
them. Disabling proxying for a channel turns all of them off.

| Variable | Value | Semantics | Defined in |
| --- | --- | --- | --- |
| `grpc_proxy` | `http://[userinfo@]host[:port][/]` | Proxy for gRPC channels. Checked first. | [HTTP CONNECT Proxy Support](../04-client-channel/09-proxy.md) ([Choosing the Proxy](../04-client-channel/09-proxy.md#31-choosing-the-proxy)) |
| `https_proxy` | Same as above | Used if `grpc_proxy` is not set. | [HTTP CONNECT Proxy Support](../04-client-channel/09-proxy.md) ([Choosing the Proxy](../04-client-channel/09-proxy.md#31-choosing-the-proxy)) |
| `http_proxy` | Same as above | Used if neither `grpc_proxy` nor `https_proxy` is set. | [HTTP CONNECT Proxy Support](../04-client-channel/09-proxy.md) ([Choosing the Proxy](../04-client-channel/09-proxy.md#31-choosing-the-proxy)) |
| `no_grpc_proxy` | Comma-separated list of host names, domain suffixes, IP addresses, and CIDR blocks | A target whose host matches an entry is not proxied. Checked before `no_proxy`. | [HTTP CONNECT Proxy Support](../04-client-channel/09-proxy.md) ([Excluding Hosts](../04-client-channel/09-proxy.md#32-excluding-hosts)) |
| `no_proxy` | Same as above | Used if `no_grpc_proxy` is not set. | [HTTP CONNECT Proxy Support](../04-client-channel/09-proxy.md) ([Excluding Hosts](../04-client-channel/09-proxy.md#32-excluding-hosts)) |

Notes:

- In this example, the first variable set to a non-empty value is used.
- The proxy URI scheme is `http`. The handling of other or missing schemes,
  and the exact matching rules for exclusion entries, follow platform
  conventions.
- If the proxy URI has no port, 443 is used.
- `userinfo` is sent as HTTP Basic credentials in `Proxy-Authorization` (see
  [Appendix A](a-metadata-keys.md)).
- The default proxy mapper applies to `dns:` targets and never to `unix:` or
  `vsock:` targets. Whether it applies to targets with other schemes is
  implementation-defined ([HTTP CONNECT Proxy Support: Default Proxy Mapper](../04-client-channel/09-proxy.md#3-default-proxy-mapper)).
- Whether upper-case variants (such as `HTTPS_PROXY`) are honored follows
  platform conventions.

## B.3 Binary Logging

| Variable | Value | Semantics | Defined in |
| --- | --- | --- | --- |
| `GRPC_BINARY_LOG_FILTER` | Binary log filter configuration string | Turns on binary logging without code changes. It selects which methods are logged and how much of their headers and messages is kept. An empty string logs nothing. A malformed value MUST NOT result in logging with a partial configuration, and SHOULD make gRPC fail at initialization. An API option that accepts the same string is equivalent. | [Binary Logging](../08-observability/07-binary-logging.md) ([Binary Logging: Enabling Binary Logging](../08-observability/07-binary-logging.md#1-enabling-binary-logging), [Binary Logging: Configuration String](../08-observability/07-binary-logging.md#5-configuration-string)) |

## B.4 ALTS

| Variable | Value | Semantics | Defined in |
| --- | --- | --- | --- |
| `GRPC_ALTS_MAX_CONCURRENT_HANDSHAKES` | Positive integer | The maximum number of ALTS handshakes that have a handshaker service stream open at the same time. The default, any upper bound, and whether client and server handshakes share one limit are implementation-defined (recommended: default 100, separate limits). | [ALTS](../06-security/05-alts.md) ([ALTS: Handshaker Service](../06-security/05-alts.md#2-handshaker-service)) |

## B.5 Vendor-Specific Features

| Variable | Value | Semantics | Defined in |
| --- | --- | --- | --- |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path of a file | The Google credentials file that Application Default Credentials use first. Defined by Google's Application Default Credentials procedure, not by gRPC. | [Google Call Credentials](../10-vendor-specific/05-google-call-credentials.md) ([Google Call Credentials: Application Default Credentials](../10-vendor-specific/05-google-call-credentials.md#2-application-default-credentials)) |
