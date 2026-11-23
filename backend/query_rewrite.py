"""Query 理解与预处理：改写、子问题拆解、意图识别。

目的（对应原文档召回层）：扩展检索词、提升召回多样性，避免只召回单一立场。
由于搜索 API 无排序/时间参数，这里靠多子查询来凑召回量。
"""
import re

_COMPARE_HINT = ["还是", "对比", "哪个好", "vs", "区别", "选", "推荐"]
_EXP_HINT = ["怎么", "如何", "经验", "值得", "体验", "踩坑"]
_CONTROVERSY_HINT = ["争议", "真的", "是不是", "到底", "坑"]


def detect_intent(query: str) -> str:
    if any(h in query for h in _COMPARE_HINT):
        return "compare"      # 对比选购
    if any(h in query for h in _CONTROVERSY_HINT):
        return "controversy"  # 争议话题
    if any(h in query for h in _EXP_HINT):
        return "experience"   # 经验查询
    return "general"


def rewrite(query: str):
    """返回 (intent, [子查询...])。子查询用于扩大召回、覆盖正反立场。"""
    intent = detect_intent(query)
    base = query.strip()
    subs = [base]
    # 规则式扩展（原型用规则；接入 LLM 后替换为模型改写）
    if intent == "compare":
        subs += [f"{base} 优点", f"{base} 缺点", f"{base} 踩坑"]
    elif intent == "controversy":
        subs += [f"{base} 支持", f"{base} 反对", f"{base} 真实体验"]
    elif intent == "experience":
        subs += [f"{base} 注意事项", f"{base} 后悔"]
    else:
        subs += [f"{base} 评价", f"{base} 对比"]
    # 去重保序
    seen, out = set(), []
    for s in subs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return intent, out
