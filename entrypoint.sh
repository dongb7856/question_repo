#!/bin/sh
set -e

if [ "${SKIP_IMPORT:-0}" != "1" ]; then
  echo ">> 同步题库到 PostgreSQL（migration + pay 付费真题）..."
  python3 scripts/import_pay_questions.py || echo "WARN: 导入失败，请检查数据库连接"
fi

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8765 \
  --proxy-headers \
  --forwarded-allow-ips="*"
