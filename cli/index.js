#!/usr/bin/env node

/**
 * CrabRes CLI — AI Growth Agent in your terminal
 * 
 * 多点触达的 CLI 入口：给 AI Agent（如 Knot/Claude）调用
 * 支持 SSE 流式输出，实时看到专家思考和搜索过程
 * 
 * Usage:
 *   crabres "help me grow my SaaS product"
 *   crabres chat "I built an AI resume tool"
 *   crabres chat "@social_media analyze my Twitter strategy"
 *   crabres status
 *   crabres plan
 *   crabres files
 *   crabres browse https://competitor.com
 *   crabres login
 *   crabres config
 *   crabres --api http://localhost:8000/api  "test locally"
 */

// ===== 配置 =====
let API = process.env.CRABRES_API || 'https://crab-researcher.onrender.com/api'
let TOKEN = process.env.CRABRES_TOKEN || ''
const DEBUG = process.env.CRABRES_DEBUG === '1'

const args = process.argv.slice(2)

// 解析 --api 标志
const apiIdx = args.indexOf('--api')
if (apiIdx !== -1 && args[apiIdx + 1]) {
  API = args[apiIdx + 1]
  args.splice(apiIdx, 2)
}

// 解析 --lang 标志
let LANG = process.env.CRABRES_LANG || 'en'
const langIdx = args.indexOf('--lang')
if (langIdx !== -1 && args[langIdx + 1]) {
  LANG = args[langIdx + 1]
  args.splice(langIdx, 2)
}

const command = args[0]
const rest = args.slice(1).join(' ')

// ANSI 颜色
const c = {
  reset: '\x1b[0m',
  bold: '\x1b[1m',
  dim: '\x1b[2m',
  italic: '\x1b[3m',
  blue: '\x1b[36m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
  orange: '\x1b[38;5;208m',
  purple: '\x1b[35m',
  gray: '\x1b[90m',
}

// 专家 emoji 映射
const expertEmoji = {
  market_researcher: '🔬', economist: '📊', content_strategist: '✍️',
  social_media: '📱', paid_ads: '💰', partnerships: '🤝',
  ai_distribution: '🤖', psychologist: '🧠', product_growth: '📈',
  data_analyst: '📉', copywriter: '✏️', critic: '⚖️', designer: '🎨',
}

async function main() {
  if (!command || command === 'help' || command === '--help' || command === '-h') {
    printHelp()
    return
  }

  if (command === 'login') { await login(); return }
  if (command === 'config') { printConfig(); return }
  if (command === 'version') { console.log(`CrabRes CLI v2.0.0`); return }

  // 尝试从文件读取 token
  await loadToken()

  if (!TOKEN && command !== 'login') {
    console.log(`${c.yellow}⚠ Not logged in.${c.reset} Run: ${c.bold}crabres login${c.reset}`)
    console.log(`${c.dim}Or set CRABRES_TOKEN environment variable${c.reset}`)
    return
  }

  switch (command) {
    case 'chat': await chatStream(rest); break
    case 'status': await status(); break
    case 'plan': await plan(); break
    case 'files': await files(); break
    case 'browse': await browse(rest); break
    case 'discoveries': await discoveries(); break
    case 'cost': await cost(); break
    case 'experts': listExperts(); break
    default:
      // 没有命令直接当 chat（方便 AI Agent 调用）
      await chatStream(args.join(' '))
  }
}

function printHelp() {
  console.log(`
${c.orange}🦀 CrabRes CLI${c.reset} ${c.dim}v2.0.0${c.reset} — AI Growth Agent in your terminal

${c.bold}Core Commands:${c.reset}
  crabres <message>                Talk to CrabRes (default command)
  crabres chat <message>           Same as above, explicit
  crabres chat "@expert msg"       Direct message to a specific expert
  crabres browse <url>             Browse a website and analyze it

${c.bold}Dashboard:${c.reset}
  crabres status                   Growth dashboard & creature state
  crabres plan                     View current growth plan
  crabres files                    List workspace files
  crabres discoveries              Latest market discoveries
  crabres cost                     Token usage & cost report
  crabres experts                  List all 13 AI expert advisors

${c.bold}Auth & Config:${c.reset}
  crabres login                    Authenticate with email/password
  crabres config                   Show current configuration
  crabres version                  Show version

${c.bold}Flags:${c.reset}
  --api <url>                      Override API base URL
  --lang <en|zh>                   Set response language

${c.bold}Examples:${c.reset}
  ${c.dim}# Quick growth research${c.reset}
  crabres "I built an AI resume tool for job seekers, help me grow"
  
  ${c.dim}# Target specific platform${c.reset}
  crabres "Help me grow on X/Twitter, target 100 users in 10 days"
  
  ${c.dim}# Analyze a competitor${c.reset}
  crabres browse https://habitify.me
  
  ${c.dim}# Talk to a specific expert${c.reset}
  crabres chat "@social_media What's the best Reddit strategy for SaaS?"
  
  ${c.dim}# Use locally (development)${c.reset}
  crabres --api http://localhost:8000/api "test my product"

${c.bold}Environment:${c.reset}
  CRABRES_TOKEN    Auth token (or run 'crabres login')
  CRABRES_API      API base URL (default: production)
  CRABRES_LANG     Response language: en or zh (default: en)
  CRABRES_DEBUG    Set to 1 for debug output
`)
}

