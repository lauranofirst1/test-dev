# FestaFlow API 계약

- Base: `/api`
- 모든 요청/응답은 JSON. 시각은 ISO 8601 UTC(`2026-08-16T09:00:00Z`).
- 오류 응답 형식은 전부 동일합니다.

```json
{ "error": { "code": "BOOTH_NOT_IN_FESTIVAL", "message": "해당 부스는 이 축제에 속하지 않습니다.", "details": {} } }
```

| 상태 | 사용처 |
|---|---|
| 400 | 도메인 규칙 위반 (타 축제 리소스 연결 등) |
| 401 | 토큰 없음·만료 |
| 403 | 역할·부스 권한 부족 |
| 404 | 리소스 없음 또는 아카이브됨 |
| 409 | 상태 충돌 (다른 부스의 미션 지급, 보드 재확인 필요) |
| 410 | 만료된 부스 QR 토큰 |
| 422 | 입력 검증 실패 (기간 역전, 음수 방문객) |

---

## 1. 인증

| 메서드 | 경로 | 역할 | 설명 |
|---|---|---|---|
| POST | `/auth/staff/login` | - | `{ festival_id, staff_id, access_code }` → 세션 토큰 |
| POST | `/festivals/{id}/staff` | operator | 스태프 발급. 초대 URL + 평문 코드를 **1회만** 응답 |
| GET | `/festivals/{id}/staff` | operator | 스태프 목록 (코드 해시는 미노출) |
| POST | `/festivals/{id}/staff/{sid}/rotate` | operator | 접근 코드 재발급 |
| DELETE | `/festivals/{id}/staff/{sid}` | operator | 비활성화 |

**2단계 로그인** — 초대 QR은 `/staff/login?f={festival_id}&s={staff_id}`를 담습니다.
여기에 비밀은 없습니다. 스캔하면 로그인 화면이 열리고, 6자리 접근 코드를 입력해야
세션이 발급됩니다. QR 사진이 유출돼도 코드 없이는 들어올 수 없습니다.

`POST /festivals/{id}/staff` 응답 `201`:

```json
{
  "staff": { "id": 45, "role": "booth_manager", "display_name": "김운영", "booth_id": 7 },
  "invite_url": "https://festaflow.kr/staff/login?f=12&s=45",
  "access_code": "8K2QD7"
}
```

토큰 payload: `{ staff_id, festival_id, role, booth_id }`.
`booth_manager` 토큰은 자신의 `booth_id`에 속한 미션만 지급할 수 있습니다(서버 강제, 위반 시 403).
접근 코드는 5회 연속 실패 시 10분 잠급니다.

---

## 2. 축제 · 기획

| 메서드 | 경로 | 역할 | 설명 |
|---|---|---|---|
| GET | `/festivals` | planner | 목록. `archived_at IS NULL`, 생성 시각 DESC, ID DESC |
| POST | `/festivals` | planner | 생성. 축제 + 기획 + pending 진단 + 기본 보드 + operator 스태프를 한 트랜잭션으로 |
| GET | `/festivals/{id}` | 전체 | 상세 (기획 상세 포함) |
| PUT | `/festivals/{id}` | planner | 수정. `updated_at`만 갱신, 하위 데이터 무변경 |
| POST | `/festivals/{id}/archive` | planner | 보관(구 삭제) |

`POST /festivals` 요청 예시:

```json
{
  "name": "춘천 가을 먹거리 축제",
  "region": "강원특별자치도 춘천시",
  "venue": "공지천 조각공원",
  "starts_on": "2026-10-10",
  "ends_on": "2026-10-12",
  "expected_visitors": 18000,
  "total_budget": 240000000,
  "plan": {
    "summary": "지역 식재료와 로컬 뮤지션이 만나는 3일",
    "purposes": ["지역상권 활성화", "관광객 유치"],
    "target_segments": ["가족", "20~30대"],
    "venue_capacity": 4000,
    "planned_food": 12,
    "planned_performance": 6,
    "safety_plan": "권역별 안전요원 2인 배치, 야간 조명 보강"
  }
}
```

