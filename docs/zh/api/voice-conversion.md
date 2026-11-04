# 语音转换 API

[API 参考](README.md) · [English](../../en/api/voice-conversion.md)

`WebSocket /ws`

持续发送源音频，实时接收转换后的音频。输入支持单声道 PCM 或 Opus，输出为单声道 16-bit PCM。目标音色由服务端配置。

## 1. 调用示例

连接 `ws://localhost:8042/ws`。`/` 是相同接口的别名；启用 TLS 时使用 `wss://`。每个连接处理一条音频流。

以下使用标准协议，将 16 kHz、16-bit、单声道 PCM 转换为 16 kHz PCM。控制消息使用 JSON 文本，音频使用 WebSocket 二进制消息。

**发送初始化消息**

```json
{
  "type": "config",
  "session_id": "example-001",
  "api_key": "example-key"
}
```

**等待服务就绪**

```json
{
  "type": "ready",
  "session_id": "example-001",
  "message": "Ready to process audio"
}
```

收到 `ready` 后，并行发送音频、接收转换结果。一个输入包可能产生零个或多个输出块，不要逐包等待回复。

**发送结束消息**

```json
{"type": "end"}
```

停止发送音频，继续接收剩余输出，直到收到：

```json
{"type": "complete", "stats": {}}
```

服务处理剩余输入后发送 `complete` 并关闭连接。`stats` 当前为空对象。开始下一条音频流需要新建连接。

