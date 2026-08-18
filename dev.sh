#!/usr/bin/env bash
#
# 백엔드(:8000)와 프론트엔드(:5173)를 한 번에 띄운다. Ctrl-C 한 번으로 둘 다 내려간다.
#
#   ./dev.sh
#
# 포트는 API_PORT / WEB_PORT 로 바꿀 수 있다. 브라우저는 프론트엔드 주소만 열면 되고,
# /api 요청은 vite 가 백엔드로 프록시한다(apps/web/vite.config.ts).
#
# 최초 1회 셋업(가상환경·의존성·DB·.env)은 이 스크립트가 하지 않는다.
# 빠진 게 있으면 무엇을 실행해야 하는지 알려주고 멈춘다. README '개발 환경 준비' 참고.

set -uo pipefail
cd "$(dirname "$0")"

API_PORT=${API_PORT:-8000}
WEB_PORT=${WEB_PORT:-5173}

die() {
  echo "✗ $1" >&2
  exit 1
}

# ── 전제 조건 ────────────────────────────────────────────────────────────────
[ -x apps/api/.venv/bin/uvicorn ] ||
  die "apps/api/.venv 가 없습니다 → cd apps/api && python3 -m venv .venv && ./.venv/bin/pip install -e \".[dev]\""

[ -d apps/web/node_modules ] ||
  die "apps/web/node_modules 가 없습니다 → cd apps/web && npm install"

[ -f .env ] ||
  die ".env 가 없습니다 → cp .env.example .env 후 KTO_API_KEY 에 공공데이터포털 Decoding 키를 넣으세요"

# pg_isready 는 PATH 에 없을 수 있다(Homebrew 는 keg-only 로 깐다).
PG_ISREADY=$(command -v pg_isready || echo /opt/homebrew/opt/postgresql@17/bin/pg_isready)
if [ -x "$PG_ISREADY" ]; then
  "$PG_ISREADY" -q -h localhost ||
    die "PostgreSQL 이 응답하지 않습니다 → brew services start postgresql@17"
else
  echo "⚠ pg_isready 를 찾지 못해 DB 확인을 건너뜁니다. 연결 오류가 나면 postgresql@17 상태를 보세요." >&2
fi

# 이미 뜬 서버를 조용히 두고 새로 띄우면 어느 쪽을 보고 있는지 알 수 없다. 멈춘다.
for port in "$API_PORT" "$WEB_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    die "$port 포트를 이미 누가 쓰고 있습니다 → lsof -ti:$port | xargs kill"
  fi
done

# ── 실행 ─────────────────────────────────────────────────────────────────────
api_pid=""
web_pid=""
cleaned=""

cleanup() {
  [ -n "$cleaned" ] && return
  cleaned=1
  echo ""
  echo "내려갑니다…"
  # uvicorn --reload 와 vite 는 자식 프로세스를 띄운다. 프로세스 그룹째로 보내야 남지 않는다.
  for pid in "$api_pid" "$web_pid"; do
    [ -n "$pid" ] && kill -TERM -"$pid" 2>/dev/null || true
  done
  wait 2>/dev/null
}
trap cleanup INT TERM EXIT

# set -m 으로 각 잡을 독립 프로세스 그룹에 넣어 kill -TERM -PID 가 통하게 한다.
set -m

(cd apps/api && exec ./.venv/bin/uvicorn festaflow.main:app --reload --port "$API_PORT") &
api_pid=$!

(cd apps/web && exec npm run dev -- --port "$WEB_PORT" --strictPort) &
web_pid=$!

set +m

echo ""
echo "  백엔드    http://localhost:$API_PORT/docs"
echo "  프론트엔드 http://localhost:$WEB_PORT   ← 여기로 접속"
echo ""
echo "  Ctrl-C 로 둘 다 종료"
echo ""

# 한쪽이 죽으면 나머지도 내린다 — 반쪽만 살아 있는 상태가 제일 헷갈린다.
# (`wait -n` 은 macOS 기본 bash 3.2 에 없어서 폴링한다.)
while kill -0 "$api_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do
  sleep 1
done

# Ctrl-C 로 내려온 것은 정상 종료다. 아래 진단은 한쪽이 혼자 죽은 경우만 찍는다.
[ -n "$cleaned" ] && exit 0

kill -0 "$api_pid" 2>/dev/null || echo "✗ 백엔드가 먼저 종료됐습니다. 위 로그를 보세요." >&2
kill -0 "$web_pid" 2>/dev/null || echo "✗ 프론트엔드가 먼저 종료됐습니다. 위 로그를 보세요." >&2
