# 06 — 아키텍처

이 문서와 `packages/shared/`가 프론트·백엔드 병렬 작업의 **계약**입니다.
애매하게 남기면 두 쪽이 서로 다른 걸 만듭니다.

상세 스키마는 `docs/02-data-model.md`, 상세 API는 `docs/03-api-contract.md`를 정본으로 참조합니다.
여기서는 스택·경계·티켓만 확정합니다.

---

## 1. 스택 결정

| 영역 | 선택 | 이유 | 버린 대안 | 트레이드오프 |
|---|---|---|---|---|
| DB | **PostgreSQL 15** | 부분 유니크 인덱스·enum·jsonb·생성컬럼이 전부 필요 | SQLite | 로컬 개발에 컨테이너 필요 |
| 백엔드 | **Python 3.12 + FastAPI** | Pydantic이 곧 API 스키마이고 OpenAPI가 자동 생성됨 | Node/NestJS | 파이썬·TS 두 언어 운영 |
| ORM | **SQLAlchemy 2.0 + Alembic** | 부분 인덱스·CHECK를 마이그레이션으로 관리 | Prisma(파이썬 미지원) | 러닝커브 |
| 프론트 | **React 18 + TypeScript + Vite** | 생태계·채용, ECharts 연동 검증됨 | SvelteKit | 번들 크기 관리 필요 |
| 서버 상태 | **TanStack Query** | 폴링·`ETag` 캐시·낙관적 업데이트가 기본 제공 | Redux | 클라이언트 상태는 별도 관리 |
| 라우팅 | **React Router 6** | 세 영역(기획/운영/관객)의 레이아웃 분리가 쉬움 | TanStack Router | — |
| 차트 | **Apache ECharts (SVG 렌더러)** | 히트맵·커스텀 시리즈, PDF 벡터 출력 | Recharts | 번들 큼 → 관객 화면에서는 미로드 |
| 오프라인 | **IndexedDB (idb) + Service Worker** | 지급 큐 영속화. localStorage는 용량·동기 I/O 한계 | localStorage | SW 디버깅 비용 |
| QR 생성 | **qrcode (클라이언트)** | 참여 코드가 제3자 서버 로그에 남지 않음 | 외부 QR 이미지 API | — |
| QR 인식 | **BarcodeDetector + jsQR 폴백 (지연 로딩)** | iOS Safari 미지원 대응. 폴백은 부스 지급 화면에서만 받는다(gzip 47KB) | zxing-wasm | wasm 은 더 무겁고 로드가 늦어 부스 단말에서 불리 |
| PDF | **서버 렌더 (Playwright)** | 차트 SVG를 그대로 벡터로 유지 | 클라이언트 jsPDF | 서버에 브라우저 의존 |
| 인증 | **JWT (스태프) + 서버 발급 secret (관객)** | 무상태, 오프라인에서 토큰 검증 가능 | 세션 쿠키 | 만료 관리 필요 |
| 테스트 | pytest + Testcontainers / Vitest + Playwright | 실제 Postgres로 제약 검증 | 목 DB | CI 시간 |

**새 의존성 원칙** — 표준 라이브러리로 되는 건 표준 라이브러리로. 위 목록에 없는 패키지를
추가할 땐 티켓에 이유를 씁니다.

---

## 2. 디렉토리 구조

