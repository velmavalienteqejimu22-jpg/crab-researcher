/**
 * Landing Page v2 — 一鸣惊人
 * 
 * 设计原则：
 * - 渐变背景 + 网格纹理 + 噪点（不是纯白）
 * - Hero 区有生物体动画作为视觉焦点
 * - 每个区块有滚动进入动画
 * - Space Grotesk 标题 + DM Sans 正文
 * - 玻璃态卡片 + hover 提升
 */

import { useState } from 'react'
import { CreatureRenderer } from '../components/creature/CreatureRenderer'
import { generateCreature, SPECIES_CONFIG } from '../components/creature/types'

interface LandingProps {
  onGetStarted: () => void
  onLogin: () => void
}

export function Landing({ onGetStarted, onLogin }: LandingProps) {
  const creatures = ['crab', 'octopus', 'jellyfish', 'pufferfish', 'seahorse'] as const
  const heroCreature = generateCreature('hero', 'saas')
  heroCreature.mood = 'happy'

  return (
    <div className="min-h-screen bg-surface bg-grid bg-noise relative z-10">
      {/* 顶部渐变光晕 */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-brand/5 rounded-full blur-[120px] pointer-events-none" />

      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-5xl mx-auto relative z-10">
        <div className="flex items-center gap-2.5">
          <span className="text-xl">🦀</span>
          <span className="font-heading font-bold text-primary tracking-tight">CrabRes</span>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={onLogin} className="btn-ghost !text-sm">Log in</button>
          <button onClick={onGetStarted} className="btn-primary !text-sm">Start free →</button>
        </div>
      </nav>

      {/* Hero */}
      <section className="text-center px-4 pt-20 pb-24 max-w-2xl mx-auto relative z-10">
        {/* 生物体浮动在标题上方 */}
        <div className="mb-6 animate-float">
          <CreatureRenderer creature={heroCreature} size={80} />
        </div>

        <h1 className="font-heading text-5xl sm:text-6xl font-bold tracking-tight leading-[1.1] mb-5">
          <span className="text-primary">You build it.</span><br />
          <span className="text-gradient">We grow it.</span>
        </h1>

        <p className="text-lg text-secondary max-w-md mx-auto mb-8 leading-relaxed">
          The AI growth agent that researches your market, validates your direction,
          and writes every post, email, and plan — for you.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-4">
          <button onClick={onGetStarted}
            className="btn-primary !text-base !py-3.5 !px-8 !rounded-xl shadow-lg hover:shadow-xl transition-shadow">
            Start free — no credit card →
          </button>
        </div>

        <p className="text-xs text-muted">Join 300+ products growing with CrabRes</p>
      </section>

      {/* 三个核心卖点 */}
      <section className="px-4 pb-24 max-w-4xl mx-auto relative z-10">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          {[
            { icon: '🔍', title: 'Validates first', desc: "Won't waste your time on a bad direction. Tells you the truth — backed by real competitor data." },
            { icon: '🧠', title: '13 expert minds', desc: 'Economist, psychologist, copywriter, designer — a full growth team debating YOUR strategy.' },
            { icon: '✍️', title: 'Writes everything', desc: 'Every Reddit post, outreach email, landing page. Copy-paste ready. Not templates — personalized.' },
          ].map((f, i) => (
            <div key={i} className="card p-7 text-center group animate-fade-in" style={{ animationDelay: `${i * 0.1}s`, opacity: 0 }}>
              <div className="text-3xl mb-4">{f.icon}</div>
              <h3 className="font-heading font-semibold text-primary text-lg mb-2">{f.title}</h3>
              <p className="text-sm text-secondary leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 群聊预览 */}
      <section className="px-4 pb-24 max-w-3xl mx-auto relative z-10">
        <h2 className="font-heading text-3xl font-bold text-primary text-center mb-3">
          A growth team that works for you
        </h2>
        <p className="text-sm text-secondary text-center mb-10 max-w-md mx-auto">
          13 AI experts discuss your product in a roundtable.
          You see one conversation. Behind it, 13 minds are thinking.
        </p>

        {/* 模拟群聊界面 */}
        <div className="card p-5 space-y-3 card-glow">
          {[
            { icon: '🔍', name: 'Market Researcher', color: '#0EA5E9', msg: '"Found 3 competitors: FocusBear ($4.99/mo, 12K users), Freedom ($8.99/mo, 500K users), Cold Turkey ($39 one-time). Your pricing gap is between $5-9/mo."' },
            { icon: '💰', name: 'Economist', color: '#10B981', msg: '"At $50/mo budget, paid ads are out. Reddit organic + cold DM is your best ROI path. Estimated CAC: $0.80."' },
            { icon: '🧠', name: 'Psychologist', color: '#14B8A6', msg: '"Remote workers\' core anxiety is guilt about wasted time. Frame FocusFlow as \'proof you\'re productive\' — not just a blocker."' },
            { icon: '🦀', name: 'CrabRes', color: '#F97316', msg: '"Based on the research: lead with the \'deep work tracker\' angle, not \'website blocker.\' Here\'s your first Reddit post..."' },
          ].map((m, i) => (
            <div key={i} className="flex gap-2.5 animate-fade-in" style={{ animationDelay: `${0.3 + i * 0.15}s`, opacity: 0 }}>
              <div className="w-7 h-7 shrink-0 rounded-full flex items-center justify-center text-xs mt-0.5"
                style={{ background: m.color + '15', color: m.color }}>
                {m.icon}
              </div>
              <div>
                <p className="text-[10px] font-heading font-medium" style={{ color: m.color }}>{m.name}</p>
                <p className="text-sm text-secondary leading-relaxed">{m.msg}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 生物体展示 */}
      <section className="px-4 pb-24 max-w-4xl mx-auto text-center relative z-10">
        <h2 className="font-heading text-3xl font-bold text-primary mb-3">Your growth companion</h2>
        <p className="text-sm text-secondary mb-10 max-w-md mx-auto">
          10 unique species. Each reflects your product. It grows as you grow.
        </p>
        <div className="flex flex-wrap justify-center gap-6">
          {creatures.map((species, i) => {
            const c = generateCreature(species, 'saas')
            c.species = species
            c.mood = 'happy'
            return (
              <div key={species} className="flex flex-col items-center gap-2 animate-fade-in" style={{ animationDelay: `${i * 0.1}s`, opacity: 0 }}>
                <CreatureRenderer creature={c} size={56} animate={false} />
                <span className="text-xs text-muted font-heading">{SPECIES_CONFIG[species].displayName}</span>
              </div>
            )
          })}
        </div>
      </section>

      {/* 社会证明 */}
      <section className="px-4 pb-24 max-w-3xl mx-auto relative z-10">
        <h2 className="font-heading text-3xl font-bold text-primary text-center mb-10">What users say</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            { quote: "CrabRes told me my product idea had no market. Saved me 6 months of wasted effort.", author: "@indie_maker" },
            { quote: "I copy-pasted the Reddit posts it wrote. Got 40 upvotes and 12 signups from ONE post.", author: "@saas_builder" },
            { quote: "The economist calculated my budget would burn out on ads. Saved $500 by going organic first.", author: "@bootstrapper_22" },
            { quote: "It suggested I cold-DM career coaches for partnerships. Never would have thought of that myself.", author: "@job_tool_dev" },
          ].map((t, i) => (
            <div key={i} className="card p-5 animate-fade-in" style={{ animationDelay: `${i * 0.1}s`, opacity: 0 }}>
              <p className="text-sm text-primary leading-relaxed mb-3">"{t.quote}"</p>
              <p className="text-xs text-muted font-mono">{t.author}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 定价 */}
      <section className="px-4 pb-24 max-w-3xl mx-auto relative z-10">
        <h2 className="font-heading text-3xl font-bold text-primary text-center mb-2">Simple pricing</h2>
        <p className="text-sm text-muted text-center mb-10">Start free. Upgrade when you're ready.</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { name: 'Free', price: '$0', period: '', features: ['1 project', 'Basic research', '5 chats/day'], cta: 'Start free', hl: false },
            { name: 'Pro', price: '$29', period: '/mo', features: ['3 projects', '13 experts + 8 skills', 'Unlimited chats', 'Daily tasks', 'Competitor monitoring'], cta: 'Start 14-day trial', hl: true },
            { name: 'Team', price: '$79', period: '/mo', features: ['Unlimited projects', 'Everything in Pro', 'API + MCP access', 'Team collaboration'], cta: 'Contact us', hl: false },
          ].map((p, i) => (
            <div key={i} className={`card p-6 ${p.hl ? 'border-brand ring-1 ring-brand/20 card-glow' : ''}`}>
              {p.hl && <span className="text-[10px] font-heading font-semibold text-brand mb-2 block uppercase tracking-wider">Most popular</span>}
              <h3 className="font-heading font-semibold text-primary text-lg">{p.name}</h3>
              <div className="flex items-baseline gap-0.5 mt-1 mb-5">
                <span className="font-heading text-4xl font-bold text-primary">{p.price}</span>
                <span className="text-sm text-muted">{p.period}</span>
              </div>
              <ul className="space-y-2 mb-6">
                {p.features.map(f => (
                  <li key={f} className="text-sm text-secondary flex items-center gap-2">
                    <span className="text-brand text-xs">✓</span>{f}
                  </li>
                ))}
              </ul>
              <button onClick={onGetStarted}
                className={`w-full py-2.5 rounded-lg text-sm font-heading font-medium transition-all ${
                  p.hl ? 'btn-primary' : 'bg-hover text-primary hover:bg-border'
                }`}>
                {p.cta}
              </button>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted text-center mt-4">Pro trial is free for 14 days. No credit card required.</p>
      </section>

      {/* FAQ */}
      <section className="px-4 pb-24 max-w-2xl mx-auto relative z-10">
        <h2 className="font-heading text-3xl font-bold text-primary text-center mb-10">Questions</h2>
        <div className="space-y-3">
          {[
            { q: "How is this different from ChatGPT?", a: "ChatGPT doesn't research your specific competitors, forgets everything next session, and gives the same advice to everyone. CrabRes searches the real internet, remembers your product across weeks, and has 13 specialized experts with different perspectives." },
            { q: "Will it work for my niche?", a: "CrabRes doesn't use templates. It researches YOUR market and YOUR competitors. If your niche is too small, it will honestly tell you — and suggest pivots." },
            { q: "What if I have zero marketing experience?", a: "That's exactly who this is for. Describe your product, and CrabRes does the rest. Every task is copy-paste simple." },
            { q: "Can I cancel anytime?", a: "Yes. Cancel with one click. Downgrade to Free keeps all your data." },
          ].map((item, i) => (
            <FaqItem key={i} q={item.q} a={item.a} />
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="text-center px-4 pb-24 relative z-10">
        <h2 className="font-heading text-3xl font-bold text-primary mb-5">Stop guessing.<br />Start growing.</h2>
        <button onClick={onGetStarted}
          className="btn-primary !text-base !py-3.5 !px-8 !rounded-xl shadow-lg">
          Start free →
        </button>
      </section>

      {/* Footer */}
      <footer className="text-center py-8 border-t border-border relative z-10">
        <p className="text-xs text-muted">🦀 CrabRes · © 2026 · Privacy · Terms</p>
      </footer>
    </div>
  )
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="card overflow-hidden">
      <button onClick={() => setOpen(!open)}
        className="w-full p-4 text-left flex items-center justify-between hover:bg-hover transition-colors">
        <span className="text-sm font-heading font-medium text-primary pr-4">{q}</span>
        <span className="text-muted text-sm shrink-0">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 text-sm text-secondary leading-relaxed animate-fade-in">
          {a}
        </div>
      )}
    </div>
  )
}
