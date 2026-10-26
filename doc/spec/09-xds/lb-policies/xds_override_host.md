# `xds_override_host` LB Policy

<!-- Sources: A55, A60, A61, A74, A75, grpc-proto grpc/service_config/service_config.proto -->

> **Experimental:** This policy is registered as `xds_override_host_experimental`.

**Registered name:** `xds_override_host_experimental`.
**Config** (`OverrideHostLoadBalancingPolicyConfig`):

| JSON field | Type | Description |
| --- | --- | --- |
| `clusterName` | string | Required. The leaf cluster name. |
| `childPolicy` | LoadBalancingConfig list | Required. Child policy. |

The deprecated `overrideHostStatus` field MUST be ignored. The policy takes
two values from the parsed cluster resource in the `XdsConfig`:

- `override_host_statuses`: the set of EDS health statuses for which the
  session override is honored. It comes from
  `common_lb_config.override_host_status`. Only UNKNOWN, HEALTHY, and
  DRAINING are meaningful. The default is {UNKNOWN, HEALTHY}.
- `connection_idle_timeout` (called `idle_timeout` below): from the
  cluster's `upstream_config` HTTP protocol options
  `common_http_protocol_options.idle_timeout`, default 1 hour.

Validation of both is in [resources/cluster.md](../resources/cluster.md). The
policy is always present in the tree. If no stateful session xDS HTTP filter
is configured, no RPC carries the override attribute and the policy only
passes picks through.

## 1. Address map

The policy keeps an **address map** from address (`IP:port` string) to an
entry with:

- the subchannel for that address, if any, and whether the policy itself
  **owns** it or the child policy owns it;
- the subchannel's last-seen connectivity state;
- the endpoint's EDS health status;
- the endpoint's **address list**: all addresses of the endpoint as a
  comma-separated string, with this entry's address first (this is what the
  session cookie must contain if this address is used);
- the endpoint's per-endpoint attributes (used to create a subchannel);
- `last_used_time`: the last time the entry was used for a session.

On each update from `cds`:

1. For each endpoint in the update, and each of its addresses, the entry is
   created or updated with the health status, address list, and attributes.
   Exception: an endpoint whose health status is DRAINING and is not in
   `override_host_statuses` is left out of the map.
2. Entries for addresses no longer present are removed. Any subchannel the
   policy owns for them is released.
3. The endpoint list passed to the child **always** leaves out endpoints in
   state DRAINING, whatever `override_host_statuses` contains. DRAINING endpoints
   receive only session traffic.
4. The idle sweep timer is rescheduled ([Idle sweep](#3-idle-sweep)).

## 2. Subchannel ownership

- When the child creates a subchannel, the policy wraps it and records it in
  the entry for its address as child-owned. If the policy owned a subchannel
  for that address, it releases its own one.
- When the child releases a subchannel: if the entry's `last_used_time` is
  within `idle_timeout` of now, the policy takes ownership of the subchannel
  instead of letting it be destroyed. Otherwise, the subchannel is removed
  from the entry.
- A subchannel that the child does not own is created by the policy when the
  picker needs it for a session ([Picker](#4-picker)). This happens, for
  example, for an endpoint in a lower priority whose `priority` child has not
  been created, or for a DRAINING endpoint. Such a subchannel is created with
  the entry's per-endpoint attributes and is owned by the policy.
- The policy tracks the connectivity state of every subchannel in the map,
  whoever owns it.

## 3. Idle sweep

The policy runs a timer that releases owned subchannels that have not been
used for a session within `idle_timeout`:

```
def Sweep():
  now = Now(); next = idle_timeout
  for entry in address_map:
    if entry.last_used_time <= now - idle_timeout:
      release entry's owned subchannel, if any
    else:
      next = min(next, entry.last_used_time + idle_timeout - now)
  schedule Sweep after max(next, 5 seconds)
```

The timer first runs after `idle_timeout` (or earlier, from the entries'
`last_used_time`). Runs are at least 5 seconds apart. Child-owned subchannels
are never released by the sweep.

## 4. Picker

`last_used_time` is updated only for RPCs that carry the override-host call
attribute, which the stateful session xDS HTTP filter sets (see
[http-filters.md](../http-filters.md)). The attribute contains the cookie's
address list. The policy uses it to report back the actual address list of the
endpoint that was used.

```
def Pick(pick_args):
  attr = pick_args.call_attributes.get(override_host_attribute)
  if attr is not None and attr.cookie_address_list is not empty:
    entry_with_no_subchannel = None
    idle_subchannel = None
    found_connecting = False
    for address in attr.cookie_address_list:        # comma-separated, in order
      entry = address_map.get(address)
      if entry is None: continue
      if entry.health_status not in override_host_statuses: continue
      if entry.subchannel is None:
        if entry_with_no_subchannel is None: entry_with_no_subchannel = entry
        continue
      if entry.subchannel.state == READY:
        entry.last_used_time = Now()
        attr.set_actual_address_list(entry.address_list)
        return COMPLETE(entry.subchannel)
      elif entry.subchannel.state == IDLE:
        if idle_subchannel is None: idle_subchannel = entry.subchannel
      elif entry.subchannel.state == CONNECTING:
        found_connecting = True
    if idle_subchannel is not None:
      in the control plane: request a connection on idle_subchannel
      return QUEUE
    if found_connecting:
      return QUEUE
    if entry_with_no_subchannel is not None:
      in the control plane: create an owned subchannel for that entry
      return QUEUE
    # Only TRANSIENT_FAILURE subchannels found (or no usable entries):
    # fall through to normal load balancing.
  result = child_picker.Pick(pick_args)
  if result is COMPLETE and attr is not None:
    entry = address_map.get(address of result.subchannel)
    if entry is not None:
      entry.last_used_time = Now()
      attr.set_actual_address_list(entry.address_list)
  return result
```

The map is read by pickers and written by the policy concurrently, so access
MUST be synchronized (for example, with a reader/writer lock). The policy
reports its child's connectivity state unchanged. It reports a new picker when
the child does, and when it creates an owned subchannel.

## 5. API Requirements

- gRPC MUST register this policy in the LB policy registry under the name `xds_override_host_experimental` so that the configuration generated by the xDS client data plane can select it.
- This policy is internal to xDS support. Applications are not expected to configure it directly, and gRPC is not required to provide any public API specific to it beyond the general LB policy API requirements in [xDS LB Policies: API Requirements](../lb-policies.md#3-api-requirements).
