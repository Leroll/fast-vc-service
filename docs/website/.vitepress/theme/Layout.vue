<script setup>
import DefaultTheme from 'vitepress/theme-without-fonts'
import { useData } from 'vitepress'
import { computed } from 'vue'
const { frontmatter, lang } = useData()
const english = computed(() => lang.value.startsWith('en'))
</script>

<template>
  <DefaultTheme.Layout>
    <template #nav-bar-title-before>
      <span class="brand-mark" aria-hidden="true"><i/><i/><i/><i/><i/></span>
    </template>
    <template #nav-bar-title-after><span class="brand-subtitle">{{ english ? 'Docs' : '文档' }}</span></template>
    <template #nav-bar-content-after>
      <a class="language-link" :href="frontmatter.translation || (english ? '/fast-vc-service/' : '/fast-vc-service/en/')" :lang="english ? 'zh-CN' : 'en'" :title="english ? '阅读简体中文文档' : frontmatter.translation ? 'Read this page in English' : '本页暂无英文译文，前往英文文档索引'">{{ english ? '中文' : 'EN' }}</a>
    </template>
    <template #doc-before>
      <div class="page-meta">
        <a class="version-label" href="https://github.com/Leroll/fast-vc-service/releases" :title="english ? 'Development documentation. Find release-specific docs on GitHub Releases.' : '当前为开发分支文档；已发布版本请从 GitHub Releases 阅读对应标签。'">{{ english ? 'Docs' : '文档' }} <span>main</span></a>
      </div>
      <p v-if="frontmatter.historical" class="history-note">{{ english ? 'Historical record. Read this page in the context of its date or version.' : '历史记录：请结合记录日期或对应版本阅读。' }}</p>
    </template>
    <template #home-hero-before>
      <div class="home-eyebrow"><span class="status-dot"/>{{ english ? 'REAL-TIME VOICE CONVERSION' : '实时流式语音转换' }}<a href="https://github.com/Leroll/fast-vc-service/releases">main <span aria-hidden="true">↗</span></a></div>
    </template>
  </DefaultTheme.Layout>
</template>
