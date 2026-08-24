"""진단 채점 엔진 테스트.

채점 함수는 순수 함수라 DB·네트워크 없이 검증합니다.
"근거 없는 점수는 점술"이라는 주장이 코드에서 참인지 확인합니다.
"""

from __future__ import annotations

from datetime import date

import pytest

from festaflow.models.enums import DiagnosisCategory, RiskLevel, TourismProvider
from festaflow.services import rubric
from festaflow.services.diagnosis import (
    FestivalFacts,
    build_items,
    score_crowd_safety,
    score_local_linkage,
    score_ops_readiness,
    score_program_balance,
    score_tourism_demand,
)
from festaflow.services.tourism import TourismIndicators

CFG = rubric.load("v1")


def make_facts(**kw) -> FestivalFacts:
    plan = {
        "summary": True, "description": True, "core_audience": True,
        "venue_capacity": 4000, "staff_count": 30, "volunteer_count": 20,
        "safety_staff_count": 10, "safety_plan": True, "traffic_plan": True,
        "crowd_plan": True, "planned_total": 18, "planned_types": 3,
    }
    plan.update(kw.pop("plan", {}))
    base = {
        "expected_visitors": 18000, "days": 3, "daily_expected": 6000,
        "total_budget": 240_000_000, "active_booths": 6, "booth_types": 3,
        "active_missions": 12, "plan": plan,
    }
    base.update(kw)
    return FestivalFacts(**base)


def make_ind(**kw) -> TourismIndicators:
    base = {
        "provider": TourismProvider.KTO_LIVE,
        "region_key": "강원춘천", "base_month": "202510",
        "content_count": 480, "category_count": 5,
        "resources": [{"title": f"자원{i}", "category": "NA"} for i in range(6)],
        "demand_index": 62.0, "season_fit": 0.61,
        "estimated_daily_capacity": 9000, "congestion_risk": 0.42,
        "local_link_readiness": 0.86,
        "sources": {"관광수요": "조회"},
    }
    base.update(kw)
    return TourismIndicators(**base)


# ── 배점 상한 ───────────────────────────────────────────────────────────────


def test_total_max_is_100():
    assert rubric.total_max("v1") == 100


def test_every_item_respects_its_max():
    """어떤 입력에도 항목 점수가 배점을 넘지 않아야 한다."""
    facts = make_facts(active_booths=99, booth_types=99, active_missions=99)
    ind = make_ind(demand_index=100, season_fit=1.0, local_link_readiness=1.0,
                   resources=[{"title": f"r{i}", "category": "NA"} for i in range(50)])
    for s in build_items(facts, ind):
        assert 0 <= s.score <= s.max_score, s.category


def test_total_never_exceeds_100():
    facts = make_facts(active_booths=99, booth_types=99, active_missions=99)
    ind = make_ind(demand_index=100, season_fit=1.0, congestion_risk=0.0,
                   local_link_readiness=1.0,
                   resources=[{"title": f"r{i}", "category": "NA"} for i in range(50)])
    assert sum(s.score for s in build_items(facts, ind)) <= 100


# ── 혼잡·수용 (30점, 배점 최대) ─────────────────────────────────────────────


def test_venue_capacity_takes_priority_over_estimate():
    """입력한 동시 수용 인원이 있으면 추정치보다 우선한다."""
    facts = make_facts(plan={"venue_capacity": 4000})
    s = score_crowd_safety(facts, make_ind(), CFG, 30)
    assert s.details["capacity"] == 8000  # 4000 × 2회전
    assert s.details["capacity_source"] == "기획 입력"
    assert "기획 입력" in s.reason


def test_falls_back_to_estimated_capacity():
    facts = make_facts(plan={"venue_capacity": None})
    s = score_crowd_safety(facts, make_ind(estimated_daily_capacity=9000), CFG, 30)
    assert s.details["capacity"] == 9000
    assert s.details["capacity_source"] == "FestaFlow 추정"
    # 추정치를 썼다는 사실이 근거 문장에 드러나야 한다
    assert "추정" in s.reason


