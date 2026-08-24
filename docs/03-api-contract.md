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

**봉투는 한 겹입니다.** 라우트를 못 찾은 404, 메서드 불일치 405, Pydantic 검증
실패 422처럼 **우리가 만들지 않은** 오류도 같은 모양으로 나갑니다
(`main.py`의 예외 핸들러 3개). 프레임워크 기본 응답은 `{"detail": ...}`이라
그대로 두면 오류 종류마다 봉투가 달라지고, 화면은 모든 경우를 알고 있어야 합니다.

우리가 만들지 않은 오류의 `code`는 `HTTP_ERROR`이며 `message`는 한국어입니다 —
`message`는 그대로 화면에 노출되므로 여기서만 영어가 새어 나가면 안 됩니다.
`Allow` 같은 응답 헤더는 봉투를 갈아 끼워도 그대로 실립니다.

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
  "invite_path": "/staff/login?f=12&s=45",
  "invite_url": "https://festaflow.kr/staff/login?f=12&s=45",
  "access_code": "8K2QD7"
}
```

**브라우저는 `invite_path` 를 쓰고 자기 오리진을 붙입니다.** `invite_url` 은
`PUBLIC_WEB_ORIGIN` 이 없으면 요청이 도착한 주소(=API 서버)로 만들어져,
프런트가 따로 뜬 환경에서는 `/staff/login` 이 없는 곳을 가리킵니다.
(부스 QR 의 `scan_path` 와 같은 이유입니다 — §8.2.)

**평문 접근 코드는 이 응답에서만 나옵니다.** 저장하는 것은 bcrypt 해시뿐이라
서버도 다시 알아낼 수 없습니다. 잃어버리면 `rotate` 가 유일한 길입니다.

`booth_manager` 는 `booth_id` 가 없으면 발급을 거절합니다 — 부스를 안 정하면
`require_booth_scope` 가 모든 지급을 막아, 발급은 성공했는데 현장에서 아무것도
못 하는 스태프가 됩니다.

`DELETE` 는 **비활성화이지 삭제가 아닙니다.** 행을 지우면 그가 지급한 참여
이력의 `granted_by_staff_id` 가 끊기고, 사후에 "누가 줬는지" 를 말할 수 없습니다.
`reactivate` 로 되돌리고, `unlock` 으로 잠금만 풀 수 있습니다(코드는 그대로).

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
      "status_label": "집중",
      "last_completed_at": "2026-10-10T04:59:12Z"
    }
  ],
  "recommendations": [
    {
      "type": "REDISTRIBUTE",
      "situation": "막국수 체험존에 최근 30분 참여의 49%가 몰렸습니다.",
      "evidence": "같은 시간 15% 이하에 머문 부스 — 지역상점존(8%, 8건), 청년창업존(11%, 11건)",
      "action": "지역상점존 현장이 실제로 한산한지 확인해 주세요. 맞다면 한시 추가 보상을 검토할 수 있습니다.",
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

`status_label`은 **사람이 읽는 상태 이름**입니다. 대개 `status`와 1:1이지만
(데이터 부족 / 여유 / 주의 / 집중), 최근 30분 완료가 0건인 부스만은 `status`가
`LOW`여도 `"참여 없음"`이 나갑니다. 운영자는 "여유"를 보고 "괜찮구나"로 읽고
지나가는데, 그 부스는 한산한 게 아니라 QR이 안 보이거나 인쇄물이 떨어졌을 수
있고 바로 위 추천 카드가 그걸 확인해 달라고 말합니다.
한 화면이 서로 다른 말을 하면 둘 다 신뢰를 잃습니다.

**한산한 부스가 여럿이어도 `REDISTRIBUTE` 카드는 하나입니다.** 같은 상황을
설명하는 카드가 여러 장 뜨면 운영자는 그걸 다 처리하지 못하고, 처리 못 할 카드가
쌓이면 다음부터 카드를 읽지 않습니다. 대신 해당 부스를 `evidence`에 **전부**
적고 `target_booth_id`로 가장 조용한 한 곳을 찍어 줍니다 —
조용히 잘라내면 안 적힌 부스는 아무도 확인하러 가지 않습니다.

부스 이름은 운영자가 쓰는 자유 텍스트라 문구에 조사를 붙이지 않습니다.
`"부스 5은"` 같은 문장이 반드시 섞입니다.

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
클라이언트가 시각을 판정하지 않습니다 — 폰 시계가 틀어진 만큼 배너가 일찍
사라지거나 끝난 캠페인이 계속 떠 있고, 축제장에서 "포인트 두 배라며 왜 안 줘요"가
여기서 나옵니다. 응답의 `is_live`가 그 판정 결과입니다.

**경품 뽑기(§12)와 다른 물건입니다.** 경품은 보드를 완성한 사람에게 주는 실물이고,
캠페인은 특정 부스의 미션 포인트를 정해진 시간 동안만 올리는 장치입니다.
운영 대시보드가 편중을 발견했을 때 쓸 수 있는 개입 수단이 이것뿐입니다 —
경품은 부스별로 조절할 수 있는 물건이 아닙니다.
헷갈리기 쉬워 화면에서는 **"한시 추가 포인트"**라고 부릅니다.

`DELETE`는 **행을 지우지 않고 `is_active=false`로 끕니다.**
`participations.reward_campaign_id`가 이 행을 가리키고 있어, 지우면 어떤 지급에
어떤 캠페인이 붙었는지가 사라지고 개입 효과 분석이 깨집니다.

캠페인을 고치거나 꺼도 **이미 지급된 보너스는 바뀌지 않습니다** — 지급 시점에
`participations.bonus_points`로 스냅샷을 박기 때문입니다. 받은 포인트가 나중에
줄어드는 것만큼 현장에서 설명하기 어려운 일이 없습니다.

캠페인 최대 길이는 **24시간**입니다. 축제 하루보다 길면 "한시"가 아니고, 그건
미션 포인트를 올리는 것과 같습니다 — 그쪽은 미션 편집으로 해야 이력이 남습니다.

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
2건에서 6건이 되면 "200% 증가"가 되는데, 그건 증가가 아니라 잡음입니다.

**before가 0건이면 `completion_change_rate`는 `null`입니다.** 0을 분모로 두고
"무한 증가"나 "100%"를 만들어 내면 그 숫자가 화면에 나가고, 아무도 그게 0에서
시작했다는 걸 모릅니다.

비교 기준은 캠페인 **시작 시각**입니다. 종료 기준으로 잡으면 캠페인 기간 전체가
before에 섞여 들어갑니다. 다른 축제 참여는 집계하지 않습니다 — 전체 완료 수가
분모라 한 건만 새도 비율이 통째로 틀어집니다.

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

응답에는 `scan_path`(오리진 없는 경로)와 `scan_url`(전체 주소)이 함께 옵니다.
**브라우저는 `scan_path` 를 쓰고 자기 오리진을 앞에 붙이세요.** `scan_url` 은
`PUBLIC_WEB_ORIGIN` 이 없으면 요청이 도착한 주소, 즉 **API 서버**로 만들어집니다 —
프런트가 따로 뜬 환경에서는 그 주소에 `/join` 라우트가 없어 QR 이 404 로 갑니다.

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

`quiz`의 `explanation`(해설)도 **참여자 응답에 담기지 않습니다.** 해설은 정답을
설명하는 글이라 사실상 정답이고, 문제와 함께 내리면 풀 필요가 없어집니다.
공개 시점은 서버가 정합니다.

| 상황 | 해설 |
|---|---|
| 맞혔다 | 내려간다 (`GrantResult.explanation`). 악용할 여지가 없다 |
| 틀렸고 시도가 남았다 | **숨긴다.** 거기 정답이 있으면 남은 시도가 공짜가 된다 |
| 틀렸고 시도를 다 썼다 | 내려간다 (오류 `details.explanation`). 더 쓸 시도가 없다 |

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
{ "participant_code": "FF-3A9K2P7Q", "mission_id": 12,
  "client_request_id": "3f2b...", "queued_at": "2026-10-10T05:03:11Z" }
```

