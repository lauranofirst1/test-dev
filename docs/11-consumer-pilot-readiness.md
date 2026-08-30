# FestaFlow Consumer V1 — 제품 QA와 파일럿 준비도

검증 기준일: 2026-08-30 (Asia/Seoul)

## 최종 판정

> **NOT PILOT READY — V1 기술 후보는 완성됐지만, 실제 휴대폰과 실제 사용자로 통과해야 할 출시 게이트가 남아 있다.**

코어 여정, 서버 트랜잭션, 360/390/430px 레이아웃, 현실적인 데모 데이터와 운영자
리포트는 연결해 검증했다. 다만 헤드리스 Chrome에는 실제 카메라가 없으므로
`카메라 권한 → 실제 QR 인식 → 서명된 링크 → 완료`를 물리 기기에서 증명하지 못했다.
소프트 키보드와 safe-area도 실제 기기에서 확인하지 못했고, 5–10명 참여자 및 1–3명
운영자 테스트는 아직 실행 전이다. 개인정보 보존·삭제 안내와 학번 기반 재발급 정책도
실제 행사 운영자가 확정해야 한다.

| 게이트 | 현재 증거 | 판정 |
|---|---|---|
| 코어 참가자 루프 | 발급부터 Favorite Memory와 리포트까지 실제 API·DB를 사용한 브라우저 여정 | 통과 |
| 트랜잭션 계약 | API 전체 테스트 491개 통과, DB 테스트 skip 없음 | 통과 |
| 모바일 레이아웃 | 360/390/430px에서 `innerWidth = clientWidth = scrollWidth`, 핵심 조작 44px 이상 | 통과 |
| 서명 QR | 인쇄 QR 서명과 특강 체크인 서명을 실제 서버가 검증 | 통과 |
| 실제 참가자 카메라 | 헤드리스 환경은 미지원 fallback만 검증; 실제 렌즈·권한은 미검증 | **미통과** |
| 실제 기기 입력 | 학생번호 소프트 키보드, iOS/Android safe-area 미검증 | **미통과** |
| 사람 대상 사용성 | 테스트 키트만 준비, 참여자·운영자 세션 미실행 | **미통과** |
| 파일럿 개인정보 운영 | 최소 안내는 화면에 추가, 보존·삭제·법률 문구는 미확정 | **미통과** |
| 배포 환경 | 로컬 통합 검증 완료, production HTTPS/cookie/CORS와 현장 Wi-Fi 미검증 | **미통과** |

이 판정은 빌드 품질이 낮다는 뜻이 아니다. 현재 결과는 **실기기 파일럿 리허설에 올릴
수 있는 기술 후보**라는 뜻이다. 아래 종료 게이트를 통과한 뒤에만 `PILOT READY`로 바꾼다.

## 1. Post-build audit

2026-08-27의 cold-start audit가 지적한 핵심 문제는 390px 가로 잘림, 동작하지 않는
참가자 스캐너, 끊긴 설문 계약, DB 테스트 대량 skip이었다. 이번 검증에서는 해당
코드를 다시 읽고 전체 여정을 연결해 실행했다.

| 분류 | 감사 결과 |
|---|---|
| IMPLEMENTED AS INTENDED | ARRIVE/NOW/Explore/Detail/My Flow/REMEMBER, source adapter, Verified Moment, 기기 로컬 Personal Moment, 명시적 Favorite, Experience Open, 실제 집계 기반 Experience Insights |
| PARTIALLY IMPLEMENTED | 앱 내 카메라 스캐너와 기본 카메라/붙여넣기 fallback은 구현됐으나 실제 기기 권한은 미검증. participant 복원은 같은 브라우저에는 동작하지만 다중 기기 복구는 없음. 개인정보 설명은 최소 안내만 존재 |
| INCORRECT / PRODUCT MISMATCH — FIXED | 종료일을 지난 `live` 상태가 NOW를 보이던 문제, 종료 후 live 탭·공지 노출, 첫 특강 체크인을 출석 완료처럼 말하던 문구, Favorite 대상을 바꿔도 이전 사유가 남던 문제, 포인트가 Moment보다 앞서던 일부 성공 피드백 |
| TECHNICALLY BROKEN — FIXED | `survey`가 Stamp UI로 떨어져 응답 없이 422가 나던 경로, 성공 후 Flow/출결/투표 캐시가 즉시 갱신되지 않던 경로, 막힌 localStorage에서 participant 상태가 사라지던 경로, 완료 시각이 없는 Flow 항목 |
| NOT IMPLEMENTED | 사진 Experience, participant 전체 오프라인 처리, 실제 군중·대기시간·GPS 측정, production 배포 자동화 |
| INTENTIONALLY DEFERRED | AI 추천, 지도/Place 시스템, push, social/friend, 서버 기반 Personal Flow, 다중 기기 복구, 복잡한 개인화 |

