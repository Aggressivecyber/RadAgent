"""Web 搜索工具: 使用 DuckDuckGo 搜索辐照仿真相关参数推荐

通过 mihomo 代理访问 DuckDuckGo。
"""

import logging
import os

from ddgs import DDGS

logger = logging.getLogger("radagent.node.tools")

PROXY = os.environ.get("MIHOMO_PROXY", "http://127.0.0.1:7892")


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """DuckDuckGo 文本搜索，返回结果列表"""
    logger.info("DuckDuckGo 搜索: query=%s, max=%d", query[:100], max_results)
    results = []
    try:
        with DDGS(proxy=PROXY) as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "href": r.get("href", ""),
                })
        logger.info("搜索返回 %d 条结果", len(results))
    except Exception as e:
        logger.error("搜索失败: %s", e)
    return results


def search_parameter_recommendation(particle: str | None, material: str | None, scenario: str = "") -> str:
    """搜索辐照仿真参数推荐，返回拼接的搜索摘要"""
    queries = []

    if particle and not material:
        queries.append(f"{particle} irradiation simulation typical material energy thickness Geant4")
    elif material and not particle:
        queries.append(f"{material} radiation testing typical particle energy Geant4 simulation")
    elif not particle and not material:
        queries.append(f"{scenario} irradiation simulation recommended parameters Geant4" if scenario
                       else "radiation effects simulation typical parameters Geant4 recommended")

    snippets = []
    for q in queries:
        results = search_web(q, max_results=3)
        for r in results:
            snippets.append(f"- {r['title']}: {r['body']}")

    return "\n".join(snippets) if snippets else "未找到相关推荐信息。"
