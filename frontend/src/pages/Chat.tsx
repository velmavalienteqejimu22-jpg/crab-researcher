/**
 * Chat — Growth War Room + Workspace
 * 
 * 左右分屏布局：
 *   左侧 — 聊天对话（Chat）
 *   右侧 — Workspace（文件树 + 文档查看器 + Agent 日志）
 * 
 * 风格：Tavily 质感 — 暖白底、宽松间距、卡片式展示、克制的颜色
 */

import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { RoundtableSimulation } from '../components/ui/RoundtableSimulation'
import { ArrowLeftIcon, SendIcon } from '../components/ui/Icons'
import { PanelRightIcon, PanelCloseIcon } from '../components/ui/WorkspaceIcons'
import { Workspace } from '../components/ui/Workspace'
import type { CreatureState } from '../components/creature/types'
import { t } from '../lib/i18n'
import { api } from '../lib/api'
import { EXPERTS } from '../lib/experts'
import PixImg from '../assets/pix_basic.png'

interface ChatProps {
  creature: CreatureState
  onBack: () => void
  onPlan?: () => void
}

interface Message {
  id: string
  role: 'user' | 'assistant' | 'status' | 'expert'
  content: string
  expertId?: string
  timestamp: number
}

interface LogEntry {
  id: string
  type: 'terminal' | 'browser' | 'action'
  content: string
  timestamp: number
}

const STORAGE_KEY = 'crabres_chat_messages'
const SESSION_KEY = 'crabres_chat_session'

