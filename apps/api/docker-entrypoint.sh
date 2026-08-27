#!/bin/sh
# 마이그레이션을 먼저 올리고 서버를 띄웁니다.
#
# 마이그레이션이 실패하면 **서버를 띄우지 않습니다.** 스키마가 낡은 채로 뜨면
# 화면은 멀쩡해 보이는데 특정 조회만 500 이 나고, 그게 축제 당일에 터집니다.
set -e

echo "▸ DB 를 기다립니다…"
python - <<'PY'
import os, time, socket, urllib.parse
url = os.environ.get("DATABASE_URL", "")
host = urllib.parse.urlparse(url.replace("postgresql+psycopg", "postgresql")).hostname or "db"
port = int(urllib.parse.urlparse(url.replace("postgresql+psycopg", "postgresql")).port or 5432)
for attempt in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"  {host}:{port} 열렸습니다")
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(f"DB 에 연결할 수 없습니다 — {host}:{port}")
PY

echo "▸ 마이그레이션"
python -m alembic upgrade head

echo "▸ uvicorn (workers=${API_WORKERS:-4})"
exec uvicorn festaflow.main:app \
    --host 0.0.0.0 --port 8000 \
    --workers "${API_WORKERS:-4}" \
    --proxy-headers --forwarded-allow-ips='*'
