import { beforeEach, describe, expect, it, vi } from 'vitest'

import { request, setApiBaseUrl, setUnauthorizedHandler } from '../services/http'
import { clearSession, getAccessToken, loginWithWechat, setSession } from '../store/session'

type RequestCall = WechatMiniprogram.RequestOption

describe('request', () => {
  let captured: RequestCall | undefined
  let response: WechatMiniprogram.RequestSuccessCallbackResult

  beforeEach(() => {
    captured = undefined
    response = { statusCode: 200, data: {} } as WechatMiniprogram.RequestSuccessCallbackResult
    clearSession()
    setApiBaseUrl('http://127.0.0.1:8000/api/v1')
    setUnauthorizedHandler(undefined)

    vi.stubGlobal('wx', {
      getStorageSync: vi.fn(() => ''),
      setStorageSync: vi.fn(),
      removeStorageSync: vi.fn(),
      request: vi.fn((options: RequestCall) => {
        captured = options
        options.success?.(response)
      }),
    })
  })

  it('drops an expired app token before making a request', () => {
    setSession({ accessToken: 'expired-token', expiresAt: Date.now() - 1 })

    expect(getAccessToken()).toBeNull()
    expect(wx.removeStorageSync).toHaveBeenCalled()
  })

  it('adds the app token and caller idempotency key to a mutating request', async () => {
    setSession({ accessToken: 'token-1', expiresAt: Date.now() + 60_000 })
    response = { statusCode: 201, data: { id: 7 } } as unknown as WechatMiniprogram.RequestSuccessCallbackResult

    await expect(
      request({ method: 'POST', path: '/foods/manual', data: {}, idempotencyKey: 'food-1' }),
    ).resolves.toEqual({ id: 7 })

    expect(captured?.header).toMatchObject({
      Authorization: 'Bearer token-1',
      'Idempotency-Key': 'food-1',
    })
  })

  it('turns a backend error envelope into a retryable client error', async () => {
    response = {
      statusCode: 503,
      data: {
        error: {
          code: 'queue_unavailable',
          message: '识别服务暂时不可用',
          retryable: true,
        },
      },
    } as unknown as WechatMiniprogram.RequestSuccessCallbackResult

    await expect(request({ method: 'GET', path: '/health/ready' })).rejects.toMatchObject({
      code: 'queue_unavailable',
      message: '识别服务暂时不可用',
      retryable: true,
      statusCode: 503,
    })
  })

  it('reports a transport failure without leaking platform details', async () => {
    vi.mocked(wx.request).mockImplementationOnce((options: RequestCall) => {
      options.fail?.({ errMsg: 'request:fail socket closed' } as unknown as WechatMiniprogram.RequestFailCallbackErr)
      return {} as WechatMiniprogram.RequestTask
    })

    await expect(request({ method: 'GET', path: '/foods' })).rejects.toMatchObject({
      code: 'network_unavailable',
      retryable: true,
    })
  })

  it('renews the session once after a backend 401 and retries with the new token', async () => {
    setSession({ accessToken: 'old-token', expiresAt: Date.now() + 60_000 })
    const authorizationHeaders: string[] = []
    let attempt = 0
    vi.mocked(wx.request).mockImplementation((options: RequestCall) => {
      authorizationHeaders.push(String(options.header?.Authorization))
      attempt += 1
      if (attempt === 1) {
        options.success?.({ statusCode: 401, data: { error: { code: 'invalid_token', message: '登录已过期', retryable: false } } } as unknown as WechatMiniprogram.RequestSuccessCallbackResult)
      } else {
        options.success?.({ statusCode: 200, data: { items: [] } } as unknown as WechatMiniprogram.RequestSuccessCallbackResult)
      }
      return {} as WechatMiniprogram.RequestTask
    })
    setUnauthorizedHandler(async () => {
      setSession({ accessToken: 'new-token', expiresAt: Date.now() + 60_000 })
    })

    await expect(request({ method: 'GET', path: '/foods' })).resolves.toEqual({ items: [] })
    expect(authorizationHeaders).toEqual(['Bearer old-token', 'Bearer new-token'])
  })

  it('uses demo-user only for localhost login and stores the returned app token', async () => {
    vi.mocked(wx.request).mockImplementationOnce((options: RequestCall) => {
      captured = options
      options.success?.({ statusCode: 200, data: { access_token: 'app-token', token_type: 'bearer' } } as unknown as WechatMiniprogram.RequestSuccessCallbackResult)
      return {} as WechatMiniprogram.RequestTask
    })
    Object.assign(wx, {
      login: vi.fn((options: WechatMiniprogram.LoginOption) => {
        options.success?.({ code: 'real-wechat-code', errMsg: 'login:ok' })
      }),
    })

    const session = await loginWithWechat()

    expect(captured?.data).toEqual({ code: 'demo-user' })
    expect(session.accessToken).toBe('app-token')
    expect(getAccessToken()).toBe('app-token')
  })

  it('sends the wx.login code when the API is not localhost', async () => {
    setApiBaseUrl('https://api.example.com/api/v1')
    vi.mocked(wx.request).mockImplementationOnce((options: RequestCall) => {
      captured = options
      options.success?.({ statusCode: 200, data: { access_token: 'prod-token', token_type: 'bearer' } } as unknown as WechatMiniprogram.RequestSuccessCallbackResult)
      return {} as WechatMiniprogram.RequestTask
    })
    Object.assign(wx, {
      login: vi.fn((options: WechatMiniprogram.LoginOption) => {
        options.success?.({ code: 'real-wechat-code', errMsg: 'login:ok' })
      }),
    })

    await loginWithWechat()

    expect(captured?.data).toEqual({ code: 'real-wechat-code' })
  })
})
