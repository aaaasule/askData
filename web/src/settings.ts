const STORAGE_KEY = 'askdata.web.settings'

export interface ClientSettings {
  apiKey: string
  baseUrl: string
}

const DEFAULTS: ClientSettings = {
  apiKey: 'change-me',
  baseUrl: '',
}

export function loadSettings(): ClientSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULTS }
    const parsed = JSON.parse(raw) as Partial<ClientSettings>
    return {
      apiKey: typeof parsed.apiKey === 'string' ? parsed.apiKey : DEFAULTS.apiKey,
      baseUrl: typeof parsed.baseUrl === 'string' ? parsed.baseUrl : '',
    }
  } catch {
    return { ...DEFAULTS }
  }
}

export function saveSettings(next: ClientSettings): void {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      apiKey: next.apiKey.trim(),
      baseUrl: next.baseUrl.trim().replace(/\/$/, ''),
    }),
  )
}
