import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { routeFor, slugify, rewriteLink, rewriteHTML, prepareContent, createManifest, extractProtocol, isHistorical, isSearchable, stripEntryMetadata, ROOT } from './content.mjs'

test('保留入口与普通页面的目录式网址', () => {
  assert.equal(routeFor('docs/README.md'), 'index.md')
  assert.equal(routeFor('docs/en/README.md'), 'en/project/index.md')
  assert.equal(routeFor('docs/en/index.md'), 'en/index.md')
  assert.equal(routeFor('docs/api/voice-conversion.md'), 'api/voice-conversion/index.md')
  assert.equal(routeFor('README.md'), 'project/index.md')
})

test('数字与中文标题保持原有锚点', () => {
  assert.equal(slugify('1.1 安装与运行'), '11-安装与运行')
  assert.equal(slugify('3.2 Opus 示例'), '32-opus-示例')
  assert.equal(slugify('配置（默认值） / x_y'), '配置默认值--x_y')
})

test('隐藏重复语言导航，不删除以文档链接开头的正文', () => {
  const body = '[API 参考](api/README.md) 集中维护消息、字段和错误。\n\n'
  assert.equal(stripEntryMetadata('[用户文档](../README.md) · [English](../en/index.md)\n\n' + body), body)
  assert.equal(stripEntryMetadata('[User documentation](../index.md) · [简体中文](../../README.md)\n\n' + body), body)
})

test('文档链接保留查询参数与锚点，源码指向 GitHub', () => {
  const manifest = createManifest()
  assert.equal(rewriteLink('../api/README.md?mode=pcm#3-认证', 'docs/getting-started/quick-start.md', manifest), '/api/?mode=pcm#3-认证')
  assert.equal(rewriteLink('../../configs/prod.yaml', 'docs/api/README.md', manifest), 'https://github.com/Leroll/fast-vc-service/blob/main/configs/prod.yaml')
  assert.equal(rewriteLink('#sample', 'docs/api/README.md', manifest), '#sample')
})

test('拒绝不存在与越出仓库的相对链接', () => {
  assert.throws(() => rewriteLink('../../../../outside.txt', 'docs/api/README.md', {}), /不存在或越界/)
  assert.throws(() => rewriteLink('missing.md', 'docs/README.md', {}), /不存在或越界/)
})

test('原生 HTML 链接与图片适配，不修改普通文本', () => {
  const manifest = createManifest()
  assert.equal(rewriteHTML('<a href="api/README.md">api/README.md</a>', 'docs/README.md', manifest), '<a href="/fast-vc-service/api/">api/README.md</a>')
  assert.equal(rewriteHTML('<img src="assets/cover.webp" alt="cover">', 'README.md', manifest), '<img src="/brand/cover.webp" alt="cover">')
  assert.equal(rewriteHTML('<img src="../../assets/cover.webp" alt="cover">', 'docs/en/README.md', manifest), '<img src="/brand/cover.webp" alt="cover">')
  assert.equal(rewriteLink('assets/cover.webp', 'README.md', manifest), '/brand/cover.webp')
})

test('协议展示从正文提取，简单协议不添加 ready', () => {
  const source = 'docs/api/voice-conversion.md'
  const protocol = extractProtocol(fs.readFileSync(path.join(ROOT, source), 'utf8'), source, createManifest())
  assert.deepEqual(protocol.flows.standard, ['config', 'ready', 'end', 'complete'])
  assert.deepEqual(protocol.flows.simple, ['start', 'end', 'completed'])
  assert.equal(protocol.standard.fields.length, 9)
  assert.equal(protocol.simple.fields.length, 7)
  assert.equal(JSON.parse(protocol.simple.sample).signal, 'start')
})

test('构建准备不改原文、不拷贝音频，删除文档后移除对应临时页', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'fast-vc-docs-'))
  try {
    fs.mkdirSync(path.join(root, 'docs/website'), { recursive: true })
    const original = '# Example\n\n```bash\nprintf "[x](missing.md)"\n```\n'
    for (const name of ['README.md', 'CONTRIBUTING.md', 'docs/README.md', 'docs/guide.md']) fs.writeFileSync(path.join(root, name), original)
    fs.mkdirSync(path.join(root, 'assets/brand/concepts'), { recursive: true })
    for (const name of ['assets/cover.webp', 'assets/brand/logo-128.png', 'assets/brand/favicon.ico']) fs.writeFileSync(path.join(root, name), `fixture:${name}`)
    fs.writeFileSync(path.join(root, 'assets/brand/concepts/draft.png'), 'excluded')
    fs.writeFileSync(path.join(root, 'docs/private.wav'), 'excluded')
    fs.writeFileSync(path.join(root, 'docs/website/internal.md'), 'excluded')
    const output = path.join(root, 'docs/website/.generated')
    prepareContent(root, output)
    assert.equal(fs.readFileSync(path.join(root, 'docs/guide.md'), 'utf8'), original)
    assert.match(fs.readFileSync(path.join(output, 'guide/index.md'), 'utf8'), /printf "\[x\]\(missing\.md\)"/)
    assert.equal(fs.existsSync(path.join(output, 'private.wav')), false)
    assert.equal(fs.existsSync(path.join(output, 'website')), false)
    assert.deepEqual(fs.readdirSync(path.join(output, 'public/brand')).sort(), ['cover.webp', 'favicon.ico', 'logo-128.png'])
    assert.equal(fs.readFileSync(path.join(output, 'public/brand/cover.webp'), 'utf8'), 'fixture:assets/cover.webp')
    assert.equal(fs.readFileSync(path.join(output, 'public/brand/logo-128.png'), 'utf8'), 'fixture:assets/brand/logo-128.png')
    assert.equal(fs.readFileSync(path.join(output, 'public/brand/favicon.ico'), 'utf8'), 'fixture:assets/brand/favicon.ico')
    fs.unlinkSync(path.join(root, 'docs/guide.md'))
    prepareContent(root, output)
    assert.equal(fs.existsSync(path.join(output, 'guide/index.md')), false)
  } finally { fs.rmSync(root, { recursive: true, force: true }) }
})

test('历史正文保留提示且不进入搜索，评测入口和当前文档可检索', () => {
  for (const source of ['docs/specs/task/plan.md', 'docs/changelog/2026-11-03.md', 'docs/design/archive/old.md', 'docs/evaluation/reports/2025-06-15_1803/4090d.md']) {
    assert.equal(isSearchable(source), false)
    assert.equal(isHistorical(source), true)
  }
  for (const source of ['docs/evaluation/README.md', 'docs/evaluation/reports/README.md', 'docs/api/voice-conversion.md']) {
    assert.equal(isSearchable(source), true)
    assert.equal(isHistorical(source), false)
  }
  assert.equal(isSearchable('docs/changelog/releases.md'), true)
})
