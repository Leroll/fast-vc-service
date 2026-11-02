import fs from 'node:fs'
import path from 'node:path'
import { createServer } from 'vitepress'
import { ROOT, WEBSITE, prepareContent } from './content.mjs'

prepareContent()
const server = await createServer(WEBSITE, { host: '127.0.0.1', port: 18127 })
await server.listen()
server.printUrls()
let timer
const refresh = () => {
  clearTimeout(timer)
  timer = setTimeout(() => { try { prepareContent() } catch (error) { console.error(error) } }, 100)
}
const watchers = [fs.watch(path.join(ROOT, 'docs'), { recursive: true }, (_, name) => {
  if (name?.endsWith('.md') && !name.startsWith(`website${path.sep}`)) refresh()
})]
watchers.push(fs.watch(ROOT, (_, name) => {
  if (['README.md', 'CONTRIBUTING.md'].includes(name)) refresh()
}))
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, async () => {
  for (const watcher of watchers) watcher.close()
  await server.close()
  process.exit()
})
