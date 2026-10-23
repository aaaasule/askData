export interface TableResult {
  title: string
  columns: string[]
  rows: unknown[][]
  rowCount: number
  sql: string
}

export interface ChartResult {
  title: string
  chartType: string
  option: Record<string, unknown>
}

export type ParsedAnalysisEvent =
  | { type: 'text'; content: string }
  | { type: 'table'; result: TableResult }
  | { type: 'chart'; result: ChartResult }
  | { type: 'tool'; name: string; phase: 'before' | 'executed'; status: string; failed: boolean }
  | { type: 'log'; content: string }
  | { type: 'error'; message: string }
  | { type: 'done' }
  | { type: 'ignore' }

interface DeltaEvent {
  name?: string
  columns?: unknown
  rows?: unknown
  row_count?: unknown
  sql?: unknown
  title?: unknown
  chart_type?: unknown
  option?: unknown
  tool_name?: unknown
  status?: unknown
  failed?: unknown
  message?: unknown
}

export function parseSseBlock(block: string): ParsedAnalysisEvent | null {
  const dataText = block
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('')
  if (!dataText) return null
  if (dataText === '[DONE]') return { type: 'done' }
  let chunk: {
    choices?: { delta?: { content?: string; event?: DeltaEvent }; finish_reason?: string | null }[]
  }
  try {
    chunk = JSON.parse(dataText) as typeof chunk
  } catch {
    return null
  }
  const delta = chunk.choices?.[0]?.delta
  const event = delta?.event
  const name = event?.name || ''
  if ((name === 'message.delta' || (!name && delta?.content)) && delta?.content) {
    return { type: 'text', content: delta.content }
  }
  if (name === 'log.delta' && delta?.content) {
    return { type: 'log', content: delta.content }
  }
  if (name === 'analysis.table' && event) {
    return {
      type: 'table',
      result: {
        title: String(event.title || '查询结果'),
        columns: toStringArray(event.columns),
        rows: toMatrix(event.rows),
        rowCount: Number(event.row_count || 0),
        sql: String(event.sql || ''),
      },
    }
  }
  if (name === 'analysis.echart' && event) {
    const option = sanitizeEchartOption(event.option)
    if (!option) return { type: 'error', message: '图表配置无效' }
    return {
      type: 'chart',
      result: {
        title: String(event.title || '图表'),
        chartType: String(event.chart_type || 'auto'),
        option,
      },
    }
  }
  if (name === 'tool.before' || name === 'tool.executed') {
    return {
      type: 'tool',
      name: String(event?.tool_name || ''),
      phase: name === 'tool.before' ? 'before' : 'executed',
      status: String(event?.status || ''),
      failed: Boolean(event?.failed),
    }
  }
  if (name === 'error' || name === 'timeout') {
    return { type: 'error', message: String(event?.message || name) }
  }
  return { type: 'ignore' }
}

export function sanitizeEchartOption(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  try {
    const serialized = JSON.stringify(value, (key, item) => {
      if (key === '__proto__' || key === 'constructor' || key === 'prototype') return undefined
      return typeof item === 'function' ? undefined : item
    })
    const parsed = JSON.parse(serialized) as Record<string, unknown>
    return Array.isArray(parsed.series) && parsed.series.length > 0 ? parsed : null
  } catch {
    return null
  }
}

export function toolLabel(name: string): string {
  if (name === 'query_data') return '查询数据'
  if (name === 'inspect_selected_tables') return '查看表结构'
  if (name === 'get_current_time') return '当前时间'
  return name || '工具'
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : []
}

function toMatrix(value: unknown): unknown[][] {
  if (!Array.isArray(value)) return []
  return value.map((row) => (Array.isArray(row) ? row : []))
}