// ===== Token 管理 =====
async function loadToken() {
  if (TOKEN) return
  try {
    const fs = await import('fs')
    const os = await import('os')
    const path = await import('path')
    const tokenFile = path.join(os.default.homedir(), '.crabres-token')
    TOKEN = fs.default.readFileSync(tokenFile, 'utf-8').trim()
  } catch {}
}

async function login() {
  const readline = await import('readline')
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout })
  const ask = (q) => new Promise(r => rl.question(q, r))

  console.log(`\n${c.orange}🦀 CrabRes Login${c.reset}\n`)
  console.log(`${c.dim}API: ${API}${c.reset}\n`)

  const email = await ask('Email: ')
  const password = await ask('Password: ')
  rl.close()

  try {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const data = await res.json()

    if (data.access_token) {
      TOKEN = data.access_token
      const fs = await import('fs')
      const os = await import('os')
      const path = await import('path')
      fs.default.writeFileSync(path.join(os.default.homedir(), '.crabres-token'), TOKEN)
      console.log(`\n${c.green}✓ Logged in!${c.reset} Token saved to ~/.crabres-token`)
    } else {
      console.log(`\n${c.red}✗ Login failed:${c.reset} ${data.detail || JSON.stringify(data)}`)
    }
  } catch (e) {
    console.log(`${c.red}✗ Connection failed:${c.reset} ${e.message}`)
    console.log(`${c.dim}Check your API URL: ${API}${c.reset}`)
  }
}

// ===== 核心：SSE 流式聊天 =====
async function chatStream(message) {
  if (!message) {
    console.log(`${c.yellow}Usage:${c.reset} crabres "your message"`)
    return
  }

  if (DEBUG) console.log(`${c.dim}[DEBUG] POST ${API}/agent/chat/stream${c.reset}`)

  try {
    const res = await fetch(`${API}/agent/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${TOKEN}`,
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify({ message, language: LANG }),
    })

    if (res.status === 401) {
      console.log(`${c.red}✗ Session expired.${c.reset} Run: ${c.bold}crabres login${c.reset}`)
      return
    }

    if (!res.ok) {
      const err = await res.text()
      console.log(`${c.red}✗ Error ${res.status}:${c.reset} ${err.slice(0, 200)}`)
      return
    }

    // 解析 SSE 流
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let expertCount = 0
    let hasMessage = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') continue

        try {
          const event = JSON.parse(raw)
          renderEvent(event)
          if (event.type === 'expert_thinking') expertCount++
          if (event.type === 'message') hasMessage = true
        } catch (e) {
          if (DEBUG) console.log(`${c.dim}[DEBUG] Parse error: ${e.message}${c.reset}`)
        }
      }
    }

    // 底部统计
    if (hasMessage) {
      console.log(`\n${c.dim}─── ${expertCount} experts consulted ───${c.reset}`)
    }

  } catch (e) {
    console.log(`${c.red}✗ Error:${c.reset} ${e.message}`)
    if (e.cause) console.log(`${c.dim}Cause: ${e.cause}${c.reset}`)
  }
}

