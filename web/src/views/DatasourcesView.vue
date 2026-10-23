<script setup lang="ts">
import {
  NButton,
  NEmpty,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpin,
  NTag,
} from 'naive-ui'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  createDatasource,
  datasourceLocation,
  DB_TYPES,
  databasePlaceholder,
  deleteDatasource,
  listDatasources,
  testDatasource,
  testDatasourceBody,
  updateDatasource,
  type Datasource,
  type DatasourceInput,
} from '@/api/datasource'
import { notifyError, notifySuccess } from '@/feedback'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const items = ref<Datasource[]>([])
const showEditor = ref(false)
const editingId = ref<string | null>(null)

const form = reactive({
  name: '',
  db_type: 'sqlite',
  host: '',
  port: null as number | null,
  database: '',
  username: '',
  password: '',
  jdbc_url: '',
})

function resetForm() {
  form.name = ''
  form.db_type = 'sqlite'
  form.host = ''
  form.port = null
  form.database = ''
  form.username = ''
  form.password = ''
  form.jdbc_url = ''
}

function openCreate() {
  editingId.value = null
  resetForm()
  showEditor.value = true
}

function openEdit(item: Datasource) {
  editingId.value = item.id
  form.name = item.name
  form.db_type = item.db_type
  form.host = item.host || ''
  form.port = item.port
  form.database = item.database || ''
  form.username = item.username || ''
  form.password = ''
  form.jdbc_url = item.jdbc_url || ''
  showEditor.value = true
}

function payload(): DatasourceInput {
  const body: DatasourceInput = {
    name: form.name.trim(),
    db_type: form.db_type,
    host: form.host.trim(),
    port: form.port,
    database: form.database.trim(),
    username: form.username.trim(),
    jdbc_url: form.jdbc_url.trim() || null,
  }
  if (!editingId.value || form.password) body.password = form.password
  return body
}

async function load() {
  loading.value = true
  try {
    items.value = await listDatasources()
  } catch (error) {
    notifyError(error, '数据源列表加载失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.name.trim()) {
    notifyError(new Error('请填写名称'))
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateDatasource(editingId.value, payload())
      notifySuccess('已保存数据源')
    } else {
      await createDatasource(payload())
      notifySuccess('已创建数据源')
    }
    showEditor.value = false
    await load()
  } catch (error) {
    notifyError(error)
  } finally {
    saving.value = false
  }
}

async function testForm() {
  testing.value = true
  try {
    const result = editingId.value && !form.password
      ? await testDatasource(editingId.value)
      : await testDatasourceBody(payload())
    if (result.ok) {
      notifySuccess(result.message || `连接成功${result.latency_ms != null ? `（${result.latency_ms} ms）` : ''}`)
    } else {
      notifyError(new Error(result.message || '连接失败'))
    }
  } catch (error) {
    notifyError(error)
  } finally {
    testing.value = false
  }
}

async function testSaved(item: Datasource) {
  try {
    const result = await testDatasource(item.id)
    if (result.ok) notifySuccess(`${item.name} 连接成功`)
    else notifyError(new Error(result.message || '连接失败'))
  } catch (error) {
    notifyError(error)
  }
}

async function remove(item: Datasource) {
  if (!window.confirm(`删除数据源「${item.name}」？`)) return
  try {
    await deleteDatasource(item.id)
    notifySuccess('已删除')
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
        <p class="eyebrow">数据源</p>
        <h1>业务库连接</h1>
        <p class="lede">登记要问数的库，再在详情里勾选允许模型访问的表。</p>
      </div>
      <div class="head-actions">
        <NButton secondary @click="load">刷新</NButton>
        <NButton type="primary" @click="openCreate">新建数据源</NButton>
      </div>
    </header>

    <NSpin :show="loading">
      <div v-if="items.length" class="card-grid">
        <article v-for="item in items" :key="item.id" class="panel ds-card">
          <div class="ds-title">
            <h2>{{ item.name }}</h2>
            <NTag size="small" :bordered="false">{{ item.db_type }}</NTag>
          </div>
          <p class="muted">{{ datasourceLocation(item) }}</p>
          <p class="id-line">{{ item.id }}</p>
          <div class="row-actions">
            <NButton size="small" type="primary" @click="router.push(`/datasources/${item.id}`)">
              表授权
            </NButton>
            <NButton size="small" secondary @click="openEdit(item)">编辑</NButton>
            <NButton size="small" secondary @click="testSaved(item)">测试</NButton>
            <NButton size="small" quaternary type="error" @click="remove(item)">删除</NButton>
          </div>
        </article>
      </div>
      <NEmpty v-else class="empty" description="还没有数据源。先建一个 SQLite 文件或数据库连接。" />
    </NSpin>

    <NModal
      v-model:show="showEditor"
      preset="card"
      :title="editingId ? '编辑数据源' : '新建数据源'"
      style="width: min(640px, 94vw)"
    >
      <div class="form-grid">
        <label>名称<input v-model="form.name" /></label>
        <label>
          类型
          <NSelect v-model:value="form.db_type" :options="DB_TYPES" />
        </label>
        <label>主机<NInput v-model:value="form.host" placeholder="SQLite 可留空" /></label>
        <label>端口<NInputNumber v-model:value="form.port" :show-button="false" placeholder="可选" /></label>
        <label class="span-2">
          数据库
          <NInput
            v-model:value="form.database"
            :placeholder="databasePlaceholder(form.db_type)"
          />
        </label>
        <label>用户名<NInput v-model:value="form.username" /></label>
        <label>
          密码
          <NInput
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            :placeholder="editingId ? '留空则保持原密码' : '可空'"
          />
        </label>
        <label class="span-2">
          JDBC / SQLAlchemy URL（可选，主机和数据库都空时才使用）
          <NInput
            v-model:value="form.jdbc_url"
            placeholder="可选。例如 jdbc:oracle:thin:@//host:1521/FREEPDB1"
          />
        </label>
      </div>
      <div class="modal-actions">
        <NButton secondary :loading="testing" @click="testForm">测试连接</NButton>
        <NButton type="primary" :loading="saving" @click="save">保存</NButton>
      </div>
    </NModal>
  </section>
</template>
