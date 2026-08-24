import { getApiBaseUrl, request } from '../services/http'
import type { Session, TokenResponse } from '../types/api'

const SESSION_STORAGE_KEY = 'xianzhi.session.v1'
const SESSION_LIFETIME_MS = 23 * 60 * 60 * 1000

let memorySession: Session | null = null

function isSession(value: unknown): value is Session {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<Session>
  return typeof candidate.accessToken === 'string' && typeof candidate.expiresAt === 'number'
}

export function setSession(session: Session): void {
  memorySession = session
  wx.setStorageSync(SESSION_STORAGE_KEY, session)
}

export function clearSession(): void {
  memorySession = null
  if (typeof wx !== 'undefined') wx.removeStorageSync(SESSION_STORAGE_KEY)
}

export function getSession(): Session | null {
  if (!memorySession && typeof wx !== 'undefined') {
    const stored: unknown = wx.getStorageSync(SESSION_STORAGE_KEY)
    if (isSession(stored)) memorySession = stored
  }
  if (memorySession && memorySession.expiresAt <= Date.now()) {
    clearSession()
  }
  return memorySession
}

export function getAccessToken(): string | null {
  return getSession()?.accessToken ?? null
}

function wxLogin(): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.login({
      success(result) {
        if (result.code) resolve(result.code)
        else reject(new Error('wechat_login_failed'))
      },
      fail() {
        reject(new Error('wechat_login_failed'))
      },
    })
  })
}

export async function loginWithWechat(): Promise<Session> {
  const wxCode = await wxLogin()
  const isLocalApi = /^https?:\/\/(127\.0\.0\.1|localhost|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(:\d+)?\//.test(getApiBaseUrl())
  const token = await request<TokenResponse>({
    method: 'POST',
    path: '/auth/wechat/login',
    data: { code: isLocalApi ? 'demo-user' : wxCode },
    authenticated: false,
    retryOnUnauthorized: false,
  })
  const session = {
    accessToken: token.access_token,
    expiresAt: Date.now() + SESSION_LIFETIME_MS,
  }
  setSession(session)
  return session
}
