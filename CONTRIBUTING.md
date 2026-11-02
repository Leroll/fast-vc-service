# 参与 Fast-VC 开发

## 1. 从这里开始

欢迎提交修复、文档改进、可复现的问题报告和服务集成。先阅读[项目主页](README.md)和[文档索引](docs/README.md)。项目文档以中文维护，项目介绍、安装、配置、API 和故障排查提供[英文译文](docs/en/README.md)；设计、任务记录和每日工程日志以中文维护。

问题和建议通过 [GitHub Issues](https://github.com/Leroll/fast-vc-service/issues) 提交。请说明仓库版本或提交、模型与配置、环境、输入格式、复现步骤、预期行为和实际结果，提供最小示例及脱敏日志。

## 2. 准备开发环境

克隆时包含子模块，按[快速开始](docs/getting-started/quick-start.md)准备环境。使用 uv 和仓库现有的 pyproject.toml、uv.lock，在仓库根目录执行命令。

服务代码位于 `src/fast_vc_service/`，客户端位于 `examples/websocket/`，配置位于 `configs/`。Seed-VC 子模块属于本仓库的依赖，修改流式处理行为前先阅读[当前设计](docs/design/README.md)。

## 3. 提出与实现改动

重要功能、协议变更、重构、推理行为或部署变更，先在 [Spec](docs/specs/README.md) 中记录设计和验收标准，再开始实现。小修复可以只写简短的 changelog；续做同一任务时更新已有记录。

一次改动围绕同一目的。行为变化时同步当前设计及相关用户文档，已纳入翻译范围的文档同步更新中英文版本。[文档维护约定](docs/README.md#3-多语言维护)统一说明原文语言、翻译范围和导航规则，新增文档不自动要求翻译。AI 辅助开发遵循 [AGENTS.md](AGENTS.md)。

## 4. 验证

文档改动检查相对链接、锚点、源码一致性和 `git diff --check`。

代码改动按影响范围选择协议或配置检查、服务联调、GPU 推理、试听评测或压力测试。仓库目前没有专门的自动化测试套件，不将客户端示例视为回归测试覆盖；说明实际执行了哪些验证，以及哪些仍未测试。

性能和音质结果需要注明模型、硬件、配置及输入条件，方法见[评测指南](docs/evaluation/README.md)。除非贡献范围已明确包含相关内容的公开发布，否则不要将原始音频、模型缓存、会话输出或凭据加入改动。

## 5. 拉取请求与提交

说明问题、改动后的行为、兼容影响和验证结果，链接相关 Issue 或 Spec，并写明限制。保留无关修改及历史记录。

提交信息使用 `<类型>: <中文描述>`，例如 `docs: 更新流式接口与快速开始`。类型包括 feat、fix、docs、refactor、test、build、ci、chore。

实际变更记录在 [changelog](docs/changelog/README.md)。[todo](docs/todo.md) 只收录已确认且未完成的工作，未接受的提议不直接转为待办。
