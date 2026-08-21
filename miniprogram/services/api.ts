import { ClientAPIError, getApiBaseUrl, request } from './http'
import { getAccessToken } from '../store/session'
import type {
  Food,
  FoodList,
  FoodManualCreate,
  FoodPatch,
  FreshnessBucket,
  ImagePurpose,
  ScanFinalizeInput,
  ScanFinalizeResponse,
  ScanFrame,
  ScanSession,
  ScanSessionCreate,
  SubscriptionOutcomes,
} from '../types/api'

function bearerHeader(extra: Record<string, string> = {}): Record<string, string> {
  const token = getAccessToken()
  return token ? { Authorization: `Bearer ${token}`, ...extra } : extra
}

export function listFoods(bucket?: FreshnessBucket): Promise<FoodList> {
  const query = bucket ? `?bucket=${encodeURIComponent(bucket)}` : ''
  return request({ method: 'GET', path: `/foods${query}` })
}

export function getFood(foodId: number): Promise<Food> {
  return request({ method: 'GET', path: `/foods/${foodId}` })
}

export function createManualFood(payload: FoodManualCreate, idempotencyKey: string): Promise<Food> {
  return request({ method: 'POST', path: '/foods/manual', data: payload, idempotencyKey })
}

export function updateFood(foodId: number, payload: FoodPatch): Promise<Food> {
  return request({ method: 'PUT', path: `/foods/${foodId}`, data: payload })
}

export function deleteFood(foodId: number, idempotencyKey: string): Promise<void> {
  return request({ method: 'DELETE', path: `/foods/${foodId}`, idempotencyKey })
}

const thumbnailPaths = new Map<string, string>()

export function downloadFoodThumbnail(foodId: number): Promise<string> {
  const cacheKey = `${getAccessToken() ?? 'anonymous'}:${foodId}`
  const cached = thumbnailPaths.get(cacheKey)
  if (cached) return Promise.resolve(cached)
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: `${getApiBaseUrl()}/foods/${foodId}/thumbnail`,
      header: bearerHeader(),
      success(result) {
        if (result.statusCode >= 200 && result.statusCode < 300) {
          thumbnailPaths.set(cacheKey, result.tempFilePath)
          resolve(result.tempFilePath)
          return
        }
        reject(new ClientAPIError('thumbnail_unavailable', '食品图片暂时无法加载', true, result.statusCode))
      },
      fail() {
        reject(new ClientAPIError('network_unavailable', '网络连接不稳定，请稍后再试', true, 0))
      },
    })
  })
}

export function createScanSession(payload: ScanSessionCreate = {}): Promise<ScanSession> {
  return request({ method: 'POST', path: '/scan-sessions', data: payload })
}

export function getScanSession(scanSessionId: string): Promise<ScanSession> {
  return request({ method: 'GET', path: `/scan-sessions/${scanSessionId}` })
}

export function cancelScanSession(scanSessionId: string): Promise<ScanSession> {
  return request({ method: 'POST', path: `/scan-sessions/${scanSessionId}/cancel`, data: {} })
}

export function uploadFrame(
  scanSessionId: string,
  filePath: string,
  purpose: ImagePurpose,
  idempotencyKey: string,
): Promise<ScanFrame> {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${getApiBaseUrl()}/scan-sessions/${scanSessionId}/frames`,
      filePath,
      name: 'image',
      formData: { purpose },
      header: bearerHeader({ 'Idempotency-Key': idempotencyKey }),
      success(result) {
        let data: unknown
        try {
          data = JSON.parse(result.data)
        } catch {
          reject(new ClientAPIError('invalid_response', '识别服务返回了无效结果', true, result.statusCode))
          return
        }
        if (result.statusCode >= 200 && result.statusCode < 300) {
          resolve(data as ScanFrame)
          return
        }
        const error = data as { error?: { code?: string; message?: string; retryable?: boolean } }
        reject(new ClientAPIError(
          error.error?.code ?? 'frame_upload_failed',
          error.error?.message ?? '关键画面上传失败',
          error.error?.retryable ?? result.statusCode >= 500,
          result.statusCode,
        ))
      },
      fail() {
        reject(new ClientAPIError('network_unavailable', '网络连接不稳定，请稍后再试', true, 0))
      },
    })
  })
}

export function finalizeScan(
  scanSessionId: string,
  payload: ScanFinalizeInput,
  idempotencyKey: string,
): Promise<ScanFinalizeResponse> {
  return request({
    method: 'POST',
    path: `/scan-sessions/${scanSessionId}/finalize`,
    data: payload,
    idempotencyKey,
  })
}

export function recordReminderSubscription(
  foodId: number,
  outcomes: SubscriptionOutcomes,
): Promise<void> {
  return request({
    method: 'POST',
    path: `/foods/${foodId}/reminder-subscription`,
    data: { outcomes },
  })
}
