import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelScanSession,
  createManualFood,
  createScanSession,
  deleteFood,
  downloadFoodThumbnail,
  finalizeScan,
  getFood,
  getScanSession,
  listFoods,
  recordReminderSubscription,
  updateFood,
  uploadFrame,
} from '../services/api'
import { setApiBaseUrl } from '../services/http'
import { clearSession, setSession } from '../store/session'

describe('typed backend API', () => {
  const requestCalls: WechatMiniprogram.RequestOption[] = []

  beforeEach(() => {
    requestCalls.length = 0
    clearSession()
    setApiBaseUrl('http://127.0.0.1:8000/api/v1')
    vi.stubGlobal('wx', {
      getStorageSync: vi.fn(() => ''),
      setStorageSync: vi.fn(),
      removeStorageSync: vi.fn(),
      request: vi.fn((options: WechatMiniprogram.RequestOption) => {
        requestCalls.push(options)
        options.success?.({ statusCode: 200, data: { items: [] } } as unknown as WechatMiniprogram.RequestSuccessCallbackResult)
        return {} as WechatMiniprogram.RequestTask
      }),
      downloadFile: vi.fn((options: WechatMiniprogram.DownloadFileOption) => {
        options.success?.({ statusCode: 200, tempFilePath: 'wxfile://milk.jpg', filePath: '', profile: {} } as WechatMiniprogram.DownloadFileSuccessCallbackResult)
        return {} as WechatMiniprogram.DownloadTask
      }),
      uploadFile: vi.fn((options: WechatMiniprogram.UploadFileOption) => {
        options.success?.({ statusCode: 202, data: JSON.stringify({ id: 4, purpose: 'identity', analysis_status: 'queued', duplicate: false }) } as WechatMiniprogram.UploadFileSuccessCallbackResult)
        return {} as WechatMiniprogram.UploadTask
      }),
    })
    setSession({ accessToken: 'token-1', expiresAt: Date.now() + 60_000 })
  })

  it('maps food operations to their authenticated routes', async () => {
    await listFoods('urgent')
    await getFood(7)
    await createManualFood({
      food_name: '草莓',
      storage_type: 'chilled',
      added_on: '2026-08-21',
      recommended_consume_by: '2026-08-23',
    }, 'create-7')
    await updateFood(7, { storage_type: 'frozen' })
    await deleteFood(7, 'delete-7')

    expect(requestCalls.map(({ method, url }) => [method, url])).toEqual([
      ['GET', 'http://127.0.0.1:8000/api/v1/foods?bucket=urgent'],
      ['GET', 'http://127.0.0.1:8000/api/v1/foods/7'],
      ['POST', 'http://127.0.0.1:8000/api/v1/foods/manual'],
      ['PUT', 'http://127.0.0.1:8000/api/v1/foods/7'],
      ['DELETE', 'http://127.0.0.1:8000/api/v1/foods/7'],
    ])
    expect(requestCalls[2]?.header).toMatchObject({ 'Idempotency-Key': 'create-7' })
    expect(requestCalls[4]?.header).toMatchObject({ 'Idempotency-Key': 'delete-7' })
  })

  it('maps scan lifecycle operations without creating alternate routes', async () => {
    await createScanSession({ mock_scenario: 'packaged_success' })
    await getScanSession('scan-1')
    await cancelScanSession('scan-1')
    await finalizeScan('scan-1', { food_name: '鲜牛奶' }, 'finalize-1')

    expect(requestCalls.map(({ method, url }) => [method, url])).toEqual([
      ['POST', 'http://127.0.0.1:8000/api/v1/scan-sessions'],
      ['GET', 'http://127.0.0.1:8000/api/v1/scan-sessions/scan-1'],
      ['POST', 'http://127.0.0.1:8000/api/v1/scan-sessions/scan-1/cancel'],
      ['POST', 'http://127.0.0.1:8000/api/v1/scan-sessions/scan-1/finalize'],
    ])
    expect(requestCalls[3]?.header).toMatchObject({ 'Idempotency-Key': 'finalize-1' })
  })

  it('uses authenticated download and multipart upload boundaries', async () => {
    await expect(downloadFoodThumbnail(7)).resolves.toBe('wxfile://milk.jpg')
    await expect(uploadFrame('scan-1', 'wxfile://frame.jpg', 'identity', 'frame-1')).resolves.toMatchObject({ id: 4, duplicate: false })

    expect(wx.downloadFile).toHaveBeenCalledWith(expect.objectContaining({
      url: 'http://127.0.0.1:8000/api/v1/foods/7/thumbnail',
      header: { Authorization: 'Bearer token-1' },
    }))
    expect(wx.uploadFile).toHaveBeenCalledWith(expect.objectContaining({
      url: 'http://127.0.0.1:8000/api/v1/scan-sessions/scan-1/frames',
      filePath: 'wxfile://frame.jpg',
      name: 'image',
      formData: { purpose: 'identity' },
      header: { Authorization: 'Bearer token-1', 'Idempotency-Key': 'frame-1' },
    }))
  })

  it('keeps reminder authorization behind one typed client boundary', async () => {
    await recordReminderSubscription(7, { PRE_TEMPLATE: 'accept', DUE_TEMPLATE: 'reject' })

    expect(requestCalls[0]).toMatchObject({
      method: 'POST',
      url: 'http://127.0.0.1:8000/api/v1/foods/7/reminder-subscription',
      data: { outcomes: { PRE_TEMPLATE: 'accept', DUE_TEMPLATE: 'reject' } },
    })
  })
})