응답 `201`:

```json
{
  "festival": { "id": 12, "status": "planning", "...": "..." },
  "diagnosis": { "id": 34, "status": "pending" },
  "stamp_board": { "id": 12, "version": 1, "rows": 3, "cols": 3 },
  "operator_access_code": "8K2QD7"
}
```

`operator_access_code`는 이 응답에서만 평문으로 나옵니다.

**검증** — `ends_on >= starts_on`, `expected_visitors > 0`, `total_budget >= 0` 위반 시 `422`.

---

## 3. 진단

| 메서드 | 경로 | 역할 | 설명 |
|---|---|---|---|
| POST | `/festivals/{id}/diagnoses` | planner | 새 진단 실행 (append-only) |
| GET | `/festivals/{id}/diagnoses/latest` | planner | 최신 완료 진단 + 5개 항목 |
| GET | `/festivals/{id}/diagnoses` | planner | 이력, 최신순 페이지네이션 |
| GET | `/festivals/{id}/diagnoses/comparison` | planner | 최신 완료 2건 비교 |
| GET | `/festivals/{id}/tourism-insights` | planner | 관광 지표 · 자원 · 홍보 활용안 |

원문의 `POST /festivals/{id}/diagnose`(단수)를 리소스 컬렉션 `POST /diagnoses`로 바꿨습니다.
진단이 이력으로 쌓이는 구조와 경로 의미를 일치시키기 위함입니다.

`GET /diagnoses/latest` 응답 일부:

```json
{
  "id": 51,
  "status": "completed",
  "rubric_version": "v1",
  "total_score": 78.5,
  "risk": "caution",
  "created_at": "2026-08-16T09:00:00Z",
  "tourism_source": {
    "provider": "kto_live",
    "base_month": "202510",
    "note": "체류·소비 지수는 한국관광공사 실데이터, 수용력·혼잡 위험도·지역 연계 준비도는 FestaFlow 추정치"
  },
  "items": [
    {
      "category": "crowd_safety",
      "score": 21.0, "max_score": 30, "level": "caution",
      "reason": "일평균 6,000명 대비 계획 일일 수용력 8,000명(동시 수용 4,000명 × 2회전) 사용률 75%",
      "recommendation": "피크 시간대 입장 분산 안내와 우회 동선을 확보하세요."
    }
  ],
  "warnings": [
    { "code": "BOARD_UNCOMPLETABLE", "message": "9조각 보드에 활성 부스가 5개라 완성이 불가능합니다." }
  ]
}
```

`GET /diagnoses/comparison` 응답:

```json
{
  "comparable": true,
  "previous": { "id": 44, "total_score": 71.0, "risk": "caution" },
  "current":  { "id": 51, "total_score": 78.5, "risk": "caution" },
  "delta": 7.5,
  "items": [
    { "category": "ops_readiness", "previous": 5.0, "current": 8.0, "delta": 3.0 },
    { "category": "program_balance", "previous": 14.0, "current": 13.0, "delta": -1.0 }
  ],
  "biggest_improvement": {
    "category": "ops_readiness", "delta": 3.0,
    "reason": "안전 계획과 교통 계획이 추가되었습니다.",
    "recommendation": "혼잡 대응 계획을 추가하면 항목 만점에 도달합니다."
  }
}
```

진단이 1건뿐이면 `{ "comparable": false, "reason": "FIRST_DIAGNOSIS" }`,
두 진단의 관광 데이터 공급자가 다르면 `{ "comparable": false, "reason": "PROVIDER_MISMATCH" }`를 반환합니다.
항목 배열은 개선·악화·유지를 모두 포함하며 숨기지 않습니다.

---

