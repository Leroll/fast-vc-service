# Fast-VC 文档

简体中文 · [English](../en/index.md) · [项目主页](../../README.md)

从第一次语音转换开始，再按任务查找部署、接口和原理说明。

[开始使用](getting-started/quick-start.md) · [查看 API](api/README.md)

**文档版本：main 开发分支。** 使用已发布版本时，请从 [GitHub Releases](https://github.com/Leroll/fast-vc-service/releases) 进入对应标签阅读文档。

## 1. 使用服务

<a id="11-安装与运行"></a>

| 任务 | 说明 | 阅读入口 |
| --- | --- | --- |
| 完成第一次转换 | 准备环境、启动服务，用仓库样例验证音频输入与输出。 | [快速开始](getting-started/quick-start.md) |
| 接入你的应用 | 查询消息、字段和音频格式，接收转换结果及会话数据。 | [语音转换 API](api/voice-conversion.md) · [系统接口](api/system.md) · [会话数据](api/session-data.md) |
| 配置与部署 | 调整模型、参考音色、设备与 Worker，排查运行问题。 | [配置与部署](getting-started/configuration.md) · [故障排查](getting-started/troubleshooting.md) |
| 理解原理与评测 | 了解流式处理链路，按统一方法测量效果、延迟与吞吐。 | [总体设计](design/总体设计.md) · [评测指南](evaluation/README.md) · [评测报告](evaluation/reports/README.md) |

## 2. 查询接口与理解原理

<a id="12-接口参考"></a>

[API 参考](api/README.md)集中维护消息、字段、错误和接入约定；[配置与部署](getting-started/configuration.md#2-常用配置)说明示例部署参数及其来源。

需要理解处理过程时，从[总体设计](design/总体设计.md)开始，再按[设计索引](design/README.md)阅读缓冲、会话、流式转换或模型专题。

## 3. 版本与贡献

用户可见的变化见[版本说明](changelog/releases.md)。参与开发、维护文档或查阅工程记录，请进入[开发与维护](maintainers/README.md)。

<a id="2-理解与贡献"></a>
<a id="3-多语言维护"></a>
<a id="4-维护边界"></a>

文档编写、[多语言维护与版本约定](maintainers/documentation.md#3-多语言维护)见维护指南；历史资料与任务记录从开发与维护入口访问。
