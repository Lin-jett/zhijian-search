"""核心编排：把七层架构串成一条可执行链路。

数据流（对应文档"五、数据流示意"）：
用户Query → Query改写 → 召回topN →
【时效打分过滤】→【可信度质检】→【BGE重排】→
LLM结构化萃取(卡片) → LLM观点聚类(共识/分歧矩阵) → 渲染结构
"""
from .zhihu_client import client
from .query_rewrite import rewrite
from .filters import freshness, credibility, rerank
from .extract import build_card
from .cluster import build_matrix
from .llm import zhida_baseline


def _collect_answers(questions):
    """把多问题的回答摊平，并挂上所属问题标题。"""
    out = []
    for q in questions:
        for a in q.get("answers", []):
            a = dict(a)
            a["_question"] = q.get("question", "")
            out.append(a)
    return out


def search(query: str, options: dict | None = None) -> dict:
    options = options or {}
    filter_ad = options.get("filter_ad", True)            # 过滤软文（降权/隐藏）
    time_window = int(options.get("time_window_days", 0))  # 时效筛选
    enable_matrix = options.get("enable_matrix", True)     # 观点矩阵
    enable_card = options.get("enable_card", True)         # 结构化卡片
    include_baseline = options.get("include_baseline", True)

    trace = []  # 链路可解释：每层处理前后数量，答辩演示用

    # 1. Query 改写
    intent, subqueries = rewrite(query)
    trace.append({"stage": "query_rewrite", "intent": intent, "subqueries": subqueries})

    # 2. 召回（多子查询扩大召回，去重）
    seen_q = {}
    for sq in subqueries:
        for q in client.search_questions(sq):
            seen_q[q["question"]] = q
    questions = list(seen_q.values())
    answers = _collect_answers(questions)
    trace.append({"stage": "recall", "questions": len(questions), "answers": len(answers)})

    # 3. 时效打分 + 窗口过滤
    kept = []
    for a in answers:
        a, keep = freshness.annotate(a, time_window_days=time_window)
        if keep:
            kept.append(a)
    answers = kept
    trace.append({"stage": "freshness", "after": len(answers),
                  "stale": sum(1 for a in answers if a.get("is_stale"))})

    # 4. 可信度质检
    for a in answers:
        credibility.assess(a)
    ad_suspect = sum(1 for a in answers if a.get("is_ad_suspect"))
    if filter_ad:
        # 软文不删除，但移出主列表（可通过开关找回）—— 这里降权保留并标记
        answers = sorted(answers, key=lambda a: a.get("is_ad_suspect", False))
    trace.append({"stage": "credibility", "ad_suspect": ad_suspect})

    # 5. 基础相关性重排 + 多因子综合排序
    answers = rerank.rerank_and_filter(query, answers)
    trace.append({"stage": "rerank", "top_score": answers[0]["final_score"] if answers else None})

    # 6+7. 按问题分组做结构化卡片 + 观点矩阵
    groups = {}
    for a in answers:
        groups.setdefault(a.get("_question", query), []).append(a)

    cards, matrices = [], []
    for qtitle, grp in groups.items():
        if enable_card:
            cards.append({"question": qtitle, "card": build_card(qtitle, grp)})
        if enable_matrix:
            matrices.append({"question": qtitle, "matrix": build_matrix(qtitle, grp)})

    result = {
        "query": query,
        "intent": intent,
        "answers": [_public_answer(a) for a in answers],
        "cards": cards,
        "matrices": matrices,
        "trace": trace,
    }
    if include_baseline:
        result["zhida_baseline"] = zhida_baseline(query)
    return result


def _public_answer(a: dict) -> dict:
    return {
        "question": a.get("_question"),
        "content_text": a.get("content_text"),
        "url": a.get("url"),
        "vote_up_count": a.get("vote_up_count"),
        "comment_count": a.get("comment_count"),
        "author_signature": a.get("author_signature"),
        "age_days": a.get("age_days"),
        "freshness_score": a.get("freshness_score"),
        "is_stale": a.get("is_stale"),
        "credibility": a.get("credibility"),
        "is_ad_suspect": a.get("is_ad_suspect"),
        "credibility_warn": a.get("credibility_warn"),
        "credibility_reasons": a.get("credibility_reasons"),
        "relevance": a.get("relevance"),
        "final_score": a.get("final_score"),
    }
