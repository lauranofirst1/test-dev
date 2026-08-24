"""공결 확인서 — 교수님이 계정 없이 진위를 확인한다.

공결을 인정하는 사람은 특강 주최자가 아니라 **그 시간 정규 수업 담당 교수**이고,
수십 명입니다. 그들에게 계정을 나눠 주는 절차는 만들어도 쓰이지 않습니다.
대신 학생이 스스로 증명을 건네고, 코드가 그 증명의 진위를 담보합니다.

이 파일이 지키는 것은 셋입니다.

**1. 코드는 추측할 수 없다.** 학번이나 특강 id 에서 유도되지 않는다.
**2. 확인서는 스냅샷이 아니다.** 출결이 정정되면 확인 결과도 함께 바뀐다.
**3. 새어 나가는 정보는 최소다.** 교수는 "이 학생이 왔는가" 를 확인하려는 것이지
명단을 수집하려는 것이 아니다.
"""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Festival,
    LectureSession,
    Organization,
    Participant,
    SessionAttendance,
    SessionCheckpoint,
)
from festaflow.models.enums import IdentityMode
from festaflow.services import attendance as svc

_codes = itertools.count(1)


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


@pytest.fixture
def festival(db: Session, org: Organization) -> Festival:
    f = Festival(
        organization_id=org.id,
        name="제8회 Hallym SW Week",
        region="강원특별자치도 춘천시",
        venue="한림대학교 공학관",
        starts_on=date(2026, 11, 3),
        ends_on=date(2026, 11, 7),
        expected_visitors=1200,
        total_budget=11800000,
        identity_mode=IdentityMode.STUDENT_ID,
    )
    db.add(f)
    db.flush()
    return f


@pytest.fixture
def session_(db: Session, festival: Festival) -> LectureSession:
    now = datetime.now(UTC)
    s = LectureSession(
        festival_id=festival.id,
        title="생성형 AI 실무 특강",
        speaker="김한림",
        starts_at=now - timedelta(hours=2),
        ends_at=now,
        required_checkins=2,
        grants_excused_absence=True,
    )
    db.add(s)
    db.flush()
    return s


def _student(db: Session, festival: Festival, student_no: str) -> tuple[Participant, str]:
    secret = security.generate_participant_secret()
    p = Participant(
        festival_id=festival.id,
        code=f"FF-{next(_codes):08d}",
        student_no=student_no,
        secret_hash=security.hash_participant_secret(secret),
    )
    db.add(p)
    db.flush()
    return p, secret


def _check_in(db: Session, session_: LectureSession, participant: Participant, n: int) -> None:
    at = datetime.now(UTC)
    for i in range(n):
        cp = SessionCheckpoint(
            session_id=session_.id,
            sequence=i + 1,
            opens_at=at - timedelta(minutes=30 - i),
            closes_at=at - timedelta(minutes=29 - i),
        )
        db.add(cp)
        db.flush()
        db.add(
            SessionAttendance(
                session_id=session_.id,
                checkpoint_id=cp.id,
                participant_id=participant.id,
                checked_at=at,
            )
        )
    db.flush()


def _issue(client: TestClient, festival, session_, secret: str):
    return client.get(
        f"/api/festivals/{festival.id}/lectures/{session_.id}/certificate",
        headers={"X-Participant-Secret": secret},
    )


# ── 발급 ────────────────────────────────────────────────────────────────────


def test_학생이_확인서를_발급한다(
    db: Session, client: TestClient, festival, session_
) -> None:
    p, secret = _student(db, festival, "20211234")
    _check_in(db, session_, p, 2)
    db.commit()

    r = _issue(client, festival, session_, secret)

    assert r.status_code == 200
    body = r.json()
    assert len(body["code"]) == 16
    assert body["verify_path"] == f"/verify/{festival.id}/{body['code']}"


def test_같은_코드가_다시_나온다(
    db: Session, client: TestClient, festival, session_
) -> None:
    """HMAC 으로 파생되므로 발급이라기보다 조회다. 잃어버려도 다시 열면 그만이다."""
    p, secret = _student(db, festival, "20211234")
    _check_in(db, session_, p, 1)
    db.commit()

    first = _issue(client, festival, session_, secret).json()["code"]
    second = _issue(client, festival, session_, secret).json()["code"]

    assert first == second


def test_안_찍은_사람에게는_발급하지_않는다(
    db: Session, client: TestClient, festival, session_
) -> None:
    """"안 왔다" 를 증명하는 종이는 확인서가 아니다."""
    _, secret = _student(db, festival, "20215678")
    db.commit()

    r = _issue(client, festival, session_, secret)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "NO_ATTENDANCE"


def test_남의_확인서는_발급할_수_없다(
    db: Session, client: TestClient, festival, session_
) -> None:
    """본인 secret 으로만 열린다. 학번을 안다고 남의 확인서가 나오면 안 된다."""
    mine, my_secret = _student(db, festival, "20211234")
    other, _ = _student(db, festival, "20215678")
    _check_in(db, session_, mine, 2)
    _check_in(db, session_, other, 2)
    db.commit()

    code = _issue(client, festival, session_, my_secret).json()["code"]
    verified = client.get(
        f"/api/festivals/{festival.id}/attendance-certificates/{code}"
    ).json()

    assert verified["participant_code"] == mine.code
    assert verified["participant_code"] != other.code


