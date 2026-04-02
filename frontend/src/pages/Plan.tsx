/**
 * Growth Plan — Playbook 执行面板
 * 
 * 不再是纯文本计划。是 Phase→Step 的可视化执行面板。
 * 每个 Step 可以标记完成、查看详情、记录笔记。
 */

import { useState, useEffect } from 'react'
import type { CreatureState } from '../components/creature/types'
import { api } from '../lib/api'
import { ArrowLeftIcon } from '../components/ui/Icons'

interface PlanProps {
  creature: CreatureState
  onBack: () => void
}

export function Plan({ creature, onBack }: PlanProps) {
  const [playbooks, setPlaybooks] = useState<any[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api<any>('/playbooks')
        setPlaybooks(res.playbooks || [])
        const active = (res.playbooks || []).find((p: any) => p.status === 'active')
        if (active) setActiveId(active.id)
      } catch {} finally { setLoading(false) }
    }
    load()
  }, [])

  const activePb = playbooks.find(p => p.id === activeId)
  const isGlobal = creature.market === 'global'

  const updateStep = async (pbId: string, phaseIdx: number, stepIdx: number, status: string) => {
    try {
      await api('/playbooks/' + pbId + '/step', {
        method: 'POST',
        body: JSON.stringify({ phase_idx: phaseIdx, step_idx: stepIdx, status, notes: '' }),
      })
      // Refresh
      const res = await api<any>('/playbooks')
      setPlaybooks(res.playbooks || [])
    } catch {}
  }

  return (
    <div className="min-h-screen bg-surface">
      {/* 头部 */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-glass sticky top-0 z-10 max-w-3xl mx-auto">
        <button onClick={onBack} className="p-2 rounded-xl hover:bg-hover transition-colors">
          <ArrowLeftIcon />
        </button>
        <div className="flex-1">
          <p className="text-sm font-heading font-bold text-primary">
            {isGlobal ? 'Growth Playbooks' : '增长执行手册'}
          </p>
          <p className="text-[10px] text-muted font-mono uppercase">
            {playbooks.length > 0 
              ? `${playbooks.length} playbook${playbooks.length > 1 ? 's' : ''}`
              : isGlobal ? 'Chat with CrabRes to generate playbooks' : '和 CrabRes 对话生成执行手册'}
          </p>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">

        {/* 空状态 */}
        {!loading && playbooks.length === 0 && (
          <div className="text-center py-16">
            <div className="text-4xl mb-4">📋</div>
            <p className="text-lg font-heading font-bold text-primary mb-2">
              {isGlobal ? 'No playbooks yet' : '还没有执行手册'}
            </p>
            <p className="text-sm text-muted max-w-sm mx-auto mb-6">
              {isGlobal 
                ? 'Tell CrabRes about your product. It will research your market and create structured growth playbooks with step-by-step instructions.'
                : '告诉 CrabRes 你的产品，它会研究市场并创建结构化的增长执行手册。'}
            </p>
            <button onClick={onBack} className="btn-primary">
              {isGlobal ? 'Start a conversation →' : '开始对话 →'}
            </button>
          </div>
        )}

        {/* Playbook 列表（非激活的） */}
        {playbooks.filter(p => p.id !== activeId).length > 0 && (
          <div>
            <h3 className="text-xs font-heading font-medium text-muted uppercase tracking-wider mb-3">
              {isGlobal ? 'Available Playbooks' : '可用的执行手册'}
            </h3>
            <div className="space-y-2">
              {playbooks.filter(p => p.id !== activeId).map(pb => {
                const totalSteps = (pb.phases || []).reduce((s: number, ph: any) => s + (ph.steps?.length || 0), 0)
                const doneSteps = (pb.phases || []).reduce((s: number, ph: any) => s + (ph.steps || []).filter((st: any) => st.status === 'done').length, 0)
                return (
                  <div key={pb.id} className="card p-4 hover:border-brand/20 transition-colors">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-bold text-primary">{pb.name}</p>
                        <p className="text-xs text-muted">{pb.description?.slice(0, 80)}</p>
                        <p className="text-[10px] text-muted mt-1">{totalSteps} steps · {pb.total_budget || '$0'} · {pb.expected_timeline || 'TBD'}</p>
                      </div>
                      <button
                        onClick={async () => {
                          try {
                            await api('/playbooks/' + pb.id + '/activate', { method: 'POST' })
                            setActiveId(pb.id)
                          } catch {}
                        }}
                        className="text-xs font-bold text-brand px-3 py-1.5 rounded-lg border border-brand/20 hover:bg-brand hover:text-white transition-all"
                      >
                        {isGlobal ? 'Activate' : '启动'} →
                      </button>
                    </div>
                    {doneSteps > 0 && (
                      <div className="mt-2 h-1 rounded-full bg-border overflow-hidden">
                        <div className="h-full bg-brand rounded-full" style={{ width: `${totalSteps ? (doneSteps/totalSteps*100) : 0}%` }} />
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* 激活的 Playbook 详情 */}
        {activePb && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <div className="w-2 h-2 rounded-full bg-brand animate-pulse" />
              <h2 className="text-lg font-heading font-bold text-primary">{activePb.name}</h2>
            </div>

            {activePb.description && (
              <p className="text-sm text-secondary mb-4">{activePb.description}</p>
            )}

            {/* 总进度 */}
            {(() => {
              const total = (activePb.phases || []).reduce((s: number, ph: any) => s + (ph.steps?.length || 0), 0)
              const done = (activePb.phases || []).reduce((s: number, ph: any) => s + (ph.steps || []).filter((st: any) => st.status === 'done').length, 0)
              const pct = total ? Math.round(done / total * 100) : 0
              return (
                <div className="card p-4 mb-6">
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-2xl font-heading font-bold text-primary">{pct}%</span>
                    <span className="text-xs text-muted">{done}/{total} steps completed</span>
                  </div>
                  <div className="h-2 rounded-full bg-border overflow-hidden">
                    <div className="h-full bg-brand rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
                  </div>
                  {activePb.total_budget && (
                    <p className="text-[10px] text-muted mt-2">
                      Budget: {activePb.total_budget} · Timeline: {activePb.expected_timeline || 'TBD'}
                    </p>
                  )}
                </div>
              )
            })()}

            {/* Phases & Steps */}
            <div className="space-y-6">
              {(activePb.phases || []).map((phase: any, phaseIdx: number) => (
                <div key={phaseIdx}>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-6 h-6 rounded-full bg-brand/10 flex items-center justify-center text-[10px] font-bold text-brand">
                      {phaseIdx + 1}
                    </div>
                    <h3 className="text-sm font-heading font-bold text-primary">{phase.name}</h3>
                    {phase.duration && (
                      <span className="text-[10px] text-muted font-mono">{phase.duration}</span>
                    )}
                  </div>

                  <div className="space-y-2 ml-3 border-l-2 border-border pl-4">
                    {(phase.steps || []).map((step: any, stepIdx: number) => {
                      const isDone = step.status === 'done'
                      const isActive = step.status === 'in_progress'
                      return (
                        <StepCard
                          key={stepIdx}
                          step={step}
                          isDone={isDone}
                          isActive={isActive}
                          isGlobal={isGlobal}
                          onToggle={() => {
                            const newStatus = isDone ? 'pending' : 'done'
                            updateStep(activePb.id, phaseIdx, stepIdx, newStatus)
                          }}
                        />
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>

            {/* Risk factors */}
            {activePb.risk_factors?.length > 0 && (
              <div className="mt-6">
                <h3 className="text-xs font-heading font-medium text-muted uppercase tracking-wider mb-2">
                  {isGlobal ? 'Risk Factors' : '风险提示'}
                </h3>
                <div className="card p-4 space-y-1">
                  {activePb.risk_factors.map((r: string, i: number) => (
                    <p key={i} className="text-xs text-secondary flex gap-2">
                      <span className="text-accent shrink-0">⚠️</span>{r}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StepCard({ step, isDone, isActive, isGlobal, onToggle }: { 
  step: any; isDone: boolean; isActive: boolean; isGlobal: boolean; onToggle: () => void 
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`rounded-xl border transition-all ${
      isDone ? 'bg-emerald-50/50 border-emerald-200 dark:bg-emerald-500/5 dark:border-emerald-500/20' 
      : isActive ? 'bg-brand/5 border-brand/20' 
      : 'bg-card border-border hover:border-brand/20'
    }`}>
      {/* Step 头部 */}
      <div className="flex items-center gap-3 p-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <button
          onClick={(e) => { e.stopPropagation(); onToggle() }}
          className={`w-5 h-5 rounded-md border-2 shrink-0 flex items-center justify-center transition-all ${
            isDone ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-border hover:border-brand'
          }`}
        >
          {isDone && <CheckIcon />}
        </button>
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-medium ${isDone ? 'line-through text-muted' : 'text-primary'}`}>
            {step.title}
          </p>
          {step.duration && (
            <p className="text-[10px] text-muted">{step.duration} · {step.budget || '$0'}</p>
          )}
        </div>
        <span className="text-muted text-xs shrink-0">{expanded ? '−' : '+'}</span>
      </div>

      {/* 展开详情 */}
      {expanded && (
        <div className="px-3 pb-3 pt-0 space-y-2 animate-fade-in">
          {step.detail && (
            <p className="text-xs text-secondary leading-relaxed">{step.detail}</p>
          )}
          {step.tools?.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {step.tools.map((t: string, i: number) => (
                <span key={i} className="text-[10px] px-2 py-0.5 rounded-full bg-brand/10 text-brand">{t}</span>
              ))}
            </div>
          )}
          {step.output && (
            <p className="text-[10px] text-muted">
              <span className="font-bold">{isGlobal ? 'Output:' : '产出:'}</span> {step.output}
            </p>
          )}
          {step.success_criteria && (
            <p className="text-[10px] text-emerald-600">
              <span className="font-bold">✓ {isGlobal ? 'Success:' : '成功标准:'}</span> {step.success_criteria}
            </p>
          )}
          {step.common_mistakes?.length > 0 && (
            <div className="text-[10px] text-accent space-y-0.5">
              <span className="font-bold">⚠️ {isGlobal ? 'Avoid:' : '避坑:'}</span>
              {step.common_mistakes.map((m: string, i: number) => (
                <p key={i} className="ml-4">• {m}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function CheckIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
}
