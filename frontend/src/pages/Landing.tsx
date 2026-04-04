/**
 * Landing Page — Clean, warm, focused
 * Tavily-inspired: cream background, soft shadows, Inter font, no noise
 */

import PixFrontImg from '../assets/pix_fronted.png'
import { EXPERTS } from '../lib/experts'

interface LandingProps {
  onGetStarted: () => void
  onLogin: () => void
  onCompare?: () => void
}

export function Landing({ onGetStarted, onLogin }: LandingProps) {
  return (
    <div className="min-h-screen bg-surface">
      {/* Nav */}
      <nav className="max-w-4xl mx-auto flex items-center justify-between px-6 py-5">
        <span className="text-base font-semibold text-primary tracking-tight">CrabRes</span>
        <div className="flex items-center gap-3">
          <button onClick={onLogin} className="text-sm text-secondary hover:text-primary transition-colors">Log in</button>
          <button onClick={onGetStarted} className="text-sm font-medium text-white bg-brand hover:bg-brand-hover px-4 py-2 rounded-lg transition-all">
            Get started free
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-2xl mx-auto text-center px-6 pt-16 pb-20">
        <div className="mb-6">
          <img src={PixFrontImg} alt="CrabRes" className="w-16 h-16 mx-auto object-contain" />
        </div>

        <h1 className="text-4xl sm:text-5xl font-bold text-primary tracking-tight leading-[1.15] mb-5">
          You build it.<br />
          <span className="text-brand">We grow it.</span>
        </h1>

        <p className="text-lg text-secondary max-w-lg mx-auto mb-8 leading-relaxed">
          The AI growth agent that researches your market, analyzes competitors by name,
          and creates a playbook you can execute — not generic advice.
        </p>

        <button onClick={onGetStarted}
          className="text-base font-medium text-white bg-brand hover:bg-brand-hover px-8 py-3.5 rounded-xl transition-all shadow-md hover:shadow-lg">
          Start free — no credit card
        </button>

        <p className="text-xs text-muted mt-4">Free tier available. No credit card required.</p>
      </section>

      {/* What makes it different */}
      <section className="max-w-3xl mx-auto px-6 pb-20">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          {[
            {
              title: 'Researches first',
              desc: 'Finds your competitors, their traffic sources, and where your users hang out — before giving any advice.',
            },
            {
              title: '13 expert minds',
              desc: 'Economist, psychologist, copywriter, social media strategist — they debate YOUR strategy, not templates.',
            },
            {
              title: 'Writes everything',
              desc: 'Every Reddit post, outreach email, and content plan. Copy-paste ready. Personalized to your product.',
            },
          ].map((item, i) => (
            <div key={i} className="p-5 rounded-xl border border-border bg-[var(--bg-card)] shadow-sm">
              <h3 className="text-sm font-semibold text-primary mb-2">{item.title}</h3>
              <p className="text-sm text-secondary leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="max-w-2xl mx-auto px-6 pb-20">
        <h2 className="text-2xl font-bold text-primary text-center mb-10">How it works</h2>
        <div className="space-y-6">
          {[
            { step: '1', title: 'Describe your product', desc: 'A one-liner is enough. "AI resume optimizer for job seekers at $9.99/mo."' },
            { step: '2', title: 'We research your market', desc: 'Real search data: competitor names, traffic numbers, Reddit discussions, pricing comparisons.' },
            { step: '3', title: 'Experts analyze & debate', desc: 'Market researcher, economist, social media expert — they argue about YOUR best strategy.' },
            { step: '4', title: 'Get your playbook', desc: 'Not "try Reddit." Instead: "Post in r/cscareerquestions Tuesday 9am with this exact title format."' },
          ].map((item, i) => (
            <div key={i} className="flex gap-4 items-start">
              <div className="w-8 h-8 rounded-full bg-brand/10 flex items-center justify-center text-sm font-bold text-brand shrink-0 mt-0.5">
                {item.step}
              </div>
              <div>
                <h3 className="text-sm font-semibold text-primary mb-1">{item.title}</h3>
                <p className="text-sm text-secondary leading-relaxed">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Expert team */}
      <section className="max-w-3xl mx-auto px-6 pb-20">
        <h2 className="text-2xl font-bold text-primary text-center mb-3">Your growth team</h2>
        <p className="text-sm text-secondary text-center mb-8 max-w-md mx-auto">
          You hear one voice. Behind it, 13 specialists are working.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          {Object.entries(EXPERTS).map(([key, expert]) => (
            <div key={key} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-[var(--bg-card)] shadow-sm">
              <img src={expert.avatar} alt={expert.short} className="w-6 h-6 rounded-full object-cover" />
              <span className="text-xs font-medium text-primary">{expert.short}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Not another ChatGPT wrapper */}
      <section className="max-w-2xl mx-auto px-6 pb-20">
        <div className="p-6 rounded-xl border border-border bg-[var(--bg-card)] shadow-sm">
          <h3 className="text-base font-semibold text-primary mb-3">Not another ChatGPT wrapper</h3>
          <div className="space-y-3 text-sm text-secondary leading-relaxed">
            <p>
              <span className="text-muted">ChatGPT:</span> "You should try Reddit marketing and consider SEO for long-term growth."
            </p>
            <p>
              <span className="text-brand font-medium">CrabRes:</span> "Your top competitor <strong>Teal.com</strong> gets 4.8M visits/month, 72% from SEO. Reddit <strong>r/resumes</strong> (850K members) has 12 threads asking for AI resume tools this month. Here's your first post, ready to copy-paste."
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-2xl mx-auto px-6 pb-20 text-center">
        <h2 className="text-2xl font-bold text-primary mb-4">Ready to grow?</h2>
        <p className="text-sm text-secondary mb-6">Tell us about your product. We'll start researching in 30 seconds.</p>
        <button onClick={onGetStarted}
          className="text-base font-medium text-white bg-brand hover:bg-brand-hover px-8 py-3.5 rounded-xl transition-all shadow-md hover:shadow-lg">
          Start free
        </button>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-6 text-center">
        <p className="text-xs text-muted">CrabRes &middot; &copy; {new Date().getFullYear()} &middot; 13 AI experts &middot; 3 deep channels</p>
      </footer>
    </div>
  )
}
