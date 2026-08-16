"""스키마 제약이 실제로 동작하는지 검증.

설계 문서가 "DB 제약으로 건다"고 주장하는 항목들을 실제 Postgres 에서 확인합니다.
애플리케이션 코드에만 있는 규칙은 동시 요청에서 뚫리므로, 여기서 통과해야 그 주장이 참입니다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from festaflow.models import (
    Booth,
    Festival,
    FestivalPlan,
    Mission,
    Organization,
    Participant,
    Participation,
    StampBoard,
)
from festaflow.models.enums import BoothType, ParticipationStatus

pytestmark = pytest.mark.usefixtures("engine")


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


def make_festival(db: Session, **kw) -> Festival:
    org = Organization(name="춘천시문화재단")
    db.add(org)
    db.flush()
    f = Festival(
        organization_id=org.id,
        name=kw.get("name", "춘천 가을 먹거리 축제"),
        region="강원특별자치도 춘천시",
        venue="공지천 조각공원",
        starts_on=kw.get("starts_on", date(2026, 10, 10)),
        ends_on=kw.get("ends_on", date(2026, 10, 12)),
        expected_visitors=kw.get("expected_visitors", 18000),
        total_budget=kw.get("total_budget", 240_000_000),
    )
    db.add(f)
    db.flush()
    db.add(FestivalPlan(festival_id=f.id))
    db.flush()
    return f


def make_booth_mission(db: Session, festival: Festival) -> tuple[Booth, Mission]:
    b = Booth(festival_id=festival.id, name="막국수 체험존", booth_type=BoothType.EXPERIENCE)
    db.add(b)
    db.flush()
    m = Mission(festival_id=festival.id, booth_id=b.id, title="막국수 반죽 체험", points=100)
    db.add(m)
    db.flush()
    return b, m


def make_participant(db: Session, festival: Festival, code: str = "FF-3A9K2P7Q") -> Participant:
    p = Participant(festival_id=festival.id, code=code, secret_hash="x")
    db.add(p)
    db.flush()
    return p


def grant(db: Session, f, p, m, b, **kw) -> Participation:
    row = Participation(
        festival_id=f.id,
        participant_id=p.id,
        mission_id=m.id,
        booth_id=b.id,
        status=ParticipationStatus.COMPLETED,
        completed_at=kw.pop("completed_at", datetime.now(UTC)),
        base_points=kw.pop("base_points", 100),
        bonus_points=kw.pop("bonus_points", 0),
        **kw,
    )
    db.add(row)
    db.flush()
    return row


# ── US-12 중복 지급 방지 ────────────────────────────────────────────────────


def test_duplicate_grant_is_blocked_by_db(db: Session):
    """같은 참여자·미션으로 두 번 지급하면 DB 가 막는다."""
    f = make_festival(db)
    b, m = make_booth_mission(db, f)
    p = make_participant(db, f)

    grant(db, f, p, m, b)
    with pytest.raises(IntegrityError):
        grant(db, f, p, m, b)


def test_same_mission_different_participants_is_fine(db: Session):
    f = make_festival(db)
    b, m = make_booth_mission(db, f)
    p1 = make_participant(db, f, "FF-AAAAAAAA")
    p2 = make_participant(db, f, "FF-BBBBBBBB")

    grant(db, f, p1, m, b)
    grant(db, f, p2, m, b)  # 예외 없이 통과해야 한다


# ── US-13 오프라인 재전송 멱등성 ────────────────────────────────────────────


def test_client_request_id_prevents_replay(db: Session):
    """오프라인 큐가 같은 요청을 다시 보내도 중복 이력이 생기지 않는다."""
    f = make_festival(db)
    b, m = make_booth_mission(db, f)
    p1 = make_participant(db, f, "FF-AAAAAAAA")
    p2 = make_participant(db, f, "FF-BBBBBBBB")
    rid = "0f8b6e5a-3c21-4a77-9d10-2b7e5f1c8a44"

    grant(db, f, p1, m, b, client_request_id=rid)
    # 참여자가 달라도 같은 요청 ID 면 재전송이므로 막혀야 한다.
    with pytest.raises(IntegrityError):
        grant(db, f, p2, m, b, client_request_id=rid)


def test_null_client_request_id_does_not_collide(db: Session):
    """온라인 지급은 client_request_id 가 없다. NULL 끼리는 충돌하면 안 된다."""
    f = make_festival(db)
    b, m = make_booth_mission(db, f)
    p1 = make_participant(db, f, "FF-AAAAAAAA")
    p2 = make_participant(db, f, "FF-BBBBBBBB")

    grant(db, f, p1, m, b, client_request_id=None)
    grant(db, f, p2, m, b, client_request_id=None)


# ── 포인트 스냅샷 ───────────────────────────────────────────────────────────


def test_granted_points_is_generated_by_db(db: Session):
    """애플리케이션이 합계를 잘못 계산할 여지를 없앤다."""
    f = make_festival(db)
    b, m = make_booth_mission(db, f)
    p = make_participant(db, f)

    row = grant(db, f, p, m, b, base_points=100, bonus_points=50)
    db.refresh(row)
    assert row.granted_points == 150


def test_points_snapshot_survives_mission_change(db: Session):
    """미션 포인트를 나중에 바꿔도 이미 지급된 금액은 변하지 않는다."""
    f = make_festival(db)
    b, m = make_booth_mission(db, f)
    p = make_participant(db, f)
    row = grant(db, f, p, m, b, base_points=100)

    m.points = 999
    db.flush()
    db.refresh(row)
    assert row.base_points == 100
    assert row.granted_points == 100


def test_booth_snapshot_survives_mission_reassignment(db: Session):
    """미션을 다른 부스로 옮겨도 과거 집계가 이동하지 않는다."""
    f = make_festival(db)
    b1, m = make_booth_mission(db, f)
    b2 = Booth(festival_id=f.id, name="닭갈비 골목", booth_type=BoothType.FOOD)
    db.add(b2)
    db.flush()

    p = make_participant(db, f)
    row = grant(db, f, p, m, b1)

    m.booth_id = b2.id  # 운영 중 미션 재배치
    db.flush()
    db.refresh(row)
    assert row.booth_id == b1.id  # 스냅샷은 그대로


# ── 참여 이력 정합성 ────────────────────────────────────────────────────────


def test_completed_requires_completed_at(db: Session):
    f = make_festival(db)
    b, m = make_booth_mission(db, f)
    p = make_participant(db, f)

    with pytest.raises(IntegrityError):
        grant(db, f, p, m, b, completed_at=None)


def test_participant_code_format_enforced(db: Session):
    f = make_festival(db)
    db.add(Participant(festival_id=f.id, code="bad-code", secret_hash="x"))
    with pytest.raises(IntegrityError):
        db.flush()


# ── 축제 기간 ───────────────────────────────────────────────────────────────


def test_end_before_start_is_rejected(db: Session):
    with pytest.raises(IntegrityError):
        make_festival(db, starts_on=date(2026, 10, 12), ends_on=date(2026, 10, 10))


def test_single_day_festival_is_one_day(db: Session):
    f = make_festival(db, starts_on=date(2026, 10, 10), ends_on=date(2026, 10, 10))
    assert f.duration_days == 1


def test_duration_counts_both_ends(db: Session):
    f = make_festival(db)  # 10/10 ~ 10/12
    assert f.duration_days == 3


def test_zero_visitors_rejected(db: Session):
    with pytest.raises(IntegrityError):
        make_festival(db, expected_visitors=0)


# ── 부스 ────────────────────────────────────────────────────────────────────


def test_booth_name_unique_per_festival_case_insensitive(db: Session):
    f = make_festival(db)
    db.add(Booth(festival_id=f.id, name="막국수 체험존", booth_type=BoothType.EXPERIENCE))
    db.flush()
    db.add(Booth(festival_id=f.id, name="막국수 체험존", booth_type=BoothType.FOOD))
    with pytest.raises(IntegrityError):
        db.flush()


def test_archived_booth_frees_the_name(db: Session):
    """보관한 부스의 이름은 다시 쓸 수 있어야 한다."""
    f = make_festival(db)
    b = Booth(festival_id=f.id, name="막국수 체험존", booth_type=BoothType.EXPERIENCE)
    db.add(b)
    db.flush()
    b.archived_at = datetime.now(UTC)
    db.flush()

    db.add(Booth(festival_id=f.id, name="막국수 체험존", booth_type=BoothType.FOOD))
    db.flush()  # 예외 없이 통과


def test_qr_secret_is_autogenerated(db: Session):
    """pgcrypto 의 gen_random_bytes 기본값이 실제로 동작하는지."""
    f = make_festival(db)
    b = Booth(festival_id=f.id, name="안내소", booth_type=BoothType.INFORMATION)
    db.add(b)
    db.flush()
    db.refresh(b)
    assert b.qr_secret is not None
    assert len(b.qr_secret) == 32


# ── 스탬프 보드 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("rows", "cols"), [(2, 2), (2, 3), (3, 3)])
def test_supported_grids_accepted(db: Session, rows, cols):
    f = make_festival(db, name=f"축제{rows}{cols}")
    db.add(StampBoard(festival_id=f.id, rows=rows, cols=cols))
    db.flush()


def test_unsupported_grid_rejected(db: Session):
    f = make_festival(db)
    db.add(StampBoard(festival_id=f.id, rows=3, cols=2))  # 3×2 는 미지원
    with pytest.raises(IntegrityError):
        db.flush()


def test_board_total_tiles(db: Session):
    f = make_festival(db)
    board = StampBoard(festival_id=f.id, rows=3, cols=3)
    db.add(board)
    db.flush()
    assert board.total_tiles == 9


# ── 기획 상세 헬퍼 ──────────────────────────────────────────────────────────


def test_planned_type_count_ignores_zeros(db: Session):
    """진단 ③에서 쓰는 유형 수. 0인 항목은 유형으로 세지 않는다."""
    f = make_festival(db)
    plan = db.get(FestivalPlan, f.id)
    plan.planned_food = 12
    plan.planned_performance = 6
    plan.planned_experience = 0
    db.flush()
    assert plan.planned_type_count == 2
    assert plan.planned_program_total == 18


# ── 스태프 권한 ─────────────────────────────────────────────────────────────


def test_non_booth_manager_cannot_have_booth(db: Session):
    from festaflow.models import FestivalStaff
    from festaflow.models.enums import StaffRole

    f = make_festival(db)
    b, _ = make_booth_mission(db, f)
    db.add(
        FestivalStaff(
            festival_id=f.id,
            role=StaffRole.OPERATOR,
            display_name="김운영",
            booth_id=b.id,  # operator 인데 부스 배정 → 차단
            access_code_hash="x",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


# ── 실측 방문객 ─────────────────────────────────────────────────────────────


def test_multiple_visitor_sources_same_day_allowed(db: Session):
    """입구 계수기와 지자체 집계가 다른 건 정상이다. 둘 다 저장돼야 한다."""
    from festaflow.models import VisitorCount
    from festaflow.models.enums import VisitorSource

    f = make_festival(db)
    d = date(2026, 10, 10)
    db.add(VisitorCount(festival_id=f.id, count_date=d, visitors=6200,
                        source=VisitorSource.MANUAL_COUNTER))
    db.add(VisitorCount(festival_id=f.id, count_date=d, visitors=7000,
                        source=VisitorSource.PARTNER))
    db.flush()

    with pytest.raises(IntegrityError):  # 같은 출처 중복은 차단
        db.add(VisitorCount(festival_id=f.id, count_date=d, visitors=6300,
                            source=VisitorSource.MANUAL_COUNTER))
        db.flush()


# ── 보상 캠페인 ─────────────────────────────────────────────────────────────


def test_campaign_window_must_be_forward(db: Session):
    from festaflow.models import RewardCampaign

    f = make_festival(db)
    b, _ = make_booth_mission(db, f)
    now = datetime.now(UTC)
    db.add(
        RewardCampaign(
            festival_id=f.id, booth_id=b.id, title="지역상점존 보너스",
            message="지금 방문하면 +50P", bonus_points=50,
            starts_at=now, ends_at=now - timedelta(minutes=1),
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
