import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import MarkdownIt from 'markdown-it'

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
export const WEBSITE = path.join(ROOT, 'docs/website')
export const STAGING = path.join(WEBSITE, '.generated')
export const BASE = '/fast-vc-service/'
export const REPO = 'https://github.com/Leroll/fast-vc-service'
const markdown = new MarkdownIt({ html: true })
const posix = path.posix

// 与既有 Python-Markdown 标题保持一致，不改变公开的数字／中文锚点。
export function slugify(text) {
  return text.normalize('NFC').replace(/<\/?[^>]*>/g, '').trim().toLowerCase().replace(/[^\p{L}\p{N}_\- ]/gu, '').replace(/ /g, '-')
}

export function routeFor(source) {
  if (source === 'README.md') return 'project/index.md'
  if (source === 'CONTRIBUTING.md') return 'contributing/index.md'
  if (source === 'docs/en/README.md') return 'en/project/index.md'
  const name = source.replace(/^docs\//, '')
  if (/(^|\/)(README|index)\.md$/.test(name)) return name.replace(/(README|index)\.md$/, 'index.md')
  return name.replace(/\.md$/, '/index.md')
}

export function collectSources(root = ROOT) {
  const sources = ['README.md', 'CONTRIBUTING.md']
  function walk(directory) {
    for (const item of fs.readdirSync(path.join(root, directory), { withFileTypes: true })) {
      const source = `${directory}/${item.name}`
      if (source === 'docs/website' || item.isSymbolicLink()) continue
      if (item.isDirectory()) walk(source)
      else if (item.isFile() && source.endsWith('.md')) sources.push(source)
    }
  }
  walk('docs')
  return sources.sort()
}

export function createManifest(root = ROOT) {
  const manifest = Object.fromEntries(collectSources(root).map(source => [source, routeFor(source)]))
  if (new Set(Object.values(manifest)).size !== Object.keys(manifest).length) throw new Error('文档网页路径冲突')
  return manifest
}

export function rewriteLink(value, source, manifest, root = ROOT, raw = false) {
  if (!value || /^(?:[a-z][a-z\d+.-]*:|\/|#)/i.test(value)) return value
  const match = value.match(/^([^?#]*)(.*)$/)
  const target = posix.normalize(posix.join(posix.dirname(source), decodeURIComponent(match[1])))
  const suffix = match[2]
  if (manifest[target]) {
    const route = manifest[target].replace(/index\.md$/, '')
    return `${raw ? BASE : '/'}${route.split('/').map(encodeURIComponent).join('/')}${suffix}`
  }
  const file = path.resolve(root, target)
  if (!file.startsWith(`${root}${path.sep}`) || !fs.existsSync(file)) throw new Error(`${source}: 仓库链接不存在或越界: ${value}`)
  const encoded = target.split('/').map(encodeURIComponent).join('/')
  if (/\.(png|jpe?g|webp|svg|gif)$/i.test(target)) return `https://raw.githubusercontent.com/Leroll/fast-vc-service/main/${encoded}${suffix}`
  return `${REPO}/${fs.statSync(file).isDirectory() ? 'tree' : 'blob'}/main/${encoded}${suffix}`
}

export function rewriteHTML(html, source, manifest, root = ROOT) {
  return html.replace(/(<[a-z][^>]*?\s(?:href|src)\s*=\s*)(["'])(.*?)\2/gi, (_, prefix, quote, value) => {
    const decoded = value.replace(/&amp;/g, '&')
    return prefix + quote + rewriteLink(decoded, source, manifest, root, true).replace(/&/g, '&amp;').replace(/"/g, '&quot;') + quote
  })
}

export function isHistorical(source) {
  return /^docs\/(specs\/|changelog\/|design\/archive\/|getting_started\/|perfermance_tests\/)/.test(source)
}

export function isSearchable(source) {
  return !/^docs\/(specs\/|changelog\/20|design\/archive\/|getting_started\/|perfermance_tests\/version)/.test(source)
}

export function stripEntryMetadata(text) {
  return text.replace(/^\*\*(?:文档版本：|Documentation version:).*\n\n/gm, '')
    .replace(/^(?:简体中文|English|\[(?:简体中文|English|API 参考|API reference|用户文档|User documentation)\])[^\n]* · [^\n]*\n\n/gm, '')
}

function fieldTable(section) {
  const lines = section.match(/^\|.*\|[ \t]*$/gm) || []
  if (lines.length < 3) throw new Error('找不到协议参数表')
  return lines.join('\n')
}

export function extractProtocol(text, source, manifest, root = ROOT) {
  const sections = text.split(/^## /m)
  const standard = sections.find(section => section.startsWith('1. '))
  const fields = sections.find(section => section.startsWith('2. '))
  const simple = sections.find(section => section.startsWith('4. '))
  if (!standard || !fields || !simple) throw new Error(`${source}: 协议章节不完整`)
  const messages = section => [...section.matchAll(/```json\s*\n([\s\S]*?)\n```/g)].map(match => JSON.parse(match[1]))
  const stdMessages = messages(standard)
  const simpleMessages = messages(simple)
  if (stdMessages[0]?.type !== 'config' || simpleMessages[0]?.signal !== 'start') throw new Error(`${source}: 无法识别协议初始化示例`)
  const render = value => {
    const tokens = markdown.parseInline(value, {})
    for (const token of tokens[0].children || []) if (token.type === 'link_open') token.attrSet('href', rewriteLink(token.attrGet('href'), source, manifest, root, true))
    return markdown.renderer.render(tokens, markdown.options, {})
  }
  const parse = (section, sample) => ({
    sample: JSON.stringify(sample, null, 2),
    fields: fieldTable(section).split('\n').slice(2).map(line => {
      const cells = line.trim().slice(1, -1).split(/(?<!\\)\|/).map(cell => render(cell.trim()))
      if (cells.length !== 5) throw new Error(`${source}: 参数表应有五列`)
      return { name: cells[0], type: cells[1], required: cells[2], default: cells[3], description: cells[4] }
    })
  })
  return {
    standard: parse(fields, stdMessages[0]), simple: parse(simple, simpleMessages[0]),
    anchors: { standard: slugify(standard.split('\n')[0]), simple: slugify(simple.split('\n')[0]) },
    flows: { standard: stdMessages.map(message => message.type), simple: simpleMessages.map(message => message.signal) }
  }
}

export function pageMetadata(source, text, manifest, root = ROOT) {
  const english = source.startsWith('docs/en/') || source === 'docs/changelog/releases_en.md'
  const home = ['docs/README.md', 'docs/en/index.md'].includes(source)
  const api = /\/(?:en\/)?api\//.test(source)
  const metadata = {
    repoSource: source, lang: english ? 'en' : 'zh-CN', historical: isHistorical(source),
    search: isSearchable(source), pageClass: home ? 'home-page' : api ? 'api-page' : 'reading-page',
    ...(home ? { layout: 'home' } : {}), ...(api ? { aside: false } : {})
  }
  if (source.endsWith('/api/voice-conversion.md')) metadata.protocols = extractProtocol(text, source, manifest, root)
  return metadata
}

export function prepareContent(root = ROOT, output = STAGING) {
  const manifest = createManifest(root)
  const expected = new Set()
  for (const [source, destination] of Object.entries(manifest)) {
    const original = fs.readFileSync(path.join(root, source), 'utf8')
    const metadata = pageMetadata(source, original, manifest, root)
    let body = stripEntryMetadata(original)
    if (metadata.protocols) {
      const sections = body.split(/^## /m)
      for (let i = 1; i < sections.length; i++) {
        if (sections[i].startsWith('2. ')) sections[i] = sections[i].replace(fieldTable(sections[i]), '<ApiParameters protocol="standard" />')
        if (sections[i].startsWith('4. ')) {
          sections[i] = sections[i].replace(/```json\s*\n[\s\S]*?\n```\n/, '')
          sections[i] = sections[i].replace(fieldTable(sections[i]), '<ApiParameters protocol="simple" />')
        }
      }
      body = sections.join('## ').replace(/^(## 1\. )/m, '<ProtocolNav />\n\n$1')
    }
    const frontmatter = Object.entries(metadata).map(([key, value]) => `${key}: ${JSON.stringify(value)}`).join('\n')
    const file = path.join(output, destination)
    expected.add(file)
    fs.mkdirSync(path.dirname(file), { recursive: true })
    const content = `---\n${frontmatter}\n---\n\n${body}`
    if (!fs.existsSync(file) || fs.readFileSync(file, 'utf8') !== content) fs.writeFileSync(file, content)
  }
  // 仅清理本步骤管理的临时 Markdown，不接触仓库原文。
  function prune(directory) {
    for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, item.name)
      if (item.isDirectory()) prune(file)
      else if (file.endsWith('.md') && !expected.has(file)) fs.unlinkSync(file)
    }
  }
  prune(output)
  fs.writeFileSync(path.join(output, 'manifest.json'), JSON.stringify(manifest, null, 2))
  return manifest
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  console.log(`已准备 ${Object.keys(prepareContent()).length} 页；原 Markdown 保持不变。`)
}
