const page = (text, link) => ({ text, link })
export const guide = [
  page('快速开始', '/getting-started/quick-start/'), page('配置与部署', '/getting-started/configuration/'),
  page('故障排查', '/getting-started/troubleshooting/'), page('项目介绍', '/project/')
]
export const api = [
  page('API 概览', '/api/'), page('语音转换', '/api/voice-conversion/'),
  page('系统接口', '/api/system/'), page('会话数据', '/api/session-data/')
]
export const design = ['总体设计', '服务启动与运行配置', '接入与协议适配', '会话与状态管理', '音频输入与缓冲', '流式转换流水线', '模型与参考音色', '数据记录与可观测性'].map(text => page(text, `/design/${text}/`))
const maintainers = [page('贡献指南', '/contributing/'), page('开发与维护', '/maintainers/'), page('文档维护', '/maintainers/documentation/'), page('文档网站', '/design/文档网站/'), page('版本历史', '/changelog/releases/')]
const group = (text, items, collapsed = false) => ({ text, items, collapsed })
export const zhSidebar = {
  '/getting-started/': [group('使用指南', guide), group('继续阅读', [api[0], page('评测指南', '/evaluation/')])],
  '/project/': [group('使用指南', guide)],
  '/api/': [group('API 参考', api), group('接入准备', [guide[0], guide[1], guide[2]])],
  '/design/': [group('当前设计', [page('设计索引', '/design/'), ...design]), group('评测', [page('评测指南', '/evaluation/'), page('评测报告', '/evaluation/reports/')])],
  '/evaluation/': [group('评测', [page('评测指南', '/evaluation/'), page('评测报告', '/evaluation/reports/')]), group('原理', design, true)],
  '/': [group('开发与维护', maintainers), group('使用指南', guide, true), group('API 参考', api, true)]
}
const enGuide = [page('Quick start', '/en/getting-started/quick-start/'), page('Configuration & deployment', '/en/getting-started/configuration/'), page('Troubleshooting', '/en/getting-started/troubleshooting/'), page('Project overview', '/en/project/')]
const enApi = [page('API overview', '/en/api/'), page('Voice conversion', '/en/api/voice-conversion/'), page('System', '/en/api/system/'), page('Session data', '/en/api/session-data/')]
export const enSidebar = {
  '/en/api/': [group('API reference', enApi), group('Getting started', enGuide, true)],
  '/en/': [group('Guides', enGuide), group('API reference', enApi, true)]
}
export const zhNav = [page('使用指南', guide[0].link), page('API', '/api/'), page('原理与评测', '/design/'), page('贡献', '/contributing/')]
export const enNav = [page('Guides', enGuide[0].link), page('API', '/en/api/'), page('Architecture (中文)', '/design/'), page('Contribute (中文)', '/contributing/')]
