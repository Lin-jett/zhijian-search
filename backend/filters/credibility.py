"""痛点3 —— 可信度质检：客观信号 + LLM 预警 双因子。

实测文档结论：知乎返回 VoteUpCount/CommentCount/AuthorityLevel 等客观信号，
比原方案更强，可做"LLM + 客观信号"双因子打分。
低可信度不删除，只降权 + 标红警示，保留给用户判断。
"""
from ..config import settings
from ..llm import complete_json
from ..prompts import CREDIBILITY_PROMPT


def _objective_signal(answer: dict) -> float:
    """基于客观互动/权威信号给 0~1 分。"""
    votes = answer.get("vote_up_count", 0)
    comments = answer.get("comment_count", 0)
    authority = answer.get("authority_level", 0)
    s = 0.3
    if votes >= 1000:
        s += 0.3
    elif votes >= 200:
        s += 0.2
    elif votes >= 50:
        s += 0.1
    if comments >= 100:
        s += 0.1
    s += min(0.3, authority * 0.1)
    return min(1.0, s)


def assess(answer: dict) -> dict:
    """返回带可信度标注的 answer。"""
    prompt = CREDIBILITY_PROMPT.format(
        content=answer.get("content_text", ""),
        votes=answer.get("vote_up_count", 0),
        comments=answer.get("comment_count", 0),
        authority=answer.get("authority_level", 0),
    )
    llm = complete_json(prompt, task="credibility")
    llm_score = float(llm.get("credibility", 0.6))
    obj_score = _objective_signal(answer)
    # 双因子加权：LLM 语义 0.6 + 客观信号 0.4
    final = round(0.6 * llm_score + 0.4 * obj_score, 3)
    answer["credibility"] = final
    answer["is_ad_suspect"] = bool(llm.get("is_ad_suspect", False))
    answer["credibility_reasons"] = llm.get("reasons", [])
    answer["credibility_warn"] = final < settings.CREDIBILITY_WARN_THRESHOLD or answer["is_ad_suspect"]
    return answer
