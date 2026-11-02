<script setup>
import { computed } from 'vue'
import { useData } from 'vitepress'
const { frontmatter, lang } = useData()
const english = computed(() => lang.value.startsWith('en'))
const protocols = computed(() => frontmatter.value.protocols)
const flow = type => {
  const messages = [...protocols.value.flows[type]]
  messages.splice(type === 'standard' ? 2 : 1, 0, english.value ? 'audio' : '音频流')
  return messages.join(' → ')
}
</script>

<template>
  <nav class="protocol-nav" :aria-label="english ? 'Protocol guides' : '选择协议指南'">
    <a :href="`#${protocols.anchors.standard}`"><span>{{ english ? 'Standard protocol' : '标准协议' }} <small>{{ english ? 'Recommended' : '推荐' }}</small></span><code>{{ flow('standard') }}</code></a>
    <a :href="`#${protocols.anchors.simple}`"><span>{{ english ? 'Simple protocol' : '简单协议' }} <span aria-hidden="true">↗</span></span><code>{{ flow('simple') }}</code></a>
  </nav>
</template>