### V1에서 고친 내용

| 영역 | 변경 |
|---|---|
| 생명주기 | 종료일 이후에는 stale `live/planning` 값보다 실제 날짜를 우선하고, `closed`는 즉시 REMEMBER로 전환 |
| 내비게이션 | LIVE는 지금/둘러보기/나의 Flow, ENDED는 기억/나의 Flow만 노출 |
| 관심 측정 | 상세 재진입은 의미 있는 Open으로 기록하되 StrictMode의 즉시 중복 호출은 억제 |
| 스캔 | 카메라 미지원 시 기본 카메라 또는 전체 링크 붙여넣기 안내, 서명·query를 재구성하지 않고 보존 |
| 설문 | rating/choice 문항을 모두 응답해야 제출되며 서버 계약에 맞는 정수 배열을 전송 |
| 후속 상태 | 미션·특강·전시 성공 직후 관련 Query를 무효화해 Flow와 출결·투표 상태를 즉시 갱신 |
| 성공 피드백 | 올바른 Experience 제목과 DB 완료 시각을 표시하고, 다음 미션을 강제하지 않음 |
| 특강 | 첫 체크포인트는 “체크인이 기록됐어요”, 실제 출석 조건 충족 때만 완료 의미를 표시 |
| 전시 | 투표한 작품명을 넣어 “My Flow에 … 순간이 남았어요”로 안내 |
| Flow | 미션·특강·전시의 실제 완료/체크인/투표 시각을 사용 |
| Favorite | 대상을 바꾸면 이전 reason/comment를 초기화하고, 선택 상태를 `aria-pressed`로 노출 |
| 개인정보 | Open·확인 행동은 집계, Personal Moment는 기기 로컬, Favorite은 명시 제출이라는 짧은 설명 추가 |
| 모바일 | Consumer 링크·태그·선택 조작을 최소 44px로 맞추고 좁은 화면 overflow 제거 |
| 공유 | Experience는 source identity를 포함한 딥링크, Flow/REMEMBER는 요약+Flow 링크를 공유하며 Web Share 실패 시 복사·수동 복사로 복구 |
| 데모 | 12개 Experience와 Open/Favorite 데이터, LIVE/ENDED 전환 도구를 현실적인 SW Week seed에 추가 |

## 2. End-to-end validation

### 하나로 연결한 실제 여정

아래는 정적 성공 화면이 아니라 로컬 FastAPI/PostgreSQL, Vite, 격리된 Chrome 프로필을
사용했다. 참가자 secret, 서명 검증, 완료·투표·Favorite 저장과 리포트 집계는 실제
API와 DB를 거쳤다.

| 단계 | 검증한 행동 | 결과 |
|---:|---|---|
| 1–3 | `/join/{id}` 진입 → 실제 미리보기 확인 → 새 학번 participant 발급 | 성공 |
| 4–5 | 빈 NOW → 진행 중 특강과 짧은 Experience 확인 | 성공 |
| 6–7 | Explore 렌즈/검색 → 미션·특강·전시·불완전 메타데이터 상세 확인 | 없는 duration/location은 숨기고 실제 정보만 표시 |
| 8–10 | 서버가 만든 인쇄 QR 서명으로 설문/안내 미션 수행 → grant 트랜잭션 → “하나의 순간이 남았어요” | 성공 |
| 11 | 성공 직후 My Flow에서 실제 완료 시각 확인 | 성공 |
| 12–13 | 아직 검증하지 않은 동아리 발표를 Personal Moment로 직접 저장 | localStorage에만 저장, 포인트 `20 → 20`으로 불변 |
| 14–15 | 새 페이지로 재진입 | NOW에 Verified 1개 + Personal 1개, “2개의 순간이 남았어요” 표시 |
| 16–18 | seed를 ENDED로 좁게 전환 → REMEMBER → Favorite과 사유 명시 제출 → 재열기 | 성공; 360/390/430px에서 선택 유지 |
| 19 | 운영자 실제 로그인 → `/festivals/{id}/report` | Experience 12행, Open/Discovery/Verified/Favorite가 별도 열로 표시 |