## 4. 부스 · 미션

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/festivals/{id}/booths` | operator, booth_manager |
| POST | `/festivals/{id}/booths` | operator |
| PUT | `/festivals/{id}/booths/{bid}` | operator |
| POST | `/festivals/{id}/booths/{bid}/archive` | operator |
| GET | `/festivals/{id}/missions` | operator, booth_manager |
| POST | `/festivals/{id}/missions` | operator |
| PUT | `/festivals/{id}/missions/{mid}` | operator |
| POST | `/festivals/{id}/missions/{mid}/archive` | operator |

부스 생성 시 첫 미션 동시 추가:

```json
{
  "name": "막국수 체험존",
  "booth_type": "experience",
  "type_label": "체험",
  "location": "A구역 3번",
  "manager_name": "김운영",
  "verify_mode": "staff_scan",
  "first_mission": { "title": "막국수 반죽 체험", "points": 100, "is_active": true }
}
```

`verify_mode`는 `staff_scan`(기본) 또는 `participant_scan`입니다.
`qr_secret`은 어떤 응답에도 포함되지 않습니다.

서버는 부스 flush로 ID를 확보한 뒤 미션의 `booth_id`를 그 값으로 **강제 설정**합니다.
요청에 다른 `booth_id`가 들어와도 무시합니다. 실패 시 전체 롤백.

타 축제 부스를 미션에 연결하면 `400 MISSION_BOOTH_FESTIVAL_MISMATCH`.

---

## 5. 운영 인사이트

```
GET /festivals/{id}/operations/insights
역할: operator
```

`ETag` 헤더를 반환하며, 클라이언트가 `If-None-Match`를 보내고 변화가 없으면 `304`입니다.
10초 폴링에서 대부분의 응답이 304가 되어 집계 부하가 줄어듭니다.

```json
{
  "generated_at": "2026-10-10T05:00:00Z",
  "kpi": {
    "total_participants": 412,
    "total_completions": 1180,
    "completions_last_30m": 96,
    "high_concentration_booths": 1
  },
  "booths": [
    {
      "booth_id": 7, "name": "막국수 체험존", "is_active": true,
      "total_completions": 420, "unique_participants": 300,
      "last_10m": 18, "last_30m": 47, "last_60m": 88,
      "share_last_30m": 0.49,
      "status": "HIGH",
      "status_reason": "최근 30분 축제 전체 96건 중 47건(49%)이 이 부스에서 발생",
      "last_completed_at": "2026-10-10T04:59:12Z"
    }
  ],
  "recommendations": [
    {
      "type": "REDISTRIBUTE",
      "situation": "막국수 체험존에 최근 30분 참여의 49%가 집중되었습니다.",
      "evidence": "같은 시간 지역상점존은 8%(8건)에 머물렀습니다.",
      "action": "지역상점존에 한시 추가 보상을 걸고 위치 안내를 강화하세요.",
      "target_booth_id": 9
    }
  ],
  "warnings": [
    { "code": "BOARD_UNCOMPLETABLE", "message": "9조각 보드에 활성 부스가 5개라 완성이 불가능합니다." }
  ],
  "disclaimer": "이 지표는 부스에서 검증된 QR/미션 완료 건수를 현장 참여량의 proxy로 사용한 참여 편중 위험 지표이며, 실제 인원수나 물리적 밀집도가 아닙니다."
}
```

최근 30분 전체 완료가 10건 미만이면 모든 부스 `status`는 `INSUFFICIENT_DATA`,
`recommendations`는 빈 배열입니다.

---

## 6. 보상 캠페인

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/festivals/{id}/reward-campaigns?active_only=true` | 전체 (참여자 화면 포함) |
| POST | `/festivals/{id}/reward-campaigns` | operator |
| PUT | `/festivals/{id}/reward-campaigns/{cid}` | operator |
| DELETE | `/festivals/{id}/reward-campaigns/{cid}` | operator |
| GET | `/festivals/{id}/reward-campaigns/{cid}/impact?window_minutes=30` | operator |

`active_only=true`는 **서버 시각 기준** 활성 캠페인만 반환합니다.
클라이언트가 시각을 판정하지 않습니다.

