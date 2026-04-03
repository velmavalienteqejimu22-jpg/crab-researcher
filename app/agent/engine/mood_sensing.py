"""
CrabRes Mood Sensing — 增长情绪感知

学习 Claude Code 的 Frustration Detection，但做得更深：
不只检测"用户在骂我"，而是理解增长过程中的 5 种情绪状态，
并自动调整 Agent 的沟通风格和策略建议。

5 种情绪检测维度：
1. 焦虑（Anxiety）：担心没有用户、竞品领先
2. 失去动力（Demotivation）：回复变短、跳过任务、久不登录
3. 方向迷茫（Confusion）：频繁切换策略、不确定
4. 过度乐观（Overoptimism）：不切实际的目标
5. 执行疲劳（Fatigue）：任务完成率下降、表达负担感
"""

import re
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class MoodType(str, Enum):
    NEUTRAL = "neutral"
    ANXIOUS = "anxious"
    DEMOTIVATED = "demotivated"
    CONFUSED = "confused"
    OVEROPTIMISTIC = "overoptimistic"
    FATIGUED = "fatigued"


@dataclass
class MoodSignal:
    """检测到的情绪信号"""
    mood: MoodType
    confidence: float  # 0-1
    trigger: str  # 触发的关键词/模式
    response_strategy: str  # 建议的响应策略


# 情绪关键词/模式库
MOOD_PATTERNS: dict[MoodType, list[dict]] = {
    MoodType.ANXIOUS: [
        {"pattern": r"为什么还没有用户|没有人用|没人买|zero users|no users|no signups", "weight": 0.9},
        {"pattern": r"竞品已经|competitor already|they raised|他们融资了", "weight": 0.8},
        {"pattern": r"是不是方向不对|am i wrong|is this viable|产品有人要吗", "weight": 0.85},
        {"pattern": r"worried|担心|焦虑|anxious|scared|害怕失败", "weight": 0.9},
        {"pattern": r"running out of|快没钱了|budget.*running|money.*tight", "weight": 0.8},
        {"pattern": r"should i give up|要不要放弃|算了吧", "weight": 0.95},
    ],
    MoodType.DEMOTIVATED: [
        {"pattern": r"^(ok|好|行|嗯|fine|whatever|随便)\.?$", "weight": 0.6},
        {"pattern": r"don't feel like|不想做|懒得|没动力|no motivation", "weight": 0.85},
        {"pattern": r"什么都没变|nothing changed|没有效果|doesn't work|不管用", "weight": 0.8},
        {"pattern": r"太慢了|too slow|this is taking forever|要等多久", "weight": 0.7},
        {"pattern": r"有什么用|what's the point|pointless|意义|值得吗", "weight": 0.85},
    ],
    MoodType.CONFUSED: [
        {"pattern": r"要不要换方向|should i pivot|要不要转型|change direction", "weight": 0.8},
        {"pattern": r"不确定|not sure|uncertain|confused|迷茫|没头绪", "weight": 0.85},
        {"pattern": r"到底该|which one|should i.*or|选哪个|先做哪个", "weight": 0.7},
        {"pattern": r"太多选择|too many options|overwhelming|信息太多", "weight": 0.75},
        {"pattern": r"换个策略|try something else|换一个|different approach", "weight": 0.6},
    ],
    MoodType.OVEROPTIMISTIC: [
        {"pattern": r"(10|100)万用户.*(1|2|3)个月|(\d{5,})\s*users?\s*in\s*(1|2|3)\s*month", "weight": 0.9},
        {"pattern": r"viral|病毒|爆款|一夜之间|overnight success", "weight": 0.7},
        {"pattern": r"打败.*google|beat.*facebook|超越.*amazon|取代", "weight": 0.85},
        {"pattern": r"很简单|easy|piece of cake|no problem|轻松", "weight": 0.5},
        {"pattern": r"(百万|million).*revenue.*(first|1|第一).*(month|月)", "weight": 0.9},
    ],
    MoodType.FATIGUED: [
        {"pattern": r"太多了|too much|做不过来|overwhelmed|exhausted", "weight": 0.85},
        {"pattern": r"能不能简化|simplify|less|减少|少做点", "weight": 0.8},
        {"pattern": r"累了|tired|burned out|burnout|疲惫", "weight": 0.9},
        {"pattern": r"没时间|no time|忙不过来|too busy", "weight": 0.75},
        {"pattern": r"能不能自动|automate|帮我做|do it for me|自动化", "weight": 0.5},
    ],
}

