import { request } from '@/api/http'

export interface ModelRecord {
  id: string
  name: string
  provider: string
  model: string
  type: string
  base_url: string
  endpoint: string
  api_key: string
  temperature: number | null
  enabled: boolean
}

export interface ModelInput {
  name: string
  provider?: string
  model: string
  type?: string
  base_url?: string
  endpoint?: string
  api_key?: string
  temperature?: number | null
  enabled?: boolean
}

export function listModels() {
  return request<ModelRecord[]>('/api/v1/aigc/models')
}

export function createModel(payload: ModelInput) {
  return request<ModelRecord>('/api/v1/aigc/models', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateModel(id: string, payload: Partial<ModelInput>) {
  return request<ModelRecord>(`/api/v1/aigc/models/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteModel(id: string) {
  return request<null>(`/api/v1/aigc/models/${id}`, { method: 'DELETE' })
}