`queued_at`은 스태프가 **현장에서 버튼을 누른** 시각입니다. 서버는 이 값을
`completed_at`으로 쓰고 도달 시각을 `synced_at`에 따로 남깁니다. 이 값이 없으면
오프라인에 쌓였던 지급이 전부 통신 복구 시점으로 기록되어, 운영 인사이트의
"최근 30분 편중" 판정과 리포트 시간축이 통째로 왜곡됩니다.

`client_request_id`는 **UUID 형식이어야 하며**(버전은 강제하지 않습니다),
유니크 제약은 **축제 단위**입니다. 전역으로 두면 다른 축제의 같은 키가 500으로
막히고 — 500은 큐가 재시도하는 응답이라 그 항목이 큐 앞에서 영원히 돕니다 —
조회에 스코프가 없으면 남의 축제 지급 기록이 `was_already_granted: true`와 함께
포인트·미션·부스·완료 시각까지 실려 돌아갑니다.

**보너스는 `queued_at` 기준으로 계산합니다.** 도달 시각으로 찾으면 통신이
끊겼다는 이유만으로 참여자가 보너스를 잃습니다 — 14시 50분에 "지금 두 배"를 보고
미션을 했는데 큐가 15시 10분에 풀리면 캠페인이 이미 끝나 있습니다. `completed_at`도
같은 값이므로, 이렇게 해야 리포트의 캠페인 전후 분석에 "캠페인 창 안의 완료인데
보너스가 0"인 행이 남지 않습니다.

