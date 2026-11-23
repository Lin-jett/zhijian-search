"""痛点1 —— 观点聚类 & 对照矩阵生成（A4 归并质量优化版）。

把过滤后的多条回答摘要聚成：共识 / 分歧 / 风险 三个集合，
不强行合并成单一答案。输出结构直接供前端"矩阵视图"渲染。

=== A4 五条优化点落地（对应任务清单）===
1. consensus 不再是兜底桶：要求"多条内容说法一致"（≥2 条支持、信号重合）才算共识，
   靠轻量相似度聚类，而不是"没命中关键词就塞进去"。
2. divergence 不再靠"但是/不过"浅判断：先对每条做立场分类（正面/负面/条件性/中立），
   再把对立立场配成对照。
3. risks 要求"有具体场景"：只有命中场景词（面积/户型/宠物/体脂/专业/预算…）或
   明确踩坑信号的内容，才进风险桶，避免泛泛而谈。
4. core_conclusion 保持降级链：LLM 可用优先用 LLM，失败/不可用退回本模块规则聚类，
   二者输出结构一致。
5. 同一问题多条回答：先按观点信号聚合去重，再在聚合后的簇上找分歧，
   避免 3 条同题回答各自成桶。

设计原则：规则引擎零外部依赖、确定性、可单测；LLM 仅作增强而非唯一来源，
所以 mock / 无 Key 环境下分桶质量也真实可用（而非写死占位）。
"""
import re

from .config import settings
from .llm import complete_json
from .prompts import CLUSTER_PROMPT


# ---------------------------------------------------------------------------
# 立场词典（优化点 2）：正面 / 负面 / 条件性 三类信号
# ---------------------------------------------------------------------------
_POSITIVE_WORDS = [
    "值得", "推荐", "建议", "划算", "够用", "优先", "上岸", "性价比",
    "可以直接", "一步到位", "没必要追", "足够", "更吃香",
]
_NEGATIVE_WORDS = [
    "后悔", "别", "不值得", "止损", "痛苦", "落差", "卡", "不够", "忽悠",
    "坑", "太多", "省", "多花", "别无脑", "别盲目", "别只看",
]
# 条件性立场：结论依赖前提，这类内容本身就是"分歧的根源"
_CONDITIONAL_WORDS = [
    "取决于", "看", "如果", "要看", "分情况", "因人而异", "不同",
    "没有绝对", "没有标准答案", "视", "根据",
]

# ---------------------------------------------------------------------------
# 具体场景词典（优化点 3）：命中才算"有场景的坑"，否则不进风险桶
# ---------------------------------------------------------------------------
_SCENARIO_WORDS = [
    # 通用生活场景
    "面积", "户型", "宠物", "长发", "预算",
    # 数码场景
    "独显", "内存", "续航", "散热", "设计专业", "文科", "计算机", "跑分", "8g", "16g",
    # 考研场景
    "二战", "应届生", "推免", "招生简章", "专业", "院校", "科研院所", "大厂",
    # 健身场景
    "体脂", "增肌", "减脂", "热量", "瘦子", "新手福利",
]

# 过时/软文类风险信号（场景无关，但属于"知鉴"要主动提示的风险）
_META_RISK_SIGNALS = [
    ("过时", ["三年前", "两年前", "早年", "当年", "时代变了", "现在推免", "核对最新", "信息可能过时"]),
    ("软文", ["点击", "下单", "私信", "优惠", "领券", "秒杀", "买它", "旗舰店"]),
]

# 停用词：聚类做信号重合时忽略
_STOPWORDS = set("的了是我你他她它们这那和与及或要会在有就都也很还把被给为对从向以于之而且但不没也".strip())


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _signals(text: str) -> set:
    """抽取一条内容的"内容信号"：2 字以上的中文片段 token，去停用词。
    用于判断两条内容是否"说法一致"（优化点 1 的相似度基础）。"""
    toks = re.findall(r"[\u4e00-\u9fa5]{2,}", text or "")
    out = set()
    for t in toks:
        for i in range(len(t) - 1):
            bg = t[i:i + 2]
            if bg[0] not in _STOPWORDS and bg[1] not in _STOPWORDS:
                out.add(bg)
    return out