impact 응답:

```json
{
  "campaign_id": 3,
  "window_minutes": 30,
  "before": { "from": "2026-10-10T04:30:00Z", "to": "2026-10-10T05:00:00Z", "target_completions": 8,  "festival_completions": 90, "share": 0.089 },
  "after":  { "from": "2026-10-10T05:00:00Z", "to": "2026-10-10T05:30:00Z", "target_completions": 31, "festival_completions": 104, "share": 0.298 },
  "share_change_pp": 20.9,
  "completion_change_rate": 2.875,
  "top_booth_before": { "booth_id": 7, "share_before": 0.49, "share_after": 0.33 },
  "data_status": "SUFFICIENT",
  "in_progress": false,
  "disclaimer": "캠페인 전후 참여 변화이며 보상의 인과 효과가 아닙니다."
}
```

before+after 표본 합계가 20건 미만이면 `data_status: "INSUFFICIENT_DATA"`,
after 구간이 아직 진행 중이면 `in_progress: true`입니다.

---

## 7. 스탬프 보드

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/festivals/{id}/stamp-board` | operator |
| PUT | `/festivals/{id}/stamp-board` | operator |
| GET | `/festivals/{id}/stamp-board/me` | participant (secret) |

`PUT` 요청에서 `rows`/`cols`/`reveal_mode`/`grant_unit` 중 하나라도 바뀌고
현재 버전에 공개 이력이 있으면:

```
409 Conflict
{ "error": { "code": "BOARD_RESET_REQUIRES_CONFIRMATION",
             "message": "참여자 37명의 수집 진행이 초기화됩니다.",
             "details": { "affected_participants": 37, "revealed_count": 158 } } }
