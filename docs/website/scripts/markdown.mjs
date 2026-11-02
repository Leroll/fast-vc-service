import fs from 'node:fs'
import path from 'node:path'
import { ROOT, STAGING, createManifest, rewriteLink, rewriteHTML, stripEntryMetadata } from './content.mjs'

export function repositoryMarkdown(md) {
  md.core.ruler.after('inline', 'repository-links', state => {
    const manifest = createManifest()
    const reverse = Object.fromEntries(Object.entries(manifest).map(([source, destination]) => [destination, source]))
    const relative = state.env.relativePath || path.relative(STAGING, state.env.path || '')
    const source = reverse[relative]
    if (!source) return
    for (const token of state.tokens) {
      if (token.type === 'html_block') token.content = rewriteHTML(token.content, source, manifest)
      for (const child of token.children || []) {
        for (const attribute of ['href', 'src']) {
          const value = child.attrGet(attribute)
          if (value) child.attrSet(attribute, rewriteLink(value, source, manifest))
        }
        if (child.type === 'html_inline') child.content = rewriteHTML(child.content, source, manifest)
      }
    }
    if (!['docs/README.md', 'docs/en/index.md'].includes(source) || state.env.searchRender) return
    let paragraph = 0
    for (const token of state.tokens) {
      if (token.type !== 'paragraph_open') continue
      paragraph++
      if (paragraph === 1) token.attrJoin('class', 'home-lead')
      if (paragraph === 2) token.attrJoin('class', 'home-actions')
    }
    // 首页任务表仍由普通 Markdown 维护，网页将其渲染为语义化列表。
    const begin = state.tokens.findIndex(token => token.type === 'table_open')
    if (begin < 0) return
    const end = state.tokens.findIndex((token, index) => index > begin && token.type === 'table_close')
    const body = state.tokens.slice(begin, end + 1)
    const rows = []
    let cells = null
    for (const token of body) {
      if (token.type === 'tr_open') cells = []
      if (token.type === 'inline' && cells) cells.push(md.renderer.renderInline(token.children, state.md.options, state.env))
      if (token.type === 'tr_close') { rows.push(cells); cells = null }
    }
    const replacement = new state.Token('html_block', '', 0)
    replacement.content = `<div class="home-task-grid" role="list">${rows.slice(1).map((row, index) => `<div class="home-task" role="listitem"><span class="task-number" aria-hidden="true">0${index + 1}</span><h3>${row[0]}</h3>${row.slice(1).map(cell => `<p>${cell}</p>`).join('')}</div>`).join('')}</div>\n`
    state.tokens.splice(begin, end - begin + 1, replacement)
  })
}

// 索引原文中的字段与示例，避免 Vue 展示组件使全文搜索丢失正文。
export function renderSearch(src, env, md) {
  md.render(src, env)
  if (env.frontmatter?.search === false) return ''
  const source = env.frontmatter?.repoSource
  if (!source) throw new Error(`搜索页面缺少来源: ${env.relativePath}`)
  env.searchRender = true
  return md.render(stripEntryMetadata(fs.readFileSync(path.join(ROOT, source), 'utf8')), env)
}
