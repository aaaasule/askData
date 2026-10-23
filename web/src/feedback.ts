import { createDiscreteApi } from 'naive-ui'

const { message } = createDiscreteApi(['message'])

export function notifySuccess(text: string) {
  message.success(text)
}

export function notifyError(error: unknown, fallback = '操作失败') {
  const text = error instanceof Error ? error.message : fallback
  message.error(text || fallback)
}
