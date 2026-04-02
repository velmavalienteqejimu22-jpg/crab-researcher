"""
CrabRes Skills 知识注册表

这不是安装 Skills 到 .claude/ 目录，而是将高质量开源 Skills 的核心知识
整合为我们专家的参考知识库。

来源（经审核的高质量 Skills）：
- superamped/ai-marketing-skills (18 Skills, MIT)
- coreyhaines31/marketingskills (52.4K installs, MIT)
- inferen-sh/skills (product-hunt-launch 8.1K installs)
- openclaudia/openclaudia-skills (60+ Skills)

每个专家在被调度时，会根据任务类型从这里获取相关的框架和模板。
"""

# 每个专家可引用的知识模块
# key = expert_id, value = 该专家可调用的知识片段

EXPERT_KNOWLEDGE: dict[str, list[dict]] = {

    "market_researcher": [
        {
            "name": "competitor_landscape",
            "source": "superamped/ai-marketing-skills",
            "description": "跨竞品对比分析框架",
            "framework": """分析步骤:
1. Feature Matrix: 按战略重要性排序，标注 ✅❌🔶
2. Pricing Comparison: 不仅对比价格，还对比模式和价值指标，识别定价信号
3. Positioning Map: 2x2 定位图（默认: 市场presence vs 产品广度），标注空白区域
4. Aggregate SWOT: 基于整个市场格局的宏观 SWOT，不是单一公司
5. Moat Landscape: 对比网络效应、转换成本、规模经济
6. Strategic Recommendations: 赢面、弱点、市场空缺、定位建议、雷区

规则:
- 绝不编造数据，缺失标注 "data not available"
- 至少需要 2 个竞品
- 推荐必须有数据支持
- 如果用户产品处于弱势必须诚实指出""",
        },
        {
            "name": "community_discovery",
            "source": "superamped/ai-marketing-skills",
            "description": "发现目标用户活跃的在线社区",
            "framework": """搜索维度:
- Reddit: 相关子版块，按活跃度和相关度排序
- Discord/Slack: 相关服务器/频道
- Facebook Groups: 相关群组
- LinkedIn Groups: 行业群组
- 论坛/垂直社区: 行业专属论坛
评估标准: 信噪比、活跃度、商业友好度、准入门槛""",
        },
        {
            "name": "channel_discovery",
            "source": "superamped/ai-marketing-skills",
            "description": "评估最佳获客渠道",
            "framework": """按 5 个标准评分:
1. Audience fit (目标用户是否在这个渠道)
2. Competition level (竞品密度)
3. Cost efficiency (CAC 预估)
4. Scalability (能否规模化)
5. Time to results (多快见效)
输出前 3 个优先渠道，附理由""",
        },
    ],

    "economist": [
        {
            "name": "pricing_strategy",
            "source": "coreyhaines31/marketingskills + psychology",
            "description": "定价策略和心理学框架",
            "framework": """定价心理:
- 魅力定价: $99 < $100（左位效应）
- 100法则: <$100 用百分比折扣, >$100 用绝对折扣
- 好-更好-最好: 三层定价，中间层是目标
- 诱饵效应: 添加较差的第三选项使首选更吸引
- 心理账户: "$3/天" < "$90/月"（感知不同）
- 免费的力量: $0→$1 的跳跃远大于 $1→$2

单位经济分析:
- CAC = 总获客成本 / 新客户数
- LTV = ARPU × 平均生命周期
- LTV/CAC > 3 = 健康
- 回收期 = CAC / 月收入/用户""",
        },
    ],

    "content_strategist": [
        {
            "name": "keyword_research",
            "source": "aaron-he-zhu/seo-geo-claude-skills (2.3K installs)",
            "description": "关键词研究和主题集群",
            "framework": """步骤:
1. 种子关键词 → 扩展为关键词宇宙
2. 按搜索意图分组: informational / navigational / commercial / transactional
3. 评估: 搜索量 × 竞争度 × 和产品的相关度
4. 建立主题集群: 1个支柱页面 + N个集群页面
5. 内容优先级: 高相关+低竞争优先""",
        },
        {
            "name": "seo_audit",
            "source": "addyosmani/web-quality-skills (4.8K installs)",
            "description": "SEO + AI 搜索优化审计",
            "framework": """38 点审计:
- 技术 SEO: 页面速度、移动适配、Schema 标记
- 内容结构: H1/H2 层级、FAQ 区块、对比表
- AI/GEO 准备度: 结构化数据、可引用答案、FAQ Schema
- E-E-A-T: 经验、专业性、权威性、可信度""",
        },
        {
            "name": "geo_optimization",
            "source": "CrabRes 2026 + Averi.ai research",
            "description": "GEO - 生成引擎优化（让 AI 搜索引擎引用你）",
            "framework": """GEO (Generative Engine Optimization) — 2026 年最重要的新渠道

什么是 GEO:
让 ChatGPT、Perplexity、Google AI Overviews 在回答用户问题时引用你的内容。
Peter Levels 发现 AI 推荐流量一个月内从 4% 跃升到 20%。

优化方法:
1. 结构化答案格式:
   - 每篇文章开头直接给出结论（不要废话导入）
   - 使用 FAQ 格式（Question → Direct Answer）
   - 包含对比表（AI 特别喜欢引用表格数据）
   - 使用确切数字和数据（"228.8亿元" > "数百亿"）

2. Schema 标记:
   - FAQPage schema 让 AI 能解析你的问答
   - Product schema 让 AI 知道你的定价和功能
   - HowTo schema 让 AI 引用你的步骤指南
   - Comparison schema 让 AI 引用你的对比数据

3. 内容结构:
   - H2 用问题形式（"What is the best X for Y?"）
   - 每个 H2 下面第一句话直接回答（无需铺垫）
   - 列举式内容（numbered lists）比段落更容易被引用
   - 包含 "as of 2026" 时间标记（AI 偏爱新鲜内容）

4. 引用建设:
   - 被高权威网站引用的内容更容易被 AI 推荐
   - 在 Reddit/HN/StackOverflow 上回答问题并链接回你的文章
   - 创建"唯一来源"数据（原创研究/调查/基准测试）

5. 对比页面（GEO 金矿）:
   - "X vs Y" 页面是 AI 最常引用的页面类型
   - 包含功能对比表 + 定价对比 + 适用场景
   - 诚实评价（不贬低竞品，AI 会检测偏见）

衡量:
- 在 ChatGPT/Perplexity 中搜索你的关键词，看是否引用你
- 追踪来自 AI 搜索引擎的流量（GA4 的 referral 中看 chat.openai.com 等）""",
        },
    ],

    "psychologist": [
        {
            "name": "marketing_psychology",
            "source": "coreyhaines31/marketingskills (38.3K installs)",
            "description": "70+ 营销心理学原则",
            "framework": """快速参考:
| 挑战 | 模型 |
|------|------|
| 低转化 | 希克定律、活化能、BJ Fogg行为模型 |
| 价格异议 | 锚定、框架、心理账户、损失厌恶 |
| 建立信任 | 权威、社会认同、互惠、出丑效应 |
| 增加紧迫感 | 稀缺性、损失厌恶、蔡格尼克效应 |
| 留存/流失 | 禀赋效应、转换成本、现状偏见 |
| 增长停滞 | 约束理论、复利、飞轮效应 |
| 决策瘫痪 | 选择悖论、默认效应、助推理论 |
| 入职 | 目标梯度、宜家效应、承诺一致性 |

核心说服框架:
- 互惠: 先给予再要求
- 承诺一致性: 小承诺→大承诺
- 社会认同: 展示他人在做
- 权威: 专家/认证背书
- 喜好: 相似性和故事
- 稀缺性: 限时/限量（仅在真实时使用）""",
        },
        {
            "name": "conversion_audit",
            "source": "superamped/ai-marketing-skills",
            "description": "53 点转化审计",
            "framework": """审计维度:
1. 客户关注点: 是否解决了核心痛点
2. 叙事弧线: 痛点→梦想→解决方案
3. 文案质量: 清晰度、说服力、具体性
4. 设计: 视觉层级、CTA 可见度、移动适配
5. CTA: 文案、位置、紧迫感
6. 社会证明: 类型、位置、可信度""",
        },
    ],

    "copywriter": [
        {
            "name": "copywriting_framework",
            "source": "coreyhaines31/marketingskills (52.4K installs)",
            "description": "完整文案写作框架",
            "framework": """写作原则:
- 清晰 > 机智
- 利益 > 功能
- 具体 > 模糊（"4小时→15分钟" > "节省时间"）
- 客户语言 > 公司语言
- 每部分一个想法

标题公式:
- "{达到结果} without {痛点}"
- "The {类别} for {受众}"
- "Stop {痛点}. Start {结果}."
- "{数字} ways to {结果} in {时间}"

CTA 公式: [动词] + [得到什么] + [限定词]
- 弱: 提交/注册/了解更多
- 强: 开始免费试用/获取你的[东西]/创建你的第一个[东西]

页面结构:
1. 首屏: 标题+副标题+CTA
2. 社会证明: Logo/数字/推荐
3. 问题/痛点
4. 解决方案/利益(3-5个)
5. 工作原理(3-4步)
6. 异议处理/FAQ
7. 最终CTA+风险逆转""",
        },
    ],

    "social_media": [
        {
            "name": "reddit_marketing",
            "source": "superamped + ReplyAgent research",
            "description": "Reddit 深度营销策略",
            "framework": """核心规则:
- Reddit 用户反感任何营销味
- 先提供价值 100 次，再提 1 次产品
- 帖子格式: 经验分享 > 教程 > 案例 > AMA
- 回复比发帖更有效
- 用子版块的语气和术语

高价值机会发现（学 ReplyAgent）:
1. 搜索 Google 排名高的 Reddit 帖子（这些帖子长期有流量）
2. 寻找用户直接表达痛点的帖子（"有人推荐一个好用的 X 吗？"）
3. 监控新帖子——前 2 小时回复效果最好
4. 用 social_search 工具搜 "site:reddit.com [关键词]"

3 种安全的获客方式:
1. 帮人解决问题时顺带提及（最有效）
2. 做"免费资源"帖子附产品链接
3. 在个人主页 bio 放链接

高级策略（学 OptaReach）:
- 识别高意图帖子（有人在主动寻找解决方案）
- 不要回复冷帖（低评论低赞的老帖不值得）
- 回复要有实质价值（至少 3-5 行有用内容，最后一行提产品）
- 用不同角度回复同一个需求（一次经验分享，一次工具推荐，一次数据支撑）""",
        },
    ],

    "partnerships": [
        {
            "name": "product_hunt_launch",
            "source": "inferen-sh/skills (8.1K installs)",
            "description": "Product Hunt 发布完整策略",
            "framework": """发布前(2周):
- 准备 Gallery (5张截图+1个视频)
- 写好 tagline (60字符内)、description、first comment
- 联系 5-10 个 Hunter 找人帮你 Hunt
- 在社媒预热

发布日:
- 太平洋时间 00:01 发布
- 第一条评论: 创始人故事+为什么做这个
- 当天持续回复每一条评论
- 社媒同步推广

发布后:
- 给所有评论者发感谢邮件
- 把 PH badge 加到网站
- 发布复盘帖子""",
        },
        {
            "name": "influencer_outreach",
            "source": "dengineproblem/agents-monorepo (79 installs)",
            "description": "博主外联策略",
            "framework": """发现:
- 搜索 YouTube/Twitter/博客中讨论相关话题的人
- 优先 1K-10K 粉丝（小博主回复率高、性价比好）
- 评估: 受众匹配度、互动率、内容质量

外联:
- 邮件主题行: 具体+个人化（不要"合作邀请"）
- 第一句: 证明你看过对方的内容
- 价值交换: 你能给对方什么
- CTA: 一个明确的下一步

合作模式:
- 免费试用换评测（成本最低）
- 赞助内容（$100-1000 per post for small creators）
- 分佣/联盟（长期关系）""",
        },
    ],

    "paid_ads": [
        {
            "name": "ad_campaign_framework",
            "source": "openclaudia + superamped",
            "description": "广告投放框架",
            "framework": """测试流程:
1. 小额测试($20-50): 3组创意 × 2组受众
2. 72小时后分析: CPC、CTR、转化率
3. 砍掉最差的，放大最好的
4. 持续迭代

创意角度(5种):
- Problem: 展示痛点
- Solution: 展示结果
- Comparison: 和替代方案对比
- Proof: 用户案例/数据
- Curiosity: 激发好奇心

预算低于$500/月的建议:
- 不做 Google Ads（CPC 太贵）
- Reddit Ads 最便宜（CPM $0.5-2）
- 或者完全不做广告，把钱投到内容/合作上""",
        },
    ],

    "designer": [
        {
            "name": "social_design",
            "source": "eachlabs/skills (432 installs) + 404kidwiz",
            "description": "社媒视觉设计规范",
            "framework": """尺寸速查:
- Instagram: 1080×1080 (方) / 1080×1350 (竖)
- Twitter/X: 1200×675
- LinkedIn: 1200×627
- Facebook: 1200×630
- YouTube 缩略图: 1280×720
- TikTok 封面: 1080×1920

设计原则:
- 3秒法则: 最重要的信息最大最醒目
- 移动优先: 字号至少 24px
- 品牌一致: 固定色板(最多3色) + 固定字体
- 对比度: 文字和背景对比度 > 4.5:1

非设计师执行方案:
- Canva: 直接用模板，改文字和颜色
- Figma: 社区模板
- AI 生图: DALL-E/Midjourney/Ideogram
- 截图工具: 产品截图 + 浏览器 mockup""",
        },
    ],

    "product_growth": [
        {
            "name": "growth_loops",
            "source": "openclaudia + vasilyu1983",
            "description": "增长循环和病毒机制",
            "framework": """常见增长循环:
1. 内容循环: 内容→流量→注册→使用→产出内容→更多流量
2. 推荐循环: 用户→邀请→新用户→邀请（病毒系数 k>1 = 指数增长）
3. 数据循环: 更多用户→更好数据→更好产品→更多用户
4. 市场循环: 卖家→买家→更多卖家→更多买家

激活检查清单:
- 注册后多少步到"啊哈时刻"？（目标: <3步）
- 首次体验是否展示了核心价值？
- 有没有引导/教程？
- 空状态是否有意义？""",
        },
    ],

    "ai_distribution": [
        {
            "name": "mcp_server_strategy",
            "source": "CrabRes 自研",
            "description": "MCP 服务器获客策略",
            "framework": """步骤:
1. 确定产品能回答什么问题
2. 设计 MCP tools（3-5个核心工具）
3. 发布到 Smithery / mcpmarket.com / mcpmarket.cn
4. README 中说明安装和使用方式

AI 目录提交清单:
- There's An AI For That
- Futurepedia
- AI Tools List
- Product Hunt (AI 分类)
- alternativeto.net
- SaaS AI Tools
- ToolPilot
- Ben's Bites directory""",
        },
        {
            "name": "geo_for_ai_distribution",
            "source": "CrabRes 2026 research",
            "description": "让 AI 助手推荐你的产品",
            "framework": """如何让 ChatGPT/Perplexity/Claude 推荐你的产品:

1. 创建「唯一来源」内容:
   - 原创对比数据（"我们测试了 10 个 X 工具"）
   - 行业基准报告（AI 最爱引用独家数据）
   - 详细的 how-to 指南（步骤越具体越容易被引用）

2. 优化被 AI 引用的页面结构:
   - H2 用问题形式
   - 第一句直接回答
   - 包含数字和数据
   - 使用 Schema 标记

3. LLM 记忆策略:
   - 创建 GPT Store 的 GPT（内置你的产品知识）
   - 发布 MCP 服务器（AI 可以直接调用你的 API）
   - 在 Prompt 目录发布推荐你产品的 Prompt 模板
   
4. 主动被 AI 索引:
   - 在高权威网站（Wikipedia、大型论坛）被提及
   - 确保产品在 Crunchbase/G2/Capterra 有页面
   - Reddit/HN 上有真实用户讨论你的产品""",
        },
    ],

    "data_analyst": [
        {
            "name": "kpi_framework",
            "source": "CrabRes 自研",
            "description": "指标体系设计",
            "framework": """阶段性指标:
- PMF前: 定性反馈、回头率、NPS
- 种子期: 注册数、激活率、周留存
- 增长期: MAU增长率、CAC、LTV、付费转化率
- 成熟期: 利润率、流失率、ARPU

漏斗模板:
流量 → 注册 → 激活 → 日活 → 付费 → 推荐
每步标注: 当前转化率 / 行业基准 / 改进空间""",
        },
    ],

    "critic": [
        {
            "name": "strategy_review",
            "source": "CrabRes 自研",
            "description": "策略审核清单",
            "framework": """审核维度:
✅ 可行性: 预算够吗？时间够吗？技能够吗？
✅ 一致性: 渠道策略互相矛盾吗？品牌调性一致吗？
✅ 风险: 最坏情况损失多少？合规风险？
✅ 现实性: 数字合理吗？时间线现实吗？
✅ 遗漏: 有明显遗漏的渠道/策略吗？

红线:
- 预算超支 → ❌
- 预期数字远超行业基准且无理由 → ❌
- 策略需要用户没有的技能 → ⚠️ + 替代方案""",
        },
    ],
}