**이미 지급된 건은 활성 검사보다 먼저 답합니다.** 재전송 사이에 운영자가 부스를
중지하면, 이미 지급이 끝난 건이 `BOOTH_INACTIVE`로 거절되어 스태프 화면에는
"보내지 못했다"로 뜹니다. 그 상태의 진실은 실패가 아니라 성공입니다 — 지급은
일어난 시점에 일어난 것이고, 나중에 부스를 닫았다고 없던 일이 되지 않습니다.

**`queued_at`은 클라이언트가 정하는 시각이라 그대로 믿지 않습니다.**
`[now - 24h, now + 2분]` 밖이면 **조용히 버리고** 서버 시각을 씁니다.
버릴 때는 **경고 로그를 남깁니다** — 버리면 `queued_at`도 `synced_at`도 비어
그 지급이 온라인 지급과 구분되지 않고, 부스 폰 시계가 3분만 빨라도 그 부스의
오프라인 흔적이 통째로 사라집니다. 거부하지 않는 이유는 지급 자체가 반드시
성공해야 하기 때문입니다 — 오프라인
우선 지급의 요점은 현장에서 줄이 멈추지 않는 것이고, 폰 시계가 틀렸다고
스탬프를 못 주면 그 요점이 사라집니다. 앞쪽 여유 2분은 실제로 흔한 시계 오차를
위한 것이고, 뒤쪽 24시간은 축제 하루가 끝나면 그 큐가 의미를 잃기 때문입니다.

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

### 14.4b 공결 확인서 (E9)

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/festivals/{id}/lectures/{sid}/certificate` | 참여자 (본인) |
| GET | `/festivals/{id}/attendance-certificates/{code}` | **인증 없음** |

```json
{ "session_id": 4, "title": "생성형 AI 실무 특강",
  "code": "onMeSEFCthdwzRfC", "verify_path": "/verify/16/onMeSEFCthdwzRfC" }
