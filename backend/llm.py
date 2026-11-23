"""LLM 封装：主力 DeepSeek/Qwen（OpenAI 兼容），知乎直答作对照基线。

默认 mock 模式：用规则模拟 LLM 的 JSON 输出，使整条链路在无任何 API Key 时
也能跑通、可演示。切到 api 模式即调用真实模型。
"""
import json
import re
from .config import settings


def _extract_json(text: str):
    """从模型返回里鲁棒地抽出第一个 JSON 对象。"""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def _call_openai_compatible(prompt: str, base_url: str, api_key: str, model: str) -> str:
    import requests
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ---------------- Mock 规则引擎 ----------------
_AD_WORDS = ["点击", "链接", "优惠", "下单", "折扣", "私信", "代购", "官方旗舰",
             "无敌", "最强", "秒杀", "闭眼入", "绝绝子", "yyds", "买它"]


def _mock_credibility(prompt: str) -> dict:
    content = re.search(r"「(.*?)」", prompt, re.S)
    text = content.group(1) if content else prompt
    hits = [w for w in _AD_WORDS if w in text]
    votes = int((re.search(r"赞同数=(\d+)", prompt) or [0, 0])[1]) if re.search(r"赞同数=(\d+)", prompt) else 0
    base = 0.82
    base -= 0.12 * len(hits)
    if votes >= 500:
        base += 0.08
    base = max(0.05, min(0.98, base))
    return {
        "credibility": round(base, 2),
        "is_ad_suspect": len(hits) >= 2,
        "reasons": ([f"含营销词：{','.join(hits)}"] if hits else ["未见明显营销信号"]),
    }


def _mock_extract(prompt: str) -> dict:
    return {
        "core_conclusion": "多数回答认为需结合自身需求权衡，无单一标准答案（mock 聚合）",
        "preconditions": ["预算与使用场景不同结论不同"],
        "pros": ["性价比方案被多次提及", "上手成本较低"],
        "cons": ["长期维护/续费成本容易被低估"],
        "pitfalls": ["警惕只报喜不报忧的推荐", "注意发布时间，老帖信息可能过时"],
        "risk_notes": ["部分回答疑似软文，已在卡片标注可信度"],
    }


def _mock_cluster(prompt: str) -> dict:
    ids = [int(x) for x in re.findall(r"\[(\d+)\]", prompt)] or [1, 2, 3]
    return {
        "consensus": [{"point": "核心诉求上大家方向一致（mock）", "support_ids": ids[:2]}],
        "divergence": [
            {"stance": "实用派", "argument": "优先满足刚需、控制成本", "support_ids": ids[:1]},
            {"stance": "进阶派", "argument": "一步到位避免二次更换", "support_ids": ids[1:2] or ids[:1]},
        ],
        "risks": [{"point": "注意辨别软文与过时信息", "support_ids": ids}],
    }


def complete_json(prompt: str, task: str) -> dict:
    """task ∈ {credibility, extract, cluster}。返回已解析的 dict。"""
    if settings.LLM_MODE == "api" and settings.LLM_API_KEY:
        raw = _call_openai_compatible(
            prompt, settings.LLM_BASE_URL, settings.LLM_API_KEY, settings.LLM_MODEL
        )
        parsed = _extract_json(raw)
        if parsed is not None:
            return parsed
        # 解析失败则降级到 mock，保证链路不中断
    return {"credibility": _mock_credibility, "extract": _mock_extract,
            "cluster": _mock_cluster}[task](prompt)


def zhida_baseline(query: str) -> str:
    """知乎直答对照基线（额度 2/天）。mock 模式返回占位对照文本。"""
    if settings.LLM_MODE == "api" and settings.ZHIDA_BASE_URL and settings.LLM_API_KEY:
        try:
            return _call_openai_compatible(
                f"请直接回答：{query}", settings.ZHIDA_BASE_URL,
                settings.LLM_API_KEY, settings.ZHIDA_MODEL,
            )
        except Exception as e:
            return f"[直答调用失败，额度或鉴权问题] {e}"
    return ("【直答基线（mock）】直接给出一个合并后的单一答案，不区分立场、"
            "不标注时效与可信度——这正是知鉴Search 的多层过滤要改进的对照项。")