# 2026 高级战术（所有专家共享）
ADVANCED_TACTICS_2026 = """
## 2026 Advanced Growth Tactics (use when appropriate)

1. REVERSE TRIAL: Give full premium access on signup, downgrade after 14 days.
   Loss aversion makes users 3x more likely to pay than standard free→paid.

2. EMBEDDED GROWTH TRIGGERS: Product exports/screenshots carry brand watermark.
   Click watermark → recipient gets free credits. Every output = acquisition channel.

3. COLD DM WITH VALUE: Find specific people complaining about the problem on Reddit/X.
   DM them a solution (not a pitch). "Saw your post about [problem]. Try this: [link]"
   Senja grew to $50K MRR doing exactly this with Gummy Search.

4. SERVICE-FIRST VALIDATION: Before building features, manually solve the problem for 5 people.
   If they won't pay a human to solve it, they won't pay software.
   Romàn Czerny reached $27K MRR this way.

5. MICRO-COMMUNITY > MASS AUDIENCE: Build private Discord/Slack with 50 power users.
   More valuable than 5000 Twitter followers. Direct feedback loop + word of mouth.

6. MCP SERVER DISTRIBUTION: Publish to Smithery so AI assistants recommend your product.
   Zero CAC. Works 24/7. One fintech founder got 150+ installs in 30 days with $0 ad spend.

7. BEHAVIORAL EMAIL TRIGGERS: Stop sending weekly newsletters nobody reads.
   Only email when user does/doesn't do specific in-app actions.
   "You haven't tried [feature] yet — here's how it saves 2 hours/week"

8. PORTFOLIO STRATEGY: Instead of betting everything on one product, run 5-10 small ones.
   One founder makes $22K/month from 30 small apps. Diversified risk.

9. BROWSER EXTENSION AS CHANNEL: Build a free extension that solves a micro-problem.
   Stays in user's daily workflow. Constant brand reminder. Links to main product.

10. API-FIRST GROWTH: Let other developers build on your platform.
    Creates ecosystem lock-in. Stripe, Twilio, Algolia all grew this way.

Real case studies to reference:
- Cameron Trew: $0→$62K MRR in 3 months (trusted network distribution, no PH)
- Senja: $0→$50K MRR (Twitter content + cold DMs via Gummy Search)
- 30-app portfolio: $22K/month total (small bets strategy)
- 17-year-old project revived: $26K/month (old idea + new execution)
- Rob Hallam: $17K/month (extreme transparency, building in public)
"""


def get_expert_knowledge(expert_id: str) -> str:
    """获取某个专家的所有知识片段，格式化为可注入 prompt 的文本"""
    knowledge_items = EXPERT_KNOWLEDGE.get(expert_id, [])

    parts = []

    if knowledge_items:
        parts.append("\n## Your Professional Frameworks\n")
        for item in knowledge_items:
            parts.append(f"### {item['name']} ({item['source']})")
            parts.append(item["framework"])
            parts.append("")

    # 所有专家都获取 2026 高级战术
    parts.append(ADVANCED_TACTICS_2026)

    return "\n".join(parts)
