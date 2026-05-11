# Changelog

## v5.0.0 — Hybrid Architecture + TokenDance Gateway

**核心变化**：主引擎从 `AgentLoop` 切换到 `GraphBuilder`；LLM 接入 TokenDance 多模型网关。

### 升级动作（部署侧必须做）

1. `git pull`
2. `.env` 增加：
   ```
   TOKENDANCE_API_KEY=sk-<your-key>
   TOKENDANCE_BASE_URL=https://tokendance.space/gateway/v1
   ```
3. 重启服务（清空内存里的旧 `_sessions` 缓存，里面是 v4.x 的 `AgentLoop` 实例）

无数据库迁移，无前端 API 契约改动。

### Highlights

| 维度 | v4.x | v5.0 |
|---|---|---|
| 主引擎 | 单一 ReAct 循环（LLM 全程决策） | Router → Quick / Pipeline / ReAct 三路 |
| 打招呼/闲聊 | 走完整循环 ~$0.02 | Quick 直接回复 **~$0.0005** |
| 标准增长咨询 | LLM 自由决策每一步 | 确定性 Pipeline（UNDERSTAND→RESEARCH→EXPERT→DELIVER） |
| 交付物 | 无脑生成 4 件 | 按意图裁剪（只问竞品 → 只生成 report） |
| LLM 模型 | Moonshot + OpenRouter | TokenDance（DeepSeek V4 / GLM 4.7 / Kimi K2.6 / Qwen3 8B）+ 回退链 |
| 单次完整咨询成本 | 难以稳定预估 | 实测 ~$0.025 |

### Hybrid Architecture — "Code as fast path, LLM as fallback"

新设计思路：能用规则/查表的就别问 LLM；只在代码判断不出来的"边缘场景"才让 LLM 介入。

**P0 — 确定性流程优化**
- **Intent-aware deliverables**：node_understand 用关键词把请求细分成 `competitor_only` / `content_only` / `plan_only` / `full`，node_deliver 只生成需要的产物。语料里典型场景节省 ~70% deliver 阶段成本。
- **Pipeline 步数预算**：硬上限 20 步，防御性 guardrail（异常路径下不会无限循环）。

**P1 — LLM 兜底**
- **Router LLM fallback**：8 条正则路由规则全 miss 且消息 < 200 字符时，调用 PARSING tier（qwen3-8b，单次 ~$0.0001）做兜底分类。覆盖正则漏召回（"yo"、"早上好"、网络流行语等）。LLM 失败时静默降级回 Pipeline 默认路径。
- **专家选择 LLM 介入**：仅当 `product_type=="default"`（查表矩阵未覆盖的轴外产品，例如"宠物 AI 训练 app"、"AR 朝圣路线导览"）时，让 LLM 从 13 个专家里挑 4 个最相关的。常规 SaaS/Tool/Community 仍走零 token 的查表快路径。

### TokenDance Gateway

接入 OpenAI 兼容的多模型聚合网关，单 key 覆盖 DeepSeek/GLM/Kimi/Qwen/MiniMax 等 40+ 模型。

4-Tier 重新分配：

| Tier | 主选 | 备选 | 兜底 |
|---|---|---|---|
| CRITICAL (CGO 综合) | DeepSeek V4 Pro | GLM 4.7 → Kimi K2.6 | Moonshot |
| THINKING (专家分析) | GLM 4.7 | DeepSeek V4 Pro | Moonshot |
| WRITING (文案生成) | GLM 4.7 | DeepSeek V4 Flash | Moonshot |
| PARSING (路由/抽取) | Qwen3 8B | DeepSeek V4 Flash | Moonshot |

**关键设计**：
- 没配 key 的 provider 自动跳过 chain 节点（避免 401 重试浪费时间）
- TokenDance 挂掉时静默回退到 Moonshot/OpenRouter
- 推理模型（DeepSeek V4 Flash 等）返回空 content 时（被 reasoning_content 吃光 token）自动 fallback 到链下一个模型
- WRITING tier 主选改成 GLM 4.7（非推理模型，直出干净文本）

### Bug 修复

跑 GraphBuilder 端到端时挖出 5 个老 bug（说明这条路径在 v4.x 从未被真正调用过）：

- `NodeDeps` 字段缺类型注解，`@dataclass` 装饰器产生空构造器，`NodeDeps(llm=...)` 直接 `TypeError`
- `node_expert` 漏 `import asyncio`，专家批次执行时 `NameError`
- `type('', name=eid)` 语法错误（`type()` 不收关键字参数）
- Windows 默认 GBK 编码导致 `read_text`/`write_text`/`open` 写入含 `€` 等 Unicode 字符时 `UnicodeEncodeError`
- `loop.py` 里 `_compact_context` 和 `_collapse_history` 用了 `await` 但函数没声明 `async`（`_collapse_history` 还被定义了两次，前一份是 dead+broken 代码）

### API 契约

无破坏性变更。`/agent/chat` 和 `/agent/chat/stream` 接受同样的请求 schema，返回同样的事件流（`type`/`content`/`expert_id` 等字段）。前端无需改动。

### 文件结构变化

```
app/agent/engine/
├── graph_builder.py     # 新增 — 主引擎
├── router.py            # 新增 — 路由层 + LLM 兜底
├── state.py             # 新增 — 统一 AgentState
├── nodes/__init__.py    # 新增 — 4 个共享节点
├── errors.py            # 新增 — 异常分类
├── loop.py              # 保留 — GraphBuilder ReAct 路径复用其 prompt 构造
└── llm_adapter.py       # 扩展 — 注册 TokenDance + 4-Tier 重排
```

### 观察 & 已知项

- GraphBuilder 在 v4.x 编写完成但从未在 API 层被调用，这次切换是它的第一次生产暴露
- Quick 路径已验证；Pipeline 路径已端到端验证；ReAct 路径走的是 `_run_react`，依赖 trust_level（默认条件较严，绝大多数请求不会进入）
- 后续可考虑做的 P1.3：Pipeline 节点内嵌局部 ReAct（深度研究类请求），当前因受众小已推后

### Commits

```
034fe44 feat(api): switch /agent/chat from AgentLoop to GraphBuilder
60e618b fix: GraphBuilder E2E blockers found during integration test
37540c9 fix(llm): handle reasoning-model empty content + reorder WRITING chain
a5597e5 feat(llm): integrate TokenDance gateway as primary multi-model provider
55a3804 refactor(engine): unified GraphBuilder + intent-aware deliverables + LLM fallback
```

---

## v4.4.1 — Expert chat + parallel deliverables fixes

- Expert chat message event support
- Parallel deliverables generation
- Deliver-stage timeout handling

## v4.4.0 — Browser + sandbox hardening

- Jina Reader API integration
- Persistent workspace
- Image support

## v4.3.0 — LLM-driven research + onboarding

- LLM-driven research query expansion
- Onboarding context capture
- CLI v2.0

## v4.2.0 — File persistence + language fixes

- File persistence fix
- Platform-aware language detection
- Browser timeout handling

## v4.1.0 — UX optimizations

- Live workspace
- Browser preview
- Smart language
- Event streaming

## v4.0.0 — Deterministic Orchestrator

- Initial deterministic stage orchestrator

## v3.0 — ReAct AgentLoop

- Switch to ReAct architecture: LLM decides, code executes
