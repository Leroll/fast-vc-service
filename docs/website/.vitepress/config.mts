import fs from 'node:fs'
import path from 'node:path'
import { defineConfig } from 'vitepress'
import { ROOT, BASE, REPO, createManifest, slugify } from '../scripts/content.mjs'
import { repositoryMarkdown, renderSearch } from '../scripts/markdown.mjs'
import { zhSidebar, enSidebar, zhNav, enNav } from './navigation.mjs'

export default defineConfig({
  title: 'Fast-VC', description: '实时流式语音转换服务：安装、部署、接口与原理',
  base: BASE, srcDir: '.generated', outDir: '../../site',
  appearance: true, lastUpdated: false, ignoreDeadLinks: false,
  head: [['meta', { name: 'theme-color', content: '#F6F7F2', media: '(prefers-color-scheme: light)' }], ['meta', { name: 'theme-color', content: '#181C16', media: '(prefers-color-scheme: dark)' }]],
  locales: {
    root: { label: '简体中文', lang: 'zh-CN', link: '/', themeConfig: {
      nav: zhNav, sidebar: zhSidebar, outline: { label: '本页内容', level: [2, 3] },
      docFooter: { prev: '上一篇', next: '下一篇' }, editLink: { pattern: page => page.frontmatter.editLink, text: '查看 Markdown 源文档' },
      darkModeSwitchLabel: '主题', darkModeSwitchTitle: '切换至暗色主题', lightModeSwitchTitle: '切换至浅色主题',
      sidebarMenuLabel: '目录', returnToTopLabel: '回到顶部', langMenuLabel: '切换语言', skipToContentLabel: '跳到正文',
      footer: { message: 'Fast-VC · 实时流式语音转换', copyright: 'GPL-3.0 · 文档跟随 main 分支' }
    } },
    en: { label: 'English', lang: 'en', link: '/en/', themeConfig: {
      nav: enNav, sidebar: enSidebar, outline: { label: 'On this page', level: [2, 3] },
      docFooter: { prev: 'Previous', next: 'Next' }, editLink: { pattern: page => page.frontmatter.editLink, text: 'View Markdown source' },
      footer: { message: 'Fast-VC · Real-time streaming voice conversion', copyright: 'GPL-3.0 · Documentation follows main' }
    } }
  },
  themeConfig: {
    siteTitle: 'Fast-VC', i18nRouting: false, socialLinks: [{ icon: 'github', link: REPO }],
    search: { provider: 'local', options: {
      _render: renderSearch,
      miniSearch: { options: {
        // 此函数会被序列化至浏览器；不能依赖构建进程里的闭包变量。
        tokenize: (text: string) => {
          const words = text.toLowerCase().split(/[\s\p{P}\p{S}]+/u).filter(Boolean)
          return words.flatMap(word => {
            if (!/\p{Script=Han}/u.test(word)) return [word]
            if (typeof Intl.Segmenter === 'function') return [...new Intl.Segmenter('zh', { granularity: 'word' }).segment(word)].filter(item => item.isWordLike).map(item => item.segment)
            return [word, ...Array.from(word)]
          })
        }
      } },
      locales: { root: { translations: {
        button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
        modal: { noResultsText: '没有找到结果', resetButtonTitle: '清除搜索', displayDetails: '显示详细结果',
          footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' } }
      } } }
    } }
  },
  markdown: { anchor: { slugify }, config: repositoryMarkdown },
  transformPageData(pageData) {
    const source = pageData.frontmatter.repoSource
    if (!source) return
    pageData.frontmatter.editLink = `${REPO}/blob/main/${source.split('/').map(encodeURIComponent).join('/')}`
    const manifest = createManifest()
    const policy = fs.readFileSync(path.join(ROOT, 'tools/docs/content.toml'), 'utf8').split('[review]')[0]
    for (const match of policy.matchAll(/^"([^"]+)"\s*=\s*"([^"]+)"/gm)) {
      if ([match[1], match[2]].includes(source)) {
        const other = source === match[1] ? match[2] : match[1]
        pageData.frontmatter.translation = BASE + manifest[other].replace(/index\.md$/, '')
      }
    }
  },
  async buildEnd(config) {
    fs.writeFileSync(path.join(config.outDir, 'docs-manifest.json'), JSON.stringify({ base: BASE, pages: createManifest() }, null, 2))
  }
})
