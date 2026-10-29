# WebSocket API

## 1. 范围与版本

本文按仓库版本 0.1.7 的路由、适配器和缓冲实现整理。标准协议与简单协议均接收二进制音频，返回单声道 int16 PCM。参考音色由服务配置指定，不通过每次请求上传。

| 协议文档历史 | 日期 | 变更 |
| --- | --- | --- |
| 1.0 | 2025-05-27 | 初始版本 |
| 1.1 | 2025-06-15 | 简单协议与 opus_frame_duration |
| 1.2 | 2025-11-04 | sample_rate_out |

2026-10-29 校正文档与源码的一致性，没有修改协议实现。[English](websocket-api-doc_EN.md) · [快速开始](../getting_started/quick_started_zh.md)

## 2. 连接与流程

连接 `ws://localhost:8042/ws`；路由也接受 `/`。配置 TLS 的部署使用相应 wss 地址。

标准流程：连接 → config → ready → 双向音频流 → end → 处理剩余缓冲 → complete → 关闭。简单协议以 start 开始，没有 ready，结束回复为 completed。

首条消息为 JSON 文本，音频使用二进制消息；客户端应并发发送和接收。audio / converted 只是方向描述，不是 JSON type 字段。

## 3. 标准协议配置

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

| 字段 | 约定与默认行为 |
| --- | --- |
| type | 必须为 config |
| session_id | 客户端提供唯一、适合文件名的字符串；当前未完整验证格式 |
| api_key | 当前只检查非空，并非真实密钥认证；示例值用于演示 |
| sample_rate | 输入采样率，缺省 16000 Hz |
| sample_rate_out | 返回 PCM 的采样率，缺省 16000 Hz；tiny 配置可显式请求 22050 Hz，减少输出重采样 |
| bit_depth | PCM 输入有符号整数位深，缺省 16；解码支持 16 / 24 / 32，不是 float32 |
| channels | 必须为 1 |
| encoding | PCM 或 OPUS，缺省 PCM；当前非 OPUS 值落入 PCM 分支，客户端只应发送上述值 |
| opus_frame_duration | Opus 帧长，毫秒；未指定时读取 buffer.opus_frame_duration（prod.yaml 为 20） |

输入与输出采样率可不同。Opus 输入采样率限 8000 / 12000 / 16000 / 24000 / 48000 Hz。字段校验不完整，无效值可能导致连接关闭，而非稳定的结构化错误。

初始化成功返回：

```json
{"type": "ready", "session_id": "example-001", "message": "Ready to process audio"}
```

模型和参考条件在 Worker 启动时加载；ready 表示本次连接的 Session / Buffer 初始化完成。

## 4. 音频与正常结束

PCM 输入是单声道整数样本字节，不附 WAV/RIFF 头；建议使用小端 int16。Opus 输入每条二进制消息携带一个原始 Opus 包，不发送 Ogg 容器。服务按自己的推理块长累计输入。

返回始终为单声道 int16 PCM，无文件头，采样率由 sample_rate_out 确定。输入 OPUS 不改变输出格式。

输入完成发送：

```json
{"type": "end"}
```

服务补齐并处理剩余缓冲，当前完成消息为：

```json
{"type": "complete", "stats": {}}
```

stats 当前为空。complete 不保证会话文件已经落盘，也不代表音质或每个内部步骤都通过验收。不要用主动断开替代 end；超时或异常断开不保证转换未处理的尾块。

## 5. 简单协议

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

stream_id 对应 session_id，sample_bit 对应 bit_depth；声道固定为 1，适配器内部设置占位 api_key。sample_rate、sample_rate_out、sample_bit、encoding 的缺省值分别为 16000、16000、16、PCM。没有 ready 回复。

音频与标准协议相同；结束及回复如下：

```json
{"signal": "end"}
```

```json
{"signal": "completed"}
```

现有简单客户端只作为 PCM / 16000 Hz 输出的上手入口。它未把 encoding 写入首条消息，输出保存固定为 16000 Hz；其 OPUS 命令行选项不能直接作为正确接入示例。需要 Opus 或显式输出采样率时，使用[快速开始](../getting_started/quick_started_zh.md)中的标准客户端调用方式。

## 6. 错误与断开

明确返回的初始化错误包括 INVALID_CONFIG（首条类型或声道不合要求）和 AUTH_FAILED（标准配置未通过占位密钥检查）。

标准错误：

```json
{"type": "error", "error_code": "INVALID_CONFIG", "message": "Only mono audio (1 channel) is supported"}
```

简单协议错误：

```json
{"status": "failed", "stream_id": "example-002", "error_msg": "Only mono audio (1 channel) is supported"}
```

标准适配器可格式化 details，但当前初始化调用未提供；它的错误不携带 session_id。其他异常可能只记日志后关闭连接。Opus 解码失败会记日志并补静音，部分推理异常也只记日志。客户端应同时处理错误文本、连接关闭和接收超时。

app.receive_timeout 控制初始化后每次收包等待（prod.yaml 为 120 秒），不覆盖初始配置等待。异常退出也可能用关闭码 1000，不能只凭关闭码判断业务成功。

## 7. 访问与数据

api_key 为占位检查，简单协议不要求调用者提供密钥，HTTP 会话读取接口也未鉴权。访问控制由部署方提供，见[配置与部署](../getting_started/配置与部署.md)。

音频和时间线按服务配置保存；保存开关和目录由服务端设置。参考音色固定于 Worker，协议没有上传参考音频、切换模型或训练操作。

## 8. 实现与维护

来源：[ws.py](../../src/fast_vc_service/routers/ws.py)、[适配器](../../src/fast_vc_service/adapters/protocol_adapter.py)、[识别器](../../src/fast_vc_service/adapters/protocol_detector.py)、[buffer.py](../../src/fast_vc_service/buffer.py)。协议变更同步中英文本文、示例调用和相关 Spec。
