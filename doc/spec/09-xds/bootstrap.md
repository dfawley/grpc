# Bootstrap

<!-- Sources: A27, A29, A30, A36, A47, A53, A65, A71, A81, A87, A88, A95, A97, doc/grpc_xds_bootstrap_format.md -->

The bootstrap configuration is a JSON document. It tells the XdsClient which
xDS servers to contact, which credentials to use with them, how to identify
the gRPC instance to them (the `Node`), how to build resource names, and which
certificate provider instances are available. All XdsClient instances in a
process use the same bootstrap configuration, unless an application supplies
one programmatically for a specific channel or server (see
[Locating the Bootstrap Configuration](#1-locating-the-bootstrap-configuration)).

## 1. Locating the Bootstrap Configuration

gRPC looks for the bootstrap configuration in these sources, in this order of
precedence:

1. **A programmatic per-channel or per-server configuration**, if the
   application supplied one when it created the channel or server (see
   [API Requirements](#6-api-requirements)). A channel or server
   configured this way gets its own XdsClient instance, which is not shared
   with other channels or servers.
2. **`GRPC_XDS_BOOTSTRAP`**: if this environment variable is set, its value is
   the path of a file whose contents are the bootstrap JSON.
3. **`GRPC_XDS_BOOTSTRAP_CONFIG`**: if this environment variable is set (and
   `GRPC_XDS_BOOTSTRAP` is not), its value is the bootstrap JSON itself.
4. **A programmatic process-wide fallback configuration**, if the application
   supplied one.

If none of these is available, or if the file cannot be read, then creating
an XdsClient fails. The component that needed the XdsClient (the xds resolver
or the xDS-enabled server) reports the failure (see [Client](client.md)
and [xDS-Enabled Servers](server.md)).

<!-- REVIEW(divergence) [XDS_BOOTSTRAP-1]: All three have a per-channel/per-server override that gets its own XdsClient, but only as test-oriented APIs (Java: XdsNameResolverProvider.createForTest / XdsServerBuilder.overrideBootstrapForTest; Go: xdsclient.NewPool(config) via internal resolver/server test options; C++: GRPC_ARG_TEST_ONLY_DO_NOT_USE_IN_PROD_XDS_BOOTSTRAP_CONFIG channel arg). Process-wide config: Go (Pool.SetFallbackBootstrapConfig) and C++ (SetXdsFallbackBootstrapConfig) use it as the lowest-precedence fallback after both env vars; Java (InternalSharedXdsClientPoolProvider.setDefaultProviderBootstrapOverride) uses it INSTEAD of the env vars (highest precedence). Spec says: per-channel first, process-wide last (Go/C++). -->

The process-wide bootstrap configuration is read and parsed when the first
XdsClient that needs it is created. It MAY be cached for the life of the
process, so later changes to the environment variables or to the file might
not take effect.

If the JSON does not parse or fails validation, creating the XdsClient fails
with an error that describes every validation failure found.

## 2. General Parsing Rules

- The document MUST be a JSON object.
- **Unknown fields MUST be ignored** at every level, so that older clients
  keep working with newer bootstrap files.
- A field that is present but has the wrong JSON type is a validation error.
- Duration fields use the JSON form of `google.protobuf.Duration` (for
  example, `"600s"`).

## 3. Top-Level Fields

| Field | Type | Required | Semantics |
| --- | --- | --- | --- |
| `xds_servers` | array of [XdsServer](#41-xdsserver-object) | Yes; MUST be non-empty | The default xDS servers, in priority order (first is highest). Used for old-style (non-`xdstp:`) resource names and for every authority that does not set its own `xds_servers`. All entries are used for fallback (see [XdsClient](xds-client.md)). |
| `node` | [Node](#42-node-object) object | No | Identifies this gRPC instance to the xDS servers. |
| `authorities` | map from authority name (string) to [Authority](#43-authority-object) | No | Config for each authority used in `xdstp:` resource names. A new-style name with an empty authority uses the key `""`. Using an `xdstp:` name whose authority is not in this map is an error (see [XdsClient](xds-client.md)). |
| `client_default_listener_resource_name_template` | string | No; default `"%s"` (also used if the value is empty) | Template for the client Listener resource name when the channel's `xds` target URI has no authority. Every `%s` is replaced by the target's service authority: the URI path with any leading `/` removed. If the template starts with `xdstp:`, the replacement is percent-encoded first (see [XdsClient](xds-client.md)), and the authority of the resulting name selects the entry in `authorities`. If the result does not start with `xdstp:`, the name is old-style and the top-level `xds_servers` are used. |
| `server_listener_resource_name_template` | string | No; no default | Template for the Listener resource name that an xDS-enabled server watches for each listening address. Every `%s` is replaced by the listening address in `IP:port` form (for example, `0.0.0.0:8080` or `[::]:8080`). If the template starts with `xdstp:`, the replacement is percent-encoded first, and the authority of the resulting name selects the entry in `authorities`. Otherwise no special character handling is done. If the field is unset, xDS-enabled servers cannot be used (see [xDS-Enabled Servers](server.md)). |
| `certificate_providers` | map from instance name (string) to [CertificateProvider](#44-certificate-provider-instances) | No | Certificate provider plugin instances that xDS security config can refer to by instance name (see [xDS Security](security.md)). |

## 4. Object Definitions

### 4.1 XdsServer Object

An XdsServer object describes one xDS server. The same object format is used
in the top-level `xds_servers`, in an authority's `xds_servers`, and inside
LB policy config that names an LRS server (see
[xDS LB Policies](lb-policies.md)).

| Field | Type | Required | Semantics |
| --- | --- | --- | --- |
| `server_uri` | string | Yes | gRPC target URI of the xDS server, used to create the xDS channel. Any resolver scheme that gRPC supports may be used. |
| `channel_creds` | array of `{ "type": string, "config": object }` | Yes; MUST contain at least one supported type | Channel credentials for the xDS channel. gRPC uses the **first** entry whose `type` it supports and ignores unsupported types. `type` is required in every entry. `config` is optional and defaults to an empty object. The selected entry (the first with a supported type) MUST have a `config` that is valid for that type, or the bootstrap is invalid; gRPC does not fall through to a later entry. Entries after the selected one are not validated. If no entry has a supported type, the bootstrap is invalid. |
| `call_creds` | array of `{ "type": string, "config": object }` | No | Call credentials for RPCs on the xDS channel. Unlike `channel_creds`, gRPC applies **every** entry whose `type` it supports, and ignores unsupported types. If the field is missing or has no supported entry, no call credentials are used. Call credential types are a separate namespace from channel credential types. Every entry with a supported type MUST have a valid `config`, or the bootstrap is invalid. |
| `server_features` | array | No | Server features (see [Server Features](#5-server-features)). Entries that are not strings, and strings that are not recognized, MUST be ignored. |

<!-- REVIEW(divergence) [XDS_BOOTSTRAP-2]: Validation of supported channel_creds entries after the selected one. Java (GrpcBootstrapperImpl.parseChannelCredentials) and Go (internal/xds/bootstrap/bootstrap.go ServerConfig.UnmarshalJSON) stop at the first supported entry and validate only it (invalid config there is an error, no fall-through). C++ (xds_server_grpc.cc ParseXdsBootstrapChannelCreds) validates every supported entry. Spec says: only the selected entry is validated (Java/Go). -->

Two XdsServer entries are **the same server** when their `server_uri`,
selected channel credentials (type and config), applied call credentials
(types and configs), and set of recognized server features are all equal.
The XdsClient uses this identity to share channels (see
[XdsClient](xds-client.md)).

#### Channel credential types

| `type` | Config | Semantics |
| --- | --- | --- |
| `insecure` | none | Plaintext (no transport security). |
| `google_default` | none | Google default credentials. |
| `tls` | see below | TLS, or mTLS when an identity certificate is configured. Certificate files are reloaded periodically. |

`tls` config fields:

| Field | Type | Required | Semantics |
| --- | --- | --- | --- |
| `ca_certificate_file` | string | No | Path to a PEM file of CA certificates used to verify the server. If unset, the system root certificates are used. |
| `certificate_file` | string | No | Path to a PEM identity certificate (chain). If set, mTLS is used. |
| `private_key_file` | string | No | Path to the PEM private key for `certificate_file`. |
| `refresh_interval` | Duration | No; default `"600s"` | How often to re-read the files. |

Validation for `tls`: `certificate_file` and `private_key_file` MUST be both
set or both unset. Unlike the `file_watcher` certificate provider, the `tls`
type may leave all of `ca_certificate_file`, `certificate_file`, and
`private_key_file` unset; it then does server-authenticated TLS with system
roots. Implementations MAY use the `file_watcher` certificate provider
internally to reload the files.

#### Call credential types

| `type` | Config | Semantics |
| --- | --- | --- |
| `jwt_token_file` | `{ "jwt_token_file": string }`. `jwt_token_file` is required. | JWT token file call credentials (see [Call Credentials](../06-security/call-credentials.md)). The token is read from the named file and sent in the `authorization` header as `Bearer <token>`. |

### 4.2 Node Object

The `node` object supplies some of the fields of the xDS
`envoy.config.core.v3.Node` message (`envoy/config/core/v3/base.proto`). The
XdsClient sends that message in the first request on every ADS stream, and
the LRS client sends it on every LRS stream.

| Field | Type | Semantics |
| --- | --- | --- |
| `id` | string | Opaque identifier for this gRPC instance. Copied to `Node.id`. |
| `cluster` | string | The local service cluster that this instance runs in. Copied to `Node.cluster`. |
| `locality` | object with optional string fields `region`, `zone`, `sub_zone` | Where this instance runs. Copied to `Node.locality`. |
| `metadata` | JSON object | Opaque metadata. Converted to the `google.protobuf.Struct` in `Node.metadata`. |

All `node` fields are optional. gRPC itself fills in these `Node` fields, so
they SHOULD NOT appear in the bootstrap. If they do appear, they are ignored:

| `Node` field | Value |
| --- | --- |
| `user_agent_name` | A string that identifies the gRPC implementation (for example, `"gRPC <language>"`). |
| `user_agent_version` | The gRPC library version. |
| `client_features` | The client features that the implementation supports (see [xDS](README.md#3-client-features)). |

The deprecated `build_version` field is never sent.

### 4.3 Authority Object

| Field | Type | Required | Semantics |
| --- | --- | --- | --- |
| `client_listener_resource_name_template` | string | No | Template for the client Listener resource name when a channel's `xds` target URI has this authority. Every `%s` is replaced by the percent-encoded service authority (see [XdsClient](xds-client.md)). If set to a non-empty value, it MUST start with `xdstp://<authority_name>/`, or the bootstrap is invalid. If unset or empty, it defaults to `xdstp://<authority_name>/envoy.config.listener.v3.Listener/%s`, with `<authority_name>` percent-encoded as a URI authority. |
| `xds_servers` | array of [XdsServer](#41-xdsserver-object) | No | The xDS servers for this authority, in priority order. If unset or empty, the top-level `xds_servers` are used. A server listed under several authorities is the same server, and the XdsClient shares one ADS stream for all of them (see [XdsClient](xds-client.md)). |
| `fallback_on_reachability_only` | bool | No; default `false` | If `true`, the XdsClient falls back to the next server for this authority whenever the current server is unreachable, even if every watched resource is already cached. If `false`, it falls back only when at least one watched resource is not cached (see [XdsClient](xds-client.md)). |

<!-- REVIEW(divergence) [XDS_BOOTSTRAP-3]: Empty authority client_listener_resource_name_template. Go (internal/xds/bootstrap/bootstrap.go, xds_resolver.go) and C++ (xds_bootstrap_grpc.cc, xds_resolver.cc) treat "" as unset and use the default. Java (BootstrapperImpl) applies the default only when the field is absent; "" fails the xdstp://<authority>/ prefix check, so the bootstrap is invalid. Spec says: empty = unset (Go/C++). -->

### 4.4 Certificate Provider Instances

Each entry in `certificate_providers` maps an *instance name* (the name that
xDS security config uses in `CertificateProviderPluginInstance.instance_name`)
to:

| Field | Type | Required | Semantics |
| --- | --- | --- | --- |
| `plugin_name` | string | Yes | Name of the certificate provider plugin implementation. It MUST be a plugin that gRPC supports, or the bootstrap is invalid. |
| `config` | object | No; default `{}` | Plugin-specific config. It MUST be valid for the plugin, or the bootstrap is invalid. |

An xDS resource that refers to an instance name not in this map is invalid
(see [xDS Security](security.md)).

#### `file_watcher` plugin

The only certificate provider plugin is `file_watcher`. It reads PEM files
(`certificate_file`, `private_key_file`, `ca_certificate_file`) and an
optional SPIFFE trust bundle map (`spiffe_trust_bundle_map_file`) from the
local file system, and re-reads them every `refresh_interval` (default
`"600s"`). Its config fields and validation rules are specified in
[xDS Security](security.md). An invalid config makes the bootstrap
invalid. Certificate provider behavior is specified in
[TLS](../06-security/tls.md).

<!-- REVIEW(divergence) [XDS_BOOTSTRAP-4]: file_watcher SPIFFE field name. Java (FileWatcherCertificateProviderProvider SPIFFE_TRUST_MAP_FILE_KEY) and Go (credentials/tls/certprovider/pemfile/builder.go) parse spiffe_trust_bundle_map_file, matching A87. C++ (src/core/xds/grpc/file_watcher_certificate_provider_factory.cc) parses spiffe_bundle_map_file. Spec says: spiffe_trust_bundle_map_file (gRFC, Java/Go). -->

## 5. Server Features

The following strings are recognized in `server_features`. Each one applies
only to the XdsServer entry that lists it.

| Feature | Semantics |
| --- | --- |
| `fail_on_data_errors` | Tells gRPC that it cannot rely on this server's operators to be alerted to data errors. When a data error happens for a resource that is already cached (a NACK of a new version, an LDS or CDS resource deletion, or a server-reported resource error with status NOT_FOUND or PERMISSION_DENIED), the XdsClient drops the cached resource and reports the error to watchers as a resource error. Without this feature, the XdsClient keeps the cached resource and reports the error as an ambient error. See [XdsClient](xds-client.md). |
| `resource_timer_is_transient_error` | The does-not-exist timer for resources fetched from this server is 30 seconds instead of 15. When it fires, the cache entry goes to state `TIMEOUT` and watchers get an UNAVAILABLE error, instead of state `DOES_NOT_EXIST` and NOT_FOUND. Use this only with servers known to report missing resources explicitly through per-resource errors. Otherwise, clients take longer to notice a resource that does not exist. |
| `trusted_xds_server` | Marks the server as trusted for security-sensitive features. This means that `RouteAction.auto_host_rewrite` in RDS resources from this server is honored (authority rewriting; see [RDS](resources/route-configuration.md) and [Client](client.md)). If the feature is absent, that field is ignored. |
| `ignore_resource_deletion` | Recognized but has **no effect**. By default, LDS and CDS deletions of cached resources are already treated as ambient errors (unless `fail_on_data_errors` is set). |
| `xds_v3` | Recognized but has **no effect**. gRPC always uses xDS v3. |

## 6. API Requirements

- gRPC MUST read the bootstrap configuration from the file named by
  `GRPC_XDS_BOOTSTRAP` or from the contents of `GRPC_XDS_BOOTSTRAP_CONFIG`,
  with the precedence given in [Locating the Bootstrap Configuration](#1-locating-the-bootstrap-configuration).
- gRPC MUST provide a way for an application to supply the bootstrap
  configuration programmatically for the whole process. This is used when
  neither environment variable is set.
- gRPC MUST provide a way for an application to supply a bootstrap
  configuration for a specific xDS-enabled channel or server. That
  configuration takes precedence over all other sources. The channel or
  server then uses its own XdsClient instance.
- gRPC MUST NOT require any bootstrap field that this document marks as
  optional.

## 7. Example

```json
{
  "xds_servers": [
    {
      "server_uri": "xds.primary.example.com:443",
      "channel_creds": [
        {
          "type": "tls",
          "config": {
            "ca_certificate_file": "/etc/xds/ca.pem",
            "certificate_file": "/etc/xds/cert.pem",
            "private_key_file": "/etc/xds/key.pem",
            "refresh_interval": "300s"
          }
        },
        { "type": "insecure" }
      ],
      "call_creds": [
        {
          "type": "jwt_token_file",
          "config": { "jwt_token_file": "/var/run/secrets/tokens/xds-token" }
        }
      ],
      "server_features": ["fail_on_data_errors", "trusted_xds_server"]
    },
    {
      "server_uri": "xds.fallback.example.com:443",
      "channel_creds": [ { "type": "google_default" } ]
    }
  ],
  "node": {
    "id": "projects/1234/networks/default/nodes/5678",
    "cluster": "cluster",
    "locality": { "region": "us-central1", "zone": "us-central1-a" },
    "metadata": { "TRAFFICDIRECTOR_NETWORK_NAME": "default" }
  },
  "client_default_listener_resource_name_template":
      "xdstp://xds.example.com/envoy.config.listener.v3.Listener/grpc/client/%s",
  "server_listener_resource_name_template":
      "xdstp://xds.example.com/envoy.config.listener.v3.Listener/grpc/server/%s",
  "authorities": {
    "xds.example.com": {},
    "endpoints.example.com": {
      "xds_servers": [
        {
          "server_uri": "eds.example.com:443",
          "channel_creds": [ { "type": "google_default" } ],
          "server_features": ["resource_timer_is_transient_error"]
        },
        {
          "server_uri": "eds-backup.example.com:443",
          "channel_creds": [ { "type": "google_default" } ]
        }
      ],
      "fallback_on_reachability_only": true
    }
  },
  "certificate_providers": {
    "default_mesh_certs": {
      "plugin_name": "file_watcher",
      "config": {
        "certificate_file": "/var/run/certs/certificates.pem",
        "private_key_file": "/var/run/certs/private_key.pem",
        "ca_certificate_file": "/var/run/certs/ca_certificates.pem",
        "refresh_interval": "600s"
      }
    }
  }
}
```

With this configuration:

- A channel for `xds:///foo.example.com:8080` watches the Listener
  `xdstp://xds.example.com/envoy.config.listener.v3.Listener/grpc/client/foo.example.com:8080`.
  Authority `xds.example.com` sets no servers, so the top-level servers are
  used: `xds.primary.example.com:443`, with fallback to
  `xds.fallback.example.com:443`.
- A channel for `xds://endpoints.example.com/foo` watches
  `xdstp://endpoints.example.com/envoy.config.listener.v3.Listener/foo` from
  `eds.example.com:443`. It falls back to `eds-backup.example.com:443`
  whenever the primary is unreachable.
- An xDS-enabled server listening on `0.0.0.0:50051` watches
  `xdstp://xds.example.com/envoy.config.listener.v3.Listener/grpc/server/0.0.0.0:50051`.
