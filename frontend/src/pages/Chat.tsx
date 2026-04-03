/**
 * Chat — Growth War Room
 * 
 * UI 风格：Tavily 质感 — 暖白底、宽松间距、卡片式展示、克制的颜色
 * 不是即时通讯泡泡，是专业增长工具的对话界面
 */

import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { RoundtableSimulation } from '../components/ui/RoundtableSimulation'
import { ArrowLeftIcon, SendIcon } from '../components/ui/Icons'
import type { CreatureState } from '../components/creature/types'
import { t } from '../lib/i18n'
import { api } from '../lib/api'
import { EXPERTS } from '../lib/experts'
import PixImg from '../assets/pix_basic.png'

interface ChatProps {
  creature: CreatureState
  onBack: () => void
}

interface Message {
  id: string
  role: 'user' | 'assistant' | 'status' | 'expert'
  content: string
  expertId?: string
  timestamp: number
}

const STORAGE_KEY = 'crabres_chat_messages'
const SESSION_KEY = 'crabres_chat_session'

export function Chat({ creature, onBack }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) return parsed
      }
    } catch {}
    return []  // 空消息列表，首次展示引导卡片
  })
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [activeExpert, setActiveExpert] = useState<string | undefined>(undefined)
  const [sessionId, setSessionId] = useState<string | null>(() => localStorage.getItem(SESSION_KEY))
  const [showRoundtable, setShowRoundtable] = useState(false)  // 默认隐藏圆桌，不迷惑新用户
  const [showAtMenu, setShowAtMenu] = useState(false)
  const [atFilter, setAtFilter] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const toSave = messages.slice(-100)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave)) } catch {}
  }, [messages])

  useEffect(() => {
    if (sessionId) localStorage.setItem(SESSION_KEY, sessionId)
  }, [sessionId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = { id: `u-${Date.now()}`, role: 'user', content: input.trim(), timestamp: Date.now() }
    setMessages(prev => [...prev, userMsg])
    const msgText = input.trim()
    setInput('')
    if (inputRef.current) inputRef.current.style.height = 'auto'
    setLoading(true)

    try {
      const API = (import.meta as any).env?.VITE_API_BASE || '/api'
      const token = localStorage.getItem('crabres_token') || ''
      const response = await fetch(`${API}/agent/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ message: msgText, session_id: sessionId, language: localStorage.getItem('crabres_language') || 'en' }),
      })

      if (!response.ok) throw new Error(`API Error ${response.status}`)

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) throw new Error('No response body')

      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') continue
          try {
            const event = JSON.parse(data)
            if (event.session_id && !sessionId) setSessionId(event.session_id)
            if (event.type === 'expert_thinking') setActiveExpert(event.expert_id)
            else if (event.type === 'message' || event.type === 'question') setActiveExpert(undefined)

            const newMsg: Message = {
              id: `s-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              role: event.type === 'expert_thinking' ? 'expert' as const
                : event.type === 'status' ? 'status' as const
                : 'assistant' as const,
              content: event.content || '',
              expertId: event.expert_id || undefined,
              timestamp: Date.now(),
            }
            setMessages(prev => {
              if (event.type === 'expert_thinking' && !event.content?.includes('is analyzing')) {
                return [...prev.filter(m => !(m.expertId === event.expert_id && m.content?.includes('is analyzing'))), newMsg]
              }
              return [...prev, newMsg]
            })
          } catch {}
        }
      }
      setActiveExpert(undefined)
    } catch (e: any) {
      try {
        const res = await api<any[]>('/agent/chat', {
          method: 'POST',
          body: JSON.stringify({ message: msgText, session_id: sessionId, language: localStorage.getItem('crabres_language') || 'en' }),
        })
        if (res.length > 0 && res[0].session_id) setSessionId(res[0].session_id)
        for (const r of res) {
          if (r.type === 'expert_thinking') setActiveExpert(r.expert_id)
          else setActiveExpert(undefined)
          setMessages(prev => [...prev, {
            id: `f-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            role: r.type === 'expert_thinking' ? 'expert' as const : r.type === 'status' ? 'status' as const : 'assistant' as const,
            content: r.content, expertId: r.expert_id || undefined, timestamp: Date.now(),
          }])
        }
        setActiveExpert(undefined)
      } catch (fallbackErr: any) {
        setMessages(prev => [...prev, {
          id: `e-${Date.now()}`, role: 'assistant',
          content: `Connection failed: ${fallbackErr.message}. Please try again.`,
          timestamp: Date.now(),
        }])
      }
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const activeExperts = new Set(messages.filter(m => m.role === 'expert').map(m => m.expertId).filter(Boolean))

  return (
    <div className="h-screen flex flex-col bg-surface">
      {/* ====== 头部 — 干净克制 ====== */}
      <div className="shrink-0 border-b border-border bg-surface z-20">
        <div className="max-w-4xl mx-auto flex items-center gap-3 px-5 py-3">
          <button onClick={onBack} className="p-2 -ml-2 rounded-lg hover:bg-hover transition-colors">
            <ArrowLeftIcon />
          </button>

          <div className="flex items-center gap-2.5 flex-1 min-w-0">
            <img src={PixImg} alt="CrabRes" className="w-8 h-8 rounded-full object-cover" />
            <div>
              <p className="text-sm font-semibold text-primary">{t('chat.title')}</p>
              <p className="text-[11px] text-muted">
                {loading ? 'Researching...' : '13 experts ready'}
              </p>
            </div>
          </div>

          <button
            onClick={() => setShowRoundtable(!showRoundtable)}
            className={`hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${showRoundtable ? 'bg-brand/8 text-brand' : 'text-muted hover:bg-hover'}`}
          >
            Roundtable
          </button>
        </div>
      </div>

      {/* ====== 主体 ====== */}
      <div className="flex-1 flex max-w-4xl mx-auto w-full min-h-0">

        {/* 左栏：圆桌 */}
        {showRoundtable && (
          <div className="hidden sm:flex flex-col w-[280px] shrink-0 border-r border-border overflow-y-auto">
            <div className="flex-1 flex flex-col items-center justify-center px-3 py-4">
              <RoundtableSimulation activeExpertId={activeExpert} isSimulating={loading || !!activeExpert} />
            </div>
            <div className="shrink-0 border-t border-border px-2 py-2 space-y-0.5">
              <p className="text-[9px] text-muted px-2 py-1 uppercase tracking-wider">@ direct message</p>
              {Object.entries(EXPERTS).map(([key, expert]) => {
                const isActive = activeExpert === key
                const contributed = activeExperts.has(key)
                return (
                  <button key={key}
                    onClick={() => { setInput(`@${key} `); inputRef.current?.focus() }}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-all text-left hover:bg-hover ${isActive ? 'bg-brand/5' : contributed ? 'opacity-80' : 'opacity-40 hover:opacity-70'}`}
                  >
                    <img src={expert.avatar} alt={expert.short} className="w-5 h-5 rounded-full object-cover shrink-0" />
                    <span className={`truncate ${isActive ? 'font-medium text-primary' : 'text-muted'}`}>{expert.short}</span>
                    {isActive && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-brand animate-pulse shrink-0" />}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* 右栏：内容 + 输入 */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">

          {/* 消息区 */}
          <div className="flex-1 overflow-y-auto px-5 py-6 space-y-5">

            {/* ====== 首次引导 ====== */}
            {messages.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center h-full max-w-md mx-auto text-center py-12">
                <img src={PixImg} alt="CrabRes" className="w-16 h-16 rounded-full object-cover mb-4" />
                <h2 className="text-lg font-semibold text-primary mb-2">Hi! I'm CrabRes.</h2>
                <p className="text-sm text-secondary mb-6 leading-relaxed">
                  Tell me what you're building and I'll research your market, find competitors, and create a growth plan.
                </p>
                <div className="w-full space-y-2">
                  {[
                    "I'm building an AI resume optimizer at $9.99/mo. Goal: 1000 users in 3 months.",
                    "I have a habit tracker app. No users yet. Budget is $0.",
                    "We're launching a B2B SaaS for HR teams. Help me find channels.",
                  ].map((prompt, i) => (
                    <button key={i}
                      onClick={() => { setInput(prompt); inputRef.current?.focus() }}
                      className="w-full text-left px-4 py-3 rounded-xl border border-border text-sm text-secondary hover:border-brand/30 hover:bg-brand/3 transition-all"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted mt-6">Or just describe your product in your own words.</p>
              </div>
            )}
            {messages.map(msg => {

              // ── 用户消息：右对齐，简洁 ──
              if (msg.role === 'user') {
                return (
                  <div key={msg.id} className="flex justify-end">
                    <div className="max-w-[75%] bg-brand text-white px-4 py-2.5 rounded-2xl rounded-br-md text-sm leading-relaxed">
                      {msg.content}
                    </div>
                  </div>
                )
              }

              // ── Agent 主回复：卡片式，Markdown 格式化 ──
              if (msg.role === 'assistant') {
                return (
                  <div key={msg.id} className="animate-fade-in">
                    <div className="flex items-center gap-2 mb-2">
                      <img src={PixImg} alt="CrabRes" className="w-6 h-6 rounded-full object-cover" />
                      <span className="text-xs font-medium text-brand">CrabRes</span>
                      <span className="text-[10px] text-muted">{new Date(msg.timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</span>
                    </div>
                    <div className="crabres-prose ml-8">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                )
              }

              // ── 专家分析：折叠卡片 ──
              if (msg.role === 'expert' && msg.expertId) {
                const expert = EXPERTS[msg.expertId]
                if (!expert) return null
                const isShort = msg.content.includes('is analyzing')
                if (isShort) {
                  return (
                    <div key={msg.id} className="ml-8 flex items-center gap-2 text-xs text-muted animate-fade-in">
                      <img src={expert.avatar} alt={expert.short} className="w-4 h-4 rounded-full" />
                      <span>{expert.name} analyzing...</span>
                      <span className="w-1.5 h-1.5 rounded-full bg-brand/50 animate-pulse" />
                    </div>
                  )
                }
                return (
                  <ExpertCard key={msg.id} expert={expert} content={msg.content} />
                )
              }

              // ── 状态消息：细线 ──
              if (msg.role === 'status') {
                return (
                  <div key={msg.id} className="flex items-center gap-3 ml-8 animate-fade-in">
                    <div className="h-px flex-1 bg-border" />
                    <span className="text-[10px] text-muted whitespace-nowrap flex items-center gap-1.5">
                      <span className="w-1 h-1 rounded-full bg-brand/60 animate-pulse" />
                      {msg.content}
                    </span>
                    <div className="h-px flex-1 bg-border" />
                  </div>
                )
              }

              return null
            })}

            {loading && (
              <div className="ml-8 flex items-center gap-2 text-xs text-muted animate-fade-in">
                <div className="flex gap-0.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-brand/40 animate-bounce" style={{ animationDelay: '0ms' }} />
                  <div className="w-1.5 h-1.5 rounded-full bg-brand/40 animate-bounce" style={{ animationDelay: '150ms' }} />
                  <div className="w-1.5 h-1.5 rounded-full bg-brand/40 animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span>Thinking...</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* ====== 输入区 ====== */}
          <div className="shrink-0 px-5 py-3 border-t border-border relative">
            {showAtMenu && (
              <div className="absolute bottom-full left-5 right-5 mb-1 bg-[var(--bg-card)] border border-border rounded-xl p-2 shadow-lg max-h-[280px] overflow-y-auto z-30">
                <p className="text-[10px] text-muted px-2 py-1 uppercase">@ Direct message</p>
                {Object.entries(EXPERTS)
                  .filter(([key, ex]) => !atFilter || ex.name.toLowerCase().includes(atFilter.toLowerCase()) || key.includes(atFilter.toLowerCase()))
                  .map(([key, expert]) => (
                    <button key={key}
                      className="w-full flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-hover transition-colors text-left"
                      onClick={() => { setInput(`@${key} `); setShowAtMenu(false); setAtFilter(''); inputRef.current?.focus() }}
                    >
                      <img src={expert.avatar} alt={expert.short} className="w-7 h-7 rounded-full object-cover" />
                      <div>
                        <p className="text-sm font-medium text-primary">{expert.name}</p>
                        <p className="text-[10px] text-muted">@{key}</p>
                      </div>
                    </button>
                  ))
                }
              </div>
            )}
            <div className="flex gap-2 items-end max-w-3xl mx-auto">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => {
                  const val = e.target.value
                  setInput(val)
                  if (inputRef.current) {
                    inputRef.current.style.height = 'auto'
                    inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 120) + 'px'
                  }
                  if (val.endsWith('@') || (val.includes('@') && !val.includes(' '))) {
                    setShowAtMenu(true)
                    setAtFilter(val.split('@').pop() || '')
                  } else {
                    setShowAtMenu(false)
                  }
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); setShowAtMenu(false); sendMessage() }
                  if (e.key === 'Escape') setShowAtMenu(false)
                }}
                placeholder="Describe your product or ask a growth question..."
                className="flex-1 !rounded-xl resize-none !py-2.5 !min-h-[42px] !max-h-[120px] text-sm"
                rows={1}
                disabled={loading}
              />
              <button
                onClick={() => { setShowAtMenu(false); sendMessage() }}
                disabled={loading || !input.trim()}
                className="btn-primary !px-4 !py-2.5 !rounded-xl disabled:opacity-30"
              >
                <SendIcon />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ====== 专家卡片：可折叠 ======

function ExpertCard({ expert, content }: { expert: { name: string; color: string; avatar: string; short: string }; content: string }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = content.length > 500

  return (
    <div className="ml-8 animate-fade-in">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left group"
      >
        <img src={expert.avatar} alt={expert.short} className="w-5 h-5 rounded-full shrink-0" />
        <span className="text-xs font-medium" style={{ color: expert.color }}>{expert.name}</span>
        <div className="h-px flex-1 bg-border" />
        <span className="text-[10px] text-muted group-hover:text-primary transition-colors">
          {expanded ? 'Collapse' : 'Expand'}
        </span>
      </button>
      {expanded && (
        <div className="mt-2 pl-7 border-l-2 animate-fade-in" style={{ borderColor: expert.color + '30' }}>
          <div className="crabres-prose text-secondary">
            <ReactMarkdown>{isLong ? content : content}</ReactMarkdown>
          </div>
        </div>
      )}
      {!expanded && (
        <p className="mt-1 pl-7 text-xs text-muted line-clamp-2 cursor-pointer hover:text-secondary transition-colors"
           onClick={() => setExpanded(true)}>
          {content.replace(/[#*_`]/g, '').slice(0, 150)}...
        </p>
      )}
    </div>
  )
}