def _overlap(a: set, b: set) -> float:
    """Jaccard 相似度，衡量两条内容说法是否一致。"""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _classify_stance(text: str) -> str:
    """立场分类（优化点 2）：positive / negative / conditional / neutral。

    优先级：条件性结构 > 正负对比。
    依据——"如果…但…""取决于""看情况"这类句式本质是"结论依赖前提"，
    属于独立的"条件派"立场；若按零散正/负面词判，会被误拉成支持或反对。
    只有在几乎没有条件信号、且正负倾向明确时，才判 positive / negative。
    """
    t = text or ""
    cond = sum(1 for w in _CONDITIONAL_WORDS if w in t)
    pos = sum(1 for w in _POSITIVE_WORDS if w in t)
    neg = sum(1 for w in _NEGATIVE_WORDS if w in t)
    # 结构性条件信号：同时出现"如果/但"这类转折，强判条件派
    has_if_but = ("如果" in t and ("但" in t or "否则" in t)) or "取决于" in t
    if has_if_but or cond >= 2:
        return "conditional"
    if cond >= 1 and abs(pos - neg) <= 1:
        return "conditional"
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _scenario_hits(text: str) -> list:
    """命中的具体场景词（优化点 3）。"""
    t = (text or "").lower()
    return [w for w in _SCENARIO_WORDS if w.lower() in t]


def _short(text: str, n: int = 48) -> str:
    text = re.sub(r"\s+", "", text or "")
    return text[:n] + ("…" if len(text) > n else "")


# ---------------------------------------------------------------------------
# 规则聚类引擎（降级链的"兜底"，但质量真实可用）
# ---------------------------------------------------------------------------
def rule_based_matrix(question: str, answers: list) -> dict:
    """基于内容的三桶聚类。不依赖 LLM，确定性、可单测。

    answers 里每条至少含 content_text；可选 vote_up_count / credibility /
    is_ad_suspect / is_stale / url。support_ids 从 1 开始（与前端卡片编号一致）。
    """
    items = []
    for i, a in enumerate(answers):
        text = a.get("content_text", "")
        items.append({
            "id": i + 1,
            "text": text,
            "sig": _signals(text),
            "stance": _classify_stance(text),
            "scenarios": _scenario_hits(text),
            "vote": a.get("vote_up_count", 0),
            "cred": a.get("credibility", 0.6),
            "is_ad": a.get("is_ad_suspect", False),
            "is_stale": a.get("is_stale", False),
        })

    # 软文不参与观点聚类（它不是真实观点），但保留给风险桶提示
    opinion_items = [it for it in items if not it["is_ad"]]

    consensus = _build_consensus(opinion_items)
    divergence = _build_divergence(opinion_items)
    risks = _build_risks(items)  # 风险桶要包含软文/过时项

    return {
        "consensus": consensus,
        "divergence": divergence,
        "risks": risks,
        "_engine": "rule",  # 标记来源，便于前端/评测区分
    }


def _build_consensus(items: list) -> list:
    """优化点 1 & 5：只有"多条内容说法一致"才算共识。
    用信号重合做单链聚类，簇内 ≥2 条且相似度达标才输出，否则 consensus 可为空。"""
    if len(items) < 2:
        return []
    SIM = 0.14  # 信号 Jaccard 阈值：中文摘要上该值能区分"同说法/异说法"
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            # 说法一致：信号足够重合 **且** 立场不对立
            si, sj = items[i]["stance"], items[j]["stance"]
            opposite = {si, sj} == {"positive", "negative"}
            if not opposite and _overlap(items[i]["sig"], items[j]["sig"]) >= SIM:
                parent[find(i)] = find(j)

    clusters = {}
    for idx in range(n):
        clusters.setdefault(find(idx), []).append(idx)

    out = []
    for members in clusters.values():
        if len(members) < 2:  # 单条不成共识（优化点 1 核心）
            continue
        members.sort(key=lambda m: items[m]["vote"], reverse=True)
        lead = items[members[0]]
        out.append({
            "point": _short(lead["text"], 56),
            "support_ids": sorted(items[m]["id"] for m in members),
        })
    out.sort(key=lambda c: len(c["support_ids"]), reverse=True)
    return out


