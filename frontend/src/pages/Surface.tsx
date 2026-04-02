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

/**
 * 精准计算 X (Twitter) 字符长度
 * 规则：
 * 1. 基础 ASCII 字符 (0-127): 1 字符
 * 2. 非 ASCII (中文, Emojis, 扩展拉丁等): 2 字符
 * 3. 链接 (http/https): 无论长短统一算 23 字符
 */
function calculateTwitterLength(text: string): number {
  if (!text) return 0
  
  let length = 0
  // 1. 处理链接
  const urlRegex = /https?:\/\/[^\s]+/g
  const textWithoutUrls = text.replace(urlRegex, () => {
    length += 23
    return ""
  })

  // 2. 处理剩余字符
  for (const char of textWithoutUrls) {
    // 使用 codePointAt 处理 4 字节 Emoji (如 🦀)
    const codePoint = char.codePointAt(0) || 0
    if (codePoint <= 127) {
      length += 1
    } else {
      length += 2
    }
  }
  
  // 考虑到回车符在某些环境下可能被算作 2 字符 (CRLF)，我们强制按 1 字符计，但保留余量
  return length
}

export function Surface({ creature, onChat, onPlan, onSettings }: SurfaceProps) {
  const greeting = getGreeting(creature)
  const [discoveries, setDiscoveries] = useState<any[]>([])
  const [tasks, setTasks] = useState<any[]>([])
  const [stats, setStats] = useState<any>(null)
  const [hunterBullets, setHunterBullets] = useState<Record<number, string>>({})
  const [hunterLoading, setHunterLoading] = useState<Record<number, boolean>>({})

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

  const generateBullet = async (index: number) => {
    setHunterLoading(prev => ({ ...prev, [index]: true }))
    try {
      const res = await api<any[]>('/agent/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: `Write a ready-to-publish X/Twitter post (under 280 chars) about my product. Make it punchy, authentic, and growth-focused. Target: indie hackers and founders. Include 2-3 relevant hashtags. Post #${index + 1}.`,
        }),
      })
      const content = res.find((r: any) => r.type === 'message')?.content
        || res[res.length - 1]?.content
        || 'Could not generate. Try again.'
      setHunterBullets(prev => ({ ...prev, [index]: content }))
    } catch {
      setHunterBullets(prev => ({ ...prev, [index]: '⚠️ Generation failed. Please try again.' }))
    } finally {
      setHunterLoading(prev => ({ ...prev, [index]: false }))
    }
  }

  return (
    <div className="min-h-screen bg-surface bg-grid bg-noise flex flex-col items-center px-4 py-8 max-w-lg mx-auto relative z-10">
      {/* 顶部栏 */}
      <div className="w-full flex items-center justify-between mb-8">
        <div className="flex items-center gap-2.5">
          <span className="text-xl">🦀</span>
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

      {/* 增长猎手 (Growth Hunter) - 新模块 */}
      <div className="w-full mb-8 relative">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-medium text-brand uppercase tracking-widest font-heading flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-brand"></span>
            </span>
            {creature.market === 'global' ? 'Growth Hunter' : '增长猎手'}
          </h3>
          <span className="text-[10px] text-muted font-mono uppercase tracking-tighter">Hunter Mode: Active</span>
        </div>
        
        <div className="card bg-brand/5 border-brand/20 p-5 overflow-hidden relative group">
          {/* 背景雷达装饰 */}
          <div className="absolute -right-10 -top-10 w-40 h-40 border border-brand/10 rounded-full animate-pulse pointer-events-none"></div>
          <div className="absolute -right-5 -top-5 w-20 h-20 border border-brand/5 rounded-full pointer-events-none"></div>
          
          <div className="relative z-10">
            <p className="text-sm font-bold text-primary mb-1">
              {creature.market === 'global' ? '5 Targeted Leads Found' : '发现 5 个精准猎杀目标'}
            </p>
            <p className="text-xs text-secondary mb-4 opacity-80 leading-relaxed">
              {creature.market === 'global' 
                ? 'Experts identified founders struggling with distribution. Ready for engagement.' 
                : '专家团锁定了正在为分发发愁的创始人。已准备好“降维打击”话术。'}
            </p>
            
            <div className="space-y-3">
              {[0, 1, 2].map(i => {
                const bullet = hunterBullets[i]
                const loading = hunterLoading[i]
                // 核心：使用精准的 Twitter 长度算法
                const charCount = calculateTwitterLength(bullet || "")
                const isOverLimit = charCount > 280

                return (
                  <div key={i} className="rounded-xl bg-black/20 border border-white/5 overflow-hidden transition-all">
                    <div className="flex items-center justify-between p-3 cursor-pointer group/item hover:bg-black/20"
                      onClick={() => !bullet && generateBullet(i)}>
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center text-brand text-xs font-bold">#0{i+1}</div>
                        <div>
                          <div className="text-xs font-bold text-primary">Target Group: {i === 0 ? 'r/SaaS' : i === 1 ? 'r/IndieHackers' : 'X/Founders'}</div>
                          <div className="text-[10px] text-muted">Awaiting your response...</div>
                        </div>
                      </div>
                      {!bullet ? (
                        <button className="text-[10px] font-bold text-brand px-3 py-1.5 rounded-lg border border-brand/20 hover:bg-brand hover:text-white transition-all disabled:opacity-50"
                          disabled={loading}>
                          {loading ? (creature.market === 'global' ? 'GENERATING...' : '生成中...') : (creature.market === 'global' ? 'GENERATE BULLET' : '生成子弹')}
                        </button>
                      ) : (
                        <div className={`text-[10px] font-mono font-bold ${isOverLimit ? 'text-red-500 animate-pulse' : 'text-success'}`}>
                          {charCount}/280
                        </div>
                      )}
                    </div>
                    
                    {bullet && (
                      <div className="px-4 pb-4 animate-fade-in">
                        <textarea 
                          value={bullet}
                          onChange={(e) => setHunterBullets(prev => ({ ...prev, [i]: e.target.value }))}
                          className={`w-full bg-black/40 border p-3 rounded-lg text-xs font-mono leading-relaxed transition-colors focus:outline-none ${isOverLimit ? 'border-red-500/50 focus:border-red-500' : 'border-white/10 focus:border-brand/50'}`}
                          rows={4}
                        />
                        <div className="flex justify-between items-center mt-3">
                           <p className={`text-[9px] italic font-medium ${isOverLimit ? 'text-red-400' : 'text-muted'}`}>
                             {isOverLimit 
                               ? (creature.market === 'global' ? '❌ EXCEEDS X LIMIT!' : '❌ 超出 X 平台限制！') 
                               : (creature.market === 'global' ? '✓ Ready to send' : '✓ 已就绪')}
                           </p>
                           <button className="btn-primary !px-4 !py-1.5 !text-[10px] disabled:opacity-50 disabled:bg-gray-700 disabled:cursor-not-allowed" 
                             disabled={isOverLimit || loading}
                             onClick={async () => {
                               try {
                                 const res = await api<any>('/execute/prepare', {
                                   method: 'POST',
                                   body: JSON.stringify({ platform: 'x', content: bullet, action_type: 'post' }),
                                 })
                                 if (res.url) {
                                   navigator.clipboard.writeText(bullet)
                                   window.open(res.url, '_blank')
                                 }
                               } catch {
                                 navigator.clipboard.writeText(bullet)
                                 window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(bullet.slice(0, 270))}`, '_blank')
                               }
                             }}>
                             {creature.market === 'global' ? 'SEND NOW' : '立即发送'}
                           </button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            
            <button className="w-full mt-4 py-2 text-[11px] font-bold text-muted hover:text-brand transition-colors uppercase tracking-widest border-t border-white/5 pt-4"
              onClick={onPlan}>
              {creature.market === 'global' ? 'View Hunter Dashboard →' : '进入猎手中心 →'}
            </button>
          </div>
        </div>
      </div>

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
    <div className="flex items-center gap-3 p-4 rounded-2xl bg-card border border-border hover:border-brand/30 transition-all group hover:shadow-glow">
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