마지막 리포트에서 `동아리 번개 발표 듣기` 행은 실제 QA 이후 Open 18, 고유 열람자
17, 확인 참여 16, 완료 16, Favorite 1을 표시했다. 이 숫자는 물리 방문객이나 혼잡도가
아니며, 화면에도 “열람은 관심 신호일 뿐 참여 완료가 아니다”라는 해석 제한이 붙는다.

### 실제 행동과 실패 상태

| 경로 | 브라우저/API 증거 | 상태 |
|---|---|---|
| 참가자 인쇄 QR | booth id와 서버 HMAC 서명을 가진 전체 URL로 안내·설문 완료 | 통과 |
| 참가자 회전 QR 계약 | 토큰 시간 창·만료·위조·한 스캔 한 지급을 API 테스트 | 통과 |
| 스태프 지급 | participant-scan과 분리된 역할/부스 범위 및 중복 방지를 API 테스트 | 통과 |
| 설문 | choice 선택, `answers` 제출, 완료와 Flow 반영 | 통과 |
| 특강 | 실제 서명 checkpoint 첫 체크인, 중복·필요 체크포인트 수·완료 시각 | 통과 |
| 전시 | 실제 작품 투표, 중복/취소/한도 계약, Flow 시각 | 통과 |
| invalid QR | 브라우저에서 “이 QR로는 지급할 수 없습니다”와 서버 메시지 | 통과 |
| expired QR | API 계약과 오류 코드 | 통과; 브라우저 실시간 만료 대기는 별도 리허설 권장 |
| 네트워크 오류 | `scan-grants` 요청 차단 → 한국어 오류 → 같은 선택으로 재시도 성공 | 통과 |
| scanner 미지원 | headless Chrome에서 기본 카메라/링크 붙여넣기 fallback | 통과 |
| 카메라 권한 거부 | 물리 카메라 환경이 없어 실행하지 못함 | **실기기 게이트** |

### 자동 검증

```text
API pytest             491 passed, 0 skipped, 2 warnings
Alembic current/head   3f2a9c7d1e04
Alembic check          No new upgrade operations detected
Web typecheck          passed
Web production build   passed (existing >500 kB chunk warning)
Web share node:test    8 passed
git diff --check       whitespace error 없음
```

경고 2건은 Starlette TestClient의 httpx 전환 안내와 다른 비밀키 서명을 거부하는
테스트가 의도적으로 짧은 외부 키를 만드는 경고다. 실패나 skip은 아니다.

추가된 API 여정 테스트는 공개 행사 조회 → participant 발급 → Detail Open → 실제 서명
인쇄 QR context → grant → participant/me → Favorite → organizer Experience Insights를
한 테스트로 연결한다.

## 3. Mobile validation

Chrome DevTools device metrics로 실제 DOM 크기와 조작 영역을 측정했다. 모든 표의
`문서 폭`은 `innerWidth = clientWidth = scrollWidth`였다.

| 폭 | 확인 화면 | 문서 폭 | 최소 보이는 조작 영역 | 결과 |
|---:|---|---:|---:|---|
| 360px | ARRIVE, NOW, Explore, Detail, scanner fallback, signed action, 설문, network error, post-action, Flow, 전시 성공, invalid QR, REMEMBER/Favorite | 360 | 44px | 통과 |
| 390px | NOW, Explore, Detail/Personal Moment, 재진입, Flow, scanner fallback, REMEMBER, 공유 복사·수동 fallback | 390 | 44px | 통과 |
| 430px | NOW, Explore, Flow, scanner fallback, REMEMBER | 430 | 44px | 통과 |

확인한 긴 콘텐츠에는 `제9회 Hallym SW Week (테스트)`, `클라우드 네이티브 입문`,
`생성형 AI 시대의 개발자`, `공학관 대강의실 101`, 긴 설문 문항이 포함된다. Consumer
핵심 여정에는 별도 modal이 없으며, Favorite의 선택형 추가 입력은 페이지 안에서
잘리지 않았다. 하단 내비게이션과 콘텐츠도 겹치지 않았다.

다음은 CSS/device emulation만으로 판정하지 않는다.

