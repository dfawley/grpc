> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 0. Introduction and Conventions

<!-- Sources: doc/PROTOCOL-HTTP2.md, doc/compression.md, doc/statuscodes.md, RFC 2119, RFC 8174, RFC 5234; spec layout defined by the spec owner -->

## 1. Purpose

This document is the consolidated specification of gRPC. It defines the
behavior that every gRPC implementation is expected to exhibit, regardless of
programming language, so that:

- clients and servers built with different implementations interoperate on the
  wire;
- applications see the same RPC semantics (status codes, deadlines, metadata,
  cancellation, retries, and so on) in every implementation;
- control planes and operators (for example, an xDS management server, a DNS
  service config, or an observability backend) can configure and observe any
  implementation in the same way.

The specification describes the **current** behavior of gRPC. It does not
describe how that behavior evolved. Superseded mechanisms are collected in
[Appendix E](../appendices/e-historical.md) for reference only; they are not part
of the specification.

## 2. Scope

The specification covers the following cross-language areas:

| Area | Covered in |
|------|------------|
| RPC model and call semantics: methods, streams, metadata, deadlines, cancellation, status, compression, message limits, interceptors, codecs | [Core RPC Semantics](../02-rpc-semantics/README.md) |
| Wire protocol: gRPC over HTTP/2 and HTTP/3, transport behavior, the true-binary-metadata extension, the Protocol Buffers mapping | [Wire Protocol](../03-wire-protocol/README.md) |
| The client channel: targets, name resolution, service config, per-call configuration, load balancing and the standard LB policies, subchannels, proxies, client-side health checking, retries and hedging | [Client Channel](../04-client-channel/README.md) |
| The server: listeners, connection management, method dispatch, server-side limits | [Server](../05-server/README.md) |
| Security: channel and call credentials, TLS, authorization | [Security](../06-security/README.md) |
| Standard services: health, reflection, backend metrics (ORCA), admin interface | [Standard Services](../07-services/README.md) |
| Observability: instrumentation points, metrics, tracing, channelz, binary logging | [Observability](../08-observability/README.md) |
| xDS (proxyless service mesh): bootstrap, XdsClient, resources, client and server data planes, xDS LB policies, xDS HTTP filters, security, load reporting, CSDS | [xDS](../09-xds/README.md) |

The following are out of scope:

