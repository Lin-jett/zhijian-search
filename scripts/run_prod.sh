#!/usr/bin/env bash
# 知鉴Search 后端生产启动脚本（任务 A3 · 进程守护底座）
#
# 用法：
#   DEEPSEEK/知乎密钥一律走环境变量，绝不写进文件（A3 要求）。
#   export ZHIJIAN_DATA_MODE=hybrid
#   export ZHIHU_TOKEN=xxx
#   export ZHIJIAN_LLM_MODE=api
#   export LLM_API_KEY=xxx
#   ./scripts/run_prod.sh
#
# 说明：
#   - 用 uvicorn 多 worker 常驻；崩溃由外层守护（systemd / docker restart）拉起。
#   - 监听 127.0.0.1，由前置 Nginx 反代 + HTTPS（见 deploy/nginx.conf）。
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${APP_HOST:-127.0.0.1}"
PORT="${APP_PORT:-8000}"
WORKERS="${APP_WORKERS:-2}"

echo "[run_prod] data_mode=${ZHIJIAN_DATA_MODE:-offline} llm_mode=${ZHIJIAN_LLM_MODE:-mock} host=$HOST port=$PORT workers=$WORKERS"

# 不打印任何密钥；仅提示是否已配置
[ -n "${ZHIHU_TOKEN:-}" ] && echo "[run_prod] ZHIHU_TOKEN: 已配置" || echo "[run_prod] ZHIHU_TOKEN: 未配置（offline/hybrid 缓存可用）"
[ -n "${LLM_API_KEY:-}" ] && echo "[run_prod] LLM_API_KEY: 已配置" || echo "[run_prod] LLM_API_KEY: 未配置（走 mock 规则摘要）"

exec uvicorn backend.main:app \
  --host "$HOST" --port "$PORT" \
  --workers "$WORKERS" \
  --log-level info \
  --no-access-log
