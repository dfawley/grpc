> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 7.4 Admin Interface

<!-- Sources: A38 -->

> **Introduced by:** [gRFC A38: Admin Interface API](https://github.com/grpc/proposal/blob/master/A38-admin-interface-api.md)

Some gRPC services expose the state of all gRPC activity in a process, not the
behavior of one application service. These are the **admin services**. The set
can grow over time, and some members only make sense in some setups (for
example, CSDS only when xDS is in use). The admin interface lets an application
add every relevant admin service to a server with one call. gRPC decides which
services that includes, so applications do not have to change when the set
changes.

## 1. Admin Services

| Service | Proto | Included when | Specified in |
| --- | --- | --- | --- |
| Channelz (`grpc.channelz.v1.Channelz`) | `grpc/channelz/v1/channelz.proto` | Always | [Channelz](../08-observability/06-channelz.md) |
| Client Status Discovery Service (`envoy.service.status.v3.ClientStatusDiscoveryService`) | `envoy/service/status/v3/csds.proto` | When gRPC's xDS support is part of the application | [CSDS](../09-xds/11-csds.md) |

The set MAY grow. Services added to it later are added automatically to
servers that use the admin interface.

Inclusion depends on dependencies. CSDS is added only when the application
includes gRPC's xDS support, for example when the xDS package or module is
linked or imported. Using the admin interface MUST NOT, by itself, pull xDS
support into an application.

## 2. Behavior

* The admin interface **adds services to a server that the application
  provides**. The application controls everything else about that server:
  listening addresses, credentials, interceptors, other services, transport
  options, and threading. The admin services can share a server with
  application services, or run on a dedicated server.
* gRPC MUST NOT open listening ports for admin services on its own. In
  particular, gRPC MUST NOT start an admin server because of an environment
  variable, a configuration file, or any other trigger outside the
  application's code. A library must not open additional listening ports
  unless the application explicitly asks it to.
* Admin services expose sensitive information, such as peer addresses, traffic
  statistics, and xDS configuration. Applications SHOULD protect the server or
  listening address that hosts them with appropriate credentials
  ([Security](../06-security/README.md)) and/or authorization
  ([Authorization](../06-security/04-authorization.md)), or limit it to a local or trusted
  network.

## 3. API Requirements

1. gRPC MUST provide a single function (or the equivalent) that adds all
   currently relevant admin services ([Admin Services](#1-admin-services)) to an
   application-provided server, or to the server's builder or configuration
   before start. The function MAY instead return the set of admin service
   implementations, which the application then registers.
2. The function MUST work on any server the application can build, including
   xDS-enabled servers ([xDS-Enabled Servers](../09-xds/08-server.md)).
3. Each admin service MUST also be available individually, so that an
   application can register a chosen subset.
