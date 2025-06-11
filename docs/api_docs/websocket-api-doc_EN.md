# Streaming Voice Conversion Service - WebSocket API Specification

## Document Overview

This document is the WebSocket interface specification for the streaming Voice Conversion service, intended for developers who need to integrate this service. The document provides detailed descriptions of connection establishment, message formats, interaction flows, and error handling.

## 1. Service Overview

This service provides real-time voice conversion functionality, allowing clients to send audio streams via WebSocket and receive converted audio streams, enabling voice conversion from source speaker to target speaker.

### 1.1 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-05-27 | Initial version |
| 1.1 | 2025-06-15 | Added simple protocol support, added opus_frame_duration field |

## 2. Interaction Flow

### 2.1 Basic Workflow

```
Client                                Server
  |                                   |
  |  --- Config Request ----------->   |
  |  <-- Ready Confirmation --------  |  Initialize model
  |                                   |
  |  --- Audio Chunk 1 ------------>  |  Process audio
  |  <-- Converted Audio 1 ---------   |
  |                                   |
  |  --- Audio Chunk 2 ------------>  |  Process audio
  |  <-- Converted Audio 2 ---------   |
  |                                   |
  |  --- Audio Chunk N ------------>  |  Process audio
  |  <-- Converted Audio N ---------   |
  |                                   |
  |  --- End Signal --------------->  |  Complete processing
  |  <-- Complete Status -----------   |
  |                                   |
  |  --- Close Connection --------->  |
  |                                   |
```

### 2.2 Error Handling Flow

When an error occurs, the server will send an error message and close the connection.

```
Client                                Server
  |                                   |
  |  --- Audio Chunk -------------->  |
  |  <-- Error Message -------------   |  Processing error
  |  <-- Close Connection ----------   |  Actively close WebSocket
  |                                   |  
```

## 3. Connection Establishment

### 3.1 WebSocket URL

```
ws://[server_address]/ws
```

### 3.2 Connection Parameters

No parameters are required in the URL when establishing the connection. All configuration information will be sent through the configuration request message.

## 4. Message Format

The service uses two types of message formats:
1. **Control Messages**: JSON format, used to transmit configuration, status, and error information
2. **Audio Data**: Binary format, used to transmit raw audio data and converted audio data

### 4.1 Message Types

| Message Type | Direction | Format | Description |
|-------------|-----------|--------|-------------|
| config | Client -> Server | JSON | Configuration request |
| ready | Server -> Client | JSON | Ready confirmation |
| audio | Client -> Server | Binary | Input audio data chunk |
| converted | Server -> Client | Binary | Converted audio data chunk |
| end | Client -> Server | JSON | End signal |
| complete | Server -> Client | JSON | Complete status |
| error | Server -> Client | JSON | Error information |

## 5. Detailed API Description

### 5.1 Configuration Request (config)

After establishing the WebSocket connection, the client first sends a configuration message:

```json
{
  "type": "config",
  "session_id": "sess_12345abcde",
  "api_key": "your_api_key_here",
  "sample_rate": 16000,
  "bit_depth": 16,
  "channels": 1,
  "encoding": "PCM",
  "opus_frame_duration": 20
}
```

Parameter description:
- `type`: Fixed as "config"
- `session_id`: Session ID for identifying the current connection
- `api_key`: API key for authentication
- `sample_rate`: Sample rate (Hz)
- `bit_depth`: Bit depth
- `channels`: Number of channels, fixed as 1 (mono)
- `encoding`: Encoding format (PCM/WAV)
- `opus_frame_duration`: (Optional) OPUS encoding frame duration in milliseconds, default is 20ms

### 5.2 Ready Confirmation (ready)

After server initialization is complete, it sends a ready confirmation:

```json
{
  "type": "ready",
  "session_id": "sess_12345abcde",
  "message": "Ready to process audio"
}
```

### 5.3 Audio Data (audio)

Audio data sent by the client is in binary format, sent directly as WebSocket binary messages, not wrapped in JSON. Each audio chunk should conform to the format and size specified in the configuration.

### 5.4 Converted Audio (converted)

Converted audio data returned by the server is also in binary format, returned directly as WebSocket binary messages, not wrapped in JSON.

### 5.5 End Signal (end)

When the client completes sending all audio, it sends an end signal:

```json
{
  "type": "end"
}
```

### 5.6 Complete Status (complete)

After the server completes all processing, it sends a complete status:

```json
{
  "type": "complete",
  "stats": {
    "total_processed_ms": 5000,
    "chunks_processed": 25,
    "average_latency_ms": 120
  }
}
```

## 6. Error Handling

### 6.1 Error Message Format

When the server detects an error, it will send an error message and then immediately close the connection:

```json
{
  "type": "error",
  "error_code": "ERR_CODE",
  "message": "Error description",
  "details": {
    "additional_info": "Additional error information"
  }
}
```

Parameter description:
- `type`: Fixed as "error"
- `error_code`: Error code
- `message`: Human-readable error description
- `details`: (Optional) detailed error information

### 6.2 Common Error Codes

| Error Code | Description | Handling Suggestion |
|-----------|-------------|-------------------|
| INVALID_CONFIG | Invalid configuration parameters | Check audio format configuration |
| AUTH_FAILED | Authentication failed | Check API key |
| INVALID_AUDIO | Invalid audio data format | Ensure audio data meets configuration requirements |
| INTERNAL_ERROR | Server internal error | Retry later or contact support team |
| TIMEOUT | Processing timeout | Try reducing audio chunk size or retry later |

## 7. Protocol Adaptation

### 7.1 Overview

To support different client systems, the service provides automatic protocol detection and adaptation functionality. The server will automatically identify the protocol type based on the first message and perform corresponding format conversion.

### 7.2 Simple Protocol

#### 7.2.1 Initialization Message

Initialization message format sent by simple protocol clients:

```json
{
  "signal": "start",
  "stream_id": "stream_12345",
  "sample_rate": 16000,
  "sample_bit": 16,
  "opus_frame_duration": 20
}
```

Parameter description:
- `signal`: Fixed as "start"
- `stream_id`: Stream ID for identifying the current connection
- `sample_rate`: Sample rate (Hz)
- `sample_bit`: Bit depth
- `opus_frame_duration`: (Optional) OPUS encoding frame duration in milliseconds, default is 20ms

**Note**: Simple protocol does not require API key authentication, and the server will not send a ready confirmation message.

#### 7.2.2 Audio Data

Audio data transmission format is the same as the standard protocol, using WebSocket binary messages.

#### 7.2.3 End Signal

End signal format for simple protocol:

```json
{
  "signal": "end"
}
```

#### 7.2.4 Complete Status

Complete status returned by the server to simple protocol clients:

```json
{
  "signal": "completed"
}
```

#### 7.2.5 Error Message

Error message format returned by the server to simple protocol clients:

```json
{
  "status": "failed",
  "stream_id": "stream_12345",
  "error_msg": "Error description"
}
```

### 7.3 Automatic Protocol Detection

The server automatically detects the protocol type based on the first message:

| Detection Condition | Protocol Type | Description |
|-------------------|---------------|-------------|
| `"signal": "start"` | Simple Protocol | Automatically converts to standard format for processing |
| `"type": "config"` | Standard Protocol | Processes according to standard flow |
| Other | Standard Protocol | Uses standard protocol by default |

### 7.4 Simple Protocol Interaction Flow

```
Simple Protocol Client                Server
  |                                   |
  |  --- Start Signal ------------->  |  Auto-detect protocol
  |                                   |  Initialize model (no ready message)
  |                                   |
  |  --- Audio Chunk 1 ------------>  |  Process audio
  |  <-- Converted Audio 1 ---------   |
  |                                   |
  |  --- Audio Chunk N ------------>  |  Process audio
  |  <-- Converted Audio N ---------   |
  |                                   |
  |  --- End Signal --------------->  |  Complete processing
  |  <-- Complete Signal -----------   |
  |                                   |
  |  --- Close Connection --------->  |
  |                                   |
```

### 7.5 Protocol Comparison

| Feature | Standard Protocol | Simple Protocol |
|---------|------------------|-----------------|
| Initialization Message | `type: "config"` | `signal: "start"` |
| API Key Authentication | Required | Not required |
| Ready Confirmation | Sent | Not sent |
| End Signal | `type: "end"` | `signal: "end"` |
| Complete Message | `type: "complete"` | `signal: "completed"` |
| Error Format | Standard error format | Simplified error format |