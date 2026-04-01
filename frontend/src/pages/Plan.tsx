/**
 * Growth Plan — 增长计划页面
 * 
 * 展示完整的增长策略、进度和内容日历。
 */

import { useState, useEffect } from 'react'
import type { CreatureState } from '../components/creature/types'
import { api } from '../lib/api'

interface PlanProps {
  creature: CreatureState
  onBack: () => void
}

interface Strategy {
  id: string
  name: string
  status: 'active' | 'in_progress' | 'early' | 'planned'
  channel: string
  metric: string
  detail: string
}

interface CalendarItem {
  day: string
  status: 'done' | 'ready' | 'upcoming'
  title: string
  channel: string
}

export function Plan({ creature, onBack }: PlanProps) {
  const [plan, setPlan] = useState<any>(null)
  const [calendar, setCalendar] = useState<CalendarItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [planRes, calRes] = await Promise.all([
          api<any>('/growth/plan').catch(() => null),
          api<any>('/growth/calendar').catch(() => ({ calendar: [] })),
        ])
        if (planRes) setPlan(planRes)
        setCalendar(calRes.calendar || [])
      } catch {} finally { setLoading(false) }
    }
    load()
  }, [])

  // 从 plan 数据中提取策略，或用默认
  const planContent = plan?.plan?.content || ''
  const strategies: Strategy[] = plan?.plan?.strategies || [
    { id: '1', name: 'Start a conversation', status: 'planned' as const,
      channel: 'Talk to CrabRes', metric: 'Not started',
      detail: 'Tell CrabRes about your product to generate your growth plan' },
  ]

  const progress = plan?.plan?.progress || creature.totalUsers
  const goal = plan?.plan?.goal || 500
  const pct = Math.min(Math.round((progress / goal) * 100), 100)

  return (
    <div className="min-h-screen bg-surface max-w-2xl mx-auto">
      {/* 头部 */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-glass sticky top-0 z-10">
        <button onClick={onBack} className="p-2 rounded-xl hover:bg-hover transition-colors">
          <ArrowLeftIcon />
        </button>
        <div className="flex-1">
          <p className="text-sm font-medium text-primary">Growth Plan</p>
          <p className="text-xs text-muted">v3 · Updated 2 days ago</p>
        </div>
        <button className="btn-ghost !text-xs !py-1.5 !px-3">Export</button>
        <button className="btn-ghost !text-xs !py-1.5 !px-3">Share</button>
      </div>

      <div className="px-4 py-6 space-y-6">
        {/* 进度总览 */}
        <div className="card p-5">
          {/* 阶段进度条 */}
          <div className="flex items-center gap-2 mb-4">
            {['Research', 'Strategy', 'Execute', 'Review'].map((stage, i) => (
              <div key={stage} className="flex items-center gap-2 flex-1">
                <div className={`w-3 h-3 rounded-full shrink-0 ${
                  i < 2 ? 'bg-brand' : i === 2 ? 'bg-brand/40' : 'bg-border'
                }`} />
                <span className={`text-xs ${i <= 2 ? 'text-primary font-medium' : 'text-muted'}`}>
                  {stage}
                </span>
                {i < 3 && <div className={`flex-1 h-px ${i < 2 ? 'bg-brand' : 'bg-border'}`} />}
              </div>
            ))}
          </div>

          {/* 数字 */}
          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-3xl font-bold text-primary">{progress}</span>
            <span className="text-sm text-muted">/ {goal} users</span>
            <span className="text-xs text-muted ml-auto">Week 3 of 12</span>
          </div>

          {/* 进度条 */}
          <div className="w-full h-2 rounded-full bg-border overflow-hidden">
            <div
              className="h-full rounded-full bg-brand transition-all duration-1000"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-xs text-muted mt-1">{pct}% · Budget: $200/mo</p>
        </div>

        {/* 策略卡片 */}
        <div>
          <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-3">Strategies</h3>
          <div className="space-y-3">
            {strategies.map(s => (
              <div key={s.id} className="card p-4 hover:border-brand/20 transition-colors">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm font-medium text-primary">{s.name}</span>
                  <StatusBadge status={s.status} />
                </div>
                <p className="text-xs text-muted mb-1">{s.channel}</p>
                <p className="text-xs text-secondary">{s.detail}</p>
                <div className="flex items-center justify-between mt-3">
                  <span className="text-xs font-medium text-brand">{s.metric}</span>
                  <button className="text-xs text-muted hover:text-primary transition-colors">
                    Details →
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 内容日历 */}
        <div>
          <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-3 font-heading">This week</h3>
          {calendar.length > 0 ? (
            <div className="space-y-2">
              {calendar.map((item, i) => (
              <div key={i} className="flex items-center gap-3 p-3 rounded-xl hover:bg-hover transition-colors">
                <div className="w-10 text-center shrink-0">
                  <span className="text-xs font-medium text-muted">{item.day}</span>
                </div>
                <div className={`w-2 h-2 rounded-full shrink-0 ${
                  item.status === 'done' ? 'bg-emerald-500' :
                  item.status === 'ready' ? 'bg-brand' : 'bg-border'
                }`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-primary truncate">{item.title}</p>
                  <p className="text-xs text-muted">{item.channel}</p>
                </div>
                {item.status === 'done' && (
                  <span className="text-xs text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">Published</span>
                )}
                {item.status === 'ready' && (
                  <button className="text-xs text-brand bg-brand/8 px-2 py-0.5 rounded-full hover:bg-brand/15 transition-colors">
                    Review →
                  </button>
                )}
              </div>
            ))}
          </div>
          ) : (
            <div className="card p-6 text-center">
              <p className="text-sm text-muted">No content scheduled yet.</p>
              <p className="text-xs text-muted mt-1">Chat with CrabRes to generate your content calendar.</p>
            </div>
          )}
        </div>

        {/* Agent 输出的完整计划 */}
        {planContent && (
          <div>
            <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-3 font-heading">Full Plan</h3>
            <div className="card p-5">
              <div className="text-sm text-secondary whitespace-pre-wrap leading-relaxed">
                {planContent}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ====== 子组件 ======

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: 'bg-emerald-50 text-emerald-600',
    in_progress: 'bg-amber-50 text-amber-600',
    early: 'bg-blue-50 text-blue-600',
    planned: 'bg-gray-50 text-gray-500',
  }
  const labels: Record<string, string> = {
    active: 'Active',
    in_progress: 'In progress',
    early: 'Early stage',
    planned: 'Planned',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${styles[status] || styles.planned}`}>
      {labels[status] || status}
    </span>
  )
}

function ArrowLeftIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-muted"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>
}
