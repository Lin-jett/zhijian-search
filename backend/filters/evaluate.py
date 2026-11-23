"""过滤器评测核心（A6）。

评测对象：可信度过滤器对"软文/营销内容"的识别效果。
标注口径（C 的 labels.csv 每行一条回答）：
    label = ad  → 人工判定为软文/营销，系统应识别（is_ad_suspect=True）
    label = ok  → 人工判定为正常内容，系统不应误判

指标：
    recall（召回率）        = 正确识别的软文 / 真实软文总数
    false_kill_rate（误杀率）= 被误判为软文的正常内容 / 正常内容总数
    precision（精确率）     = 正确识别的软文 / 系统判为软文的总数
    漏判案例 missed         = 真软文但系统没识别（label=ad, pred=ok）
    误杀案例 false_kills    = 正常内容被判软文（label=ok, pred=ad）

设计为纯函数、不依赖网络：传入"已带 is_ad_suspect 预测的记录"即可评测，
便于复现与单测。命令行入口见仓库根 evaluate.py。
"""
from __future__ import annotations

from typing import Iterable


def evaluate(records: Iterable[dict]) -> dict:
    """records: 每条含 {text?, url?, label, predicted_ad(bool)}。

    label ∈ {"ad","ok"}；predicted_ad 为系统预测是否软文。
    返回指标字典 + 漏判 / 误杀案例列表。
    """
    records = list(records)
    tp = fp = tn = fn = 0
    missed, false_kills = [], []

    for r in records:
        label = str(r.get("label", "")).strip().lower()
        pred = bool(r.get("predicted_ad", False))
        is_ad = label in ("ad", "1", "true", "软文", "营销")

        if is_ad and pred:
            tp += 1
        elif is_ad and not pred:
            fn += 1
            missed.append(r)
        elif not is_ad and pred:
            fp += 1
            false_kills.append(r)
        else:
            tn += 1

    total_ad = tp + fn
    total_ok = tn + fp
    recall = tp / total_ad if total_ad else None
    false_kill_rate = fp / total_ok if total_ok else None
    precision = tp / (tp + fp) if (tp + fp) else None

    return {
        "n_total": len(records),
        "n_ad_labeled": total_ad,
        "n_ok_labeled": total_ok,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "recall": recall,                 # 召回率：真软文抓到的比例
        "false_kill_rate": false_kill_rate,  # 误杀率：正常内容被误判的比例
        "precision": precision,
        "missed": missed,                 # 漏判案例
        "false_kills": false_kills,       # 误杀案例
    }