- iOS Safari와 Android Chrome의 실제 safe-area
- 학생번호 입력 시 소프트 키보드와 자동 스크롤
- 카메라 권한 허용/거부 및 렌즈 전환
- production HTTPS의 실제 Android/iOS 네이티브 공유 시트와 사용자 취소
- 야외 밝기, 저사양 기기, 현장 Wi-Fi에서의 이미지·대형 JS chunk 체감

이 네 항목은 현재 `NOT PILOT READY` 판정의 실기기 게이트다.

## 4. 현실적인 테스트 이벤트

`scripts/seed_test_account.py`는 정확한 이름의 테스트 행사 하나만 만든다.

```text
행사       제9회 Hallym SW Week (테스트)
장소       한림대학교 공학관 일원
상태       LIVE (기본)
참여 방식  student_id — 실제 SSO 인증이 아니라 이 테스트 행사의 식별자
로그인     test@test.com / 123456test! (개발·테스트 DB 전용)
```

초기 seed 기준 데이터는 부스 6, 미션 6, 완료 100, 참여자 72, 특강 2, 전시 4,
관객 투표 48, Consumer Experience 12, Open 142, Favorite 29다. QA를 실행하면 실제
참여와 Open/Favorite가 추가되므로 숫자가 늘어나는 것이 정상이다.

| # | Experience | 맥락과 검증 |
|---:|---|---|
| 1 | AI 그림 프롬프트 실험 | 12분, 추천, 퀴즈, staff scan/회전 QR, 30점 |
| 2 | 3D 프린팅 키링 만들기 | 20분, staff scan/회전 QR, 30점 |
| 3 | 동아리 번개 발표 듣기 | duration 미입력, 안내 읽기, 0점; QR 검증 없이 Personal Moment로도 남길 수 있음 |
| 4 | 진로 고민 카드 상담 | 15분, choice 설문, participant scan/인쇄 QR, 20점 |
| 5 | 로컬 푸드 한입 시식 | 5분, staff scan/회전 QR, 10점 |
| 6 | 오프닝 라이브 함께 보기 | duration 미입력, 추천, participant scan/인쇄 QR, 0점 |
| 7 | 생성형 AI 시대의 개발자 | 지난 특강, 체크포인트 2개, 48명 중 37명 출석 인정 |
| 8 | 클라우드 네이티브 입문 | 현재 진행 특강, 실제 시간·장소, 첫 checkpoint 오픈 |
| 9 | 출결 QR 위조 탐지기 | 전시, 8분, 추천, 관객 투표 |
| 10 | 캠퍼스 길찾기 AR | 전시, 10분, 추천, 관객 투표 |
| 11 | 강의실 혼잡도 알림 | 전시, 6분, 관객 투표. 제목은 작품명일 뿐 FestaFlow의 실측 혼잡 데이터가 아님 |
| 12 | 학식 리뷰 모음 | 전시, duration 미입력, 관객 투표 |

관객용 투표 마감 공지와 스태프용 긴급 콘센트 공지도 서로 다른 채널로 들어 있다.
ENDED 전환 시 현장성 관객 공지는 기록을 지우지 않고 비활성화된다.

### 시드와 생명주기 명령

```bash
cd apps/api

# 없으면 생성, 이미 있으면 사용자 테스트 데이터를 보존
./.venv/bin/python scripts/seed_test_account.py

# 정확히 이 테스트 행사만 삭제 후 재생성 — 행사 ID가 바뀐다
./.venv/bin/python scripts/seed_test_account.py --reset

# 정확히 이 테스트 행사의 상태·날짜·투표·관객 공지만 좁게 전환
./.venv/bin/python scripts/seed_test_account.py --phase live
./.venv/bin/python scripts/seed_test_account.py --phase ended
```

Windows에서는 `./.venv/bin/python` 대신 `.\.venv\Scripts\python.exe`를 쓴다.
인계 시 현재 데모 행사는 다시 `LIVE`로 돌려 두었다.

## 5. Participant user-test kit — 5–10명

### 목적과 준비

목적은 기능 선호 조사보다 `DISCOVER → DECIDE → EXPERIENCE → MOMENT → FLOW →
REMEMBER`가 설명 없이 이어지는지 보는 것이다. 한 명씩 20–30분, 참가자가 평소 쓰는
휴대폰으로 진행한다. 최소 iOS Safari 2대, Android Chrome 2대를 포함한다.

