"""부스 QR 체험 — 퀴즈·안내. docs/05-booth-experience.md, 계약 §11.

여기서 지키는 것은 하나입니다. **정답은 서버 밖으로 나가지 않고, 채점도 서버만 한다.**
정답이 화면으로 내려가면 개발자 도구를 여는 것만으로 축제 전체가 통과됩니다.
부스 QR 토큰이 현장 방문을 보장하더라도 퀴즈의 의미는 그때 사라집니다.

두 번째는 시도 횟수입니다. 오답은 참여 이력을 만들지 않으므로(집계에 섞이면 안 되므로)
시도를 따로 세야 하고, 그 기록이 실패 응답과 함께 롤백되면 새로고침 한 번으로
무한히 다시 풀 수 있게 됩니다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import (
    Booth,
    Festival,
    Mission,
    MissionAttempt,
    Organization,
    Participation,
    StampBoard,
    StampTile,
)
from festaflow.models.enums import (
    BoothQrMode,
    BoothType,
    BoothVerifyMode,
    ExperienceType,
)
from festaflow.services import experience
from festaflow.services import grants as svc

QUIZ = {
    "question": "춘천 막국수의 주재료는?",
    "choices": ["메밀", "밀", "쌀", "감자"],
    "answer_index": 0,
    "max_attempts": 3,
    "hint": "겨울에 잘 자라는 곡물입니다",
}


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="춘천시문화재단")
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
        name="춘천 가을 먹거리 축제",
        region="강원특별자치도 춘천시",
        venue="공지천 조각공원",
        starts_on=date(2026, 10, 10),
        ends_on=date(2026, 10, 12),
        expected_visitors=18000,
        total_budget=240000000,
    )
    db.add(f)
    db.flush()
    board = StampBoard(festival_id=f.id, rows=2, cols=2)
    db.add(board)
    db.flush()
    for idx in range(board.total_tiles):
        db.add(StampTile(board_id=board.id, board_version=board.version, tile_index=idx))
    db.flush()
    return f


def _quiz_booth(db: Session, festival: Festival, config: dict | None = None):
    booth = Booth(
        festival_id=festival.id,
        name="막국수 체험존",
        booth_type=BoothType.EXPERIENCE,
        verify_mode=BoothVerifyMode.PARTICIPANT_SCAN,
        # 체험 테스트는 회전 QR 기준이다. 모델 기본값은 인쇄다.
        qr_mode=BoothQrMode.ROTATING,
        qr_secret=b"x" * 32,
        use_experience=True,
    )
    db.add(booth)
    db.flush()
    mission = Mission(
        festival_id=festival.id,
        booth_id=booth.id,
        title="막국수 퀴즈",
        points=100,
        experience_type=ExperienceType.QUIZ,
        experience_config=config if config is not None else dict(QUIZ),
    )
    db.add(mission)
    db.flush()
    return booth, mission


def _issue(client, festival):
    r = client.post(f"/api/festivals/{festival.id}/participants")
    assert r.status_code == 201, r.text
    return r.json()["code"], {"X-Participant-Secret": r.json()["secret"]}


def _token(booth: Booth) -> str:
    return security.booth_scan_token(booth.qr_secret, booth.id, security.current_window())


def _err(r) -> str:
    return r.json()["error"]["code"]


def _details(r) -> dict:
    return r.json()["error"]["details"]


def _submit(client, festival, booth, mission, headers, response):
    return client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={
            "booth_id": booth.id,
            "token": _token(booth),
            "mission_id": mission.id,
            "response": response,
        },
        headers=headers,
    )


# ── 정답 노출 (이 파일의 존재 이유) ─────────────────────────────────────────


def test_scan_never_reveals_the_answer(client, festival, db):
    """`GET /scan` 응답 어디에도 answer_index 가 없어야 한다."""
    booth, mission = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.get(
        f"/api/festivals/{festival.id}/scan",
        params={"booth_id": booth.id, "token": _token(booth)},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert "answer_index" not in r.text

    m = r.json()["missions"][0]
    assert m["experience_type"] == "quiz"
    # 문항과 보기는 화면이 그려야 하므로 내려간다.
    assert m["experience_config"]["question"] == QUIZ["question"]
    assert m["experience_config"]["choices"] == QUIZ["choices"]
    assert m["experience_config"]["hint"] == QUIZ["hint"]
    assert m["attempts_left"] == 3


def test_public_festival_never_reveals_the_answer(client, festival, db):
    """참여 전 공개 화면에도 설정이 새면 안 된다."""
    _quiz_booth(db, festival)
    db.commit()
    r = client.get(f"/api/festivals/{festival.id}/public")
    assert r.status_code == 200
    assert "answer_index" not in r.text
    assert "메밀" not in r.text


# ── 채점 ────────────────────────────────────────────────────────────────────


def test_correct_answer_grants_and_records_attempt_count(client, festival, db):
    booth, mission = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = _submit(client, festival, booth, mission, headers, {"choice_index": 0})
    assert r.status_code == 200, r.text
    assert r.json()["participation"]["attempt_count"] == 1
    assert r.json()["board_progress"]["revealed_count"] == 1


def test_wrong_answer_does_not_create_a_participation(client, festival, db):
    """오답은 집계에 섞이면 안 된다 — 참여 이력을 만들지 않는다."""
    booth, mission = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = _submit(client, festival, booth, mission, headers, {"choice_index": 1})
    assert r.status_code == 422
    assert _err(r) == "EXPERIENCE_WRONG_ANSWER"
    assert _details(r)["attempts_left"] == 2

    assert db.query(Participation).filter(Participation.mission_id == mission.id).count() == 0


def test_wrong_answer_survives_the_failed_response(client, festival, db):
    """시도 기록이 실패 응답과 함께 롤백되면 새로고침으로 무한 재시도가 된다."""
    booth, mission = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    _submit(client, festival, booth, mission, headers, {"choice_index": 1})

    row = db.query(MissionAttempt).filter(MissionAttempt.mission_id == mission.id).one()
    assert row.attempt_count == 1

    # 다시 물어봐도 남은 횟수가 줄어 있어야 한다.
    r = client.get(
        f"/api/festivals/{festival.id}/scan",
        params={"booth_id": booth.id, "token": _token(booth)},
        headers=headers,
    )
    assert r.json()["missions"][0]["attempts_left"] == 2


def test_attempts_run_out_and_then_even_the_right_answer_is_refused(client, festival, db):
    """소진 뒤에는 정답이어도 받지 않는다. 아니면 마지막에 답을 알아내면 그만이다."""
    booth, mission = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    for expected_left in (2, 1, 0):
        r = _submit(client, festival, booth, mission, headers, {"choice_index": 3})
        assert r.status_code == 422
        assert _details(r)["attempts_left"] == expected_left

    r = _submit(client, festival, booth, mission, headers, {"choice_index": 0})
    assert r.status_code == 429
    assert _err(r) == "EXPERIENCE_ATTEMPTS_EXCEEDED"
    assert db.query(Participation).filter(Participation.mission_id == mission.id).count() == 0


def test_missing_choice_is_not_counted_as_an_attempt(client, festival, db):
    """보기를 안 고른 건 오답이 아니다. 통신 오류로 시도가 깎이면 안 된다."""
    booth, mission = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = _submit(client, festival, booth, mission, headers, {})
    assert r.status_code == 422
    assert _err(r) == "VALIDATION_FAILED"
    assert db.query(MissionAttempt).count() == 0


def test_client_cannot_claim_correctness(client, festival, db):
    """응답에 correct: true 를 실어 보내도 채점은 서버가 한다."""
    booth, mission = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = _submit(
        client, festival, booth, mission, headers, {"choice_index": 2, "correct": True}
    )
    assert r.status_code == 422
    assert _err(r) == "EXPERIENCE_WRONG_ANSWER"


# ── 안내(info) ──────────────────────────────────────────────────────────────


def test_info_rejects_submission_before_minimum_dwell(client, festival, db):
    """클라이언트가 보낸 체류 시간을 믿지 않는다 — 스캔 시각이 진실이다."""
    booth, mission = _quiz_booth(db, festival)
    mission.experience_type = ExperienceType.INFO
    mission.experience_config = {
        "body": "소양강 스카이워크는 도보 15분 거리입니다.",
        "links": [],
        "min_dwell_seconds": 120,
    }
    db.commit()
    _, headers = _issue(client, festival)

    r = _submit(client, festival, booth, mission, headers, {"dwell_seconds": 9999})
    assert r.status_code == 422
    assert _err(r) == "EXPERIENCE_DWELL_TOO_SHORT"


def test_info_without_dwell_requirement_grants_immediately(client, festival, db):
    booth, mission = _quiz_booth(db, festival)
    mission.experience_type = ExperienceType.INFO
    mission.experience_config = {"body": "안내", "links": [], "min_dwell_seconds": 0}
    db.commit()
    _, headers = _issue(client, festival)

    r = _submit(client, festival, booth, mission, headers, {"dwell_seconds": 3})
    assert r.status_code == 200, r.text


# ── 설정 검증 (운영자가 저장할 때) ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("config", "field"),
    [
        ({"choices": ["가", "나"], "answer_index": 0}, "question"),
        ({"question": "문제", "choices": ["가"], "answer_index": 0}, "choices"),
        ({"question": "문제", "choices": ["가", "나"], "answer_index": 5}, "answer_index"),
        ({"question": "문제", "choices": ["가", "나"]}, "answer_index"),
        (
            {"question": "문제", "choices": ["가", "나"], "answer_index": 0, "max_attempts": 0},
            "max_attempts",
        ),
    ],
)
def test_broken_quiz_config_is_refused_at_save_time(client, festival, config, field):
    """현장에서 깨진 문항을 만나면 그때는 못 고친다. 저장이 마지막 기회다."""
    r = client.post(
        f"/api/festivals/{festival.id}/booths",
        json={
            "name": f"부스-{field}",
            "booth_type": "experience",
            "first_mission": {
                "title": "퀴즈",
                "experience_type": "quiz",
                "experience_config": config,
            },
        },
    )
    assert r.status_code == 422, r.text
    assert _details(r).get("field") == field


def test_saving_a_quiz_normalizes_and_keeps_the_answer_for_operators(client, festival):
    r = client.post(
        f"/api/festivals/{festival.id}/booths",
        json={
            "name": "막국수 체험존",
            "booth_type": "experience",
            "first_mission": {
                "title": "퀴즈",
                "experience_type": "quiz",
                "experience_config": {
                    "question": "  춘천 막국수의 주재료는?  ",
                    "choices": [" 메밀 ", "밀"],
                    "answer_index": 0,
                    "unknown_key": "버려져야 한다",
                },
            },
        },
    )
    assert r.status_code == 201, r.text
    config = r.json()["first_mission"]["experience_config"]
    assert config["question"] == "춘천 막국수의 주재료는?"
    assert config["choices"] == ["메밀", "밀"]
    # 운영자 응답에는 정답이 있어야 한다 — 편집 화면이 그걸 읽는다.
    assert config["answer_index"] == 0
    assert config["max_attempts"] == 3
    assert "unknown_key" not in config


def test_photo_and_survey_are_refused_with_a_reason(client, festival):
    """아직 못 여는 유형은 조용히 저장되지 않고 이유를 말한다."""
    r = client.post(
        f"/api/festivals/{festival.id}/booths",
        json={
            "name": "포토존",
            "booth_type": "etc",
            "first_mission": {"title": "사진", "experience_type": "photo"},
        },
    )
    assert r.status_code == 422
    assert _err(r) == "EXPERIENCE_TYPE_UNSUPPORTED"


# ── 시간 예산 ───────────────────────────────────────────────────────────────
#
# 퀴즈를 30초 안에 못 풀면 지급이 막힙니다. 3번 시도를 허용해 놓고 예산을 60초로
# 두면 설정과 현실이 어긋나고, 참여자는 "정답을 아는데 만료됐다"에 갇힙니다.
# 그래서 체험이 붙은 부스만 예산을 늘립니다 — 나머지는 그대로여야 합니다.


def _token_from(booth: Booth, back: int) -> str:
    """`back` window 전에 발급된 토큰."""
    return security.booth_scan_token(
        booth.qr_secret, booth.id, security.current_window() - back
    )


def test_quiz_booth_accepts_a_token_older_than_the_default_budget(client, festival, db):
    booth, mission = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    # 기본 예산(2 window)을 넘긴 토큰. 도착 확인 부스였다면 만료다.
    r = client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={
            "booth_id": booth.id,
            "token": _token_from(booth, 3),
            "mission_id": mission.id,
            "response": {"choice_index": 0},
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_stamp_booth_budget_is_unchanged(client, festival, db):
    """체험이 없으면 예산은 그대로다. 퀴즈 때문에 전체가 느슨해지면 안 된다."""
    booth, mission = _quiz_booth(db, festival)
    mission.experience_type = ExperienceType.STAMP
    mission.experience_config = {}
    db.commit()
    _, headers = _issue(client, festival)

    r = client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={
            "booth_id": booth.id,
            "token": _token_from(booth, 3),
            "mission_id": mission.id,
        },
        headers=headers,
    )
    assert r.status_code == 410
    assert _err(r) == "SCAN_TOKEN_EXPIRED"


def test_expired_and_forged_stay_distinguishable_with_a_wider_budget(client, festival, db):
    """예산을 늘려도 만료(410)와 위조(400)는 갈려야 한다.

    만료는 다시 스캔하면 되지만 위조는 안 된다. 뭉개면 참여자가 영원히 다시 스캔한다.
    """
    booth, _ = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    expired = client.get(
        f"/api/festivals/{festival.id}/scan",
        params={"booth_id": booth.id, "token": _token_from(booth, 7)},
        headers=headers,
    )
    assert expired.status_code == 410
    assert _err(expired) == "SCAN_TOKEN_EXPIRED"

    forged = client.get(
        f"/api/festivals/{festival.id}/scan",
        params={"booth_id": booth.id, "token": "AAAAAAAAAAAA"},
        headers=headers,
    )
    assert forged.status_code == 400
    assert _err(forged) == "SCAN_TOKEN_INVALID"


def test_countdown_matches_what_the_server_will_accept(client, festival, db):
    """화면이 세는 시간과 서버가 받아주는 시간이 다르면 둘 중 하나는 거짓말이다."""
    booth, _ = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.get(
        f"/api/festivals/{festival.id}/scan",
        params={"booth_id": booth.id, "token": _token_from(booth, 0)},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()

    window = settings.scan_token_window_seconds
    budget = experience.EXPERIENCE_ACCEPTED_WINDOWS * window
    # 남은 시간은 (예산 - window, 예산] 구간에 든다. 현재 window 가 얼마나
    # 지났느냐에 따라 달라지기 때문이다.
    #
    # 하한을 `<` 로 두면 깜빡인다 — 서버가 초를 int 로 잘라 내려주므로 window
    # 끝자락에 요청이 닿으면 120.4 초가 120 으로 잘려 하한과 같아진다.
    assert budget - window <= body["seconds_remaining"] <= budget


# ── 해설 공개 시점 ──────────────────────────────────────────────────────────
#
# 해설은 정답을 설명하는 글이라 **사실상 정답입니다.** 언제 보여주느냐가 전부입니다.
#
#   맞혔을 때            → 보여준다 (악용할 여지가 없고, 읽는 것이 체험의 목적)
#   틀렸는데 시도가 남음  → 숨긴다  (거기 정답이 있으면 남은 시도가 공짜가 된다)
#   틀렸고 시도 소진      → 보여준다 (더 쓸 시도가 없다. 이유를 모른 채 떠나는 게 최악)

EXPLAINED = dict(QUIZ, max_attempts=2, explanation="막국수는 메밀가루로 만듭니다.")


def test_explanation_never_ships_with_the_question(client, festival, db):
    booth, _ = _quiz_booth(db, festival, EXPLAINED)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.get(
        f"/api/festivals/{festival.id}/scan",
        params={"booth_id": booth.id, "token": _token(booth)},
        headers=headers,
    )
    assert r.status_code == 200
    assert "메밀가루로" not in r.text
    assert "explanation" not in r.text


def test_explanation_is_withheld_while_attempts_remain(client, festival, db):
    booth, mission = _quiz_booth(db, festival, EXPLAINED)
    db.commit()
    _, headers = _issue(client, festival)

    r = _submit(client, festival, booth, mission, headers, {"choice_index": 1})
    assert r.status_code == 422
    assert _details(r)["attempts_left"] == 1
    assert "explanation" not in _details(r)


def test_explanation_arrives_when_attempts_run_out(client, festival, db):
    booth, mission = _quiz_booth(db, festival, EXPLAINED)
    db.commit()
    _, headers = _issue(client, festival)

    _submit(client, festival, booth, mission, headers, {"choice_index": 1})
    r = _submit(client, festival, booth, mission, headers, {"choice_index": 2})
    assert r.status_code == 422
    assert _details(r)["attempts_left"] == 0
    assert _details(r)["explanation"] == EXPLAINED["explanation"]


def test_explanation_comes_back_with_a_correct_answer(client, festival, db):
    booth, mission = _quiz_booth(db, festival, EXPLAINED)
    db.commit()
    _, headers = _issue(client, festival)

    r = _submit(client, festival, booth, mission, headers, {"choice_index": 0})
    assert r.status_code == 200, r.text
    assert r.json()["explanation"] == EXPLAINED["explanation"]


def test_quiz_without_explanation_returns_null(client, festival, db):
    booth, mission = _quiz_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = _submit(client, festival, booth, mission, headers, {"choice_index": 0})
    assert r.status_code == 200
    assert r.json()["explanation"] is None


# ── 부스 QR 링크 ────────────────────────────────────────────────────────────


def test_scan_token_gives_an_origin_free_path(client, festival, db):
    """QR 에 담을 링크는 **오리진 없이** 내려와야 한다.

    `scan_url` 은 요청이 도착한 주소로 만들어지는데, 개발 환경에서 그건 API 서버
    (:8000)다. 프런트는 :5173 이고 API 서버에는 `/join` 라우트가 없어서, 그 주소를
    QR 로 만들면 찍는 순간 404 다. 브라우저는 자기 오리진을 붙여 쓴다.
    """
    booth, _ = _quiz_booth(db, festival)
    booth.verify_mode = BoothVerifyMode.PARTICIPANT_SCAN
    db.commit()

    r = client.get(f"/api/festivals/{festival.id}/booths/{booth.id}/scan-token")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["scan_path"].startswith(f"/join/{festival.id}/scan?")
    assert "://" not in body["scan_path"]
    assert f"b={booth.id}" in body["scan_path"]

    # `/join/...` 은 프런트엔드 라우트라 API 가 서빙하지 않는다. QR 이 데려갈
    # 화면이 맞는지가 아니라, **그 안에 담긴 토큰이 유효한지**를 확인한다.
    query = dict(
        pair.split("=", 1) for pair in body["scan_path"].split("?", 1)[1].split("&")
    )
    _, headers = _issue(client, festival)
    scan = client.get(
        f"/api/festivals/{festival.id}/scan",
        params={"booth_id": query["b"], "token": query["t"]},
        headers=headers,
    )
    assert scan.status_code == 200, scan.text
    assert scan.json()["booth_id"] == booth.id


# ── 인쇄 QR (계약 §14.4, 기획서 E4) ─────────────────────────────────────────
#
# 지역 축제 천막 부스에는 태블릿도 상시 전원도 없습니다. 보안을 이유로 장비를
# 강요하면 그 기능은 안 쓰이고, **안 쓰이는 보안은 보안이 아닙니다.**
# 그래서 인쇄가 기본이고 회전 QR 이 상위 옵션입니다.
#
# 대신 인쇄 QR 은 사진으로 찍혀 돌 수 있습니다. 그 약점을 아래 테스트가
# 명시적으로 못박습니다 — 나중에 누가 "원격 완료가 막히는 줄 알았다"고
# 오해하지 않도록.


def _printed_booth(db: Session, festival: Festival, config: dict | None = None):
    booth, mission = _quiz_booth(db, festival, config)
    booth.qr_mode = BoothQrMode.PRINTED
    mission.experience_type = ExperienceType.STAMP
    mission.experience_config = {}
    return booth, mission


def _signature(booth: Booth) -> str:
    return security.booth_print_signature(booth.qr_secret, booth.id)


def test_printed_booth_accepts_a_fixed_signature(client, festival, db):
    booth, mission = _printed_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={"booth_id": booth.id, "signature": _signature(booth), "mission_id": mission.id},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_printed_signature_does_not_expire(client, festival, db):
    """인쇄물은 바뀌지 않는다. 시간이 지나도 같은 서명이 통해야 한다."""
    booth, mission = _printed_booth(db, festival)
    db.commit()

    # 회전 토큰이었다면 진작 만료됐을 만큼 시각을 밀어도 서명은 그대로다.
    later = datetime.now(UTC) + timedelta(hours=8)
    assert security.match_print_signature(booth.qr_secret, booth.id, _signature(booth))
    assert svc.verify_print_signature(booth, _signature(booth), now=later) == (
        security.current_window(later)
    )


def test_printed_booth_refuses_a_rotating_token(client, festival, db):
    """모드를 나눈 의미가 사라지지 않게, 부스가 정한 증명만 받는다."""
    booth, mission = _printed_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={"booth_id": booth.id, "token": _token(booth), "mission_id": mission.id},
        headers=headers,
    )
    assert r.status_code == 400
    assert _err(r) == "SCAN_SIGNATURE_REQUIRED"


def test_rotating_booth_refuses_a_print_signature(client, festival, db):
    booth, mission = _quiz_booth(db, festival)  # 기본이 ROTATING
    db.commit()
    _, headers = _issue(client, festival)

    r = client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={
            "booth_id": booth.id,
            "signature": _signature(booth),
            "mission_id": mission.id,
            "response": {"choice_index": 0},
        },
        headers=headers,
    )
    assert r.status_code == 400
    assert _err(r) == "SCAN_TOKEN_REQUIRED"


def test_print_signature_of_another_booth_is_refused(client, festival, db):
    """같은 축제의 다른 부스 서명으로는 통과할 수 없다."""
    booth, mission = _printed_booth(db, festival)
    other = Booth(
        festival_id=festival.id,
        name="다른 부스",
        booth_type=BoothType.ETC,
        verify_mode=BoothVerifyMode.PARTICIPANT_SCAN,
        qr_mode=BoothQrMode.PRINTED,
        qr_secret=b"y" * 32,
    )
    db.add(other)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={"booth_id": booth.id, "signature": _signature(other), "mission_id": mission.id},
        headers=headers,
    )
    assert r.status_code == 400
    assert _err(r) == "SCAN_TOKEN_INVALID"


def test_rotating_qr_reissue_invalidates_the_printed_sheet(client, festival, db):
    """재발행하면 이미 붙여 둔 인쇄물이 그 순간 무효가 된다 — §14.4.

    인쇄 QR 이 사진으로 돌고 있다는 걸 알게 됐을 때 운영자가 쓸 수 있는
    유일한 수단이다. 실제로 끊기지 않으면 그 수단이 없는 것과 같다.
    """
    booth, mission = _printed_booth(db, festival)
    db.commit()
    old_signature = _signature(booth)

    r = client.post(f"/api/festivals/{festival.id}/booths/{booth.id}/qr/rotate")
    assert r.status_code == 200, r.text
    new_url = r.json()["scan_url"]
    assert old_signature not in new_url

    _, headers = _issue(client, festival)
    refused = client.post(
        f"/api/festivals/{festival.id}/scan-grants",
        json={"booth_id": booth.id, "signature": old_signature, "mission_id": mission.id},
        headers=headers,
    )
    assert refused.status_code == 400
    assert _err(refused) == "SCAN_TOKEN_INVALID"


def test_printed_scan_context_has_no_countdown(client, festival, db):
    """인쇄 QR 은 만료되지 않는다. 카운트다운을 내리면 없는 제한 시간이 생긴다."""
    booth, _ = _printed_booth(db, festival)
    db.commit()
    _, headers = _issue(client, festival)

    r = client.get(
        f"/api/festivals/{festival.id}/scan",
        params={"booth_id": booth.id, "s": _signature(booth)},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["seconds_remaining"] is None
    assert r.json()["qr_mode"] == "printed"


def test_printed_qr_endpoint_returns_no_expiry(client, festival, db):
    booth, _ = _printed_booth(db, festival)
    db.commit()

    body = client.get(f"/api/festivals/{festival.id}/booths/{booth.id}/scan-token").json()
    assert body["qr_mode"] == "printed"
    assert body["expires_at"] is None
    assert body["refresh_after_seconds"] is None
    assert "&s=" in body["scan_path"]
    assert "qr_secret" not in str(body)


def test_printed_qr_can_be_reused_remotely_this_is_the_known_tradeoff(client, festival, db):
    """**인쇄 QR 은 현장 방문을 증명하지 않습니다.**

    회전 QR 은 "지금 그 부스 앞에 있다"를 증명하지만, 인쇄물은 사진 한 장이면
    어디서든 같은 값입니다. 기획서 E4 가 이 약점을 적고 스태프 확인 병행이나
    이상 패턴 탐지로 보완하라고 한 이유입니다.

    이 테스트는 막기 위한 것이 아니라 **사실을 고정하기 위한 것**입니다.
    누군가 인쇄 모드에서도 원격 완료가 막힌다고 오해하면, 그 오해 위에
    운영 계획이 세워집니다.
    """
    booth, mission = _printed_booth(db, festival)
    db.commit()
    signature = _signature(booth)

    # 서로 다른 참여자 둘이 같은 서명으로 각자 받는다. 부스에 온 적이 없어도.
    for _ in range(2):
        _, headers = _issue(client, festival)
        r = client.post(
            f"/api/festivals/{festival.id}/scan-grants",
            json={"booth_id": booth.id, "signature": signature, "mission_id": mission.id},
            headers=headers,
        )
        assert r.status_code == 200, r.text


def test_printed_booth_still_gives_one_mission_per_scan_window(client, festival, db):
    """고정 QR 이라도 한 번에 그 부스 미션을 쓸어담지는 못한다.

    토큰이 고정이라 토큰으로는 묶을 수 없으므로 서버 시각의 window 로 묶는다.
    줄을 선 사람들 사이에서 실제로 필요한 간격이다.
    """
    booth, first = _printed_booth(db, festival)
    second = Mission(
        festival_id=festival.id, booth_id=booth.id, title="두 번째 미션", points=50
    )
    db.add(second)
    db.commit()
    _, headers = _issue(client, festival)
    signature = _signature(booth)

    def grant(mission_id: int):
        return client.post(
            f"/api/festivals/{festival.id}/scan-grants",
            json={"booth_id": booth.id, "signature": signature, "mission_id": mission_id},
            headers=headers,
        )

    assert grant(first.id).status_code == 200
    blocked = grant(second.id)
    assert blocked.status_code == 409
    assert _err(blocked) == "SCAN_ALREADY_USED"
