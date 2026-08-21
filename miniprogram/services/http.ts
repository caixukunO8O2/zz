import { getAccessToken } from '../store/session'
import type { BackendErrorEnvelope } from '../types/api'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE'

export interface RequestOptions {
  method: HttpMethod
  path: string
  data?: WechatMiniprogram.IAnyObject | string | ArrayBuffer
  idempotencyKey?: string
  authenticated?: boolean
  retryOnUnauthorized?: boolean
  timeout?: number
}

export class ClientAPIError extends Error {
  readonly code: string
  readonly retryable: boolean
  readonly statusCode: number

  constructor(code: string, message: string, retryable: boolean, statusCode: number) {
    super(message)
    this.name = 'ClientAPIError'
    this.code = code
    this.retryable = retryable
    this.statusCode = statusCode
  }
}

let apiBaseUrl = 'http://127.0.0.1:8000/api/v1'
let unauthorizedHandler: (() => Promise<unknown>) | undefined

export function setApiBaseUrl(value: string): void {
  apiBaseUrl = value.replace(/\/$/, '')
}

export function getApiBaseUrl(): string {
  return apiBaseUrl
}

export function setUnauthorizedHandler(handler: (() => Promise<unknown>) | undefined): void {
  unauthorizedHandler = handler
}

function backendError(statusCode: number, data: unknown): ClientAPIError {
  const envelope = data as BackendErrorEnvelope
  return new ClientAPIError(
    envelope.error?.code ?? 'request_failed',
    envelope.error?.message ?? '请求暂时没有完成，请稍后再试',
    envelope.error?.retryable ?? statusCode >= 500,
    statusCode,
  )
}

function send<T>(options: RequestOptions): Promise<T> {
  const token = options.authenticated === false ? null : getAccessToken()
  const header: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) header.Authorization = `Bearer ${token}`
  if (options.idempotencyKey) header['Idempotency-Key'] = options.idempotencyKey

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBaseUrl}${options.path}`,
      method: options.method,
      data: options.data,
      header,
      timeout: options.timeout ?? 10_000,
      success(result) {
        if (result.statusCode >= 200 && result.statusCode < 300) {
          resolve(result.data as T)
          return
        }
        reject(backendError(result.statusCode, result.data))
      },
      fail() {
        reject(new ClientAPIError('network_unavailable', '网络连接不稳定，请稍后再试', true, 0))
      },
    })
  })
}

export async function request<T>(options: RequestOptions): Promise<T> {
  const handler = unauthorizedHandler
  if (options.authenticated !== false && !getAccessToken() && handler) {
    await handler()
  }

  try {
    return await send<T>(options)
  } catch (error) {
    const shouldRetry =
      error instanceof ClientAPIError &&
      error.statusCode === 401 &&
      options.retryOnUnauthorized !== false &&
      handler
    if (!shouldRetry) throw error
    await handler()
    return send<T>({ ...options, retryOnUnauthorized: false })
  }
}
