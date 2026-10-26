# Server Reflection

<!-- Sources: doc/server-reflection.md, doc/server_reflection_tutorial.md (informative), grpc/reflection/v1/reflection.proto, A15 -->

Server reflection lets a client find out at runtime which services a server
exposes and get the protobuf descriptors it needs to build requests and decode
responses, without compiled stubs. Its main use is command-line and debugging
tools. Such a tool takes a method name and a human-readable payload, encodes the
payload in the binary protobuf wire format, sends the RPC, and decodes the
response for display.

The service answers two questions:

1. Which services, and therefore which methods, does the server export?
2. For a given method, is it unary or streaming, and what are its request and
   response types? Answering this means the client must be able to fetch the
   full descriptors of those types, with all their dependencies.

A server need not list every method it can handle. For example, a reverse proxy
can serve reflection for the methods it implements itself without listing the
methods of its backends. Reflection covers protobuf-defined services only.

## 1. Service Definition

The service is `grpc.reflection.v1.ServerReflection`, defined in
`grpc/reflection/v1/reflection.proto`. It has one bidirectional streaming
method, `/grpc.reflection.v1.ServerReflection/ServerReflectionInfo`:

```protobuf
syntax = "proto3";

package grpc.reflection.v1;

service ServerReflection {
  rpc ServerReflectionInfo(stream ServerReflectionRequest)
      returns (stream ServerReflectionResponse);
}

message ServerReflectionRequest {
  string host = 1;
  oneof message_request {
    string file_by_filename = 3;
    string file_containing_symbol = 4;
    ExtensionRequest file_containing_extension = 5;
    string all_extension_numbers_of_type = 6;
    string list_services = 7;
  }
}

message ExtensionRequest {
  string containing_type = 1;   // <package>.<type>
  int32 extension_number = 2;
}

message ServerReflectionResponse {
  string valid_host = 1;
  ServerReflectionRequest original_request = 2;
  oneof message_response {
    FileDescriptorResponse file_descriptor_response = 4;
    ExtensionNumberResponse all_extension_numbers_response = 5;
    ListServiceResponse list_services_response = 6;
    ErrorResponse error_response = 7;
  }
}

message FileDescriptorResponse {
  // Serialized google.protobuf.FileDescriptorProto messages.
  repeated bytes file_descriptor_proto = 1;
}

message ExtensionNumberResponse {
  string base_type_name = 1;    // <package>.<type>
  repeated int32 extension_number = 2;
}

message ListServiceResponse {
  repeated ServiceResponse service = 1;
}

message ServiceResponse {
  string name = 1;              // <package>.<service>
}

message ErrorResponse {
  int32 error_code = 1;         // a gRPC status code value
  string error_message = 2;
}
```

The protocol uses one bidirectional stream so that all related queries go to
the **same server**. Behind a naive reverse proxy, backends can run different
builds. Mixing descriptors from different builds can produce an inconsistent
database (for example, a message that moved from one file to another would
appear twice). Using one stream also lets the server skip descriptors it has
already sent in that stream.

## 2. Stream Semantics

* The client sends any number of `ServerReflectionRequest` messages on one
  stream. For **each** request, the server sends **exactly one**
  `ServerReflectionResponse`. Responses are sent in the order of the requests.
* Each response echoes the request in `original_request`. It sets `valid_host`
  to the host whose data it reports, normally the request's `host`.
* `host` is reserved for selecting a virtual host. A server that does not
  support virtual hosting ignores it and answers from its single descriptor
  database.
* Errors with a single request are returned as an `error_response` in that
  request's response. They **do not** end the stream. The stream ends when the
  client half-closes (the server then ends the call with `OK`), or when the
  call is cancelled.
* Descriptors are sent as serialized `google.protobuf.FileDescriptorProto`
  messages (`bytes`), so the reflection proto does not depend on
  `descriptor.proto`.

## 3. Requests

