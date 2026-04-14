# CrabRes TODO — 2026-04-15

## 🎯 核心目标：让 Agent 触达真实世界

---

## ✅ 已完成 (49/49 核心能力)

### 感知层 (10/10) 👁️
- [x] Web Search (Tavily/Exa)
- [x] Social Search (SerpAPI)
- [x] Website Scraping (httpx)
- [x] Deep Scrape (Firecrawl)
- [x] JS Rendering (Playwright)
- [x] Competitor Change Detection (BrowserCrawler)
- [x] RSS/Atom Subscription (RSSWatcher)
- [x] Twitter Read (code ready, needs token)
- [x] Webhook Receiver (GitHub + Generic + SSE)
- [x] Mood Sensing

### 思考层 (8/8) 🧠
- [x] 13-Expert Roundtable (parallel + dependency graph)
- [x] Context Engine (selective injection + expert weight matrix)
- [x] Knowledge Base (1102-line SOP)
- [x] Channel Playbooks
- [x] Deep Strategy (ULTRAPLAN, 8 async experts)
- [x] LLM Adapter (4-tier)
- [x] Prompt Cache
- [x] Playbook Templates

### 记忆层 (8/8) 📚
- [x] 5-layer Memory (8 categories)
- [x] FTS5 Semantic Search (BM25)
- [x] Growth Dream (memory distillation)
- [x] Skill Self-Evolution (5 seed skills)
- [x] Growth Log (Action/Result/Strategy)
- [x] Experiment Tracker
- [x] Result Judgment (channel benchmarks)
- [x] Playbook Store

### 执行层 (8/8) ✋
- [x] Write Post (6 platform templates)
- [x] Publish Post (Twitter API, needs token)
- [x] Write Email (4 types)
- [x] Submit to Directory (6 AI directories)
- [x] Set Active Campaign
- [x] Save Competitors
- [x] **Autonomous Execution** (risk-based auto-execute)
- [x] **Scheduled Actions** (via Daemon + APScheduler)

### 自主层 (9/9) 🤖
- [x] Daemon Scheduler (APScheduler, 30min tick)
- [x] EventBus (memory + Redis upgrade path)
- [x] Action→Result Loop
- [x] ActionTracker Lifecycle (6 states)
- [x] RealWorldConnector (RSS + Crawler + Tracking)
- [x] **Proactive Notifier** (SSE + Telegram + queue)
- [x] **Autonomous Decision Chain** (3-tier risk + approval)
- [x] **Goal Tracker** (OKR + auto-sync + at-risk detection)
- [x] **Reflection Engine** (daily + execution + feedback)

### 交付层 (6/6) 📊
- [x] Competitor Analysis Report
- [x] Social Media Draft
- [x] 30-Day Growth Plan
- [x] Structured Playbook
- [x] **Weekly Report** (auto-generated)
- [x] **Dashboard Data** (128 API routes)

---

## 🔴 P0 — 需要你手动做的

- [ ] **配置 TELEGRAM_BOT_TOKEN** — @BotFather → Token → .env
- [ ] **配置 DISCORD_BOT_TOKEN** — Developer Portal → .env
- [ ] **配置 TWITTER_BEARER_TOKEN** — X Developer Portal → .env
- [ ] **git push** — commits 待推送
- [ ] **部署到线上** — 验证 128 个路由全部可访问

## 🟡 P1 — 后续迭代

- [ ] Docker 沙箱（Agent 执行代码不污染主机）
- [ ] Redis 生产部署
- [ ] 前端 SSE 实时展示通知
- [ ] 前端 Dashboard 对接 /api/goals + /api/reports/weekly
- [ ] 前端 Autonomous 审批界面
- [ ] 微信 / 飞书 Bot 配置完善
- [ ] 更多 Seed Skills

---

## 📊 能力完成度

| 维度 | 完成 | 总数 | 状态 |
|------|------|------|------|
| 👁️ 感知层 | 10 | 10 | ✅ 100% |
| 🧠 思考层 | 8 | 8 | ✅ 100% |
| 📚 记忆层 | 8 | 8 | ✅ 100% |
| ✋ 执行层 | 8 | 8 | ✅ 100% |
| 🤖 自主层 | 9 | 9 | ✅ 100% |
| 📊 交付层 | 6 | 6 | ✅ 100% |
| **总计** | **49** | **49** | **✅ 100%** |

> ⚠️ 代码层面 100%，但真实世界连接需要 API Token 配置才能激活
