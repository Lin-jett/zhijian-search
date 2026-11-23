"""知鉴Search FastAPI 入口。

运行：
  cd zhijian-search
  uvicorn backend.main:app --reload --port 8000
接口：
  GET  /                      健康检查
  POST /api/search            主检索（body: {query, options})
  GET  /api/seed_topics       可选的 seed 主题列表（演示引导）
前端 frontend/index.html 直接 fetch 本服务。
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from .pipeline import search
from .zhihu_client import client
from .config import settings

logger = logging.getLogger("zhijian")

app = FastAPI(title="知鉴Search · 知乎增强检索引擎", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 单条 query 最大长度：超长直接截断，避免把后端拖垮（A5 边界）
MAX_QUERY_LEN = 200


class SearchRequest(BaseModel):
    # 不在此处用 max_length 硬卡：超长交给 do_search 截断处理，避免返回 422。
    # 只做一个极宽松的上限兜底（防御超大 body 拖垮解析）。
    query: str = Field(default="", max_length=20000)
    options: Optional[Dict[str, Any]] = None


@app.get("/")
def health():
    return {
        "service": "zhijian-search",
        "status": "ok",
        "data_mode": settings.DATA_MODE,
        "llm_mode": settings.LLM_MODE,
    }


@app.get("/api/seed_topics")
def seed_topics():
    try:
        seed = client._load_seed()
        return {"topics": [{"question": s["question"], "keywords": s.get("keywords", [])} for s in seed]}
    except Exception as e:
        logger.warning("seed_topics failed: %s", type(e).__name__)
        return {"topics": [], "error": "seed_unavailable"}


def _empty_result(query: str, mode: str, note: str) -> dict:
    """统一的空/降级返回骨架，前端拿到的字段永远完整，不会因缺字段崩。"""
    return {
        "query": query,
        "intent": "general",
        "answers": [],
        "cards": [],
        "matrices": [],
        "trace": [{"stage": "guard", "note": note}],
        "zhida_baseline": "",
        "mode": mode,
    }


@app.post("/api/search")
def do_search(req: SearchRequest):
    # --- A5 边界：query 清洗 ---
    raw = req.query if isinstance(req.query, str) else str(req.query or "")
    query = raw.strip()
    if not query:
        # 空 query 不报 500，返回正常空结果 + 友好提示
        return _empty_result("", "empty_query", "空 query，未执行检索")
    if len(query) > MAX_QUERY_LEN:
        query = query[:MAX_QUERY_LEN]

    # --- 主流程 + 兜底：任何内部异常都降级为 mode=degraded，绝不抛 500 ---
    try:
        result = search(query, req.options or {})
        result.setdefault("mode", "ok")
        return result
    except Exception as e:
        # 安全：只记异常类型，不用 logger.exception —— 完整 traceback / 异常消息
        # 可能夹带请求 URL、token 等 secret（A5 第4条：日志不出现 secret）。
        logger.error("search degraded: %s", type(e).__name__)
        degraded = _empty_result(query, "degraded", f"检索失败已降级：{type(e).__name__}")
        return JSONResponse(status_code=200, content=degraded)