# 每种情绪的响应策略
MOOD_RESPONSES: dict[MoodType, dict] = {
    MoodType.ANXIOUS: {
        "strategy": "reassure_with_data",
        "tone_shift": "Switch to calm, data-driven reassurance mode.",
        "prompt_injection": (
            "⚠️ MOOD DETECTED: User is ANXIOUS about their growth. "
            "DO: Show concrete progress data (even tiny wins count). "
            "DO: Normalize their timeline ('Most SaaS products take 6-12 months to find PMF'). "
            "DO: Give ONE specific next action to create momentum. "
            "DON'T: Overwhelm with a 10-step plan. "
            "DON'T: Dismiss their anxiety. Acknowledge it first."
        ),
        "creature_mood": "worried",
    },
    MoodType.DEMOTIVATED: {
        "strategy": "spark_competitive_fire",
        "tone_shift": "Use competitive intelligence to reignite drive.",
        "prompt_injection": (
            "⚠️ MOOD DETECTED: User is DEMOTIVATED. "
            "DO: Show what their competitor just did (creates urgency). "
            "DO: Highlight a quick win they can achieve TODAY. "
            "DO: Celebrate any past progress, no matter how small. "
            "DON'T: Give a long strategy — they need a spark, not a manual. "
            "DON'T: Be preachy. Be a teammate."
        ),
        "creature_mood": "sad",
    },
    MoodType.CONFUSED: {
        "strategy": "clarify_and_simplify",
        "tone_shift": "Be decisive and directive. Reduce options to 2.",
        "prompt_injection": (
            "⚠️ MOOD DETECTED: User is CONFUSED about direction. "
            "DO: Make a CLEAR recommendation (not 'you could do A or B'). "
            "DO: Explain WHY in 1-2 sentences with data. "
            "DO: Offer to trigger a Deep Strategy session if the confusion is fundamental. "
            "DON'T: Add more options. They already have too many. "
            "DON'T: Say 'it depends'. Take a stand."
        ),
        "creature_mood": "thinking",
    },
    MoodType.OVEROPTIMISTIC: {
        "strategy": "gentle_reality_check",
        "tone_shift": "Warm but honest. Use benchmarks to calibrate expectations.",
        "prompt_injection": (
            "⚠️ MOOD DETECTED: User has UNREALISTIC expectations. "
            "DO: Acknowledge their ambition positively. "
            "DO: Share industry benchmarks (avg SaaS growth rate, typical time to 1K users). "
            "DO: Recalculate their goal with realistic numbers. "
            "DO: Suggest an ambitious-but-achievable milestone. "
            "DON'T: Crush their dream. Redirect it. "
            "DON'T: Be condescending."
        ),
        "creature_mood": "thinking",
    },
    MoodType.FATIGUED: {
        "strategy": "simplify_and_automate",
        "tone_shift": "Cut their task list drastically. Focus on the 1 thing that matters.",
        "prompt_injection": (
            "⚠️ MOOD DETECTED: User is FATIGUED from execution. "
            "DO: Cut their current plan to the TOP 1-2 tasks only. "
            "DO: Offer to automate or batch what you can. "
            "DO: Remind them why they started (their original goal). "
            "DON'T: Add new tasks. "
            "DON'T: Say 'you need to do X, Y, Z, and W'."
        ),
        "creature_mood": "working",
    },
}


class MoodSensor:
    """
    情绪感知器
    
    分析用户消息检测情绪状态，输出响应策略。
    可以被注入到 Coordinator prompt 中，自动调整沟通风格。
    """
    
    def __init__(self):
        self._history: list[dict] = []  # 最近的情绪检测历史
        self._last_mood: MoodType = MoodType.NEUTRAL
        self._consecutive_short_messages = 0
    
    def detect(self, message: str, context: Optional[dict] = None) -> Optional[MoodSignal]:
        """
        检测用户消息中的情绪信号
        
        Returns:
            MoodSignal if a mood is detected with confidence > 0.5, else None
        """
        best_signal: Optional[MoodSignal] = None
        best_score = 0.0
        
        # 短消息计数（demotivation 的行为信号）
        if len(message.strip()) < 20:
            self._consecutive_short_messages += 1
        else:
            self._consecutive_short_messages = 0
        
        for mood_type, patterns in MOOD_PATTERNS.items():
            for pattern_info in patterns:
                try:
                    if re.search(pattern_info["pattern"], message, re.IGNORECASE):
                        score = pattern_info["weight"]
                        
                        # 连续短消息加权（demotivation 信号）
                        if mood_type == MoodType.DEMOTIVATED and self._consecutive_short_messages >= 3:
                            score = min(1.0, score + 0.2)
                        
                        # 如果和上一次检测到的情绪相同，加权（持续的情绪更可信）
                        if mood_type == self._last_mood:
                            score = min(1.0, score + 0.1)
                        
                        if score > best_score:
                            best_score = score
                            response = MOOD_RESPONSES[mood_type]
                            best_signal = MoodSignal(
                                mood=mood_type,
                                confidence=score,
                                trigger=pattern_info["pattern"][:50],
                                response_strategy=response["strategy"],
                            )
                except re.error:
                    continue
        
        if best_signal and best_signal.confidence >= 0.5:
            self._last_mood = best_signal.mood
            self._history.append({
                "time": time.time(),
                "mood": best_signal.mood.value,
                "confidence": best_signal.confidence,
                "message_preview": message[:100],
            })
            # 只保留最近 20 条
            self._history = self._history[-20:]
            
            logger.info(
                f"Mood detected: {best_signal.mood.value} "
                f"(confidence={best_signal.confidence:.2f}, "
                f"trigger='{best_signal.trigger}')"
            )
            return best_signal
        
        return None
    
    def get_prompt_injection(self, signal: MoodSignal) -> str:
        """获取要注入到 Coordinator prompt 中的情绪感知指令"""
        response = MOOD_RESPONSES.get(signal.mood)
        if response:
            return response["prompt_injection"]
        return ""
    
    def get_creature_mood(self, signal: MoodSignal) -> str:
        """获取对应的生物体表情状态"""
        response = MOOD_RESPONSES.get(signal.mood)
        if response:
            return response.get("creature_mood", "idle")
        return "idle"
    
    def get_mood_history(self) -> list[dict]:
        """获取最近的情绪检测历史"""
        return self._history.copy()
    
    def get_dominant_mood(self, window_minutes: int = 30) -> Optional[MoodType]:
        """获取最近 N 分钟内的主导情绪"""
        cutoff = time.time() - window_minutes * 60
        recent = [h for h in self._history if h["time"] > cutoff]
        if not recent:
            return None
        
        mood_counts: dict[str, int] = {}
        for h in recent:
            mood_counts[h["mood"]] = mood_counts.get(h["mood"], 0) + 1
        
        dominant = max(mood_counts, key=mood_counts.get)
        return MoodType(dominant)
