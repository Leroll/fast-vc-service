# API 参考

[English](../en/api/README.md) · [快速开始](../getting-started/quick-start.md) · [用户文档](../README.md)

Fast-VC 提供流式语音转换、服务状态查询和会话文件读取接口。本文档适用于服务版本 `0.1.7`。

## 1. 接口

| 功能 | 方法与路径 | 说明 |
| --- | --- | --- |
| [语音转换](voice-conversion.md) | WebSocket `/ws` | 发送 PCM 或 Opus 音频，接收转换后的 PCM 音频 |
| [健康检查](system.md#1-健康检查) | GET `/health` | 检查 API 是否可访问 |
| [版本查询](system.md#2-版本查询) | GET `/version` | 获取服务版本和构建日期 |
| [会话数据](session-data.md) | GET `/tools/session/{session_id}` | 获取已保存的录音和时间线 |

WebSocket `/` 是 `/ws` 的别名。语音转换支持标准协议和简单协议；新客户端建议使用带 `ready` 确认的标准协议，详见[消息流程](voice-conversion.md#1-调用示例)。

## 2. 服务地址

本地示例使用以下地址，主机和端口按部署替换：

| 接口 | 地址 |
| --- | --- |
| HTTP | `http://localhost:8042` |
| WebSocket | `ws://localhost:8042/ws` |

启用 TLS 的部署使用 `https://` 和 `wss://`。服务启动后，可访问 `/docs` 查看 HTTP 交互文档，或访问 `/openapi.json` 获取 HTTP Schema；WebSocket 消息格式见[语音转换](voice-conversion.md)。

## 3. 认证

当前服务没有完整的内置鉴权：标准协议只检查 `api_key` 非空，简单协议不要求客户端提供密钥，HTTP 接口不检查密钥。部署时通过网关或反向代理配置认证与访问控制；会话数据接口可返回已保存的录音。

## 4. 相关文档

- [快速开始](../getting-started/quick-start.md)：安装、启动和首次转换。
- [配置与部署](../getting-started/configuration.md)：模型、参考音色、保存开关与服务端参数。参考音色在服务启动时配置，当前没有逐请求上传参考音频或切换模型的接口。
- [当前设计](../design/README.md)：缓冲、转换和会话管理的内部实现。
