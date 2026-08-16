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
```

## 실행

```bash
cd apps/api

# 개발 서버
./.venv/bin/uvicorn festaflow.main:app --reload --port 8000
# → http://localhost:8000/docs

# 테스트 (인증키 불필요)
./.venv/bin/python -m pytest -q

# TourAPI 실호출 점검 (인증키 필요)
./.venv/bin/python scripts/kto_smoke.py
```

`kto_smoke.py`는 승인된 API만 성공합니다. 미승인 서비스는 `code=30`이 나오는데,
키가 틀린 게 아니라 **아직 활용신청을 안 했다**는 뜻입니다.
신청하면 자동 승인으로 약 10분 뒤 열립니다.

## 진행 상황

| | 상태 |
|---|---|
| 프로젝트 구조 · 환경변수 | ✅ |
| PostgreSQL 17 + pgcrypto | ✅ |
| TourAPI 클라이언트 (함정 8개 대응) | ✅ 테스트 21개 통과 |
| FastAPI 앱 부팅 · 공통 에러 포맷 | ✅ |
| 데이터 모델 · Alembic 마이그레이션 | ⏳ 다음 |
| 사전 진단 파이프라인 | ⏳ |
| QR 지급 · 조각 보드 · 관객 화면 | ⏳ |
| 사후 리포트 | ⏳ |
| 프론트엔드 | ⏳ |

## 규정 주의

- **캐시 기본 OFF** (`TOURISM_SNAPSHOT_CACHE_ENABLED=false`).
  공모전은 실시간 호출을 요구하고 인증키의 **실제 호출 이력을 검증**합니다.
  캐시 히트로 호출이 0회가 되면 심사 불이익 대상입니다.
- 화면 출처 표기는 `출처: ⓒ한국관광공사`. **`TourAPI` 단독 표기는 금지**입니다.
- 서비스명·로고에 "한국관광공사", "KTO"를 쓸 수 없습니다.
