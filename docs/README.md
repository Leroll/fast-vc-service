# Fast-VC 文档

简体中文 · [English](en/index.md) · [在线文档](https://leroll.github.io/fast-vc-service/) · [项目主页](../README.md)

中文为主文档语言；英文入口见[项目首页](en/README.md)与[用户文档](en/index.md)。从安装服务到接入语音转换，可按下面的顺序阅读。

## 1. 使用服务

### 1.1 安装与运行

| 文档 | 内容 |
| --- | --- |
| [快速开始](getting-started/quick-start.md) | 安装依赖、启动服务、完成第一次转换 |
| [配置与部署](getting-started/configuration.md) | 配置来源、模型、参考音色、多 Worker 与服务管理 |
| [故障排查](getting-started/troubleshooting.md) | 启动、客户端、音频输出及常见问题 |

### 1.2 接口参考

| 文档 | 内容 |
| --- | --- |
| [API 概览](api/README.md) | 接口清单、服务地址和认证 |
| [语音转换](api/voice-conversion.md) | 流式调用、字段、音频格式与错误 |
| [系统接口](api/system.md) | 健康检查和版本查询 |
| [会话数据](api/session-data.md) | 获取录音与时间线、解码及保存时序 |

## 2. 理解与贡献

- [当前设计](design/README.md)：总体设计，以及启动配置、协议适配、会话状态、音频缓冲、转换流水线、模型与参考音色、数据记录七个模块。
- [评测指南](evaluation/README.md)：性能口径与效果评测；[历史性能报告](perfermance_tests/README.md)保留原始数据与语言。
- [贡献指南](../CONTRIBUTING.md)：开发准备、报告问题、验证和提交。
- [文档网站](design/文档网站.md)：本地预览、构建验证与 GitHub Pages 自动发布。
- [协作规则](../AGENTS.md)：开发助手入口及维护规则。
- [需求与验收](specs/README.md)：重要任务的方案与实施证据。
- [每日变更](changelog/README.md)：实际改动、验证及限制。
- [版本历史](changelog/releases.md) / [English](changelog/releases_en.md)：从原 README 保留的发布说明。
- [已确认待办](todo.md)：已确定且未完成的工作。
- [历史原理笔记](design/archive/README.md)：原始笔记及迁移说明。

本节维护文档使用中文，不默认提供译文；历史材料保留原语言。

## 3. 多语言维护

中文原文使用根目录和 `docs/` 下的常规文档结构，英文译文集中在 `docs/en/`。翻译范围限定为下表，新增文档先在本索引中明确读者、语言和翻译范围，不自动增加英文版本或空目录。

| 内容 | 中文原文 | 英文译文 |
| --- | --- | --- |
| 项目主页 | `README.md` | `docs/en/README.md` |
| 用户导航 | `docs/README.md` 中的使用服务入口 | `docs/en/index.md`，仅维护用户导航和必要的进一步阅读链接 |
| 安装与运行 | `docs/getting-started/` 下的 `quick-start.md`、`configuration.md`、`troubleshooting.md` | `docs/en/getting-started/` 下的同名文件 |
| API | `docs/api/` 下的 `README.md`、`voice-conversion.md`、`system.md`、`session-data.md` | `docs/en/api/` 下的同名文件 |

- **原文与译文**：中文作为维护原文和默认阅读入口，英文保持相同的事实、接口语义和示例；接口事实最终以源码和有效配置为准。英文用户索引只翻译用户导航，不复制中文总索引中的维护规则。
- **同步更新**：修改翻译范围内的行为、字段、默认值、命令或示例时，在同一改动中同步中英文。暂时无法同步的译文需用英文标注待同步范围并链接中文原文，不将旧内容默认为当前行为。
- **单页语言**：每篇文档使用一种正文语言。代码、字段名、错误原文、专有名词及语言切换链接保留必要的原文形式，不属于逐段双语对照。未翻译内容通过链接说明，不把整段中文插进英文页面。
- **路径对应**：除项目首页和用户索引外，英文文件在 `docs/en/` 下保持中文文件相对于 `docs/` 的路径，例如 `docs/api/system.md` 对应 `docs/en/api/system.md`。上述用户文档的普通文件名使用小写英文和连字符，目录入口使用 `README.md`；英文用户索引使用 `index.md`。
- **导航与资源**：已翻译页面在页首链接对应语言版本，正文优先链接同语言页面。英文文档引用仅有中文的页面时明确标注中文；新增译文后同步相关导航。共享图片、音频、源码和配置引用仓库现有文件，不按语言复制。

AGENTS、CONTRIBUTING、设计、Spec、每日 changelog、todo 与评测入口以中文维护。AGENTS 仅保留根目录一份，不在译文目录复制协作规则。历史正文及发布记录保留原语言和位置，包括 `docs/changelog/releases_en.md`；不为统一目录改写历史。原 `docs/getting_started/` 下的历史笔记跳转页继续保留以兼容旧链接。

## 4. 维护边界

当前设计以仓库源码和配置为依据，规划与已实现行为分开标注。历史版本说明、旧性能报告和原始笔记保存当时上下文，不能代替当前操作指南。

本仓库文档自足，不依赖仓库外资料。新增文档或职责变化同步本索引。源码审阅不等于服务启动、GPU 推理或性能验收。