> 应通过 `end` 结束输入。主动断开会跳过正常尾部处理；未收到 `complete` 的流应视为未正常完成。完成消息不代表[会话文件](session-data.md#4-保存时序)已经保存。

## 2. 初始化参数

新接入使用标准协议，首条消息的 `type` 为 `config`。参数在整个连接内生效，不能通过再次发送配置修改。

| 字段 | 类型 | 要求 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `type` | string | 必填 | — | 固定为 `config` |
| `session_id` | string | 建议提供 | 无 | 唯一、适合文件名的会话标识；服务不自动生成或校验唯一性 |
| `api_key` | string | 必填 | — | 非空字符串；当前仅作占位检查，见[认证](README.md#3-认证) |
| `sample_rate` | integer | 可选 | `16000` | 输入采样率，Hz；须与实际音频一致 |
| `sample_rate_out` | integer | 可选 | `16000` | 输出 PCM 采样率，Hz；tiny 模型可使用 `22050` 避免额外输出重采样 |
| `bit_depth` | integer | 可选 | `16` | PCM 输入位深：`16`、`24` 或 `32`；均为有符号整数 |
| `channels` | integer | 可选 | `1` | 仅支持 `1`，即单声道 |
| `encoding` | string | 可选 | `PCM` | `PCM` 或 `OPUS`，不区分大小写 |
| `opus_frame_duration` | number | Opus 时建议提供 | 服务配置 | Opus 包帧长，毫秒；使用 prod.yaml 时为 `20`，PCM 输入忽略此字段 |

默认值在省略字段时生效，请按表中类型传值，不要用数字字符串或 `null` 代替。`opus_frame_duration` 是例外：省略或为 `null` 时读取服务配置，未配置时回退为 20 ms。

服务尚未完整校验参数：会话 ID 的空值、格式与重复不会统一拒绝；采样率应使用有效正整数，任意采样率不保证可用；非 `OPUS` 的编码字符串当前按 PCM 处理。无效参数可能直接导致连接关闭，详见[错误处理](#5-错误与超时)。

## 3. 音频格式

### 3.1 输入与输出

| 方向 | 二进制消息内容 |
| --- | --- |
| PCM 输入 | 单声道有符号整数样本，位深与 `bit_depth` 一致；常用小端 int16，无 WAV / RIFF 头 |
| Opus 输入 | 每条消息一个原始 Opus 包，无 Ogg 容器 |
| 输出 | 单声道 int16 PCM，采样率为 `sample_rate_out`，无文件头 |

PCM 消息需包含完整样本；32-bit PCM 是整数格式，不是 float32。音频不能包装为 JSON 或 Base64。修改 `sample_rate` 字段不会对客户端的源文件重采样。

### 3.2 Opus 示例

以下配置使用 16 kHz Opus 输入、20 ms 帧长和 22050 Hz PCM 输出：

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

Opus 输入采样率支持 `8000`、`12000`、`16000`、`24000`、`48000` Hz，解码位深固定为 16 位。建议使用 20 ms 帧长，声明值必须与音频包匹配；服务未完整校验帧长，不保证任意值可解码。

### 3.3 分块与播放

服务累计音频后执行转换，prod.yaml 的推理块长为 0.5 秒。网络包无需与推理块等长。客户端持续接收，并按 `sample_rate_out` 播放或封装文件；输出时长为 `字节数 / 2 / sample_rate_out` 秒。

输出消息不含时间戳或序号。预填充、尾块补静音和流式拼接可能改变总时长，因此不能假定输入输出逐包等长。

## 4. 简单协议

简单协议适用于已有 `start` / `end` 消息格式的客户端，与标准协议使用相同路径及音频格式。两种协议由首条消息选择，不能混用。

### 4.1 初始化

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

简单协议**不返回 `ready`**。发送 `start` 后按顺序发送音频，同时接收输出。

| 字段 | 类型 | 要求 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `signal` | string | 必填 | — | 固定为 `start` |
| `stream_id` | string | 建议提供 | 空字符串 | 对应标准协议的 `session_id` |
| `sample_rate` | integer | 可选 | `16000` | 输入采样率，Hz |
| `sample_rate_out` | integer | 可选 | `16000` | 输出 PCM 采样率，Hz |
| `sample_bit` | integer | 可选 | `16` | 对应标准协议的 `bit_depth` |
| `encoding` | string | 可选 | `PCM` | `PCM` 或 `OPUS` |
| `opus_frame_duration` | number | Opus 时建议提供 | 服务配置 | Opus 包帧长，毫秒 |

参数约束与[标准协议](#2-初始化参数)相同。声道固定为 1，`api_key` 由服务内部填充；客户端传入的 `channels` 和 `api_key` 不生效。会话标识和位深应分别使用 `stream_id`、`sample_bit`。

### 4.2 结束

发送：

```json
{"signal": "end"}
```

接收剩余音频后，服务发送以下消息并关闭连接：

```json
{"signal": "completed"}
```

与标准协议相同，完成消息不代表文件已保存或每个音频块都处理成功。

## 5. 错误与超时

### 5.1 初始化错误

标准协议初始化失败时可能返回以下消息，然后关闭连接。例如 `channels` 为 2：

```json
{
  "type": "error",
  "error_code": "INVALID_CONFIG",
  "message": "Only mono audio (1 channel) is supported"
}
```

| `error_code` | 触发条件 | `message` |
| --- | --- | --- |
| `INVALID_CONFIG` | 标准协议首条消息的 `type` 不为 `config` | `Expected config message type` |
| `AUTH_FAILED` | `api_key` 缺失、为 null 或空字符串 | `Invalid API key or authentication failed` |
| `INVALID_CONFIG` | `channels` 不为 1 | `Only mono audio (1 channel) is supported` |

`type` 固定为 `error`，`error_code` 和 `message` 为字符串；响应不回显会话 ID。按表中原因修正初始化参数后重新连接。

简单协议的错误格式使用 `status: failed`、`stream_id` 和 `error_msg`，没有 `error_code`。有效 `start` 消息自动提供标准配置类型、占位密钥和单声道；向其中添加 `channels: 2` 不会触发上述错误。并非所有异常都会返回结构化错误。

### 5.2 超时与断开

使用 prod.yaml 时，初始化后每次等待下一条客户端消息的时限为 120 秒，由 `app.receive_timeout` 配置；配置类默认值为 480 秒。此值不限制首条初始化消息等待、单次推理耗时或整条流的总时长。

超时或异常断开后，尾部音频不保证处理。客户端需同时处理音频、控制消息和断开事件；服务在异常退出时也可能使用关闭码 `1000`，应以 `complete` / `completed` 判断正常结束。

### 5.3 其他处理行为

- 初始化后的非结束 JSON 对象被忽略，包括再次发送配置；无效 JSON 或非对象控制消息可能使连接关闭。
- 空二进制消息被忽略；不完整 PCM 样本或错误音频参数可能导致处理失败。
- Opus 解码失败会记录日志并补入相应帧长的静音；部分音频块处理失败仅记录日志，之后仍可能收到完成消息。因此完成消息不保证所有音频块都成功处理。

## 6. 客户端示例

使用[标准客户端](../../../examples/websocket/ws_client.py)接入，完整运行命令见[快速开始](../getting-started/quick-start.md#4-标准协议与并发调用)。客户端的 `samplerate_out` 对应协议字段 `sample_rate_out`。

[简单客户端](../../../examples/websocket/simple_protocol_ws_client.py)当前未传递 `encoding`，并按固定 16000 Hz 保存输出，仅建议用于 PCM 输入、16 kHz 输出示例。需要 Opus 或其他输出采样率时使用标准客户端。