준비물:

- LIVE 참가 링크 QR, 서명된 실제 부스 QR 2개, 특강 checkpoint QR 1개
- 서로 다른 테스트 학번 또는 anonymous 행사 사본
- 운영용 계정과 QR fallback용 **전체 링크** 인쇄본
- 화면/음성 기록 동의, 개인정보 안내, 관찰 기록지
- 세션 사이 participant 상태를 섞지 않을 별도 브라우저 프로필

진행자는 “행사에서 무엇을 할지 찾고 기록을 남기는 도구입니다” 이상을 먼저
설명하지 않는다. 버튼 위치, NOW/Explore/Flow의 뜻, 정답을 가르치지 않는다.

### 과업

| 과업 | 참가자에게 읽을 문장 | 관찰할 행동 |
|---|---|---|
| A | “이 행사에 처음 왔다고 생각하고 시작해보세요.” | 5초 안에 행사·장소/기간·시작 방법을 설명하는가, 학번을 로그인/SSO로 오해하는가 |
| B | “지금 할 만한 걸 하나 찾아보세요.” | NOW에서 결정하는가, Explore로 이동하는가, 무관한 공지에 막히는가 |
| C | “이 Experience를 할지 말지 판단해보세요.” | 무엇/시간/소요시간/장소/행동 중 무엇을 근거로 쓰는가, 없는 정보를 찾느라 헤매는가 |
| D | “실제로 하나 참여해보세요.” | 카메라 권한, QR 초점, 링크 이동, 제출, 오류 복구에서 도움이 필요한가 |
| E | 첫 성공 뒤 “지금 화면을 보고 어떤 의미인지 설명해주세요.” | “Moment/오늘 한 일”로 이해하는가, 점수·미션 완료 화면으로만 이해하는가 |
| F | 앱을 완전히 닫고 다시 연 뒤 “지금 무엇을 알 수 있나요?” | 상태 복원, 현재 맥락, Flow 누적을 스스로 찾는가 |
| G | ENDED 전환 후 “행사가 끝났습니다.” | 기록을 먼저 읽는가, Favorite를 의무 설문으로 오해하는가, Personal/Verified 구분을 이해하는가 |

과업 D 뒤에는 참가자가 선택하지 않았던 상세 하나를 열고 “이 경험을 했지만 QR은
찍지 않았다고 생각해보세요”라고만 말한다. Personal Moment를 스스로 발견하는지,
저장 전후 포인트가 변했다고 생각하는지 기록한다.

### 사후 질문

- 처음 화면을 보고 어떤 서비스라고 생각했나요?
- 행사에서 뭘 할지 찾는 데 도움이 됐나요?
- 가장 이해하기 어려운 화면은 어디였나요?
- Experience를 고를 때 어떤 정보가 필요했나요?
- My Flow를 보고 뭐라고 이해했나요?
- Flow를 다시 보려고 앱을 열 것 같나요? 왜요?
- 행사 끝 화면은 설문처럼 느껴졌나요, 기록처럼 느껴졌나요?
- FestaFlow 없이 행사에 참여했을 때와 뭐가 달랐나요?
- 앱에서 없어도 될 것 같은 건 뭐였나요?
- 딱 하나 더 필요하다면 무엇인가요?

### 관찰 기록지

의견과 행동을 같은 칸에 섞지 않는다.

| 참가자/기기 | 과업·시각 | 관찰한 행동 | 망설임/되돌아감 | 도움 요청 | 참가자 발언(원문) | 분류 |
|---|---|---|---|---|---|---|
| P__ / ____ | A–G / __:__ | | | | | TECH / UX / OPS / CONTENT |

세션 후 각 발견을 `BLOCKER`, `HIGH FRICTION`, `MEDIUM`, `FEATURE REQUEST`로 분류한다.
BLOCKER와 반복되는 HIGH FRICTION을 먼저 고치고, 단발성 기능 요청은 구현하지 않는다.

## 6. Organizer user-test kit — 1–3명

참여자 데이터가 쌓인 뒤 실제 행사 기획 가능성이 있는 사람에게 리포트를 먼저 보여 준다.
처음에는 지표 뜻을 설명하지 않는다.

### 과업

