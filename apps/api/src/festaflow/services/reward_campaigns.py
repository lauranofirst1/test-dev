"""한시 추가 보상 — 지금 저 부스로 사람을 보내는 지렛대. 계약 §6, 기획서 7.2.

**경품 뽑기와 다른 물건입니다.** 경품은 보드를 완성한 사람에게 주는 실물이고,
캠페인은 *특정 부스의 미션 포인트를 정해진 시간 동안만* 올리는 장치입니다.
운영 대시보드가 편중을 발견했을 때 쓸 수 있는 개입 수단이 이것뿐입니다 —
경품은 부스별로 조절할 수 있는 물건이 아닙니다.

지급 시점의 보너스 계산은 `services/grants.py` 의 `pick_campaign` 에 있습니다.
여기 있는 것은 캠페인 자체의 CRUD 와 검증입니다.

**캠페인 생성은 추천의 자동 실행이 아닙니다.** 대시보드의 추천 카드는 대상
부스를 폼에 채워 줄 뿐이고, 실제 실행은 운영자가 값을 확인하고 제출해야
일어납니다. 참여 데이터가 편향된 표본인 이상, 그 데이터로 포인트를 자동으로
바꾸면 아무도 결정하지 않은 개입이 현장에 나갑니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core.errors import ApiError, not_found
from festaflow.models import Booth, Mission, RewardCampaign

#: 캠페인 최대 길이. 축제 하루보다 길면 "한시"가 아니고, 그건 미션 포인트를
#: 올리는 것과 같다 — 그쪽은 미션 편집으로 해야 이력이 남는다.
MAX_HOURS = 24


def get(db: Session, festival_id: int, campaign_id: int) -> RewardCampaign:
    c = db.execute(
        select(RewardCampaign).where(
            RewardCampaign.id == campaign_id,
            RewardCampaign.festival_id == festival_id,
        )
    ).scalar_one_or_none()
    if c is None:
        raise not_found("보상 캠페인")
    return c


def listing(
    db: Session, festival_id: int, *, active_only: bool = False, now: datetime | None = None
) -> list[RewardCampaign]:
    """`active_only` 는 **서버 시각**으로 판정한다.

    클라이언트가 `ends_at` 을 보고 스스로 거르면 폰 시계가 틀어진 만큼 배너가
    일찍 사라지거나 끝난 캠페인이 계속 떠 있다. 축제장에서 "포인트 2배라며
    왜 안 줘요"가 여기서 나온다.
    """
    at = now or datetime.now(UTC)
    stmt = select(RewardCampaign).where(RewardCampaign.festival_id == festival_id)
    if active_only:
        stmt = stmt.where(
            RewardCampaign.is_active.is_(True),
            RewardCampaign.starts_at <= at,
            RewardCampaign.ends_at > at,
        )
    return list(
        db.execute(stmt.order_by(RewardCampaign.starts_at.desc(), RewardCampaign.id.desc()))
        .scalars()
    )


def is_active(campaign: RewardCampaign, *, now: datetime | None = None) -> bool:
    at = now or datetime.now(UTC)
    return campaign.is_active and campaign.starts_at <= at < campaign.ends_at


def _aware(value: datetime) -> datetime:
    """naive 로 들어온 시각을 UTC 로 본다.

    DB 컬럼은 timezone-aware 라 naive 와 비교하면 TypeError 가 난다. 요청 본문에
    타임존 없는 문자열이 오는 경우가 실제로 있다(사람이 손으로 만든 요청).
    """
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def validate(
    db: Session,
    festival_id: int,
    *,
    booth_id: int,
    mission_id: int | None,
    starts_at: datetime,
    ends_at: datetime,
) -> tuple[datetime, datetime]:
    """부스·미션 소속과 기간을 검증한다. HTTP 라우트에 두지 않는 이유가 이것이다 —
    같은 검증을 만드는 곳과 고치는 곳 두 군데에 두면 반드시 한쪽이 뒤처진다."""
    starts_at, ends_at = _aware(starts_at), _aware(ends_at)

    if ends_at <= starts_at:
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "종료 시각이 시작 시각보다 뒤여야 합니다.",
            {"field": "ends_at"},
        )
    if (ends_at - starts_at).total_seconds() > MAX_HOURS * 3600:
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            f"캠페인은 최대 {MAX_HOURS}시간까지입니다. "
            "더 길게 두려면 미션 포인트 자체를 올리세요.",
            {"field": "ends_at"},
        )

    booth = db.execute(
        select(Booth).where(
            Booth.id == booth_id,
            Booth.festival_id == festival_id,
            Booth.archived_at.is_(None),
        )
    ).scalar_one_or_none()
    if booth is None:
        # 타 축제 부스에 캠페인을 걸면 그 축제 참여자에게 포인트가 나간다.
        raise not_found("부스")

    if mission_id is not None:
        mission = db.execute(
            select(Mission).where(
                Mission.id == mission_id,
                Mission.festival_id == festival_id,
                Mission.booth_id == booth_id,
                Mission.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if mission is None:
            # 다른 부스의 미션을 지정하면 캠페인이 영원히 안 걸린다.
            # 조용히 통과시키면 운영자는 왜 안 되는지 알 방법이 없다.
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                "선택한 미션이 이 부스의 활성 미션이 아닙니다.",
                {"field": "mission_id"},
            )

    return starts_at, ends_at


def create(
    db: Session,
    festival_id: int,
    *,
    booth_id: int,
    mission_id: int | None,
    title: str,
    message: str,
    bonus_points: int,
    starts_at: datetime,
    ends_at: datetime,
    staff_id: int | None = None,
) -> RewardCampaign:
    starts_at, ends_at = validate(
        db,
        festival_id,
        booth_id=booth_id,
        mission_id=mission_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    campaign = RewardCampaign(
        festival_id=festival_id,
        booth_id=booth_id,
        mission_id=mission_id,
        title=title.strip(),
        message=message.strip(),
        bonus_points=bonus_points,
        starts_at=starts_at,
        ends_at=ends_at,
        created_by_staff_id=staff_id,
    )
    db.add(campaign)
    db.flush()
    return campaign


def update(db: Session, campaign: RewardCampaign, **fields) -> RewardCampaign:
    """이미 지급된 보너스는 바뀌지 않는다.

    지급 시점에 `participations.bonus_points` 로 스냅샷을 박아 두기 때문입니다.
    캠페인을 고치거나 꺼도 과거 지급액은 그대로입니다 — 받은 포인트가 나중에
    줄어드는 것만큼 현장에서 설명하기 어려운 일이 없습니다.
    """
    booth_id = fields.get("booth_id", campaign.booth_id)
    starts_at = fields.get("starts_at", campaign.starts_at)
    ends_at = fields.get("ends_at", campaign.ends_at)
    starts_at, ends_at = validate(
        db,
        campaign.festival_id,
        booth_id=booth_id,
        mission_id=fields.get("mission_id", campaign.mission_id),
        starts_at=starts_at,
        ends_at=ends_at,
    )
    fields["starts_at"], fields["ends_at"] = starts_at, ends_at

    for key, value in fields.items():
        setattr(campaign, key, value.strip() if isinstance(value, str) else value)
    db.flush()
    return campaign


def stop(db: Session, campaign: RewardCampaign) -> RewardCampaign:
    """캠페인을 끈다. **행을 지우지 않습니다.**

    `participations.reward_campaign_id` 가 이 행을 가리키고 있어, 지우면 어떤
    지급에 어떤 캠페인이 붙었는지가 사라집니다. 사후 리포트의 개입 효과 분석이
    그 참조로 돌아갑니다.
    """
    campaign.is_active = False
    db.flush()
    return campaign
