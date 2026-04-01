/**
 * CrabRes 生物体系统
 * 
 * 不只是螃蟹——是一个海洋生物家族。
 * 每个用户的生物体由产品类型 + 用户ID 确定性生成。
 * 没有两个用户的生物体完全一样。
 */

export type CreatureSpecies =
  | 'crab'        // 🦀 螃蟹 — SaaS/工具类
  | 'octopus'     // 🐙 章鱼 — 社区/社交类
  | 'jellyfish'   // 🪼 水母 — 内容/媒体类
  | 'pufferfish'  // 🐡 河豚 — 电商/零售类
  | 'seahorse'    // 🐴 海马 — 教育/学习类
  | 'starfish'    // ⭐ 海星 — 创意/设计类
  | 'turtle'      // 🐢 海龟 — 金融/稳健型
  | 'clownfish'   // 🐠 小丑鱼 — 娱乐/游戏类
  | 'whale'       // 🐋 小鲸鱼 — 企业/B2B 大客户
  | 'shrimp'      // 🦐 小虾 — 超早期/刚开始

export type CreatureMood =
  | 'happy'       // 开心（增长好）
  | 'thinking'    // 思考中（研究中）
  | 'excited'     // 兴奋（大发现/里程碑）
  | 'worried'     // 担忧（发现问题）
  | 'sleeping'    // 睡觉（夜间整理）
  | 'working'     // 工作中（执行任务）
  | 'waving'      // 打招呼（欢迎/回归）
  | 'sad'         // 伤心（用户久没来）
  | 'celebrating' // 庆祝（达成目标）
  | 'idle'        // 默认状态

export type CreatureSize = 'tiny' | 'small' | 'medium' | 'large' | 'grand'

export interface CreatureAccessory {
  id: string
  name: string
  emoji: string        // 仅内部标识用，UI 用 SVG
  description: string
  unlockedBy: string   // 解锁条件
}

export interface CreatureState {
  species: CreatureSpecies
  mood: CreatureMood
  size: CreatureSize
  name: string                    // 用户可以给它起名字
  color: string                   // 主色调（hex）
  accentColor: string             // 辅助色
  accessories: CreatureAccessory[]
  streakDays: number
  totalUsers: number              // 用户的产品用户数
  growthRate: number              // 周增长率 %
  level: number                   // 1-100
  xp: number                     // 当前经验值
  xpToNext: number               // 升级需要的经验值
}

// ====== 物种配置 ======

export const SPECIES_CONFIG: Record<CreatureSpecies, {
  displayName: string
  description: string
  baseColor: string
  accentColor: string
  personality: string
}> = {
  crab: {
    displayName: 'Tech Crab',
    description: 'Resourceful and tenacious. Moves sideways to find the best path.',
    baseColor: '#F97316',
    accentColor: '#FB923C',
    personality: 'methodical',
  },
  octopus: {
    displayName: 'Social Octopus',
    description: 'Eight arms, eight strategies. Connects everything to everything.',
    baseColor: '#8B5CF6',
    accentColor: '#A78BFA',
    personality: 'connector',
  },
  jellyfish: {
    displayName: 'Flow Jelly',
    description: 'Goes with the current. Creates beautiful content effortlessly.',
    baseColor: '#06B6D4',
    accentColor: '#67E8F9',
    personality: 'creative',
  },
  pufferfish: {
    displayName: 'Puff Merchant',
    description: 'Small but mighty. Puffs up to grab attention when it matters.',
    baseColor: '#EAB308',
    accentColor: '#FDE047',
    personality: 'bold',
  },
  seahorse: {
    displayName: 'Wise Seahorse',
    description: 'Patient and nurturing. Knows that growth takes time.',
    baseColor: '#10B981',
    accentColor: '#6EE7B7',
    personality: 'patient',
  },
  starfish: {
    displayName: 'Star Creator',
    description: 'Regenerates endlessly. Turns every setback into a comeback.',
    baseColor: '#EC4899',
    accentColor: '#F9A8D4',
    personality: 'resilient',
  },
  turtle: {
    displayName: 'Steady Turtle',
    description: 'Slow and steady wins the race. Compound growth is the way.',
    baseColor: '#059669',
    accentColor: '#34D399',
    personality: 'steady',
  },
  clownfish: {
    displayName: 'Fun Fish',
    description: 'Brings joy everywhere. Makes your product impossible to ignore.',
    baseColor: '#F43F5E',
    accentColor: '#FDA4AF',
    personality: 'playful',
  },
  whale: {
    displayName: 'Big Blue',
    description: 'Thinks big. Moves markets. Gentle giant with serious strategy.',
    baseColor: '#3B82F6',
    accentColor: '#93C5FD',
    personality: 'ambitious',
  },
  shrimp: {
    displayName: 'Tiny Starter',
    description: 'Small but scrappy. Every giant started as a shrimp.',
    baseColor: '#FB7185',
    accentColor: '#FECDD3',
    personality: 'scrappy',
  },
}

