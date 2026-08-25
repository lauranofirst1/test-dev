"""교내 행사 — 학번 신원과 특강 출결.

이 파일이 지키는 것은 둘입니다.

**1. 1 학번 = 1 참여자.** 종이 스티커를 여러 장 붙이던 부정이 디지털에서는
"참여 코드 여러 개 받기"로 나타납니다. 익명 코드는 무제한 발급되므로, 학번을
받지 않으면 투표 제한이 아무것도 막지 못합니다.

**2. 출튀는 입장 스캔으로 막히지 않는다.** 예고 없는 시점에 여러 번 확인해야
"그 시간에 그 자리에 있었다"가 증명됩니다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Exhibit,
    Festival,
    LectureSession,
    Organization,
    Participant,
    SessionAttendance,
    StampBoard,
)
from festaflow.models.enums import IdentityMode
from festaflow.services import attendance as att


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="한림대학교 SW중심대학사업단")
    db.add(o)
    db.flush()
    return o


@pytest.fixture
def client(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _festival(db: Session, org: Organization, mode: IdentityMode) -> Festival:
    f = Festival(
        organization_id=org.id,
        name="제8회 Hallym SW Week",
        region="강원특별자치도 춘천시",
        venue="한림대학교 공학관",
        starts_on=date(2026, 11, 3),
        ends_on=date(2026, 11, 7),
        expected_visitors=1200,
        total_budget=11800000,
        identity_mode=mode,
    )
    db.add(f)
    db.flush()
    board = StampBoard(festival_id=f.id, rows=2, cols=2)
    db.add(board)
    db.flush()
    return f


@pytest.fixture
def campus(db: Session, org: Organization) -> Festival:
    return _festival(db, org, IdentityMode.STUDENT_ID)


def _err(r) -> str:
    return r.json()["error"]["code"]


def _join(client, festival, student_no=None):
    body = {"student_no": student_no} if student_no is not None else {}
    return client.post(f"/api/festivals/{festival.id}/participants", json=body)


# ── 1 학번 = 1 참여자 ───────────────────────────────────────────────────────


def test_student_festival_requires_a_student_number(client, campus, db):
    db.commit()
    r = _join(client, campus)
    assert r.status_code == 422
    assert _err(r) == "STUDENT_NO_REQUIRED"


def test_same_student_number_never_creates_a_second_participant(client, campus, db):
    """**여기가 투표 부정 방지의 뿌리다.**

    익명 축제에서는 새로고침할 때마다 새 참여 코드가 나온다. 학번 축제에서
    그러면 스티커를 여러 장 붙이던 행위가 그대로 재현된다.
    """
    db.commit()

    first = _join(client, campus, "20251234")
    assert first.status_code == 201, first.text
    assert first.json()["resumed"] is False

    again = _join(client, campus, "20251234")
    assert again.status_code == 201
    assert again.json()["resumed"] is True
    # 같은 참여자다. 코드가 같아야 한다.
    assert again.json()["code"] == first.json()["code"]

    assert db.query(Participant).filter(Participant.festival_id == campus.id).count() == 1


def test_reissue_rotates_the_secret_so_the_old_device_stops(client, campus, db):
    """기기를 바꾼 학생은 이어받고, 옛 기기는 그 순간 끊긴다."""
    db.commit()
    first = _join(client, campus, "20251234").json()
    second = _join(client, campus, "20251234").json()

    assert second["secret"] != first["secret"]

    old = client.get(
        f"/api/festivals/{campus.id}/participants/me",
        headers={"X-Participant-Secret": first["secret"]},
    )
    assert old.status_code == 401

    new = client.get(
        f"/api/festivals/{campus.id}/participants/me",
        headers={"X-Participant-Secret": second["secret"]},
    )
    assert new.status_code == 200


def test_reissue_count_is_visible_to_operators(client, campus, db):
    """남의 학번을 넣어 가로채려는 시도는 이 숫자로 드러난다."""
    db.commit()
    for _ in range(3):
        _join(client, campus, "20251234")

    p = db.query(Participant).filter(Participant.festival_id == campus.id).one()
    db.refresh(p)
    assert p.recovery_attempts == 2  # 최초 발급은 재발급이 아니다


@pytest.mark.parametrize("messy", ["2025-1234", " 20251234 ", "2025 1234"])
def test_student_number_spelling_does_not_create_a_second_account(client, campus, db, messy):
    """`2025-1234` 와 `20251234` 가 다른 학번이면 두 표기로 두 번 투표할 수 있다."""
    db.commit()
    base = _join(client, campus, "20251234").json()
    again = _join(client, campus, messy).json()
    assert again["code"] == base["code"]
    assert db.query(Participant).filter(Participant.festival_id == campus.id).count() == 1


def test_anonymous_festival_ignores_a_student_number(client, db, org):
    """받지 않겠다고 한 것을 조용히 저장해 두면 그 약속이 거짓이 된다."""
    festival = _festival(db, org, IdentityMode.ANONYMOUS)
    db.commit()

    r = _join(client, festival, "20251234")
    assert r.status_code == 201
    p = db.query(Participant).filter(Participant.festival_id == festival.id).one()
    assert p.student_no is None
    # 익명 축제는 여전히 무제한 발급이다 — 그게 그쪽의 옳은 설계다.
    _join(client, festival, "20251234")
    assert db.query(Participant).filter(Participant.festival_id == festival.id).count() == 2


def test_public_screen_tells_the_client_whether_to_ask(client, campus, db, org):
    db.commit()
    body = client.get(f"/api/festivals/{campus.id}/public").json()
    assert body["identity_mode"] == "student_id"


def test_공개_응답이_특강과_전시_유무를_알려준다(client, campus, db) -> None:
    """관객 화면의 하단 탭이 이 둘을 본다. 없는데 탭을 띄우면 눌러도
    "아직 없습니다" 만 나오고, 죽은 링크가 있는 메뉴는 없는 메뉴보다 나쁘다."""
    db.commit()

    empty = client.get(f"/api/festivals/{campus.id}/public").json()

    assert empty["has_lectures"] is False
    assert empty["has_exhibits"] is False


def test_특강을_만들면_탭이_생긴다(client, campus, db, lecture) -> None:
    db.commit()

    body = client.get(f"/api/festivals/{campus.id}/public").json()

    assert body["has_lectures"] is True
    assert body["has_exhibits"] is False


def test_내린_작품은_탭을_켜지_않는다(client, campus, db) -> None:
    """작품을 내리면 관객이 열 것이 없다. 개수가 아니라 살아 있는지를 본다."""
    db.add(
        Exhibit(
            festival_id=campus.id,
            entry_no=1,
            title="내린 작품",
            is_active=False,
        )
    )
    db.commit()

    body = client.get(f"/api/festivals/{campus.id}/public").json()

    assert body["has_exhibits"] is False


def test_student_number_never_leaks_to_participants(client, campus, db):
    db.commit()
    issued = _join(client, campus, "20251234").json()
    headers = {"X-Participant-Secret": issued["secret"]}

    for path in ("/public", "/participants/me"):
        r = client.get(f"/api/festivals/{campus.id}{path}", headers=headers)
        assert r.status_code == 200, r.text
        assert "20251234" not in r.text
        assert "student_no" not in r.text


# ── 특강 출결 ───────────────────────────────────────────────────────────────


@pytest.fixture
def lecture(db: Session, campus: Festival) -> LectureSession:
    s = LectureSession(
        festival_id=campus.id,
        title="인공지능, 무엇이고 어디로 가고 있는가?",
        speaker="정송",
        affiliation="KAIST",
        location="공학관 1163호",
        starts_at=datetime(2026, 11, 3, 4, 30, tzinfo=UTC),
        ends_at=datetime(2026, 11, 3, 6, 30, tzinfo=UTC),
        required_checkins=2,
        grants_excused_absence=True,
        qr_secret=b"L" * 32,
    )
    db.add(s)
    db.flush()
    return s


def _open_checkpoint(client, campus, lecture):
    r = client.post(f"/api/festivals/{campus.id}/lectures/{lecture.id}/checkpoints")
    assert r.status_code == 201, r.text
    return r.json()


def _checkin(client, campus, lecture, cp, headers):
    return client.post(
        f"/api/festivals/{campus.id}/lectures/{lecture.id}/checkin",
        json={"checkpoint_id": cp["checkpoint_id"], "token": _token_of(cp)},
        headers=headers,
    )


def _token_of(cp) -> str:
    return cp["scan_path"].split("&t=")[1]


def test_checkin_link_carries_the_session(client, campus, lecture, db):
    """참여자 화면이 어느 특강인지 알아야 한다. 90초짜리 화면에서 추측할 여유가 없다."""
    db.commit()
    cp = _open_checkpoint(client, campus, lecture)
    assert f"s={lecture.id}" in cp["scan_path"]
    assert f"c={cp['checkpoint_id']}" in cp["scan_path"]


def test_one_checkin_is_not_enough_when_two_are_required(client, campus, lecture, db):
    """입장 스캔 한 번으로 출석이 되면 출튀가 그대로 통한다."""
    db.commit()
    issued = _join(client, campus, "20251234").json()
    headers = {"X-Participant-Secret": issued["secret"]}

    cp = _open_checkpoint(client, campus, lecture)
    r = _checkin(client, campus, lecture, cp, headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["was_new"] is True
    assert body["attendance"]["checked"] == 1
    assert body["attendance"]["is_met"] is False
    assert body["attendance"]["remaining"] == 1


def test_two_checkins_meet_the_requirement(client, campus, lecture, db):
    db.commit()
    issued = _join(client, campus, "20251234").json()
    headers = {"X-Participant-Secret": issued["secret"]}

    for _ in range(2):
        cp = _open_checkpoint(client, campus, lecture)
        r = _checkin(client, campus, lecture, cp, headers)
        assert r.status_code == 200, r.text

    assert r.json()["attendance"]["is_met"] is True
    assert r.json()["attendance"]["remaining"] == 0


def test_checking_the_same_checkpoint_twice_counts_once(client, campus, lecture, db):
    """한 체크인에 두 번 찍어 요구 횟수를 채울 수는 없다."""
    db.commit()
    issued = _join(client, campus, "20251234").json()
    headers = {"X-Participant-Secret": issued["secret"]}

    cp = _open_checkpoint(client, campus, lecture)
    first = _checkin(client, campus, lecture, cp, headers)
    second = _checkin(client, campus, lecture, cp, headers)

    assert first.json()["was_new"] is True
    # 두 번째는 오류가 아니다 — 이미 찍혔다는 사실을 그대로 알려준다.
    assert second.status_code == 200
    assert second.json()["was_new"] is False
    assert second.json()["attendance"]["checked"] == 1
    assert db.query(SessionAttendance).filter(
        SessionAttendance.session_id == lecture.id
    ).count() == 1


def test_a_closed_checkpoint_no_longer_accepts(client, campus, lecture, db):
    """계속 열어 두면 늦게 온 사람도 다 찍혀서 아무것도 증명하지 못한다."""
    db.commit()
    issued = _join(client, campus, "20251234").json()
    headers = {"X-Participant-Secret": issued["secret"]}

    cp = _open_checkpoint(client, campus, lecture)
    # 이미 열렸다 닫힌 체크인으로 만든다. 여는 시각도 함께 밀어야 한다 —
    # `closes_at > opens_at` 제약이 "열리기 전에 닫힌" 상태를 막는다.
    from festaflow.models import SessionCheckpoint

    row = db.get(SessionCheckpoint, cp["checkpoint_id"])
    row.opens_at = datetime.now(UTC) - timedelta(minutes=5)
    row.closes_at = datetime.now(UTC) - timedelta(minutes=4)
    db.commit()

    r = _checkin(client, campus, lecture, cp, headers)
    assert r.status_code == 410
    assert _err(r) == "CHECKPOINT_CLOSED"


def test_a_token_from_another_lecture_is_refused(client, campus, lecture, db):
    """다른 강의의 QR 로 출석되면 두 강의를 동시에 들을 수 있게 된다."""
    other = LectureSession(
        festival_id=campus.id,
        title="다른 특강",
        starts_at=datetime(2026, 11, 5, 4, 30, tzinfo=UTC),
        ends_at=datetime(2026, 11, 5, 6, 30, tzinfo=UTC),
        qr_secret=b"Z" * 32,
    )
    db.add(other)
    db.commit()

    issued = _join(client, campus, "20251234").json()
    headers = {"X-Participant-Secret": issued["secret"]}
    cp = _open_checkpoint(client, campus, lecture)

    forged = client.post(
        f"/api/festivals/{campus.id}/lectures/{lecture.id}/checkin",
        json={"checkpoint_id": cp["checkpoint_id"], "token": "AAAAAAAAAAAA"},
        headers=headers,
    )
    assert forged.status_code == 400
    assert _err(forged) == "CHECKIN_TOKEN_INVALID"


def test_checkin_qr_rotates(client, campus, lecture, db):
    """체크인 QR 이 고정이면 사진 한 장이 단톡방에 돌면서 출결이 무너진다."""
    db.commit()
    cp = _open_checkpoint(client, campus, lecture)

    now = datetime.now(UTC)
    later = now + timedelta(seconds=120)
    a = att.checkpoint_token(lecture.qr_secret, cp["checkpoint_id"], att.security.current_window(now))
    b = att.checkpoint_token(
        lecture.qr_secret, cp["checkpoint_id"], att.security.current_window(later)
    )
    assert a != b
    assert att.match_checkpoint_window(lecture.qr_secret, cp["checkpoint_id"], b, now) is None


def test_roster_carries_student_numbers_for_the_excused_absence_list(
    client, campus, lecture, db
):
    """공결을 처리하려면 학교에 낼 명단이 필요하다. 해시만 두면 이게 불가능하다."""
    db.commit()
    met = _join(client, campus, "20251234").json()
    short = _join(client, campus, "20255678").json()

    cp1 = _open_checkpoint(client, campus, lecture)
    for who in (met, short):
        _checkin(client, campus, lecture, cp1, {"X-Participant-Secret": who["secret"]})
    cp2 = _open_checkpoint(client, campus, lecture)
    _checkin(client, campus, lecture, cp2, {"X-Participant-Secret": met["secret"]})

    body = client.get(f"/api/festivals/{campus.id}/lectures/{lecture.id}/roster").json()
    assert body["grants_excused_absence"] is True
    assert body["opened_checkpoints"] == 2
    assert body["total"] == 2
    assert body["met_count"] == 1

    by_no = {r["student_no"]: r for r in body["rows"]}
    assert by_no["20251234"]["is_met"] is True
    assert by_no["20255678"]["is_met"] is False
    assert by_no["20255678"]["checked"] == 1


def test_my_attendance_shows_what_i_missed(client, campus, lecture, db):
    """몇 번을 놓쳤는지 스스로 볼 수 있어야 이의를 제기할 수 있다."""
    db.commit()
    issued = _join(client, campus, "20251234").json()
    headers = {"X-Participant-Secret": issued["secret"]}

    _open_checkpoint(client, campus, lecture)  # 놓친 회차
    cp = _open_checkpoint(client, campus, lecture)
    _checkin(client, campus, lecture, cp, headers)

    mine = client.get(f"/api/festivals/{campus.id}/lectures/me", headers=headers).json()
    assert len(mine) == 1
    assert mine[0]["opened"] == 2
    assert mine[0]["checked"] == 1
    assert mine[0]["is_met"] is False
