"""운영 인사이트 · 추천 판정. 계약 §5, §14.5.

축제 당일 대시보드가 **10초마다** 부릅니다. 매번 전체 집계를 다시 돌리고
전체 JSON 을 내려보내면 부스가 늘수록 비용이 선형으로 커집니다. 그래서 응답
본문의 해시를 `ETag` 로 붙이고, 바뀐 게 없으면 `304` 로 끊습니다 — 참여가
뜸한 시간대에는 폴링의 대부분이 304 가 됩니다.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Header, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core.deps import (
    CanOperate,
    CurrentOrg,
    DbSession,
    FestivalAccess,
    OptionalStaff,
)
from festaflow.core.errors import not_found
from festaflow.models import Booth, Festival, RecommendationFeedback, StampBoard
from festaflow.schemas.operations import (
    BoothLoadOut,
    FeedbackIn,
    FeedbackOut,
    InsightKpi,
    InsightsOut,
    RecommendationOut,
    WarningOut,
)
from festaflow.services import grants, operations_insights, operations_recommendations
from festaflow.services.operations_recommendations import status_label

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["operations"])

OPERATOR = [FestivalAccess]

#: 계약 §5 의 문구 그대로. 화면이 지어내지 않도록 서버가 내려준다.
DISCLAIMER = (
    "이 지표는 부스에서 검증된 QR/미션 완료 건수를 현장 참여량의 proxy로 사용한 "
    "참여 편중 위험 지표이며, 실제 인원수나 물리적 밀집도가 아닙니다."
)


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


def _etag(payload: InsightsOut) -> str:
    """본문에서 `generated_at` 을 뺀 해시.

    시각을 포함하면 매 요청 ETag 가 달라져 304 가 영원히 나오지 않는다.
    실제로 바뀌었는지는 집계값으로만 판단해야 한다.
    """
    body = payload.model_dump(mode="json")
    body.pop("generated_at", None)
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return f'W/"{digest[:32]}"'


@router.get(
    "/operations/insights", response_model=InsightsOut, dependencies=[*OPERATOR, CanOperate]
)
def get_insights(
    festival_id: int,
    db: DbSession,
    org: CurrentOrg,
    response: Response,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
):
    _owned(db, org.id, festival_id)

    insights = operations_insights.build(db, festival_id)
    recs = operations_recommendations.build(insights)

    # 보드가 없는 축제도 있다(조각 보드를 안 쓰는 행사). 없으면 경고도 없다.
    warnings: list[WarningOut] = []
    board = db.execute(
        select(StampBoard).where(StampBoard.festival_id == festival_id)
    ).scalar_one_or_none()
    if board is not None:
        warning = grants.uncompletable_warning(db, festival_id, board)
        if warning:
            warnings.append(WarningOut(**warning))

    payload = InsightsOut(
        generated_at=insights.generated_at,
        kpi=InsightKpi(
            total_participants=insights.total_participants,
            total_completions=insights.total_completions,
            completions_last_30m=insights.completions_last_30m,
            high_concentration_booths=insights.high_concentration_booths,
        ),
        booths=[
            BoothLoadOut(
                booth_id=b.booth.id,
                name=b.booth.name,
                is_active=b.booth.is_active,
                total_completions=b.total_completions,
                unique_participants=b.unique_participants,
                last_10m=b.recent[10],
                last_30m=b.recent[30],
                last_60m=b.recent[60],
                share_last_30m=b.share_last_30m,
                status=b.status,
                status_reason=b.status_reason,
                status_label=status_label(b, enough=insights.enough_data),
                last_completed_at=b.last_completed_at,
            )
            for b in insights.booths
        ],
        recommendations=[
            RecommendationOut(
                type=r.type,
                situation=r.situation,
                evidence=r.evidence,
                action=r.action,
                target_booth_id=r.target_booth_id,
            )
            for r in recs
        ],
        warnings=warnings,
        disclaimer=DISCLAIMER,
    )

    tag = _etag(payload)
    response.headers["ETag"] = tag
    # 프록시가 캐시하면 다른 운영자의 인사이트가 섞인다. 캐시 주체는 브라우저뿐이다.
    response.headers["Cache-Control"] = "private, no-cache"
    if if_none_match and tag in [v.strip() for v in if_none_match.split(",")]:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": tag, "Cache-Control": "private, no-cache"},
        )
    return payload


@router.post(
    "/recommendations/feedback",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*OPERATOR, CanOperate],
)
def record_feedback(
    festival_id: int,
    body: FeedbackIn,
    db: DbSession,
    org: CurrentOrg,
    staff: OptionalStaff,
) -> FeedbackOut:
    """추천이 현장과 맞았는지 기록한다.

    같은 추천을 두 번 눌러도 막지 않습니다 — 운영자가 판단을 바꾸는 것은
    정상이고, 리포트는 시각순으로 마지막 판정을 씁니다. 유니크 제약을 걸면
    "아까 잘못 눌렀다" 를 되돌릴 방법이 없어집니다.
    """
    _owned(db, org.id, festival_id)

    if body.booth_id is not None:
        # 타 축제 부스 ID 를 넣으면 리포트 적중률이 조용히 오염된다.
        booth = db.execute(
            select(Booth).where(
                Booth.id == body.booth_id, Booth.festival_id == festival_id
            )
        ).scalar_one_or_none()
        if booth is None:
            raise not_found("부스")

    observed = body.observed_at
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)

    record = RecommendationFeedback(
        festival_id=festival_id,
        booth_id=body.booth_id,
        rec_type=body.rec_type,
        observed_at=observed,
        verdict=body.verdict,
        staff_id=staff.id if staff is not None else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return FeedbackOut(
        id=record.id,
        rec_type=record.rec_type,
        booth_id=record.booth_id,
        verdict=record.verdict,
        observed_at=record.observed_at,
    )