```

**공결을 인정하는 사람은 특강 주최자가 아니라 그 시간 정규 수업 담당 교수입니다.**
수십 명에게 계정을 나눠 주는 절차는 만들어도 쓰이지 않습니다. 대신 학생이 스스로
증명을 건네고, 코드가 그 증명의 진위를 담보합니다. 그래서 확인 경로에 인증이
없습니다 — **코드 자체가 비밀입니다.**

코드는 `base64url(HMAC_SHA256(session.qr_secret, "cert|{session_id}|{participant_id}"))[0:16]`
입니다. 부스 토큰·체크인 토큰과 메시지 접두어가 달라 서로를 대신 쓸 수 없고,
학번이나 id 에서 유도되지 않아 남의 것을 추측할 수 없습니다.

**테이블에 저장하지 않습니다.** 확인서를 스냅샷으로 저장하면 나중에 출결이
정정됐을 때 종이만 옛 사실을 말합니다. 이 코드는 기록이 아니라 **가리키는
손가락**이라, 확인 페이지가 언제나 지금의 출결을 읽습니다. 폐기 절차도 필요
없습니다.

응답의 `student_no_masked`는 **뒷 세 자리만** 담습니다. 교수는 "이 학생이
왔는가"를 확인하려는 것이지 명단을 수집하려는 것이 아닙니다. 체크인 기록이
하나도 없으면 `409 NO_ATTENDANCE`입니다 — "안 왔다"를 증명하는 종이는
확인서가 아닙니다. 코드가 틀리면 `404`이며, 형식 오류와 구분하지 않습니다.

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

## 14.7 현장 공지 (E8)

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/festivals/{id}/announcements/live` | 누구나 (참여자 secret 선택) |
| POST | `/festivals/{id}/announcements/{aid}/ack` | 참여자 |
| GET | `/festivals/{id}/announcements/staff-live` | 스태프 |
| POST | `/festivals/{id}/announcements/{aid}/staff-ack` | 스태프 |
| GET / POST | `/festivals/{id}/announcements` | operator |
| PUT / DELETE | `/festivals/{id}/announcements/{aid}` | operator |

```json
{ "channel": "both", "level": "urgent",
  "title": "우천으로 야외 부스가 중단됐습니다",
  "body": "실내 전시장으로 이동해 주세요.", "ends_at": null }
```

**관객 경로는 `channel`을 파라미터로 받지 않습니다.** 받는 순간 그 값은 요청자가
정하는 값이 되고, `?channel=staff` 한 번으로 내부 전달("현금 정산 30분 뒤")이
관객 화면에 뜹니다. 경계를 파라미터가 아니라 **경로**로 만든 이유입니다.

**관객 경로는 인증을 요구하지 않습니다.** 참여 코드를 아직 못 받은 사람도 우천
중단 공지는 봐야 합니다 — 안내를 받으려면 먼저 등록하라고 요구하는 순간, 그
안내는 가장 필요한 사람에게 닿지 않습니다. secret이 실려 오면 확인 여부(`acked`)
까지 함께 내려주고, 틀린 secret은 401이 아니라 조용히 무시합니다.

`level: urgent`는 화면을 덮고 확인을 받습니다. `ack`는 두 가지 일을 합니다 —
확인한 사람에게 덮개를 다시 씌우지 않고, 운영자에게 **몇 명이 봤는지** 알려줍니다.
띄운 것과 전달된 것은 다릅니다. 일반 공지에 `ack`를 보내면 `409 NOT_URGENT`입니다 —
조용히 받아 주면 확인 수가 부풀어 긴급 공지의 도달률을 읽을 수 없게 됩니다.

**문구·등급·대상이 바뀌면 확인 기록이 지워집니다.** "야외 부스 중단"을 확인한
사람에게 "행사 전체 종료"로 바뀐 같은 공지가 안 뜨면, 그 사람은 바뀐 내용을
영영 못 봅니다. 기간만 연장하는 것은 확인을 지우지 않습니다.

`ends_at: null`이면 운영자가 내릴 때까지 떠 있습니다. 종료 시각을 필수로 하면
운영자는 "일단 3시간" 같은 임의의 값을 넣게 되고, 그 시각이 지나면 비가 그대로인데
공지만 사라집니다. `DELETE`는 내리는 것이지 지우는 것이 아닙니다 — 무엇을 언제
띄웠고 몇 명이 봤는지가 사후에 답해야 하는 질문입니다.

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

**측정 가능 여부는 운영자가 정하지 않습니다.** `PUT /kpi-targets`가 `is_measurable`을
받지 않고 `metric_key`로부터 서버가 정합니다. 체크 하나로 달성률을 켤 수 있게 두면
반드시 켜지고, 그 순간 QR 참여자 수가 방문객 수로 둔갑합니다.
같은 이유로 기본 지표의 `label`과 `unit`도 서버가 덮어씁니다 — 라벨이 제각각이면
축제 간 비교가 안 됩니다. 사용자 정의 지표는 `custom:` 접두어가 필요하며
FestaFlow가 집계할 수 없으므로 항상 `measurable: false`입니다.

