/**
 * Chat — Growth War Room
 * 
 * 不是普通聊天。是增长作战室。
 * 左栏：专家圆桌可视化（桌面端）
 * 主区：群聊消息流（专家 + CrabRes + 用户）
 * 顶部：战术状态条（活跃专家、研究进度）
 */

import { useState, useRef, useEffect } from 'react'
import { RoundtableSimulation } from '../components/ui/RoundtableSimulation'
import { ArrowLeftIcon, SendIcon } from '../components/ui/Icons'
import type { CreatureState } from '../components/creature/types'
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
  // 从 localStorage 恢复消息和 session
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) return parsed
      }
    } catch {}
    return [{
      id: '0', role: 'assistant' as const,
      content: "War Room active. Tell me about your product — I'll deploy the research team immediately.",
      timestamp: Date.now(),
    }]
  })
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [activeExpert, setActiveExpert] = useState<string | undefined>(undefined)
  const [sessionId, setSessionId] = useState<string | null>(() => localStorage.getItem(SESSION_KEY))
  const [showRoundtable, setShowRoundtable] = useState(true)
  const [showAtMenu, setShowAtMenu] = useState(false)
  const [atFilter, setAtFilter] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // 持久化消息到 localStorage
  useEffect(() => {
    // 只保存最近 100 条消息（避免 localStorage 爆）
    const toSave = messages.slice(-100)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave)) } catch {}
  }, [messages])

  // 持久化 sessionId
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
    setInput('')
    setLoading(true)

    try {
      const res = await api<any[]>('/agent/chat', {
        method: 'POST',
        body: JSON.stringify({ message: userMsg.content, session_id: sessionId }),
      })
      if (res.length > 0 && res[0].session_id) setSessionId(res[0].session_id)

      for (let i = 0; i < res.length; i++) {
        const r = res[i]
        if (r.type === 'expert_thinking') {
          setActiveExpert(r.expert_id)
          if (r.content.includes('is analyzing')) {
            await new Promise(resolve => setTimeout(resolve, 800))
          }
        } else {
          setActiveExpert(undefined)
        }

        const newMsg: Message = {
          id: `a-${Date.now()}-${i}`,
          role: r.type === 'expert_thinking' ? 'expert' as const
            : r.type === 'status' ? 'status' as const
            : 'assistant' as const,
          content: r.content,
          expertId: r.expert_id || undefined,
          timestamp: Date.now() + i,
        }

        setMessages(prev => {
          if (r.type === 'expert_thinking' && !r.content.includes('is analyzing')) {
            const filtered = prev.filter(m => !(m.expertId === r.expert_id && m.content.includes('is analyzing')))
            return [...filtered, newMsg]
          }
          return [...prev, newMsg]
        })

        if (i < res.length - 1) {
          const delay = r.type === 'status' ? 150 : 300
          await new Promise(resolve => setTimeout(resolve, delay))
        }
      }
      setActiveExpert(undefined)
    } catch (e: any) {
      setMessages(prev => [...prev, {
        id: `e-${Date.now()}`, role: 'assistant',
        content: `Something went wrong: ${e.message}. Please try again.`,
        timestamp: Date.now(),
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const activeExperts = new Set(messages.filter(m => m.role === 'expert').map(m => m.expertId).filter(Boolean))
  const statusCount = messages.filter(m => m.role === 'status').length
  const expertCount = activeExperts.size

  return (
    <div className="h-screen flex flex-col bg-surface">
      {/* ====== 头部状态条 — 固定顶部 ====== */}
      <div className="shrink-0 border-b border-border bg-glass z-20">
        <div className="max-w-5xl mx-auto flex items-center gap-3 px-4 py-2.5">
          <button onClick={onBack} className="p-2 rounded-xl hover:bg-hover transition-colors" aria-label="Back">
            <ArrowLeftIcon />
          </button>

          <div className="flex -space-x-1.5">
            <img src={PixImg} alt="Pix" className={`w-7 h-7 rounded-full object-cover border-2 border-white ${loading ? 'animate-pulse' : ''}`} />
            {Array.from(activeExperts).slice(0, 5).map(eid => {
              const expert = EXPERTS[eid || '']
              return expert ? (
                <img key={eid} src={expert.avatar} alt={expert.short}
                  className="w-7 h-7 rounded-full border-2 border-white shadow-sm object-cover" />
              ) : null
            })}
          </div>

          <div className="flex-1 min-w-0">
            <p className="text-sm font-heading font-bold text-primary tracking-tight">Growth War Room</p>
            <p className="text-[10px] text-muted font-mono uppercase tracking-wider">
              {loading ? 'RESEARCHING...' :
                expertCount > 0 ? `${expertCount} EXPERTS · ${statusCount} OPS` : 'STANDBY · 13 EXPERTS READY'}
            </p>
          </div>

          <button
            onClick={() => setShowRoundtable(!showRoundtable)}
            className={`hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all ${showRoundtable ? 'bg-brand/10 text-brand border border-brand/20' : 'bg-hover text-muted border border-border'}`}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: showRoundtable ? 'var(--brand)' : 'var(--text-muted)' }} />
            Roundtable
          </button>
        </div>
      </div>

      {/* ====== 主体 — 填满剩余高度 ====== */}
      <div className="flex-1 flex max-w-5xl mx-auto w-full min-h-0">

        {/* 左栏：圆桌 — 固定不滚动 */}
        {showRoundtable && (
          <div className="hidden sm:flex flex-col w-[300px] shrink-0 border-r border-border bg-surface overflow-y-auto">
            <div className="flex-1 flex flex-col items-center justify-center px-3 py-4">
              <RoundtableSimulation activeExpertId={activeExpert} isSimulating={loading || !!activeExpert} />
            </div>

            {/* 专家列表 — 可点击 @ 私聊 */}
            <div className="shrink-0 border-t border-border px-2 py-2 space-y-0.5">
              <p className="text-[9px] text-muted px-2 py-1 font-heading uppercase tracking-wider">Click to @ direct message</p>
              {Object.entries(EXPERTS).map(([key, expert]) => {
                const isActive = activeExpert === key
                const contributed = activeExperts.has(key)
                return (
                  <button key={key}
                    onClick={() => {
                      setInput(`@${key} `)
                      inputRef.current?.focus()
                    }}
                    className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-all text-left hover:bg-hover ${isActive ? 'bg-brand/8 border border-brand/15' : contributed ? 'opacity-90' : 'opacity-50 hover:opacity-80'}`}
                  >
                    <img src={expert.avatar} alt={expert.short} className="w-5 h-5 rounded-full object-cover shrink-0" />
                    <span className={`font-heading truncate ${isActive ? 'font-bold text-primary' : 'text-muted'}`}>{expert.short}</span>
                    {isActive && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-brand animate-pulse shrink-0" />}
                    {contributed && !isActive && <span className="ml-auto text-[9px] text-brand/60 shrink-0">✓</span>}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* 右栏：消息流 + 输入框 */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">

          {/* 消息区 — 可滚动 */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {messages.map(msg => {
              if (msg.role === 'user') {
                return (
                  <div key={msg.id} className="flex justify-end animate-fade-in">
                    <div className="max-w-[80%] px-4 py-3 rounded-2xl rounded-br-sm bg-brand text-white text-sm shadow-sm">
                      {msg.content}
                    </div>
                  </div>
                )
              }

              if (msg.role === 'assistant') {
                return (
                  <div key={msg.id} className="flex gap-2.5 animate-fade-in">
                    <img src={PixImg} alt="Pix" className="w-7 h-7 shrink-0 mt-0.5 rounded-full object-cover" />
                    <div className="max-w-[85%]">
                      <p className="text-[10px] font-heading font-semibold text-brand mb-1">CrabRes</p>
                      <div className="px-4 py-3 rounded-2xl rounded-tl-sm card text-sm text-primary whitespace-pre-wrap leading-relaxed">
                        {msg.content}
                      </div>
                    </div>
                  </div>
                )
              }

              if (msg.role === 'expert' && msg.expertId) {
                const expert = EXPERTS[msg.expertId]
                if (!expert) return null
                return (
                  <div key={msg.id} className="flex gap-2.5 animate-fade-in">
                    <img src={expert.avatar} alt={expert.short}
                      className="w-7 h-7 shrink-0 mt-0.5 rounded-full object-cover"
                      style={{ border: `1.5px solid ${expert.color}40` }} />
                    <div className="max-w-[85%]">
                      <p className="text-[10px] font-heading font-semibold mb-1" style={{ color: expert.color }}>
                        {expert.name}
                      </p>
                      <div className="px-3.5 py-2.5 rounded-2xl rounded-tl-sm text-sm text-secondary leading-relaxed"
                        style={{ background: expert.color + '06', border: `1px solid ${expert.color}12` }}>
                        {msg.content.length > 400 ? (
                          <CollapsibleText text={msg.content} maxLength={400} />
                        ) : msg.content}
                      </div>
                    </div>
                  </div>
                )
              }

              if (msg.role === 'status') {
                return (
                  <div key={msg.id} className="flex justify-center animate-fade-in">
                    <span className="text-[10px] text-muted bg-hover px-3 py-1 rounded-full flex items-center gap-1.5 font-mono uppercase tracking-wider">
                      <span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" />
                      {msg.content}
                    </span>
                  </div>
                )
              }

              return null
            })}

            {loading && (
              <div className="flex gap-2.5 animate-fade-in">
                <img src={PixImg} alt="Pix" className="w-7 h-7 shrink-0 mt-0.5 rounded-full object-cover animate-pulse" />
                <div className="px-4 py-3 rounded-2xl rounded-tl-sm card">
                  <div className="flex items-center gap-2">
                    <div className="flex gap-1">
                      <div className="w-1.5 h-1.5 rounded-full bg-brand/50 animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-1.5 h-1.5 rounded-full bg-brand/50 animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-1.5 h-1.5 rounded-full bg-brand/50 animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    <span className="text-[10px] text-muted font-mono uppercase">Deploying experts...</span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* ====== 输入区 — 固定底部 ====== */}
          <div className="shrink-0 px-4 py-3 border-t border-border bg-glass relative">
            {/* @ 弹出菜单 */}
            {showAtMenu && (
              <div className="absolute bottom-full left-4 right-4 mb-1 card p-2 shadow-lg max-h-[300px] overflow-y-auto z-30">
                <p className="text-[10px] text-muted px-2 py-1 font-heading uppercase">@ Direct Message an Expert</p>
                {Object.entries(EXPERTS)
                  .filter(([key, ex]) => !atFilter || ex.name.toLowerCase().includes(atFilter.toLowerCase()) || key.includes(atFilter.toLowerCase()))
                  .map(([key, expert]) => (
                    <button key={key}
                      className="w-full flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-hover transition-colors text-left"
                      onClick={() => {
                        setInput(`@${key} `)
                        setShowAtMenu(false)
                        setAtFilter('')
                        inputRef.current?.focus()
                      }}
                    >
                      <img src={expert.avatar} alt={expert.short} className="w-8 h-8 rounded-full object-cover" />
                      <div>
                        <p className="text-sm font-medium text-primary">{expert.name}</p>
                        <p className="text-[10px] text-muted">@{key}</p>
                      </div>
                    </button>
                  ))
                }
              </div>
            )}
            <div className="flex gap-2 items-end">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => {
                  const val = e.target.value
                  setInput(val)
                  // 自动扩展高度
                  if (inputRef.current) {
                    inputRef.current.style.height = 'auto'
                    inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 120) + 'px'
                  }
                  // 检测 @ 触发
                  if (val.endsWith('@') || (val.includes('@') && !val.includes(' '))) {
                    setShowAtMenu(true)
                    setAtFilter(val.split('@').pop() || '')
                  } else {
                    setShowAtMenu(false)
                  }
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    setShowAtMenu(false)
                    sendMessage()
                  }
                  if (e.key === 'Escape') setShowAtMenu(false)
                }}
                placeholder="Message... (type @ to DM an expert, Shift+Enter for new line)"
                className="flex-1 !rounded-xl resize-none !py-2.5 !min-h-[40px] !max-h-[120px]"
                rows={1}
                disabled={loading}
                aria-label="Message input"
              />
              <button
                onClick={() => { setShowAtMenu(false); sendMessage() }}
                disabled={loading || !input.trim()}
                className="btn-primary !px-4 !rounded-xl disabled:opacity-40"
                aria-label="Send message"
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

function CollapsibleText({ text, maxLength }: { text: string; maxLength: number }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <>
      {expanded ? text : text.slice(0, maxLength) + '...'}
      <button onClick={() => setExpanded(!expanded)}
        className="ml-1 text-brand text-xs hover:underline">
        {expanded ? 'Show less' : 'Read more'}
      </button>
    </>
  )
}

// SendIcon imported from Icons.tsx