1. “어떤 Experience가 관심을 끌었다고 보이나요? 근거를 짚어주세요.”
2. “관심과 실제 확인 참여가 다른 항목을 찾아주세요.”
3. “사람들이 무엇을 통해 발견했는지 설명해주세요.”
4. “Favorite가 참여 건수와 다른 정보를 주는 항목을 찾아주세요.”
5. “이 결과로 다음 행사에서 바꿀 결정 하나를 말해주세요.”
6. “이 숫자로 알 수 **없는** 것도 말해주세요.”

### 질문과 판정

- 이 정보 중 실제 다음 행사에서 쓸 것 같은 것은 무엇인가요?
- 지금 기존에 보던 데이터와 무엇이 다른가요?
- 이걸 보고 실제로 어떤 결정을 바꿀 수 있을까요?
- Open을 방문객 수, verified count를 구역 혼잡도로 오해하는가?
- Favorite를 만족도 점수로 오해하는가?

운영자가 “상세 확인 대비 확인 참여가 상대적으로 낮다”라고 읽으면 적절하다.
“대기시간 때문에 이탈했다”처럼 측정하지 않은 원인을 붙이면 오해로 기록한다. 답이
“쓸 것이 없다”여도 차트를 추가하지 말고 현재 표의 의미와 표현을 먼저 재검토한다.

## 7. Privacy and data review

| 항목 | 현재 동작 | 파일럿 전 조치 |
|---|---|---|
| participant secret | 원문은 브라우저 localStorage, 서버는 hash만 저장. analytics에는 secret을 저장하지 않음 | 공용 기기 금지 안내, XSS/기기 분실 위험을 운영 문서에 반영 |
| 학번 | `student_id` 행사에서 participant 식별자로 저장되며 SSO 검증이 아님 | 수집 목적·보존 기간·삭제 창구와 재발급 정책 확정 |
| Experience Open | 인증 participant가 상세를 실제 연 시점과 source/context만 저장. 카드 impression은 수집하지 않음 | 집계 목적과 보존 기간 안내 |
| Verified 행동 | 기존 미션 grant, checkpoint, audience vote 트랜잭션에서 파생 | 방문객·혼잡·대기시간으로 표현하지 않기 |
| Personal Moment | 행사별 localStorage에만 저장, 포인트/조각/인증 없음 | 기기 삭제·변경 시 사라짐을 안내 |
| Favorite Memory | 사용자가 대상·사유를 선택해 명시적으로 PUT할 때만 서버 저장 | 선택 제출임을 유지; Personal source를 고르면 그 선택만 업로드됨을 안내 |
| 선택 comment | 공백 정규화, 최대 500자, 행사/source 소유권 검증 | 열람 권한, 보존·삭제, 부적절 내용 처리 정책 확정 |
| 위치 | background location, precise GPS 수집 없음 | “주변”을 GPS 기반이라고 홍보하지 않기 |

현재 화면의 짧은 설명은 제품 동작을 밝히지만 법률 자문이나 동의 문서를 대신하지
않는다. 실제 파일럿 전 담당자가 학번·활동·선택 comment의 보존 기간, 삭제 요청,
미성년자 가능성, 연구/테스트 기록 동의를 별도로 확정해야 한다.

## 8. 파일럿 종료 게이트와 운영안

### `PILOT READY`로 바꾸기 위한 종료 게이트

- [ ] 실제 iPhone Safari와 Android Chrome에서 참가 링크 진입
- [ ] 카메라 허용 → 인쇄 QR 및 회전 QR 인식 → 서버 서명 검증 → 완료
- [ ] 카메라 거부 → 이해 가능한 안내 → 기본 카메라 또는 전체 링크 fallback
- [ ] production HTTPS의 iPhone Safari·Android Chrome에서 네이티브 공유와 취소, 복사 fallback
- [ ] 학생번호 입력 중 소프트 키보드, safe-area, 하단 탭 겹침 없음
- [ ] 행사장 Wi-Fi/셀룰러에서 네트워크 끊김과 재시도
- [ ] 5–10명 참여자 테스트에서 core-loop BLOCKER 0건
- [ ] 1–3명 운영자가 Interest/Verified/Discovery/Memory를 구분
- [ ] production에서 local/demo 인증 fallback 비활성, HTTPS/cookie/CORS 확인
- [ ] 개인정보 안내·보존·삭제·문의 담당자 승인
- [ ] high-stakes 출결에 쓸 경우 학번 재발급/본인 확인 정책 별도 승인

### 게이트 통과 후 첫 파일럿