function renderEvent(event) {
  const { type, content, expert_id, action, url, title } = event

  switch (type) {
    case 'status':
      // 进度状态 — 单行覆盖
      process.stdout.write(`\r${c.dim}  ⏳ ${content}${' '.repeat(20)}${c.reset}`)
      break

    case 'expert_thinking':
      // 专家思考 — 折叠显示（只显示前 2 行）
      process.stdout.write('\r' + ' '.repeat(80) + '\r') // 清除状态行
      const emoji = expertEmoji[expert_id] || '🧠'
      const preview = content.split('\n')[0].slice(0, 100)
      console.log(`  ${emoji} ${c.blue}[${expert_id}]${c.reset} ${c.dim}${preview}...${c.reset}`)
      break

    case 'message':
      // 主消息 — 完整显示
      process.stdout.write('\r' + ' '.repeat(80) + '\r')
      console.log(`\n${c.orange}🦀 CrabRes:${c.reset}\n`)
      console.log(formatMarkdown(content))
      break

    case 'browser_event':
      process.stdout.write('\r' + ' '.repeat(80) + '\r')
      if (action === 'navigating') {
        console.log(`  ${c.purple}🌐 Browsing:${c.reset} ${url}`)
      } else if (action === 'loaded') {
        console.log(`  ${c.green}✓ Loaded:${c.reset} ${title || url}`)
      } else if (action === 'failed') {
        console.log(`  ${c.red}✗ Failed:${c.reset} ${url} — ${event.error || 'timeout'}`)
      }
      break

    case 'file_created':
      console.log(`  ${c.green}📄 File:${c.reset} ${event.name || event.path}`)
      break

    case 'error':
      console.log(`\n${c.red}✗ Error:${c.reset} ${content}`)
      break

    default:
      if (DEBUG) console.log(`${c.dim}[DEBUG] Unknown event type: ${type}${c.reset}`)
  }
}

// 简单的 Markdown 格式化（终端友好）
function formatMarkdown(text) {
  return text
    .replace(/^### (.+)$/gm, `${c.bold}${c.orange}$1${c.reset}`)
    .replace(/^## (.+)$/gm, `\n${c.bold}$1${c.reset}`)
    .replace(/\*\*(.+?)\*\*/g, `${c.bold}$1${c.reset}`)
    .replace(/⚠️/g, `${c.yellow}⚠️${c.reset}`)
    .replace(/`([^`]+)`/g, `${c.blue}$1${c.reset}`)
}

// ===== browse 命令 — 浏览器分析竞品 =====
async function browse(url) {
  if (!url) {
    console.log(`${c.yellow}Usage:${c.reset} crabres browse https://competitor.com`)
    return
  }
  // 通过 chat 发送浏览器请求
  await chatStream(`Please browse ${url} and analyze their growth strategy, pricing, and user acquisition approach.`)
}

// ===== Dashboard 命令 =====
async function status() {
  try {
    const [stats, creature] = await Promise.all([
      apiFetch('/growth/stats').catch(() => ({})),
      apiFetch('/creature/state').catch(() => ({})),
    ])

    console.log(`\n${c.orange}🦀 CrabRes Growth Dashboard${c.reset}`)
    console.log(`${c.dim}${'─'.repeat(40)}${c.reset}`)

    if (creature.mood) {
      const attrs = creature.attributes || {}
      console.log(`  Mood: ${creature.mood}  Level: ${creature.level || 1}  Size: ${creature.size || 'small'}`)
      console.log(`  Growth: ${bar(attrs.growth)}  Reach: ${bar(attrs.reach)}`)
      console.log(`  Consistency: ${bar(attrs.consistency)}  Momentum: ${bar(attrs.momentum)}`)
    }

    if (stats.total_users !== undefined) {
      console.log()
      console.log(`  Users: ${c.bold}${stats.total_users}${c.reset}  Growth: ${c.green}+${stats.growth_rate || 0}%${c.reset}  Streak: ${c.orange}${stats.streak_days || 0}d${c.reset}`)
    }
  } catch (e) {
    console.log(`${c.red}✗ Error:${c.reset} ${e.message}`)
  }
}

async function plan() {
  try {
    const data = await apiFetch('/growth/plan')
    if (data.plan?.content) {
      console.log(`\n${c.orange}📋 Growth Plan${c.reset}\n`)
      console.log(formatMarkdown(data.plan.content))
    } else {
      console.log(`${c.yellow}No growth plan yet.${c.reset} Run: crabres "Help me create a growth plan for my product"`)
    }
  } catch (e) {
    console.log(`${c.red}✗ Error:${c.reset} ${e.message}`)
  }
}

async function files() {
  try {
    const data = await apiFetch('/workspace/tree')
    if (!data.tree || data.tree.length === 0) {
      console.log(`${c.dim}Workspace is empty.${c.reset}`)
      return
    }
    console.log(`\n${c.orange}📁 Workspace Files${c.reset}\n`)
    printTree(data.tree, '')
  } catch (e) {
    console.log(`${c.red}✗ Error:${c.reset} ${e.message}`)
  }
}

function printTree(nodes, indent) {
  for (const node of nodes) {
    const icon = node.type === 'directory' ? '📁' : '📄'
    console.log(`${indent}${icon} ${node.name}`)
    if (node.children) {
      printTree(node.children, indent + '  ')
    }
  }
}