목표는 축제당 지표당 하나라 **PUT upsert**입니다. POST로 두면 목표를 고치려던
운영자가 409를 보고, 리포트에는 같은 줄이 두 개 뜹니다.

`visitor_basis`는 실측(`visitor_counts`)이 있을 때만 실립니다. 없으면 `null`이며
참여율을 만들어 내지 않습니다. 실측이 들어오면 `expected_visitors` 목표가 그때부터
`measurable: true`가 되고 달성률을 갖습니다.

```json
"visitor_basis": {
  "visitors": 5200, "source": "manual_counter", "source_label": "입구 계수기",
  "caveat": null, "participation_rate": 0.0348,
  "others": [{ "source_label": "주최측 추산", "visitors": 9000 }]
}
```

날짜별로 우선순위가 높은 출처 하나씩만 더합니다 — 단순 합계를 쓰면 같은 날 두 출처가
들어온 만큼 방문객이 두 배가 됩니다. 고른 것들 중 **가장 신뢰도가 낮은** 출처가
대표가 됩니다. 하루는 센서, 하루는 추산으로 채웠다면 합계 전체를 센서 수치라고
부를 수 없습니다. `estimate`가 대표면 `caveat: "주최측 추산 기준"`이 붙습니다.

`timeline`과 `peak_hour_kst`는 **KST 고정**입니다. 서버가 UTC로 돌아도
"14시대에 몰렸다"는 현장 사람의 시계로 읽혀야 합니다.

---

## 12. 경품 뽑기 (조각 보드 완성 보상)

조각 보드를 완성한 참여자가 **축제당 한 번** 돌립니다.
설계 05 §3 이 룰렛을 v2 로 미룬 이유(보너스 포인트가 보상 캠페인과 겹침)를
**포인트가 아니라 실물 경품을 주는 것**으로 해소했습니다. 미션 지급 경로를
건드리지 않으므로 참여 이력·포인트 집계·중복 지급 방지가 그대로 남습니다.

### 12.1 운영자

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/festivals/{id}/prizes` | operator |
| POST | `/festivals/{id}/prizes` | operator |
| PUT | `/festivals/{id}/prizes/{pid}` | operator |
| POST | `/festivals/{id}/prizes/{pid}/archive` | operator |
| GET | `/festivals/{id}/prize-draws` | operator |
| GET | `/festivals/{id}/prize-draws/lookup?code=FF-XXXXXXXX` | operator |
| POST | `/festivals/{id}/prize-draws/{did}/claim` | operator |

```json
{ "name": "막국수 쿠폰", "description": null,
  "stock": 20, "weight": 10, "is_blank": false, "is_active": true }
```

`stock: null` 은 **무제한**입니다. 꽝(`is_blank: true`)은 반드시 무제한이어야 합니다 —
재고가 떨어지면 아무도 뽑을 수 없는 상태가 되기 때문입니다.

`weight` 는 확률(%)이 아니라 **상대 가중치**입니다. 확률로 받으면 합이 100 이
되도록 운영자가 맞춰야 하고, 상품 하나를 중지하는 순간 합이 100 이 아니게 됩니다.
가중치는 그때그때 뽑을 수 있는 후보들 사이에서 정규화됩니다.

`GET /prizes` 는 `drawable_count` 와 `warnings` 를 함께 반환합니다
(`NO_DRAWABLE_PRIZE`, `NO_BLANK_PRIZE`, `ALL_STOCK_FINITE`).
당일에 "아무도 못 뽑는 상태"를 발견하면 늦습니다.

삭제는 **아카이브만** 합니다. 지우면 이미 당첨된 사람의 화면이 빈칸이 됩니다.

### 12.2 참여자

```
GET  /festivals/{id}/prize-draw/me    인증: X-Participant-Secret
POST /festivals/{id}/prize-draw       인증: X-Participant-Secret
```

`GET` 은 화면이 카드를 그리는 데 필요한 전부를 줍니다.

```json
{ "enabled": true, "can_draw": false, "revealed_count": 4, "total_tiles": 6,
  "is_complete": false, "draw": null,
  "prizes": [{ "name": "막국수 쿠폰", "description": null, "is_blank": false }] }
