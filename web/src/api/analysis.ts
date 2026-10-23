import { ApiError, joinUrl, messageFromBody, request } from '@/api/http'
import { loadSettings } from '@/settings'
import { parseSseBlock, type ParsedAnalysisEvent } from '@/sse'

export interface CatalogTable {
  name: string
  comment?: string | null
  imported?: boolean
  enabled?: boolean
  columns?: { name: string; type?: string; comment?: string | null }[]
}

export interface Catalog {
  datasourceId: string
  tables: CatalogTable[]
}

export interface AnalysisRequest {
  datasourceId: string
  question: string
  tableNames: string[]
  modelId?: string | null
  conversationId?: string | null
}

export function clearConversation(conversationId: string) {
  return request<null>(`/api/v1/core/data-analysis/conversations/${conversationId}`, {
    method: 'DELETE',
  })
}

export function getCatalog(datasourceId: string) {
  const query = new URLSearchParams({ datasourceId })
  return request<Catalog>(`/api/v1/core/data-analysis/catalog?${query.toString()}`)
}

export async function streamAnalysis(
  payload: AnalysisRequest,
  onEvent: (event: ParsedAnalysisEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const settings = loadSettings()
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
    'Content-Type': 'application/json',
  }
  if (settings.apiKey) headers.Authorization = `Bearer ${settings.apiKey}`
  const response = await fetch(joinUrl(settings.baseUrl, '/api/v1/core/data-analysis/chat/stream'), {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  })
  if (!response.ok || !response.body) {
    const text = await response.text()
    throw new ApiError(response.status, messageFromBody(text, `问数失败（${response.status}）`))
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const step = await reader.read()
    buffer += decoder.decode(step.value || new Uint8Array(), { stream: !step.done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const event = parseSseBlock(block)
      if (event) onEvent(event)
    }
    if (step.done) break
  }
  if (buffer.trim()) {
    const event = parseSseBlock(buffer)
    if (event) onEvent(event)
  }
}
