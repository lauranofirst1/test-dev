"""축제 준비도 진단 — 지정과제 9번의 핵심.

5개 항목 100점. 각 항목은 점수만이 아니라 **계산 근거와 개선 제안**을 함께 냅니다.
근거 없는 점수는 점술이므로, 어떤 데이터를 썼는지(조회/추정/폴백)까지 문장에 남깁니다.

진단은 append-only 입니다. 기존 진단을 수정하거나 교체하지 않습니다.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from festaflow.models import (
    Booth,
    Diagnosis,
    DiagnosisItem,
    Festival,
    FestivalPlan,
    Mission,
    StampBoard,
)
from festaflow.models.enums import DiagnosisCategory, DiagnosisStatus, RiskLevel
from festaflow.services import rubric
from festaflow.services.tourapi import TourApiClient
from festaflow.services.tourism import TourismIndicators, collect

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Scored:
    category: DiagnosisCategory
    score: float
    max_score: float
    reason: str
    recommendation: str
    details: dict = field(default_factory=dict)


@dataclass(slots=True)
class FestivalFacts:
    """진단이 보는 축제의 사실. 여기 담긴 값이 곧 재현 가능한 입력 스냅샷이다."""

    expected_visitors: int
    days: int
    daily_expected: int
    total_budget: int
    active_booths: int
    booth_types: int
    active_missions: int
    plan: dict

    @classmethod
    def gather(cls, db: Session, festival: Festival) -> FestivalFacts:
        plan = db.get(FestivalPlan, festival.id)
        booths = db.execute(
            select(Booth).where(
                Booth.festival_id == festival.id,
                Booth.archived_at.is_(None),
                Booth.is_active.is_(True),
            )
        ).scalars().all()
        missions = db.execute(
            select(func.count(Mission.id)).where(
                Mission.festival_id == festival.id,
                Mission.archived_at.is_(None),
                Mission.is_active.is_(True),
            )
        ).scalar_one()

        days = festival.duration_days
        return cls(
            expected_visitors=festival.expected_visitors,
            days=days,
            daily_expected=math.ceil(festival.expected_visitors / max(days, 1)),
            total_budget=festival.total_budget,
            active_booths=len(booths),
            booth_types=len({b.booth_type for b in booths}),
            active_missions=int(missions),
            plan={
                "summary": bool(plan and plan.summary),
                "description": bool(plan and plan.description),
                "core_audience": bool(plan and plan.core_audience),
                "venue_capacity": plan.venue_capacity if plan else None,
                "staff_count": plan.staff_count if plan else None,
                "volunteer_count": plan.volunteer_count if plan else None,
                "safety_staff_count": plan.safety_staff_count if plan else None,
                "safety_plan": bool(plan and plan.safety_plan),
                "traffic_plan": bool(plan and plan.traffic_plan),
                "crowd_plan": bool(plan and plan.crowd_plan),
                "planned_total": plan.planned_program_total if plan else 0,
                "planned_types": plan.planned_type_count if plan else 0,
            },
        )


# ── 항목별 채점 ─────────────────────────────────────────────────────────────


def score_tourism_demand(
    ind: TourismIndicators, cfg: dict, maximum: float
) -> Scored:
    c = cfg["tourism_demand"]
    demand_pts = ind.demand_index * c["demand_weight"]
    season_pts = ind.season_fit * c["season_weight"]
    score = min(maximum, demand_pts + season_pts)

    src = ind.sources.get("관광수요", "추정")
    if ind.daily_visitors_avg:
        basis = (
            f"{ind.base_month} 기준 지역 일평균 방문자 {ind.daily_visitors_avg:,.0f}명"
            f"(외지인 {ind.outsider_ratio:.0%})을 조회해 산출했습니다"
            if ind.outsider_ratio is not None
            else f"{ind.base_month} 기준 지역 일평균 방문자 {ind.daily_visitors_avg:,.0f}명을 조회했습니다"
        )
    else:
        basis = f"방문자 실측을 얻지 못해 관광 콘텐츠 {ind.content_count:,}건으로 추정했습니다"

    reason = (
        f"관광수요 지수 {ind.demand_index:.1f}(×{c['demand_weight']}) + "
        f"계절 적합도 {ind.season_fit:.2f}(×{c['season_weight']}) = {score:.1f}점. {basis}. [{src}]"
    )
    rec = (
        "행사 시기의 지역 방문 수요가 낮습니다. 성수기 이동이나 인근 관광지와의 연계 일정을 검토하세요."
        if score < maximum * 0.6
        else "지역 방문 수요는 양호합니다. 외지인 유입 시점에 맞춰 홍보를 집중하세요."
    )
    return Scored(
        DiagnosisCategory.TOURISM_DEMAND, score, maximum, reason, rec,
        {"demand_index": round(ind.demand_index, 2), "season_fit": round(ind.season_fit, 3),
         "daily_visitors_avg": ind.daily_visitors_avg, "outsider_ratio": ind.outsider_ratio,
         "source": src},
    )


def score_crowd_safety(
    facts: FestivalFacts, ind: TourismIndicators, cfg: dict, maximum: float
) -> Scored:
    c = cfg["crowd_safety"]
    venue = facts.plan.get("venue_capacity")

    if venue:
        capacity = int(venue) * int(c["venue_turnover_per_day"])
        basis = f"입력한 동시 수용 {venue:,}명 × 하루 {c['venue_turnover_per_day']}회전"
        cap_src = "기획 입력"
    else:
        capacity = ind.estimated_daily_capacity
        basis = f"관광 콘텐츠 기반 FestaFlow 추정 일일 수용력 {capacity:,}명"
        cap_src = "FestaFlow 추정"

    usage = facts.daily_expected / max(capacity, 1)
    cap_score = c["capacity_bands"][-1]["score"]
    for band in c["capacity_bands"]:
        if band["max_usage"] is not None and usage <= band["max_usage"]:
            cap_score = band["score"]
            break

    congestion_score = (1.0 - ind.congestion_risk) * c["congestion_weight"]
    score = min(maximum, cap_score + congestion_score)

    reason = (
        f"일평균 방문 {facts.daily_expected:,}명 대비 {basis} → 사용률 {usage:.0%}, "
        f"수용 {cap_score}점. 혼잡 위험도 {ind.congestion_risk:.2f} → 혼잡 "
        f"{congestion_score:.1f}점. 합계 {score:.1f}점. [수용력 근거: {cap_src}]"
    )
    if usage > 1.0:
        rec = (
            f"계획 수용력을 {usage - 1:.0%} 초과합니다. 입장 분산(시간대별 사전예약), "
            "동선 우회로 확보, 행사 일수 연장 중 하나를 검토하세요."
        )
    elif not venue:
        rec = "동시 수용 인원을 입력하면 추정치 대신 실제 계획값으로 수용력을 판정할 수 있습니다."
    else:
        rec = "수용 여력은 확보돼 있습니다. 피크 시간대 통로 폭과 대기 동선을 점검하세요."

    return Scored(
        DiagnosisCategory.CROWD_SAFETY, score, maximum, reason, rec,
        {"daily_expected": facts.daily_expected, "capacity": capacity,
         "usage_ratio": round(usage, 3), "capacity_source": cap_src,
         "congestion_risk": round(ind.congestion_risk, 3)},
    )


def score_program_balance(facts: FestivalFacts, cfg: dict, maximum: float) -> Scored:
    c = cfg["program_balance"]
    uses_actual = facts.active_booths > 0

    if uses_actual:
        booth_pts = min(facts.active_booths * c["booth_points_each"], c["booth_points_max"])
        type_pts = min(facts.booth_types * c["type_points_each"], c["type_points_max"])
        mission_pts = min(facts.active_missions * c["mission_points_each"], c["mission_points_max"])
        basis = (
            f"실제 등록된 부스 {facts.active_booths}개({facts.booth_types}개 유형)와 "
            f"활성 미션 {facts.active_missions}개"
        )
    else:
        planned = facts.plan["planned_total"]
        types = facts.plan["planned_types"]
        booth_pts = min(planned * c["booth_points_each"], c["booth_points_max"])
        type_pts = min(types * c["type_points_each"], c["type_points_max"])
        mission_pts = 0.0
        basis = f"기획 예정 프로그램 {planned}개({types}개 유형) — 실제 부스가 아직 없습니다"

    score = min(maximum, booth_pts + type_pts + mission_pts)
    reason = (
        f"{basis} 기준 — 규모 {booth_pts}점 + 유형 다양성 {type_pts}점 + "
        f"미션 {mission_pts}점 = {score:.1f}점"
    )
    if not uses_actual:
        rec = "부스를 등록하면 예정값 대신 실제 구성으로 평가되고, 현장 참여 측정도 가능해집니다."
    elif facts.booth_types < 3:
        rec = "부스 유형이 편중돼 있습니다. 먹거리·체험·지역상점을 섞으면 체류 시간이 늘어납니다."
    else:
        rec = "프로그램 구성은 균형이 잡혀 있습니다. 부스별 미션을 늘려 순회를 유도하세요."

    return Scored(
        DiagnosisCategory.PROGRAM_BALANCE, score, maximum, reason, rec,
        {"uses_actual_booths": uses_actual, "active_booths": facts.active_booths,
         "booth_types": facts.booth_types, "active_missions": facts.active_missions},
    )


def score_local_linkage(ind: TourismIndicators, cfg: dict, maximum: float) -> Scored:
    c = cfg["local_linkage"]
    res_pts = min(len(ind.resources) * c["resource_points_each"], c["resource_points_max"])
    ready_pts = min(ind.local_link_readiness * c["readiness_weight"], c["readiness_max"])
    score = min(maximum, res_pts + ready_pts)

    names = ", ".join(r["title"] for r in ind.resources[:3]) or "없음"
    reason = (
        f"인근 관광자원 {len(ind.resources)}곳({names} 등) × {c['resource_points_each']} = "
        f"{res_pts:.1f}점, 지역 연계 준비도 {ind.local_link_readiness:.2f} → {ready_pts:.1f}점. "
        f"합계 {score:.1f}점. [연계 준비도: FestaFlow 추정]"
    )
    rec = (
        "인근 관광자원과의 연계 계획이 약합니다. 축제 전후 반나절 코스와 지역 상권 공동 프로모션을 검토하세요."
        if score < maximum * 0.6
        else "연계 가능한 자원이 충분합니다. 자원별 홍보 채널을 나눠 노출을 분산하세요."
    )
    return Scored(
        DiagnosisCategory.LOCAL_LINKAGE, score, maximum, reason, rec,
        {"resource_count": len(ind.resources), "content_count": ind.content_count,
         "local_link_readiness": round(ind.local_link_readiness, 3)},
    )


def score_ops_readiness(facts: FestivalFacts, cfg: dict, maximum: float) -> Scored:
    c = cfg["ops_readiness"]
    p = facts.plan

    basics_checks = [p["summary"] or p["description"], p["core_audience"],
                     facts.expected_visitors > 0, facts.total_budget > 0]
    basics = sum(basics_checks) / len(basics_checks) * c["basics_max"]

    safety_checks = [
        bool(p["staff_count"] or p["volunteer_count"] or p["safety_staff_count"]),
        p["safety_plan"], p["traffic_plan"], p["crowd_plan"],
    ]
    safety = sum(safety_checks) / len(safety_checks) * c["safety_max"]

    actuals = (
        c["actuals_max"]
        if facts.active_booths and facts.active_missions
        else (c["actuals_max"] / 2 if facts.active_booths or facts.active_missions else 0.0)
    )
    score = min(maximum, basics + safety + actuals)

    missing = [
        label
        for label, ok in (
            ("안전 계획", p["safety_plan"]),
            ("교통 계획", p["traffic_plan"]),
            ("혼잡 대응 계획", p["crowd_plan"]),
            ("운영 인력", bool(p["staff_count"] or p["volunteer_count"] or p["safety_staff_count"])),
            ("핵심 방문 대상", p["core_audience"]),
        )
        if not ok
    ]
    reason = (
        f"기본 정보 {basics:.1f}/{c['basics_max']}점 + 안전·운영 {safety:.1f}/{c['safety_max']}점 + "
        f"실제 등록 {actuals:.1f}/{c['actuals_max']}점 = {score:.1f}점"
        + (f". 미작성: {', '.join(missing)}" if missing else ". 필수 항목이 모두 작성됐습니다")
    )
    rec = (
        f"{missing[0]}부터 채우세요. 운영 준비도는 현장 사고 대응력과 직결됩니다."
        if missing
        else "운영 준비가 충실합니다. 부스 등록 후 재진단하면 실제 구성으로 평가됩니다."
    )
    return Scored(
        DiagnosisCategory.OPS_READINESS, score, maximum, reason, rec,
        {"missing": missing, "basics": round(basics, 2), "safety": round(safety, 2)},
    )


# ── 실행 ────────────────────────────────────────────────────────────────────


def build_items(
    facts: FestivalFacts, ind: TourismIndicators, version: str = rubric.DEFAULT_VERSION
) -> list[Scored]:
    cfg = rubric.load(version)
    mx = cfg["max_scores"]
    return [
        score_tourism_demand(ind, cfg, mx["tourism_demand"]),
        score_crowd_safety(facts, ind, cfg, mx["crowd_safety"]),
        score_program_balance(facts, cfg, mx["program_balance"]),
        score_local_linkage(ind, cfg, mx["local_linkage"]),
        score_ops_readiness(facts, cfg, mx["ops_readiness"]),
    ]


def board_warning(db: Session, festival_id: int, active_booths: int) -> str | None:
    """타일 수 > 지급 단위 수이면 아무도 보드를 완성할 수 없다.

    참여자가 이유도 모른 채 미완성으로 끝나는 일을 막기 위해 진단에서 경고한다.
    """
    board = db.execute(
        select(StampBoard).where(StampBoard.festival_id == festival_id)
    ).scalar_one_or_none()
    if board is None:
        return None
    tiles = board.total_tiles
    if board.grant_unit.value == "booth" and active_booths and tiles > active_booths:
        return (
            f"현재 구성으로는 이미지 보드를 완성할 수 없습니다 "
            f"({tiles}조각 / 활성 부스 {active_booths}개). "
            f"보드를 줄이거나 부스를 늘리세요."
        )
    return None


async def run(
    db: Session,
    festival: Festival,
    *,
    client: TourApiClient,
    version: str = rubric.DEFAULT_VERSION,
    requested_by_staff_id: int | None = None,
) -> Diagnosis:
    """진단을 실행하고 새 레코드를 추가한다(append-only).

    🚨 관광 데이터를 **실시간으로 호출**합니다. 캐시로 건너뛰지 않습니다 —
       공모전이 인증키의 실제 호출 이력을 검증하기 때문입니다.
    """
    facts = FestivalFacts.gather(db, festival)
    diagnosis = Diagnosis(
        festival_id=festival.id,
        status=DiagnosisStatus.RUNNING,
        rubric_version=version,
        requested_by_staff_id=requested_by_staff_id,
    )
    db.add(diagnosis)
    db.flush()

    try:
        ind = await collect(
            client,
            region=festival.region,
            starts_on=festival.starts_on,
            expected_visitors=festival.expected_visitors,
            days=facts.days,
        )
    except Exception as exc:  # noqa: BLE001 — 진단이 통째로 실패하면 안 된다
        log.exception("관광 지표 수집 실패")
        diagnosis.status = DiagnosisStatus.FAILED
        diagnosis.error_message = str(exc)[:500]
        diagnosis.completed_at = datetime.now(UTC)
        db.flush()
        return diagnosis

    scored = build_items(facts, ind, version)
    total = sum(s.score for s in scored)

    for s in scored:
        db.add(
            DiagnosisItem(
                diagnosis_id=diagnosis.id,
                category=s.category,
                score=round(s.score, 2),
                max_score=s.max_score,
                level=rubric.level_for_item(s.score, s.max_score, version),
                reason=s.reason,
                recommendation=s.recommendation,
                details=s.details,
            )
        )

    warning = board_warning(db, festival.id, facts.active_booths)

    diagnosis.status = DiagnosisStatus.COMPLETED
    diagnosis.total_score = round(total, 2)
    diagnosis.risk = rubric.risk_for_total(total, version)
    diagnosis.completed_at = datetime.now(UTC)
    diagnosis.input_snapshot = {
        "festival": {
            "name": festival.name,
            "region": festival.region,
            "starts_on": festival.starts_on.isoformat(),
            "ends_on": festival.ends_on.isoformat(),
            "expected_visitors": facts.expected_visitors,
            "total_budget": facts.total_budget,
            "days": facts.days,
        },
        "actuals": {
            "active_booths": facts.active_booths,
            "booth_types": facts.booth_types,
            "active_missions": facts.active_missions,
        },
        "plan": facts.plan,
        "tourism": {
            "provider": ind.provider.value,
            "base_month": ind.base_month,
            "area_code": ind.area_code,
            "sigungu_code": ind.sigungu_code,
            "legal_dong_code": ind.legal_dong_code,
            "content_count": ind.content_count,
            "demand_index": round(ind.demand_index, 2),
            "season_fit": round(ind.season_fit, 3),
            "daily_visitors_avg": ind.daily_visitors_avg,
            "outsider_ratio": ind.outsider_ratio,
            "sources": ind.sources,
            "source_note": ind.source_note,
            "resources": ind.resources,
        },
        "warnings": [warning] if warning else [],
        "api_calls": client.call_count,
    }
    db.flush()
    return diagnosis


def latest(db: Session, festival_id: int, limit: int = 1) -> list[Diagnosis]:
    """최신 완료 진단. 스냅샷 복사도 교체도 없이 정렬로 구한다."""
    return list(
        db.execute(
            select(Diagnosis)
            .where(
                Diagnosis.festival_id == festival_id,
                Diagnosis.status == DiagnosisStatus.COMPLETED,
            )
            .order_by(Diagnosis.created_at.desc(), Diagnosis.id.desc())
            .limit(limit)
        ).scalars()
    )


def top_risks(items: list[DiagnosisItem], limit: int = 3) -> list[str]:
    """주의·위험 항목의 계산 근거 중 최대 3개."""
    risky = [i for i in items if i.level in (RiskLevel.CAUTION, RiskLevel.RISK)]
    risky.sort(key=lambda i: float(i.score) / float(i.max_score))
    return [i.reason for i in risky[:limit]]
