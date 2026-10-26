# Appendix E. Historical and Superseded Behavior (Informative)

<!-- Sources: A5, A6, A15, A17, A24, A26, A27, A28, A29, A30, A31, A37, A42, A45, A47, A48, A50, A52, A53, A56, A61, A62, A64, A66, A72, A74, A75, A76, A78, A85, A88, A94, A96, A101, A115, grpc-proto grpc/service_config/service_config.proto (deprecated messages and fields) -->

This appendix is informative. It briefly lists mechanisms that were once part
of gRPC behavior but are no longer specified, and says what replaced each one.
It is meant to help readers of older gRFCs, older documentation, and older
configurations. Nothing in this appendix is a requirement. Where an old
configuration name or field is still *accepted* for compatibility, the
normative section that says so is linked.

## E.1 xDS Transport and Configuration

| Former behavior | Replaced by | Current spec |
| --- | --- | --- |
| **xDS v2 transport.** The xDS v2 API (`envoy.api.v2.*` resource types and the v2 ADS service) was the original transport. A bootstrap server feature selected v3. | Only xDS v3 is supported (A30). The `xds_v3` server feature is still recognized but has no effect. | [xDS](../09-xds/README.md) ([Transport protocol variant](../09-xds/README.md#21-transport-protocol-variant)); [Bootstrap](../09-xds/bootstrap.md) ([Bootstrap: Server Features](../09-xds/bootstrap.md#5-server-features)) |
| **`ignore_resource_deletion` server feature** (A53). It told the XdsClient to keep using a cached Listener or Cluster after the server deleted it. | Data error handling (A88): deletions of cached resources are ambient errors by default, and `fail_on_data_errors` opts into dropping them. The feature string is recognized but has no effect. | [XdsClient](../09-xds/xds-client.md) ([XdsClient: Error Handling](../09-xds/xds-client.md#7-error-handling)); [Bootstrap](../09-xds/bootstrap.md) ([Bootstrap: Server Features](../09-xds/bootstrap.md#5-server-features)) |
| **Does-not-exist timer semantics of A57.** | Modified by A88: the timer is not started while the channel is in TRANSIENT_FAILURE, and the server feature `resource_timer_is_transient_error` adds a second mode. | [XdsClient](../09-xds/xds-client.md) ([Does-not-exist timer](../09-xds/xds-client.md#74-does-not-exist-timer)) |
| **`lrs_load_reporting_server_name`** (a string that could only mean "the same server as the bootstrap"). | An XdsServer object identifying the LRS server (A47). | [Cluster](../09-xds/resources/cluster.md) ([Load Reporting](../09-xds/resources/cluster.md#7-load-reporting)); [Load Reporting (LRS)](../09-xds/load-reporting.md) |
| **SNI ignored for xDS TLS.** The `UpstreamTlsContext.sni` and `auto_sni_san_validation` fields were ignored (A29). | They are honored (A101). | [xDS Security](../09-xds/security.md) ([SNI Selection](../09-xds/security.md#23-sni-selection), [xDS Security: Server Identity Verification](../09-xds/security.md#3-server-identity-verification)) |
| **Routing on the last route only.** The first xDS client used only the default (last) route of the matched virtual host (A27). | Full route matching and weighted clusters (A28), evaluated per RPC by the xDS ConfigSelector (A31). | [Client Data Plane](../09-xds/client.md) ([Client Data Plane: xDS ConfigSelector](../09-xds/client.md#5-xds-configselector)) |

## E.2 xDS LB Policies

These policies had JSON configuration in
`grpc/service_config/service_config.proto`. The messages are now marked
deprecated. None of them is part of the current xDS LB policy tree
([xDS LB Policies](../09-xds/lb-policies.md)).

| Former policy | Role | Replaced by |
| --- | --- | --- |
| `xds` / `xds_experimental` (`XdsConfig`, with a `balancerName` field) | An early experimental policy that contacted an xDS server named in the service config, before there was a bootstrap file and an `xds` resolver. | The `xds` resolver and bootstrap configuration (A27). |
| `eds_experimental` (`EdsLoadBalancingPolicyConfig`) | Watched EDS and built the per-priority, per-locality tree. Also handled drops and load reporting (A27). | `xds_cluster_resolver` plus `xds_cluster_impl` (A37, A42). It was later replaced by the XdsDependencyManager plus the `cds` → `priority` → `xds_cluster_impl` tree (A74). |
| `lrs_experimental` (`LrsLoadBalancingPolicyConfig`) | Per-locality load recording for LRS (A27). | Load recording in `xds_cluster_impl` (A42), using locality attributes. |
| `xds_routing_experimental` | Route matching inside the LB policy, with `weighted_target` for traffic splitting (A28). | The xDS ConfigSelector (routing, per RPC) plus `xds_cluster_manager` (A31). |
| `xds_cluster_resolver_experimental` (`XdsClusterResolverLoadBalancingPolicyConfig`) | Watched EDS and resolved LOGICAL_DNS names for one cluster, or for all the clusters of an aggregate cluster. Produced the priority list (A37). | The XdsDependencyManager in the `xds` resolver supplies all resources in the `XdsConfig` attribute. `cds` builds the `priority` children directly (A74). |
| Fields of `xds_cluster_impl_experimental`: `eds_service_name`, `lrs_load_reporting_server`, `max_concurrent_requests`, `drop_categories`, `telemetry_labels` | Cluster data copied into the LB policy config. | Read from the `XdsConfig` resolver attribute (A74). |
| `override_host_status` field of the override-host policy config | Health statuses allowed for overriding. | Read from the Cluster resource in `XdsConfig`. |
| Child-policy generation from `Cluster.lb_policy` in the individual LB policy designs (A42, A48) | Each design converted its own Cluster fields. | The xDS LB policy registry and `Cluster.load_balancing_policy` (A52). The legacy `lb_policy` enum is still converted ([xDS LB Policies](../09-xds/lb-policies.md), [Legacy `lb_policy`](../09-xds/lb-policies.md#22-legacy-lb_policy)). |

## E.3 Aggregate Clusters

| Former behavior | Replaced by | Current spec |
| --- | --- | --- |
| **Aggregate cluster as one flattened priority list.** The priorities of all underlying clusters were concatenated into one `priority` policy, so each priority could have its configuration from a different cluster (A37). | An aggregate cluster is a `priority` policy whose children are `cds` policies, one for each underlying cluster (A75). | [xDS LB Policies](../09-xds/lb-policies.md) ([Aggregate cluster](../09-xds/lb-policies.md#12-aggregate-cluster), [Child config for an aggregate cluster](../09-xds/lb-policies/cds.md#5-child-config-for-an-aggregate-cluster)); [Client Data Plane](../09-xds/client.md) ([Aggregate cluster graph](../09-xds/client.md#23-aggregate-cluster-graph)) |
| **Per-priority outlier detection and stateful session affinity.** Because of the flattened list, `outlier_detection` (A50) and session affinity (A55, A60) were placed below `priority` and worked only within a single priority. | `outlier_detection`, `xds_cluster_impl`, and `xds_override_host` sit above the priority policy of each cluster, so they work across all of that cluster's priorities (A75). | [xDS LB Policies](../09-xds/lb-policies.md) ([xDS LB Policies: LB Policy Tree](../09-xds/lb-policies.md#1-lb-policy-tree)) |

## E.4 Load Reporting

| Former behavior | Replaced by | Current spec |
| --- | --- | --- |
| **All ORCA `named_metrics` propagated to LRS** by default, as custom metrics (A64). | Propagation is opt-in, controlled by the Cluster's LRS report configuration, and uses the `named_metrics.` prefix (A85). | [Load Reporting (LRS)](../09-xds/load-reporting.md) ([Load Reporting (LRS): Backend Metrics from ORCA](../09-xds/load-reporting.md#4-backend-metrics-from-orca)) |

## E.5 Client Channel and Load Balancing

| Former behavior | Replaced by | Current spec |
| --- | --- | --- |
| **grpclb and implicit selection.** Resolvers marked addresses as balancer addresses (`is_balancer`), and the presence of such addresses selected the `grpclb` policy implicitly (A5, A24). DNS SRV `_grpclb._tcp` records supplied the balancer addresses. | A26 made LB policy selection explicit (balancer addresses became a resolver attribute, and `grpclb` is chosen only through `loadBalancingConfig`). grpclb itself is not part of this specification. | [Name Resolution](../04-client-channel/name-resolution.md) ([LB Policy Selection](../04-client-channel/name-resolution.md#31-lb-policy-selection)); [Service Config](../04-client-channel/service-config.md) ([`loadBalancingConfig`](../04-client-channel/service-config.md#52-loadbalancingconfig)) |
| **Health checking inside the subchannel.** The subchannel ran the health-check stream itself and reported unhealthy as TRANSIENT_FAILURE to every user of the subchannel (A17). | A generic health watch on the subchannel. It is driven by `pick_first` when running under a petiole policy, and outlier detection ejects through it (A61). | [Client-Side Health Checking](../04-client-channel/health-checking.md); [Load Balancing](../04-client-channel/load-balancing.md) ([Load Balancing: Generic Health Reporting](../04-client-channel/load-balancing.md#10-generic-health-reporting)) |
| **Serial `pick_first` connection attempts.** Addresses were tried strictly one at a time (A62 background). | Happy Eyeballs, with a Connection Attempt Delay (A61). The address list is flattened and families are interleaved. | [`pick_first`](../04-client-channel/lb-policies/pick_first.md) ([Address List Processing](../04-client-channel/lb-policies/pick_first.md#3-address-list-processing), [Happy Eyeballs Connection Algorithm](../04-client-channel/lb-policies/pick_first.md#4-happy-eyeballs-connection-algorithm)) |
| **Policies that balance across addresses managed subchannels directly** (`round_robin`, `ring_hash`, `least_request`, `weighted_round_robin`). | Petiole policies with one `pick_first` child per endpoint. Endpoints can have several addresses (A61). | [Load Balancing](../04-client-channel/load-balancing.md) ([Leaf, Parent, and Petiole Policies](../04-client-channel/load-balancing.md#91-leaf-parent-and-petiole-policies)) |
| **`ring_hash` picker behavior of A42** (the picker scheduled connection attempts on hash collisions with failed endpoints). | Revised by A61 (endpoint children, with proactive connection logic in the policy) and A76 (`request_hash_header`, random hash for requests without a hash, endpoint hash keys). | [`ring_hash`](../04-client-channel/lb-policies/ring_hash.md) |
| **Retention of removed `priority` children.** A child removed from the config was kept, deactivated, for 15 minutes in case it came back (A56). | Removed children SHOULD be deleted immediately (A115), but an implementation MAY still retain them for up to 15 minutes. Deactivated lower priorities are still retained. | [`priority`](../04-client-channel/lb-policies/priority.md) ([Child Lifetime](../04-client-channel/lb-policies/priority.md#5-child-lifetime)) |
| **`loadBalancingPolicy` service config field.** A single policy name. | `loadBalancingConfig` (A24). The old field is still accepted but deprecated. | [Service Config](../04-client-channel/service-config.md) ([`loadBalancingPolicy` (deprecated)](../04-client-channel/service-config.md#53-loadbalancingpolicy-deprecated)) |

## E.6 Observability

| Former behavior | Replaced by | Current spec |
| --- | --- | --- |
| **OpenCensus stats and tracing**, including the OpenCensus retry metrics and attempt spans (A6, A45), and OpenCensus-based propagation. | OpenTelemetry metrics (A66, A79), OpenTelemetry tracing with the `grpc-trace-bin` propagator (A72), and OpenTelemetry retry metrics (A96). OpenCensus is not part of this specification. | [Metrics Framework](../08-observability/metrics-framework.md); [Metric Catalog](../08-observability/metrics.md); [Tracing](../08-observability/tracing.md) |
| **`pick_first` metrics** `grpc.lb.pick_first.disconnections`, `grpc.lb.pick_first.connection_attempts_succeeded`, and `grpc.lb.pick_first.connection_attempts_failed` (A78). | Subchannel metrics `grpc.subchannel.disconnections`, `grpc.subchannel.connection_attempts_succeeded`, and `grpc.subchannel.connection_attempts_failed`, with added optional labels, plus `grpc.subchannel.open_connections` (A94). | [Metric Catalog](../08-observability/metrics.md) ([Metric Catalog: Subchannel Metrics](../08-observability/metrics.md#4-subchannel-metrics)) |

## E.7 Standard Services

| Former behavior | Status | Current spec |
| --- | --- | --- |
| **Server reflection `grpc.reflection.v1alpha`.** The original package of the reflection service. | Deprecated by the promotion to `grpc.reflection.v1` (A15). It is wire-identical and still SHOULD be served alongside v1. Clients fall back to it on `UNIMPLEMENTED`. | [Server Reflection](../07-services/reflection.md) ([Server Reflection: Versions](../07-services/reflection.md#6-versions)) |
