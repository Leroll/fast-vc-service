<script setup>
import { computed, ref } from 'vue'
import { useData } from 'vitepress'
const props = defineProps({ protocol: { type: String, required: true } })
const { frontmatter, lang } = useData()
const english = computed(() => lang.value.startsWith('en'))
const data = computed(() => frontmatter.value.protocols[props.protocol])
const status = ref('')
async function copy() {
  try { await navigator.clipboard.writeText(data.value.sample); status.value = english.value ? 'Copied' : '已复制' }
  catch { status.value = english.value ? 'Select and copy the example below' : '请选中下方示例复制' }
}
</script>

<template>
  <div class="api-parameters">
    <dl class="field-list">
      <div v-for="field in data.fields" :key="field.name" class="field">
        <dt><span v-html="field.name"/><span class="field-type" v-html="field.type"/></dt>
        <dd class="field-constraint"><span v-html="field.required"/><span>{{ english ? 'Default' : '默认' }} <span v-html="field.default"/></span></dd>
        <dd class="field-description" v-html="field.description"/>
      </div>
    </dl>
    <div class="request-example">
      <div class="example-heading"><span>{{ english ? 'Initialization message' : '初始化消息' }}</span><button type="button" @click="copy" :aria-label="english ? 'Copy initialization message' : '复制初始化消息'">{{ english ? 'Copy' : '复制' }}</button></div>
      <div class="example-kind">{{ protocol === 'standard' ? 'type: config' : 'signal: start' }}<span>JSON</span></div>
      <pre tabindex="0"><code>{{ data.sample }}</code></pre>
      <p class="copy-status" aria-live="polite">{{ status }}</p>
    </div>
  </div>
</template>
