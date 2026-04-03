"""
CrabRes Prompt Cache — 上下文复用缓存

学习 Claude Code 的 Prompt Cache 机制：
对重复或相似的提示词请求进行缓存，降低 token 消耗，提升响应速度。

核心思路：
1. 产品信息 hash → 如果产品信息没变，不重复注入完整的产品描述
2. 知识库 hash → 同一个专家的知识不会在同一 session 中重复发送
3. 系统 prompt 前缀缓存 → Coordinator prompt 的静态部分（人格、规则）提取为不变前缀

实现方式：
- 不是网络层缓存，是 context construction 层的智能去重
- 用 hash 比对决定是否注入完整内容还是摘要引用
"""

import hashlib
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class PromptCache:
    """
    Prompt 级别的上下文缓存
    
    在一个 session 生命周期内：
    - 追踪哪些"大块内容"已经被发送过
    - 第二次遇到相同内容时，用一行引用替代完整注入
    - 节省 30-60% 的 token 消耗
    """
    
    def __init__(self):
        # 已发送内容的 hash → (摘要, 发送时间, token 估算)
        self._sent: dict[str, dict] = {}
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "tokens_saved": 0,
        }
    
    def check_and_cache(self, key: str, content: str, summary: str = "") -> tuple[str, bool]:
        """
        检查内容是否已缓存，返回（最终内容, 是否为缓存命中）
        
        Args:
            key: 缓存键（如 "product_info", "expert_knowledge_social_media"）
            content: 完整内容
            summary: 缓存命中时的替代摘要（不提供则自动生成）
        
        Returns:
            (output_content, is_cached)
            - 首次: (完整内容, False)
            - 缓存命中且内容未变: (摘要引用, True)
            - 缓存命中但内容变了: (完整内容, False)
        """
        content_hash = self._hash(content)
        
        if key in self._sent:
            old = self._sent[key]
            if old["hash"] == content_hash:
                # 命中：内容完全一样
                self._stats["cache_hits"] += 1
                est_tokens = len(content) // 4
                self._stats["tokens_saved"] += est_tokens
                
                ref = summary or f"[Cached: {key} — unchanged since last injection, {len(content)} chars]"
                logger.debug(f"Prompt cache HIT: {key} (saved ~{est_tokens} tokens)")
                return ref, True
            else:
                # 内容变了，更新缓存
                logger.debug(f"Prompt cache UPDATE: {key} (content changed)")
        
        # Miss：首次或内容变更
        self._sent[key] = {
            "hash": content_hash,
            "summary": summary or content[:200],
            "sent_at": time.time(),
            "char_count": len(content),
        }
        self._stats["cache_misses"] += 1
        return content, False
    
    def invalidate(self, key: str):
        """手动清除某个缓存项（比如用户更新了产品信息）"""
        self._sent.pop(key, None)
    
    def clear(self):
        """清空所有缓存"""
        self._sent.clear()
    
    def get_stats(self) -> dict:
        return {
            **self._stats,
            "cached_keys": list(self._sent.keys()),
            "total_cached_chars": sum(v["char_count"] for v in self._sent.values()),
        }
    
    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()[:12]
