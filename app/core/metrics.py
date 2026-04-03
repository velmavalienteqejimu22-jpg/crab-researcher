"""
CrabRes Metrics — 结构化指标收集

生产级可观测性：
- Agent 调用次数 / 响应时间 / 错误率
- 工具调用成功率 / 超时率
- LLM token 消耗
- 活跃会话数

当前实现：内存计数器 + API 端点暴露。
未来：接入 Prometheus / Datadog。
"""

import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MetricsCollector:
    """全局指标收集器（单例）"""
    
    # 计数器
    agent_calls: int = 0
    agent_errors: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    tool_retries: int = 0
    expert_calls: int = 0
    roundtable_calls: int = 0
    
    # 累计时间（秒）
    total_agent_time: float = 0.0
    total_tool_time: float = 0.0
    
    # Token 消耗
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    
    # 按工具分计
    tool_stats: dict = field(default_factory=lambda: defaultdict(lambda: {"calls": 0, "errors": 0, "total_time": 0.0}))
    
    # 按专家分计
    expert_stats: dict = field(default_factory=lambda: defaultdict(lambda: {"calls": 0, "total_time": 0.0}))
    
    # 启动时间
    started_at: float = field(default_factory=time.time)
    
    def record_agent_call(self, duration: float, error: bool = False):
        self.agent_calls += 1
        self.total_agent_time += duration
        if error:
            self.agent_errors += 1
    
    def record_tool_call(self, tool_name: str, duration: float, error: bool = False, retried: bool = False):
        self.tool_calls += 1
        self.total_tool_time += duration
        self.tool_stats[tool_name]["calls"] += 1
        self.tool_stats[tool_name]["total_time"] += duration
        if error:
            self.tool_errors += 1
            self.tool_stats[tool_name]["errors"] += 1
        if retried:
            self.tool_retries += 1
    
    def record_expert_call(self, expert_id: str, duration: float):
        self.expert_calls += 1
        self.expert_stats[expert_id]["calls"] += 1
        self.expert_stats[expert_id]["total_time"] += duration
    
    def record_roundtable(self):
        self.roundtable_calls += 1
    
    def record_tokens(self, tokens: int, cost_usd: float):
        self.total_tokens += tokens
        self.total_cost_usd += cost_usd
    
    def get_report(self) -> dict:
        uptime = time.time() - self.started_at
        return {
            "uptime_seconds": round(uptime, 1),
            "agent": {
                "total_calls": self.agent_calls,
                "errors": self.agent_errors,
                "error_rate": round(self.agent_errors / max(self.agent_calls, 1), 3),
                "avg_response_time": round(self.total_agent_time / max(self.agent_calls, 1), 2),
            },
            "tools": {
                "total_calls": self.tool_calls,
                "errors": self.tool_errors,
                "retries": self.tool_retries,
                "success_rate": round(1 - self.tool_errors / max(self.tool_calls, 1), 3),
                "avg_time": round(self.total_tool_time / max(self.tool_calls, 1), 2),
                "by_tool": {
                    name: {
                        "calls": stats["calls"],
                        "errors": stats["errors"],
                        "avg_time": round(stats["total_time"] / max(stats["calls"], 1), 2),
                    }
                    for name, stats in self.tool_stats.items()
                },
            },
            "experts": {
                "total_calls": self.expert_calls,
                "roundtables": self.roundtable_calls,
                "by_expert": {
                    eid: {
                        "calls": stats["calls"],
                        "avg_time": round(stats["total_time"] / max(stats["calls"], 1), 2),
                    }
                    for eid, stats in self.expert_stats.items()
                },
            },
            "llm": {
                "total_tokens": self.total_tokens,
                "total_cost_usd": round(self.total_cost_usd, 4),
            },
        }


# 全局单例
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    return _metrics