def _build_divergence(items: list) -> list:
    """优化点 2 & 5：按立场分组，把对立/不同立场配成对照。
    只有同时存在 ≥2 种立场时才有"分歧"，单一立场场景 divergence 可为空。"""
    groups = {"positive": [], "negative": [], "conditional": [], "neutral": []}
    for it in items:
        groups[it["stance"]].append(it)

    label = {
        "positive": "支持 / 肯定派",
        "negative": "反对 / 保留派",
        "conditional": "条件派（视情况而定）",
        "neutral": "中立 / 经验分享",
    }
    # 有实质分歧的立场：positive / negative / conditional
    active = [k for k in ("positive", "negative", "conditional") if groups[k]]
    if len(active) < 2:
        return []  # 不硬凑分歧（A4 注意事项：某场景只有两桶是正常的）

    out = []
    for k in active:
        g = sorted(groups[k], key=lambda x: x["vote"], reverse=True)
        lead = g[0]
        out.append({
            "stance": label[k],
            "argument": _short(lead["text"], 56),
            "support_ids": sorted(x["id"] for x in g),
        })
    return out


def _build_risks(items: list) -> list:
    """优化点 3：只有"有具体场景"或命中 meta 风险（软文/过时）才进风险桶。"""
    out = []
    seen = set()

    # 1) 有具体场景的"坑"类内容
    for it in items:
        if it["is_ad"]:
            continue
        neg_like = it["stance"] == "negative" or any(
            w in it["text"] for w in ("坑", "后悔", "别", "注意", "忽悠", "省")
        )
        if it["scenarios"] and neg_like:
            key = ("scene", it["id"])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "point": _short(it["text"], 56),
                "scenario": it["scenarios"][:4],
                "support_ids": [it["id"]],
            })

    # 2) meta 风险：软文 / 过时内容（知鉴主动提示的风险）
    ad_ids = [it["id"] for it in items if it["is_ad"]]
    if ad_ids:
        out.append({
            "point": "疑似营销软文，已标红降权，请谨慎参考",
            "scenario": ["软文"],
            "support_ids": sorted(ad_ids),
        })
    stale_ids = [it["id"] for it in items if it.get("is_stale") and not it["is_ad"]]
    if stale_ids:
        out.append({
            "point": "部分内容发布较早，结论可能已过时，注意核对最新信息",
            "scenario": ["过时"],
            "support_ids": sorted(stale_ids),
        })
    return out


# ---------------------------------------------------------------------------
# 对外入口：LLM 优先 + 规则兜底（优化点 4 的降级链）
# ---------------------------------------------------------------------------
def _is_valid_llm_matrix(m) -> bool:
    """校验 LLM 返回是否结构完整且不是空壳。"""
    if not isinstance(m, dict):
        return False
    for k in ("consensus", "divergence", "risks"):
        if not isinstance(m.get(k, []), list):
            return False
    # 三桶全空视为无效，退回规则引擎
    return any(m.get(k) for k in ("consensus", "divergence", "risks"))


def build_matrix(question: str, answers: list) -> dict:
    """生成观点矩阵。

    降级链（优化点 4）：
      api 模式且 Key 可用 → 调 LLM；LLM 返回无效 → 退回规则聚类。
      mock / 无 Key → 直接规则聚类（质量真实，不再是写死占位）。
    """
    if not answers:
        return {"consensus": [], "divergence": [], "risks": [], "_engine": "empty"}

    if settings.LLM_MODE == "api" and settings.LLM_API_KEY:
        joined = "\n".join(
            f"[{i+1}] (赞{a.get('vote_up_count',0)} 可信度{a.get('credibility','-')}) "
            f"{a.get('content_text','')}"
            for i, a in enumerate(answers)
        )
        prompt = CLUSTER_PROMPT.format(question=question, answers=joined)
        try:
            matrix = complete_json(prompt, task="cluster")
            if _is_valid_llm_matrix(matrix):
                matrix.setdefault("_engine", "llm")
                return matrix
        except Exception:
            pass  # 落到规则兜底

    return rule_based_matrix(question, answers)
