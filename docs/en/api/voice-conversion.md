# Voice Conversion API

[API reference](README.md) · [简体中文](../../zh/api/voice-conversion.md)

`WebSocket /ws`

Send source audio continuously and receive converted audio in real time. Input supports mono PCM or Opus; output is mono 16-bit PCM. The target voice is configured on the server.

## 1. Example

Connect to `ws://localhost:8042/ws`. `/` is an alias for the same endpoint; use `wss://` when TLS is enabled. Each connection handles one audio stream.

This example uses the standard protocol with 16 kHz, 16-bit mono PCM input and 16 kHz PCM output. Send control messages as JSON text and audio as WebSocket binary messages.

**Send the initialization message**

```json
{
  "type": "config",
  "session_id": "example-001",
  "api_key": "example-key"
}
```

**Wait for the ready response**

```json
{
  "type": "ready",
  "session_id": "example-001",
  "message": "Ready to process audio"
}
```

After `ready`, send audio and receive converted audio concurrently. One input packet may produce zero or more output chunks; do not wait for a reply to each packet.

**Send the end message**

```json
{"type": "end"}
```

Stop sending audio and keep receiving the remaining output until:

```json
{"type": "complete", "stats": {}}
```

The server processes the remaining input, sends `complete`, then closes the connection. `stats` is currently an empty object. Open a new connection for the next audio stream.