- 규모: 20–40명, 2–3시간, 8–12개 Experience
- 선택: 참가자가 고를 수 있는 활동 3개 이상, 강제 동선 없음
- 검증: participant signed QR 1개 이상, staff verified 1개 이상, 특강 또는 투표 1개
- 인력: 총괄 1명, QR/참가 지원 1명, 각 검증 지점 담당자
- 리뷰: 종료 직후 기술 로그, 다음 날 참여자 인터뷰와 운영자 리포트 해석 세션

### 운영 준비물

- 참가자 entry QR과 짧은 개인정보 안내
- 각 action의 QR 표지: Experience명, 해야 할 행동, fallback 전체 URL
- 테스트 운영자 계정과 역할별 staff code; 코드는 공개 표지와 분리
- “기본 카메라로 열기 → 안 되면 전체 링크 입력 → 그래도 안 되면 스태프 확인” 3단계 fallback
- 행사명·기간·장소·duration·행동 문구를 실제 운영자가 최종 검수한 metadata
- 실패 기록지: 시각, 기기, 네트워크, QR 종류, endpoint/error code, 복구 여부
- 종료 후 report-review 시간과 3–5명 후속 인터뷰 예약

행사 중에는 큰 기능 변경을 하지 않는다. 핵심 여정 복구에 필요한 hotfix만 적용하고,
발견을 `TECHNICAL`, `PRODUCT UX`, `EVENT OPERATIONS`, `CONTENT/METADATA`로 분리한다.
부스를 못 찾은 이유가 화면, 표지, 잘못 입력한 장소 중 무엇인지 먼저 확인한다.

### 파일럿 리뷰 형식

| 판정 | 기록할 근거 |
|---|---|
| KEEP | 설명 없이 성공한 행동과 반복 사용 |
| FIX | core concept는 통했지만 반복 망설임·지원 요청이 생긴 지점 |
| REMOVE | 쓰이지 않고 결정 시간을 늘린 요소 |
| TEST AGAIN | 표본이 작거나 기기/운영 변수가 섞인 결과 |
| V2 CANDIDATE | 여러 참가자에게 반복되고 더 단순한 해결이 없는 문제 |

리뷰에는 참가자가 **한 행동**, core loop가 끊긴 곳, 재진입 이유, 무시한 항목,
발견/확인/Favorite의 차이, 실제로 유용했던 운영자 해석, 없었던 데이터와 지원 요청을
포함한다.

## 9. Known limitations

1. 실제 카메라·권한·soft keyboard·safe-area는 미검증이다.
2. Personal Moment와 participant secret은 기기 브라우저에 묶인다. storage 삭제나
   기기 변경 시 Personal Moment는 복구되지 않는다.
3. participant action은 오프라인 저장 후 동기화하지 않는다. 오류와 재시도는 명확하지만
   완료에는 연결이 필요하다.
4. 인쇄 QR은 서명됐지만 고정 링크라 원격 재사용 가능성이 있다. 신뢰 수준이 더 필요한
   행동은 staff scan 또는 짧은 회전 QR을 사용한다.
5. 학번 재입력은 학교 SSO가 아니며, 학번을 아는 사람에 대한 강한 본인 확인이 아니다.
6. 사진 Experience는 동의·보존·삭제·객체 저장소 정책 전까지 서버가 명시적으로 거부한다.
7. production HTTPS/cookie/CORS, 현장 네트워크, 부하·동시 접속, 백업/복구는 검증하지 않았다.
8. production bundle은 빌드되지만 500kB 초과 chunk 경고가 있다. 실제 저사양 기기에서
   Time to Decision에 영향을 주는지 측정해야 한다.
9. 비밀번호 재설정과 공개 참여 API의 요청 속도 제한·남용 모니터링은 production
   프록시 또는 애플리케이션에서 별도로 적용해야 한다.
9. 공유 분기에는 의존성 없는 `node:test` 회귀 테스트가 있지만 frontend 전체 회귀
   자동화는 아직 정식 테스트 스위트가 아니다. 브라우저 QA도 Chrome/CDP로 수행했지만
   CI에 편입되지 않았다.
10. Open/verified/Favorite는 앱·DB 행동이다. 방문객 수, 혼잡, 대기시간, 인과관계를
    측정하지 않는다.

## 10. V2 holding list

아래는 구현 승인이 아니라 **관찰 대기 목록**이다.

