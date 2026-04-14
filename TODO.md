# CrabRes TODO — 2026-04-15

## 🎯 核心目标：让 Agent 触达真实世界

---

## ✅ 已完成

- [x] APScheduler 替换 asyncio.sleep（Daemon 持久化调度）
- [x] Playwright 安装并验证（浏览器渲染 JS 页面）
- [x] Telegram Long Polling 模块（不依赖公网 Webhook）
- [x] EventBus 事件总线（内存模式 + Redis 升级路径）
- [x] Webhook 接收器（GitHub/通用/SSE 流）
- [x] 5 个 Seed Skills 灌入（HN Launch/BIP Thread/Cold Email/XHS/PH Launch）
- [x] ChannelGateway 统一入口
- [x] Skill Evolution System（SkillStore + SkillWriter）
- [x] FTS5 语义记忆搜索
- [x] Daemon API（6 个端点）
- [x] 评估体系文档 + MetricsCollector
- [x] Bug 修复（语言一致性/记忆注入/Playbook 生成）
- [x] 104 个路由全部加载

## 🔴 P0 — 需要你手动做的

- [ ] **配置 TELEGRAM_BOT_TOKEN** — @BotFather 创建 Bot → 拿 Token → 写入 .env
- [ ] **配置 DISCORD_BOT_TOKEN** — Discord Developer Portal → 创建 Bot → 写入 .env
- [ ] **配置 TWITTER_BEARER_TOKEN** — X Developer Portal → 创建 App → 写入 .env
- [ ] **安装 Docker** — `brew install --cask docker`（沙箱环境需要）
- [ ] **git push** — 4 个 commit 待推送

## 🟡 P1 — 我正在做的

- [ ] **Docker 沙箱环境** — Agent 执行代码不污染主机
- [ ] **真实浏览器爬虫任务** — 定时抓取竞品页面变化
- [ ] **Daemon 接入 EventBus** — tick 结果实时推送到前端
- [ ] **RSS/Atom 订阅器** — 被动接收竞品博客更新
- [ ] **Action → Result 闭环** — 执行后自动追踪效果

## 🟢 P2 — 后续迭代

- [ ] Redis 生产部署
- [ ] 前端 SSE 实时展示 Daemon 发现
- [ ] 微信 Bot 接入
- [ ] 飞书 Bot 配置完善
- [ ] 更多 Seed Skills（Reddit、LinkedIn、邮件营销）
- [ ] Agent 自主决策链（不需要人确认就能执行低风险操作）

---

## 📊 距离"触达真实世界"的差距评估

| 维度 | 状态 | 完成度 |
|------|------|--------|
| 🧠 思考能力（Pipeline+13专家） | ✅ 完成 | 90% |
| 📚 记忆能力（FTS5+Skill进化） | ✅ 代码完成，数据灌入 | 70% |
| 👁️ 感知能力（EventBus+Webhook） | ⚠️ 代码完成，缺凭证 | 40% |
| ✋ 执行能力（发帖/发邮件/爬虫） | ⚠️ 框架在，缺真实API | 20% |
| 🏠 生存能力（沙箱/持久化/自愈） | ⚠️ APScheduler完成，缺Docker | 30% |
| 📡 触达能力（Telegram/Discord/飞书） | ⚠️ 代码完成，缺Token | 15% |

**综合完成度：约 45%**
