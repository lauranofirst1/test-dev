"""사후 리포트 · 성과 목표 · 실측 방문객. 계약 §15, §14.1.

리포트는 저장하지 않고 **매번 원본 테이블에서 조립**합니다. 스냅샷으로 굳혀
두면 부스 이름을 고치거나 참여를 정리한 뒤에도 옛 숫자가 남고, 어느 쪽이 맞는지
아무도 모르게 됩니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core.deps import (
    CanManagePlan,
    CanOperate,
    CurrentOrg,
    DbSession,
    FestivalAccess,
)
from festaflow.core.errors import ApiError, not_found
from festaflow.models import (
    BUILTIN_METRICS,
    Booth,
    Festival,
    KpiTarget,
    RewardCampaign,
    VisitorCount,
)
from festaflow.schemas.report import (
    BoothPerformanceOut,
    CampaignImpactSummary,
    ImprovementOut,
    KpiResultOut,
    KpiTargetIn,
    KpiTargetList,
    KpiTargetOut,
    MissionPerformanceOut,
    PlanVsActual,
    RecommendationAccuracy,
    ReportOut,
    SummaryOut,
    TimelinePoint,
    VisitorBasisOut,
    VisitorCountIn,
    VisitorCountList,
    VisitorCountOut,
)
from festaflow.services import reports as svc
from festaflow.services import reward_campaign_impact as impact_svc

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["reports"])

#: 리포트와 목표는 기획자·운영자 둘 다 본다.
VIEWER = [FestivalAccess, CanManagePlan]


def _owned(db: Session, org_id: int, festival_id: int) -> Festival:
    f = db.execute(
        select(Festival).where(
            Festival.id == festival_id,
            Festival.organization_id == org_id,
            Festival.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if f is None:
        raise not_found("축제")
    return f


# ── 성과 목표 ───────────────────────────────────────────────────────────────


@router.get("/kpi-targets", response_model=KpiTargetList, dependencies=VIEWER)
def list_targets(festival_id: int, db: DbSession, org: CurrentOrg) -> KpiTargetList:
    _owned(db, org.id, festival_id)
    items = list(
        db.execute(
            select(KpiTarget).where(KpiTarget.festival_id == festival_id).order_by(KpiTarget.id)
        ).scalars()
    )
    used = {t.metric_key for t in items}
    return KpiTargetList(
        items=[
            KpiTargetOut(
                id=t.id,
                metric_key=t.metric_key,
                label=t.label,
                target_value=float(t.target_value),
                unit=t.unit,
                is_measurable=t.is_measurable,
            )
            for t in items
        ],
        # 화면이 지표 목록을 하드코딩하면 여기 기본값이 늘어날 때 조용히 어긋난다.
        available=[
            {"metric_key": key, "label": label, "unit": unit, "is_measurable": measurable}
            for key, (label, unit, measurable) in BUILTIN_METRICS.items()
            if key not in used
        ],
    )


@router.put("/kpi-targets", response_model=KpiTargetOut, dependencies=VIEWER)
def upsert_target(
    festival_id: int, body: KpiTargetIn, db: DbSession, org: CurrentOrg
) -> KpiTargetOut:
    """같은 지표를 다시 보내면 값을 덮어쓴다.

    POST 로 두면 목표를 고치려던 운영자가 409 를 보고, 리포트에는 같은 줄이
    두 개 뜹니다. 목표는 축제당 지표당 하나입니다.
    """
    _owned(db, org.id, festival_id)

    builtin = BUILTIN_METRICS.get(body.metric_key)
    if builtin is None and not body.metric_key.startswith("custom:"):
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "기본 지표가 아니면 `custom:` 으로 시작하는 키를 쓰세요.",
            {"field": "metric_key", "builtin": sorted(BUILTIN_METRICS)},
        )

    if builtin:
        # 라벨·단위·측정 가능 여부를 서버가 정한다. 라벨이 제각각이면 축제 간
        # 비교가 안 되고, 측정 가능 여부는 애초에 운영자가 정할 값이 아니다.
        label, unit, measurable = builtin
    else:
        label = (body.label or body.metric_key.removeprefix("custom:")).strip()
        unit = (body.unit or "건").strip()
        # 사용자 정의 지표는 FestaFlow 가 집계할 방법이 없다.
        measurable = False
        if not label:
            raise ApiError(
                422, "VALIDATION_FAILED", "지표 이름을 입력하세요.", {"field": "label"}
            )

    existing = db.execute(
        select(KpiTarget).where(
            KpiTarget.festival_id == festival_id, KpiTarget.metric_key == body.metric_key
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = KpiTarget(festival_id=festival_id, metric_key=body.metric_key)
        db.add(existing)

    existing.label = label
    existing.unit = unit
    existing.is_measurable = measurable
    existing.target_value = body.target_value
    db.commit()
    db.refresh(existing)

    return KpiTargetOut(
        id=existing.id,
        metric_key=existing.metric_key,
        label=existing.label,
        target_value=float(existing.target_value),
        unit=existing.unit,
        is_measurable=existing.is_measurable,
    )


@router.delete(
    "/kpi-targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=VIEWER
)
def delete_target(
    festival_id: int, target_id: int, db: DbSession, org: CurrentOrg
) -> None:
    _owned(db, org.id, festival_id)
    t = db.execute(
        select(KpiTarget).where(
            KpiTarget.id == target_id, KpiTarget.festival_id == festival_id
        )
    ).scalar_one_or_none()
    if t is None:
        raise not_found("성과 목표")
    db.delete(t)
    db.commit()


# ── 실측 방문객 ─────────────────────────────────────────────────────────────


@router.get("/visitor-counts", response_model=VisitorCountList, dependencies=VIEWER)
def list_visitors(festival_id: int, db: DbSession, org: CurrentOrg) -> VisitorCountList:
    _owned(db, org.id, festival_id)
    items = list(
        db.execute(
            select(VisitorCount)
            .where(VisitorCount.festival_id == festival_id)
            .order_by(VisitorCount.count_date, VisitorCount.id)
        ).scalars()
    )
    basis = svc.visitor_basis(db, festival_id, 0)
    return VisitorCountList(
        items=[
            VisitorCountOut(
                id=v.id,
                count_date=v.count_date,
                visitors=v.visitors,
                source=v.source,
                source_label=svc.SOURCE_LABEL.get(v.source, v.source.value),
                note=v.note,
            )
            for v in items
        ],
        # 날짜별로 우선순위가 높은 출처 하나씩만 더한 값이다. 단순 합계를 쓰면
        # 같은 날 두 출처가 들어온 만큼 방문객이 두 배가 된다.
        total_visitors=basis.visitors if basis else 0,
    )


@router.post(
    "/visitor-counts",
    response_model=VisitorCountOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=VIEWER,
)
def add_visitors(
    festival_id: int, body: VisitorCountIn, db: DbSession, org: CurrentOrg
) -> VisitorCountOut:
    """같은 날짜에 여러 출처가 공존할 수 있다.

    입구 계수기 수치와 지자체 집계가 다른 것은 정상입니다. 하나로 합치라고
    강요하면 운영자는 아무 값이나 하나 골라 넣고, 그 선택은 기록에 남지 않습니다.
    """
    _owned(db, org.id, festival_id)
    existing = db.execute(
        select(VisitorCount).where(
            VisitorCount.festival_id == festival_id,
            VisitorCount.count_date == body.count_date,
            VisitorCount.source == body.source,
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = VisitorCount(
            festival_id=festival_id, count_date=body.count_date, source=body.source
        )
        db.add(existing)
    existing.visitors = body.visitors
    existing.note = body.note
    db.commit()
    db.refresh(existing)

    return VisitorCountOut(
        id=existing.id,
        count_date=existing.count_date,
        visitors=existing.visitors,
        source=existing.source,
        source_label=svc.SOURCE_LABEL.get(existing.source, existing.source.value),
        note=existing.note,
    )


@router.delete(
    "/visitor-counts/{visitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FestivalAccess, CanOperate],
)
def delete_visitors(
    festival_id: int, visitor_id: int, db: DbSession, org: CurrentOrg
) -> None:
    _owned(db, org.id, festival_id)
    v = db.execute(
        select(VisitorCount).where(
            VisitorCount.id == visitor_id, VisitorCount.festival_id == festival_id
        )
    ).scalar_one_or_none()
    if v is None:
        raise not_found("방문객 기록")
    db.delete(v)
    db.commit()


# ── 리포트 ──────────────────────────────────────────────────────────────────


@router.get("/report", response_model=ReportOut, dependencies=VIEWER)
def get_report(festival_id: int, db: DbSession, org: CurrentOrg) -> ReportOut:
    festival = _owned(db, org.id, festival_id)

    # 캠페인 전후 변화를 먼저 구해 개선안 규칙에 넘긴다.
    campaigns = list(
        db.execute(
            select(RewardCampaign)
            .where(RewardCampaign.festival_id == festival_id)
            .order_by(RewardCampaign.starts_at)
        ).scalars()
    )
    summaries: list[CampaignImpactSummary] = []
    impacts: list[tuple[str, float, bool]] = []
    for c in campaigns:
        result = impact_svc.build(db, c)
        booth = db.get(Booth, c.booth_id)
        sufficient = result.data_status == impact_svc.SUFFICIENT and not result.in_progress
        summaries.append(
            CampaignImpactSummary(
                campaign_id=c.id,
                title=c.title,
                booth_name=booth.name if booth else f"부스 {c.booth_id}",
                share_change_pp=result.share_change_pp,
                data_status=result.data_status,
                in_progress=result.in_progress,
            )
        )
        impacts.append((c.title, result.share_change_pp, sufficient))

    r = svc.build(db, festival, impacts)
    hits = r.recommendation_hits

    return ReportOut(
        festival_id=festival.id,
        festival_name=festival.name,
        generated_at=datetime.now(UTC),
        summary=SummaryOut(
            unique_participants=r.summary.unique_participants,
            total_completions=r.summary.total_completions,
            avg_completions_per_participant=r.summary.avg_completions_per_participant,
            missions_with_completion={
                "count": r.summary.missions_with_completion,
                "total": r.summary.missions_total,
                "ratio": r.summary.mission_ratio,
            },
        ),
        plan_vs_actual=PlanVsActual(
            expected_visitors=festival.expected_visitors,
            festaflow_participants=r.summary.unique_participants,
            participation_scale=r.participation_scale,
            disclaimer=svc.SCALE_DISCLAIMER,
        ),
        visitor_basis=(
            VisitorBasisOut(
                visitors=r.visitor_basis.visitors,
                source=r.visitor_basis.source,
                source_label=r.visitor_basis.source_label,
                caveat=r.visitor_basis.caveat,
                participation_rate=r.visitor_basis.participation_rate,
                others=[{"source_label": s, "visitors": n} for s, n in r.visitor_basis.others],
            )
            if r.visitor_basis
            else None
        ),
        timeline=[
            TimelinePoint(hour_kst=hour, completions=count) for hour, count in r.timeline
        ],
        booths=[
            BoothPerformanceOut(
                booth_id=b.booth_id,
                name=b.name,
                completions=b.completions,
                unique_participants=b.unique_participants,
                share=b.share,
                rank=b.rank,
                peak_hour_kst=b.peak_hour_kst,
                peak_completions=b.peak_completions,
            )
            for b in r.booths
        ],
        missions=[
            MissionPerformanceOut(
                mission_id=m.mission_id,
                title=m.title,
                booth_name=m.booth_name,
                completions=m.completions,
                unique_participants=m.unique_participants,
                share=m.share,
            )
            for m in r.missions
        ],
        unassigned_completions=r.unassigned_completions,
        kpi=[
            KpiResultOut(
                metric_key=k.metric_key,
                label=k.label,
                target=k.target,
                actual=k.actual,
                achievement=k.achievement,
                measurable=k.measurable,
                unit=k.unit,
                note=k.note,
            )
            for k in r.kpi
        ],
        recommendation_accuracy=(
            RecommendationAccuracy(
                total=hits[1], hits=hits[0], rate=round(hits[0] / hits[1], 4)
            )
            if hits and hits[1]
            else None
        ),
        campaigns=summaries,
        improvements=[ImprovementOut(rule=i.rule, message=i.message) for i in r.improvements],
    )