```
/
├─ apps/
│  ├─ api/                        ← 백엔드 전용 소유
│  │  ├─ src/festaflow/
│  │  │  ├─ main.py
│  │  │  ├─ routers/              HTTP 계층 — 검증·계산 로직 금지
│  │  │  │  ├─ festivals.py  booths.py  missions.py
│  │  │  │  ├─ grants.py     participants.py
│  │  │  │  ├─ insights.py   reports.py  staff.py
│  │  │  ├─ services/             도메인 로직 전부 여기
│  │  │  │  ├─ operations_insights.py
│  │  │  │  ├─ operations_recommendations.py
│  │  │  │  ├─ reward_campaigns.py
│  │  │  │  ├─ reward_campaign_impact.py
│  │  │  │  ├─ stamp_reveal.py    grants.py
│  │  │  │  ├─ diagnosis.py       reports.py
│  │  │  ├─ models/               SQLAlchemy
│  │  │  ├─ schemas/              Pydantic (OpenAPI 원천)
│  │  │  ├─ db/  auth/  config.py
│  │  ├─ migrations/              Alembic
│  │  └─ tests/
│  │
│  └─ web/                        ← 프론트엔드 전용 소유
│     ├─ src/
│     │  ├─ app/                  라우팅·프로바이더
│     │  ├─ areas/
│     │  │  ├─ planner/           SCR-1,2,3,13
│     │  │  ├─ admin/             SCR-4,6,7,8
│     │  │  ├─ booth/             SCR-9
│     │  │  └─ join/              SCR-10,11,12
│     │  ├─ components/           디자인 시스템 구현
│     │  ├─ charts/               ECharts 래퍼
│     │  ├─ offline/              IndexedDB 큐 + SW
│     │  ├─ api/                  생성 타입 기반 클라이언트
│     │  └─ styles/design-tokens.css   ← 05-ui.md 산출물 복사
│     └─ tests/
│
├─ packages/
│  └─ shared/                     ← 백엔드 소유. 프론트는 읽기 전용
│     ├─ openapi.json             FastAPI가 생성, 커밋
│     ├─ src/enums.ts             양쪽 동기화 기준
│     ├─ src/constants.ts         임계값 상수
│     ├─ src/types.ts             openapi.json에서 생성
│     └─ package.json
│
└─ docs/                          기획·설계 문서
```

**소유 경계**

| 경로 | 소유 | 다른 쪽 |
|---|---|---|
| `apps/api/**` | 백엔드 | 읽기만 |
| `apps/web/**` | 프론트 | 읽기만 |
| `packages/shared/**` | **백엔드** | 프론트는 읽기만 |
| `docs/**` | 공용 | 수정 시 상대에게 알림 |

`packages/shared`를 백엔드 소유로 둔 이유는, Pydantic 스키마가 계약의 원천이고
`openapi.json`이 거기서 생성되기 때문입니다. 프론트가 계약이 틀렸다고 판단하면
직접 고치지 말고 **"계약 이슈"로 보고**합니다. 양쪽이 같은 파일을 고치면
병렬 실행에서 충돌합니다.

---

## 3. 데이터 모델

`docs/02-data-model.md`가 정본입니다. 전체 DDL, 인덱스, 제약, 마이그레이션 순서가 거기 있습니다.

MVP 관문에 필요한 테이블만 추리면:

```
organizations
  └ festivals ─ festival_plans
       ├ festival_staff
       ├ booths ─ missions
       ├ participants
       ├ participations ─ (booth_id/base_points/bonus_points 스냅샷)
       ├ stamp_boards ─ stamp_tiles ─ stamp_reveals
       ├ visitor_counts
       └ recommendation_feedbacks
```

**반드시 DB 제약으로 걸어야 하는 것** (애플리케이션 코드에만 두면 동시 요청에서 뚫립니다)

| 제약 | 이유 |
|---|---|
| `UNIQUE (participant_id, mission_id) WHERE mission_id IS NOT NULL` | 중복 지급 방지 |
| `UNIQUE (client_request_id) WHERE NOT NULL` | 오프라인 재전송 멱등성 |
| `UNIQUE (board_version, participant_id, tile_id)` | 타일 중복 공개 방지 |
| `UNIQUE (board_id, board_version, participant_id, booth_id) WHERE booth_id NOT NULL` | 부스당 1조각 |
| `UNIQUE (festival_id, code)` on participants | 참여 코드 유일성 |
| `CHECK (ends_on >= starts_on)` | 기간 역전 방지 |

---

## 4. API 계약

`docs/03-api-contract.md`가 정본입니다. 아래는 MVP 핵심 3개의 요약입니다.

### 축제 생성

