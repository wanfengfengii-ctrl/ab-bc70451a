import type { RestoreRequestBody, RestoreResponse } from './types'

/** Call the real restoration API and surface backend validation messages. */
export async function restoreGrid(body: RestoreRequestBody): Promise<RestoreResponse> {
  let res: Response
  try {
    res = await fetch('/api/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new Error('无法连接复原服务，请确认后端已启动')
  }
  if (!res.ok) {
    let message = `复原请求失败（HTTP ${res.status}）`
    try {
      const data = await res.json()
      if (typeof data?.detail === 'string') {
        message = data.detail
      } else if (Array.isArray(data?.detail)) {
        message = data.detail
          .map((d: { msg?: string }) => d?.msg ?? '')
          .filter(Boolean)
          .join('；')
      }
    } catch {
      /* keep the default message */
    }
    throw new Error(message)
  }
  return (await res.json()) as RestoreResponse
}
