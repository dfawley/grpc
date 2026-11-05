> [!WARNING]
> This document is part of a new, experimental
> [gRPC specification](../README.md). It was generated primarily by AI and has not
> yet been fully reviewed.

# 6. Security

<!-- Sources: doc/server_side_auth.md, doc/ssl-performance.md (informative), doc/security_audit.md (skimmed), L62, A29 (programming API), A54, A81, A83, A87, A120, grpc-proto grpc/gcp/handshaker.proto -->

This section defines gRPC's security model: how connections are secured
(channel and server credentials), how per-RPC credentials are attached (call
credentials), how the strength of a connection is described (security levels),
and how authentication results are exposed to the server application
(AuthContext). It also specifies the TLS and ALTS transport security
mechanisms.

xDS-managed security (xDS channel and server credentials, certificate provider
instances in the bootstrap, SAN matching configured by the control plane) is
specified in [xDS Security](../09-xds/09-security.md).

## Contents

- [6.1 Security Model](01-security-model.md): channel, server, call, and composite credentials; security levels; AuthContext; authority override
- [6.2 TLS](02-tls.md): versions, ALPN, SNI, hostname and per-RPC authority verification, mTLS, certificate providers, custom verification, CRLs, SPIFFE, private key offloading, key exchange groups
- [6.3 Call Credentials](03-call-credentials.md): call credential behavior; access token, token-fetching, and JWT token file credentials
- [6.4 Authorization](04-authorization.md): RBAC engine, gRPC authorization policy, audit logging
- [6.5 ALTS](05-alts.md): ALTS channel and server credentials: handshaker service, RPC protocol versions, peer identity, record protocol

## Related Sections

- [Vendor-Specific Features](../10-vendor-specific/README.md): Google default credentials, Google call credentials, and GCP service account identity credentials
