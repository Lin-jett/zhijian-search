"""全局配置。

关键口径（源自《产品与知乎工具调用》实测约束）：
- 搜索 API 只返回摘要（ContentText），不是全文 -> 萃取降级为"问题级多回答摘要聚合"
- 额度极低：知乎搜索 10/天、直答 2/天 -> 原型默认走离线缓存（seed 数据集）
- 搜索参数只有 query + count(<=10)，无时间窗/排序 -> 时效过滤只能本地按 CreateTime 做
- LLM 主力用 DeepSeek/Qwen，知乎直答仅作对照基线
"""
import os


class Settings:
    # ---- 数据源模式 ----
    # offline: 只用 data/seed_qa.json（默认，演示零额度消耗、可离线跑通）
    # live:    调用真实知乎 HTTP API（需要配置 ZHIHU_API_BASE / ZHIHU_TOKEN）
    # hybrid:  优先缓存命中，未命中再实时兜底
    DATA_MODE = os.getenv("ZHIJIAN_DATA_MODE", "offline")

    ZHIHU_API_BASE = os.getenv("ZHIHU_API_BASE", "https://openapi.zhihu.com")
    ZHIHU_TOKEN = os.getenv("ZHIHU_TOKEN", "")
    ZHIHU_SEARCH_MAX_COUNT = 10  # API 硬上限

    SEED_PATH = os.getenv(
        "ZHIJIAN_SEED_PATH",
        os.path.join(os.path.dirname(__file__), "..", "data", "seed_qa.json"),
    )

    # ---- LLM 模式 ----
    # mock: 规则/模板模拟 LLM 输出（默认，无需任何 Key 即可跑通全链路）
    # api:  调用 OpenAI 兼容端点（DeepSeek / Qwen）
    LLM_MODE = os.getenv("ZHIJIAN_LLM_MODE", "mock")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

    # 知乎直答（检索增强，2 次/天）—— 仅作对照基线，不做主力
    ZHIDA_BASE_URL = os.getenv("ZHIDA_BASE_URL", "https://openapi.zhihu.com/v1")
    ZHIDA_MODEL = os.getenv("ZHIDA_MODEL", "zhida-fast-1p5")

    # ---- 过滤默认参数（前端可覆盖）----
    FRESHNESS_HALFLIFE_DAYS = 180   # 时效衰减半衰期
    CREDIBILITY_WARN_THRESHOLD = 0.5  # 低于此分标红预警
    DEFAULT_TIME_WINDOW_DAYS = 0    # 0 = 不限


settings = Settings()
