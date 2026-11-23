"""痛点2 —— 内容解析与结构化萃取（降级为问题级摘要聚合）。

实测约束：搜索只返回摘要不是全文 -> 不做单篇长文萃取，改为把同一问题下的
多条回答摘要聚合成一张结构化卡片，既规避全文缺失，又让观点更扎实。
"""
from .llm import complete_json
from .prompts import EXTRACT_PROMPT


def build_card(question: str, answers: list) -> dict:
    joined = "\n".join(
        f"[{i+1}] {a.get('content_text','')}" for i, a in enumerate(answers)
    )
    prompt = EXTRACT_PROMPT.format(question=question, answers=joined)
    card = complete_json(prompt, task="extract")
    # 附溯源链接（痛点卡片要求"原文溯源链接"）
    card["sources"] = [
        {
            "id": i + 1,
            "url": a.get("url", ""),
            "credibility": a.get("credibility"),
            "freshness_score": a.get("freshness_score"),
            "is_stale": a.get("is_stale"),
            "is_ad_suspect": a.get("is_ad_suspect"),
        }
        for i, a in enumerate(answers)
    ]
    return card
