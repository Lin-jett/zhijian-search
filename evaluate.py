#!/usr/bin/env python3
"""知鉴Search 评测命令行入口（任务 A6）。

用法：
    # 过滤器评测：软文召回率 / 误杀率 / 漏判案例 / 误杀案例
    python evaluate.py --labels data/labels.csv

    # 附带 A4 分桶抽查（共识/分歧/风险归类人工核对表）
    python evaluate.py --labels data/labels.csv --buckets

labels.csv 列（UTF-8，可带 BOM）：
    url, question, label, content_text
    label ∈ {ad, ok}   ad=人工判定软文，ok=正常内容

结果真跑真算、可复现：同一份 labels.csv 多次运行结果一致。
数字可直接写进计划书，不手填。
"""
import argparse
import csv
import json
import os
import sys

# 允许从仓库根直接 `python evaluate.py`
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.filters.credibility import assess
from backend.filters.evaluate import evaluate
from backend.cluster import rule_based_matrix


def _read_labels(path: str):
    if not os.path.exists(path):
        print(f"[错误] 找不到标注文件：{path}", file=sys.stderr)
        sys.exit(2)
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"label", "content_text"}
        if not required.issubset({(c or "").strip() for c in (reader.fieldnames or [])}):
            print(f"[错误] CSV 需含列 {required}，实际 {reader.fieldnames}", file=sys.stderr)
            sys.exit(2)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def _predict(rows):
    """用真实可信度过滤器对每条内容预测 is_ad_suspect。"""
    out = []
    for r in rows:
        ans = {
            "content_text": r.get("content_text", ""),
            "vote_up_count": int(r.get("vote_up_count") or 0),
            "comment_count": int(r.get("comment_count") or 0),
            "authority_level": int(r.get("authority_level") or 0),
        }
        assess(ans)  # 原地写入 is_ad_suspect / credibility
        out.append({
            "url": r.get("url", ""),
            "question": r.get("question", ""),
            "label": r.get("label", ""),
            "content_text": r.get("content_text", ""),
            "predicted_ad": bool(ans.get("is_ad_suspect")),
            "credibility": ans.get("credibility"),
        })
    return out


def _fmt_pct(x):
    return "—" if x is None else f"{x*100:.1f}%"


def run_filter_eval(rows):
    preds = _predict(rows)
    m = evaluate(preds)

    print("=" * 56)
    print("过滤器评测 · 软文识别（A6）")
    print("=" * 56)
    print(f"样本总数            : {m['n_total']}")
    print(f"真实软文 / 正常     : {m['n_ad_labeled']} / {m['n_ok_labeled']}")
    print(f"命中(TP) 漏判(FN)   : {m['tp']} / {m['fn']}")
    print(f"误杀(FP) 正确放行(TN): {m['fp']} / {m['tn']}")
    print("-" * 56)
    print(f"召回率 recall       : {_fmt_pct(m['recall'])}   （真软文抓到的比例）")
    print(f"误杀率 false_kill   : {_fmt_pct(m['false_kill_rate'])}   （正常内容被误判的比例）")
    print(f"精确率 precision    : {_fmt_pct(m['precision'])}")
    print("-" * 56)

    if m["missed"]:
        print(f"漏判案例（真软文未识别）× {len(m['missed'])}：")
        for r in m["missed"]:
            print(f"  · [{r.get('url','')}] {r.get('content_text','')[:40]}")
    else:
        print("漏判案例：无")

    if m["false_kills"]:
        print(f"误杀案例（正常被判软文）× {len(m['false_kills'])}：")
        for r in m["false_kills"]:
            print(f"  · [{r.get('url','')}] {r.get('content_text','')[:40]}")
    else:
        print("误杀案例：无")
    print()
    return m


def run_bucket_sample(rows):
    """A4 分桶抽查：按问题分组跑 rule_based_matrix，打出人工核对表。"""
    groups = {}
    for r in rows:
        groups.setdefault(r.get("question", "(未分组)"), []).append({
            "content_text": r.get("content_text", ""),
            "vote_up_count": 0,
            "is_ad_suspect": str(r.get("label", "")).lower() == "ad",
        })

    print("=" * 56)
    print("归并分桶抽查（A4）· 供人工核对归类是否正确")
    print("=" * 56)
    for q, answers in groups.items():
        m = rule_based_matrix(q, answers)
        print(f"【{q}】 engine={m.get('_engine')}")
        print(f"  共识 {len(m['consensus'])} / 分歧 {len(m['divergence'])} / 风险 {len(m['risks'])}")
        for c in m["consensus"]:
            print(f"    共识 ← {c['support_ids']}: {c['point']}")
        for d in m["divergence"]:
            print(f"    分歧[{d['stance']}] ← {d['support_ids']}: {d['argument']}")
        for rk in m["risks"]:
            print(f"    风险{rk.get('scenario','')} ← {rk['support_ids']}: {rk['point']}")
        print()


def main():
    ap = argparse.ArgumentParser(description="知鉴Search 评测命令")
    ap.add_argument("--labels", required=True, help="标注 CSV 路径")
    ap.add_argument("--buckets", action="store_true", help="附带 A4 分桶抽查")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出过滤器指标")
    args = ap.parse_args()

    rows = _read_labels(args.labels)
    metrics = run_filter_eval(rows)

    if args.buckets:
        run_bucket_sample(rows)

    if args.json:
        exportable = {k: v for k, v in metrics.items() if k not in ("missed", "false_kills")}
        exportable["missed_urls"] = [r.get("url", "") for r in metrics["missed"]]
        exportable["false_kill_urls"] = [r.get("url", "") for r in metrics["false_kills"]]
        print(json.dumps(exportable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
