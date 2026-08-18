"""축제·진단 API 계약 테스트.

프런트가 이 응답 모양에 의존하므로, 계약이 바뀌면 여기가 먼저 깨져야 합니다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from festaflow.core.deps import get_current_org
from festaflow.db.session import get_db
from festaflow.main import app
from festaflow.models import Festival, Organization

PAYLOAD = {
    "name": "춘천 가을 먹거리 축제",
    "region": "강원특별자치도 춘천시",
    "venue": "공지천 조각공원",
    "starts_on": "2026-10-10",
    "ends_on": "2026-10-12",
    "expected_visitors": 18000,
    "total_budget": 240000000,
    "plan": {"summary": "지역 식재료와 로컬 뮤지션이 만나는 3일", "venue_capacity": 4000},
}


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="춘천시문화재단")
    db.add(o)
    db.flush()
    return o


@pytest.fixture
def client(db: Session, org: Organization):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_org] = lambda: org
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── 생성 ────────────────────────────────────────────────────────────────────


def test_create_returns_all_bootstrapped_resources(client):
    r = client.post("/api/festivals", json=PAYLOAD)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["festival"]["name"] == PAYLOAD["name"]
    assert body["diagnosis"]["status"] == "pending"
    assert body["stamp_board"]["total_tiles"] == 9
    # 접근 코드는 이 응답에서만 평문으로 나온다
    assert len(body["operator_access_code"]) == 6


def test_access_code_never_appears_again(client):
    created = client.post("/api/festivals", json=PAYLOAD).json()
    code = created["operator_access_code"]
    detail = client.get(f"/api/festivals/{created['festival']['id']}").text
    assert code not in detail


def test_end_before_start_rejected_with_422(client):
    bad = {**PAYLOAD, "starts_on": "2026-10-12", "ends_on": "2026-10-10"}
    r = client.post("/api/festivals", json=bad)
    assert r.status_code == 422


def test_zero_visitors_rejected(client):
    r = client.post("/api/festivals", json={**PAYLOAD, "expected_visitors": 0})
    assert r.status_code == 422


def test_failed_create_leaves_nothing_behind(client, db: Session):
    before = db.query(Festival).count()
    client.post("/api/festivals", json={**PAYLOAD, "expected_visitors": -5})
    assert db.query(Festival).count() == before


# ── 목록·상세 ───────────────────────────────────────────────────────────────


def test_list_is_newest_first(client):
    for i in range(3):
        client.post("/api/festivals", json={**PAYLOAD, "name": f"축제{i}"})
    items = client.get("/api/festivals").json()["items"]
    ids = [i["id"] for i in items]
    assert ids == sorted(ids, reverse=True)


def test_detail_includes_plan_and_counts(client):
    fid = client.post("/api/festivals", json=PAYLOAD).json()["festival"]["id"]
    body = client.get(f"/api/festivals/{fid}").json()
    assert body["plan"]["venue_capacity"] == 4000
    assert body["duration_days"] == 3
    assert body["booth_count"] == 0


def test_other_org_gets_404_not_403(client, db: Session):
    """타 기관 리소스는 존재 여부도 노출하지 않는다."""
    fid = client.post("/api/festivals", json=PAYLOAD).json()["festival"]["id"]

    other = Organization(name="다른재단")
    db.add(other)
    db.flush()
    app.dependency_overrides[get_current_org] = lambda: other

    r = client.get(f"/api/festivals/{fid}")
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "NOT_FOUND"


def test_missing_festival_is_404(client):
    assert client.get("/api/festivals/999999").status_code == 404


def test_not_found_message_picks_right_particle(client):
    """리소스명 받침에 따라 조사가 달라져야 한다 — `축제를`, `진단을`."""
    from festaflow.core.errors import not_found, object_particle

    fid = client.post("/api/festivals", json=PAYLOAD).json()["festival"]["id"]

    missing = client.get("/api/festivals/999999").json()["detail"]["error"]["message"]
    assert "축제를 찾을 수 없습니다." in missing
    r = client.get(f"/api/festivals/{fid}/diagnoses/latest")
    assert r.status_code == 404
    assert "진단을 찾을 수 없습니다." in r.json()["detail"]["error"]["message"]

    from festaflow.core.errors import subject_particle

    assert subject_particle("부스") == "가"  # 받침 없음
    assert subject_particle("미션") == "이"  # 받침 있음
    assert object_particle("축제") == "를"  # 받침 없음
    assert object_particle("진단") == "을"  # 받침 있음
    assert object_particle("리소스") == "를"
    assert object_particle("QR") == "를"  # 한글이 아니면 기본값
    assert object_particle("") == "를"
    assert "리소스를" in not_found().detail["error"]["message"]


# ── 수정 ────────────────────────────────────────────────────────────────────


def test_update_does_not_touch_child_data(client, db: Session):
    from festaflow.models import Diagnosis, StampBoard

    fid = client.post("/api/festivals", json=PAYLOAD).json()["festival"]["id"]
    diag_before = db.query(Diagnosis).filter_by(festival_id=fid).count()
    board_before = db.query(StampBoard).filter_by(festival_id=fid).one().version

    r = client.put(f"/api/festivals/{fid}", json={**PAYLOAD, "expected_visitors": 25000})
    assert r.status_code == 200
    assert r.json()["expected_visitors"] == 25000

    assert db.query(Diagnosis).filter_by(festival_id=fid).count() == diag_before
    assert db.query(StampBoard).filter_by(festival_id=fid).one().version == board_before


# ── 보관 ────────────────────────────────────────────────────────────────────


def test_archive_hides_from_list_but_keeps_row(client, db: Session):
    fid = client.post("/api/festivals", json=PAYLOAD).json()["festival"]["id"]
    assert client.post(f"/api/festivals/{fid}/archive").status_code == 204
    assert client.get("/api/festivals").json()["total"] == 0
    assert db.get(Festival, fid) is not None  # 행은 남는다


# ── 쿼터 ────────────────────────────────────────────────────────────────────


def test_quota_exceeded_returns_402(client, db: Session, org: Organization):
    org.festival_quota = 1
    db.flush()
    client.post("/api/festivals", json=PAYLOAD)
    r = client.post("/api/festivals", json={**PAYLOAD, "name": "두번째"})
    assert r.status_code == 402
    assert r.json()["detail"]["error"]["code"] == "QUOTA_EXCEEDED"


# ── 진단 조회 ───────────────────────────────────────────────────────────────


def test_latest_diagnosis_404_before_any_completed(client):
    fid = client.post("/api/festivals", json=PAYLOAD).json()["festival"]["id"]
    # 생성 시 만들어지는 진단은 pending 이라 "완료된 진단"이 아니다
    assert client.get(f"/api/festivals/{fid}/diagnoses/latest").status_code == 404


def test_comparison_says_first_diagnosis(client):
    fid = client.post("/api/festivals", json=PAYLOAD).json()["festival"]["id"]
    body = client.get(f"/api/festivals/{fid}/diagnoses/comparison").json()
    assert body["comparable"] is False
    assert body["reason"] == "FIRST_DIAGNOSIS"


def test_health_reports_contest_critical_flags(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    # 캐시가 켜져 있으면 공모전 호출 이력이 안 남는다 — 눈에 보여야 한다
    assert "tourism_cache_enabled" in body
