<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import { loadSettings } from '@/settings'

const route = useRoute()
const keyHint = computed(() => {
  const key = loadSettings().apiKey
  if (!key) return '未设置 API Key'
  return `Key ${key.slice(0, 3)}…`
})

const links = [
  { to: '/datasources', label: '数据源', hint: '连接与授权' },
  { to: '/analysis', label: '问数', hint: '自然语言查询' },
  { to: '/models', label: '模型', hint: '对话模型' },
  { to: '/settings', label: '设置', hint: 'API Key' },
]
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="brand">
        <span class="mark">问</span>
        <div>
          <strong>AskData</strong>
          <small>调研问数</small>
        </div>
      </div>
      <nav>
        <RouterLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          :class="{ active: route.path === link.to || route.path.startsWith(link.to + '/') }"
        >
          <span>{{ link.label }}</span>
          <small>{{ link.hint }}</small>
        </RouterLink>
      </nav>
      <p class="side-foot">{{ keyHint }} · 仅保存在本机浏览器</p>
    </aside>
    <div class="workspace">
      <RouterView />
    </div>
  </div>
</template>