```

`?confirm=true`를 붙이면 진행합니다. 이때 `version`이 1 올라가고 새 타일 집합이 생기며,
**기존 `stamp_reveals`는 삭제되지 않고 이전 버전 기록으로 보존됩니다.**
`image_url` / `complete_message`만 바꾸는 요청은 버전을 올리지 않습니다.

---

## 8. 부스 지급

### 8.1 staff_scan — 스태프가 참여자 QR을 스캔

```
POST /festivals/{id}/booths/{bid}/grants
역할: booth_manager (해당 부스) 또는 operator
```

```json
{ "participant_code": "FF-3A9K2P7Q", "mission_id": 21 }
```

`participant_code`는 QR 스캔 결과 또는 수동 입력 값이며, 서버가 공백 제거·대문자 정규화합니다.

응답 `200`:

```json
{
  "was_already_granted": false,
  "participation": {
    "id": 9001, "mission_id": 21, "booth_id": 7,
    "base_points": 100, "bonus_points": 50, "granted_points": 150,
    "reward_campaign_id": 3,
    "verified_via": "staff_scan",
    "completed_at": "2026-10-10T05:04:00Z"
  },
  "revealed_tile": { "tile_index": 4, "board_version": 1 },
  "board_progress": { "revealed_count": 3, "total_tiles": 9, "is_complete": false }
}
```

**오류**

| 코드 | 상태 | 조건 |
|---|---|---|
| `MISSION_NOT_IN_BOOTH` | 409 | 다른 부스의 미션 지급 시도 |
| `BOOTH_INACTIVE` | 409 | 중지된 부스 |
| `MISSION_INACTIVE` | 409 | 중지된 미션 |
| `NO_TILE_AVAILABLE` | 409 | 지정 공개 방식에서 이 부스 타일을 이미 받음 |
| `PARTICIPANT_NOT_FOUND` | 404 | 미발급 코드 |

중복 요청이면 `200`에 `was_already_granted: true`와 기존 참여·보드 상태를 반환합니다.

### 8.2 부스 QR 토큰 (participant_scan)

```
GET /festivals/{id}/booths/{bid}/scan-token
역할: booth_manager (해당 부스) 또는 operator
```

```json
{
  "booth_id": 7,
  "scan_url": "https://festaflow.kr/join/12/scan?b=7&t=Qm9vdGg3YTlm",
  "window_index": 58201234,
  "expires_at": "2026-10-10T05:04:30Z",
  "refresh_after_seconds": 30
}
```

부스 화면은 30초마다 재호출해 QR을 갱신합니다.
서버는 지급 시 **현재 window와 직전 window**를 모두 인정하므로, 갱신 직전에 스캔해도 실패하지 않습니다.
`qr_secret`은 내려주지 않습니다.

### 8.3 participant_scan — 참여자가 부스 QR을 스캔

```
POST /festivals/{id}/scan-grants
인증: X-Participant-Secret
```

```json
{ "booth_id": 7, "token": "Qm9vdGg3YTlm", "mission_id": 21 }
```

응답 본문은 8.1과 동일하며 `participation.verified_via`가 `participant_scan`입니다.

스캔 직후 미션 선택 화면을 그리기 위한 조회 엔드포인트도 함께 둡니다.

```
GET /festivals/{id}/scan?booth_id=7&token=Qm9vdGg3YTlm
인증: X-Participant-Secret
```

부스 정보와 활성 미션 목록, 각 미션의 지급 여부, 토큰 잔여 시간을 반환합니다.

**오류**

| 코드 | 상태 | 조건 |
|---|---|---|
| `SCAN_TOKEN_EXPIRED` | 410 | 현재·직전 window 어디에도 맞지 않음 |
| `SCAN_TOKEN_INVALID` | 400 | 서명 불일치, 다른 부스의 토큰 |
| `SCAN_ALREADY_USED` | 409 | 같은 부스·window·참여자로 이미 지급 (1 스캔 = 1 미션) |
| `BOOTH_MODE_MISMATCH` | 409 | `verify_mode`가 `staff_scan`인 부스에 스캔 지급 시도 |

`SCAN_TOKEN_EXPIRED`는 참여자 화면에서 "부스 화면의 QR을 다시 스캔해 주세요"로,
`SCAN_ALREADY_USED`는 "이 부스에서 방금 스탬프를 받았습니다"로 표시합니다.

### 8.4 최근 지급

```
GET /festivals/{id}/booths/{bid}/grants/recent?limit=8
```
현재 부스의 완료 참여를 최신순으로 반환합니다.

---

## 9. 참여자

| 메서드 | 경로 | 인증 |
|---|---|---|
| POST | `/festivals/{id}/participants` | 없음 (발급) |
| GET | `/festivals/{id}/participants/me` | `X-Participant-Secret` |
| GET | `/festivals/{id}/stamp-board/me` | `X-Participant-Secret` |
| GET | `/festivals/{id}/public` | 없음 (축제·활성 부스·활성 미션) |

발급 응답 `201`:

```json
{ "code": "FF-3A9K2P7Q", "secret": "s_9f2c...", "festival_id": 12 }
```

`secret`은 이 응답에서만 노출됩니다. 클라이언트는
`localStorage["festaflow-participant-12"] = { code, secret }`로 저장합니다.

`GET /participants/me` 응답에는 미션별 지급 상태(`pending` / `granted`)와
지급된 포인트 합계, 활성 캠페인 안내가 포함됩니다.
`X-Participant-Secret` 없이 보드를 조회하면 공개 조각이 없는 기본 보드가 반환됩니다.

---

## 10. 행사장 설계 (STEP 2)

| 메서드 | 경로 | 역할 | 설명 |
|---|---|---|---|
| GET | `/festivals/{id}/layout` | planner, operator | 존·노드·동선 전체 |
| PUT | `/festivals/{id}/layout` | planner | 전체 저장 (부분 저장 없음) |
| POST | `/festivals/{id}/layout/generate` | planner | 기획서 기반 배치 생성 |
| GET | `/festivals/{id}/layout/checks` | planner | 공간 설계 체크 + 필수 시설 체크 |
| GET | `/festivals/{id}/layout/heatmap?at=19:00` | planner | 시간대별 존 밀도 추정 |
| GET | `/festivals/{id}/layout/resources` | planner | 예산 배치표 + 시간대별 인력 곡선 |
| GET | `/festivals/{id}/layout/snapshots` | planner | 되돌리기 목록 (최근 10개) |
| POST | `/festivals/{id}/layout/restore/{version}` | planner | 특정 버전으로 되돌리기 |

`PUT /layout`은 존·노드·동선을 통째로 받습니다. 캔버스 편집은 수십 개 요소가 동시에
움직이므로 요소별 PATCH는 왕복이 많고 중간 상태가 깨집니다.
저장 시 직전 상태를 스냅샷으로 남깁니다.

`GET /layout/checks` 응답:

```json
{
  "design_checks": [
    { "code": "PATH_BOTTLENECK", "severity": "warning",
      "message": "주동선 1이 예상 통행량을 감당하지 못합니다.",
      "target": { "path_id": 4 }, "detail": { "bottleneck_index": 1.34 } },
    { "code": "EMERGENCY_PATH_NARROW", "severity": "critical",
      "message": "비상 대피 동선 폭이 3m 미만입니다.", "target": { "path_id": 9 } }
  ],
  "facility_checklist": {
    "satisfied": 6, "total": 8,
    "items": [
      { "kind": "ops_center", "label": "운영본부", "required": true, "satisfied": true },
      { "kind": "medical", "label": "의무실", "required": true, "satisfied": false,
        "reason": "일 예상 방문객 3,000명 이상" }
    ]
  },
  "disclaimer": "권장 기준이며 법정 설치 기준이 아닙니다."
}
```

`GET /layout/heatmap` 응답의 모든 값은 시뮬레이션 추정치이며,
`"estimated": true`와 안내 문구를 항상 포함합니다.

---

## 11. 부스 QR 체험 (STEP 2-b)

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/festivals/{id}/booths/{bid}/experience` | operator |
| PUT | `/festivals/{id}/booths/{bid}/experience` | operator |
| GET | `/festivals/{id}/booths/{bid}/experience/results` | operator |
| DELETE | `/participants/me/media/{mid}` | participant (secret) |

