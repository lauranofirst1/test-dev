# FestaFlow

축제 기획서에 쓴 숫자와 현장에서 찍힌 QR과 결과보고서가 **같은 데이터**를 쓰게 만드는 서비스.

2026 관광데이터 활용 공모전 ②-2 웹·앱 구현 부문 출품작 — **지정과제 9번**
(축제 수요 예측 실패 및 주관적 경험 의존형 기획으로 인한 예산 낭비 리스크,
대규모 관광객 쏠림에 따른 축제 만족도 저하)

> 🚨 **1차 심사 제출 마감 2026.09.21(월) 16:00** — [제출 요건과 역산 일정](docs/08-contest-submission.md)

## 문서

설계 문서는 [docs/](docs/)에 있습니다. 처음이면 [docs/README.md](docs/README.md)부터 보세요.

## 개발 환경 준비

### 1. 데이터베이스

```bash
brew install postgresql@17
brew services start postgresql@17
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"

createuser -s festaflow
createdb -O festaflow festaflow
psql -d festaflow -c "ALTER USER festaflow WITH PASSWORD 'festaflow';"
psql -d festaflow -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

`pgcrypto`는 `booths.qr_secret`의 기본값(`gen_random_bytes`)에 필요합니다.

### 2. 환경변수

```bash
cp .env.example .env
```

`.env`의 `KTO_API_KEY`에 공공데이터포털 인증키를 넣으세요.

> ⚠ 포털은 **Encoding / Decoding 두 벌**을 줍니다. **Decoding 키**를 넣으세요.
> Encoding 키를 넣으면 HTTP 클라이언트가 재인코딩해 `%2B`가 `%252B`가 되면서 인증이 깨집니다.

`.env`는 `.gitignore`에 있습니다. 커밋되지 않습니다.

### 3. 백엔드

```bash
cd apps/api
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python -m alembic upgrade head
```

### 4. 프론트엔드

```bash
cd apps/web
npm install
```

## 실행

백엔드와 프론트엔드를 한 번에 띄웁니다. Ctrl-C 한 번으로 둘 다 내려갑니다.

```bash
./dev.sh
# → http://localhost:5173      프론트엔드 (여기로 접속)
# → http://localhost:8000/docs 백엔드 API 문서
```

프론트엔드가 `/api` 요청을 백엔드로 프록시하므로 브라우저는 5173만 열면 됩니다.
포트를 바꾸려면 `API_PORT=8001 WEB_PORT=5174 ./dev.sh`.

따로 띄우려면:

```bash
cd apps/api && ./.venv/bin/uvicorn festaflow.main:app --reload --port 8000
cd apps/web && npm run dev
```

그 밖에:

```bash
cd apps/api

# 테스트 (인증키 불필요)
./.venv/bin/python -m pytest -q

# TourAPI 실호출 점검 (인증키 필요)
./.venv/bin/python scripts/kto_smoke.py
```

`kto_smoke.py`는 승인된 API만 성공합니다. 미승인 서비스는 `code=30`이 나오는데,
키가 틀린 게 아니라 **아직 활용신청을 안 했다**는 뜻입니다.
신청하면 자동 승인으로 약 10분 뒤 열립니다.

## 진행 상황

테스트 **153개 통과**. 기획 진단부터 현장 QR 지급·조각 수집까지 실제로 돕니다.
운영 인사이트(부스 편중 감지)와 사후 리포트가 남았습니다.

| | 상태 |
|---|---|
| 프로젝트 구조 · 환경변수 | ✅ |
| PostgreSQL 17 + pgcrypto | ✅ |
| TourAPI 클라이언트 (함정 8개 대응) | ✅ 테스트 21개 |
| FastAPI 앱 부팅 · 공통 에러 포맷 | ✅ |
| 데이터 모델 · Alembic 마이그레이션 | ✅ 제약 테스트 25개 |
| 사전 진단 파이프라인 | ✅ 테스트 36개 · 실호출로 검증 |
| 축제 · 진단 API | ✅ 테스트 16개 |
| 스태프 인증 (2단계 로그인 · JWT) | 🟡 스태프는 완료. 아래 참고 |
| 부스 · 미션 · QR 지급 · 조각 보드 API | ✅ 테스트 33개 |
| 프론트엔드 — 기획자 화면 | 🟡 목록 · 생성 · 진단 3화면 |
| 프론트엔드 — 관객 화면 | 🟡 참여 · 조각 보드 · QR 스캔 |
| 운영 인사이트 · 보상 캠페인 API | ⏳ 모델만 있음 |
| 사후 리포트 | ⏳ |

**🟡 스태프 인증** — `POST /api/auth/staff/login` 은 계약대로 돕니다(접근 코드 bcrypt,
5회 실패 시 10분 잠금, 자기 축제만 접근, 역할 검사). 남은 것 두 가지입니다.

- **기획자(planner) 자격증명이 스펙에 없습니다.** 계약의 로그인은 축제별 스태프용이라
  `festival_id` 가 필요한데 축제 목록·생성은 축제가 생기기 전에 호출됩니다.
  그래서 이 두 엔드포인트만 `X-Organization-Id` 헤더 폴백을 쓰고, 폴백은
  `APP_ENV=local` 또는 `DEMO_MODE=true` 에서만 삽니다. 그 밖에서는 401 입니다.
- 스태프 발급·목록·코드 재발급·비활성화 엔드포인트(계약 §1)가 아직 없습니다.
  지금은 축제 생성 시 만들어지는 운영자 한 명으로만 로그인합니다.

**🟡 프론트엔드** — 기획자 화면 3개(워크스페이스 · 새 축제 · 사전 진단)와
관객 화면 2개(`/join/:id` 참여·조각 보드, `/join/:id/scan` QR 스캔)까지입니다.
스태프 로그인 화면과 부스 운영 화면(참여자 QR 스캔 · 회전 QR 표시)은 없습니다.

조각 보드 그림은 자리표시 이미지입니다. 실제 축제 그림이 준비되면
`apps/web/public/images/chuncheon-stamp-board.png` 에 덮어쓰면 됩니다
(생성 스크립트: `apps/web/scripts/make-placeholder-board.py`).

## 규정 주의

- **캐시 기본 OFF** (`TOURISM_SNAPSHOT_CACHE_ENABLED=false`).
  공모전은 실시간 호출을 요구하고 인증키의 **실제 호출 이력을 검증**합니다.
  캐시 히트로 호출이 0회가 되면 심사 불이익 대상입니다.
- 화면 출처 표기는 `출처: ⓒ한국관광공사`. **`TourAPI` 단독 표기는 금지**입니다.
- 서비스명·로고에 "한국관광공사", "KTO"를 쓸 수 없습니다.