@pytest.mark.parametrize(
    ("daily", "capacity", "expected_band"),
    [
        (6000, 10000, 20),   # 60% → 여유
        (8000, 10000, 18),   # 80%
        (9500, 10000, 16),   # 95%
        (11000, 10000, 11),  # 110%
        (13000, 10000, 6),   # 130% → 위험
    ],
)
def test_capacity_bands(daily, capacity, expected_band):
    facts = make_facts(daily_expected=daily, plan={"venue_capacity": capacity // 2})
    s = score_crowd_safety(facts, make_ind(congestion_risk=1.0), CFG, 30)
    # 혼잡 점수가 0이 되므로 수용 점수만 남는다
    assert s.score == pytest.approx(expected_band)


def test_overcapacity_recommendation_is_actionable():
    facts = make_facts(daily_expected=20000, plan={"venue_capacity": 4000})
    s = score_crowd_safety(facts, make_ind(), CFG, 30)
    assert "초과" in s.recommendation
    assert s.details["usage_ratio"] > 1.0


# ── 프로그램 균형 ───────────────────────────────────────────────────────────


def test_actual_booths_take_priority_over_planned():
    facts = make_facts(active_booths=6, booth_types=3, active_missions=12,
                       plan={"planned_total": 99, "planned_types": 6})
    s = score_program_balance(facts, CFG, 20)
    assert s.details["uses_actual_booths"] is True
    assert "실제 등록된 부스" in s.reason


def test_planned_used_when_no_booths():
    facts = make_facts(active_booths=0, booth_types=0, active_missions=0,
                       plan={"planned_total": 18, "planned_types": 3})
    s = score_program_balance(facts, CFG, 20)
    assert s.details["uses_actual_booths"] is False
    assert "기획 예정" in s.reason
    assert "부스를 등록하면" in s.recommendation


def test_type_diversity_is_capped():
    """유형 수를 늘려도 배점 상한을 넘지 않는다 — 오타로 점수를 부풀릴 수 없다."""
    a = score_program_balance(make_facts(booth_types=2), CFG, 20)
    b = score_program_balance(make_facts(booth_types=20), CFG, 20)
    assert b.score - a.score <= CFG["program_balance"]["type_points_max"]


# ── 운영 준비도 ─────────────────────────────────────────────────────────────


def test_missing_plans_are_named_in_reason():
    facts = make_facts(plan={"safety_plan": False, "traffic_plan": False, "crowd_plan": False})
    s = score_ops_readiness(facts, CFG, 10)
    assert "안전 계획" in s.reason
    assert "미작성" in s.reason
    assert s.score < 10


def test_full_plan_scores_max():
    s = score_ops_readiness(make_facts(), CFG, 10)
    assert s.score == pytest.approx(10)
    assert "모두 작성" in s.reason


def test_partial_actuals_get_half_credit():
    facts = make_facts(active_booths=3, active_missions=0)
    s = score_ops_readiness(facts, CFG, 10)
    full = score_ops_readiness(make_facts(), CFG, 10)
    assert s.score < full.score


# ── 관광수요 ────────────────────────────────────────────────────────────────


def test_measured_visitors_appear_in_reason():
    """실측을 썼으면 그 숫자가 근거 문장에 나와야 한다."""
    ind = make_ind(daily_visitors_avg=124000.0, outsider_ratio=0.38,
                   sources={"관광수요": "조회"})
    s = score_tourism_demand(ind, CFG, 25)
    assert "124,000명" in s.reason
    assert "38%" in s.reason
    assert "[조회]" in s.reason


def test_estimated_demand_is_labeled():
    ind = make_ind(daily_visitors_avg=None, outsider_ratio=None,
                   sources={"관광수요": "추정"})
    s = score_tourism_demand(ind, CFG, 25)
    assert "[추정]" in s.reason
    assert "추정했습니다" in s.reason


# ── 지역 연계 ───────────────────────────────────────────────────────────────


def test_resource_names_are_cited():
    ind = make_ind(resources=[{"title": "소양강 스카이워크", "category": "NA"},
                              {"title": "남이섬", "category": "NA"}])
    s = score_local_linkage(ind, CFG, 15)
    assert "소양강 스카이워크" in s.reason
    assert "FestaFlow 추정" in s.reason  # 연계 준비도는 추정임을 밝힌다


def test_no_resources_lowers_score():
    s = score_local_linkage(make_ind(resources=[], local_link_readiness=0.45), CFG, 15)
    assert s.score < 15 * 0.6
    assert "연계 계획이 약합니다" in s.recommendation


# ── 등급 판정 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("total", "expected"),
    [(90, RiskLevel.STABLE), (85, RiskLevel.STABLE), (84, RiskLevel.CAUTION),
     (70, RiskLevel.CAUTION), (69, RiskLevel.RISK), (0, RiskLevel.RISK)],
)
def test_risk_thresholds(total, expected):
    assert rubric.risk_for_total(total) is expected


@pytest.mark.parametrize(
    ("score", "maximum", "expected"),
    [(30, 30, RiskLevel.STABLE), (24, 30, RiskLevel.STABLE), (23, 30, RiskLevel.CAUTION),
     (18, 30, RiskLevel.CAUTION), (17, 30, RiskLevel.RISK)],
)
def test_item_level_uses_ratio_not_absolute(score, maximum, expected):
    """배점이 다른 항목을 절대 점수로 비교하면 왜곡된다."""
    assert rubric.level_for_item(score, maximum) is expected


# ── 근거의 존재 ─────────────────────────────────────────────────────────────


def test_every_item_has_reason_and_recommendation():
    """점수만 있고 근거가 없으면 점술이다."""
    for s in build_items(make_facts(), make_ind()):
        assert s.reason.strip(), s.category
        assert s.recommendation.strip(), s.category
        assert len(s.reason) > 20


def test_all_five_categories_present():
    cats = {s.category for s in build_items(make_facts(), make_ind())}
    assert cats == set(DiagnosisCategory)


# ── 출처 표기 ───────────────────────────────────────────────────────────────


def test_source_note_credits_kto_not_tourapi():
    """공모전 규정: 'TourAPI' 단독 표기 금지, 'ⓒ한국관광공사' 사용."""
    note = make_ind().source_note
    assert "ⓒ한국관광공사" in note
    assert "TourAPI" not in note


def test_demo_provider_is_disclosed():
    ind = make_ind(provider=TourismProvider.DEMO)
    assert ind.is_demo
    assert "데모 대체 데이터" in ind.source_note