- Language-specific API shapes (class names, method signatures, threading
  models). The specification states API requirements abstractly; see
  [API Requirements](#5-api-requirements).
- Internal implementation structure, except where an internal plugin interface
  (for example, the name resolver, LB policy, or picker interface) must be
  described for components to be interchangeable.
- Features that are not part of the cross-language gRPC feature set.

## 3. Requirements Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this
specification are to be interpreted as described in
[BCP 14](https://www.rfc-editor.org/info/bcp14)
([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119),
[RFC 8174](https://www.rfc-editor.org/rfc/rfc8174)) when, and only when, they
appear in all capitals, as shown here.

In this specification, the "implementation" or "gRPC library" is the gRPC
runtime. The "application" is code that uses gRPC's public API: client code
that sends RPCs and server code (handlers) that serves them. A "plugin" is a
component that implements one of gRPC's extension interfaces (for example, a
name resolver or LB policy) and may be supplied by either the library or the
application.

### 3.1 Applicability of Requirements

Requirements describe how gRPC behaves when the feature or component they
belong to is used. This specification does not classify features as required
or optional.

Some sections define components that are selected by configuration, such as a
specific LB policy, a resolver for a specific URI scheme, a credential type, or
xDS support. Requirements in such a section apply to the behavior of that
component whenever it is used. An implementation MUST NOT register a
component under a name defined by this specification (for example, an LB policy
name, a resolver scheme, or an xDS extension type) unless the component behaves
as specified.

## 4. Experimental Features

Some features in this specification are **experimental**. An experimental
feature is fully specified, but its configuration, API, metric names, or wire
details MAY change incompatibly in a future revision of this specification.
Applications and control planes that depend on experimental features should
expect such changes.

Each experimental feature is marked with a line of the following form, placed
at the beginning of the section or next to the item it applies to:

> **Experimental:** \<what is experimental\>

For example, an LB policy whose registered name ends in `_experimental`, or a
metric marked experimental in the metric catalog, carries this marker. Material
that has no such marker is stable.

## 5. API Requirements

Each section that defines application-visible behavior contains a subsection
titled **API Requirements**. These subsections state what an application MUST
be able to do through gRPC's public API, in abstract form, for example: "The
channel API MUST provide a way to set the default service config." They do not
prescribe names, signatures, types, or whether a capability is exposed as an
option, a builder method, a context value, or something else.

Internal plugin interfaces (name resolver, LB policy, helper, subchannel,
picker, ConfigSelector, call and attempt tracers, and so on) are specified in
the same abstract form. An implementation MAY structure these interfaces
differently, provided that the specified information flows and behaviors are
preserved.

## 6. Normative and Informative Content

All content is **normative** unless it is identified as informative.
The following content is **informative**:

- Sections and subsections whose heading ends with "(Informative)".
- Paragraphs that begin with "Note:", "Example:", or "Rationale:", and blocks
  formatted as notes.
- Examples, including example configurations, example wire traces, and example
  code or pseudo-code that is labeled as an example.
- Diagrams. When a diagram and the text disagree, the text governs.

Pseudo-code that is not labeled as an example is normative. It defines
observable behavior. Implementations MAY use different algorithms that produce
the same observable results.

## 7. Notational Conventions

- **ABNF.** Grammars use Augmented Backus-Naur Form as defined in
  [RFC 5234](https://www.rfc-editor.org/rfc/rfc5234), including its core rules
  (`ALPHA`, `DIGIT`, `VCHAR`, `SP`, `OCTET`, and so on).
- **Status codes** are written by name in `UPPER_SNAKE_CASE` (for example,
  `UNAVAILABLE`). Their numeric values are defined in
  [Core RPC Semantics](../02-rpc-semantics/README.md#101-status-codes).
- **Metadata keys and header names** are written in lowercase code font (for
  example, `grpc-timeout`). All reserved keys are listed in
  [Appendix A](../appendices/a-metadata-keys.md).
- **Configuration.** gRPC consumes configuration (service config, LB policy
  configs, xDS bootstrap) in JSON. Field names are given in the JSON (lower
  camel case) form, for example `maxRequestMessageBytes`. Where a protobuf
  schema defines the structure, the schema is referenced by repository path,
  for example `grpc/service_config/service_config.proto` in the grpc-proto
  repository. The JSON form is the canonical
  [protobuf JSON mapping](https://protobuf.dev/programming-guides/proto3/#json)
  of that schema. In particular, `google.protobuf.Duration` values are JSON
  strings such as `"1.5s"`, and 64-bit integers are JSON strings. An index of
  all schemas is in [Appendix C](../appendices/c-schemas.md).
- **xDS resources** are identified by their Envoy API type names (for example,
  `envoy.config.cluster.v3.Cluster`) and fields by their proto field names.
- **Sizes** use binary prefixes: 1 KiB = 1024 bytes, 1 MiB = 1024 KiB.
- **Durations** in prose use units explicitly (for example, "20 seconds").
- **Environment variables** are written in code font. Only permanent
  configuration variables are part of the specification; they are listed in
  [Appendix B](../appendices/b-environment-variables.md).

## 8. Terminology

Terms with a specific meaning in this specification are defined where they
are introduced and are collected in the [Glossary](../appendices/g-glossary.md).
The most important terms are:

- **Channel**: a client-side virtual connection to a target, capable of
  sending RPCs (see [Core RPC Semantics: Channels and Servers](../02-rpc-semantics/README.md#1-channels-and-servers) and
  [Channel](../04-client-channel/02-channel.md)).
- **Server**: a component that accepts connections and serves RPCs (see
  [Server](../05-server/README.md)).
- **Call** or **RPC**: one invocation of a method (see
  [Core RPC Semantics: Calls](../02-rpc-semantics/README.md#3-calls)).
- **Call attempt**: one transmission of a call to a server. A call has one or
  more attempts when retries or hedging are in use (see
  [Retries and Hedging](../04-client-channel/12-retries.md)).
- **Metadata**: key/value pairs sent with request headers, response headers, or
  trailers (see [Core RPC Semantics: Metadata](../02-rpc-semantics/README.md#7-metadata)).
- **Control plane** and **data plane**: inside a client, the control plane is
  made up of the components that decide where and how RPCs are sent (name
  resolvers, the service config, LB policies, call credentials). The data plane
  is the processing of individual RPCs. In an xDS deployment, "control plane"
  also means the remote xDS management server.

## 9. Document Structure

The specification consists of the following top-level sections:

| Section | Contents |
|---------|----------|
| [Introduction and Conventions](README.md) | This section. |
| [Architecture Overview](../01-architecture/README.md) | The client and server architecture, the main components, and the points where behavior can be plugged in. Mostly informative. |
| [Core RPC Semantics](../02-rpc-semantics/README.md) | The transport-independent RPC model: methods, calls, metadata, deadlines, cancellation, status codes, message limits, compression, wait-for-ready, interceptors, and codecs. |
| [Wire Protocol](../03-wire-protocol/README.md) | [gRPC over HTTP/2](../03-wire-protocol/01-http2.md), [true binary metadata](../03-wire-protocol/02-true-binary-metadata.md), [gRPC over HTTP/3](../03-wire-protocol/03-http3.md), and the [Protocol Buffers mapping](../03-wire-protocol/04-protobuf.md). |
| [Client Channel](../04-client-channel/README.md) | [Channel](../04-client-channel/02-channel.md), [name resolution](../04-client-channel/03-name-resolution.md), [service config](../04-client-channel/04-service-config.md), [per-call configuration](../04-client-channel/05-call-dispatch.md), [load balancing](../04-client-channel/06-load-balancing.md) and the standard LB policies, [subchannels](../04-client-channel/07-subchannels.md), [client transports](../04-client-channel/08-transports/01-transport-model.md) (HTTP/2, HTTP/3, in-process), [HTTP CONNECT proxies](../04-client-channel/09-proxy.md), [client-side health checking](../04-client-channel/10-health-checking.md), [client-side backend metrics](../04-client-channel/11-backend-metrics.md), and [retries and hedging](../04-client-channel/12-retries.md). |
| [Server](../05-server/README.md) | [Server behavior](../05-server/01-server.md) (lifecycle, listeners, method dispatch, connection management) and [server transports](../05-server/02-transports/01-transport-model.md) (HTTP/2, HTTP/3, in-process). |
| [Security](../06-security/README.md) | The security model, [TLS](../06-security/02-tls.md), [call credentials](../06-security/03-call-credentials.md), and [authorization](../06-security/04-authorization.md). |
| [Standard Services](../07-services/README.md) | [Health](../07-services/01-health.md), [reflection](../07-services/02-reflection.md), [ORCA backend metrics](../07-services/03-orca.md), and the [admin interface](../07-services/04-admin.md). |
| [Observability](../08-observability/README.md) | [Instrumentation architecture](../08-observability/02-instrumentation.md), [metrics framework](../08-observability/03-metrics-framework.md), [metric catalog](../08-observability/04-metrics.md), [tracing](../08-observability/05-tracing.md), [channelz](../08-observability/06-channelz.md), and [binary logging](../08-observability/07-binary-logging.md). |
| [xDS](../09-xds/README.md) | [Bootstrap](../09-xds/02-bootstrap.md), [XdsClient](../09-xds/03-xds-client.md), resources ([common types](../09-xds/04-resources/01-common-types.md), [Listener](../09-xds/04-resources/02-listener.md), [RouteConfiguration](../09-xds/04-resources/03-route-configuration.md), [Cluster](../09-xds/04-resources/04-cluster.md), [endpoints](../09-xds/04-resources/05-endpoint.md)), [client data plane](../09-xds/05-client.md), [xDS LB policies](../09-xds/06-lb-policies.md), [xDS HTTP filters](../09-xds/07-http-filters.md), [xDS-enabled servers](../09-xds/08-server.md), [xDS security](../09-xds/09-security.md), [load reporting](../09-xds/10-load-reporting.md), and [CSDS](../09-xds/11-csds.md). |

Appendices:

| Appendix | Contents |
|----------|----------|
| [A. Reserved Metadata Keys](../appendices/a-metadata-keys.md) | Every metadata key with a meaning defined by gRPC. |
| [B. Environment Variables](../appendices/b-environment-variables.md) | Permanent configuration environment variables. |
| [C. Schemas](../appendices/c-schemas.md) | Index of the protobuf and JSON schemas this specification refers to. |
| [D. Traceability](../appendices/d-traceability.md) | Mapping from gRPC design proposals (gRFCs) to the sections of this specification. |
| [E. Historical Behavior](../appendices/e-historical.md) | Superseded mechanisms (informative). |
| [F. Conformance](../appendices/f-conformance.md) | Interoperability and conformance test suites. |
| [G. Glossary](../appendices/g-glossary.md) | Definitions of terms. |

## 10. Relationship to gRFCs (Informative)

gRPC's behavior changes through design proposals called gRFCs. A gRFC describes
a change against the behavior at the time it was written, so the gRFC series
reads as a change log. This specification consolidates the result. When a gRFC
is accepted, the affected sections of this specification are updated to
describe the new current behavior. [Appendix D](../appendices/d-traceability.md)
maps each gRFC to the sections that reflect it.