| 후보 | 현재 판정 | V2 진입 조건 |
|---|---|---|
| 다중 기기 복구 / server-backed Flow | HOLD | 실제 테스트에서 기기 변경·storage 삭제로 반복 손실 |
| Saved / 나중에 보기 | HOLD | 참가자가 Personal Moment와 구분되는 사전 저장을 반복 요구 |
| Place QR / map | HOLD | 올바른 metadata·물리 표지로도 장소 탐색 실패가 반복 |
| push | HOLD | 행사 중 재진입 의도는 있으나 시간을 놓치는 행동이 반복되고 동의·운영 비용이 정당화됨 |
| 공유 카드·친구/social 확장 | HOLD | V1 링크 공유를 넘어선 요구가 여러 명에게 관찰되고 개인정보 노출 설계가 가능 |
| personalization / AI recommendation | HOLD | 현재 렌즈로 결정 시간이 길다는 증거와 사용할 수 있는 실제 데이터가 모두 존재 |
| surprise discovery | HOLD | 의도적 탐색을 해치지 않으며 더 단순한 featured/content 개선으로 해결되지 않음 |

각 후보는 관찰된 문제 수, 더 단순한 해결, Time to Decision, 자유 탐색, 실제 보유 데이터,
운영 부담, 개인정보 기대를 모두 답하기 전에는 구현하지 않는다.

## 11. Contest demo script

약 4–5분, 한 참가자의 이야기만 사용한다. 시작 전 test seed를 LIVE로 두고 새 브라우저
프로필을 연다. 성공 상태를 미리 만들거나 스크린샷으로 대체하지 않는다.

1. **EVENT ARRIVAL** — 참가 링크를 열어 Hallym SW Week의 장소·기간과 실제
   Experience 미리보기를 보여 준다. “학번은 이 테스트 행사의 식별자이며 SSO가
   아닙니다”라고만 밝힌다.
2. **NOW** — 현재 진행 중인 `클라우드 네이티브 입문`과 짧은 Experience를 보고,
   모든 것을 완료하라는 압력이 없음을 보여 준다.
3. **DECISION** — Explore에서 `진로 고민 카드 상담` 상세를 열어 무엇/장소/15분/
   행동을 확인한다. duration이 없는 다른 카드는 빈칸을 꾸며내지 않음을 짧게 비교한다.
4. **REAL EXPERIENCE** — 현장에 인쇄한 실제 signed QR을 카메라로 읽고 설문을 제출한다.
   서버가 검증한 뒤 “하나의 순간이 남았어요”와 실제 완료 시각을 보여 준다.
5. **FLOW** — My Flow에서 Verified Moment를 확인한다. `동아리 번개 발표 듣기`는
   이번에는 QR 없이 Personal Moment로 남기고 포인트가 변하지 않음을 보여 준다.
6. **RETURN** — 앱을 닫았다 다시 열어 NOW의 두 Moment가 복원되는 것을 보여 준다.
7. **REMEMBER** — 행사 종료 상태에서 놓친 항목 대신 남은 Flow를 먼저 보여 주고,
   Favorite 하나와 가벼운 사유를 명시적으로 제출한다.
8. **ORGANIZER** — 실제 계정으로 리포트를 열어 Interest → Verified Experience →
   Discovery → Memory를 같은 Experience 행에서 읽는다. Open을 방문객 수나 원인 분석으로
   부풀리지 않는다.

마무리 문장:

> FestaFlow는 행사의 Experience를 참가자에게는 발견과 기억으로, 운영자에게는 실제
> 행동과 인사이트로 연결합니다. 앱에 오래 머물게 하는 것이 아니라, 더 빨리 결정하고
> 다시 실제 행사로 돌아가게 합니다.

## 12. 현재 인계 상태

- 데모 행사는 `LIVE`로 복원됨
- seed reset은 정확한 테스트 행사만 대상으로 동작함
- 미션/특강/투표/Personal/Favorite/리포트의 실제 연결 검증 완료
- Experience 딥링크와 Flow/REMEMBER 공유는 LAN HTTP 복사 fallback까지 검증 완료;
  production HTTPS 네이티브 시트는 실기기 게이트
- 다음 행동은 V2 구현이 아니라 **실제 휴대폰 리허설 → 5–10명 테스트 → 1–3명 운영자
  해석 테스트 → 판정 갱신** 순서임
