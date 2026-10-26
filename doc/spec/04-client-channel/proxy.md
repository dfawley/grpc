# HTTP CONNECT Proxy Support

<!-- Sources: A1 (use cases 1 and 2), doc/core/default_http_proxy_mapper.md -->

gRPC supports TCP-level proxies through the HTTP CONNECT method
(RFC 2817 / RFC 9110 §9.3.6). A TCP-level proxy knows nothing about
gRPC. It accepts a connection from the client, opens a connection to the
requested destination, and copies bytes in both directions.

Client-side per-call load balancing needs a separate connection to each
backend. How much of it survives depends on where the proxy is applied
(see [Use Cases](#2-use-cases)).

## 1. Proxy Mapper

Proxy selection is done by a **proxy mapper**, which can act at two
points:

| Hook | When | What it can do |
| --- | --- | --- |
| **Name mapping** | Before the channel's target is resolved. | Replace the name to resolve with the proxy's name, and set the **CONNECT target** to the original server name. |
| **Address mapping** | Before a subchannel connects to an address ([subchannels.md](subchannels.md)). | Replace the address to connect to with the proxy's address, and set the CONNECT target to the original address. |

When a CONNECT target is set for a connection, the connection attempt
runs the HTTP CONNECT handshake ([CONNECT Handshake](#4-connect-handshake)) right
after the transport connection to the proxy is established, before the
security handshake.

gRPC provides a default, environment-driven name-mapping proxy mapper
([Default Proxy Mapper](#3-default-proxy-mapper)). Applications can supply their own
logic for either hook (see [API Requirements](#6-api-requirements)).

## 2. Use Cases

### 2.1 All Outbound Traffic Through a Proxy (Name Mapping)

This is an environment where outbound traffic must go through a proxy,
the proxy does name resolution, and it may require a hostname in the
CONNECT request. It is usually configured by a central signal, such as
the `http_proxy` environment variable. Name mapping handles it:

- The channel resolves the **proxy's** name instead of the target's
  name. The LB policy therefore sees only the proxy's addresses, and
  creates subchannels to the proxy, not to individual backends.
- The CONNECT target is the target's `host:port`, as given by the
  application.
- Per-call load balancing across backends is impossible, because the
  client does not know the backend addresses. At most, load is balanced
  per connection, by the proxy.
- The client does not resolve the server name, so it gets no service
  config from the resolver. The resolver MUST NOT fetch a service config
  for the proxy's name, and the channel uses its default service config
  (see [service-config.md](service-config.md)).
- The channel's default authority, and the name used for TLS server
  verification, remain those of the original target, not the proxy (see
  [channel.md](channel.md)).

### 2.2 Some Addresses Through a Proxy (Address Mapping)

This is an environment where name resolution works normally, but
connections to some addresses must go through a proxy that accepts IP
addresses in CONNECT requests. Custom logic decides which addresses use
the proxy. Address mapping handles it:

- For an address that needs the proxy, the mapper replaces the address
  with the proxy's address and sets the CONNECT target to the original
  `ip:port`.
- The client resolves the server name itself, so it gets the service
  config as usual, and per-call load balancing works normally: there is
  one subchannel per backend address, each tunneled separately through
  the proxy.

## 3. Default Proxy Mapper

The default proxy mapper implements use case 1. It MUST NOT apply to
targets whose resolver does not produce network addresses from a host
name. In particular, it does not apply to `unix:`, `unix-abstract:`, or
`vsock:` targets (see [name-resolution.md](name-resolution.md)). It does
nothing if proxying is disabled for the channel (see
[API Requirements](#6-api-requirements)).

### 3.1 Choosing the Proxy

The proxy is chosen as follows:

1. If the application set a per-channel proxy option, that proxy is used.
2. Otherwise, the proxy comes from the platform's standard proxy
   configuration (for example, environment variables or runtime system
   properties). Which sources are consulted, and in what order, is
   implementation-defined, and SHOULD follow the conventions of the
   platform so that gRPC picks up the same proxy settings as other HTTP
   clients there.

If no proxy is configured, no proxy is used. The choice does not depend
on whether the channel uses TLS.

For example, an implementation that reads environment variables might
use the first of these that is set to a non-empty value: `grpc_proxy`,
then `https_proxy`, then `http_proxy`.

When the proxy is given as a URI (the per-channel option, or a
URI-valued environment variable), the value is an RFC 3986 URI of the form
`http://[userinfo@]host[:port][/]`:

- The scheme MUST be `http`. If the scheme is anything else, the value is
  ignored with an error log, and no proxy is used.
- `host[:port]` is the proxy to connect to. If the port is missing, 443
  is used.
- `userinfo`, if present (`username:password`), is percent-decoded and
  sent as proxy credentials ([CONNECT Handshake](#4-connect-handshake)).

### 3.2 Excluding Hosts

If a proxy was chosen, the platform's standard exclusion configuration
is applied. If the target's host matches an exclusion, no proxy is used
for the channel.

Which exclusion sources are consulted is implementation-defined and
SHOULD follow platform conventions. For example, an implementation that
reads environment variables might use the first of `no_grpc_proxy` and
`no_proxy` that is set. An environment-variable exclusion list is
comma-separated. Whitespace around entries is ignored. The target's host
(without port) is compared with each entry. If any entry matches, no
proxy is used for the channel:

| Entry form | Matches |
| --- | --- |
| Domain name, optionally with a leading `.` (`example.com` and `.example.com` are equivalent) | The host exactly, or any subdomain on a dot boundary. For example, `example.com` matches `example.com`, `foo.example.com`, and `a.b.example.com`, but not `notexample.com`. Comparison is case-insensitive. |
| IP address | A host that is that IP address literal. |
| CIDR block (for example, `10.10.0.0/24`) | A host that is an IP address literal inside the block. |

### 3.3 Effect

When a proxy is used, the default mapper:

1. Sets the name to resolve to the proxy's `host:port`. The channel
   resolves it with the DNS resolver.
2. Sets the CONNECT target to the original target's `host:port`. If the
   target has no port, 443 is added.
3. Records the proxy credentials, if any, for the CONNECT request.

## 4. CONNECT Handshake

After the transport connection to the proxy is established, the client
sends:

```
CONNECT <connect-target> HTTP/1.1
Host: <connect-target>
Proxy-Authorization: Basic <base64(username ":" password)>    ; only if credentials are set
<additional headers, if any>

```

- `<connect-target>` is `host:port`. A hostname is used in use case 1, and
  an IP literal (IPv6 in brackets) in use case 2.
- `Proxy-Authorization` uses the HTTP Basic scheme (RFC 7617) with the
  credentials from the proxy configuration.
- Implementations MAY add other headers configured by the proxy mapper.

The client then reads the proxy's HTTP/1.1 response:

- **2xx:** the tunnel is established. Bytes after the end of the response
  headers belong to the tunneled stream. The connection attempt continues
  with the security handshake, which uses the original target's name for
  SNI and verification (for xDS-configured proxies, the cluster's security
  configuration applies instead; see [xDS-Configured Proxies](#5-xds-configured-proxies)),
  and then HTTP/2 setup (see [subchannels.md](subchannels.md)).
- **Any other status, or a malformed response:** the connection attempt
  fails, with a status whose message includes the HTTP status line.
  Normal connection backoff applies.

## 5. xDS-Configured Proxies

xDS can tell the client to use an HTTP CONNECT proxy per endpoint,
through the cluster's transport socket configuration. This uses the same
CONNECT handshake and is specified in
[../09-xds/resources/cluster.md](../09-xds/resources/cluster.md). In that
case:

- The proxy address comes from endpoint (or locality) metadata (see
  [../09-xds/resources/endpoint.md](../09-xds/resources/endpoint.md)), and
  the CONNECT target is the endpoint's `ip:port`.
- The TLS configuration, SNI, and SAN checks for the tunneled connection
  come from the cluster's xDS security configuration and refer to the
  endpoint, not the proxy (see [../09-xds/security.md](../09-xds/security.md)).

## 6. API Requirements

- The channel API MUST provide a way to disable proxy use for a channel,
  overriding the environment.
- The channel API MUST provide a way to set the proxy explicitly for a
  channel. This option takes precedence over the platform's proxy
  configuration.
- The API MUST provide a way for applications to supply custom proxy
  selection logic (a proxy mapper) for both name mapping and address
  mapping.
- Proxy credentials MUST be configurable through the userinfo part of
  the proxy URI.

