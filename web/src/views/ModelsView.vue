<script setup lang="ts">
import { NButton, NEmpty, NInput, NInputNumber, NModal, NSpin, NSwitch, NTag } from 'naive-ui'
import { onMounted, reactive, ref } from 'vue'

import { createModel, deleteModel, listModels, updateModel, type ModelRecord } from '@/api/models'
import { notifyError, notifySuccess } from '@/feedback'

const loading = ref(false)
const saving = ref(false)
const items = ref<ModelRecord[]>([])
const showEditor = ref(false)
const editingId = ref<string | null>(null)

const form = reactive({
  name: '',
  model: '',
  base_url: '',
  api_key: '',
  temperature: 0.2 as number | null,
  enabled: true,
})

function openCreate() {
  editingId.value = null
  form.name = ''
  form.model = ''
  form.base_url = ''
  form.api_key = ''
  form.temperature = 0.2
  form.enabled = true
  showEditor.value = true
}

function openEdit(item: ModelRecord) {
  editingId.value = item.id
  form.name = item.name
  form.model = item.model
  form.base_url = item.base_url || item.endpoint || ''
  form.api_key = ''
  form.temperature = item.temperature
  form.enabled = item.enabled
  showEditor.value = true
}

async function load() {
  loading.value = true
  try {
    items.value = await listModels()
  } catch (error) {
    notifyError(error, '模型列表加载失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.name.trim() || !form.model.trim()) {
    notifyError(new Error('名称和模型 ID 都要填'))
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      model: form.model.trim(),
      provider: 'openai-compatible',
      type: 'chat',
      base_url: form.base_url.trim(),
      temperature: form.temperature,
      enabled: form.enabled,
      ...(form.api_key.trim() ? { api_key: form.api_key.trim() } : {}),
    }
    if (editingId.value) await updateModel(editingId.value, payload)
    else await createModel({ ...payload, api_key: form.api_key.trim() })
    showEditor.value = false
    notifySuccess('模型已保存')
    await load()
  } catch (error) {
    notifyError(error)
  } finally {
    saving.value = false
  }
}

async function remove(item: ModelRecord) {
  if (!window.confirm(`删除模型「${item.name}」？`)) return
  try {
    await deleteModel(item.id)
    notifySuccess('已删除模型')
    await load()
  } catch (error) {
    notifyError(error)
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div>
        <p class="eyebrow">模型</p>
        <h1>对话模型</h1>
        <p class="lede">只登记问数要用的 OpenAI 兼容模型。列表里的密钥是掩码，留空保存不会覆盖原密钥。</p>
      </div>
      <div class="head-actions">
        <NButton secondary @click="load">刷新</NButton>
        <NButton type="primary" @click="openCreate">新建模型</NButton>
      </div>
    </header>

    <NSpin :show="loading">
      <div v-if="items.length" class="card-grid">
        <article v-for="item in items" :key="item.id" class="panel ds-card">
          <div class="ds-title">
            <h2>{{ item.name }}</h2>
            <NTag size="small" :bordered="false" :type="item.enabled ? 'success' : 'default'">
              {{ item.enabled ? '启用' : '停用' }}
            </NTag>
          </div>
          <p>{{ item.model }}</p>
          <p class="muted">{{ item.base_url || item.endpoint || '未填 base_url' }}</p>
          <p class="id-line">{{ item.api_key || '无密钥' }}</p>
          <div class="row-actions">
            <NButton size="small" secondary @click="openEdit(item)">编辑</NButton>
            <NButton size="small" quaternary type="error" @click="remove(item)">删除</NButton>
          </div>
        </article>
      </div>
      <NEmpty v-else class="empty" description="还没有模型。也可以只配环境变量里的默认模型，问数时不选 modelId。" />
    </NSpin>

    <NModal
      v-model:show="showEditor"
      preset="card"
      :title="editingId ? '编辑模型' : '新建模型'"
      style="width: min(560px, 94vw)"
    >
      <div class="form-grid">
        <label>名称<input v-model="form.name" /></label>
        <label>模型 ID<input v-model="form.model" placeholder="gpt-4o-mini" /></label>
        <label class="span-2">
          Base URL
          <NInput v-model:value="form.base_url" placeholder="https://api.openai.com/v1" />
        </label>
        <label class="span-2">
          API Key
          <NInput
            v-model:value="form.api_key"
            type="password"
            show-password-on="click"
            :placeholder="editingId ? '留空则不修改' : '供应商密钥'"
          />
        </label>
        <label>温度<NInputNumber v-model:value="form.temperature" :min="0" :max="2" :step="0.1" /></label>
        <label class="switch-label">启用<NSwitch v-model:value="form.enabled" /></label>
      </div>
      <div class="modal-actions">
        <NButton type="primary" :loading="saving" @click="save">保存</NButton>
      </div>
    </NModal>
  </section>
</template>
