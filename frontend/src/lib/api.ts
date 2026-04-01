/**
 * CrabRes API 层
 */

const API = import.meta.env.VITE_API_BASE || '/api'

// Token 管理
export function getToken(): string | null { return localStorage.getItem('crabres_token') }
export function setToken(token: string) { localStorage.setItem('crabres_token', token) }
export function clearToken() { localStorage.removeItem('crabres_token') }

let _onAuthExpired: (() => void) | null = null
export function setAuthExpiredHandler(fn: () => void) { _onAuthExpired = fn }

export async function api<T = any>(path: string, opts?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(opts?.headers as Record<string, string> || {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API}${path}`, { ...opts, headers })
  if (res.status === 401) {
    clearToken()
    _onAuthExpired?.()
    throw new Error('Session expired')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `API Error ${res.status}`)
  }
  const text = await res.text()
  return text ? JSON.parse(text) : ({} as T)
}
