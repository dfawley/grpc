> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# gRPC Specification Style Guide

This guide describes how the documents in this directory are written. Follow it
when adding to or changing the specification.

## 1. Scope and Content

1. **Current behavior only.** Describe how gRPC behaves today. Do not include
   history ("previously", "gRFC Axx changed …"). Superseded mechanisms are
   omitted.
2. **Cross-language behavior only.** The spec covers behavior that is
   implemented across languages or defined in gRFCs. Never say which languages
   implement something, and never mention specific implementations by name.
   Where implementations diverge, the spec states the single desired behavior.
3. **Never call anything "optional".** Apart from the wire protocol, almost
   everything in gRPC is optional in practice. Observations about features that
   some implementations lack belong in
   [gRPC Spec: Optionality Notes](../spec-optionality-notes.md), not in the spec.
4. **Experimental features** are included and marked with a line of the form
   `> **Experimental:** <what is experimental>` (for example, metrics marked
   experimental, or LB policies whose registered names end in `_experimental`).
5. **Temporary environment-variable guards** and backward-compatibility opt-outs
   are never mentioned. Permanent configuration environment variables (such as
   `GRPC_XDS_BOOTSTRAP`) are documented.
6. **"Filter"** is used only for the xDS term "xDS HTTP filter". For
   gRPC-internal mechanisms, use "interceptor" or describe the behavior.
7. **API requirements.** Each document has an `API Requirements` section
   stating, abstractly, what applications MUST be able to do through gRPC's
   public API (for example, "The channel API MUST provide a way to …"). Do not
   use language-specific names or signatures. Internal plugin APIs (resolver, LB
   policy, subchannel, picker, and so on) are also specified abstractly.
