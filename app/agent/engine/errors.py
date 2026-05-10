"""
CrabRes Agent Engine — 自定义异常体系

替代 67 处裸 except Exception，建立分类错误处理。
业务代码只捕获预期的特定异常；未预期异常由全局处理器处理。
"""


class CrabResError(Exception):
    """所有 CrabRes Agent 异常的基类"""
    user_message: str
    recoverable: bool

    def __init__(self, message: str = "", *, user_message: str = "", recoverable: bool = True):
        self.user_message = user_message
        self.recoverable = recoverable
        super().__init__(message)


# ===== 工具相关异常 =====

class ToolError(CrabResError):
    """工具执行失败"""
    tool_name: str

    def __init__(self, tool_name: str, reason: str, *, recoverable: bool = True):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' failed: {reason}", recoverable=recoverable)


class ToolTimeoutError(ToolError):
    """工具超时"""
    def __init__(self, tool_name: str, timeout_sec: float):
        super().__init__(tool_name, f"timed out after {timeout_sec}s", recoverable=True)


class ToolNotFoundError(ToolError):
    """工具不存在"""
    def __init__(self, tool_name: str):
        super().__init__(tool_name, "not found in registry", recoverable=False)


# ===== LLM 相关异常 =====

class LLMError(CrabResError):
    """LLM 调用失败"""
    tier: str

    def __init__(self, reason: str, tier: str = "unknown", *, recoverable: bool = True):
        self.tier = tier
        super().__init__(f"LLM call ({tier}) failed: {reason}", recoverable=recoverable)


class LLMParseError(LLMError):
    """LLM 输出解析失败（JSON 解析、动作类型识别等）"""
    raw_output: str

    def __init__(self, reason: str, raw_output: str = ""):
        self.raw_output = raw_output[:500]
        super().__init__(f"parse error: {reason}", recoverable=True)


class LLMQuotaExceededError(LLMError):
    """LLM 配额耗尽"""
    def __init__(self, tier: str = "unknown"):
        super().__init__("quota exceeded", tier=tier, recoverable=False)


# ===== 专家系统异常 =====

class ExpertError(CrabResError):
    """专家调用失败"""
    expert_id: str

    def __init__(self, expert_id: str, reason: str, *, recoverable: bool = True):
        self.expert_id = expert_id
        super().__init__(f"Expert '{expert_id}' failed: {reason}", recoverable=recoverable)


class ExpertTimeoutError(ExpertError):
    """专家分析超时"""
    def __init__(self, expert_id: str, timeout_sec: float):
        super().__init__(expert_id, f"timed out after {timeout_sec}s")


# ===== 阶段/流程异常 =====

class StageError(CrabResError):
    """阶段执行失败"""
    stage: str
    critical: bool

    def __init__(self, stage: str, reason: str, *, critical: bool = False):
        self.stage = stage
        self.critical = critical
        super().__init__(f"Stage '{stage}' failed: {reason}", recoverable=not critical)


class RouterError(CrabResError):
    """路由决策失败"""
    def __init__(self, reason: str):
        super().__init__(f"Router error: {reason}", recoverable=True)


# ===== 配置异常 =====

class ConfigError(CrabResError):
    """配置错误（不可恢复）"""
    key: str

    def __init__(self, key: str, reason: str):
        self.key = key
        super().__init__(f"Config '{key}': {reason}", recoverable=False)
