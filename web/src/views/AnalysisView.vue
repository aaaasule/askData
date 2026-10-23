<script setup lang="ts">
import { NButton, NEmpty, NSelect, NSpin } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'

import { getCatalog, streamAnalysis, type CatalogTable } from '@/api/analysis'
import { listDatasources, type Datasource } from '@/api/datasource'
import { listModels, type ModelRecord } from '@/api/models'
import ChartPanel from '@/components/ChartPanel.vue'
import { notifyError } from '@/feedback'
import { toolLabel, type ChartResult, type TableResult } from '@/sse'

interface Turn {
  id: string
  question: string
  text: string
  logs: string[]
  tools: string[]
  tables: TableResult[]
  charts: ChartResult[]
  error: string
  pending: boolean
}

const loading = ref(false)
const asking = ref(false)
const datasources = ref<Datasource[]>([])
const models = ref<ModelRecord[]>([])
const tables = ref<CatalogTable[]>([])
const datasourceId = ref<string | null>(null)
const modelId = ref('')
const selectedTables = ref<string[]>([])
const question = ref('每个客户的订单金额合计是多少？')
const turns = ref<Turn[]>([])
let abort: AbortController | null = null

const datasourceOptions = computed(() =>
  datasources.value.map((item) => ({ label: `${item.name} · ${item.db_type}`, value: item.id })),
)
const modelOptions = computed(() => [
  { label: '默认（已启用模型或环境变量）', value: '' },
  ...models.value.map((item) => ({
    label: `${item.name} · ${item.model}${item.enabled ? '' : '（停用）'}`,
    value: item.id,
  })),
])

async function loadBase() {
  loading.value = true
  try {
    const [sourceRows, modelRows] = await Promise.all([listDatasources(), listModels()])
    datasources.value = sourceRows
    models.value = modelRows
    if (!datasourceId.value && sourceRows[0]) {
      datasourceId.value = sourceRows[0].id
      await loadCatalog()
    }
  } catch (error) {
    notifyError(error, '问数页加载失败')
  } finally {
    loading.value = false
  }
}

function onDatasourceChange(id: string) {
  datasourceId.value = id
  void loadCatalog()
}

async function loadCatalog() {
  tables.value = []
  selectedTables.value = []
  if (!datasourceId.value) return
  try {
    const catalog = await getCatalog(datasourceId.value)
    tables.value = catalog.tables || []
    selectedTables.value = tables.value.map((table) => table.name)
  } catch (error) {
    notifyError(error, '目录加载失败')
  }
}

function stop() {
  abort?.abort()
  abort = null
  asking.value = false
}

async function ask() {
  if (!datasourceId.value) {
    notifyError(new Error('请先选择数据源'))
    return
  }
  const text = question.value.trim()
  if (!text) return
  const turn: Turn = {
    id: `${Date.now()}`,
    question: text,
    text: '',
    logs: [],
    tools: [],
    tables: [],
    charts: [],
    error: '',
    pending: true,
  }
  turns.value = [...turns.value, turn]
  asking.value = true
  abort = new AbortController()
  try {
    await streamAnalysis(
      {
        datasourceId: datasourceId.value,
        question: text,
        tableNames: selectedTables.value,
        modelId: modelId.value || null,
        conversationId: null,
      },
      (event) => {
        if (event.type === 'text') turn.text += event.content
        else if (event.type === 'log') turn.logs.push(event.content)
        else if (event.type === 'table') turn.tables.push(event.result)
        else if (event.type === 'chart') turn.charts.push(event.result)
        else if (event.type === 'tool') {
          const label = toolLabel(event.name)
          const line = event.phase === 'before' ? `${label}…` : `${label}${event.failed ? '失败' : '完成'}`
          turn.tools.push(line)
        } else if (event.type === 'error') turn.error = event.message
      },
      abort.signal,
    )
  } catch (error) {
    if ((error as Error).name !== 'AbortError') {
      turn.error = error instanceof Error ? error.message : '问数失败'
    }
  } finally {
    turn.pending = false
    asking.value = false
    abort = null
  }
}

onMounted(loadBase)
</script>

<template>
  <section class="page analysis-page">
    <header class="page-head">
      <div>
        <p class="eyebrow">问数</p>
        <h1>用自然语言查已授权的表</h1>
        <p class="lede">结果按 SSE 事件拆开：文本、表格和图表。服务端不保存多轮历史，本页只留这次打开的记录。</p>
      </div>
    </header>

    <NSpin :show="loading">
      <div class="analysis-grid">
        <form class="panel ask-panel" @submit.prevent="ask">
          <label>
            数据源
            <NSelect
              v-model:value="datasourceId"
              :options="datasourceOptions"
              placeholder="选择数据源"
              @update:value="onDatasourceChange"
            />
          </label>
          <label>
            模型
            <NSelect v-model:value="modelId" :options="modelOptions" placeholder="默认模型" />
          </label>
          <fieldset>
            <legend>本次使用的表</legend>
            <p v-if="!tables.length" class="muted">目录是空的。到数据源详情里导入并启用表，然后保存授权。</p>
            <label v-for="table in tables" :key="table.name" class="check">
              <input v-model="selectedTables" type="checkbox" :value="table.name" />
              <span>
                {{ table.name }}
                <small>{{ table.comment }}</small>
              </span>
            </label>
          </fieldset>
          <label>
            问题
            <textarea v-model="question" rows="4" />
          </label>
          <div class="row-actions">
            <NButton attr-type="submit" type="primary" :loading="asking" :disabled="!datasourceId">提问</NButton>
            <NButton v-if="asking" secondary @click="stop">停止</NButton>
          </div>
        </form>

        <div class="thread">
          <NEmpty v-if="!turns.length" description="提问后，这里会显示回答、结果表和图表。" />
          <article v-for="turn in turns" :key="turn.id" class="panel turn">
            <h2>{{ turn.question }}</h2>
            <p v-if="turn.pending && !turn.text" class="muted">正在生成…</p>
            <p v-if="turn.text" class="answer">{{ turn.text }}</p>
            <ul v-if="turn.tools.length" class="tools">
              <li v-for="(tool, index) in turn.tools" :key="index">{{ tool }}</li>
            </ul>
            <p v-if="turn.error" class="error">{{ turn.error }}</p>
            <div v-for="(table, index) in turn.tables" :key="`t-${index}`" class="result-block">
              <h3>{{ table.title }} <small>{{ table.rowCount }} 行</small></h3>
              <pre v-if="table.sql">{{ table.sql }}</pre>
              <div class="table-scroll">
                <table class="data">
                  <thead>
                    <tr>
                      <th v-for="column in table.columns" :key="column">{{ column }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, rowIndex) in table.rows" :key="rowIndex">
                      <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell ?? '' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <ChartPanel
              v-for="(chart, index) in turn.charts"
              :key="`c-${index}`"
              :title="chart.title"
              :option="chart.option"
            />
          </article>
        </div>
      </div>
    </NSpin>
  </section>
</template>
