# Fast-VC 文档

简体中文 · [English](en/index.md) · [项目主页](../README.md)

从第一次语音转换开始，再按任务查找部署、接口和原理说明。

**文档版本：main 开发分支。** 使用已发布版本时，请从 [GitHub Releases](https://github.com/Leroll/fast-vc-service/releases) 进入对应标签阅读文档。

## 1. 使用服务

<a id="11-安装与运行"></a>

第一次使用请阅读[快速开始](getting-started/quick-start.md)：准备环境、启动服务、用仓库样例完成首次转换并检查结果。

已有运行环境时，按当前任务选择：

| 我想做什么 | 阅读入口 |
| --- | --- |
| 配置模型、参考音色或多个 Worker | [配置与部署](getting-started/configuration.md) |
| 接入 WebSocket 音频流 | [语音转换 API](api/voice-conversion.md) |
| 检查服务是否运行、查询版本 | [系统接口](api/system.md) |
| 读取录音与会话时间线 | [会话数据](api/session-data.md) |
| 排查启动、连接或音频问题 | [故障排查](getting-started/troubleshooting.md) |
| 测量效果、延迟与吞吐 | [评测指南](evaluation/README.md) |

## 2. 查询接口与理解原理

<a id="12-接口参考"></a>

[API 参考](api/README.md)集中维护消息、字段、错误和接入约定；[配置与部署](getting-started/configuration.md#2-常用配置)说明示例部署参数及其来源。

需要理解处理过程时，从[总体设计](design/总体设计.md)开始，再按[设计索引](design/README.md)阅读缓冲、会话、流式转换或模型专题。

## 3. 版本与贡献

用户可见的变化见[版本说明](changelog/releases.md)。参与开发、维护文档或查阅工程记录，请进入[开发与维护](maintainers/README.md)。

<a id="2-理解与贡献"></a>
<a id="3-多语言维护"></a>
<a id="4-维护边界"></a>

原文档索引中的[多语言维护与版本约定](maintainers/documentation.md#3-多语言维护)已移至维护指南；历史资料与任务记录从开发与维护入口访问。
