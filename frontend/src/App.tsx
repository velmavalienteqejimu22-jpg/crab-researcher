/**
 * CrabRes — AI Growth Strategy Agent
 * 
 * 主应用入口。管理路由和全局状态。
 */

import { useState, useEffect } from 'react'
import { Surface } from './pages/Surface'
import { Chat } from './pages/Chat'
import { Plan } from './pages/Plan'
import { Onboarding } from './pages/Onboarding'
import { Landing } from './pages/Landing'
import { Compare } from './pages/Compare'
import { Settings } from './pages/Settings'
import { getToken, setToken, clearToken, setAuthExpiredHandler, api } from './lib/api'
import { generateCreature } from './components/creature/types'
import type { CreatureState } from './components/creature/types'

// ====== 登录页（简洁版，后续丰富）======

function AuthPage({ onLogin }: { onLogin: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [company, setCompany] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      if (mode === 'register') {
        const res = await api<{ access_token: string }>('/auth/register', {
          method: 'POST',
          body: JSON.stringify({ company_name: company || 'My Company', contact_email: email, password }),
        })
        setToken(res.access_token)
      } else {
        const res = await api<{ access_token: string }>('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        })
        setToken(res.access_token)
      }
      onLogin()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="text-3xl mb-2">🦀</div>
          <h1 className="text-xl font-bold text-primary tracking-tight">CrabRes</h1>
          <p className="text-sm text-muted mt-1">Your AI Growth Partner</p>
        </div>

        {/* OAuth 一键登录 */}
        <div className="space-y-2 mb-4">
          <a href={`${import.meta.env.VITE_API_BASE || '/api'}/oauth/google`}
            className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg border border-border text-sm font-medium text-primary hover:bg-hover transition-colors">
            <svg width="16" height="16" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
            Continue with Google
          </a>
          <a href={`${import.meta.env.VITE_API_BASE || '/api'}/oauth/github`}
            className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg border border-border text-sm font-medium text-primary hover:bg-hover transition-colors">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.6.11.793-.26.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/></svg>
            Continue with GitHub
          </a>
        </div>

        <div className="flex items-center gap-3 mb-4">
          <div className="flex-1 h-px bg-border"></div>
          <span className="text-xs text-muted">or</span>
          <div className="flex-1 h-px bg-border"></div>
        </div>

        {/* 切换 */}
        <div className="flex gap-1 mb-6 p-1 rounded-xl bg-hover">
          <button onClick={() => setMode('login')}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${mode === 'login' ? 'bg-white shadow-sm text-primary' : 'text-muted'}`}>
            Log in
          </button>
          <button onClick={() => setMode('register')}
            className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${mode === 'register' ? 'bg-white shadow-sm text-primary' : 'text-muted'}`}>
            Sign up
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-100 text-sm text-red-600">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === 'register' && (
            <input
              className="w-full"
              placeholder="Company or product name"
              value={company}
              onChange={e => setCompany(e.target.value)}
            />
          )}
          <input
            className="w-full"
            type="email"
            placeholder="Email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
          />
          <input
            className="w-full"
            type="password"
            placeholder="Password (6+ chars)"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            minLength={6}
          />
          <button type="submit" disabled={loading}
            className="btn-primary w-full !py-3 disabled:opacity-60">
            {loading ? 'Loading...' : mode === 'login' ? 'Log in' : 'Create account'}
          </button>
        </form>

        <p className="text-xs text-muted text-center mt-6">
          {mode === 'login' ? "Don't have an account?" : 'Already have one?'}
          <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null) }}
            className="text-brand ml-1 hover:underline">
            {mode === 'login' ? 'Sign up' : 'Log in'}
          </button>
        </p>

        {/* 背书 */}
        <div className="mt-8 text-center">
          <p className="text-xs text-muted">
            Powered by 13 AI growth experts · 18 research frameworks
          </p>
        </div>
      </div>
    </div>
  )
}

// ====== 主应用 ======

export default function App() {
  const [authed, setAuthed] = useState(!!getToken())
  const [showAuth, setShowAuth] = useState(false)
  const [showCompare, setShowCompare] = useState(false)
  const [onboarded, setOnboarded] = useState(!!localStorage.getItem('crabres_onboarded'))
  const [page, setPage] = useState<'surface' | 'chat' | 'plan' | 'settings'>('surface')
  const [userId, setUserId] = useState('default')
  const [creature, setCreature] = useState<CreatureState>(() =>
    generateCreature('default', 'saas')
  )

  useEffect(() => {
    setAuthExpiredHandler(() => setAuthed(false))
    // 初始化暗色模式
    const savedTheme = localStorage.getItem('crabres_theme')
    if (savedTheme === 'dark') {
      document.documentElement.classList.add('dark')
    }
    // 处理 OAuth 回调（URL 带 ?token=xxx）
    const params = new URLSearchParams(window.location.search)
    const oauthToken = params.get('token')
    if (oauthToken) {
      setToken(oauthToken)
      setAuthed(true)
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  // 登录后加载用户数据
  useEffect(() => {
    if (!authed) return
    api<any>('/auth/me').then(user => {
      setUserId(String(user.id))
      // 如果已 onboarded，直接加载生物体
      if (onboarded) {
        const savedType = localStorage.getItem('crabres_product_type') || 'saas'
        const c = generateCreature(String(user.id), savedType)
        c.name = localStorage.getItem('crabres_product_name') || user.company_name || 'My Product'
        c.mood = 'happy'
        c.totalUsers = 0
        c.growthRate = 0
        c.streakDays = 0
        setCreature(c)
      }
    }).catch(() => {})
  }, [authed, onboarded])

  if (!authed) {
    if (showAuth) {
      return <AuthPage onLogin={() => { setAuthed(true); setShowAuth(false) }} />
    }
    if (showCompare) {
      return <Compare onGetStarted={() => { setShowCompare(false); setShowAuth(true) }} onBack={() => setShowCompare(false)} />
    }
    return <Landing onGetStarted={() => setShowAuth(true)} onLogin={() => setShowAuth(true)} onCompare={() => setShowCompare(true)} />
  }

  // 未完成 onboarding
  if (!onboarded) {
    return (
      <Onboarding
        userId={userId}
        onComplete={(c, productData) => {
          setCreature(c)
          localStorage.setItem('crabres_onboarded', '1')
          localStorage.setItem('crabres_product_type', productData.type || 'saas')
          localStorage.setItem('crabres_product_name', productData.name || '')
          setOnboarded(true)
        }}
      />
    )
  }

  // TODO: 实现 Chat 和 Plan 页面
  if (page === 'chat') {
    return <Chat creature={creature} onBack={() => setPage('surface')} />
  }

  if (page === 'plan') {
    return <Plan creature={creature} onBack={() => setPage('surface')} />
  }

  if (page === 'settings') {
    return <Settings creature={creature} onBack={() => setPage('surface')} onLogout={() => { setAuthed(false); setOnboarded(false) }} />
  }

  return (
    <Surface
      creature={creature}
      onChat={() => setPage('chat')}
      onPlan={() => setPage('plan')}
      onSettings={() => setPage('settings')}
    />
  )
}