```http
POST /api/festivals
Authorization: Bearer <planner JWT>
```

```json
{
  "name": "춘천 가을 먹거리 축제",
  "region": "강원특별자치도 춘천시",
  "venue": "공지천 조각공원",
  "starts_on": "2026-10-10",
  "ends_on": "2026-10-12",
  "expected_visitors": 18000,
  "total_budget": 240000000,
  "plan": { "summary": "지역 식재료와 로컬 뮤지션이 만나는 3일", "venue_capacity": 4000 }
}
```

```json
201
{
  "festival": { "id": 12, "organization_id": 3, "status": "planning", "plan_stage": "draft" },
  "diagnosis": { "id": 34, "status": "pending" },
  "stamp_board": { "id": 12, "version": 1, "rows": 3, "cols": 3 },
  "operator_access_code": "8K2QD7"
}
```

```json
422
{ "error": { "code": "VALIDATION_FAILED", "message": "종료일은 시작일보다 빠를 수 없습니다.",
             "details": { "field": "ends_on" } } }
```

### 스탬프 지급 (오프라인 큐 포함)

```http
POST /api/festivals/{id}/booths/{bid}/grants
Authorization: Bearer <booth_manager JWT>
```

```json
{
  "participant_code": "FF-3A9K2P7Q",
  "mission_id": 21,
  "client_request_id": "0f8b6e5a-3c21-4a77-9d10-2b7e5f1c8a44",
  "queued_at": "2026-10-10T05:04:00Z"
}
```

```json
200
{
  "was_already_granted": false,
  "participation": {
    "id": 9001, "mission_id": 21, "booth_id": 7,
    "base_points": 100, "bonus_points": 0, "granted_points": 100,
    "verified_via": "staff_scan", "completed_at": "2026-10-10T05:04:00Z"
  },
  "revealed_tile": { "tile_index": 4, "board_version": 1 },
  "board_progress": { "revealed_count": 4, "total_tiles": 9, "is_complete": false }
}
```

| 오류 | 상태 |
|---|---|
| `MISSION_NOT_IN_BOOTH` | 409 |
| `BOOTH_INACTIVE` / `MISSION_INACTIVE` | 409 |
| `NO_TILE_AVAILABLE` | 409 |
| `PARTICIPANT_NOT_FOUND` | 404 |

`completed_at`은 `queued_at`이 있으면 그 값으로 기록합니다.

### 운영 인사이트 (폴링)

```http
GET /api/festivals/{id}/operations/insights
If-None-Match: "a3f9c1"
```

변경 없으면 `304`. 있으면 `200` + `ETag`.

```json
{
  "generated_at": "2026-10-10T05:00:00Z",
  "kpi": { "total_participants": 412, "total_completions": 1180,
           "completions_last_30m": 96, "high_concentration_booths": 1 },
  "booths": [ { "booth_id": 7, "name": "막국수 체험존", "share_last_30m": 0.49,
                "status": "HIGH", "status_reason": "최근 30분 96건 중 47건(49%)" } ],
  "recommendations": [ { "type": "REDISTRIBUTE", "target_booth_id": 9,
    "situation": "지역상점존 QR 완료가 8%입니다.",
    "evidence": "최근 30분 96건 중 8건",
    "action": "현장이 실제로 한산한지 확인해 주세요." } ],
  "disclaimer": "QR 완료 기반 참여 편중 지표이며 실제 인원수가 아닙니다."
}
```

---

## 5. 횡단 관심사

### 인증·인가

| 주체 | 방식 | 토큰 내용 |
|---|---|---|
| 기획자 | 계정 로그인 → JWT | `user_id`, `organization_id`, `role=planner` |
| 스태프 | 초대 QR + 6자리 코드 → JWT | `staff_id`, `festival_id`, `role`, `booth_id` |
| 관객 | 서버 발급 secret | 헤더 `X-Participant-Secret` |

**서버 강제 규칙**

