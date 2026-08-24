"""보상 캠페인 CRUD 와 개입 효과. 계약 §6.

목록은 **참여자 화면도 부릅니다** — 활성 캠페인 배너가 거기서 나옵니다.
그래서 GET 만 기관 스코프 밖에 두고, 만들고 고치고 끄는 것은 운영자로 막습니다.

검증과 지급 계산은 라우트에 두지 않습니다(`services/reward_campaigns.py`,
`services/grants.py`). 같은 검증이 만드는 곳과 고치는 곳에 흩어지면 반드시
한쪽이 뒤처집니다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
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
from festaflow.models import Booth, Festival, Mission, RewardCampaign
from festaflow.schemas.campaign import (
    CampaignIn,
    CampaignList,
    CampaignOut,
    CampaignUpdate,
    ImpactOut,
    ImpactWindow,
    TopBoothOut,
)
from festaflow.services import reward_campaign_impact as impact_svc
from festaflow.services import reward_campaigns as svc

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["campaigns"])

OPERATOR = [FestivalAccess, CanOperate]


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


def _live(db: Session, festival_id: int) -> Festival:
    """참여자도 부르는 경로용. 기관 스코프를 요구하지 않는다."""
    f = db.execute(
        select(Festival).where(Festival.id == festival_id, Festival.archived_at.is_(None))
    ).scalar_one_or_none()
    if f is None:
        raise not_found("축제")
    return f


def _out(db: Session, c: RewardCampaign, *, now: datetime) -> CampaignOut:
    # 부스명·미션명을 함께 내려준다. 화면이 ID 만 받으면 목록을 그리려고
    # 부스 API 를 한 번 더 불러야 하고, 그 사이 보관된 부스는 이름이 비어 버린다.
    booth = db.get(Booth, c.booth_id)
    mission = db.get(Mission, c.mission_id) if c.mission_id else None
    return CampaignOut(
        id=c.id,
        festival_id=c.festival_id,
        booth_id=c.booth_id,
        booth_name=booth.name if booth else f"부스 {c.booth_id}",
        mission_id=c.mission_id,
        mission_title=mission.title if mission else None,
        title=c.title,
        message=c.message,
        bonus_points=c.bonus_points,
        starts_at=c.starts_at,
        ends_at=c.ends_at,
        is_active=c.is_active,
        is_live=svc.is_active(c, now=now),
    )


@router.get("/reward-campaigns", response_model=CampaignList)
def list_campaigns(
    festival_id: int,
    db: DbSession,
    active_only: Annotated[bool, Query()] = False,
) -> CampaignList:
    """`active_only` 는 **서버 시각** 판정이다. 참여자 화면이 이 경로를 쓴다."""
    _live(db, festival_id)
    now = datetime.now(UTC)
    items = svc.listing(db, festival_id, active_only=active_only, now=now)
    return CampaignList(
        items=[_out(db, c, now=now) for c in items], total=len(items)
    )


@router.post(
    "/reward-campaigns",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=OPERATOR,
)
def create_campaign(
    festival_id: int,
    body: CampaignIn,
    db: DbSession,
    org: CurrentOrg,
    staff: OptionalStaff,
) -> CampaignOut:
    """운영자의 **명시적 제출**로만 만들어진다. 추천이 자동으로 실행하지 않는다."""
    _owned(db, org.id, festival_id)
    c = svc.create(
        db,
        festival_id,
        booth_id=body.booth_id,
        mission_id=body.mission_id,
        title=body.title,
        message=body.message,
        bonus_points=body.bonus_points,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        staff_id=staff.id if staff is not None else None,
    )
    db.commit()
    db.refresh(c)
    return _out(db, c, now=datetime.now(UTC))


@router.put(
    "/reward-campaigns/{campaign_id}", response_model=CampaignOut, dependencies=OPERATOR
)
def update_campaign(
    festival_id: int,
    campaign_id: int,
    body: CampaignUpdate,
    db: DbSession,
    org: CurrentOrg,
) -> CampaignOut:
    _owned(db, org.id, festival_id)
    c = svc.get(db, festival_id, campaign_id)
    svc.update(db, c, **body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(c)
    return _out(db, c, now=datetime.now(UTC))


@router.delete(
    "/reward-campaigns/{campaign_id}", response_model=CampaignOut, dependencies=OPERATOR
)
def stop_campaign(
    festival_id: int, campaign_id: int, db: DbSession, org: CurrentOrg
) -> CampaignOut:
    """끄는 것이지 지우는 것이 아니다 — 지급 이력이 이 행을 가리키고 있다."""
    _owned(db, org.id, festival_id)
    c = svc.get(db, festival_id, campaign_id)
    svc.stop(db, c)
    db.commit()
    db.refresh(c)
    return _out(db, c, now=datetime.now(UTC))


@router.get(
    "/reward-campaigns/{campaign_id}/impact",
    response_model=ImpactOut,
    dependencies=OPERATOR,
)
def campaign_impact(
    festival_id: int,
    campaign_id: int,
    db: DbSession,
    org: CurrentOrg,
    window_minutes: Annotated[int, Query(ge=5, le=180)] = impact_svc.DEFAULT_WINDOW_MINUTES,
) -> ImpactOut:
    _owned(db, org.id, festival_id)
    c = svc.get(db, festival_id, campaign_id)
    result = impact_svc.build(db, c, window_minutes=window_minutes)

    return ImpactOut(
        campaign_id=result.campaign_id,
        window_minutes=result.window_minutes,
        before=ImpactWindow(
            frm=result.before.frm,
            to=result.before.to,
            target_completions=result.before.target_completions,
            festival_completions=result.before.festival_completions,
            share=result.before.share,
        ),
        after=ImpactWindow(
            frm=result.after.frm,
            to=result.after.to,
            target_completions=result.after.target_completions,
            festival_completions=result.after.festival_completions,
            share=result.after.share,
        ),
        share_change_pp=result.share_change_pp,
        completion_change_rate=result.completion_change_rate,
        top_booth_before=(
            TopBoothOut(
                booth_id=result.top_booth_before.booth_id,
                name=result.top_booth_before.name,
                share_before=result.top_booth_before.share_before,
                share_after=result.top_booth_before.share_after,
            )
            if result.top_booth_before
            else None
        ),
        data_status=result.data_status,
        in_progress=result.in_progress,
        disclaimer=impact_svc.DISCLAIMER,
    )
