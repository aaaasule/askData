import { loadSettings } from '@/settings'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function joinUrl(base: string, path: string): string {
  const trimmed = base.replace(/\/$/, '')
  return `${trimmed}${path}`
}

export function messageFromBody(text: string, fallback = '请求失败'): string {
  if (!text) return fallback
  try {
    const body = JSON.parse(text) as {
      detail?: unknown
      message?: unknown
    }
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) => {
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: unknown }).msg)
          }
          return String(item)
        })
        .join('；')
    }
    if (typeof body.message === 'string' && body.message) return body.message
  } catch {
    return text
  }
  return text
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const settings = loadSettings()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (settings.apiKey) {
    headers.set('Authorization', `Bearer ${settings.apiKey}`)
  }
  const response = await fetch(joinUrl(settings.baseUrl, path), { ...init, headers })
  const text = await response.text()
  if (response.status === 401) {
    throw new ApiError(401, 'API Key 无效或未填写，请到设置里更新')
  }
  if (!response.ok) {
    throw new ApiError(response.status, messageFromBody(text, `请求失败（${response.status}）`))
  }
  if (!text) return undefined as T
  const body = JSON.parse(text) as { code?: string; message?: string; data?: T }
  if (body && typeof body === 'object' && 'code' in body) {
    if (body.code !== 'SUCCESS') {
      throw new ApiError(response.status, body.message || body.code || '请求失败')
    }
    return body.data as T
  }
  return body as T
}
