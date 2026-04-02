/**
 * RoundtableSimulation — 专家圆桌可视化
 * 
 * 设计：环形布局 + 脉冲连接线 + 活跃专家高亮
 * 中心是 CrabRes 指挥官，13 位专家环绕
 * 当某专家在思考时，它会放大 + 连接线亮起 + 脉冲动画
 */

import { EXPERTS } from '../../lib/experts'

interface RoundtableSimulationProps {
  activeExpertId?: string
  isSimulating?: boolean
}

export function RoundtableSimulation({ activeExpertId, isSimulating }: RoundtableSimulationProps) {
  const expertKeys = Object.keys(EXPERTS)
  const size = 280
  const cx = size / 2
  const cy = size / 2
  const outerR = 110
  const innerR = 24

  return (
    <div className="flex flex-col items-center mb-6 animate-fade-in">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="overflow-visible">
        <defs>
          {/* 中心光晕 */}
          <radialGradient id="center-glow">
            <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.15" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="0" />
          </radialGradient>
          {/* 外环渐变 */}
          <radialGradient id="ring-gradient">
            <stop offset="85%" stopColor="transparent" />
            <stop offset="100%" stopColor="var(--brand)" stopOpacity="0.04" />
          </radialGradient>
        </defs>

        {/* 背景装饰环 */}
        <circle cx={cx} cy={cy} r={outerR + 20} fill="url(#ring-gradient)" />
        <circle cx={cx} cy={cy} r={outerR} fill="none" stroke="var(--border-default)" strokeWidth="1" strokeDasharray="3 6" opacity="0.5" />
        <circle cx={cx} cy={cy} r={outerR - 30} fill="none" stroke="var(--border-default)" strokeWidth="0.5" strokeDasharray="2 8" opacity="0.3" />

        {/* 连接线 — 从活跃专家到中心 */}
        {expertKeys.map((key, i) => {
          const angle = (i / expertKeys.length) * 2 * Math.PI - Math.PI / 2
          const ex = cx + outerR * Math.cos(angle)
          const ey = cy + outerR * Math.sin(angle)
          const isActive = activeExpertId === key
          const expert = EXPERTS[key]

          if (!isActive) return null
          return (
            <g key={`line-${key}`}>
              {/* 连接线 */}
              <line x1={cx} y1={cy} x2={ex} y2={ey}
                stroke={expert.color} strokeWidth="2" strokeDasharray="4 3" opacity="0.6">
                <animate attributeName="stroke-dashoffset" from="0" to="-14" dur="0.8s" repeatCount="indefinite" />
              </line>
              {/* 线上的脉冲光点 */}
              <circle r="3" fill={expert.color} opacity="0.8">
                <animateMotion dur="1s" repeatCount="indefinite"
                  path={`M${cx},${cy} L${ex},${ey}`} />
              </circle>
            </g>
          )
        })}

        {/* 中心光晕 */}
        <circle cx={cx} cy={cy} r={40} fill="url(#center-glow)">
          {isSimulating && (
            <animate attributeName="r" values="35;45;35" dur="2s" repeatCount="indefinite" />
          )}
        </circle>

        {/* 中心 — CrabRes 指挥官 */}
        <circle cx={cx} cy={cy} r={innerR} fill="var(--bg-card)" stroke="var(--brand)" strokeWidth="2.5" />
        <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="central" fontSize="18">🦀</text>
        {isSimulating && (
          <circle cx={cx} cy={cy} r={innerR + 4} fill="none" stroke="var(--brand)" strokeWidth="1" opacity="0.3">
            <animate attributeName="r" values={`${innerR + 2};${innerR + 10};${innerR + 2}`} dur="1.5s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.4;0;0.4" dur="1.5s" repeatCount="indefinite" />
          </circle>
        )}

        {/* 13 位专家 */}
        {expertKeys.map((key, i) => {
          const angle = (i / expertKeys.length) * 2 * Math.PI - Math.PI / 2
          const x = cx + outerR * Math.cos(angle)
          const y = cy + outerR * Math.sin(angle)
          const expert = EXPERTS[key]
          const isActive = activeExpertId === key
          const dimmed = isSimulating && !isActive && !!activeExpertId
          const nodeR = isActive ? 18 : 15

          return (
            <g key={key} style={{ transition: 'all 0.4s ease' }}>
              {/* 活跃专家的光晕 */}
              {isActive && (
                <circle cx={x} cy={y} r={nodeR + 6} fill={expert.color} opacity="0.12">
                  <animate attributeName="r" values={`${nodeR + 4};${nodeR + 10};${nodeR + 4}`} dur="1.2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.15;0.05;0.15" dur="1.2s" repeatCount="indefinite" />
                </circle>
              )}

              {/* 专家节点 */}
              <circle cx={x} cy={y} r={nodeR}
                fill="var(--bg-card)"
                stroke={isActive ? expert.color : `${expert.color}50`}
                strokeWidth={isActive ? 2.5 : 1.5}
                opacity={dimmed ? 0.35 : 1}
                style={{ transition: 'all 0.4s ease' }}
              />

              {/* 专家 emoji */}
              <text x={x} y={y + 1} textAnchor="middle" dominantBaseline="central"
                fontSize={isActive ? 14 : 11}
                opacity={dimmed ? 0.35 : 1}
                style={{ transition: 'all 0.4s ease' }}>
                {expert.icon}
              </text>

              {/* 活跃专家名称标签 */}
              {isActive && (
                <g>
                  <rect x={x - 30} y={y + nodeR + 4} width="60" height="16" rx="4"
                    fill={expert.color} opacity="0.9" />
                  <text x={x} y={y + nodeR + 14} textAnchor="middle" dominantBaseline="central"
                    fontSize="8" fill="white" fontWeight="600" fontFamily="var(--font-heading)">
                    {expert.short}
                  </text>
                </g>
              )}
            </g>
          )
        })}
      </svg>

      {/* 状态文字 */}
      {isSimulating && (
        <div className="text-center mt-2 space-y-1">
          <p className="text-[10px] font-mono text-brand uppercase tracking-[0.15em]">
            {activeExpertId
              ? `${EXPERTS[activeExpertId]?.name || 'Expert'} analyzing...`
              : 'Roundtable in session...'}
          </p>
          <div className="flex justify-center gap-1">
            <div className="w-1 h-1 rounded-full bg-brand animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-1 h-1 rounded-full bg-brand animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-1 h-1 rounded-full bg-brand animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
      )}
    </div>
  )
}
