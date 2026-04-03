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
import { BellIcon, SettingsIcon, PenIcon, ChatIcon, ZapIcon, ShareIcon } from '../components/ui/Icons'
import LogoImg from '../assets/CrabRes-LOGO.png'

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
  const [expSummary, setExpSummary] = useState<any>(null)
  const [recentActions, setRecentActions] = useState<any[]>([])

  // 加载真实数据
  useEffect(() => {
    const load = async () => {
      try {
        const [taskRes, discRes, statRes, expRes, actRes] = await Promise.all([
          api<any>('/growth/tasks').catch(() => ({ tasks: [] })),
          api<any>('/growth/discoveries').catch(() => ({ discoveries: [] })),
          api<any>('/growth/stats').catch(() => null),
          api<any>('/growth/experiments/summary').catch(() => null),
          api<any>('/growth/actions').catch(() => ({ actions: [] })),
        ])
        setTasks(taskRes.tasks || [])
        setDiscoveries(discRes.discoveries || [])
        if (statRes) setStats(statRes)
        if (expRes) setExpSummary(expRes)
        setRecentActions((actRes.actions || []).slice(-5).reverse())
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
        <div className="flex items-center gap-2.5">
          <img src={LogoImg} alt="CrabRes" className="w-7 h-7 rounded-lg" />
          <span className="font-heading font-bold text-primary tracking-tight">CrabRes</span>
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
        <MetricCard value={`+${stats?.growth_rate ?? creature.growthRate}%`} label={creature.market === 'global' ? "growth" : "周增长"} />
        <MetricCard value={`${stats?.total_users ?? creature.totalUsers}`} label={creature.market === 'global' ? "users" : "用户数"} />
        <MetricCard value={`${stats?.streak_days ?? creature.streakDays}d`} label={creature.market === 'global' ? "streak" : "连续增长"} accent />
      </div>

      {/* 核心里程碑 / 活跃战役 */}
      {(stats?.active_campaign_url || localStorage.getItem('crabres_active_tweet')) && (
        <div className="w-full mb-8 animate-fade-in">
          <h3 className="text-[10px] font-bold text-accent uppercase tracking-[0.2em] mb-3 flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-accent rounded-full animate-ping"></span>
            {creature.market === 'global' ? 'Active Growth Campaign' : '当前增长战役'}
          </h3>
          <div className="card border-accent/20 bg-accent/5 p-4 flex items-center justify-between group hover:border-accent/40 transition-all">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center text-accent">
                <ShareIcon />
              </div>
              <div>
                <p className="text-sm font-bold text-primary">Day 1: Global Launch Post</p>
                <p className="text-[10px] text-muted font-mono tracking-tighter uppercase">Status: Live & Tracking</p>
              </div>
            </div>
            <a 
              href={stats?.active_campaign_url || localStorage.getItem('crabres_active_tweet') || '#'} 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-[11px] font-bold text-accent px-4 py-2 rounded-xl border border-accent/20 hover:bg-accent hover:text-white transition-all shadow-sm"
            >
              {creature.market === 'global' ? 'View Live' : '查看实时'} →
            </a>
          </div>
        </div>
      )}

      {/* 今日任务 */}
      <div className="w-full mb-6">
        <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-3 font-heading">
          {creature.market === 'global' ? 'Today' : '今日待办'}
        </h3>
        <div className="space-y-2">
          {tasks.length > 0 ? tasks.map((t: any, i: number) => (
            <TaskCard
              key={t.id || i}
              icon={t.type === 'chat' ? <ChatIcon /> : <PenIcon />}
              title={t.title}
              subtitle={t.subtitle || ''}
              action={t.type === 'chat' ? (creature.market === 'global' ? 'Chat' : '开聊') : (creature.market === 'global' ? 'Do it' : '去执行')}
              onAction={onChat}
            />
          )) : (
            <TaskCard icon={<ChatIcon />} 
              title={creature.market === 'global' ? "Tell CrabRes about your product" : "告诉螃蟹你的产品细节"}
              subtitle={creature.market === 'global' ? "Start a conversation to begin research" : "开始对话以启动深度调研"} 
              action={creature.market === 'global' ? "Chat" : "开聊"}
              onAction={onChat} />
          )}
        </div>
      </div>

      {/* 增长实验追踪 — action→result 闭环 */}
      {(expSummary?.total_actions > 0 || recentActions.length > 0) && (
        <div className="w-full mb-6">
          <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-3 font-heading flex items-center gap-2">
            {creature.market === 'global' ? 'Growth Experiments' : '增长实验'}
            {expSummary?.total_actions > 0 && (
              <span className="text-[10px] font-mono text-brand bg-brand/10 px-2 py-0.5 rounded-full">
                {expSummary.tracked_actions}/{expSummary.total_actions} tracked
              </span>
            )}
          </h3>
          <div className="space-y-2">
            {recentActions.map((a: any, i: number) => (
              <div key={a.id || i} className="flex items-stretch rounded-2xl bg-card border border-border overflow-hidden hover:border-accent/30 transition-all group">
                <div className={`w-1 shrink-0 ${a.status === 'tracked' ? 'bg-emerald-500' : 'bg-accent'}`} />
                <div className="flex items-center gap-3 p-3 flex-1 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center text-xs font-bold text-accent uppercase">
                    {(a.platform || '?').slice(0, 2)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-primary truncate">{a.content_preview || a.url || 'Action recorded'}</p>
                    <p className="text-[10px] text-muted font-mono">
                      {a.platform} · {a.action_type} · {a.status === 'tracked' ? '✓ tracked' : '⏳ pending'}
                    </p>
                  </div>
                </div>
              </div>
            ))}
            {recentActions.length === 0 && expSummary?.total_actions > 0 && (
              <div className="text-center py-4 text-xs text-muted">
                {expSummary.total_actions} actions recorded · {expSummary.learnings_count} learnings extracted
              </div>
            )}
          </div>
        </div>
      )}

      {/* 发现 */}
      <div className="w-full mb-8" id="discoveries-section">
        <h3 className="text-xs font-medium text-muted uppercase tracking-wider mb-3">
          {creature.market === 'global' ? 'Discoveries' : '最新发现'}
        </h3>
        <div className="space-y-2">
          {discoveries.length > 0 ? discoveries.map((d, i) => (
            <DiscoveryCard
              key={i}
              title={d.title || d.change || d.competitor || 'New discovery'}
              action={d.url ? (creature.market === 'global' ? 'View' : '查看') : (creature.market === 'global' ? 'Analyze' : '分析')}
              onAction={() => d.url ? window.open(d.url, '_blank') : onChat()}
            />
          )) : (
            <div className="text-center py-6 text-sm text-muted">
              {creature.market === 'global' 
                ? <>Your growth daemon is scanning...<br /><span className="text-xs">Discoveries will appear here.</span></>
                : <>增长引擎正在全球扫描中...<br /><span className="text-xs">最新发现将显示在这里。</span></>}
            </div>
          )}
        </div>
      </div>

      {/* 底部入口 */}
      <div className="w-full flex gap-3 mt-auto pt-4">
        <button onClick={onChat}
          className="flex-1 py-3.5 rounded-2xl bg-brand text-white text-sm font-heading font-semibold hover:bg-brand-hover transition-all shadow-md hover:shadow-lg">
          {creature.market === 'global' ? 'Talk to CrabRes' : '与螃蟹对话'}
        </button>
        <button onClick={onPlan}
          className="flex-1 py-3.5 rounded-2xl card text-primary text-sm font-heading font-semibold hover:shadow-md transition-all">
          {creature.market === 'global' ? 'Growth Plan' : '增长策略'}
        </button>
      </div>
    </div>
  )
}

// ====== 子组件 ======

function MetricCard({ value, label, accent }: { value: string; label: string; accent?: boolean }) {
  return (
    <div className="text-center group cursor-default">
      <div className={`font-heading text-3xl font-extrabold tracking-tighter transition-all group-hover:scale-110 ${accent ? 'text-brand drop-shadow-[0_0_15px_var(--brand-glow)]' : 'text-primary'}`}>
        {value}
      </div>
      <div className="text-[10px] text-muted mt-1 font-heading font-bold uppercase tracking-widest opacity-60 group-hover:opacity-100 transition-opacity">{label}</div>
    </div>
  )
}

function TaskCard({ icon, title, subtitle, action, onAction }: { icon: React.ReactNode; title: string; subtitle: string; action: string; onAction?: () => void }) {
  return (
    <div className="flex items-stretch rounded-2xl bg-card border border-border hover:border-brand/30 transition-all group hover:shadow-glow overflow-hidden">
      <div className="w-1 bg-brand rounded-l-2xl shrink-0" />
      <div className="flex items-center gap-3 p-4 flex-1 min-w-0">
        <div className="w-9 h-9 rounded-xl bg-brand/10 flex items-center justify-center text-brand shrink-0">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-primary tracking-tight">{title}</p>
          <p className="text-xs text-muted truncate opacity-70 font-mono tracking-tighter">{subtitle}</p>
        </div>
        <button onClick={onAction} className="text-[11px] font-bold text-brand opacity-0 group-hover:opacity-100 transition-all px-3 py-1.5 rounded-lg border border-brand/20 hover:bg-brand hover:text-white">
          {action} →
        </button>
      </div>
    </div>
  )
}

function DiscoveryCard({ title, action, onAction }: { title: string; action: string; onAction?: () => void }) {
  return (
    <div className="flex items-center gap-3 p-4 rounded-2xl bg-card border border-border hover:border-accent/30 transition-all group hover:shadow-lg">
      <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center text-accent shrink-0">
        <ZapIcon />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold text-primary tracking-tight">{title}</p>
      </div>
      <button onClick={onAction} className="text-[11px] font-bold text-accent opacity-0 group-hover:opacity-100 transition-all px-3 py-1.5 rounded-lg border border-accent/20 hover:bg-accent hover:text-white">
        {action} →
      </button>
    </div>
  )
}

// ====== 问候语 ======

function getGreeting(creature: CreatureState): string {
  const hour = new Date().getHours()
  const market = creature.market || 'global'
  
  const greetings = {
    global: {
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
    },
    domestic: {
      morning: [
        `早安！已经连续增长 ${creature.streakDays} 天了。`,
        `别睡了，你的竞争对手已经在偷跑流量了。`,
        `新的一天，去海外赚点美金回来。`,
      ],
      afternoon: [
        `简单播报下：发现 2 个值得注意的增长机会。`,
        `你的增长引擎运转良好，继续保持。`,
      ],
      evening: [
        `复盘时间。今天全球市场发生了这些事。`,
        `晚上好！明天的出海文案我已经帮你写好了。`,
      ],
    }
  }

  const period = hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'
  const options = greetings[market][period]
  // 用日期做种子让每天不一样
  const dayHash = new Date().toDateString().split('').reduce((a, b) => a + b.charCodeAt(0), 0)
  return options[dayHash % options.length]
}

// Icons imported from ../components/ui/Icons
