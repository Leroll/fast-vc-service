# 文档网站工程

## 1. 职责

这里集中维护 VitePress 的依赖、配置、主题和构建适配。正文使用 docs/zh 和 docs/en 的 Markdown，根 README 和 CONTRIBUTING 在构建时复用；docs/README.md 仅作仓库语言入口。中文网页保持根路径，英文保持 en/ 路径，源码目录变化不改变既有网页地址。

## 2. 开发与维护

本地预览、完整检查、发布与依赖更新统一见[文档网站设计](../zh/design/文档网站.md)。不要编辑 .generated、node_modules 或生成的 site 目录。