- 모든 축제 스코프 쿼리에 `organization_id` 필터. 타 기관 리소스는 `403`이 아니라 **`404`**
  (존재 여부도 노출하지 않습니다)
- `booth_manager` 토큰은 `booth_id`가 일치하는 부스의 미션만 지급 가능. 위반 시 `403`
- 접근 코드 5회 실패 시 10분 잠금 (`staff_id` 단위)
- 관객 복구 시도 5회 제한 (`participant.recovery_attempts`)

### 에러 포맷

전 엔드포인트 동일합니다.

```json
{ "error": { "code": "SCREAMING_SNAKE", "message": "사용자에게 보여줄 한국어 문장",
             "details": { } } }
```

`message`는 그대로 화면에 노출되므로 **무엇이 잘못됐고 어떻게 고치는지**를 씁니다.
사과문·모호한 표현 금지.

### 로깅

- 구조화 JSON. `request_id`, `organization_id`, `festival_id`, `staff_id`, `duration_ms`
- **절대 남기지 않는 것**: 참여 코드, 접근 코드, secret, 복구 해시 원문, 사진 바이너리
- 지급·보관·권한 변경은 감사 로그에 행위자와 함께 기록

### 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | — | Postgres 접속 |
| `JWT_SECRET` | — | 토큰 서명 키 |
| `JWT_TTL_HOURS` | `12` | 스태프 세션 수명 (축제 하루 기준) |
| `DEMO_MODE` | `false` | 데모 축제 자동 시드 (0건일 때만) |
| `KTO_BASE_URL` | `https://apis.data.go.kr/B551011` | 관광공사 기관 코드 경로 |
| `KTO_MOBILE_APP` | `FestaFlow` | 활용 통계용. 모든 요청에 필수 |
| `KTO_API_KEY` | — | 관광공사 공통 키 |
| `KTO_DEMAND_API_KEY` | — | 수요 API 전용 키 |
| `KTO_TOUR_API_KEY` | — | 관광정보 API 전용 키 |
| `KTO_DAILY_QUOTA` | `1000` | 개발계정 한도. 초과 전 경고 로그 |
| `TOURISM_SNAPSHOT_TTL_DAYS` | `7` | 관광 스냅샷 유효기간 |
| `MEDIA_BUCKET` | — | 사진 오브젝트 스토리지 |
| `MEDIA_RETENTION_DAYS` | `90` | 사진 보관 기간 |
| `ANONYMIZE_AFTER_DAYS` | `90` | 참여자 익명화 시점 |
| `SCAN_TOKEN_WINDOW_SECONDS` | `300` | 부스 QR 유효 window (오프라인 대응으로 5분) |
| `INSIGHTS_MIN_SAMPLE` | `10` | 최근 30분 최소 완료 수 |
| `PDF_RENDERER_URL` | — | Playwright 렌더 서비스 |

---

## 6. 작업 분할

### 백엔드

| ID | 티켓 | 경로 | 완료 조건 |
|---|---|---|---|
| BE-0 | 스키마·마이그레이션·`packages/shared` 생성 | `apps/api/migrations/**`, `packages/shared/**` | Alembic up/down 통과, `openapi.json`·`types.ts` 커밋 |
| BE-1 | 인증 (기획자 JWT, 스태프 2단계, 관객 secret) | `auth/**`, `routers/staff.py` | US-1·5·6 AC 통과, 잠금 동작 |
| BE-2 | 축제 CRUD + 기관 스코프 | `routers/festivals.py` | US-1·2·3·4 AC 통과, 타 기관 `404` |
| BE-3 | 부스·미션 CRUD | `routers/booths.py`, `missions.py` | US-7·8·9 AC 통과, 트랜잭션 롤백 검증 |
| BE-4 | 참여자 발급·복구 | `routers/participants.py` | US-10·11 AC 통과 |
| BE-5 | 지급 + 조각 공개 (트랜잭션) | `services/grants.py`, `stamp_reveal.py` | US-12·15 AC 통과, 동시 요청 20건 → 1건 |
| BE-6 | 오프라인 배치 동기화 | `routers/grants.py` | US-13 AC 통과, `completed_at == queued_at` |
| BE-7 | 스탬프 보드 설정 + 버전 | `routers/boards.py` | US-14 AC 통과, reveal 보존 검증 |
| BE-8 | 운영 인사이트 + `ETag` | `services/operations_insights.py` | US-17 AC 통과, p95 < 1s |
| BE-9 | 추천 + 판정 기록 | `services/operations_recommendations.py` | US-18 AC 통과 |
| BE-10 | 결과보고서 집계 | `services/reports.py` | US-19 AC 통과, 참여 0건에서도 200 |
| BE-11 | PDF 렌더 | `routers/reports.py` | US-20 AC 통과, 차트 벡터 유지 |
| BE-12 | 실측 방문객 | `routers/visitor_counts.py` | 출처 우선순위 동작 |
| BE-13 | 보존·익명화 배치 | `jobs/**` | 90일 경과 익명화·사진 삭제 |