export function Chat({ creature, onBack, onPlan }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) return parsed
      }
    } catch {}
    return []
  })
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [activeExpert, setActiveExpert] = useState<string | undefined>(undefined)
  const [sessionId, setSessionId] = useState<string | null>(() => localStorage.getItem(SESSION_KEY))
  const [showAtMenu, setShowAtMenu] = useState(false)
  const [atFilter, setAtFilter] = useState('')
  const [showWorkspace, setShowWorkspace] = useState(false)
  const [workspaceFile, setWorkspaceFile] = useState<string | null>(null)
  const [agentLogs, setAgentLogs] = useState<LogEntry[]>([])
  const [workspaceRefreshKey, setWorkspaceRefreshKey] = useState(0)
  const [browserState, setBrowserState] = useState<{
    status: 'idle' | 'loading' | 'loaded' | 'error'
    url?: string
    title?: string
    screenshotPath?: string
    contentPreview?: string
    error?: string
    engine?: string
    browseFile?: string
  }>({ status: 'idle' })
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

  // 从消息中提取文件引用，自动打开 workspace
  const openWorkspaceFile = (filePath: string) => {
    setWorkspaceFile(filePath)
    setShowWorkspace(true)
  }

  // 添加 Agent 日志
  const addLog = (type: LogEntry['type'], content: string) => {
    setAgentLogs(prev => [...prev.slice(-200), {
      id: `log-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`,
      type,
      content,
      timestamp: Date.now(),
    }])
  }

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

            // 记录 Agent 日志
            if (event.type === 'status') {
              addLog('action', event.content || '')
            }

            // 文件创建事件 → 自动刷新 workspace 文件树（不创建聊天消息）
            if (event.type === 'file_created') {
              setShowWorkspace(true)
              addLog('action', `File created: ${event.name || event.path || 'unknown'}`)
              setWorkspaceRefreshKey(prev => prev + 1)
              continue
            }

            // 浏览器事件 → Browser 面板实时展示（不创建聊天消息）
            if (event.type === 'browser_event') {
              setShowWorkspace(true)
              if (event.action === 'navigating') {
                addLog('browser', `Navigating to ${event.url || ''}`)
                setBrowserState({ status: 'loading', url: event.url || '' })
              } else if (event.action === 'loaded') {
                addLog('browser', `Loaded: ${event.title || event.url || ''} (${event.engine || 'unknown'})`)
                setBrowserState({
                  status: 'loaded',
                  url: event.url || '',
                  title: event.title || '',
                  screenshotPath: event.screenshot_path || '',
                  contentPreview: event.content_preview || '',
                  engine: event.engine || '',
                  browseFile: event.browse_file || '',
                })
              } else if (event.action === 'failed') {
                addLog('browser', `Failed: ${event.url || ''} — ${event.error || ''}`)
                setBrowserState({ status: 'error', url: event.url || '', error: event.error || '' })
              }
              continue
            }

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

            // 交付物消息 → 自动打开 workspace
            if (event.type === 'message' && (event.content?.includes('prepared these') || event.content?.includes('workspace'))) {
              setShowWorkspace(true)
              addLog('action', 'Deliverables ready — workspace updated')
            }
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
  const hasExpertActivity = activeExperts.size > 0 || !!activeExpert

  return (
    <div className="h-screen flex flex-col bg-surface">
      {/* ====== 头部 ====== */}
      <div className="shrink-0 border-b border-border bg-surface z-20">
        <div className="flex items-center gap-3 px-5 py-3">
          <button onClick={onBack} className="p-2 -ml-2 rounded-lg hover:bg-hover transition-colors">
            <ArrowLeftIcon />
          </button>

          <div className="flex items-center gap-2.5 flex-1 min-w-0">
            <img src={PixImg} alt="CrabRes" className="w-8 h-8 rounded-full object-cover" />
            <div>
              <p className="text-sm font-semibold text-primary">{t('chat.title')}</p>
              <p className="text-[11px] text-muted">
                {activeExpert ? `${EXPERTS[activeExpert]?.name || 'Expert'} analyzing...`
                  : loading ? 'Researching...'
                  : activeExperts.size > 0 ? `${activeExperts.size} experts consulted`
                  : '13 experts on standby'}
              </p>
            </div>
          </div>

          {/* 专家头像群 */}
          {hasExpertActivity && (
            <div className="hidden sm:flex -space-x-1.5 animate-fade-in">
              {Array.from(activeExperts).slice(0, 5).map(eid => {
                const expert = EXPERTS[eid || '']
                return expert ? (
                  <img key={eid} src={expert.avatar} alt={expert.short}
                    className={`w-7 h-7 rounded-full border-2 border-[var(--bg-primary)] object-cover transition-all ${activeExpert === eid ? 'ring-2 ring-brand/50 scale-110' : ''}`} />
                ) : null
              })}
            </div>
          )}

          {/* Workspace 切换按钮 */}
          <button
            onClick={() => setShowWorkspace(!showWorkspace)}
            className={`p-2 rounded-lg transition-colors ${
              showWorkspace ? 'bg-brand/10 text-brand' : 'text-muted hover:text-primary hover:bg-hover'
            }`}
            title={showWorkspace ? 'Close workspace' : 'Open workspace'}>
            {showWorkspace ? <PanelCloseIcon className="w-[18px] h-[18px]" /> : <PanelRightIcon className="w-[18px] h-[18px]" />}
          </button>
        </div>
      </div>

      {/* ====== 主体：左右分屏 ====== */}
      <div className="flex-1 flex min-h-0">

        {/* ====== 左栏：聊天区 ====== */}
        <div className={`flex flex-col min-h-0 transition-all duration-300 ${
          showWorkspace ? 'w-[45%] min-w-[360px]' : 'flex-1 max-w-4xl mx-auto w-full'
        }`}>
          <div className="flex-1 flex min-h-0">
            {/* 专家面板 */}
            {hasExpertActivity && !showWorkspace && (
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

            {/* 消息区 + 输入 */}
            <div className="flex-1 flex flex-col min-w-0 min-h-0">
              {/* 消息区 */}
              <div className="flex-1 overflow-y-auto px-5 py-6 space-y-5">

                {/* 首次引导 */}
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
                  // 用户消息
                  if (msg.role === 'user') {
                    return (
                      <div key={msg.id} className="flex justify-end">
                        <div className="max-w-[75%] bg-brand text-white px-4 py-2.5 rounded-2xl rounded-br-md text-sm leading-relaxed">
                          {msg.content}
                        </div>
                      </div>
                    )
                  }

                  // Agent 主回复
                  if (msg.role === 'assistant') {
                    const hasPlaybook = msg.content.includes('Playbook') || msg.content.includes('playbook') || msg.content.includes('Plan tab')
                    const hasDeliverables = msg.content.includes('prepared these') || msg.content.includes('workspace')
                    // 提取文件路径引用
                    const fileRefs = extractFileRefs(msg.content)

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

                        {/* 文件引用 → 可点击打开 */}
                        {fileRefs.length > 0 && (
                          <div className="ml-8 mt-2 flex flex-wrap gap-1.5">
                            {fileRefs.map((ref, i) => (
                              <button key={i}
                                onClick={() => openWorkspaceFile(ref)}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[var(--bg-secondary)] border border-border text-[11px] text-secondary hover:border-brand/30 hover:text-brand transition-all">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                                  <polyline points="14 2 14 8 20 8" />
                                </svg>
                                {ref.split('/').pop()}
                              </button>
                            ))}
                          </div>
                        )}

                        {/* Playbook / Workspace 按钮 */}
                        {(hasPlaybook || hasDeliverables) && (
                          <div className="ml-8 mt-3 flex gap-2">
                            {hasDeliverables && (
                              <button onClick={() => setShowWorkspace(true)}
                                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-brand/8 text-brand text-xs font-medium hover:bg-brand/15 transition-all group">
                                <PanelRightIcon className="w-3.5 h-3.5" />
                                View Files
                                <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>
                              </button>
                            )}
                            {hasPlaybook && onPlan && (
                              <button onClick={onPlan}
                                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-brand/8 text-brand text-xs font-medium hover:bg-brand/15 transition-all group">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 14l2 2 4-4"/></svg>
                                Open Playbook
                                <span className="opacity-0 group-hover:opacity-100 transition-opacity">→</span>
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  }

                  // 专家分析
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
                    return <ExpertCard key={msg.id} expert={expert} content={msg.content} />
                  }

                  // 状态消息
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
                <div className="flex gap-2 items-end">
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

        {/* ====== 右栏：Workspace ====== */}
        {showWorkspace && (
          <div className="flex-1 min-w-[400px] animate-fade-in">
            <Workspace
              visible={showWorkspace}
              initialFile={workspaceFile}
              logs={agentLogs}
              refreshKey={workspaceRefreshKey}
              browserState={browserState}
            />
          </div>
        )}
      </div>
    </div>
  )
}

// ====== 提取消息中的文件路径引用 ======

function extractFileRefs(content: string): string[] {
  const refs: string[] = []
  // 匹配 reports/xxx.md, drafts/xxx.md, plans/xxx.md 等
  const regex = /((?:reports|drafts|plans|workspace)\/[\w\-_.]+\.(?:md|json|txt|yaml))/g
  let match
  while ((match = regex.exec(content)) !== null) {
    if (!refs.includes(match[1])) refs.push(match[1])
  }
  return refs
}

// ====== 专家卡片 ======

function ExpertCard({ expert, content }: { expert: { name: string; color: string; avatar: string; short: string }; content: string }) {
  const [expanded, setExpanded] = useState(false)

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
            <ReactMarkdown>{content}</ReactMarkdown>
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
