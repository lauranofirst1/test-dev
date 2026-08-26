#!/usr/bin/env python
"""테스트 계정 하나와 **안이 채워진 축제 하나**를 만든다.

    cd apps/api
    ./.venv/bin/python scripts/seed_test_account.py

    로그인: test@test.com / 123456test!

빈 화면에서는 무엇이 잘못됐는지 보이지 않습니다. 표는 한 줄일 때 늘 멀쩡해
보이고, 편중 판정도 집계 경고도 데이터가 있어야 켜집니다. 그래서 이 스크립트는
계정만 만들지 않고 **화면마다 볼 것이 생기는 만큼** 채웁니다 — 부스와 참여,
특강과 출결(찍고 나간 사람 포함), 전시 작품과 심사 점수와 관객 투표.

만드는 축제는 교내 행사입니다(한림대 SW Week). 관광 축제 데모(`demo_seed.py`)와
달리 신원이 학번이고, 특강 출결이 공결로 이어지며, 전시 심사가 있습니다.

**두 번 돌려도 안전합니다.** 계정이 있으면 비밀번호만 맞춰 두고, 축제가 이미
있으면 손대지 않습니다 — 테스트하다 만들어 둔 것을 지우지 않기 위해서입니다.
처음부터 다시 만들려면 `--reset` 을 붙이세요(그 축제만 지웁니다).

🚨 개발·테스트 DB 전용입니다.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from festaflow.core import security  # noqa: E402
from festaflow.db.session import SessionLocal  # noqa: E402
from festaflow.models import (  # noqa: E402
    Announcement,
    AudienceVote,
    Booth,
    Exhibit,
    Festival,
    FestivalPlan,
    FestivalStaff,
    JudgeScore,
    KpiTarget,
    LectureSession,
    Mission,
    Organization,
    OrganizationAccount,
    Participant,
    Participation,
    Prize,
    SessionAttendance,
    SessionCheckpoint,
    StampBoard,
    StampTile,
    VoteCriterion,
)
from festaflow.models.enums import (  # noqa: E402
    AnnouncementChannel,
    AnnouncementLevel,
    BoardStyle,
    BoothQrMode,
    BoothType,
    BoothVerifyMode,
    FestivalStatus,
    GrantUnit,
    IdentityMode,
    ParticipationStatus,
    PlanStage,
    RevealMode,
    StaffRole,
)

EMAIL = "test@test.com"
PASSWORD = "123456test!"
ORG_NAME = "한림대학교 SW중심대학사업단 (테스트)"
FESTIVAL_NAME = "제9회 Hallym SW Week (테스트)"

#: 씨를 고정한다. 다시 돌려도 같은 화면이 나와야 "어제와 다르다" 가 신호가 된다.
RNG = random.Random(20261102)

#: 스태프 접근 코드. 발급 코드는 원래 무작위지만, 테스트 계정에서는 **고정**한다 —
#: 현장 화면(부스 지급·심사표)에 들어가 보려면 코드가 손에 있어야 하고, 매번
#: 바뀌면 그때마다 스크립트 출력을 뒤져야 한다. 글자는 코드 알파벳 안에서만 쓴다.
STAFF_CODES: list[tuple[StaffRole, str, str, int | None]] = [
    (StaffRole.OPERATOR, "현장 운영", "SWEEK2", None),
    (StaffRole.BOOTH_MANAGER, "AI 체험존 담당", "BSTAF2", 0),
    (StaffRole.BOOTH_MANAGER, "메이커존 담당", "BSTAF3", 1),
    (StaffRole.JUDGE, "심사위원 김교수", "JUDGE2", None),
    (StaffRole.JUDGE, "심사위원 이교수", "JUDGE3", None),
    (StaffRole.JUDGE, "심사위원 박멘토", "JUDGE4", None),
]

#: (이름, 유형, 위치, 확인 방식, QR 방식, 미션[(제목, 점수)])
BOOTHS: list[tuple[str, BoothType, str, BoothVerifyMode, BoothQrMode, list[tuple[str, int]]]] = [
    (
        "AI 체험존",
        BoothType.EXPERIENCE,
        "공학관 1층 A구역",
        BoothVerifyMode.STAFF_SCAN,
        BoothQrMode.ROTATING,
        [("모델 데모 돌려보기", 30), ("프롬프트 챌린지", 20)],
    ),
    (
        "메이커존",
        BoothType.EXPERIENCE,
        "공학관 1층 B구역",
        BoothVerifyMode.STAFF_SCAN,
        BoothQrMode.ROTATING,
        [("3D 프린팅 관람", 20), ("키링 만들기", 30)],
    ),
    (
        "동아리 홍보관",
        BoothType.ETC,
        "공학관 2층 복도",
        BoothVerifyMode.PARTICIPANT_SCAN,
        BoothQrMode.PRINTED,
        [("동아리 소개 듣기", 10)],
    ),
    (
        "SW 진로 상담",
        BoothType.INFORMATION,
        "공학관 로비",
        BoothVerifyMode.PARTICIPANT_SCAN,
        BoothQrMode.PRINTED,
        [("상담 받기", 20)],
    ),
    (
        "푸드트럭 존",
        BoothType.FOOD,
        "공학관 앞 광장",
        BoothVerifyMode.STAFF_SCAN,
        BoothQrMode.ROTATING,
        [("간식 받기", 10)],
    ),
    (
        "개막 공연",
        BoothType.PERFORMANCE,
        "대강당",
        BoothVerifyMode.PARTICIPANT_SCAN,
        BoothQrMode.PRINTED,
        [("공연 관람 인증", 10)],
    ),
]

#: 참여를 부스에 흩는 가중치. 일부러 한쪽으로 몰아 둔다 — 균등하게 두면
#: 대시보드의 편중 판정과 "조용한 부스" 추천 카드가 영영 안 뜬다.
BOOTH_WEIGHTS = [34, 22, 14, 9, 16, 5]

#: 그중 **최근 25분 안**에 둘 건수. 당일 화면의 편중 판정은 최근 30분 완료가
#: 10건을 넘어야 켜지고, 한 부스가 40% 를 넘겨야 과밀(HIGH)이 되며, 15% 이하인
#: 부스가 있어야 "조용한 부스로 보내세요" 추천이 뜬다. 어제부터 고르게 흩어
#: 두면 판정도 추천도 영영 확인할 수 없어서, 지금 이 순간의 모양을 만들어 둔다.
RECENT_WEIGHTS = [24, 8, 5, 3, 6, 1]

#: (제목, 팀, 한 줄 소개, 태그, 전시 위치)
EXHIBITS: list[tuple[str, str, str, list[str], str]] = [
    (
        "출결 QR 위조 탐지기",
        "3팀 겹눈",
        "화면 촬영본으로 찍은 출석을 잡아냅니다.",
        ["보안", "머신러닝"],
        "공학관 1층 A-1",
    ),
    (
        "캠퍼스 길찾기 AR",
        "5팀 나침반",
        "강의실 번호만 넣으면 복도에 화살표를 띄웁니다.",
        ["AR", "모바일"],
        "공학관 1층 A-2",
    ),
    (
        "강의실 혼잡도 알림",
        "1팀 자리요",
        "빈 좌석 수를 실시간으로 셉니다.",
        ["IoT", "비전"],
        "공학관 1층 A-3",
    ),
    (
        "학식 리뷰 모음",
        "7팀 든든",
        "학식 메뉴와 후기를 한 곳에 모읍니다.",
        ["웹", "크롤링"],
        "공학관 1층 B-1",
    ),
    (
        "수어 번역 글러브",
        "2팀 손말",
        "손가락 관절 각도를 읽어 자모로 옮깁니다.",
        ["하드웨어", "접근성"],
        "공학관 1층 B-2",
    ),
    (
        "탄소 발자국 대시보드",
        "9팀 초록발",
        "학과별 전력 사용량을 하루 단위로 보여줍니다.",
        ["데이터", "시각화"],
        "공학관 1층 B-3",
    ),
]

#: (항목, 만점, 가중치). 가중치는 상대값이라 합이 100 일 필요가 없다.
CRITERIA: list[tuple[str, int, int]] = [
    ("창의성", 5, 2),
    ("완성도", 5, 2),
    ("발표력", 5, 1),
    ("실용성", 5, 1),
]

#: 작품별 심사 성향(평균으로 삼을 값). 1번 작품이 앞서고 4번이 처진다.
EXHIBIT_BIAS = [4.6, 4.1, 3.9, 3.2, 4.3, 3.6]

#: 작품별 관객 득표. 심사 1등과 관객 1등을 **일부러 어긋나게** 둔다 —
#: 두 점수를 어떻게 섞는지가 이 화면의 핵심인데, 순위가 같으면 확인이 안 된다.
EXHIBIT_VOTES = [12, 9, 21, 6, 14, 4]


def _dt(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm), tzinfo=UTC)


def seed(db: Session, *, reset: bool) -> None:
    today = datetime.now(UTC).date()

    account = db.execute(
        select(OrganizationAccount).where(OrganizationAccount.email == EMAIL)
    ).scalar_one_or_none()

    if account is None:
        org = Organization(name=ORG_NAME)
        db.add(org)
        db.flush()
        # `accounts.sign_up` 을 쓰지 않는다. 저 함수는 "이메일 아이디가 비밀번호에
        # 들어 있으면 거절" 규칙을 갖고 있어 test@test.com / 123456test! 조합을
        # 받지 않는다. 정한 자격증명을 그대로 쓰려고 여기서 직접 만든다 —
        # 로그인은 해시만 보므로 그대로 들어가진다. **테스트 계정 전용**이다.
        account = OrganizationAccount(
            organization_id=org.id,
            email=EMAIL,
            password_hash=security.hash_password(PASSWORD),
            display_name="테스트 담당자",
        )
        db.add(account)
        db.flush()
        print(f"✓ 계정 생성 {EMAIL} (기관 #{org.id} {ORG_NAME})")
    else:
        org = db.get(Organization, account.organization_id)
        account.password_hash = security.hash_password(PASSWORD)
        print(f"· 계정이 이미 있어 비밀번호만 맞춰 둡니다 {EMAIL} (기관 #{org.id})")

    existing = db.execute(
        select(Festival).where(
            Festival.organization_id == org.id, Festival.name == FESTIVAL_NAME
        )
    ).scalar_one_or_none()

    if existing is not None and not reset:
        print(f"· 축제 #{existing.id} 가 이미 있습니다. 데이터는 그대로 둡니다 (--reset 으로 다시).")
        return

    if existing is not None:
        db.execute(delete(Festival).where(Festival.id == existing.id))
        db.flush()
        print(f"✓ 기존 축제 #{existing.id} 를 지우고 다시 만듭니다")

    # ── 축제 ────────────────────────────────────────────────────────────────
    # 오늘이 이틀째가 되게 잡는다. 지난 것도 남은 것도 있어야 대시보드·리포트가
    # 둘 다 볼 것이 있다.
    festival = Festival(
        organization_id=org.id,
        name=FESTIVAL_NAME,
        region="강원특별자치도 춘천시",
        venue="한림대학교 공학관 일원",
        starts_on=today - timedelta(days=1),
        ends_on=today + timedelta(days=2),
        expected_visitors=1200,
        total_budget=11_800_000,
        # 교내 행사라 1인 1표와 공결 처리를 위해 학번을 받는다.
        identity_mode=IdentityMode.STUDENT_ID,
        audience_votes_per_participant=3,
        judge_weight_percent=70,
        voting_open=True,
        status=FestivalStatus.LIVE,
        plan_stage=PlanStage.OPERATIONS,
    )
    db.add(festival)
    db.flush()

    db.add(
        FestivalPlan(
            festival_id=festival.id,
            summary="재학생이 한 학기 동안 만든 것을 서로 보여주고, 외부 멘토가 심사하는 주간 행사.",
            description=(
                "전공 부스와 동아리 홍보, SW 특강, 전시 심사로 이루어집니다. "
                "특강은 출석을 인정받으면 공결 처리가 되므로 체크인을 두 번 엽니다."
            ),
            purposes=["재학생 참여 확대", "학과 간 교류", "취업 연계"],
            target_segments=["재학생", "신입생", "외부 멘토"],
            core_audience="공학관 재학생",
            staff_count=18,
            volunteer_count=24,
            safety_staff_count=4,
            parking_capacity=120,
            venue_capacity=800,
            planned_experience=2,
            planned_food=1,
            planned_performance=1,
            planned_tour_info=1,
            planned_etc=1,
            transit_access="춘천역에서 셔틀 15분",
            crowd_plan="개막 공연 시간대에 대강당 인원을 300명으로 제한합니다.",
            safety_plan="공학관 1층에 응급 키트를 두고 스태프 2명이 상주합니다.",
            promotion_plan="학과 단톡방과 학내 게시판, 인스타그램 계정.",
        )
    )

    for key, label, target, unit in (
        ("expected_visitors", "예상 방문객", 1200, "명"),
        ("qr_participants", "참여 코드 발급", 600, "명"),
        ("total_completions", "미션 완료", 1800, "건"),
    ):
        db.add(
            KpiTarget(
                festival_id=festival.id,
                metric_key=key,
                label=label,
                target_value=target,
                unit=unit,
            )
        )

    # ── 부스와 미션 ─────────────────────────────────────────────────────────
    booths: list[Booth] = []
    missions_by_booth: list[list[Mission]] = []
    for name, btype, location, verify, qr, missions in BOOTHS:
        booth = Booth(
            festival_id=festival.id,
            name=name,
            booth_type=btype,
            location=location,
            verify_mode=verify,
            qr_mode=qr,
        )
        db.add(booth)
        db.flush()
        booths.append(booth)

        made: list[Mission] = []
        for title, points in missions:
            m = Mission(
                festival_id=festival.id, booth_id=booth.id, title=title, points=points
            )
            db.add(m)
            made.append(m)
        db.flush()
        missions_by_booth.append(made)

    # ── 스탬프 보드 ─────────────────────────────────────────────────────────
    board = StampBoard(
        festival_id=festival.id,
        rows=2,
        cols=3,
        reveal_mode=RevealMode.BOOTH_ASSIGNED,
        grant_unit=GrantUnit.BOOTH,
        board_style=BoardStyle.GRID,
    )
    db.add(board)
    db.flush()
    for i, booth in enumerate(booths):
        db.add(
            StampTile(
                board_id=board.id,
                board_version=board.version,
                tile_index=i,
                assigned_booth_id=booth.id,
            )
        )

    # ── 스태프 ──────────────────────────────────────────────────────────────
    staff_by_role: dict[StaffRole, list[FestivalStaff]] = {}
    staff_by_role_order: list[FestivalStaff] = []
    for role, display_name, code, booth_idx in STAFF_CODES:
        s = FestivalStaff(
            festival_id=festival.id,
            role=role,
            display_name=display_name,
            booth_id=booths[booth_idx].id if booth_idx is not None else None,
            access_code_hash=security.hash_access_code(code),
        )
        db.add(s)
        staff_by_role.setdefault(role, []).append(s)
        staff_by_role_order.append(s)
    db.flush()

    # ── 참여자 ──────────────────────────────────────────────────────────────
    # 학번을 받는 행사다. 코드만 있는 참여자를 만들면 1인 1표가 검증되지 않는다.
    participants: list[Participant] = []
    for i in range(72):
        p = Participant(
            festival_id=festival.id,
            code=security.generate_participant_code(),
            student_no=f"2023{1000 + i:04d}",
            secret_hash=security.hash_participant_secret(
                security.generate_participant_secret()
            ),
            last_seen_at=datetime.now(UTC) - timedelta(minutes=RNG.randint(1, 600)),
        )
        db.add(p)
        participants.append(p)
    db.flush()

    # ── 현장 참여 ───────────────────────────────────────────────────────────
    now = datetime.now(UTC)
    # 한 사람이 같은 미션을 두 번 완료할 수 없다(uq_participations_grant).
    # 무작위로 뽑으면 같은 쌍이 나오므로 쓴 쌍을 기억하며 채운다.
    used_grants: set[tuple[int, int]] = set()
    total = 0
    for idx, booth in enumerate(booths):
        want = BOOTH_WEIGHTS[idx]
        pool = participants[:]
        RNG.shuffle(pool)
        made = 0
        for participant in pool:
            if made >= want:
                break
            mission = RNG.choice(missions_by_booth[idx])
            key = (participant.id, mission.id)
            if key in used_grants:
                continue
            used_grants.add(key)
            recent = made < RECENT_WEIGHTS[idx]
            minutes = RNG.randint(1, 25) if recent else RNG.randint(60, 900)
            db.add(
                Participation(
                    festival_id=festival.id,
                    participant_id=participant.id,
                    booth_id=booth.id,
                    mission_id=mission.id,
                    status=ParticipationStatus.COMPLETED,
                    completed_at=now - timedelta(minutes=minutes),
                    # granted_points 는 생성 열이다(base + bonus). 넣으면 거절당한다.
                    base_points=mission.points,
                    verified_via=booth.verify_mode,
                )
            )
            made += 1
        total += made

    # ── 특강과 출결 ─────────────────────────────────────────────────────────
    # 어제 특강: 체크인 두 번을 다 닫았다. **찍고 나간 사람이 섞여 있다** —
    # 첫 체크인만 찍고 두 번째를 안 찍은 사람은 출석이 인정되지 않는다.
    yesterday = today - timedelta(days=1)
    past = LectureSession(
        festival_id=festival.id,
        title="생성형 AI 시대의 개발자",
        speaker="김지훈",
        affiliation="네이버클라우드",
        location="공학관 대강의실 101",
        starts_at=_dt(yesterday, 5),  # 한국시간 14:00
        ends_at=_dt(yesterday, 7),
        required_checkins=2,
        grants_excused_absence=True,
    )
    db.add(past)
    db.flush()

    cp1 = SessionCheckpoint(
        session_id=past.id,
        sequence=1,
        opens_at=_dt(yesterday, 5),
        closes_at=_dt(yesterday, 5, 20),
        note="시작 직후",
    )
    cp2 = SessionCheckpoint(
        session_id=past.id,
        sequence=2,
        opens_at=_dt(yesterday, 6, 40),
        closes_at=_dt(yesterday, 7),
        note="종료 직전",
    )
    db.add_all([cp1, cp2])
    db.flush()

    attendees = participants[:48]
    left_early = attendees[:11]  # 출튀 — 첫 체크인만 찍었다
    for p in attendees:
        db.add(
            SessionAttendance(
                session_id=past.id,
                checkpoint_id=cp1.id,
                participant_id=p.id,
                checked_at=_dt(yesterday, 5, RNG.randint(1, 18)),
            )
        )
        if p not in left_early:
            db.add(
                SessionAttendance(
                    session_id=past.id,
                    checkpoint_id=cp2.id,
                    participant_id=p.id,
                    checked_at=_dt(yesterday, 6, 40 + RNG.randint(1, 18)),
                )
            )

    # 오늘 특강: 지금 체크인 하나가 열려 있다. 강의실 화면이 볼 것이 생긴다.
    live = LectureSession(
        festival_id=festival.id,
        title="클라우드 네이티브 입문",
        speaker="이서연",
        affiliation="당근",
        location="공학관 대강의실 101",
        starts_at=now - timedelta(minutes=30),
        ends_at=now + timedelta(hours=1, minutes=30),
        required_checkins=2,
        grants_excused_absence=True,
    )
    db.add(live)
    db.flush()
    open_cp = SessionCheckpoint(
        session_id=live.id,
        sequence=1,
        opens_at=now - timedelta(minutes=20),
        closes_at=now + timedelta(minutes=10),
        note="시작 직후",
    )
    db.add(open_cp)
    db.flush()
    for p in participants[:26]:
        db.add(
            SessionAttendance(
                session_id=live.id,
                checkpoint_id=open_cp.id,
                participant_id=p.id,
                checked_at=now - timedelta(minutes=RNG.randint(1, 18)),
            )
        )

    # ── 전시 심사 ───────────────────────────────────────────────────────────
    criteria: list[VoteCriterion] = []
    for order, (label, max_score, weight) in enumerate(CRITERIA):
        c = VoteCriterion(
            festival_id=festival.id,
            label=label,
            max_score=max_score,
            weight=weight,
            sort_order=order,
        )
        db.add(c)
        criteria.append(c)

    exhibits: list[Exhibit] = []
    for no, (title, team, summary, tags, location) in enumerate(EXHIBITS, start=1):
        e = Exhibit(
            festival_id=festival.id,
            entry_no=no,
            title=title,
            team_name=team,
            summary=summary,
            tags=tags,
            location=location,
        )
        db.add(e)
        exhibits.append(e)
    db.flush()

    judges = staff_by_role[StaffRole.JUDGE]
    for i, exhibit in enumerate(exhibits):
        # 마지막 작품은 일부러 두 명만 심사한다. 심사위원 수가 작품마다 다르면
        # 집계 화면이 경고를 띄우는데, 그게 실제로 뜨는지 여기서 확인한다.
        panel = judges[:2] if i == len(exhibits) - 1 else judges
        for judge in panel:
            for c in criteria:
                raw = EXHIBIT_BIAS[i] + RNG.uniform(-0.6, 0.6)
                score = max(1, min(c.max_score, round(raw)))
                db.add(
                    JudgeScore(
                        exhibit_id=exhibit.id,
                        criterion_id=c.id,
                        staff_id=judge.id,
                        score=score,
                    )
                )

    # 관객 투표. 한 사람이 같은 작품에 두 번 넣지 않고, 1인당 표 수를 넘기지 않는다 —
    # 실제 제약이 그렇고, 어긴 데이터로 채우면 화면이 현장에서 나올 수 없는 모양이 된다.
    used: dict[int, set[int]] = {}
    voters = participants[:60]
    for i, exhibit in enumerate(exhibits):
        want = EXHIBIT_VOTES[i]
        pool = [p for p in voters if len(used.get(p.id, ())) < festival.audience_votes_per_participant]
        RNG.shuffle(pool)
        for p in pool[:want]:
            used.setdefault(p.id, set()).add(exhibit.id)
            db.add(
                AudienceVote(
                    festival_id=festival.id,
                    exhibit_id=exhibit.id,
                    participant_id=p.id,
                    voted_at=now - timedelta(minutes=RNG.randint(5, 600)),
                )
            )

    # ── 경품과 공지 ─────────────────────────────────────────────────────────
    for name, stock, weight, blank in (
        ("학식 교환권", 40, 30, False),
        ("스타벅스 기프티콘", 15, 15, False),
        ("SW Week 굿즈 세트", 8, 8, False),
        ("꽝", None, 47, True),
    ):
        db.add(
            Prize(
                festival_id=festival.id,
                name=name,
                stock=stock,
                weight=weight,
                is_blank=blank,
            )
        )

    db.add(
        Announcement(
            festival_id=festival.id,
            channel=AnnouncementChannel.AUDIENCE,
            level=AnnouncementLevel.NORMAL,
            title="전시 관람 투표는 오늘 17시까지입니다",
            body="1층 A·B구역 작품을 둘러보고 마음에 드는 작품 3개까지 투표할 수 있습니다.",
        )
    )
    db.add(
        Announcement(
            festival_id=festival.id,
            channel=AnnouncementChannel.STAFF,
            level=AnnouncementLevel.URGENT,
            title="공학관 1층 콘센트 사용 금지",
            body="누전 점검 중입니다. 체험 부스는 보조 배터리를 쓰세요.",
        )
    )

    db.flush()

    print(f"✓ 축제 #{festival.id} {FESTIVAL_NAME}")
    print(f"  부스 {len(booths)} · 미션 {sum(len(m) for m in missions_by_booth)} · 참여 {total}건")
    print(f"  참여자 {len(participants)}명 · 특강 2개(출튀 {len(left_early)}명 포함)")
    print(f"  작품 {len(exhibits)} · 심사 항목 {len(criteria)} · 심사위원 {len(judges)}명 · 투표 {sum(EXHIBIT_VOTES)}표")
    # 초대 주소를 그대로 찍는다. 스태프 ID 는 다시 채울 때마다 바뀌는데,
    # 그때마다 콘솔을 뒤져 찾게 하면 팀원은 현장 화면까지 가지 않는다.
    print("\n  현장 화면 — 아래 주소를 열고 접근 코드를 넣으세요:")
    for (role, display_name, code, _), staff in zip(
        STAFF_CODES, staff_by_role_order, strict=True
    ):
        print(
            f"    {code}  {display_name:16} "
            f"http://localhost:5173/staff/login?f={festival.id}&s={staff.id}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--reset",
        action="store_true",
        help="같은 이름의 테스트 축제가 있으면 지우고 다시 만든다",
    )
    args = ap.parse_args()

    with SessionLocal() as db:
        seed(db, reset=args.reset)
        db.commit()

    print(f"\n로그인: {EMAIL} / {PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
