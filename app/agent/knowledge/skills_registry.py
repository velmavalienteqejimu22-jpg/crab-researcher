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

EXPERT_KNOWLEDGE: dict[str, list[dict[str, str]]] = {

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
            "name": "pricing_and_unit_economics",
            "source": "SaaS pricing benchmarks 2026 + behavioral economics research",
            "description": "定价策略、单位经济、预算分配（实战级）",
            "framework": """=== PRICING & UNIT ECONOMICS PRACTITIONER KNOWLEDGE ===

## Pricing Psychology (proven tactics)
- Charm pricing: $99 < $100 (left-digit effect, 8-12% conversion lift)
- Rule of 100: <$100 use percentage discount, >$100 use absolute discount
- Good-Better-Best: 3-tier pricing, middle tier = target (65% choose middle)
- Decoy effect: add inferior 3rd option to make preferred option look better
- Mental accounting: "$3/day" feels cheaper than "$90/month"
- Free→$1 jump: 10x bigger barrier than $1→$2. Free tier is strategic, not generous.
- Reverse trial (2026 trend): give FULL premium access → downgrade after 14 days. Loss aversion = 3x more likely to pay vs standard free→paid.
- Annual discount: offer 2 months free on annual plan (20% discount standard)

## Unit Economics (must-know formulas)
CAC = Total acquisition cost / New customers
LTV = ARPU x Average customer lifetime (months)
LTV:CAC ratio: >3:1 = healthy, <1:1 = bleeding money
Payback period = CAC / Monthly revenue per user
Quick ratio = (New MRR + Expansion MRR) / (Churned MRR + Contraction MRR). >4 = elite.
Magic number = Net new ARR / Sales & marketing spend. >0.75 = efficient.

## Budget Allocation Framework
For startups (<$1K/month marketing budget):
- 60% Content + Community (Reddit/X/小红书 — free labor, high ROI)
- 20% Tools (analytics, email, design — Canva/Mailchimp/GA)
- 20% Experiments (small ad tests, influencer micro-collabs)
- 0% on anything you can't measure

For growth stage ($1K-10K/month):
- 40% Paid ads (after organic proves product-market fit)
- 30% Content + SEO (long-term flywheel)
- 20% Influencer/partnerships
- 10% Experimentation

## Flywheel Economics
- Identify actions with COMPOUNDING returns (content SEO = flywheel, paid ads = treadmill)
- Every $1 should ideally generate >$1 in lifetime value AND make the next $1 more efficient
- Content + SEO: costs upfront, traffic compounds over months. After 6 months, CAC approaches $0.
- Paid ads: linear — stop spending = stop getting users. Use for acceleration, not foundation.
- Referral: viral coefficient k. If k>1, exponential growth. Even k=0.5 means each user brings 0.5 more.

## When to spend vs save
- Pre-PMF: spend $0 on marketing. Talk to users. Validate manually.
- Post-PMF (<100 users): content + community only. Prove organic works.
- Growth (100-1000 users): start testing paid channels with $20-50/test
- Scale (1000+ users): shift budget to highest-ROI channel. Kill everything else.""",
        },
    ],

    "content_strategist": [
        {
            "name": "seo_geo_aeo_2026",
            "source": "Lumar/Arcalea SEO experts 2026 + programmatic SEO research",
            "description": "SEO + GEO + AEO 三位一体内容策略（2026 实战）",
            "framework": """=== SEO / GEO / AEO CONTENT STRATEGY 2026 ===

## The Three Pillars (2026)
1. SEO (Search Engine Optimization): rank in Google/Bing traditional results
2. GEO (Generative Engine Optimization): get cited by ChatGPT/Perplexity/Google AI Overview
3. AEO (Answer Engine Optimization): get featured in snippets, knowledge panels, voice search

In 2026, all three matter. Peter Levels: AI referral traffic went from 4% to 20% in one month.

## SEO Fundamentals (still the foundation)
Keyword research:
1. Seed keywords → expand to keyword universe
2. Classify by intent: informational / navigational / commercial / transactional
3. Evaluate: search volume x competition x product relevance
4. Build topic clusters: 1 pillar page + N cluster pages
5. Priority: high relevance + low competition FIRST

Technical SEO checklist:
- Page speed <2.5s LCP (Core Web Vitals)
- Mobile-first (responsive)
- Clean URL structure (/category/keyword)
- Internal linking (every page linked from at least 2 others)
- XML sitemap + robots.txt
- HTTPS mandatory
- Schema markup (FAQ, Product, HowTo, Comparison)

## GEO — Getting Cited by AI (the 2026 gold rush)
How to make ChatGPT/Perplexity cite your content:

1. Structure content as direct answers:
   - H2 as questions ("What is the best X for Y?")
   - First sentence after H2 = direct answer (no preamble)
   - Include specific numbers and data
   - Add "as of 2026" timestamps (AI prefers fresh content)

2. Create "sole source" data:
   - Original research/surveys (AI LOVES citing unique data)
   - Benchmark reports
   - Comparison tables with real pricing/features
   - "We tested X products" type content

3. Schema markup for AI:
   - FAQPage schema → AI can parse your Q&A
   - Product schema → AI knows your pricing/features
   - HowTo schema → AI cites your step guides
   - Comparison schema → AI cites your comparison data

4. Get cited by high-authority sites:
   - Reddit/HN answers linking to your content
   - Guest posts on industry blogs
   - Be a source for journalists (HARO/Connectively)

## AEO — Featured Snippets & Voice
- Target question-based keywords ("how to", "what is", "best X for Y")
- Answer in <50 words for snippet eligibility
- Use numbered lists and tables (snippet-friendly formats)
- FAQ blocks on every important page

## Programmatic SEO (scale to 1000+ pages)
Pattern: [category] + [modifier] = unique page
Examples:
  "best [product] alternatives" → 500+ pages
  "[brand A] vs [brand B]" → 2000+ pages
  "[product] pricing 2026" → 1000+ pages

Execution: structured data + LLM content generation + manual quality review
Cost: ~$0.01-0.05 per page with DeepSeek. 10,000 pages = $100-500.

## Content Calendar
- 1 pillar page per month (3000+ words, comprehensive)
- 4 cluster pages per month (1000-1500 words each)
- 2 comparison pages per month (X vs Y)
- Weekly blog post (800-1200 words, topical)
- Repurpose everything: blog → X thread → 小红书笔记 → LinkedIn post""",
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
            "name": "x_twitter_deep_knowledge",
            "source": "X open-source algorithm reverse-engineering (tang-vu/x-algorithm-playbook) + Calmops 2026 indie hacker guide + 掘金实战心得",
            "description": "X/Twitter 实战运营知识（算法公式+冷启动+内容+互动+转化）",
            "framework": """=== X (TWITTER) PLATFORM PRACTITIONER-LEVEL KNOWLEDGE ===

## Algorithm Scoring Formula (from open-source reverse engineering, 2026 update)
Post Score = Σ (weight × P(action))
Algorithm predicts 19 user behaviors with these weights:
  POSITIVE: Reply (+2×), Quote (+1.5×), Retweet (+1×), Like (+1×), Follow author (+1×)
  NEGATIVE: Block (-10×), Report (-20×, devastating), Mute (-1×), "Not interested" (-1×)
  NEUTRAL (but tracked): Click, Dwell time, Profile visit

Key insight: 1 reply = 2 likes in algorithm value. 1 block = -10 likes. AVOID BLOCKS AT ALL COSTS.

## Recommendation Pipeline (4 steps)
1. Candidate Sources:
   - Thunder: tweets from people you follow (in-network, shown first)
   - Phoenix: ML-discovered tweets from strangers (out-of-network, harder to get into)
2. Filtering: 12 filters (too old, blocked author, spam, etc.) — content removed entirely
3. Scoring: Grok Transformer model predicts engagement probability → weighted score
4. Ranking: highest scores shown first. Author diversity penalty applied (don't post too frequently)

## 10 Golden Rules (from algorithm reverse-engineering)
1. REPLIES ARE KING — posts generating replies score ~2x higher
2. AVOID NEGATIVE SIGNALS — 1 block (-10×) wipes out 10 likes
3. SPACE YOUR POSTS — author diversity penalty kicks in after first post. Wait 2-4 hours between posts
4. IN-NETWORK FIRST — your followers see you before strangers do. Build follower base first
5. MEDIA MATTERS — Video > Image > Text (if video exceeds minimum length threshold)
6. DWELL TIME COUNTS — longer content = higher engagement signal (threads >> single tweets)
7. DON'T TRIGGER FILTERS — 12 filters can completely hide your content
8. AUTHENTIC ENGAGEMENT — algorithm tracks your interaction patterns. No engagement pods
9. STAY VERTICAL — consistent topic helps retrieval matching
10. QUALITY > QUANTITY — one great post beats five mediocre ones

## Cold Start Playbook (0 → 1000 followers)

### Account Setup
- Username: simple, memorable, no underscores/numbers if possible
- Bio formula: [Who you are] + [What you do] + [Value prop] + [CTA link]
- Profile photo: clear face, looking at camera, professional
- Pinned tweet: your best thread or product announcement

### Phase 1: 前两周 Reply Guy Strategy
- Find 10-20 large accounts in your niche (10K-100K followers)
- Reply to their tweets within 30 min of posting (early replies get top position)
- Reply MUST add value: data, personal experience, contrarian take (not "great point!")
- Goal: 20-30 quality replies/day → their followers notice you → follow you
- This alone can get 200-500 followers in 2 weeks

### Phase 2: 第三四周 Original Content
- Content ratio: 40% value/教学 + 25% personal/幕后 + 20% engagement + 15% promo
- 1 Thread per week (5-12 tweets): Hook → Value points → CTA
- 2-3 single tweets per day
- Post 3-5 tweets/day when <500 followers (building presence)
- Reduce to 1-2/day after 1000 followers (quality over quantity)

### Phase 3: Month 2+ Build in Public
- Share real numbers (MRR, users, failures)
- Vulnerability > perfection ("I launched and got 0 users" > fake success)
- Weekly milestones, monthly retrospectives

## Daily Engagement Routine (30-60 min, NON-NEGOTIABLE)
- Reply to 5-10 tweets from peers/targets (quality replies with data/opinions)
- Like 20-30 relevant tweets (maintain visibility)
- Quote retweet 3-5 tweets adding your perspective
- Check notifications and reply to ALL mentions
- Best times: 7-9 AM, 12-1 PM, 5-7 PM (user's target timezone). Post 30 min before peak.

## Thread Structure (the #1 growth format)
Tweet 1 (HOOK — decides everything):
  Formula: "I [did X / studied X / spent $X]. Here's what [I learned / nobody tells you / actually works]:"
  Must create curiosity gap. If hook fails, thread dies.
Tweet 2-N (VALUE):
  One idea per tweet. Short sentences. Line breaks for readability.
  Use images/screenshots to break up text.
  Each tweet should be standalone-readable (people enter mid-thread).
Last tweet (CTA):
  "Follow me for more [topic]" or "I'm building [product] — try it free: [link in reply]"
  NEVER put links in main tweet — put in reply (algorithm penalizes external links)

## Single Tweet Formulas That Work
- "I [achievement with number]. Here are the [N] things that actually worked:"
- "Most people think [common belief]. They're wrong. Here's why:"
- Before/After with specific numbers
- Screenshot of real data + 1-sentence hot take
- Contrarian opinion (drives replies which = 2× algorithm boost)

## What Kills Your Reach
- External links in main tweet (put in reply instead)
- More than 2 hashtags (looks spammy, this isn't Instagram)
- Engagement pods (algorithm detects coordinated behavior)
- Posting >5 times without spacing (author diversity penalty)
- Getting blocked by multiple users (devastating: -10× each)
- Deleting tweets (signals low quality to algorithm)

## Conversion: Followers → Customers
- Bio link → specific landing page with UTM (not homepage)
- Pinned tweet = social proof (best thread, or launch announcement)
- DM strategy: only after genuine interaction. Never cold pitch.
- Monitor keywords related to your product → jump into conversations organically
- Build relationship before selling (80/20: value/promo)""",
        },
        {
            "name": "xiaohongshu_deep_knowledge",
            "source": "千万级变现实操经验 + 蝉妈妈/飞瓜数据 + CrabRes 2026 平台研究",
            "description": "小红书实战运营知识（养号+算法+内容+人设+变现，基于千万级变现实操）",
            "framework": """=== 小红书 (XIAOHONGSHU/RED NOTE) PRACTITIONER-LEVEL KNOWLEDGE ===
(来源：已变现千万级的实操总结，不讲概念，一切基于实操)

## 底层逻辑（必须理解）
- 小红书是女性友好平台
- 小红书是种草平台（分享好物，不是卖东西）
- 小红书是"美好XX分享"平台（正面、积极、生活化）

## 四个流量口
关注 / 发现 / 本地 / 搜索
实际上只有两个重要：**发现页** + **搜索页**

### 发现页算法逻辑
笔记发布后两条路：A违规 B收录（被搜索到）
收录后的互动权重排名（口诀：**一关二评三点赞**）：
  关注 > 评论=转发 > 点赞=收藏
  1个关注 = 1个评论+1个转发
  1个评论 = 1个点赞+1个收藏

只要有人持续互动，平台持续推流，可以几个月甚至一年以上还有推荐。
口号：**做爆一篇，吃上一年**

### 搜索页算法逻辑
搜索排序决定流量，位置不固定，实时变动。
**关键词是核心中的核心！**
官方说法：好标题更多赞。标题非常重要×3。

关键词来源：
1. 系统默认推荐（基于用户标签）
2. 搜索热门（短期热搜词条）
3. 联想关键词（用户输入自动补齐）

关键词选择原则：
- 热搜是短期流量，关键词是长期流量
- 选竞争小+流量大+匹配度高的词，不要泛词
- 反推：如果你是用户，会搜什么词能找到你？
- 合理布局，别硬堆（硬堆=广告=降权废号）

## 八级流量池（真实数据）
一级 0-200：没违规就有，多篇看站内信
二级 200-500：大部分账号的常态，如果长期→检查活跃度/垂直/原创/质量
三级 500-2000：内容还行但互动率低，提高内容和互动
**注：2000以下基本是AI机器人内容水平**
四级 2000-2万：正常，新手容易达到的标准
五级 2万-10万：自然流最后一关，过了就人工审核。要找到这个节奏感
六级 10万-100万：门槛！系统判定营销号/标题党就不推了。做到10万=成功一半
七级 100万-500万：人工干预，看内容+核心价值观+舆论风险
八级 500万+：新手不用考虑

**我们的目标：常态五级（2万+），够得着六级（10万+）**

## 养号七天法（一机一卡一号，禁频繁切换）
Day 1：不改任何资料，不发内容，搜索行业关键词，认真刷30分钟×3次，真人活跃（关注点赞评论）
Day 2：同Day 1，搜索行业关键词刷，不发内容
Day 3：不用搜索，看发现页。一屏4-5篇中有3篇以上是行业内容=养号成功→修改资料→发第一篇干货
Day 4-7：每天3篇左右干货分享，7天保证10篇干货

判定成功：
- 发布第一篇就出"恭喜你XXX"提示
- 发布后10分钟点薯条推广，能加热=账号正常
- 能出恭喜=权重有保证，后续正常更新，推流越来越高

**前七天千万不能发营销内容！第一篇绝不能违规！**

## 内容创作实战

### 封面（决定点击率70%）
- 统一3:4竖屏
- 封面要跟标题对得上
- 封面加文字：把笔记内核放封面
- 单篇至少三图以上
- 要好看、简洁、有高级感
- **没思路直接抄同行**

### 标题（=武器，决定生死）
标题逻辑：**话题+情绪**，20字左右，包含主题关键词
标题跟封面、内容、选题四项要有关联

标题套路：
数字类："百分之九十的人都不知道XX这么简单" / "三招教你XX" / "十个做XX的网站"
话题+提问："XX如何赚到一百万？" / "新手如何做XX？" / "一部手机能做XX吗？"
矛盾反差："XX月入十万，但我辞职了" / "中专毕业凭什么能月入十万"
反向法："天天吃肉也能减肥" / "不运动也能减肥"
提问+方案："XX如何上手，一部手机就够了"
猎奇心理："从年入百万到外卖骑手" / "一支可以当传家宝的手表"

标题怎么找：**搜、蹭、学、抄**
搜：全网搜索平台搜你的行业词，看自动弹出的后缀=用户关心的问题
蹭：蹭热点，热点+自己的行业=爆（当天发，最迟半天内）
学：用工具拉同行爆文，提关键字+同类词，直接照抄
抄：同行写什么你就写什么，图片标题内容按自己习惯一比一复制

### 内容
- 前10篇必须优质，垃圾内容没用
- 前7天不考虑引流、转化、营销
- 不要原封不动偷图（100%识别），改图5分钟
- 文案不要照抄（照抄是傻逼），专业内容可用AI转化，首尾按个人习惯口语化改写
- 600字以上加分，800字最合适
- **不要自己思考内容×3！同行已经给了验证过的答案，先抄再优化**

## 人设模板（转化率核心）

用户已经见号色变，专家号基本没转化率了。最高转化的两类：
1. **同类人**：跟用户有一样困扰的人（"我也在减肥的姐妹"）
2. **先行者**：已经做过这件事的人（"减肥成功的普通人"）

ABC矩阵打法：
A素人展示生活 + B提问 + C回答，但ABC都是你的号
基于真实分享=信任度大大提升

具体人设选择：
- 意见领袖型：有专业性又有普适性（最佳，需技术积累）
- 普通人记录生活：最容易拉近用户，信任度高，适合多账号
- 品牌创始人：配合A种B收，专业背书增强信任

## 发布节奏
前三天一篇/天 → 七天内补到10篇 → 正式营销时15-21篇
养号后一天一更即可，每篇间隔4小时以上
发布后看是否能投流，前期不要关注浏览量×3

## 权重算法
账号权重：原创 + 垂直 + 内容质量 + 活跃度 + 等级
笔记权重 > 账号权重（好内容普通号也能爆）
关键词要有关联，宁少勿多勿乱

## 违规红线
- 一手机多账号频繁切换
- 昵称/头像/个签出现联系方式
- 搬运/非原创/刷数据/钓鱼分享
- 不友善行为/敏感内容
- 评论区留联系方式（包括暗示）
- 一上来就发营销笔记

## 变现路径
笔记 → 评论区/主页引导 → 私域（微信）→ 成交
笔记 → 小红书店铺 → 直接成交
笔记 → 品牌搜索 → 淘宝/京东成交（种草→搜索经典路径）
导流方式很多，绝不能在公开区域留联系方式""",
        },
        {
            "name": "reddit_deep_knowledge",
            "source": "Karmic Reddit Organic Playbook 2025 + ReplyAgent/OptaReach research + Reddit Pro official guide",
            "description": "Reddit 实战运营知识（Karma Ladder 四阶段 + CQS + 反封号 + 归因）",
            "framework": """=== REDDIT PRACTITIONER-LEVEL KNOWLEDGE ===
(Source: Karmic Reddit Organic Playbook + ReplyAgent + Reddit Pro official guide)

## Platform Culture (CRITICAL — violate this and you're dead)
- Reddit is ANTI-MARKETING. Users actively hunt and downvote promotional content.
- Each subreddit is its own country with its own laws (rules, mods, culture).
- Karma = credibility. Low karma account posting about a product = instant suspicion.
- Mods have absolute power. If a mod doesn't like your post, you're banned. No appeal.
- "10% rule": most subreddits expect <10% of your posts/comments to be self-promotional.
- Authenticity is currency. "I built this" posts work. "Check out this amazing tool" posts die.

## CQS: Contributor Quality Score (HIDDEN — critical to understand)
Reddit has a HIDDEN account quality score that determines if your content gets shown:
- Factors: email verified, 2FA enabled, interaction quality (comments > posts), 
  content performance relative to community, behavior patterns (bot-like = penalized),
  mod actions (posts deleted = severe CQS damage)
- LOW CQS = posts auto-hidden or removed silently (you won't even know)
- HIGH CQS = priority display, content shown more broadly
- Building CQS takes weeks of genuine participation. Destroying it takes one spam post.

## Product-Reddit-Fit Assessment (before investing time)
Not every product belongs on Reddit. Score 0-10 on:
1. Pre-purchase consideration: Do customers research heavily before buying? (SaaS=yes, impulse buy=no)
2. Total addressable audience: Are there enough potential users? (mass market=yes, ultra-niche enterprise=no)
3. Show vs Tell: Does your product need text explanation? (B2B software=tell=good fit, fashion=show=harder)

Scoring: 8-10 = go all in. 5-7 = test in 2-3 subreddits. 0-4 = skip Reddit, just monitor.

## Karma Ladder: 120-Day Four-Phase Strategy (from Karmic)

### Phase 1: Foundation (Day 1-30) — BUILD LEGITIMACY
Goal: pass Reddit's spam filters, build real karma
- Account: use "brandname_yourname" format, verify email, enable 2FA
- Day 1-2: ONLY browse. No likes, no comments. Let algorithm observe you.
- Day 3-14: Join LOW-STAKES subreddits (r/AskReddit, r/CasualConversation)
  Post 1-3 helpful comments/day. ZERO brand mentions.
- Day 15-30: Gradually join TARGET subreddits (where your users hang out)
  Continue commenting helpfully. Still NO brand mentions.
- Target: 100+ karma, 30-day account age, zero violations

### Phase 2: Authority (Day 31-90) — BECOME TRUSTED VOICE
Goal: gain recognition in target communities
- Post 1-3 comments/day in target subreddits
- Directly answer questions, provide context, share experiences
- GOLDEN RULE: never mention your brand/product/website
- If someone asks for recommendations, reply "happy to share via DM"
- Target: 250+ karma, 25+ karma in each of 1-3 target subreddits

### Phase 3: Engagement (Day 91-120) — CREATE DISCUSSION
Goal: post high-engagement topics that boost authority
- Post "engagement topics": emotional triggers, hot takes, industry debates
- Title must be compelling, body must invite discussion
- Reply to every comment on your posts (boosts engagement metrics)
- ABSOLUTELY NO self-promotion or sneaky link insertion
- Target: at least 1 post per target subreddit with 25K+ views

### Phase 4: Intent (Day 120+) — GENTLE PROMOTION
Three types of promotional content (ONLY after phases 1-3):
1. Adapted content: repurpose blog/LinkedIn posts into Reddit-native format. Remove brand jargon.
2. Brand announcements: new features, funding, partnerships. GET MOD PERMISSION FIRST.
3. AMA (Ask Me Anything): founder answers community questions. Best trust-builder. Often cited by AI engines.

## Algorithm & Ranking
- Hot algorithm: score = upvotes - downvotes, weighted by recency (logarithmic)
- First 10 upvotes = same weight as next 100 (early momentum is everything)
- First 1-2 hours critical — early downvotes kill a post permanently
- Comments ranked similarly: early upvoted comments "lock" at top
- Google indexes Reddit HEAVILY — top posts rank in search for 6-24 months
- This is why replying to Google-ranking old posts = passive long-term traffic

## Content Formats Ranked
1. "I did X. Here's what happened." (experience share) → highest trust
2. "Guide: How to do X" (tutorial) → gets bookmarked, long Google shelf life
3. "I analyzed X for Y days" (data/research) → upvoted for effort, often viral
4. "AMA about X" → great if you have genuine expertise
5. "I built X" (show & tell) → works in r/SideProject, r/startups

## Reply Strategy (often MORE effective than posting)
- Find posts ALREADY ranking on Google for your keywords → reply with value + product mention
  These get steady traffic for months. Your reply = passive leads forever.
- Reply within 2 hours of new posts (early replies get top position)
- Reply structure: 3-5 sentences genuine help + 1 sentence natural product mention
- Never reply from alt accounts (Reddit detects cross-account patterns)

## Anti-Ban Survival
- Never same link to multiple subreddits simultaneously
- Space self-promotional posts by 7+ days minimum
- If post removed: DON'T repost. Message mods politely, ask why.
- Vary content format and writing style between posts
- Old account with history >> new account (CQS advantage)
- One bad move can trigger shadowban (you post, nobody sees — check r/ShadowBan)

## Result Attribution (the hard part)
Reddit doesn't support clean UTM tracking. Use multi-signal approach:
1. Reddit metrics: karma gained, post views, comment upvotes
2. Holy grail: OTHER users mentioning your brand in threads you didn't participate in
3. Website: reddit.com referral traffic + LLM referral traffic (ChatGPT/Perplexity citing your Reddit posts)
4. Best attribution method: add "Where did you hear about us?" with "Reddit" option on signup form""",
        },
    ],

    "partnerships": [
        {
            "name": "influencer_kol_outreach_sop",
            "source": "MySocial/Sprout Social/KolSprite 2026 + 蒲公英平台数据",
            "description": "KOL/博主合作完整 SOP（发现→评估→外联→合作→追踪）",
            "framework": """=== KOL/INFLUENCER COLLABORATION SOP ===

## Discovery (找人)
1. Define ICP (Ideal Creator Profile):
   - Follower range: 1K-10K (micro, highest ROI) / 10K-100K (mid, best reach/cost balance) / 100K+ (macro, brand awareness)
   - Engagement rate threshold: >3% Instagram, >5% TikTok, >1% YouTube
   - Audience overlap with your target: >50% match
   - Content style must fit your brand naturally

2. Where to find creators:
   - Platform native: Instagram Explore, TikTok Creator Marketplace, YouTube search
   - Tools: Modash.io, Heepsy, Upfluence, CreatorIQ
   - Competitor analysis: who are your competitors working with? (check their tagged posts)
   - Hashtag mining: search #[your niche] and find creators posting there
   - 小红书: 蒲公英平台 (official), 蝉妈妈/飞瓜 (third-party data)

3. Vetting checklist (MUST check before outreach):
   ✅ Engagement rate (likes+comments / followers > 3%)
   ✅ Comment quality (real conversations vs "nice!" / emoji spam)
   ✅ Audience demographics (age/gender/location match your target?)
   ✅ Recent content quality and frequency (active? declining?)
   ✅ Brand safety: scan last 6 months for controversy, political takes, competitor deals
   ✅ Fake follower check (sudden spikes in follower count = bought followers)
   ❌ SKIP creators with: >50% ads in recent posts, bought followers, recent controversy

## Outreach (联系)
Tiered approach:
- Micro (1K-10K): DM first, then email. Offer free product. No payment needed for most.
- Mid (10K-100K): Email with personalized pitch. Product + $200-1000 fee.
- Macro (100K+): Through agent/manager. Product + $1000-10000+.

Email template structure (under 150 words!):
  Line 1: Reference their SPECIFIC recent content (proves you actually watched)
  Line 2: One sentence about your product
  Line 3: Specific offer (free product, fee, commission)
  Line 4: No-pressure CTA ("Would you be open to trying it?")

Follow-up: Day 3-5 (different angle, NOT "just checking in"). Max 1 follow-up.

## Collaboration (执行)
- Send product with: branded packaging + handwritten note + content brief
- Content brief must include: key messages (max 3), hashtags, tracking link/promo code, deadline, format preference
- Set up UTM links or unique promo codes per creator (essential for ROI tracking)
- Don't over-script: let creator maintain their authentic voice

## Tracking & ROI
- Track per creator: views, engagement, link clicks, promo code uses, conversions
- Calculate CPA per creator = (product cost + fee + shipping) / conversions
- Compare across tiers: micro vs mid vs macro ROI
- Top performers → long-term relationship → ambassador program
- Underperformers → analyze why, don't repeat

## Pricing Reference (2026)
Instagram post: micro $50-300, mid $300-2000, macro $2000-20000
TikTok video: micro $100-500, mid $500-5000, macro $5000-50000
YouTube video: micro $200-1000, mid $1000-10000, macro $10000-100000
小红书笔记: 素人¥50-200, KOC¥200-1000, 腰部¥1000-10000, 头部¥10000+""",
        },
        {
            "name": "product_hunt_launch_sop",
            "source": "inferen-sh/skills + 2026 PH best practices",
            "description": "Product Hunt 发布完整策略",
            "framework": """=== PRODUCT HUNT LAUNCH SOP ===

Pre-launch (2-4 weeks before):
- Build email list of supporters (aim 200+ for launch day votes)
- Prepare Gallery: 5 screenshots + 1 demo video (30-60 sec)
- Write tagline (60 chars max): benefit-focused, not feature-focused
- Write description (260 chars): who it's for + what it does + why it's different
- Write first comment (the story): why you built this, personal journey, what's next
- Find a Hunter (someone with 1000+ followers to submit for you) — check PH leaderboard
- Schedule launch for Tuesday (highest traffic day), 12:01 AM PST

Launch day:
- Post at 00:01 PST (Pacific Time)
- First comment ready immediately (founder story + ask for feedback)
- Reply to EVERY comment within 1 hour (engagement signal to PH algorithm)
- Social media blitz: X thread + LinkedIn + email to list + Discord/Slack communities
- Keep engagement high for first 4 hours (PH ranking is velocity-based)

Post-launch:
- Thank everyone who commented (DM or email)
- Add PH badge to your website
- Write a launch retrospective (great content for X/LinkedIn)
- Follow up with anyone who offered to connect""",
        },
    ],

    "paid_ads": [
        {
            "name": "paid_ads_complete_sop",
            "source": "Meta Ads 2026 guides + Buffer + Adsmurai specs",
            "description": "付费广告投放完整 SOP（平台选择→创意→测试→放大→优化）",
            "framework": """=== PAID ADVERTISING COMPLETE SOP ===

## Platform Selection (which platform for which product)
- Meta (Facebook+Instagram): best for B2C, visual products, lifestyle. Broad targeting works now (Advantage+ AI).
- Google Ads: best for high-intent searches ("buy X", "X near me"). Expensive but high conversion.
- TikTok Ads: best for Gen Z, entertaining/visual products. Cheapest CPM but lower intent.
- Reddit Ads: cheapest CPM ($0.50-2). Good for niche targeting by subreddit. Low competition.
- LinkedIn Ads: best for B2B. Most expensive ($8-12 CPC) but highest lead quality.
- Pinterest Ads: underrated for e-commerce/lifestyle. Long ad lifespan (pins live for months).

## Creative Production
Ad sizes cheat sheet:
  Meta: 1080x1080 (feed), 1080x1350 (feed vertical), 1080x1920 (stories/reels)
  Google Display: 1200x628 (landscape), 300x250 (rectangle)
  TikTok: 1080x1920 (full screen vertical)
  LinkedIn: 1200x627 (single image), 1080x1080 (carousel)
  Pinterest: 1000x1500 (standard pin), 1080x1920 (idea pin)

5 creative angles (test all):
1. PROBLEM: Show the pain ("Tired of X?") — emotional hook
2. SOLUTION: Show the result ("From X to Y in Z days") — aspirational
3. SOCIAL PROOF: Show others using it ("10,000 users trust...") — trust
4. COMPARISON: Side-by-side with competitor/old way — logical
5. UGC-STYLE: Looks like organic content, not an ad — highest CTR in 2026

Video ad rules:
- Hook in first 3 seconds (or user scrolls past)
- 15-30 seconds optimal length
- Captions mandatory (85% watch without sound)
- CTA at end AND as text overlay throughout
- UGC style > polished studio (2-3x higher CTR on Meta/TikTok)

## Testing Framework
Phase 1 (test): $20-50 per ad set, 72 hours, DON'T TOUCH
  - 3 audiences x 3 creatives = 9 ad sets
  - Automatic bidding (let algorithm learn)
  - Measure: CPA, CTR, ROAS

Phase 2 (analyze): after 72 hours
  - Kill bottom 50% (be ruthless)
  - Identify: which audience? which creative? which placement?
  - Don't average — look at individual ad set performance

Phase 3 (scale): increase budget 20% every 3 days on winners
  - Create variations of winning creative (same angle, new visuals)
  - Add lookalike audiences based on converters
  - Monitor CPA — if it rises >50% above test phase, pause and refresh creative

## Budget Rules
- <$500/month: probably don't do paid ads. Use organic channels.
- $500-2000/month: test ONE platform thoroughly. Don't spread thin.
- $2000-10000/month: primary platform + one secondary test
- Never spend >50% of budget on unproven creative

## Tracking Setup (DO THIS FIRST or you waste money)
1. Install Meta Pixel / Google Tag / TikTok Pixel on your site
2. Set up conversion events: PageView, AddToCart, Purchase/Signup
3. Create UTM parameters for each campaign
4. Verify events fire correctly (test purchase)
5. Wait 3-7 days for pixel to collect data before optimizing""",
        },
    ],

    "designer": [
        {
            "name": "ad_creative_design_sop",
            "source": "mediacheatsheet.com + Adsmurai specs + UGC best practices 2026",
            "description": "广告创意与社媒视觉设计实战（尺寸+原则+UGC+工具）",
            "framework": """=== CREATIVE DESIGN PRACTITIONER KNOWLEDGE ===

## Platform Ad Specs (2026, always verify on platform)
Meta (Facebook/Instagram):
  Feed: 1080x1080 (square) or 1080x1350 (vertical, recommended)
  Stories/Reels: 1080x1920 (9:16)
  Carousel: 1080x1080 per card
  Text overlay: <20% of image area (algorithm penalizes text-heavy)

X (Twitter): 1200x675 (16:9) or 1080x1080
Google Display: 1200x628, 300x250, 728x90 (responsive display ads preferred)
YouTube: 1920x1080 (video), 1280x720 (thumbnail)
TikTok: 1080x1920 (9:16 ONLY), video 15-60 sec
LinkedIn: 1200x627 (single), 1080x1080 (carousel)
Pinterest: 1000x1500 (2:3), 1080x1920 (9:16 idea pin)
小红书: 1080x1440 (3:4), cover image CRITICAL for CTR

## Design Principles (non-negotiable)
1. 3-SECOND RULE: Most important info = biggest + most visible
2. MOBILE-FIRST: 85% of social media is mobile. Min font 24px.
3. BRAND CONSISTENCY: Max 3 colors + 1-2 fonts across all materials
4. CONTRAST: Text-to-background contrast ratio >4.5:1 (WCAG AA)
5. HIERARCHY: Eye path should go: Hook → Value → CTA
6. WHITE SPACE: Don't cram. Breathing room = premium feel.

## UGC (User-Generated Content) — 2026's highest-performing ad format
- UGC ads outperform studio ads 2-3x on CTR (Meta/TikTok data)
- Why: looks organic in feed, triggers trust, doesn't feel like an ad
- How to create:
  1. Use iPhone (not professional camera)
  2. Natural lighting (no studio setup)
  3. Person talking to camera or showing product in real use
  4. Captions always (auto-caption tools: CapCut, Descript)
  5. First 3 sec = hook ("I've been using X for 30 days and...")
  6. 15-30 sec total
  7. End with clear CTA ("Link in bio" / "Comment for link")

## Tools for non-designers
Image: Canva (templates), Figma (community files), Midjourney/DALL-E (concept art)
Video: CapCut (editing + captions), Descript (podcast→video), Loom (screen record)
Mockups: Shots.so (app screenshots), Smartmockups (product in context)
Batch creation: Canva Bulk Create, Bannerbear (API-based)

## Creative Refresh Cadence
- Ads fatigue after 7-14 days (CTR drops, CPA rises)
- Refresh creative weekly: same angle + new visuals/copy
- Keep winning hooks, change everything else
- Archive all creatives with performance data for future reference""",
        },
    ],

    "product_growth": [
        {
            "name": "plg_playbook_2026",
            "source": "PLG 7-layer guide 2026 + IdeaPlan + Beancount",
            "description": "产品驱动增长完整体系（激活→留存→病毒→扩张）",
            "framework": """=== PRODUCT-LED GROWTH (PLG) 2026 PLAYBOOK ===

## The PLG Flywheel
Acquire → Activate → Engage → Monetize → Expand → Advocate → (back to Acquire)
Each stage feeds the next. The product IS the growth engine.

## Activation (most important metric for early-stage)
Activation = user reaches "Aha Moment" (first time they get real value)
- Map your activation path: signup → [step 1] → [step 2] → Aha Moment
- Goal: <3 steps from signup to value
- Measure: % of signups who reach Aha Moment within first session
- Industry benchmark: 20-40% activation rate = good for SaaS

Onboarding checklist:
1. Zero-friction signup (email/Google only, no credit card, no phone)
2. First value in <60 seconds (show the magic before asking for anything)
3. Guided tour (interactive > video > static text)
4. Empty states that educate (don't show blank screens)
5. Progress indicator (humans complete things that look almost done)
6. Contextual tips (show features when relevant, not all at once)

## Retention
- Day 1 retention: did they come back the next day?
- Week 1 retention: did they use it 3+ times in first week?
- 30-day retention: benchmark varies, but >40% = strong

Retention tactics:
1. Behavioral email triggers (NOT newsletters):
   - "You haven't tried [feature] yet" (day 3)
   - "Your [metric] improved 23% this week" (weekly)
   - "You're on a 5-day streak!" (engagement gamification)
2. Push notifications (sparingly): only for high-value events
3. Habit loops: tie product usage to existing daily routine
4. Social features: invite team, share results, collaborate

## Viral Loops
Types:
1. Inherent virality: using the product creates exposure (e.g., Calendly link in emails)
2. Word of mouth: product is so good people tell others (NPS > 50)
3. Incentivized referral: give both referrer and referee something
4. Content virality: user-generated output is shareable (e.g., Spotify Wrapped)

Viral coefficient (k) = invitations per user x conversion rate of invites
k > 1 = exponential growth (extremely rare)
k = 0.5 = each user brings 0.5 more (still very valuable, 50% cheaper CAC)

Referral program design:
- Double-sided reward (giver AND receiver get value)
- Reward should be product-related (free months > random swag)
- Make sharing frictionless (1-click invite, pre-written message)
- Show progress ("3 friends invited, 2 more for premium month")

## Expansion Revenue
- Usage-based pricing: charge more as they use more (natural expansion)
- Seat-based: each new team member = revenue
- Feature gating: free tier → paid features (but free must be genuinely useful)
- Annual plans: offer 20% discount for annual commitment (reduces churn, improves cash flow)

## Key Metrics Dashboard
- Activation rate: signups → Aha Moment
- Time to value: how long from signup to first value
- Feature adoption: % using each key feature
- Retention: D1/D7/D30 curves
- NPS: >50 = viral potential
- Expansion rate: revenue growth from existing users
- Quick ratio: (new + expansion MRR) / (churned + contraction MRR)""",
        },
    ],

    "ai_distribution": [
        {
            "name": "mcp_server_strategy",
            "source": "CrabRes 2026 + Smithery data",
            "description": "MCP 服务器 + AI 目录获客策略",
            "framework": """=== AI DISTRIBUTION STRATEGY ===

## MCP Server (Model Context Protocol) — zero-CAC acquisition
Steps:
1. Identify what questions your product can answer
2. Design 3-5 MCP tools (focused, not generic)
3. Publish to: Smithery (smithery.ai), mcpmarket.com, mcpmarket.cn
4. README with clear install instructions + use cases

## AI Directory Submission Checklist
- There's An AI For That (theresanaiforthat.com) — largest AI directory
- Futurepedia — curated AI tools
- AI Tools List
- Product Hunt (AI category)
- alternativeto.net
- SaaS AI Tools + ToolPilot + Ben's Bites directory

## GEO: Getting AI to Recommend Your Product
1. Create "sole source" content (original research, benchmarks, comparison data)
2. Optimize page structure for AI citation (H2 as questions, direct answers first)
3. Schema markup (FAQ, Product, HowTo)
4. Get mentioned on high-authority sites (Wikipedia, Reddit, G2, Capterra)
5. Build GPT Store presence (custom GPTs with your product knowledge)
6. Publish MCP server (AI can directly call your API)""",
        },
    ],

    "data_analyst": [
        {
            "name": "growth_analytics_framework",
            "source": "Industry benchmarks 2026 + funnel analysis best practices",
            "description": "增长数据分析完整框架（指标→漏斗→实验→归因）",
            "framework": """=== GROWTH ANALYTICS FRAMEWORK ===

## Stage-Appropriate Metrics
Pre-PMF: qualitative feedback, return rate, NPS, willingness to pay
Seed (0-100 users): signups, activation rate, D7 retention
Growth (100-1000): MAU growth rate, CAC, LTV, paid conversion
Scale (1000+): profit margin, churn rate, ARPU, expansion revenue

## Funnel Template
Traffic → Signup → Activation → Active (D7) → Paid → Referral
For each step: current rate / industry benchmark / gap / improvement hypothesis

Industry benchmarks (SaaS):
- Landing page → Signup: 2-5% (good), >8% (excellent)
- Signup → Activation: 20-40% (good), >60% (excellent)
- Activation → D7 Active: 25-40% (good)
- Free → Paid: 2-5% (freemium), 10-25% (free trial)
- Monthly churn: <5% (good), <2% (excellent)

## Experiment Design (don't guess, test)
Structure:
1. Hypothesis: "If we [change], then [metric] will improve by [amount] because [reason]"
2. Sample size: minimum 100 conversions per variant for statistical significance
3. Duration: minimum 7 days (capture day-of-week effects)
4. One variable at a time (unless using multivariate testing)
5. Document EVERYTHING: what, why, result, learning

## Attribution
- First touch: which channel introduced the user?
- Last touch: which channel closed the conversion?
- Multi-touch: credit distributed across journey
- For startups: simple self-reported "How did you hear about us?" field
  (dropdown: Reddit, X/Twitter, Google search, friend referral, AI recommendation, other)
  This is often more accurate than any attribution tool.

## Dashboards (what to build)
Daily: signups, activation, revenue
Weekly: CAC, LTV, retention cohorts, experiment results
Monthly: channel ROI comparison, growth rate, burn rate""",
        },
    ],

    "critic": [
        {
            "name": "strategy_review_checklist",
            "source": "CrabRes + Y Combinator startup advice + common failure patterns",
            "description": "策略审核完整清单（可行性+一致性+风险+现实性）",
            "framework": """=== STRATEGY REVIEW CHECKLIST ===

## Feasibility Check
- Budget: does the user have enough money? (if not, recommend $0 alternatives)
- Time: can they execute with ≤30 min/day? (most indie hackers have day jobs)
- Skills: do they have the required skills? (if not, suggest tools/services)
- Tech barriers: does it require coding/design/video? (suggest no-code alternatives)

## Consistency Check
- Channel strategies: do they contradict each other? (e.g., premium brand + discount ads)
- Brand voice: consistent across all channels?
- Budget allocation: aligned with priorities?
- Timeline: realistic sequencing? (can't launch PH before product is ready)

## Risk Assessment
- What's the worst case? (how much money/time lost if this fails completely)
- Compliance risks? (GDPR, FTC influencer disclosure, platform ToS)
- Dependency risks? (relies on one channel that could change algorithm/rules)
- Reputation risks? (aggressive Reddit strategy could backfire)

## Reality Check
- Are the projected numbers reasonable? Compare to industry benchmarks.
  "1000 users from Reddit in 1 month" — unlikely without paid promotion.
  "50 signups from 10 Reddit posts" — possible if targeting right subreddits.
- Is the timeline realistic? Organic SEO = 3-6 months. Reddit = 2-4 weeks. Ads = 72 hours.
- Are there assumptions that haven't been validated?

## Missing Check
- Any obvious channels not considered? (e.g., user ignored SEO for a content product)
- Competitors doing something the plan doesn't address?
- Customer retention strategy missing? (all acquisition, no retention = leaky bucket)

## Output Format
✅ Passes review (with specific praise for what's strong)
⚠️ Needs attention (with specific fix suggestion)
❌ Must change (with alternative approach)""",
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

    # 合并扩展知识库（7 个新增知识模块）
    try:
        from app.agent.knowledge.knowledge_expansion import get_expanded_knowledge
        expanded = get_expanded_knowledge(expert_id)
        if expanded:
            parts.append(expanded)
    except ImportError:
        pass

    # 所有专家都获取 2026 高级战术
    parts.append(ADVANCED_TACTICS_2026)

    return "\n".join(parts)
