#!/usr/bin/env python3
"""演示预热 & 线上冒烟脚本（任务 A7）。

演示前把三个演示场景各跑一遍：
  - 预热缓存 / 模型连接，避免评委第一次点开时的冷启动延迟
  - 顺带当健康冒烟：任一场景异常立刻暴露

用法：
  python scripts/warmup.py                       # 默认打本地 127.0.0.1:8000
  python scripts/warmup.py --base https://your-domain.example.com
"""
import argparse
import json
import sys
import time
import urllib.request

SCENES = ["笔记本电脑怎么选", "考研值不值得", "健身先增肌还是减脂"]


def _post(base, query, timeout=15):
    req = urllib.request.Request(
        base.rstrip("/") + "/api/search",
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8"))
    return r.status, body, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--timeout", type=int, default=15)
    args = ap.parse_args()

    # 先探活
    try:
        with urllib.request.urlopen(args.base.rstrip("/") + "/", timeout=5) as r:
            health = json.loads(r.read().decode("utf-8"))
        print(f"[health] {health}")
    except Exception as e:
        print(f"[FATAL] 服务不可达：{type(e).__name__}", file=sys.stderr)
        sys.exit(1)

    all_ok = True
    for q in SCENES:
        try:
            status, body, cost = _post(args.base, q, args.timeout)
            mode = body.get("mode")
            n = len(body.get("answers", []))
            ok = status == 200 and mode != "degraded" and n > 0
            flag = "OK " if ok else "WARN"
            print(f"[{flag}] {q:12s} status={status} mode={mode} answers={n} {cost:.2f}s")
            all_ok = all_ok and ok
        except Exception as e:
            all_ok = False
            print(f"[FAIL] {q:12s} {type(e).__name__}: {e}")

    print("=> 预热完成，三场景均正常" if all_ok else "=> 预热发现异常，检查后再演示")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
