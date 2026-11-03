import fs from 'node:fs'
import path from 'node:path'
import { ROOT, BASE } from './content.mjs'

const site = path.join(ROOT, 'site')
const records = []
const locales = new Set()
for (const name of fs.readdirSync(path.join(site, 'assets/chunks'))) {
  const match = name.match(/^@localSearchIndex(root|en)\..*\.js$/)
  if (!match) continue
  locales.add(match[1])
  const code = fs.readFileSync(path.join(site, 'assets/chunks', name), 'utf8')
  const { default: serialized } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
  const index = JSON.parse(serialized)
  const locations = Object.values(index.documentIds || {})
  if (!locations.length) throw new Error(`${match[1]} 搜索索引为空`)
  for (const location of locations) {
    if (!location.startsWith(BASE)) throw new Error(`搜索地址缺少项目路径: ${location}`)
    if (/\/specs\/|\/design\/archive\/|\/changelog\/20|\/perfermance_tests\/version/.test(location)) throw new Error(`历史资料进入搜索: ${location}`)
  }
  records.push(...locations)
}
if (locales.size !== 2) throw new Error('缺少中文或英文实际搜索索引')
fs.writeFileSync(path.join(site, 'search-records.json'), JSON.stringify([...new Set(records)], null, 2))
console.log(`已验证两种语言的实际搜索索引，共 ${records.length} 条记录。`)