> End input with `end`. Disconnecting skips normal tail processing; treat a stream without `complete` as incomplete. Completion does not mean that [session files](session-data.md#4-save-timing) have been saved.

## 2. Initialization parameters

Use the standard protocol for new integrations, with `type: config` in the first message. Parameters apply for the entire connection and cannot be changed by sending another configuration.

| Field | Type | Requirement | Default | Description |
| --- | --- | --- | --- | --- |
| `type` | string | Required | — | Always `config` |
| `session_id` | string | Recommended | None | Unique, filename-safe session identifier; the server does not generate it or validate uniqueness |
| `api_key` | string | Required | — | Nonempty string; currently a placeholder check, see [authentication](README.md#3-authentication) |
| `sample_rate` | integer | Optional | `16000` | Input sample rate in Hz; must match the actual audio |
| `sample_rate_out` | integer | Optional | `16000` | Output PCM sample rate in Hz; use `22050` with the tiny model to avoid additional output resampling |
| `bit_depth` | integer | Optional | `16` | PCM input depth: `16`, `24` or `32`, all signed integers |
| `channels` | integer | Optional | `1` | Only `1` (mono) is supported |
| `encoding` | string | Optional | `PCM` | `PCM` or `OPUS`, case-insensitive |
| `opus_frame_duration` | number | Recommended for Opus | Server configuration | Opus packet duration in milliseconds; `20` with prod.yaml; ignored for PCM input |

Defaults apply when fields are omitted. Use the listed types, not numeric strings or `null`. The exception is `opus_frame_duration`: omission or `null` uses the server setting, with a 20 ms fallback if it is not configured.

Parameter validation is incomplete. Empty, malformed or duplicate session identifiers are not consistently rejected; use valid positive integer sample rates, as arbitrary rates are not guaranteed to work. Encoding strings other than `OPUS` currently use PCM. Invalid parameters may close the connection directly; see [error handling](#5-errors-and-timeouts).

## 3. Audio formats

### 3.1 Input and output

| Direction | Binary message contents |
| --- | --- |
| PCM input | Mono signed integer samples matching `bit_depth`; commonly little-endian int16, without a WAV / RIFF header |
| Opus input | One raw Opus packet per message, without an Ogg container |
| Output | Mono int16 PCM at `sample_rate_out`, without a file header |

PCM messages must contain complete samples. 32-bit PCM means integers, not float32. Do not wrap audio in JSON or Base64. Changing `sample_rate` does not resample the client's source file.

### 3.2 Opus example

This configuration uses 16 kHz Opus input, 20 ms packets and 22050 Hz PCM output:

```json
{
  "type": "config",
  "session_id": "example-opus-001",
  "api_key": "example-key",
  "sample_rate": 16000,
  "sample_rate_out": 22050,
  "encoding": "OPUS",
  "opus_frame_duration": 20
}
```

Supported Opus input rates are `8000`, `12000`, `16000`, `24000` and `48000` Hz, decoded at 16-bit depth. Start with 20 ms packets and match the declared duration to the packets. Frame duration is not fully validated; arbitrary values are not guaranteed to decode.

### 3.3 Chunking and playback

The server accumulates audio before conversion; prod.yaml uses 0.5-second inference blocks. Network packets need not match this size. Keep receiving and play or save output at `sample_rate_out`; output duration in seconds is `byte_count / 2 / sample_rate_out`.

Output messages contain no timestamps or sequence numbers. Prefill, tail silence padding and streaming stitching may change total duration, so do not assume equal input and output lengths per packet.

## 4. Simple protocol

The simple protocol supports clients using a `start` / `end` message convention. It uses the same paths and audio formats as the standard protocol. The first message selects the protocol; do not mix them.

### 4.1 Initialization

```json
{
  "signal": "start",
  "stream_id": "example-002",
  "sample_rate": 16000,
  "sample_rate_out": 22050,
  "sample_bit": 16,
  "encoding": "PCM"
}
```

The simple protocol **does not return `ready`**. After sending `start`, send audio in order while receiving output concurrently.

| Field | Type | Requirement | Default | Description |
| --- | --- | --- | --- | --- |
| `signal` | string | Required | — | Always `start` |
| `stream_id` | string | Recommended | Empty string | Corresponds to the standard protocol's `session_id` |
| `sample_rate` | integer | Optional | `16000` | Input sample rate in Hz |
| `sample_rate_out` | integer | Optional | `16000` | Output PCM sample rate in Hz |
| `sample_bit` | integer | Optional | `16` | Corresponds to the standard protocol's `bit_depth` |
| `encoding` | string | Optional | `PCM` | `PCM` or `OPUS` |
| `opus_frame_duration` | number | Recommended for Opus | Server configuration | Opus packet duration in milliseconds |

Constraints follow the [standard protocol](#2-initialization-parameters). Channels are fixed to 1 and `api_key` is supplied internally; client-supplied `channels` and `api_key` have no effect. Use `stream_id` and `sample_bit` for the identifier and bit depth.

### 4.2 Completion

Send:

```json
{"signal": "end"}
```

After the remaining audio, the server sends this message and closes the connection:

```json
{"signal": "completed"}
```

As with the standard protocol, completion does not mean files are saved or every audio chunk was processed successfully.

## 5. Errors and timeouts

### 5.1 Initialization errors

Failed standard-protocol initialization may return an error message before closing the connection. For example, when `channels` is 2:

```json
{
  "type": "error",
  "error_code": "INVALID_CONFIG",
  "message": "Only mono audio (1 channel) is supported"
}
```

| `error_code` | Condition | `message` |
| --- | --- | --- |
| `INVALID_CONFIG` | The standard protocol's first message has a `type` other than `config` | `Expected config message type` |
| `AUTH_FAILED` | `api_key` is missing, null or an empty string | `Invalid API key or authentication failed` |
| `INVALID_CONFIG` | `channels` is not 1 | `Only mono audio (1 channel) is supported` |

`type` is always `error`; `error_code` and `message` are strings. The response does not echo the session ID. Correct the initialization parameters as described above, then reconnect.

The simple error format uses `status: failed`, `stream_id` and `error_msg`, without `error_code`. A valid `start` automatically supplies the standard configuration type, placeholder key and mono channels; adding `channels: 2` does not trigger the error above. Not all exceptions return structured errors.

### 5.2 Timeouts and disconnects

With prod.yaml, each wait for the next client message after initialization is limited to 120 seconds by `app.receive_timeout`; the configuration class default is 480 seconds. This does not limit the initial configuration wait, a single inference call or the total stream duration.

Tail audio is not guaranteed to be processed after a timeout or abnormal disconnect. Clients must handle audio, control messages and disconnect events. The server may use close code `1000` even after an error; use `complete` / `completed` to identify normal completion.

### 5.3 Other processing behavior

- Non-end JSON objects after initialization are ignored, including repeated configuration. Invalid JSON or non-object control messages may close the connection.
- Empty binary messages are ignored. Incomplete PCM samples or invalid audio parameters may cause processing failures.
- Opus decoding errors are logged and replaced with silence of the corresponding frame duration. Some chunk-processing failures are only logged, and a completion message may still follow. Completion therefore does not guarantee every audio chunk was processed successfully.

## 6. Client examples

Use the [standard client](../../../examples/websocket/ws_client.py); see the [quick start](../getting-started/quick-start.md#4-standard-protocol-and-concurrent-requests) for the full invocation. Its `samplerate_out` field maps to the protocol's `sample_rate_out`.

The [simple client](../../../examples/websocket/simple_protocol_ws_client.py) currently omits `encoding` and saves output at a fixed 16000 Hz. Use it only for PCM-input, 16 kHz-output examples. Use the standard client for Opus or other output sample rates.
