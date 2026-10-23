<script setup lang="ts">
import { NButton, NInput } from 'naive-ui'
import { reactive } from 'vue'

import { notifySuccess } from '@/feedback'
import { loadSettings, saveSettings } from '@/settings'

const form = reactive(loadSettings())

function save() {
  saveSettings({ apiKey: form.apiKey, baseUrl: form.baseUrl })
  form.apiKey = loadSettings().apiKey
  form.baseUrl = loadSettings().baseUrl
  notifySuccess('已写入本机浏览器')
}
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div>
        <p class="eyebrow">设置</p>
        <h1>连接这套 AskData 服务</h1>
        <p class="lede">
          API Key 放在 localStorage，请求头用 <code>Authorization: Bearer</code>。
          开发时 <code>npm run dev</code> 会把 <code>/api</code> 代理到 8000 端口，Base URL 留空即可。
        </p>
      </div>
    </header>
    <form class="panel settings-form" @submit.prevent="save">
      <label>
        API Key
        <NInput v-model:value="form.apiKey" type="password" show-password-on="click" placeholder="与 .env 里的 API_KEY 一致" />
      </label>
      <label>
        API Base URL
        <NInput v-model:value="form.baseUrl" placeholder="留空表示当前站点，例如 http://127.0.0.1:8000" />
      </label>
      <div class="row-actions">
        <NButton attr-type="submit" type="primary">保存</NButton>
        <a class="text-link" href="/docs">打开接口文档</a>
        <a class="text-link" href="/demo/">打开静态演示</a>
      </div>
    </form>
  </section>
</template>