```

**참여자 응답에 `stock` 과 `weight` 는 담기지 않습니다.** 남은 재고가 보이면
언제 뽑을지를 재는 사람이 생기고, 그 순간 추첨이 아니게 됩니다.

`POST` 결과입니다. 이미 뽑은 참여자가 다시 호출하면 **새로 뽑지 않고** 기존 결과를
그대로 돌려줍니다(`uq_prize_draws_participant`).

```json
{ "id": 12, "drawn_at": "...", "prize_name": "막국수 쿠폰",
  "prize_description": null, "is_blank": false, "claimed_at": null }
```

`prize_name: null` 은 **뽑을 수 있는 상품이 하나도 없었다**는 뜻이며 꽝과 다릅니다.
꽝은 운영자가 의도한 결과이고, 이쪽은 운영이 손봐야 할 상태라 구분해 기록합니다.

**오류**

| 코드 | 상태 | 조건 |
|---|---|---|
| `DRAW_NOT_ELIGIBLE` | 409 | 조각 보드를 아직 완성하지 않음. 진행 수치를 함께 반환 |
| `DRAW_NOT_CLAIMABLE` | 409 | 꽝에 수령 확인을 시도 |

재고는 읽고-쓰지 않고 **조건부 UPDATE 한 번**으로 차감합니다. 0행이면 방금 다른
사람이 가져간 것으로 보고 남은 후보로 다시 뽑습니다. 조건문으로 확인하고 차감하면
재고 1개를 두 사람이 동시에 가져갑니다.

수령 확인은 **스태프만** 찍습니다. 참여자가 스스로 찍으면 확인이 아닙니다.
`unclaimed` 집계에 꽝은 세지 않습니다 — 건넬 실물이 없습니다.

### 12.3 체험 부스의 QR 유효 시간

부스에 `quiz` 또는 `info` 미션이 하나라도 있으면 서버가 인정하는 window 수가
기본 2 에서 **5** 로 늘어납니다(30초 × 5 = 2분 30초).

기본값 2 는 도착 확인용이라 실질 30~60초입니다. 퀴즈는 그 안에 끝나지 않습니다 —
문제를 읽고, 보기를 고르고, 틀리면 힌트를 보고 다시 풉니다. 시도 3번을 허용해 놓고
예산을 60초로 두면 참여자는 "정답을 아는데 만료됐다"는 상태에 갇힙니다.

예산은 **미션이 아니라 부스 단위**입니다. 미션마다 다르면 `GET /scan` 이 카운트다운에
무엇을 실을지 정할 수 없습니다 — 참여자가 아직 미션을 고르기 전이기 때문입니다.
화면이 세는 시간과 서버가 받아주는 시간이 다르면 둘 중 하나는 반드시 거짓말이 됩니다.


### 12.4 진행 보드의 표현 (`board_style`)

`stamp_boards.board_style` 은 같은 타일을 어떻게 보여줄지만 정합니다.

| 값 | 화면 |
|---|---|
| `grid` | 그림 한 장을 격자로 쪼갠 퍼즐. 다 모으면 그림이 완성된다 |
| `trail` | 점선으로 이어진 스탬프 랠리 지도. 그림은 쓰지 않는다 |

**구조가 아니라 표현입니다.** `rows`·`cols`·`reveal_mode`·`grant_unit` 과 달리
타일 수도 배정도 공개 기록도 달라지지 않으므로, `PUT /stamp-board` 에서
`board_style` 만 바꾸면 **버전이 오르지 않고 참여자의 수집 진행이 유지됩니다.**

이 값을 구조 변경으로 취급하면 표현을 바꿀 때마다 참여자 전원의 수집이
초기화됩니다 — 축제 당일에 일어나면 되돌릴 수 없습니다.


### 12.5 경품 수령 — 코드로 찾아 건넨다

당첨된 관객이 참여 코드를 보여주면 스태프가 그것으로 찾아 실물을 건네고 확인을
찍습니다. 당첨자 목록을 훑어 찾는 방식은 현장에서 쓸 수 없습니다 — 줄이 서 있고,
당첨자가 수백 명이면 그 방식은 멈춥니다.

```
GET /festivals/{id}/prize-draws/lookup?code=FF-XXXXXXXX
```

```json
{ "participant_code": "FF-ZC5C4Y8S", "claimable": true, "reason": null,
  "draw": { "id": 12, "prize_name": "아이폰", "is_blank": false,
            "drawn_at": "...", "claimed_at": null } }
