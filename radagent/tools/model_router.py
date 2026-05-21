"""模型路由: 统一管理三档 LLM 实例，避免各模块重复初始化"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from radagent.config import MODEL_TIERS

logger = logging.getLogger("radagent.model_router")

# 缓存已创建的 LLM 实例（按档位+温度组合缓存）
_instances: dict[str, BaseChatModel] = {}


@dataclass(frozen=True)
class ModelTier:
    """模型档位配置"""
    tier: str          # "light" / "standard" / "premium"
    model: str
    base_url: str
    api_key: str
    temperature: float


def get_llm(tier: str = "standard", *, temperature: float | None = None) -> BaseChatModel | None:
    """获取指定档位的 LLM 实例。

    Args:
        tier: 模型档位 — "light"(快速提取) / "standard"(通用推理) / "premium"(高质量评估)
        temperature: 可选温度覆盖，不传则使用档位默认值

    Returns:
        ChatOpenAI 实例，API key 未配置时返回 None
    """
    config = MODEL_TIERS.get(tier)
    if not config:
        logger.error("未知档位: %s", tier)
        return None

    api_key = config["api_key"]
    if not api_key:
        logger.warning("API key 未配置，档位 %s 不可用", tier)
        return None

    temp = temperature if temperature is not None else config["temperature"]
    cache_key = f"{tier}:{temp}"

    if cache_key in _instances:
        return _instances[cache_key]

    try:
        from langchain_openai import ChatOpenAI
        instance = ChatOpenAI(
            model=config["model"],
            base_url=config["base_url"],
            api_key=api_key,
            temperature=temp,
        )
        _instances[cache_key] = instance
        logger.debug("创建 LLM 实例: tier=%s, model=%s, temp=%.1f", tier, config["model"], temp)
        return instance
    except Exception as e:
        logger.error("LLM 初始化失败 (tier=%s): %s", tier, e)
        return None


# ─── 快捷函数 ──────────────────────────────────────────────

def get_light_llm() -> BaseChatModel | None:
    """快速提取: 意图解析、参数解析、反馈解析"""
    return get_llm("light")


def get_standard_llm(*, temperature: float | None = None) -> BaseChatModel | None:
    """通用推理: 屏蔽设计、场景生成"""
    return get_llm("standard", temperature=temperature)


def get_premium_llm() -> BaseChatModel | None:
    """高质量评估: 门禁评分、质量审核"""
    return get_llm("premium")
