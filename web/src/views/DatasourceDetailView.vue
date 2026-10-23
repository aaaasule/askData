<script setup lang="ts">
import { NButton, NEmpty, NSpin, NSwitch, NTag } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  getDatasource,
  getStructure,
  introspectDatasource,
  mergeLiveTables,
  saveStructure,
  testDatasource,
  toAuthTables,
  toStructureDoc,
  type AuthTable,
  type Datasource,
} from '@/api/datasource'
import { notifyError, notifySuccess } from '@/feedback'

const route = useRoute()
const router = useRouter()
const datasourceId = computed(() => String(route.params.id || ''))

const loading = ref(false)
const busy = ref(false)
const datasource = ref<Datasource | null>(null)
const tables = ref<AuthTable[]>([])
const hadSavedStructure = ref(false)
const selected = ref('')

const selectedTable = computed(() => tables.value.find((table) => table.name === selected.value) || null)
const importedCount = computed(() => tables.value.filter((table) => table.imported).length)
const enabledCount = computed(() => tables.value.filter((table) => table.imported && table.enabled).length)

function keepSelection() {
  if (!tables.value.some((table) => table.name === selected.value)) {
    selected.value = tables.value[0]?.name || ''
  }
}

async function load() {
  loading.value = true
  try {
    datasource.value = await getDatasource(datasourceId.value)
    const saved = await getStructure(datasourceId.value)
    hadSavedStructure.value = Boolean(saved && Array.isArray(saved.tables))
    tables.value = toAuthTables(saved)
    keepSelection()
  } catch (error) {
    notifyError(error, '数据源加载失败')
  } finally {
    loading.value = false
  }
}

async function persist(quiet = false) {
  const saved = await saveStructure(datasourceId.value, toStructureDoc(tables.value))
  tables.value = toAuthTables(saved)
  hadSavedStructure.value = true
  keepSelection()
  if (!quiet) notifySuccess('表授权已保存')
}

async function refreshSchema() {
  busy.value = true
  const prior = tables.value.map((table) => ({ ...table, columns: [...table.columns] }))
  const preserve = hadSavedStructure.value
  try {
    const live = await introspectDatasource(datasourceId.value)
    tables.value = mergeLiveTables(live, prior, preserve)
    keepSelection()
    if (preserve) {
      await persist(true)
      notifySuccess('已刷新表结构，并保留原来的导入/启用标记')
    } else {
      notifySuccess('已读取库表。未勾选的表不会进入问数目录，确认后请保存授权。')
    }
  } catch (error) {
    notifyError(error, '读取库表失败')
  } finally {
    busy.value = false
  }
}

async function saveClick() {
  busy.value = true
  try {
    await persist()
  } catch (error) {
    notifyError(error)
  } finally {
    busy.value = false
  }
}

async function testConnection() {
  try {
    const result = await testDatasource(datasourceId.value)
    if (result.ok) notifySuccess(result.message || '连接成功')
    else notifyError(new Error(result.message || '连接失败'))
  } catch (error) {
    notifyError(error)
  }
}

function onImported(table: AuthTable, event: Event) {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) return
  toggleImported(table, input.checked)
}

function toggleImported(table: AuthTable, imported: boolean) {
  table.imported = imported
  if (!imported) table.enabled = false
  if (imported && !table.enabled) table.enabled = true
}

onMounted(load)
</script>

<template>
  <section class="page">
    <header class="page-head">
      <div>
        <button class="text-link" type="button" @click="router.push('/datasources')">返回列表</button>
        <h1>{{ datasource?.name || '数据源' }}</h1>
        <p class="lede">
          <NTag v-if="datasource" size="small" :bordered="false">{{ datasource.db_type }}</NTag>
          内省只负责读出库里的表。问数目录只包含「已导入且已启用」的表，保存走
          <code>PUT /structure</code>，不会改连接信息。
        </p>
      </div>
      <div class="head-actions">
        <NButton secondary @click="testConnection">测试连接</NButton>
        <NButton secondary :loading="busy" @click="refreshSchema">读取库表</NButton>
        <NButton type="primary" :loading="busy" @click="saveClick">保存授权</NButton>
      </div>
    </header>

    <NSpin :show="loading">
      <p class="stat-line">已导入 {{ importedCount }} 张 · 问数可用 {{ enabledCount }} 张</p>
      <div v-if="tables.length" class="split">
        <aside class="panel table-list">
          <button
            v-for="table in tables"
            :key="table.name"
            type="button"
            class="table-row"
            :class="{ selected: table.name === selected }"
            @click="selected = table.name"
          >
            <span>
              <strong>{{ table.name }}</strong>
              <small>{{ table.comment || '无注释' }}</small>
            </span>
            <span class="flags">
              <label @click.stop>
                <input
                  type="checkbox"
                  :checked="table.imported"
                  @change="onImported(table, $event)"
                />
                导入
              </label>
              <label @click.stop>
                <NSwitch v-model:value="table.enabled" size="small" :disabled="!table.imported" />
                启用
              </label>
            </span>
          </button>
        </aside>
        <div class="panel">
          <template v-if="selectedTable">
            <h2>{{ selectedTable.name }}</h2>
            <p class="muted">{{ selectedTable.comment || '这张表没有注释' }}</p>
            <table class="data">
              <thead>
                <tr>
                  <th>列</th>
                  <th>类型</th>
                  <th>可空</th>
                  <th>注释</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="column in selectedTable.columns" :key="column.name">
                  <td>{{ column.name }}</td>
                  <td>{{ column.type || '—' }}</td>
                  <td>{{ column.nullable === false ? '否' : '是' }}</td>
                  <td>{{ column.comment || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </template>
          <NEmpty v-else description="选择一张表查看字段" />
        </div>
      </div>
      <NEmpty v-else class="empty" description="还没有表结构。点击「读取库表」从业务库内省。" />
    </NSpin>
  </section>
</template>