// ====== 配饰库 ======

export const ACCESSORIES: CreatureAccessory[] = [
  // 基础配饰（注册就有）
  { id: 'scarf-blue', name: 'Blue Scarf', emoji: '🧣', description: 'A cozy starter scarf', unlockedBy: 'signup' },

  // 里程碑配饰
  { id: 'badge-first10', name: 'First 10 Badge', emoji: '🏅', description: 'Reached 10 users', unlockedBy: 'users:10' },
  { id: 'badge-first100', name: 'Century Badge', emoji: '💯', description: 'Reached 100 users', unlockedBy: 'users:100' },
  { id: 'crown-1k', name: 'Growth Crown', emoji: '👑', description: 'Reached 1,000 users', unlockedBy: 'users:1000' },
  { id: 'wings-10k', name: 'Golden Wings', emoji: '✨', description: 'Reached 10,000 users', unlockedBy: 'users:10000' },

  // 连胜配饰
  { id: 'flame-7d', name: 'Week Flame', emoji: '🔥', description: '7-day streak', unlockedBy: 'streak:7' },
  { id: 'flame-30d', name: 'Month Blaze', emoji: '🔥', description: '30-day streak', unlockedBy: 'streak:30' },
  { id: 'diamond-90d', name: 'Diamond Streak', emoji: '💎', description: '90-day streak', unlockedBy: 'streak:90' },

  // 行为配饰
  { id: 'glasses', name: 'Research Glasses', emoji: '🤓', description: 'Completed first deep research', unlockedBy: 'action:first_research' },
  { id: 'megaphone', name: 'Megaphone', emoji: '📢', description: 'Published first social post via CrabRes', unlockedBy: 'action:first_post' },
  { id: 'envelope', name: 'Golden Envelope', emoji: '✉️', description: 'Sent first outreach email', unlockedBy: 'action:first_email' },
  { id: 'headphones', name: 'Headphones', emoji: '🎧', description: 'Connected analytics', unlockedBy: 'action:connect_analytics' },
  { id: 'cape', name: 'Strategy Cape', emoji: '🦸', description: 'Completed 3 strategy iterations', unlockedBy: 'action:3_iterations' },
  { id: 'hat-chef', name: 'Chef Hat', emoji: '👨‍🍳', description: 'Used all 13 experts at least once', unlockedBy: 'action:all_experts' },
]

// ====== 确定性生成 ======

/**
 * 基于用户 ID 和产品类型确定性地生成生物体
 * 相同输入永远得到相同结果（学 Claude Code Buddy 的 Mulberry32 PRNG）
 */
export function generateCreature(userId: string, productType: string): CreatureState {
  // 简单的哈希函数
  const hash = simpleHash(userId + ':' + productType)

  // 根据产品类型选物种（有默认映射但加入随机性）
  const species = pickSpecies(productType, hash)
  const config = SPECIES_CONFIG[species]

  // 颜色微调（同物种不同用户的颜色略有不同）
  const colorShift = (hash % 20) - 10 // -10 到 +10 的色调偏移

  return {
    species,
    mood: 'waving',
    size: 'tiny',
    name: '',  // 用户稍后命名
    color: config.baseColor,
    accentColor: config.accentColor,
    accessories: [ACCESSORIES[0]], // 注册送围巾
    streakDays: 0,
    totalUsers: 0,
    growthRate: 0,
    level: 1,
    xp: 0,
    xpToNext: 100,
  }
}

function pickSpecies(productType: string, hash: number): CreatureSpecies {
  const typeMap: Record<string, CreatureSpecies[]> = {
    'saas': ['crab', 'octopus', 'whale'],
    'tool': ['crab', 'starfish'],
    'ecommerce': ['pufferfish', 'clownfish'],
    'community': ['octopus', 'clownfish'],
    'content': ['jellyfish', 'seahorse'],
    'education': ['seahorse', 'turtle'],
    'creative': ['starfish', 'jellyfish'],
    'finance': ['turtle', 'whale'],
    'game': ['clownfish', 'pufferfish'],
    'default': ['shrimp', 'crab'],
  }

  const candidates = typeMap[productType.toLowerCase()] || typeMap['default']
  return candidates[hash % candidates.length]
}

function simpleHash(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash // Convert to 32bit integer
  }
  return Math.abs(hash)
}
