# WebSocket API

## 1. Scope and versions

This reference describes the routes, adapters and buffers in repository version 0.1.7. Both protocols accept binary audio and return mono int16 PCM. The reference voice is configured on the server, not uploaded per request.

| Protocol document history | Date | Change |
| --- | --- | --- |
| 1.0 | 2025-05-27 | Initial version |
| 1.1 | 2025-06-15 | Simple protocol and opus_frame_duration |
| 1.2 | 2025-11-04 | sample_rate_out |

The 2026-10-29 documentation update aligns the reference with the implementation without changing the protocol. [中文](websocket-api-doc.md) · [Quick start](../getting_started/quick_started_en.md)

## 2. Connection and flow

Connect to `ws://localhost:8042/ws`; the route also accepts `/`. Use the deployment's wss address when TLS is configured.

Standard flow: connect → config → ready → bidirectional audio → end → remaining-buffer processing → complete → close. The simple protocol starts with start, sends no ready message and finishes with completed.

The first message is JSON text. Audio uses binary messages; clients should send and receive concurrently. Audio and converted describe direction, not JSON type values.

## 3. Standard configuration

```json
{
  "type": "config",
  "session_id": "example-001",
  "api_key": "example-key",
  "sample_rate": 16000,
  "sample_rate_out": 22050,
  "bit_depth": 16,
  "channels": 1,
  "encoding": "PCM",
  "opus_frame_duration": 20
}
```

| Field | Contract and default behavior |
| --- | --- |
| type | Must be config |
| session_id | Supply a unique string suitable for filenames; format validation is incomplete |
| api_key | Currently only checked for a nonempty value, not real key authentication |
| sample_rate | Input sample rate; defaults to 16000 Hz |
| sample_rate_out | Output PCM rate; defaults to 16000 Hz; explicitly request 22050 Hz to avoid output resampling in the tiny configuration |
| bit_depth | Signed integer PCM input depth; defaults to 16; decoder accepts 16 / 24 / 32, not float32 |
| channels | Must be 1 |
| encoding | PCM or OPUS; defaults to PCM; other non-OPUS values currently fall into the PCM branch, so send only the documented values |
| opus_frame_duration | Opus duration in milliseconds; defaults to server buffer.opus_frame_duration (20 in prod.yaml) |

Input and output rates may differ. Opus input rates are limited to 8000 / 12000 / 16000 / 24000 / 48000 Hz. Validation is incomplete; invalid fields may close the connection without a structured error.

Successful initialization returns:

```json
{"type": "ready", "session_id": "example-001", "message": "Ready to process audio"}
```

Models and reference conditions load at Worker startup. Ready indicates that this connection's Session and Buffer have been initialized.

## 4. Audio and normal completion

PCM input is mono integer samples without a WAV/RIFF header; little-endian int16 is recommended. Each Opus binary message contains one raw Opus packet, not an Ogg container. Input is accumulated into server inference blocks.

Output is always mono int16 PCM without a file header, at sample_rate_out. OPUS input does not change output encoding.

After sending input, send:

```json
{"type": "end"}
```

The server pads and processes the remaining buffer. Its current completion message is:

```json
{"type": "complete", "stats": {}}
```

Stats is currently empty. Complete does not guarantee that files are already saved, or certify audio quality or every processing step. Do not disconnect instead of sending end; timeout and abnormal disconnection do not guarantee conversion of unprocessed tail audio.

## 5. Simple protocol

```json
{
  "signal": "start",
  "stream_id": "example-002",
  "sample_rate": 16000,
  "sample_rate_out": 22050,
  "sample_bit": 16,
  "encoding": "PCM",
  "opus_frame_duration": 20
}
```

Stream_id maps to session_id and sample_bit to bit_depth. Channels is fixed to 1; the adapter supplies a placeholder api_key. Defaults for sample_rate, sample_rate_out, sample_bit and encoding are 16000, 16000, 16 and PCM. No ready message is sent.

Audio uses the standard protocol's format. End and completion are:

```json
{"signal": "end"}
```

```json
{"signal": "completed"}
```

The existing simple client is used only for the PCM / 16000 Hz output quick start. It omits encoding from the initial message and saves output at a fixed 16000 Hz; its OPUS command-line option is not a correct integration example. Use the standard client invocation in the [quick start](../getting_started/quick_started_en.md) for Opus or explicit output sample rates.

## 6. Errors and disconnection

Explicit initialization errors include INVALID_CONFIG (wrong initial type or channel count) and AUTH_FAILED (failure of the placeholder key check).

Standard error:

```json
{"type": "error", "error_code": "INVALID_CONFIG", "message": "Only mono audio (1 channel) is supported"}
```

Simple error:

```json
{"status": "failed", "stream_id": "example-002", "error_msg": "Only mono audio (1 channel) is supported"}
```

The standard adapter can include details, but current initialization calls do not supply it; its errors omit session_id. Other exceptions may only be logged before closing. Opus decoding errors are replaced with silence and some inference errors are only logged. Handle error text, connection closure and receive timeouts.

App.receive_timeout applies to each receive after initialization (120 seconds in prod.yaml), not to the initial configuration wait. Error exits may still use close code 1000, so that code alone does not prove success.

## 7. Access and data

Key checking is a placeholder. The simple protocol needs no caller-provided key, and the HTTP session endpoint has no authentication. Supply access control at the deployment layer; see [configuration and deployment](../getting_started/配置与部署.md) (Chinese).

Audio and timelines are saved according to server settings. Configure recording flags and directories on the server. The reference voice is fixed per Worker; there is no reference-upload, model-switching or training operation.

## 8. Implementation and maintenance

Sources: [ws.py](../../src/fast_vc_service/routers/ws.py), [adapters](../../src/fast_vc_service/adapters/protocol_adapter.py), [detection](../../src/fast_vc_service/adapters/protocol_detector.py), [buffer.py](../../src/fast_vc_service/buffer.py). Update both language versions, affected examples and the relevant Spec when changing the protocol.