`PUT`은 부스 테마(`use_experience`, `experience_theme`)와
소속 미션들의 `experience_type` / `experience_config`를 함께 저장합니다.

**`experience_config`는 응답에서 필터링됩니다.** `quiz`의 `answer_index`는
운영자 응답에만 포함되고 참여자 응답(`GET /scan`)에는 절대 내려가지 않습니다.
채점은 서버에서만 합니다.

참여자 제출은 8.3의 `POST /scan-grants`에 `response`를 실어 보냅니다.

```json
{ "booth_id": 7, "token": "Qm9vdGg3YTlm", "mission_id": 21,
  "response": { "choice_index": 0 } }
```

| 오류 | 상태 | 조건 |
|---|---|---|
| `EXPERIENCE_WRONG_ANSWER` | 422 | 퀴즈 오답. `attempts_left`를 함께 반환 |
| `EXPERIENCE_ATTEMPTS_EXCEEDED` | 429 | 시도 횟수 소진 |
| `EXPERIENCE_CONSENT_REQUIRED` | 422 | 사진 업로드 동의 누락 |
| `EXPERIENCE_DWELL_TOO_SHORT` | 422 | `info` 최소 체류 시간 미달 |

오답이나 시도 소진은 **참여 이력을 만들지 않습니다.** 집계에 섞이지 않게 하기 위함입니다.

---

## 12. 운영·안전·성과 목표 (STEP 3)

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET / PUT | `/festivals/{id}/operations-plan` | planner |
| GET / POST | `/festivals/{id}/safety-risks` | planner |
| PUT / DELETE | `/festivals/{id}/safety-risks/{rid}` | planner |
| GET / PUT | `/festivals/{id}/emergency-contacts` | planner |
| GET / PUT | `/festivals/{id}/kpi-targets` | planner |