```

**건넬 수 없는 경우를 오류로 만들지 않습니다.** 꽝·기수령·미뽑기는 전부 스태프가
읽고 안내해야 하는 사실입니다. 404 로 뭉개면 화면이 "없는 코드"와 "꽝을 뽑은
사람"을 구분하지 못합니다.

| 상황 | 응답 |
|---|---|
| 건넬 수 있다 | `claimable: true` |
| 꽝 | `claimable: false`, `reason: "꽝입니다…"`, `draw.is_blank: true` |
| 이미 수령 | `claimable: false`, `draw.claimed_at` 있음 |
| 아직 안 뽑음 | `claimable: false`, `draw: null` |
| 없는 코드 | 404 `PARTICIPANT_NOT_FOUND` |

코드는 사람이 손으로 옮겨 적습니다. 공백·대소문자는 서버가 흡수합니다 —
참여 코드 알파벳에서 `0`·`O`·`1`·`I` 를 뺀 것과 같은 이유입니다.

`POST /prize-draws/{did}/claim` 은 **멱등합니다.** 두 번 눌러도 수령 시각이
덮이지 않습니다 — 언제 건넸는지가 흔들리면 정산이 흔들립니다.

> 참여 코드는 부스에서 남에게 보이는 값입니다. 옆 사람이 코드를 외워 먼저
> 창구에 가면 남의 경품을 받아 갈 수 있습니다. 실물을 건네는 사람이 눈앞의
> 관객을 확인하는 것이 마지막 방어선이며, 추첨권을 손에 쥔 사람에게 주는
> 통상적인 경품 운영과 같은 수준입니다. 더 강한 보장이 필요하면 참여자
> 비밀에서 파생한 일회용 수령 토큰이 필요합니다.


---

## 15. 기관 계정 (로그인 · 회원가입)

**지금까지 기획자에게는 자격증명이 없었습니다.** §1 의 로그인은 축제별 스태프용이라
`festival_id` 를 요구하는데, 축제 목록·생성은 축제가 생기기 전에 호출됩니다.
그래서 그 경로들이 `X-Organization-Id` 헤더 폴백에 기대고 있었고, 그 폴백은
**헤더 하나만 바꾸면 남의 기관이 열리는 구멍**입니다.

| 메서드 | 경로 | 인증 |
|---|---|---|
| POST | `/auth/signup` | 없음 — 기관과 첫 계정을 만든다 |
| POST | `/auth/login` | 없음 |
| POST | `/auth/logout` | 없음 (쿠키를 지운다) |
| GET | `/auth/me` | 세션 |
| POST | `/auth/password` | 세션 |

### 15.1 세션은 httpOnly 쿠키다

**응답 본문에 토큰이 없습니다.** 화면이 손에 쥘 수 없어야 XSS 로도 새지 않습니다.

| 속성 | 값 | 이유 |
|---|---|---|
| `HttpOnly` | 켬 | 스크립트가 읽을 수 없다. localStorage 는 XSS 한 번에 털린다 |
| `SameSite` | `strict` | 외부 사이트에서 온 요청에 실리지 않는다 — CSRF 가 구조적으로 막힌다 |
| `Secure` | 배포에서 켬 | 로컬은 http 라 켜면 저장조차 되지 않아 설정으로 뺐다 |
| `Path` | `/` | API 와 화면이 같은 오리진이다 |

`SameSite=strict` 가 CSRF 를 막으므로 **별도 CSRF 토큰을 두지 않습니다.**

스태프 로그인(§1)도 같은 쿠키를 함께 내려줍니다. 본문의 `access_token` 은
브라우저가 아닌 클라이언트(부스 태블릿 앱·스크립트)를 위해 남깁니다.

### 15.2 두 종류의 세션은 서로를 대신하지 못한다

기관 토큰과 스태프 토큰은 같은 키로 서명됩니다. 종류를 구분하지 않으면 기관
토큰이 스태프 자리에 들어가고 `festival_id` 검사가 통째로 무너집니다. 그래서
JWT 에 `typ`(`org` / `staff`)을 박고 각 디코더가 그것을 검사합니다.

### 15.3 비밀번호

**bcrypt-sha256** 입니다. bcrypt 는 72바이트를 넘는 입력을 조용히 자르는데,
UTF-8 한글은 글자당 3바이트라 24자면 한계에 닿습니다. 자르면 긴 비밀번호가 짧은
것과 같은 해시를 갖고, 사용자는 뒤쪽이 무시되는 줄 모릅니다. sha256 으로 먼저
줄이면 길이와 무관하게 44바이트가 됩니다.

정책은 **길이로** 갑니다(10자 이상). 대문자·숫자·기호를 강제하면 사람들은
`Password1!` 을 만들고 그건 길고 무작위한 것보다 훨씬 약합니다. 대신 거절합니다 —
유출 목록 상위 값, 이메일 아이디나 기관명이 그대로 들어간 값, 글자 종류가 5개
미만인 값.

### 15.4 실패와 잠금

로그인 실패는 **이메일이 없는 것과 비밀번호가 틀린 것을 구분하지 않습니다**
(`INVALID_CREDENTIALS`). 없는 이메일에도 해시 한 번 값의 시간을 씁니다 —
응답 시간만 재도 가입 여부가 드러나면 유출 목록으로 훑는 공격의 첫 단계가
공짜가 됩니다.

연속 실패가 `LOGIN_MAX_ATTEMPTS` 에 닿으면 `LOGIN_LOCK_MINUTES` 분 잠깁니다.
잠긴 동안은 **맞는 비밀번호도** 받지 않습니다.

가입에서만 예외적으로 중복 이메일을 알려줍니다(`EMAIL_TAKEN`) — 감추면 "왜
가입이 안 되는지" 를 알 수 없어 지원 요청이 되고, 그 답이 결국 같은 사실을
알려줍니다.

### 15.5 비밀번호를 바꾸면 기존 세션이 전부 끊긴다

바꾸는 이유가 유출이면, 옛 세션이 살아 있는 한 바꾼 의미가 없습니다.
`password_changed_at` 보다 먼저 발급된 토큰은 `SESSION_REVOKED` 로 거절합니다.
(JWT `iat` 는 정수 초라 비교도 초 단위로 자릅니다 — 그러지 않으면 방금 발급한
세션이 같은 초 안에서 취소됩니다.)


### 15.6 비밀번호 재설정

```
POST /auth/password/reset-request   { email }        → 200 (언제나 같은 응답)
POST /auth/password/reset           { token, new_password } → 204
```

**요청은 가입 여부와 무관하게 같은 응답을 냅니다.** 응답이 갈리면 이 화면이 곧
"이 이메일이 가입돼 있나" 를 확인해 주는 도구가 됩니다.

**링크는 응답에 담기지 않습니다.** 담기면 남의 이메일을 넣은 사람이 그대로 계정을
가져갑니다.

표는 sha256 해시로만 저장합니다 — 서버가 만든 32바이트 난수라 전수 대입이
불가능하므로 느린 해시가 필요 없습니다(느린 해시는 저엔트로피 값 전용).
**유효 30분, 한 번 쓰면 죽고, 새로 요청하면 옛 표가 함께 죽습니다.** 링크는
메일함에 남고 메일함은 종종 남에게 열려 있습니다.

없는 표·쓴 표·만료된 표를 구분하지 않습니다(`RESET_TOKEN_INVALID`) — 구분하면
표를 훑어 "유효한 것이 있는가" 를 물어볼 수 있습니다.

재설정도 비밀번호 변경이라 **기존 세션이 전부 끊깁니다**(§15.5).

> 🚨 **메일 발송기가 아직 없습니다.** `services/mailer.py` 가 자리를 잡고 있고,
> `APP_ENV=local` 에서는 링크를 서버 로그에 찍습니다. 그 밖의 환경에서는
> **보내지 못했다는 사실을 에러 로그로 남깁니다** — 조용히 성공한 척하면
> 운영자는 메일이 갔다고 믿고 사용자는 영원히 기다립니다. SMTP 또는 메일
> 제공자를 붙이기 전까지 이 기능은 운영에서 동작하지 않습니다.
