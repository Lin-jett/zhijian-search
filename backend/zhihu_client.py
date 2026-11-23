"""知乎数据客户端。

三种模式（见 config.DATA_MODE）：
- offline：只读 data/seed_qa.json（默认，零额度、可离线演示）
- live：   走真实 HTTP API（search zhihu / question answers）
- hybrid： 缓存命中优先，未命中实时兜底（节约 10 次/天的额度）

统一对外暴露 search_questions(query) -> List[Question]，
每个 Question 含 answers 列表，字段对齐 API 实测结构：
  content_text(摘要), create_time, edit_time, vote_up_count,
  comment_count, authority_level, author_signature, url
"""
import json
import os
from .config import settings


class ZhihuClient:
    def __init__(self):
        self._seed = None

    def _load_seed(self):
        if self._seed is None:
            path = os.path.abspath(settings.SEED_PATH)
            with open(path, "r", encoding="utf-8") as f:
                self._seed = json.load(f)
        return self._seed

    # ---------- 离线缓存检索 ----------
    def _search_offline(self, query: str):
        seed = self._load_seed()
        q = query.lower()
        scored = []
        for item in seed:
            kws = [k.lower() for k in item.get("keywords", [])]
            title = item["question"].lower()
            # 关键词命中是主判据：query 包含某关键词，或关键词包含在 query 中
            kw_hits = sum(1 for k in kws if k in q or q in k)
            # 标题字词重合作为次判据
            title_overlap = sum(1 for ch in set(q) if ch in title)
            score = kw_hits * 100 + title_overlap
            scored.append((score, kw_hits, item))
        # 有关键词命中的优先；只返回真正命中关键词的问题，避免跨主题串台
        strong = [it for s, kw, it in sorted(scored, key=lambda x: x[0], reverse=True) if kw > 0]
        if strong:
            return strong
        # 完全没命中时，退回标题最相近的一条，保证不空
        scored.sort(key=lambda x: x[0], reverse=True)
        return [scored[0][2]] if scored else []

    # ---------- 实时 API（live/hybrid 兜底）----------
    def _search_live(self, query: str):
        import requests
        count = min(settings.ZHIHU_SEARCH_MAX_COUNT, 10)
        headers = {"Authorization": f"Bearer {settings.ZHIHU_TOKEN}"}
        r = requests.get(
            f"{settings.ZHIHU_API_BASE}/search",
            params={"query": query, "count": count},
            headers=headers, timeout=30,
        )
        r.raise_for_status()
        return self._normalize_live(r.json())

    @staticmethod
    def _normalize_live(raw: dict):
        """把真实 API 返回规整成与 seed 相同的结构（字段名按实测文档对齐）。"""
        questions = {}
        for hit in raw.get("data", []):
            qid = hit.get("question_id") or hit.get("object_id") or hit.get("title")
            questions.setdefault(qid, {"question": hit.get("title", ""), "keywords": [], "answers": []})
            questions[qid]["answers"].append({
                "content_text": hit.get("content_text") or hit.get("summary", ""),
                "create_time": hit.get("create_time", 0),
                "edit_time": hit.get("edit_time", 0),
                "vote_up_count": hit.get("vote_up_count", 0),
                "comment_count": hit.get("comment_count", 0),
                "authority_level": hit.get("authority_level", 0),
                "author_signature": hit.get("author_signature", ""),
                "url": hit.get("url", ""),
            })
        return list(questions.values())

    def search_questions(self, query: str):
        mode = settings.DATA_MODE
        if mode == "offline":
            return self._search_offline(query)
        if mode == "live":
            return self._search_live(query)
        # hybrid
        hits = self._search_offline(query)
        if hits:
            return hits
        try:
            return self._search_live(query)
        except Exception:
            return []


client = ZhihuClient()
