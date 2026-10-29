# Fast-VC 文档

## 1. 使用服务

| 目标 | 文档 | 语言 |
| --- | --- | --- |
| 了解用途、能力和样例 | [项目主页](../README_ZH.md) / [English](../README.md) | 中 / 英 |
| 完成第一次转换 | [快速开始](getting_started/quick_started_zh.md) / [English](getting_started/quick_started_en.md) | 中 / 英 |
| 配置模型、参考音色与部署 | [配置与部署](getting_started/配置与部署.md) | 中文 |
| 接入流式协议 | [WebSocket API](api_docs/websocket-api-doc.md) / [English](api_docs/websocket-api-doc_EN.md) | 中 / 英 |
| 健康检查、版本和会话数据 | [HTTP API](api_docs/http-api.md) | 中英摘要 |
| 定位运行问题 | [故障排查](getting_started/故障排查.md) | 中文 |
| 理解性能口径与效果评测 | [评测指南](evaluation/README.md) / [历史性能报告](perfermance_tests/README.md) | 中文，历史报告含英文 |

## 2. 理解与贡献

- [当前设计](design/README.md)：总体结构、流式音频、模型推理、会话与可观测性。
- [贡献指南](../CONTRIBUTING.md)：开发准备、报告问题、验证和提交（英文）。
- [协作规则](../AGENTS.md)：开发助手入口及维护规则。
- [需求与验收](specs/README.md)：重要任务的方案与实施证据。
- [每日变更](changelog/README.md)：实际改动、验证及限制。
- [版本历史](changelog/releases.md) / [English](changelog/releases_en.md)：从原 README 保留的发布说明。
- [已确认待办](todo.md)：已确定且未完成的工作。
- [历史原理笔记](design/archive/README.md)：原始笔记及迁移说明。

## 3. 维护边界

当前设计以仓库源码和配置为依据，规划与已实现行为分开标注。历史版本说明、旧性能报告和原始笔记保存当时上下文，不能代替当前操作指南。

本仓库文档自足，不依赖仓库外资料。双语入口同步维护事实，新增文档或职责变化同步本索引。源码审阅不等于服务启动、GPU 推理或性能验收。
