> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 10.2 Google Cloud-to-Prod (`google-c2p`) Resolver

<!-- Sources: A27, A47, A53, doc/grpc_xds_bootstrap_format.md -->

The `google-c2p` resolver ("Cloud-to-Prod", also called DirectPath) lets a
client running on Google Cloud Platform (GCP) reach Google services through
Google's xDS control plane (Traffic Director) instead of through DNS. When
the client is on GCP, the resolver generates an xDS bootstrap configuration
in memory and delegates to the `xds` resolver. Otherwise it delegates to the
`dns` resolver.

Implementations MAY provide this resolver. An implementation that provides it
registers it under the scheme `google-c2p`.

## 1. Target URI

```
google-c2p:///<name>
google-c2p:///<name>?force-xds
```

- The scheme is `google-c2p`.
- The authority MUST be empty. If a target has a non-empty authority, creating
  the resolver fails, and the channel reports the failure as for any other
  invalid target (see [Name Resolution](../04-client-channel/03-name-resolution.md)).
- `<name>` is the URI path with its leading `/` removed. It is the service
  name (for example `storage.googleapis.com`), used both as the DNS name on
  the DNS path and as the listener name on the xDS path.
- If the query contains the parameter `force-xds` (with or without a value;
  only its presence matters), the resolver uses the xDS path even when the
  client is not on GCP ([Forcing xDS](#5-forcing-xds)). Other query parameters
  are ignored.

## 2. Choosing the Path

When the resolver starts, it chooses one of two paths:

1. If `force-xds` is absent and the client is not running on GCP, the
   resolver uses the **DNS path**: it creates a `dns` resolver for the target
   `dns:///<name>` (dropping any query) and forwards everything to it. See
   [Name Resolution: `dns`](../04-client-channel/03-name-resolution.md#71-dns).
2. Otherwise it uses the **xDS path** ([xDS Path](#3-xds-path)).

Whether the client is running on GCP is determined from the platform, without
network access: the system product name reported by the platform firmware
(on Linux, the contents of `/sys/class/dmi/id/product_name`, with surrounding
whitespace removed) is `Google` or `Google Compute Engine`. On other
platforms, the equivalent product name or manufacturer value contains
`Google`.

The process-wide bootstrap environment variables (`GRPC_XDS_BOOTSTRAP` and
`GRPC_XDS_BOOTSTRAP_CONFIG`; see
[Bootstrap: Locating the Bootstrap Configuration](../09-xds/02-bootstrap.md#1-locating-the-bootstrap-configuration))
do not affect the choice, and the process-wide bootstrap configuration is
never used by this resolver.

## 3. xDS Path

On the xDS path the resolver:

1. Queries the GCP metadata server for the client's zone and IPv6 capability
   ([Metadata Server Queries](#4-metadata-server-queries)), unless
   `force-xds` is present ([Forcing xDS](#5-forcing-xds)).
2. Generates a bootstrap configuration ([Generated Bootstrap](#31-generated-bootstrap)).
3. Gets or creates an XdsClient for the child target (below), using the
   generated bootstrap instead of the process-wide one.
4. Creates an `xds` resolver for the child target

   ```
   xds://traffic-director-c2p.xds.googleapis.com/<name>
   ```

   (dropping any query) and forwards everything to it. The `xds` resolver
   uses the XdsClient from step 3 ([Client Data Plane: The `xds` Resolver](../09-xds/05-client.md#1-the-xds-resolver)).

The XdsClient is keyed by the child target string. Channels in the process
that use `google-c2p` targets with the same `<name>` share one XdsClient. If
an XdsClient already exists for the key, it is reused and the newly generated
bootstrap is discarded. The XdsClient is released when the last resolver
that uses it shuts down.

Because the child target's authority is `traffic-director-c2p.xds.googleapis.com`,
which the generated bootstrap lists under `authorities`, the Listener resource
name is built from that authority's default listener template
([XdsClient: Resource Names](../09-xds/03-xds-client.md#3-resource-names)):

```
xdstp://traffic-director-c2p.xds.googleapis.com/envoy.config.listener.v3.Listener/<name>
```

The metadata queries MAY run asynchronously; the resolver reports no result
until they finish. An implementation MAY cache the metadata results, or the
whole generated bootstrap, for the life of the process.

### 3.1 Generated Bootstrap

The generated bootstrap is equivalent to the following JSON (see
[Bootstrap](../09-xds/02-bootstrap.md) for the meaning of each field):

```json
{
  "xds_servers": [
    {
      "server_uri": "directpath-pa.googleapis.com",
      "channel_creds": [ { "type": "google_default" } ],
      "server_features": [ "ignore_resource_deletion" ]
    }
  ],
  "authorities": {
    "traffic-director-c2p.xds.googleapis.com": {
      "xds_servers": [
        {
          "server_uri": "directpath-pa.googleapis.com",
          "channel_creds": [ { "type": "google_default" } ],
          "server_features": [ "ignore_resource_deletion" ]
        }
      ]
    }
  },
  "node": {
    "id": "C2P-1234567890",
    "locality": { "zone": "us-central1-a" },
    "metadata": { "TRAFFICDIRECTOR_DIRECTPATH_C2P_IPV6_CAPABLE": true }
  }
}
```

| Field | Value |
| --- | --- |
| `xds_servers[0].server_uri` | `directpath-pa.googleapis.com`, resolved with the default `dns` resolver. The URI MAY carry an explicit `dns:///` prefix. An implementation MAY provide its own way to set a universe domain, in which case the host is `directpath-pa.<universe domain>`; the default universe domain is `googleapis.com`. |
| `xds_servers[0].channel_creds` | A single entry of type `google_default` ([Google Default Credentials](01-google-default-credentials.md)). |
| `xds_servers[0].server_features` | `ignore_resource_deletion` ([Bootstrap: Server Features](../09-xds/02-bootstrap.md#5-server-features)). The list MAY also contain features that have no effect on the XdsClient, such as `xds_v3` (no longer recognized, so ignored). |
| `authorities` | One authority, `traffic-director-c2p.xds.googleapis.com`, whose `xds_servers` is the same single server. Its `client_listener_resource_name_template` is unset, so the default template for the authority applies. |
| `client_default_listener_resource_name_template` | Unset (the default, `%s`), or set explicitly to `%s`. It is not used, because the child target always has an authority. |
| `node.id` | By default, `C2P-` followed by a random non-negative decimal integer, for example `C2P-1234567890`. Any value that starts with `C2P-` (for example `C2P-non-gcp-1234567890`) is allowed. |
| `node.locality.zone` | The zone from the metadata server. Omitted if the zone is empty. |
| `node.metadata` | `{"TRAFFICDIRECTOR_DIRECTPATH_C2P_IPV6_CAPABLE": true}` if the client is IPv6-capable. Omitted otherwise. |

The values in the table are the defaults; the variations it lists do not
change the behavior of the control plane or the client. All other bootstrap
fields are unset. The generated bootstrap is valid by
construction, and the `google_default` channel credentials type MUST be
available to it.

## 4. Metadata Server Queries

The resolver sends two HTTP/1.1 GET requests to the GCP metadata server,
each with the request header `Metadata-Flavor: Google`:

| Query | URL | Result |
| --- | --- | --- |
| Zone | `http://metadata.google.internal/computeMetadata/v1/instance/zone` | The response body has the form `projects/<project-number>/zones/<zone>`. The zone is the text after the last `/`. |
| IPv6 capability | `http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ipv6s` | The client is IPv6-capable if the response body, with surrounding whitespace removed, is non-empty. |

Each query has a timeout of 10 seconds. The two queries MAY run in parallel.

A query fails if the request cannot be sent or completed (including a
timeout), or if the response status is not 200. A failed zone query, or a
zone response with no `/`, yields an empty zone. A failed IPv6 query yields
"not IPv6-capable". A failed query does not fail resolution: the resolver
generates the bootstrap with the values above.

## 5. Forcing xDS

If the target has the `force-xds` query parameter, the resolver uses the xDS
path without checking whether the client is on GCP and without querying the
metadata server. The generated bootstrap then has no `node.locality`, and the
client is treated as IPv6-capable.

## 6. Resolver Operations

- Re-resolution requests and backoff resets are forwarded to the child
  resolver (`dns` or `xds`).
- On shutdown, the resolver cancels any pending metadata query, shuts down its
  child resolver, and releases its reference to the XdsClient.

## 7. API Requirements

- An implementation that provides this resolver MUST make it available
  through the resolver registry under the scheme `google-c2p` (see
  [Name Resolution: Resolver Registry](../04-client-channel/03-name-resolution.md#1-resolver-registry)).
- No other API is required. The resolver's inputs are the target URI and the
  platform environment.