### 프론트엔드

| ID | 티켓 | 경로 | 완료 조건 |
|---|---|---|---|
| FE-0 | 앱 셸·라우팅·토큰·API 클라이언트 | `app/**`, `api/**`, `styles/**` | 세 영역 레이아웃 분리, MSW 목 동작 |
| FE-1 | 디자인 시스템 컴포넌트 | `components/**` | 05-ui.md §2 전 컴포넌트 + 전 상태, axe 위반 0 |
| FE-2 | SCR-1 워크스페이스 | `areas/planner/**` | 로딩·빈·에러·쿼터초과 4상태 구현 |
| FE-3 | SCR-2·3 축제 생성·수정 | `areas/planner/**` | 검증 4겹, 코드 1회 노출, 실패 시 입력 유지 |
| FE-4 | SCR-5 스태프 로그인 | `areas/admin/**` | QR→코드 2단계, 잠금 안내 |
| FE-5 | SCR-6 대시보드 + 폴링 | `areas/admin/**` | 폴링이 폼 초기화 안 함, `304` 처리 |
| FE-6 | SCR-7·8 부스·미션·보드 관리 | `areas/admin/**` | 보드 재설정 확인 플로우 |
| FE-7 | SCR-9 부스 지급 | `areas/booth/**` | 스캐너 + 수동 폴백, 6개 상태 |
| FE-8 | 오프라인 큐 (IndexedDB + SW) | `offline/**` | 네트워크 차단 후 5건 → 복구 → 중복 0 |
| FE-9 | SCR-10·11·12 관객 화면 | `areas/join/**` | 3초 폴링, 조각 공개 연출, 캐시 표시 |
| FE-10 | SCR-13 리포트 + 차트 | `areas/planner/**`, `charts/**` | 06-charts.md 폼 준수, 표 보기 토글 |
| FE-11 | 접근성 마감 | 전역 | 키보드 전 경로, `aria-live`, 인쇄 스타일 |

### 실행 순서

```
BE-0 ──┬─▶ BE-1 ─▶ BE-2 ─▶ BE-3 ─▶ BE-5 ─▶ BE-7 ─▶ BE-8 ─▶ BE-9 ─▶ BE-10 ─▶ BE-11
       │                     └▶ BE-4 ─▶ BE-6            BE-12 ─┘      BE-13
       │
       └─▶ FE-0 ─▶ FE-1 ─┬─▶ FE-2 ─▶ FE-3
                          ├─▶ FE-4 ─▶ FE-5 ─▶ FE-6
                          ├─▶ FE-7 ─▶ FE-8
                          ├─▶ FE-9
                          └─▶ FE-10 ─▶ FE-11
```

**BE-0이 유일한 직렬 선행 작업**입니다. `packages/shared`가 나와야 프론트가 계약대로
목을 세우고 병렬로 출발할 수 있습니다. 그 이후 FE와 BE는 서로를 기다리지 않습니다 —
프론트는 MSW 핸들러로 개발하고 실제 엔드포인트로 전환합니다.
