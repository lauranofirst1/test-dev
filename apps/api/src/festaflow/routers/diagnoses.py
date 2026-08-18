"""진단 실행·조회 — 지정과제 9번의 사용자 접점."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from festaflow.core.deps import CanManagePlan, CurrentOrg, DbSession, FestivalAccess
from festaflow.core.errors import ApiError, not_found
from festaflow.models import Diagnosis, DiagnosisItem, Festival
from festaflow.models.enums import DiagnosisCategory
from festaflow.schemas.diagnosis import (
    DiagnosisComparison,
    DiagnosisDelta,
    DiagnosisItemOut,
    DiagnosisOut,
    TourismSource,
)
from festaflow.services import diagnosis as svc
from festaflow.services import rubric
from festaflow.services.tourapi import TourApiClient

router = APIRouter(
    prefix="/api/festivals/{festival_id}/diagnoses",
    tags=["diagnoses"],
    # 모든 경로가 {festival_id} 아래라 라우터 단위로 축제 권한을 건다.
    dependencies=[FestivalAccess],
)

CATEGORY_LABELS = {
    DiagnosisCategory.TOURISM_DEMAND: "관광수요 적합성",
    DiagnosisCategory.CROWD_SAFETY: "혼잡·수용 안정성",
    DiagnosisCategory.PROGRAM_BALANCE: "프로그램 균형",
    DiagnosisCategory.LOCAL_LINKAGE: "지역 관광 연계성",
    DiagnosisCategory.OPS_READINESS: "운영 준비도",
}


def _owned(db: DbSession, org_id: int, festival_id: int) -> Festival:
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


def _serialize(db: DbSession, d: Diagnosis) -> DiagnosisOut:
    disclosed = rubric.is_score_disclosed(db, d.rubric_version)
    cfg = rubric.load(d.rubric_version)
    snap = d.input_snapshot or {}
    tour = snap.get("tourism") or {}

    items = [
        DiagnosisItemOut(
            category=i.category,
            score=float(i.score) if disclosed else None,
            max_score=float(i.max_score) if disclosed else None,
            level=i.level,
            fulfillment=rubric.FULFILLMENT[i.level],
            reason=i.reason,
            recommendation=i.recommendation,
            details=i.details,
        )
        for i in sorted(d.items, key=lambda x: -float(x.max_score))
    ]

    return DiagnosisOut(
        id=d.id,
        festival_id=d.festival_id,
        status=d.status.value,
        rubric_version=d.rubric_version,
        display_mode="score" if disclosed else "checklist",
        score_disclosed=disclosed,
        total_score=float(d.total_score) if (disclosed and d.total_score is not None) else None,
        risk=d.risk if disclosed else None,
        items=items,
        top_risks=svc.top_risks(list(d.items)),
        warnings=snap.get("warnings", []),
        tourism_source=(
            TourismSource(
                provider=tour.get("provider", "unknown"),
                base_month=tour.get("base_month", ""),
                indicators=tour.get("sources", {}),
                note=tour.get("source_note", ""),
            )
            if tour
            else None
        ),
        # 점수를 보여줄 때 화면에 반드시 함께 표시해야 하는 문구
        disclosure_note=cfg.get("disclaimer") if disclosed else
        f"채점표 {d.rubric_version} 은 아직 과거 축제 데이터로 검증되지 않아 점수를 표시하지 않습니다.",
        api_calls=snap.get("api_calls"),
        created_at=d.created_at,
    )


@router.post(
    "",
    response_model=DiagnosisOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[CanManagePlan],
)
async def run_diagnosis(festival_id: int, db: DbSession, org: CurrentOrg) -> DiagnosisOut:
    """진단을 실행하고 새 레코드를 추가한다(append-only).

    🚨 한국관광공사 OpenAPI 를 **실시간으로 호출**합니다. 캐시로 건너뛰지 않습니다.
    """
    festival = _owned(db, org.id, festival_id)
    async with TourApiClient() as client:
        d = await svc.run(db, festival, client=client)
    db.commit()
    db.refresh(d)
    if d.status.value == "failed":
        raise ApiError(
            503,
            "DIAGNOSIS_FAILED",
            "관광 데이터를 불러오지 못해 진단에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            {"reason": d.error_message},
        )
    return _serialize(db, d)


@router.get("/latest", response_model=DiagnosisOut)
def latest_diagnosis(festival_id: int, db: DbSession, org: CurrentOrg) -> DiagnosisOut:
    _owned(db, org.id, festival_id)
    rows = svc.latest(db, festival_id, limit=1)
    if not rows:
        raise not_found("완료된 진단")
    return _serialize(db, rows[0])


@router.get("", response_model=list[DiagnosisOut])
def list_diagnoses(festival_id: int, db: DbSession, org: CurrentOrg) -> list[DiagnosisOut]:
    """이력. 최신순 — 스냅샷 복사도 교체도 없이 정렬로만 구한다."""
    _owned(db, org.id, festival_id)
    return [_serialize(db, d) for d in svc.latest(db, festival_id, limit=20)]


@router.get("/comparison", response_model=DiagnosisComparison)
def compare(festival_id: int, db: DbSession, org: CurrentOrg) -> DiagnosisComparison:
    """최신 완료 진단 2건 비교. 개선·악화·유지를 모두 표시하고 숨기지 않는다."""
    _owned(db, org.id, festival_id)
    rows = svc.latest(db, festival_id, limit=2)
    if len(rows) < 2:
        return DiagnosisComparison(
            comparable=False,
            reason="FIRST_DIAGNOSIS",
        )

    current, previous = rows[0], rows[1]

    # 두 진단이 다른 공급자(실데이터 ↔ 데모)를 썼으면 비교하지 않는다.
    # 외부 API 장애로 인한 점수 변화를 기획 개선 효과로 오해하게 만들기 때문이다.
    def _provider(d: Diagnosis) -> str:
        return ((d.input_snapshot or {}).get("tourism") or {}).get("provider", "")

    if _provider(current) != _provider(previous):
        return DiagnosisComparison(comparable=False, reason="PROVIDER_MISMATCH")

    disclosed = rubric.is_score_disclosed(db, current.rubric_version)

    def _by_cat(d: Diagnosis) -> dict[DiagnosisCategory, DiagnosisItem]:
        return {i.category: i for i in d.items}

    cur_items, prev_items = _by_cat(current), _by_cat(previous)
    deltas: list[DiagnosisDelta] = []
    for cat in DiagnosisCategory:
        c, p = cur_items.get(cat), prev_items.get(cat)
        if c is None or p is None:
            continue
        deltas.append(
            DiagnosisDelta(
                category=cat,
                previous=float(p.score) if disclosed else None,
                current=float(c.score) if disclosed else None,
                delta=round(float(c.score) - float(p.score), 2) if disclosed else None,
            )
        )

    improved = [d for d in deltas if (d.delta or 0) > 0]
    biggest = max(improved, key=lambda d: d.delta or 0, default=None)
    biggest_payload = None
    if biggest is not None:
        item = cur_items[biggest.category]
        biggest_payload = {
            "category": biggest.category.value,
            "label": CATEGORY_LABELS[biggest.category],
            "delta": biggest.delta,
            "reason": item.reason,
            "recommendation": item.recommendation,
        }

    return DiagnosisComparison(
        comparable=True,
        previous={
            "id": previous.id,
            "total_score": float(previous.total_score) if disclosed and previous.total_score else None,
            "risk": previous.risk.value if disclosed and previous.risk else None,
            "created_at": previous.created_at.isoformat(),
        },
        current={
            "id": current.id,
            "total_score": float(current.total_score) if disclosed and current.total_score else None,
            "risk": current.risk.value if disclosed and current.risk else None,
            "created_at": current.created_at.isoformat(),
        },
        delta=(
            round(float(current.total_score) - float(previous.total_score), 2)
            if disclosed and current.total_score is not None and previous.total_score is not None
            else None
        ),
        items=deltas,
        biggest_improvement=biggest_payload,
    )