async function discoveries() {
  try {
    const data = await apiFetch('/agent/discoveries')
    const items = data.discoveries || []
    if (items.length === 0) {
      console.log(`${c.dim}No new discoveries. Growth daemon is scanning...${c.reset}`)
      return
    }
    console.log(`\n${c.orange}💡 Recent Discoveries${c.reset}\n`)
    for (const d of items) {
      console.log(`  ${c.blue}${d.type || 'insight'}:${c.reset} ${d.title || d.change || d.competitor || ''}`)
      if (d.analysis) console.log(`  ${c.green}→ ${d.analysis}${c.reset}`)
      console.log()
    }
  } catch (e) {
    console.log(`${c.red}✗ Error:${c.reset} ${e.message}`)
  }
}

async function cost() {
  try {
    const sessions = await apiFetch('/agent/sessions')
    if (!sessions.sessions?.length) {
      console.log(`${c.dim}No sessions found.${c.reset}`)
      return
    }
    console.log(`\n${c.orange}💵 Cost Report${c.reset}\n`)
    for (const s of sessions.sessions) {
      try {
        const costData = await apiFetch(`/agent/session/${s.session_id}/cost`)
        console.log(`  ${s.session_id.slice(0, 8)}  $${costData.total_cost_usd?.toFixed(4) || '0'}  ${costData.total_tokens || 0} tokens  ${s.is_active ? c.green + '●' + c.reset : c.dim + '○' + c.reset}`)
      } catch {}
    }
  } catch (e) {
    console.log(`${c.red}✗ Error:${c.reset} ${e.message}`)
  }
}

function listExperts() {
  console.log(`\n${c.orange}🧠 CrabRes Expert Advisors${c.reset}\n`)
  const experts = [
    ['market_researcher', '🔬', 'Market Researcher', 'Competitive analysis, market sizing, trends'],
    ['economist', '📊', 'Economist', 'Unit economics, pricing, ROI modeling'],
    ['content_strategist', '✍️', 'Content Strategist', 'Content calendar, SEO, topic clusters'],
    ['social_media', '📱', 'Social Media', 'Platform strategy, community building, viral loops'],
    ['paid_ads', '💰', 'Paid Ads', 'Ad campaigns, targeting, budget optimization'],
    ['partnerships', '🤝', 'Partnerships', 'Co-marketing, integrations, affiliate programs'],
    ['ai_distribution', '🤖', 'AI Distribution', 'AI directories, MCP, ChatGPT plugins'],
    ['psychologist', '🧠', 'Consumer Psychologist', 'User behavior, persuasion, conversion psychology'],
    ['product_growth', '📈', 'Product Growth', 'PLG, activation, retention, onboarding'],
    ['data_analyst', '📉', 'Data Analyst', 'Metrics, cohort analysis, A/B testing'],
    ['copywriter', '✏️', 'Master Copywriter', 'Headlines, CTAs, landing page copy'],
    ['critic', '⚖️', 'Strategy Critic', 'Devil\'s advocate, risk assessment, feasibility'],
    ['designer', '🎨', 'Design Expert', 'UI/UX, visual identity, brand design'],
  ]
  for (const [id, emoji, name, desc] of experts) {
    console.log(`  ${emoji} ${c.bold}${name}${c.reset} ${c.dim}(@${id})${c.reset}`)
    console.log(`    ${desc}`)
  }
  console.log(`\n${c.dim}Direct message: crabres "@social_media What's the best Reddit strategy?"${c.reset}`)
}

function printConfig() {
  console.log(`\n${c.orange}⚙️  CrabRes Config${c.reset}\n`)
  console.log(`  API:      ${API}`)
  console.log(`  Token:    ${TOKEN ? TOKEN.slice(0, 15) + '...' : c.red + 'not set' + c.reset}`)
  console.log(`  Language: ${LANG}`)
  console.log(`  Debug:    ${DEBUG ? 'on' : 'off'}`)
  console.log(`  Token file: ~/.crabres-token`)
}

// ===== 工具函数 =====
async function apiFetch(path, opts = {}) {
  const url = `${API}${path}`
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${TOKEN}`,
    ...opts.headers,
  }
  if (DEBUG) console.log(`${c.dim}[DEBUG] ${opts.method || 'GET'} ${url}${c.reset}`)
  const res = await fetch(url, { ...opts, headers })
  if (res.status === 401) {
    console.log(`${c.red}✗ Session expired.${c.reset} Run: crabres login`)
    process.exit(1)
  }
  return res.json()
}

function bar(value = 0) {
  const filled = Math.round(value / 10)
  return `${'█'.repeat(Math.min(filled, 10))}${'░'.repeat(Math.max(10 - filled, 0))} ${value}`
}

main().catch(e => {
  console.error(`${c.red}Fatal:${c.reset} ${e.message}`)
  if (DEBUG) console.error(e.stack)
  process.exit(1)
})
