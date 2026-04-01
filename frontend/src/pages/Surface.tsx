/**
 * Surface — CrabRes 主界面
 * 
 * 用户每天打开看到的第一个画面。
 * 极致 calm：螃蟹 + 3 个数字 + 今日任务 + 最新发现。
 */

import { useState, useEffect } from 'react'
import { CreatureRenderer } from '../components/creature/CreatureRenderer'
import type { CreatureState } from '../components/creature/types'
import { api } from '../lib/api'

interface SurfaceProps {
  creature: CreatureState
  onChat: () => void
  onPlan: () => void
  onSettings?: () => void
}

export function Surface({ creature, onChat, onPlan, onSettings }: SurfaceProps) {
  const greeting = getGreeting(creature)
  const [discoveries, setDiscoveries] = useState<any[]>([])
  const [tasks, setTasks] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)

  // 加载真实数据
  useEffect(() => {
    const load = async () => {
      try {
        const [taskRes, discRes, statRes] = await Promise.all([
          api<any>('/growth/tasks').catch(() => ({ tasks: [] })),
          api<any>('/growth/discoveries').catch(() => ({ discoveries: [] })),
          api<any>('/growth/stats').catch(() => null),
        ])
        setTasks(taskRes.tasks || [])
        setDiscoveries(discRes.discoveries || [])
        if (statRes) setStats(statRes)
      } catch {}
    }
    load()
    const interval = setInterval(load, 60_000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="min-h-screen bg-surface bg-grid bg-noise flex flex-col items-center px-4 py-8 max-w-lg mx-auto relative z-10">
      {/* 顶部栏 */}
      <div className="w-full flex items-center justify-between mb-8">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold text-primary tracking-tight">CrabRes</span>
        </div>
        <div className="flex items-center gap-3">
          <button className="p-2 rounded-xl hover:bg-hover transition-colors">
            <BellIcon />
          </button>
        <button onClick={onSettings} className="p-2 rounded-xl hover:bg-hover transition-colors">
          <SettingsIcon />
          </button>
        </div>
      </div>

      {/* 生物体 */}
      <div className="mb-2 animate-float">
        <CreatureRenderer creature={creature} size={140} />
      </div>

      {/* 分享按钮 */}
      <button
        onClick={async () => {
          try {
            const res = await api<any>('/share/card-url')
            window.open(res.twitter_share, '_blank')
          } catch { }
        }}
        className="text-xs text-muted hover:text-brand transition-colors mb-2 flex items-center gap-1"
      >
        <ShareIcon /> Share your growth
      </button>

      {/* 问候语 */}
      <p className="text-sm text-secondary mb-6 text-center max-w-xs">
        "{greeting}"
      </p>

      {/* 3 个核心数字 */}
      <div className="flex items-center gap-6 mb-8">
        <MetricCard value={`+${stats?.growth_rate ?? creature.growthRate}%`} label="growth" />
        <MetricCard value={`${stats?.total_users ?? creature.totalUsers}`} label="users" />
        <MetricCard value={`${stats?.streak_days ?? creature.streakDays}d`} label="streak" accent />
      </div>

      {/* 今日任务 */}
      <div className="w-full mb-6">
        <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-3 font-heading">Today</h3>
        <div className="space-y-2">
          {tasks.length > 0 ? tasks.map((t: any, i: number) => (
            <TaskCard
              key={t.id || i}
              icon={t.type === 'chat' ? <ChatIcon /> : <PenIcon />}
              title={t.title}
              subtitle={t.subtitle || ''}
              action={t.type === 'chat' ? 'Chat' : 'Do it'}
            />
          )) : (
            <TaskCard icon={<ChatIcon />} title="Tell CrabRes about your product"
              subtitle="Start a conversation to begin research" action="Chat" />
          )}
        </div>
      </div>

      {/* 发现 */}
      <div className="w-full mb-8">
        <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-3">Discoveries</h3>
        <div className="space-y-2">
          {discoveries.length > 0 ? discoveries.map((d, i) => (
            <DiscoveryCard
              key={i}
              title={d.title || d.change || d.competitor || 'New discovery'}
              action={d.url ? 'View' : 'Analyze'}
            />
          )) : (
            <div className="text-center py-6 text-sm text-muted">
              Your growth daemon is scanning...<br />
              <span className="text-xs">Discoveries will appear here.</span>
            </div>
          )}
        </div>
      </div>

      {/* 底部入口 */}
      <div className="w-full flex gap-3 mt-auto pt-4">
        <button onClick={onChat}
          className="flex-1 py-3 rounded-2xl bg-brand text-white text-sm font-medium hover:bg-brand-hover transition-colors">
          Talk to CrabRes
        </button>
        <button onClick={onPlan}
          className="flex-1 py-3 rounded-2xl bg-glass text-primary text-sm font-medium hover:bg-hover transition-colors border border-border">
          Growth Plan
        </button>
      </div>
    </div>
  )
}

// ====== 子组件 ======

function MetricCard({ value, label, accent }: { value: string; label: string; accent?: boolean }) {
  return (
    <div className="text-center">
      <div className={`text-2xl font-bold tracking-tight ${accent ? 'text-brand' : 'text-primary'}`}>
        {value}
      </div>
      <div className="text-xs text-muted mt-0.5">{label}</div>
    </div>
  )
}

function TaskCard({ icon, title, subtitle, action }: { icon: React.ReactNode; title: string; subtitle: string; action: string }) {
  return (
    <div className="flex items-center gap-3 p-4 rounded-2xl bg-glass border border-border hover:border-brand/20 transition-colors group">
      <div className="w-9 h-9 rounded-xl bg-brand/8 flex items-center justify-center text-brand shrink-0">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-primary">{title}</p>
        <p className="text-xs text-muted truncate">{subtitle}</p>
      </div>
      <button className="text-xs font-medium text-brand opacity-0 group-hover:opacity-100 transition-opacity px-3 py-1.5 rounded-lg hover:bg-brand/8">
        {action} →
      </button>
    </div>
  )
}

function DiscoveryCard({ title, action }: { title: string; action: string }) {
  return (
    <div className="flex items-center gap-3 p-4 rounded-2xl bg-glass border border-border hover:border-amber-200 transition-colors group">
      <div className="w-9 h-9 rounded-xl bg-amber-50 flex items-center justify-center text-amber-500 shrink-0">
        <ZapIcon />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-primary">{title}</p>
      </div>
      <button className="text-xs font-medium text-amber-600 opacity-0 group-hover:opacity-100 transition-opacity px-3 py-1.5 rounded-lg hover:bg-amber-50">
        {action} →
      </button>
    </div>
  )
}

// ====== 问候语 ======

function getGreeting(creature: CreatureState): string {
  const hour = new Date().getHours()
  const greetings = {
    morning: [
      `Good morning! ${creature.streakDays} days strong.`,
      `Rise and grind! Your competitors are already up.`,
      `New day, new users. Let's go.`,
    ],
    afternoon: [
      `Quick check-in. 2 things need your attention.`,
      `Your growth engine is humming. Keep it up.`,
    ],
    evening: [
      `Wrapping up the day. Here's what happened.`,
      `Good evening! Tomorrow's content is ready for you.`,
    ],
  }

  const period = hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'
  const options = greetings[period]
  // 用日期做种子让每天不一样
  const dayHash = new Date().toDateString().split('').reduce((a, b) => a + b.charCodeAt(0), 0)
  return options[dayHash % options.length]
}

// ====== 自定义图标（简洁线性风格）======

function BellIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-muted"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
}
function SettingsIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-muted"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
}
function PenIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
}
function ChatIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
}
function ZapIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
}
function ShareIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
}