| `message_request` field | Meaning | Successful response |
| --- | --- | --- |
| `file_by_filename` | A proto file path as it appears in `import` statements and in `FileDescriptorProto.name` (for example, `foo/bar.proto`). | `file_descriptor_response` with the file and its transitive dependencies ([File Descriptor Semantics](#4-file-descriptor-semantics)). |
| `file_containing_symbol` | A fully qualified symbol name with no leading dot: a service (`<package>.<service>`), method (`<package>.<service>.<method>`), message, enum, or extension (`<package>.<type>`), including nested types and their members. | `file_descriptor_response` with the file that defines the symbol and its transitive dependencies. |
| `file_containing_extension` | `containing_type` (fully qualified message name) and `extension_number`. | `file_descriptor_response` with the file that declares the extension of `containing_type` with that field number, and its transitive dependencies. |
| `all_extension_numbers_of_type` | A fully qualified message type name. | `all_extension_numbers_response` with `base_type_name` set to the requested type and `extension_number` listing the field numbers of all known extensions of that type, in no particular order. |
| `list_services` | Any string. The value is ignored. | `list_services_response` with one `ServiceResponse` per service registered on the server. `name` is the fully qualified service name (`<package>.<service>`). The list includes the standard services registered on the server, such as reflection itself and health. |

`all_extension_numbers_of_type` is best effort. The server need not list every
extension. A server that does not support this query at all answers with an
`error_response` whose `error_code` is `UNIMPLEMENTED` (12).

## 4. File Descriptor Semantics

A `file_descriptor_response` answers a file, symbol, or extension query:

* The server MUST include the descriptor of the requested file (the file that
  matches the name, or that contains the symbol or extension). It MUST include
  it even if it already sent it earlier in the stream, and it SHOULD put it
  first.
* The response also carries every **transitive dependency** of that file
  (direct imports, their imports, and so on, public or not), because clients
  almost always need the whole closure to build a usable descriptor pool.
* The server MAY leave out dependencies it has already sent **on the same
  stream** for the same `valid_host`. Clients MUST therefore keep all
  descriptors received on a stream and resolve dependencies against all of
  them. Clients MUST NOT assume that a dependency is missing because it was
  left out of a later response.
* Descriptors a server returns MUST be self-consistent: they come from one
  descriptor database, which is the one the server uses for its own services.

Known `google.protobuf.Any` types can be looked up with `file_containing_symbol`,
using the type name taken from the `Any` type URL.

## 5. Errors

When a request cannot be answered, the response carries `error_response`.
`error_code` is the numeric value of a gRPC status code, and `error_message` is
a human-readable description.

| Condition | `error_code` |
| --- | --- |
| The file, symbol, extension, or type is not known to the server | `NOT_FOUND` (5) |
| `all_extension_numbers_of_type` is not supported | `UNIMPLEMENTED` (12) |
| No `message_request` field is set, or the field is unknown to the server | `UNIMPLEMENTED` (12) |

<!-- REVIEW(divergence) [REFLECTION-1]: Request with no (or an unknown) message_request. Java: error_response with UNIMPLEMENTED, stream continues (ProtoReflectionServiceV1.java handleReflectionRequest default case); Go: ends the stream with INVALID_ARGUMENT status (reflection/internal/internal.go); C++: error_response with UNIMPLEMENTED, stream continues (src/cpp/ext/proto_server_reflection.cc). Sources are silent. Spec says: UNIMPLEMENTED error_response (Java/C++ majority). -->

## 6. Versions

The service is also defined in package `grpc.reflection.v1alpha`
(`grpc/reflection/v1alpha/reflection.proto`, service
`grpc.reflection.v1alpha.ServerReflection`), with messages that are identical
on the wire. That version is deprecated.

* Servers that offer reflection MUST serve `grpc.reflection.v1.ServerReflection`.
  They SHOULD also serve `grpc.reflection.v1alpha.ServerReflection` with the
  same behavior, for older clients.
* Clients SHOULD call `grpc.reflection.v1.ServerReflection` first. If it fails
  with `UNIMPLEMENTED`, they SHOULD fall back to
  `grpc.reflection.v1alpha.ServerReflection`.

## 7. API Requirements

1. gRPC MUST provide a reflection service implementation that applications can
   register on a server. Once registered, it reports every service registered
   on that server and answers descriptor queries from the descriptors of those
   services (for generated services, from the descriptors embedded by the code
   generator). Registering it MUST register both the `v1` and `v1alpha`
   services.
2. The API MUST let applications supply additional descriptors, or a custom
   descriptor source, for servers whose services are not all defined by
   compiled-in protobuf code (for example, proxies or dynamic services).
3. gRPC MUST provide a client-side utility that serves as a descriptor
   database backed by the reflection protocol. It caches descriptors received
   on one stream, prefers `v1`, and falls back to `v1alpha`.