8. **Sources.** The spec is derived from the gRFCs (which act as a changelog),
   the documents in `grpc/doc`, and the protos in `grpc-proto`. Each document
   lists its sources in an HTML comment under its H1, e.g.
   `<!-- Sources: A61, A62, doc/load-balancing.md -->`. Apart from feature
   origin annotations ([Feature Origin Annotations](#5-feature-origin-annotations)),
   the body text does not cite gRFCs.

## 2. Document Format

- GitHub-flavored Markdown. RFC 2119 keywords are written in uppercase where
  normative.
- **Banner.** Every document starts, above its H1, with the `> [!WARNING]`
  banner stating that it is part of a new, experimental gRPC specification
  (linked to the top-level README), generated primarily by AI and not yet fully
  reviewed. The top-level README has a similar banner without the link.
- **Precision.** Include config field names, JSON names, defaults, limits,
  validation rules, metadata keys, state machines, algorithms (pseudocode is
  welcome), and status-code behavior. Prefer tables for field-by-field rules.
- **Proto references** name the file by repository path, e.g.
  `grpc/service_config/service_config.proto`.
- **Review comments.** Open questions about the spec are marked inline with
  `<!-- REVIEW(<category>) [<NAME>]: <details> -->`, where `<NAME>` identifies
  the item in the review tracker. Do not put review comments inside code blocks.

## 3. Numbering and Cross-References

- Each document's H1 carries its section number, e.g.
  `# 4.6 Subchannels and Connections`. LB policy documents are unnumbered, e.g.
  ``# `pick_first` LB Policy``.
- Within a document, subsections omit the parent number: H2 is `## N. Title`,
  H3 is `### N.M Title`, and H4 and deeper are unnumbered. Avoid nesting deeper
  than H3.
- Appendix sections use `## A.1 …`; glossary headings are `## A`, `## B`, and
  so on.
- Never refer to sections by number across documents. Cross-references are
  relative links whose text is the target's title, e.g.
  `[Connection Backoff](04-client-channel/06-subchannels.md#7-connection-backoff)`.
- Index documents (READMEs and Load Balancing's policy list) list documents by
  name, unnumbered.
- **File names.** Each top-level section is a directory named for its
  two-digit section number, e.g. `04-client-channel/`, with its overview in
  `README.md`. A numbered document inside a section is named
  `NN-<name>.md`, where `NN` is the two-digit last component of the section
  number in its H1: `# 4.9 Client-Side Backend Metrics (ORCA)` is
  `04-client-channel/09-backend-metrics.md`. A numbered group of documents is a
  directory named the same way (section 9.3 is `09-xds/03-resources/`).
  Unnumbered documents keep plain names: LB policy documents (named after the
  policy, in `lb-policies/` directories), appendices (`a-…` through `g-…`), and
  `README.md` files. When a document is renumbered, rename its file to match.

## 4. LB Policy Documents

Every LB policy document (`04-client-channel/lb-policies/*.md` and
`09-xds/lb-policies/*.md`) uses exactly this structure, in this order:

```
<banner>

# `<policy>` LB Policy

<!-- Sources: ... -->

> **Experimental:** ...            (only if the name or config is experimental)

## 1. Overview
### 1.1 Position in the xDS LB Policy Tree    (xDS policies only)
## 2. Configuration
### 2.1 Validation
## 3. … K.  <policy-specific behavior sections>
## K+1. LB Policy API
## K+2. API Requirements
```

### 4.1 Overview

- One or two paragraphs saying what the policy does and whether it is a leaf,
  parent, or petiole policy.
- Ends with the line ``Registered name: `<name>`.``
- **xDS policies** include `### 1.1 Position in the xDS LB Policy Tree`. It
  contains the canonical xDS LB policy tree: a nested Markdown list in which
  every policy is a link to its document. The tree is identical in every xDS
  policy document except that the current policy is bold and marked
  "(this policy)". It is followed by one sentence describing the policy's parent
  and children. When the tree changes, update it in every xDS policy document
  and in [xDS LB Policies](09-xds/05-lb-policies.md).

### 4.2 Configuration

Configuration always appears as section 2, in this fixed layout:

1. A line naming the proto message, e.g.
   ``Proto: `RoundRobinConfig` in `grpc/service_config/service_config.proto`.``
   If the config has no proto message, say so.
2. A JSON example of the policy's complete `LoadBalancingConfig` entry (the
   object keyed by the registered name) in a `json` code block, showing every
   field.
3. A field table with exactly these columns:

   | Field | Type | Required | Default | Description |
   | --- | --- | --- | --- | --- |

   - **Field** is the JSON name in backticks. Nested fields use dotted paths,
     list elements use `[]`, and map values use `{}`, e.g.
     `children{}.config` or `grpcKeybuilders[].names[].service`. A
     `LoadBalancingConfig list` field is a single row.
   - **Type** uses only: `string`, `bool`, `uint32`, `uint64`, `int32`, `int64`,
     `number`, `Duration` (a JSON string such as `"10s"`), `object`,
     `list of <type>`, `map of string → <type>`, `LoadBalancingConfig list`,
     or `enum` (values listed in Description).
   - **Required** is `Yes` or `No`. **Default** is the default value, or `—`.
   - If the config has no fields, the table is replaced by "The config has no
     fields; it MUST be an empty JSON object."
4. `### 2.1 Validation` lists every condition that makes the config invalid.

### 4.3 LB Policy API

States how the policy implements each operation of the generic LB policy API
([Load Balancing](04-client-channel/05-load-balancing.md): LB Policy API, Helper
API, and Subchannel Interface for LB Policies), as a table with exactly these
rows, in this order:

| Operation | Behavior |
| --- | --- |
| `Update(update) → status` | |
| `ExitIdle()` | |
| `ResetBackoff()` | |
| `Shutdown()` | |
| Subchannel connectivity / health updates | |
| Child `UpdateState(state, status, picker)` | |
| Child `RequestReresolution()` | |
| Child `CreateSubchannel(address, attributes)` | |

- `Update` covers config changes, endpoint lists, endpoint errors, attributes,
  and the returned status; it summarizes and links to the detailed sections.
- Rows that do not apply say so ("Not applicable: the policy has no child
  policies.").
- The picker is specified in its own policy-specific section.

## 5. Feature Origin Annotations

A section that specifies a distinct feature introduced by a gRFC links to that
gRFC, so readers can find its motivation and design discussion.

### 5.1 When to Annotate

Annotate a feature that a reader could reasonably think of as a unit that can
be turned on, configured, or used on its own. Examples:

- An LB policy, resolver, credentials type, or certificate provider.
- An xDS HTTP filter, an xDS resource type or major resource field, or an xDS
  server or client feature.
- A self-contained capability configured by its own fields or options, such as
  connection scaling, retries and hedging, outlier detection, stateful session
  affinity, or authority rewriting.
- A standard service (health, reflection, ORCA, CSDS, admin) or a named set of
  metrics.

Do not annotate:

- Clarifications, bug fixes, validation rules, or small behavior changes, even
  if a gRFC made them.
- Behavior that predates the gRFC process (for example, the core HTTP/2 wire
  protocol), or that no gRFC introduced.
- Every paragraph a gRFC touched.

A feature often appears in more than one document: for example, connection
scaling is specified in Subchannels and Connections, configured through a
service config field, and set from xDS by a Cluster field. Annotate **every**
section that a feature adds or that is dedicated to it, in every document, not
just the main one (in this example: the subchannel section, the service config
`connectionScaling` section, and the xDS section that maps the Cluster field).
A part of a feature that has no section of its own (a single table row, list
item, or sentence within a larger section) is not annotated.

### 5.2 Format

The annotation is a single line directly under the section's heading (after an
`> **Experimental:**` line, if there is one), followed by a blank line:

```
> **Introduced by:** [gRFC A105: MAX_CONCURRENT_STREAMS Connection Scaling](https://github.com/grpc/proposal/blob/master/A105-max_concurrent_streams-connection-scaling.md)
```

- The link text is `gRFC <number>: <title>`, using the title from the gRFC's
  first line. The URL points to the gRFC file on the `master` branch of
  `github.com/grpc/proposal`.
- If a later gRFC added a substantial, separately usable part of the feature,
  list both, introducing gRFC first, separated by commas:
  `> **Introduced by:** [gRFC A55: xDS-Based Stateful Session Affinity for Proxyless gRPC](https://github.com/grpc/proposal/blob/master/A55-xds-stateful-session-affinity.md), [gRFC A60: xDS-Based Stateful Session Affinity for Weighted Clusters](https://github.com/grpc/proposal/blob/master/A60-xds-stateful-session-affinity-weighted-clusters.md)`. Do not list gRFCs
  that only clarified or adjusted the feature.
- If the whole document specifies one feature (for example, an LB policy
  document), put the annotation under the H1 instead of under a section heading.
- Link only merged gRFCs. Never link pending pull requests.
- Do not put annotations inside tables, lists, or code blocks.

### 5.3 Meaning

The annotation records where a feature came from. It is not part of the
specification, and the spec text remains authoritative: where the gRFC's text
differs from the spec (because later gRFCs or decisions changed the behavior),
the spec wins. Do not describe the differences or the feature's history in the
body text.

## 6. File Layout

```
doc/spec/
  README.md                               Table of contents
  STYLE_GUIDE.md                          This guide
  00-introduction/README.md               0. Introduction and Conventions
  01-architecture/README.md               1. Architecture Overview
  02-rpc-semantics/README.md              2. Core RPC Semantics
  03-wire-protocol/                       3. Wire Protocol
    01-http2.md, 02-http2-transport.md, 03-true-binary-metadata.md,
    04-http3.md, 05-protobuf.md
  04-client-channel/                      4. Client Channel
    01-channel.md, 02-name-resolution.md, 03-service-config.md,
    04-call-dispatch.md, 05-load-balancing.md, 06-subchannels.md,
    07-proxy.md, 08-health-checking.md, 09-backend-metrics.md, 10-retries.md
    lb-policies/                          General-purpose LB policies
      pick_first.md, round_robin.md, weighted_round_robin.md, least_request.md,
      ring_hash.md, random_subsetting.md, outlier_detection.md, priority.md,
      weighted_target.md, rls.md
  05-server/README.md                     5. Server
  06-security/                            6. Security
    01-tls.md, 02-call-credentials.md, 03-authorization.md
  07-services/                            7. Standard Services
    01-health.md, 02-reflection.md, 03-orca.md, 04-admin.md
  08-observability/                       8. Observability
    01-instrumentation.md, 02-metrics-framework.md, 03-metrics.md,
    04-tracing.md, 05-channelz.md, 06-binary-logging.md
  09-xds/                                 9. xDS
    01-bootstrap.md, 02-xds-client.md, 04-client.md, 05-lb-policies.md,
    06-http-filters.md, 07-server.md, 08-security.md, 09-load-reporting.md,
    10-csds.md
    03-resources/                         9.3 xDS resource types
      01-common-types.md, 02-listener.md, 03-route-configuration.md,
      04-cluster.md, 05-endpoint.md
    lb-policies/                          xDS LB policies
      xds_cluster_manager.md, cds.md, xds_cluster_impl.md,
      xds_override_host.md, xds_wrr_locality.md
  appendices/                             Appendices A–G
```