`GET /safety-risks` 응답에는 `likelihood × impact`로 계산한 `grade`와,
등급이 높은데 `mitigation`이 비어 있으면 `needs_mitigation: true`가 포함됩니다.

---

## 13. 최종 기획서 (STEP 4)

| 메서드 | 경로 | 역할 | 설명 |
|---|---|---|---|
| GET | `/festivals/{id}/proposal` | planner | 12개 섹션 조립 결과 |
| POST | `/festivals/{id}/proposal/snapshots` | planner | 현재 상태를 버전으로 저장 |
| GET | `/festivals/{id}/proposal/snapshots` | planner | 버전 목록 |
| GET | `/festivals/{id}/proposal/snapshots/{v}` | planner | 특정 버전 |
| GET | `/festivals/{id}/proposal/diff?from=3&to=5` | planner | 버전 간 변경점 |
| GET | `/festivals/{id}/proposal.pdf` | planner | PDF 내보내기 |

`GET /proposal`은 저장된 문서가 아니라 **원본 테이블에서 매번 조립**합니다.
비어 있는 섹션은 생략하지 않고 `"status": "empty"`로 내려주며,
응답에 `completion: { filled: 9, total: 12 }`를 포함합니다.

---

## 14. 실무 검토 반영 엔드포인트

### 14.1 실측 방문객 (E1)

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET / POST | `/festivals/{id}/visitor-counts` | planner, operator |
| DELETE | `/festivals/{id}/visitor-counts/{vid}` | planner |

```json
{ "count_date": "2026-10-10", "visitors": 6200, "source": "manual_counter", "note": "정문+후문 합산" }
```

같은 날짜에 여러 출처가 공존할 수 있습니다. 리포트는 우선순위
(`beacon` > `manual_counter` > `partner` > `estimate`)로 하나를 고르고 나머지는 병기합니다.

### 14.2 참여자 복구 (E5)

```
POST /festivals/{id}/participants/recover
{ "code": "FF-3A9K2P7Q", "phone_last4": "4821" }
```

성공하면 새 `secret`을 발급합니다. 실패는 `429 RECOVERY_ATTEMPTS_EXCEEDED`까지
**코드당 5회**로 제한합니다. 뒷 4자리는 1만 분의 1이라 무제한 시도를 허용하면 뚫립니다.
등록된 복구 정보가 없으면 `404 RECOVERY_NOT_AVAILABLE`.

### 14.3 오프라인 지급 동기화 (E3)

8.1 / 8.3의 지급 요청에 필드가 추가됩니다.

```json
{ "participant_code": "FF-3A9K2P7Q", "mission_id": 21,
  "client_request_id": "0f8b6e5a-...", "queued_at": "2026-10-10T05:04:00Z" }
```

`client_request_id`는 `UNIQUE`라서 재전송이 중복 지급이 되지 않습니다.
이미 처리된 ID면 `200`에 기존 결과와 `was_already_granted: true`를 반환합니다.
**`completed_at`은 `queued_at`으로 기록됩니다** — 통신 복구 시각에 완료가
몰려 보이는 왜곡을 막기 위해서입니다.

큐 일괄 전송용 배치 엔드포인트도 둡니다.

```
POST /festivals/{id}/grants/batch
{ "grants": [ {...}, {...} ] }
→ 200 { "results": [ { "client_request_id": "...", "status": "granted" | "duplicate" | "failed", "error": {...} } ] }
```

부분 실패를 허용합니다. 한 건이 실패해도 나머지는 처리되며,
클라이언트는 실패분만 큐에 남깁니다.

### 14.4 인쇄 QR (E4)

```
GET /festivals/{id}/booths/{bid}/qr.pdf
GET /festivals/{id}/booths/qr.pdf          # 전 부스 일괄
역할: operator
```

부스 고정 서명이 담긴 인쇄용 PDF를 반환합니다. 부스명과 안내 문구가 함께 들어갑니다.
`POST /booths/{bid}/qr/rotate`로 서명을 재발행하면 기존 인쇄물은 무효가 됩니다.

