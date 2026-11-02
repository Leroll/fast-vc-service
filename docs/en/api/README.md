# API Reference

[简体中文](../../api/README.md) · [Quick start](../getting-started/quick-start.md) · [User documentation](../index.md)

Fast-VC provides streaming voice conversion, service status queries and saved session files. This reference covers service version `0.1.7`.

## 1. Endpoints

| Feature | Method and path | Description |
| --- | --- | --- |
| [Voice conversion](voice-conversion.md) | WebSocket `/ws` | Send PCM or Opus audio and receive converted PCM audio |
| [Health check](system.md#1-health-check) | GET `/health` | Check whether the API is reachable |
| [Version](system.md#2-version) | GET `/version` | Get the service version and build date |
| [Session data](session-data.md) | GET `/tools/session/{session_id}` | Retrieve saved recordings and timelines |

WebSocket `/` is an alias for `/ws`. Voice conversion supports standard and simple protocols. New clients should use the standard protocol, which provides a `ready` acknowledgment; see the [message flow](voice-conversion.md#1-example).

## 2. Base URLs

Local examples use these addresses. Replace the host and port for your deployment:

| Interface | URL |
| --- | --- |
| HTTP | `http://localhost:8042` |
| WebSocket | `ws://localhost:8042/ws` |

Use `https://` and `wss://` when TLS is configured. After starting the service, visit `/docs` for interactive HTTP documentation or `/openapi.json` for the HTTP schema. See [voice conversion](voice-conversion.md) for WebSocket message formats.

## 3. Authentication

The service does not implement full authentication. The standard protocol only checks that `api_key` is nonempty, the simple protocol requires no client-supplied key, and HTTP endpoints do not check keys. Configure authentication and access control through a gateway or reverse proxy; the session-data endpoint can return saved recordings.

## 4. Related documentation

- [Quick start](../getting-started/quick-start.md): installation, startup and a first conversion.
- [Configuration and deployment](../getting-started/configuration.md): models, reference voices, recording settings and server options. The reference voice is configured at startup; there is no per-request reference-upload or model-switching endpoint.
- [Design](../../design/README.md) (Chinese): internal buffering, conversion and session management.
