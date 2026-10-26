> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 8. Observability

<!-- Sources: A3, A14, A16, A45, A66, A72, A78, A79, A88, A89, A94, A96, A105, A108, A118, doc/binary-logging.md -->

This section specifies the facilities through which gRPC exposes information
about its own behavior to applications, operators, and external monitoring
systems.

## Contents

- [8.1 Overview and Common Principles](01-overview.md): the observability facilities and the principles they share
- [8.2 Instrumentation Architecture](02-instrumentation.md): call, attempt, and server tracers
- [8.3 Metrics Framework and OpenTelemetry Plugin](03-metrics-framework.md): instrument registry, scoping, labels, the OpenTelemetry plugin
- [8.4 Metric Catalog](04-metrics.md): every metric gRPC records
- [8.5 Tracing](05-tracing.md): OpenTelemetry tracing and `grpc-trace-bin`
- [8.6 Channelz](06-channelz.md): the channelz data model and service
- [8.7 Binary Logging](07-binary-logging.md): binary log configuration, format, and sinks
