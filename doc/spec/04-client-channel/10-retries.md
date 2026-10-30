> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 4.10 Retries and Hedging

<!-- Sources: A6, A54, grpc-proto grpc/service_config/service_config.proto, doc/service_config.md -->

> **Introduced by:** [gRFC A6: gRPC Retry Design](https://github.com/grpc/proposal/blob/master/A6-client-retries.md)

The gRPC client can automatically re-send a failed RPC as a new **attempt**.
It does this in three ways:

- **Transparent retries.** gRPC retries automatically, whatever the service
  config says, when it knows the server application never saw the attempt
  ([Transparent Retries](#8-transparent-retries)). Only disabling retries on the channel
  turns them off ([Limits and Disabling Retries](#10-limits-and-disabling-retries)).
- **Retry policy.** Configured per method in the service config. Failed
  attempts are re-sent with exponential backoff when the status is one of the
  listed retryable codes ([Retry Policy](#2-retry-policy)).
- **Hedging policy.** Configured per method in the service config. Several
  copies of the RPC are sent, staggered over time, without waiting for
  earlier ones to fail ([Hedging Policy](#3-hedging-policy)).

A method config can set at most one of `retryPolicy` and `hedgingPolicy`
(see [Service Config](03-service-config.md)). If neither is set, the RPC gets
transparent retries only. **Retry throttling** ([Retry Throttling](#4-retry-throttling))
and **server pushback** ([Server Pushback](#5-server-pushback)) limit configured
retries and hedges. The application's deadline always covers the RPC as a
whole, across all attempts.

## 1. Where Retries Happen

The retry layer sits between the per-call configuration stage and the LB pick
(see [Per-call Configuration and Call Flow](04-call-dispatch.md)). The ConfigSelector, method config,
and per-call interceptors are applied **once per RPC**. The LB pick, call
credentials, and transport stream happen **once per attempt**. Each attempt is
load-balanced on its own, so it may go to a different subchannel and server
than earlier attempts. The ConfigSelector's call attributes are the same for
every attempt. For example, under xDS all attempts of an RPC use the same
cluster.

The retry policy, hedging policy, and throttling parameters are taken from the
service config when the RPC starts and do not change for the life of the RPC.

## 2. Retry Policy

```json
"retryPolicy": {
  "maxAttempts": 4,
  "initialBackoff": "0.1s",
  "maxBackoff": "1s",
  "backoffMultiplier": 2,
  "retryableStatusCodes": [ "UNAVAILABLE" ]
}
```

### 2.1 Fields and Validation

If any rule in this table is broken, the whole service config is invalid (see
[Service Config](03-service-config.md)).

| JSON field | Type | Required | Validation and meaning |
| --- | --- | --- | --- |
| `maxAttempts` | integer | yes | MUST be a JSON integer greater than 1. It is the maximum number of attempts, including the original. Values above the client's limit (5 by default; see [Limits and Disabling Retries](#10-limits-and-disabling-retries)) are treated as that limit and are not a validation error. |
| `initialBackoff` | Duration | yes | MUST be a valid Duration string greater than 0. |
| `maxBackoff` | Duration | yes | MUST be a valid Duration string greater than 0. |
| `backoffMultiplier` | number | yes | MUST be a JSON number greater than 0. |
| `retryableStatusCodes` | array of status codes | yes | MUST be a non-empty JSON array. Each element MUST be a valid gRPC status code, given as an integer or as a case-insensitive name (for example `14`, `"UNAVAILABLE"`, or `"unavailable"`). |

Choosing retryable codes is up to the service owner. In general, only codes
that mean the server did not process the request are safe to retry. A wider
set (for example `INTERNAL`) is appropriate only for idempotent methods. gRPC
has no separate way to mark a method idempotent.

### 2.2 Backoff

Before each configured retry, the client waits a delay with ±20% jitter. Let
`n` be the number of retries since the original attempt or since the last
retry that followed a server pushback delay, whichever is later (`n = 1` for
the first one). The delay before retry `n` is:

$$
\text{delay}_n = \min\left(\text{initialBackoff} \times \text{backoffMultiplier}^{\,n-1},\ \text{maxBackoff}\right) \times \text{random}(0.8,\ 1.2)
$$

`random(0.8, 1.2)` is a uniformly distributed value drawn separately for each
retry. Because of the jitter, the delay can be a little below `initialBackoff`
or a little above `maxBackoff`. If the server sent a pushback delay, that
delay is used **instead** ([Server Pushback](#5-server-pushback)).

### 2.3 Behavior

When an attempt finishes, the retry layer decides as follows. The checks run
in order, and the first one that applies decides:

```
OnAttemptFinished(rpc, attempt, status, pushback):
  if (TransparentRetryApplies(attempt)):            // 4.10.8
    return StartAttemptNow(rpc, transparent = true)
  if (status == OK):
    throttle.RecordSuccess()                        // any RPC, policy or not
    return Commit(rpc, status)
  if (rpc.retry_policy == null):                    return Commit(rpc, status)
  if (pushback present and (negative or unparseable)):   // 4.10.5
    throttle.RecordFailure()
    return Commit(rpc, status)
  if (status.code not in retryableStatusCodes):     return Commit(rpc, status)
  if (!throttle.RecordFailureAndCheck()):           return Commit(rpc, status)  // throttled
  if (rpc.committed):                               return Finish(rpc, status)
  rpc.attempts_completed++
  if (rpc.attempts_completed >= effective_max_attempts):
                                                    return Commit(rpc, status)
  delay = pushback present ? pushback : Backoff(n)  // 4.10.2.2
  if (pushback present): reset n so the next backoff uses n = 1
  ScheduleAttempt(rpc, after = delay)               // still bounded by the deadline
```

- The RPC fails with the status of its last attempt.
<!-- REVIEW(judgment) [RETRY-1]: Throttle successes are now counted for every RPC on the channel, policy or not. The failure side is still unclear for RPCs without a retry policy: the pseudocode commits before the "don't retry" pushback check, so such a pushback is not recorded, while Token Accounting's failure rule reads as applying to any response with that pushback. Go records it for RPCs without a policy; C++ does not. Spec currently says: not recorded for RPCs without a policy (pseudocode). -->
- If `retryThrottling` is not configured, the `throttle` operations do
  nothing, and `RecordFailureAndCheck()` always allows the retry.
- If response headers are received on an attempt, the RPC is committed to
  that attempt ([Commit and Buffering](#7-commit-and-buffering)). A later failure of that
  attempt, for example a server-streaming RPC that fails mid-stream, is not
  retried. A Trailers-Only response does not commit the RPC by itself, so it
  can be retried.
- The status code is matched against `retryableStatusCodes` **after** the
  control plane status restriction ([Control Plane Status Restriction](04-call-dispatch.md#43-control-plane-status-restriction)).
  For example, if an LB policy fails a pick with `NOT_FOUND`, the code is
  rewritten to `INTERNAL`, and the attempt is retried only if `INTERNAL` is
  retryable. Service config and ConfigSelector errors are never retried,
  because they happen before the retry policy is known.
- LB pick results: an attempt whose pick result is **Fail** (and that is not
  `wait_for_ready`) finishes with the pick's status and goes through the
  checks above. An attempt whose pick result is **Drop** fails the RPC
  immediately with no retries.

## 3. Hedging Policy

```json
"hedgingPolicy": {
  "maxAttempts": 4,
  "hedgingDelay": "0.5s",
  "nonFatalStatusCodes": [ "UNAVAILABLE", "INTERNAL", "ABORTED" ]
}
```

A hedged RPC may run more than once on the server side, usually on different
backends. Service owners SHOULD configure hedging only for methods that are
safe to run more than once.

### 3.1 Fields and Validation

| JSON field | Type | Required | Validation and meaning |
| --- | --- | --- | --- |
| `maxAttempts` | integer | yes | MUST be a JSON integer greater than 1. It is the total number of attempts, including the original. Values above the client's limit (5 by default) are treated as that limit and are not a validation error. |
| `hedgingDelay` | Duration | no | If present, MUST be a valid Duration string. It is the interval between starting successive attempts. Absent or `"0s"` means all `maxAttempts` attempts are started at once. |
| `nonFatalStatusCodes` | array of status codes | no | If present, MUST be a JSON array of valid status codes, each an integer or a case-insensitive name. Absent means every non-OK status is fatal. |

### 3.2 Behavior

- The original attempt starts right away. If no attempt has committed the
  RPC after `hedgingDelay`, the next attempt starts. The rest follow every
  `hedgingDelay`, up to `maxAttempts` attempts in total. For example, with
  `maxAttempts: 4` and `hedgingDelay: "0.5s"`, there are 1, 2, 3, and 4
  outstanding attempts at about 0 ms, 500 ms, 1000 ms, and 1500 ms.
- Every message the application sends, and its half-close, goes to every
  outstanding attempt. Attempts started later get the buffered messages
  replayed.
- **Success or response headers.** When any attempt receives response headers
  or completes with `OK`, the RPC commits to that attempt. All other
  outstanding attempts are canceled, no more attempts start, and that
  attempt's result goes to the application.
- **Non-fatal status.** When an attempt fails with a code in
  `nonFatalStatusCodes`, the next attempt (if any are left) starts
  **right away**, skipping the rest of its delay. Later attempts go back to
  starting every `hedgingDelay`, counted from that start. Other outstanding
  attempts keep running.
- **Fatal status.** When an attempt fails with any other non-OK code, all
  outstanding attempts are canceled, no more start, and the RPC fails with
  that status.
- If every attempt has failed with a non-fatal status and no more can start
  (because of `maxAttempts`, throttling, or pushback), the RPC fails with the
  status of the last attempt to finish. The result goes to the application
  only after all outstanding and pending attempts have finished or been
  canceled.
- No retries happen after hedging: hedging works as retrying before a failure
  has been seen.
- The status code is matched against `nonFatalStatusCodes` after the control
  plane status restriction, as for retries.
- Throttling ([Retry Throttling](#4-retry-throttling)) and pushback
  ([Server Pushback](#5-server-pushback)) apply to every attempt after the first.
  The original attempt is always sent.
- Implementations MUST avoid races between canceling pending attempts and
  responses arriving on attempts already sent. The application MUST receive
  exactly one final status.

## 4. Retry Throttling

```json
"retryThrottling": { "maxTokens": 10, "tokenRatio": 0.1 }
```

Throttling turns off retries and hedging when the ratio of failures to
successes gets too high. This protects servers from being overloaded by
retries. It is set at the top level of the service config, not per method.

### 4.1 Fields and Validation

| JSON field | Type | Required | Validation |
| --- | --- | --- | --- |
| `maxTokens` | integer | yes | MUST be a JSON integer in the range (0, 1000]. |
| `tokenRatio` | number | yes | MUST be a JSON number greater than 0. Only 3 decimal places are used. Further digits are dropped, so `0.5466` is treated as `0.546`. |

### 4.2 Token Accounting

The client keeps a `token_count` for each server name (channel target). All
RPCs on the channel share it, whatever their service or method.
Implementations MAY share it among channels to the same target.

- `token_count` starts at `maxTokens` and always stays in `[0, maxTokens]`.
- Each attempt that **succeeds** (finishes with status `OK`) adds
  `tokenRatio`, up to `maxTokens`. This applies to every RPC on the channel,
  whether or not it has a retry or hedging policy. Receiving response
  headers is not a success by itself; only the final `OK` status counts, and
  a Trailers-Only `OK` response counts like any other.
- Each attempt that **fails** in a way that counts subtracts 1, down to 0. A
  failure counts if its status code is in `retryableStatusCodes` (retry
  policy) or `nonFatalStatusCodes` (hedging policy), or if the response
  carries a pushback that says not to retry. Other failures, for example
  `INVALID_ARGUMENT`, leave `token_count` unchanged. That way, responses to
  malformed requests are not mistaken for server trouble.
- Transparent retries ([Transparent Retries](#8-transparent-retries)) do not count as
  successes or failures.
- The **threshold** is `maxTokens / 2`. While `token_count <= threshold`,
  configured retries are not made, and hedged attempts after the first are
  not sent. A throttled retry does not wait for tokens: the RPC fails with
  the current attempt's status. A throttled hedge is not sent. If no other
  hedged attempt is outstanding, the RPC fails with the last failure.
- When a new service config changes the throttling parameters, the
  implementation SHOULD keep the current ratio `token_count / maxTokens`.

## 5. Server Pushback

A server can tell the client how to retry by setting the response trailer
`grpc-retry-pushback-ms`:

- The value is an ASCII decimal signed 32-bit integer with no unnecessary
  leading zeros. It is the number of milliseconds to wait before the next
  attempt.
- A **non-negative** value means "retry after exactly this delay", if a retry
  is otherwise allowed: the status is retryable, attempts remain, the RPC is
  not throttled, and it is not committed. The delay replaces the computed
  backoff. Retries after that one compute their backoff from
  `initialBackoff` again (`n = 1`), unless another pushback arrives.
- A **negative** or **unparseable** value means "do not retry". The RPC
  fails with the attempt's status.
- Pushback never lets the RPC go past `maxAttempts`.
- For hedging: "do not retry" stops all further hedged attempts, while
  outstanding ones continue. A delay of *n* ms starts the next hedged attempt
  after *n* ms, and the ones after it follow every `hedgingDelay` from there.

## 6. Summary of Retry and Hedging Behavior

In every case, no more attempts are started once `maxAttempts` is reached.

| Server response | Retry policy | Hedging policy |
| --- | --- | --- |
| `OK` | Return success to the application. | Cancel the other outstanding attempts and don't start pending ones. Return success. |
| Fatal (not retryable or non-fatal) status | Don't retry. Return the failure. | Cancel the other outstanding attempts and don't start pending ones. Return the failure. |
| Retryable or non-fatal status, no pushback | Retry after the backoff ([Backoff](#22-backoff)). | Start the next hedged attempt right away. The ones after it resume every `hedgingDelay`. |
| Pushback: don't retry | Don't retry. Return the failure. | Start no more hedged attempts. |
| Pushback: retry in *n* ms | Retry in *n* ms. If that attempt also fails, the next backoff starts again from `initialBackoff`. | Start the next hedged attempt in *n* ms. The ones after it follow every `hedgingDelay` from there. |

## 7. Commit and Buffering

An RPC is **committed** once the client has chosen the single attempt whose
outcome goes to the application. After that, no more attempts start, either
configured or transparent. The RPC commits when the first of these happens:

1. An attempt receives **response headers**: the server's initial metadata
   in a non-Trailers-Only response. The response headers go to the
   application, which may change its state based on them, so a later failure
   cannot be hidden by a retry. Servers SHOULD delay response headers until
   the first response message or until the application explicitly sends
   headers. If a server fails an RPC before sending headers or messages, it
   SHOULD use Trailers-Only so the RPC can still be retried.
2. The RPC's outgoing data overflows the **retry buffer**
   ([Buffer Limits](#71-buffer-limits)).
3. The retry layer decides to make no more attempts: success, a fatal status,
   attempts used up, throttling, pushback that says not to retry, the
   deadline, or cancellation.

When the RPC commits, the channel invokes the ConfigSelector's on-commit
callback, if there is one ([Per-call Configuration and Call Flow](04-call-dispatch.md)).

With a retry policy, the current attempt continues after the commit, and no
later attempt starts even if it fails with a retryable status. With hedging,
the commit keeps the attempt that has sent the most messages (the attempt
that got headers, if that caused the commit). All other outstanding attempts
are canceled at once, and pending ones never start.

### 7.1 Buffer Limits

The retry layer buffers everything the client sends on an RPC (request
headers, messages, and half-close) until the RPC commits, so it can replay
the data on a new attempt. Retries and hedging are possible only while all
the RPC's outgoing data is still buffered.

- The client application sets the buffer limits through the channel API. The
  service config does not set them. There MUST be a **per-RPC** limit. Its
  default SHOULD be 256 KiB. Implementations MAY also provide a
  **per-channel** limit (total buffer memory for all RPCs on the channel),
  with an implementation-defined default.
- If a new RPC's initial data does not fit in the available space, under
  any limit, the RPC is committed right away. It is still sent but cannot
  be retried.
- When the application sends a message that would push the RPC past any
  limit, the RPC commits. That message is never buffered. It waits until all
  earlier messages have been replayed on the chosen attempt, then is sent
  directly.
- After the commit, messages already sent on the chosen attempt are freed
  right away. Each message still being replayed is freed as soon as it is
  sent.
- When the RPC completes, all of its buffered data is freed.

## 8. Transparent Retries

An RPC attempt can fail in four different places:

| # | Where it fails | Handling |
| --- | --- | --- |
| 1 | At the LB pick | **Drop**: the RPC fails right away with no retries of any kind. **Fail**: handled by the configured retry policy, if any ([Behavior](#23-behavior)). Never transparently retried. |
| 2 | After a successful pick, but nothing reached the network (for example, the connection failed before the stream was created or before anything was written) | Transparently retried, any number of times, until success or the deadline. |
| 3 | It reached the server's gRPC library, but the server application never saw it | Transparently retried **once** per RPC. If that retry also fails this way, the failure goes to the configured retry policy. |
| 4 | The server application saw it and it failed | Handled only by the configured retry policy or hedging policy. |

In the HTTP/2 transport, the client knows it is in case 3 when either of
these happens (see [HTTP/2 Transport Behavior](../03-wire-protocol/02-http2-transport.md)):

- the stream is reset with `RST_STREAM` error code `REFUSED_STREAM`;
- the connection receives a `GOAWAY` whose last-stream-ID is lower than the
  attempt's stream ID.

Transparent retries:

- happen whatever the service config says, including for RPCs with no retry
  or hedging policy. They SHOULD happen even when the application has
  disabled retries on the channel
  ([Limits and Disabling Retries](#10-limits-and-disabling-retries));
- happen only while the RPC is uncommitted, so its data is still buffered;
- start the new attempt right away, with no backoff. The new attempt goes
  through the LB pick again, under the normal `wait_for_ready` rules;
- do not count toward `maxAttempts`, are not counted by retry throttling, and
  do not increase `grpc-previous-rpc-attempts`;
- stay bounded by the RPC's deadline.

## 9. `grpc-previous-rpc-attempts`

On every attempt after the first, the client sets the request header
`grpc-previous-rpc-attempts` to the number of earlier attempts of the RPC,
counting configured retries and hedged attempts. The header is a decimal
integer.

- The original attempt does not carry the header. The second attempt carries
  `1`, the third `2`, and so on. For hedging, the *k*-th hedged attempt
  (counting the original as the 1st) carries `k-1`.
- A transparent retry carries the same value as the attempt it replaces.
- The server can read the header, for example to log or adjust behavior. The
  client MAY also expose it to the application in the received metadata.

## 10. Limits and Disabling Retries

- **Client-side `maxAttempts` limit.** The client caps `maxAttempts` from both
  retry and hedging policies. The cap is 5 by default, and the application
  can change it with a channel option. A service config `maxAttempts` above
  the cap is treated as the cap. This limits how much load a service config
  can cause, since it may come from an untrusted source such as DNS.
- **Disabling retries.** Applications cannot override a retry policy from the
  service config, but they can disable configured retries and hedging for a
  whole channel with a channel option. This is for applications or libraries
  that do their own retries. With retries disabled, the service config's
  `retryPolicy`, `hedgingPolicy`, and `retryThrottling` are still validated
  but have no effect. Transparent retries ([Transparent Retries](#8-transparent-retries))
  SHOULD still happen when retries are disabled. They are safe, because the
  server application never saw the request, and they avoid spurious errors.
  Applications that disable retries usually want only to avoid duplicating
  configured retries.

## 11. Interactions

- **Deadlines.** The RPC's deadline covers all attempts. When it expires,
  every outstanding attempt is canceled, any scheduled retry or hedge is
  abandoned, and the RPC fails with `DEADLINE_EXCEEDED`. That holds even
  during a backoff or pushback delay, and even if attempts remain. Each
  attempt sends the time remaining until the RPC's deadline as its timeout
  ([gRPC over HTTP/2](../03-wire-protocol/01-http2.md)). A method config `timeout` affects
  the RPC deadline as described in [Per-call Configuration and Call Flow](04-call-dispatch.md).
  There is no separate per-attempt timeout in the service config.
- **Cancellation.** When the application cancels an RPC, all its attempts are
  canceled and no more start.
- **`wait_for_ready`.** It applies to each attempt's LB pick. A
  `wait_for_ready` attempt whose pick returns Fail stays queued instead of
  failing, so it is not retried ([Per-call Configuration and Call Flow](04-call-dispatch.md)).
- **Control plane status restriction.** Status codes from pick failures and
  call credentials are rewritten before retry matching
  ([Control Plane Status Restriction](04-call-dispatch.md#43-control-plane-status-restriction)).
- **xDS.** xDS route configuration can set retry policies. The xDS
  ConfigSelector turns them into the method config's retry policy. See
  [Client Data Plane](../09-xds/04-client.md).
- **Observability.** Retry-related metrics (attempts per call, transparent
  retries, retry delay) are in [Metric Catalog](../08-observability/03-metrics.md).
  Per-attempt instrumentation is in
  [Instrumentation Architecture](../08-observability/01-instrumentation.md).

## 12. API Requirements

- The channel API MUST provide an option to disable configured retries and
  hedging for the channel ([Limits and Disabling Retries](#10-limits-and-disabling-retries)).
- The channel API MUST provide an option to set the client-side `maxAttempts`
  limit (default 5).
- The channel API MUST provide an option to set the per-RPC retry buffer
  limit, and MAY provide one to set a per-channel limit
  ([Buffer Limits](#71-buffer-limits)).
- The call API MUST let the application cancel an RPC, which cancels all of
  its attempts, and MUST apply the RPC's deadline across all attempts.
- gRPC MUST NOT give applications a way to override a service config retry or
  hedging policy per RPC. The only application controls are disabling
  retries and the limits above.
- Instrumentation APIs MUST expose each attempt separately and MUST indicate
  whether an attempt is a transparent retry (see
  [Instrumentation Architecture](../08-observability/01-instrumentation.md)).
