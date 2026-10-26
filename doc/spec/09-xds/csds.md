> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 9.10 Client Status Discovery Service (CSDS)

<!-- Sources: A40, A46, A71, A88 -->

gRPC provides an implementation of the xDS **Client Status Discovery Service**
(CSDS). It lets an operator or tool ask a running gRPC process which xDS
configuration it is currently using. The CSDS service reports the state of
every XdsClient instance in the process (see [XdsClient](xds-client.md)).
It is one of the services in the admin interface (see
[Admin Interface](../07-services/admin.md)).

## 1. Service

The service is `envoy.service.status.v3.ClientStatusDiscoveryService`, defined
in `envoy/service/status/v3/csds.proto`:

```proto
service ClientStatusDiscoveryService {
  rpc StreamClientStatus(stream ClientStatusRequest) returns (stream ClientStatusResponse);
  rpc FetchClientStatus(ClientStatusRequest) returns (ClientStatusResponse);
}
```

- **`FetchClientStatus`** (unary) returns one `ClientStatusResponse` that
  reflects the state at the time of the request.
- **`StreamClientStatus`** (bidirectional streaming) writes one
  `ClientStatusResponse` for each `ClientStatusRequest` it reads, computed
  when that request is read. It is not a watch API: the server never sends a
  response that was not requested. The RPC ends with OK when the client
  half-closes.

Only the v3 service is provided. A request for any other version of the
service fails with UNIMPLEMENTED, as for any unregistered method.

## 2. Request Handling

`ClientStatusRequest` fields:

| Field | Handling |
| --- | --- |
| `node_matchers` | Node matching is meant for control planes that serve many nodes. A gRPC process is a single node (per XdsClient). If `node_matchers` is **non-empty**, the request MUST fail with status INVALID_ARGUMENT. |
| `node` | Ignored. |
| `exclude_resource_contents` | Ignored. `xds_config` is populated as described below regardless of this field. |

If the process has no XdsClient instances (for example, the bootstrap
configuration was never loaded), the response contains no `ClientConfig`
entries. This is not an error.

## 3. Response Contents

A `ClientStatusResponse` has one **`ClientConfig`** in its `config` field for
each live shared XdsClient instance in the process (see
[XdsClient: XdsClient Instances](xds-client.md#1-xdsclient-instances)). Each `ClientConfig` reflects
a consistent snapshot of that instance's cache.

### 3.1 `ClientConfig`

| Field | Contents |
| --- | --- |
| `node` | The `envoy.config.core.v3.Node` exactly as the XdsClient sends it to xDS servers: the bootstrap `node` fields plus the gRPC-filled `user_agent_name`, `user_agent_version`, and `client_features` (see [Bootstrap](bootstrap.md#42-node-object)). |
| `client_scope` | The XdsClient instance's key: the data-plane channel target for client channels, or `#server` for the instance shared by xDS-enabled servers. |
| `generic_xds_configs` | One `GenericXdsConfig` for each resource that has at least one watcher in that instance, across all authorities and resource types. |
| `xds_config` (deprecated `PerXdsConfig`) | Not populated. |

### 3.2 `GenericXdsConfig`

| Field | Contents |
| --- | --- |
| `type_url` | The full type URL of the resource, for example `type.googleapis.com/envoy.config.cluster.v3.Cluster`. |
| `name` | The resource name. A new-style name is shown in normalized `xdstp:` form (see [XdsClient: Resource Names](xds-client.md#3-resource-names)). |
| `client_status` | The cache entry state, mapped as in the table below. |
| `xds_config` | Present only if the entry holds a cached resource. It is an `Any` whose `type_url` is the resource type URL and whose `value` is the **raw serialized resource exactly as received** from the xDS server (after removing any `envoy.service.discovery.v3.Resource` wrapper). It includes fields that gRPC does not understand. |
| `version_info` | Present only if a resource is cached. The `version_info` of the response that delivered the cached resource. |
| `last_updated` | Present only if a resource is cached. The time the cached resource was last accepted. |
| `error_state` | Present only if the entry has an error. See [`error_state`](#33-error_state). |
| `config_status`, `is_static_resource` | Not populated. |

`client_status` mapping (`envoy.admin.v3.ClientResourceStatus`, in
`envoy/admin/v3/config_dump_shared.proto`):

| Cache entry state ([Cache entry states](xds-client.md#62-cache-entry-states)) | `client_status` | Resource (`xds_config`) present |
| --- | --- | --- |
| `REQUESTED` | `REQUESTED` | No |
| `DOES_NOT_EXIST` | `DOES_NOT_EXIST` | Only after an LDS/CDS deletion that was ignored because `fail_on_data_errors` is not set |
| `ACKED` | `ACKED` | Yes |
| `NACKED` | `NACKED` | Yes if a previously accepted version is still cached |
| `RECEIVED_ERROR` | `RECEIVED_ERROR` | Yes if a previously accepted version is still cached |
| `TIMEOUT` | `TIMEOUT` | No |

### 3.3 `error_state`

`error_state` is an `envoy.admin.v3.UpdateFailureState`. It shows the most
recent error for the resource and follows the XdsClient's per-resource
handling:

| Field | Contents |
| --- | --- |
| `details` | The error message: the validation error for this resource (NACK), the deletion reason (LDS/CDS deletion), the server-reported error message (`RECEIVED_ERROR`), or the timer message (does-not-exist or timeout). |
| `version_info` | The `version_info` of the response that caused the error, for NACKs, deletions, and server-reported errors. Not set when the error came from the does-not-exist timer. |
| `last_update_attempt` | The time of that response. Not set when `version_info` is not set. |
| `failed_configuration` | Not populated. |

Because NACKs work per resource (see
[Processing a response](xds-client.md#43-processing-a-response)), only the resources that
failed validation get `client_status` `NACKED` and an `error_state`. Valid
resources in the same response are `ACKED`, with the new version and no
`error_state`. When a later valid version of a resource is accepted, its
`error_state` is cleared.

<!-- REVIEW(divergence) [CSDS-1]: All three set NACKED/error_state only on the resources that failed validation; valid resources in the same response are ACKED (C++ xds_client.cc SetNacked/SetAcked; Java XdsClientImpl.handleResourceUpdate onData/onRejected; Go internal/xds/clients/xdsclient/authority.go). This differs from A40's example (all resources NACKED), which predates A46. Remaining divergence in `details`: C++ and Go store that resource's own validation error; Java stores the joined errors for the whole response. Spec says: the resource's own error (C++/Go). -->

Example: endpoints A, B, and C are watched. A response with version 1
contains valid A, B, and C. A response with version 2 contains a valid A and
an invalid B.

| Resource | `client_status` | `version_info` / resource | `error_state` |
| --- | --- | --- | --- |
| A | `ACKED` | `2` / version 2 of A | none |
| B | `NACKED` | `1` / version 1 of B (still cached; `fail_on_data_errors` not set) | `details`: B's validation error; `version_info` `2` |
| C | `ACKED` | `1` / version 1 of C (EDS has no deletion semantics) | none |

## 4. API Requirements

- gRPC MUST provide an implementation of the CSDS service that an application
  can register on any gRPC server. The CSDS service MUST be part of the set
  of services registered by the admin interface (see
  [Admin Interface](../07-services/admin.md)).
- The CSDS service MUST report on every shared XdsClient instance in the
  process, whichever server it is registered on. Dedicated instances created
  for a channel or server with its own programmatic bootstrap configuration
  (see [Bootstrap](bootstrap.md)) MAY be left out.