# ── 확인 ────────────────────────────────────────────────────────────────────


def test_교수님은_계정_없이_확인한다(
    db: Session, client: TestClient, festival, session_
) -> None:
    p, secret = _student(db, festival, "20211234")
    _check_in(db, session_, p, 2)
    db.commit()
    code = _issue(client, festival, session_, secret).json()["code"]

    # 어떤 인증 헤더도 없다.
    r = client.get(f"/api/festivals/{festival.id}/attendance-certificates/{code}")

    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "생성형 AI 실무 특강"
    assert body["speaker"] == "김한림"
    assert body["checked"] == 2
    assert body["required"] == 2
    assert body["is_met"] is True
    assert body["grants_excused_absence"] is True


def test_학번을_통째로_보여주지_않는다(
    db: Session, client: TestClient, festival, session_
) -> None:
    """교수는 "이 학생이 왔는가" 를 확인하려는 것이지 명단을 수집하려는 것이 아니다."""
    p, secret = _student(db, festival, "20211234")
    _check_in(db, session_, p, 2)
    db.commit()
    code = _issue(client, festival, session_, secret).json()["code"]

    r = client.get(f"/api/festivals/{festival.id}/attendance-certificates/{code}")

    assert r.json()["student_no_masked"] == "*****234"
    # 원문이 응답 어디에도 없어야 한다.
    assert "20211234" not in r.text


def test_틀린_코드는_404(db: Session, client: TestClient, festival, session_) -> None:
    """형식이 맞는지 틀린지를 구분해 주면 코드를 훑어 볼 수 있다."""
    r = client.get(f"/api/festivals/{festival.id}/attendance-certificates/AAAAAAAAAAAAAAAA")

    assert r.status_code == 404


def test_남의_축제_코드로는_열리지_않는다(
    db: Session, client: TestClient, org: Organization, festival, session_
) -> None:
    p, secret = _student(db, festival, "20211234")
    _check_in(db, session_, p, 2)
    db.commit()
    code = _issue(client, festival, session_, secret).json()["code"]

    other = Festival(
        organization_id=org.id,
        name="옆 행사",
        region="강원특별자치도 춘천시",
        venue="다른 곳",
        starts_on=date(2026, 11, 3),
        ends_on=date(2026, 11, 7),
        expected_visitors=100,
        total_budget=1000000,
    )
    db.add(other)
    db.commit()

    r = client.get(f"/api/festivals/{other.id}/attendance-certificates/{code}")

    assert r.status_code == 404


def test_출결이_정정되면_확인_결과도_바뀐다(
    db: Session, client: TestClient, festival, session_
) -> None:
    """확인서는 기록이 아니라 **가리키는 손가락**이다. 스냅샷으로 저장하면
    나중에 출결이 정정됐을 때 종이만 옛 사실을 말한다."""
    p, secret = _student(db, festival, "20211234")
    _check_in(db, session_, p, 1)
    db.commit()
    code = _issue(client, festival, session_, secret).json()["code"]

    url = f"/api/festivals/{festival.id}/attendance-certificates/{code}"
    before = client.get(url).json()
    assert before["checked"] == 1
    assert before["is_met"] is False

    # 한 번 더 찍었다.
    _check_in(db, session_, p, 1)
    db.commit()

    after = client.get(url).json()
    assert after["checked"] == 2
    assert after["is_met"] is True


def test_코드는_학번이나_id_에서_유도되지_않는다(db: Session, festival, session_) -> None:
    """옆 사람 학번을 안다고 그 사람 확인서를 만들 수 없어야 한다."""
    a, _ = _student(db, festival, "20211234")
    b, _ = _student(db, festival, "20211235")
    db.flush()

    code_a = security.attendance_certificate_code(session_.qr_secret, session_.id, a.id)
    code_b = security.attendance_certificate_code(session_.qr_secret, session_.id, b.id)

    assert code_a != code_b
    assert str(a.id) not in code_a
    assert "2021" not in code_a
    # 특강이 다르면 같은 학생이라도 다른 코드다.
    other = LectureSession(
        festival_id=festival.id,
        title="다른 특강",
        starts_at=session_.starts_at,
        ends_at=session_.ends_at,
        required_checkins=1,
    )
    db.add(other)
    db.flush()
    assert (
        security.attendance_certificate_code(other.qr_secret, other.id, a.id) != code_a
    )


def test_마스킹_규칙(db: Session) -> None:
    assert svc.mask_student_no("20211234") == "*****234"
    assert svc.mask_student_no("123") == "***"
    assert svc.mask_student_no("12") == "**"
    assert svc.mask_student_no(None) is None
    assert svc.mask_student_no("") is None
