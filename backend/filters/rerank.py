"""基础相关性重排。

原型用轻量词重合度打分模拟 BGE-Reranker；接入真实模型时替换 _relevance 即可
（BGE-Reranker 平台不提供，需自建，见文档"向量库/Embedding/Rerank ❌ 平台不提供"）。
"""


def _relevance(query: str, text: str) -> float:
    q = set(query)
    t = set(text)
    if not q:
        return 0.0
    return round(len(q & t) / len(q), 3)


def rerank_and_filter(query: str, answers: list, min_relevance: float = 0.0):
    """综合排序分 = 相关性 * 可信度 * 时效。返回排好序的列表。"""
    out = []
    for a in answers:
        rel = _relevance(query, a.get("content_text", ""))
        a["relevance"] = rel
        # 多因子综合分（核心差异点：不是单纯相关性）
        a["final_score"] = round(
            rel * 0.4
            + a.get("credibility", 0.6) * 0.35
            + a.get("freshness_score", 0.5) * 0.25,
            3,
        )
        if rel >= min_relevance:
            out.append(a)
    out.sort(key=lambda x: x["final_score"], reverse=True)
    return out
