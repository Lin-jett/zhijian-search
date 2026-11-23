"""痛点5 —— 时效性校验：基于 CreateTime 做时间衰减打分 + 过时标记。

API 无时间窗参数，只能先召回再本地按 create_time 过滤/衰减。
"""
import math
import time
from ..config import settings


def _age_days(create_time: int) -> float:
    if not create_time:
        return 9999.0
    return max(0.0, (time.time() - create_time) / 86400.0)


def freshness_score(create_time: int, halflife_days: int = None) -> float:
    """指数衰减：age=0 -> 1.0；age=halflife -> 0.5。"""
    hl = halflife_days or settings.FRESHNESS_HALFLIFE_DAYS
    age = _age_days(create_time)
    return round(math.pow(0.5, age / hl), 3)


def annotate(answer: dict, time_window_days: int = 0, halflife_days: int = None):
    """给单条回答加上时效字段；返回 (answer, keep)。
    keep=False 表示超出用户设定的时间窗，应被过滤。
    """
    age = _age_days(answer.get("create_time", 0))
    score = freshness_score(answer.get("create_time", 0), halflife_days)
    answer["freshness_score"] = score
    answer["age_days"] = round(age, 1)
    answer["is_stale"] = score < 0.3  # 过时标记（标签，不删除）
    keep = True
    if time_window_days and time_window_days > 0:
        keep = age <= time_window_days
    return answer, keep