### 14.5 추천 판정 (E7)

```
POST /festivals/{id}/recommendations/feedback
{ "rec_type": "REDISTRIBUTE", "booth_id": 9,
  "observed_at": "2026-10-10T05:00:00Z", "verdict": true }
```

운영자가 추천 카드의 "확인함 / 해당 없음"을 누를 때 호출합니다.
사후 리포트가 적중률로 집계합니다.

### 14.6 진단 표시 모드 (E2)

`GET /diagnoses/latest` 응답에 필드가 추가됩니다.

```json
{
  "display_mode": "checklist",
  "score_disclosed": false,
  "total_score": null,
  "risk": null,
  "items": [
    { "category": "crowd_safety", "fulfillment": "partial",
      "reason": "...", "recommendation": "...", "score": null, "max_score": null }
  ],
  "disclosure_note": "채점표 v1은 아직 과거 축제 데이터로 검증되지 않아 점수를 표시하지 않습니다."
}
```

`display_mode: "score"`일 때만 `total_score` / `risk` / `items[].score`가 채워집니다.
내부 계산과 저장은 두 모드에서 동일하며 **응답에서만 감춥니다.**
`fulfillment`는 `diagnosis_items.level`을 매핑한 값입니다
(`stable` → 충족, `caution` → 부분충족, `risk` → 미충족).

---

## 15. 사후 리포트

```
GET /festivals/{id}/report
역할: planner, operator
```

행사 결과 요약, 계획 대비 참여 신호, 시간대(KST 1시간 버킷) timeline,
부스별·미션별 성과, 모든 캠페인 impact, 규칙 기반 개선안을 포함합니다.

```json
{
  "summary": {
    "unique_participants": 412,
    "total_completions": 1180,
    "avg_completions_per_participant": 2.86,
    "missions_with_completion": { "count": 9, "total": 12, "ratio": 0.75 }
  },
  "plan_vs_actual": {
    "expected_visitors": 18000,
    "festaflow_participants": 412,
    "participation_scale": 0.023,
    "disclaimer": "FestaFlow 미션 서비스의 참여 규모입니다. 실제 축제 방문률이나 전체 방문객 대비 참여율이 아닙니다."
  },
  "timeline": [{ "hour_kst": "2026-10-10T13:00+09:00", "completions": 96 }],
  "booths": [{ "booth_id": 7, "name": "막국수 체험존", "completions": 420, "unique_participants": 300, "share": 0.356, "rank": 1, "peak_hour_kst": "2026-10-10T14:00+09:00", "peak_completions": 71 }],
  "unassigned_completions": 12,
  "improvements": [
    { "rule": "PEAK_HOUR", "message": "14시대에 완료가 집중되었습니다. 다음 행사에서 해당 시간대 운영인력과 대기 동선 강화를 검토하세요." }
  ]
}
```

`unassigned_completions`는 부스 스냅샷이 해제된 참여 수입니다.
전체 완료에는 포함하되 특정 부스에 임의 배정하지 않습니다.
참여 데이터가 0건이어도 계획 KPI, 빈 상태, 데이터 수집 개선안을 반환합니다.

STEP 3에서 성과 목표를 입력했으면 `kpi` 블록이 함께 실립니다.

```json
"kpi": [
  { "metric_key": "qr_participants", "label": "QR 참여자", "target": 500,
    "actual": 412, "achievement": 0.824, "measurable": true, "unit": "명" },
  { "metric_key": "expected_visitors", "label": "목표 방문객", "target": 18000,
    "actual": null, "achievement": null, "measurable": false, "unit": "명",
    "note": "FestaFlow는 방문객 수를 측정하지 않습니다. 참고값입니다." }
]
```

`measurable: false`인 지표는 `achievement`를 계산하지 않습니다.
측정하지 않은 값에 달성률을 붙이면 리포트 전체의 신뢰가 무너집니다.
