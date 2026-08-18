"""부스 지급과 조각 공개 — docs/03-api-contract.md §8, docs/02-data-model.md §7.

중복 지급 방지를 **애플리케이션 조건문에만 두지 않습니다.** 스키마에 이미 유니크
제약이 있고(`uq_participations_grant`, `uq_stamp_reveals_booth`,
`uq_booth_scan_uses_window`), 여기서는 그 제약이 터졌을 때를 정상 흐름으로
받아 계약의 에러 코드나 `was_already_granted` 로 번역합니다.
조건문만 믿으면 현장에서 지급 버튼을 두 번 누르는 동시 요청에 그대로 뚫립니다.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.errors import ApiError, not_found, subject_particle
from festaflow.models import (
    Booth,
    BoothScanUse,
    Festival,
    Mission,
    Participant,
    Participation,
    RewardCampaign,
    StampBoard,
    StampReveal,
    StampTile,
)
from festaflow.models.enums import (
    BoothVerifyMode,
    GrantUnit,
    ParticipationStatus,
    RevealMode,
)

log = logging.getLogger(__name__)


# ── 참여자 ──────────────────────────────────────────────────────────────────


def _forget(db: Session, obj: object) -> None:
    """savepoint 롤백 뒤 남은 참조를 정리한다. 이미 떨어져 나갔으면 그냥 둔다."""
    if obj in db:
        db.expunge(obj)


def normalize_code(raw: str) -> str:
    """QR 스캔 결과와 수동 입력을 같은 값으로 만든다.

    현장에서는 사람이 코드를 손으로 옮겨 적는다. 공백과 대소문자를 서버가
    흡수하지 않으면 "안 되는데요" 문의가 그대로 운영 부담이 된다.
    """
    return "".join(raw.split()).upper()


def issue_participant(db: Session, festival: Festival) -> tuple[Participant, str]:
    """참여자를 발급하고 평문 비밀을 함께 돌려준다. 비밀은 이때만 나온다."""
    secret = security.generate_participant_secret()

    # 코드 충돌은 32^8 중 하나라 사실상 없지만, 있으면 조용히 실패하는 대신 다시 뽑는다.
    for _ in range(5):
        participant = Participant(
            festival_id=festival.id,
            code=security.generate_participant_code(),
            secret_hash=security.hash_participant_secret(secret),
        )
        try:
            # ⚠ add 를 savepoint **안에서** 해야 한다. 밖에서 add 하면 flush 실패가
            #    바깥 트랜잭션까지 무효화해(PendingRollbackError) 이후 쿼리가 전부 죽는다.
            with db.begin_nested():
                db.add(participant)
                db.flush()
        except IntegrityError:
            _forget(db, participant)
            continue
        return participant, secret

    raise ApiError(
        503, "CODE_ALLOCATION_FAILED", "참여 코드를 발급하지 못했습니다. 다시 시도해 주세요."
    )


def find_participant(db: Session, festival_id: int, code: str) -> Participant:
    p = db.execute(
        select(Participant).where(
            Participant.festival_id == festival_id,
            Participant.code == normalize_code(code),
        )
    ).scalar_one_or_none()
    if p is None:
        raise ApiError(404, "PARTICIPANT_NOT_FOUND", "발급되지 않은 참여 코드입니다.")
    return p


# ── 보상 캠페인 ─────────────────────────────────────────────────────────────


def active_campaigns(
    db: Session, festival_id: int, *, now: datetime | None = None
) -> list[RewardCampaign]:
    """서버 시각 기준 활성 캠페인. 클라이언트가 시각을 판정하지 않는다."""
    at = now or datetime.now(UTC)
    return list(
        db.execute(
            select(RewardCampaign)
            .where(
                RewardCampaign.festival_id == festival_id,
                RewardCampaign.is_active.is_(True),
                RewardCampaign.starts_at <= at,
                RewardCampaign.ends_at > at,
            )
            .order_by(RewardCampaign.bonus_points.desc(), RewardCampaign.id)
        ).scalars()
    )


def pick_campaign(
    db: Session, *, festival_id: int, booth_id: int, mission_id: int, now: datetime | None = None
) -> RewardCampaign | None:
    """이 지급에 붙는 캠페인. **겹치면 합산하지 않고 최대 보너스 1건만** 적용한다."""
    candidates = [
        c
        for c in active_campaigns(db, festival_id, now=now)
        if c.booth_id == booth_id and c.mission_id in (None, mission_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c.bonus_points, c.id))


# ── 보드 ────────────────────────────────────────────────────────────────────


def get_board(db: Session, festival_id: int) -> StampBoard:
    board = db.execute(
        select(StampBoard).where(StampBoard.festival_id == festival_id)
    ).scalar_one_or_none()
    if board is None:
        raise not_found("스탬프 보드")
    return board


def current_tiles(db: Session, board: StampBoard) -> list[StampTile]:
    return list(
        db.execute(
            select(StampTile)
            .where(StampTile.board_id == board.id, StampTile.board_version == board.version)
            .order_by(StampTile.tile_index)
        ).scalars()
    )


def reveals_of(db: Session, board: StampBoard, participant_id: int) -> list[StampReveal]:
    """현재 버전의 공개 기록만. 버전이 올라가면 과거 기록은 집계에서 빠진다."""
    return list(
        db.execute(
            select(StampReveal)
            .where(
                StampReveal.board_id == board.id,
                StampReveal.board_version == board.version,
                StampReveal.participant_id == participant_id,
            )
            .order_by(StampReveal.revealed_at)
        ).scalars()
    )


def grant_unit_count(db: Session, festival_id: int, board: StampBoard) -> int:
    """지급 단위 수 — `booth` 면 활성 부스 수, `mission` 면 활성 미션 수."""
    if board.grant_unit == GrantUnit.BOOTH:
        stmt = select(func.count(Booth.id)).where(
            Booth.festival_id == festival_id,
            Booth.archived_at.is_(None),
            Booth.is_active.is_(True),
        )
    else:
        stmt = select(func.count(Mission.id)).where(
            Mission.festival_id == festival_id,
            Mission.archived_at.is_(None),
            Mission.is_active.is_(True),
        )
    return db.execute(stmt).scalar_one()


def uncompletable_warning(db: Session, festival_id: int, board: StampBoard) -> dict | None:
    """`rows*cols > 지급 단위 수` 면 완성이 불가능하다 — 데이터모델 C2.

    당일에 발견하면 늦다. 진단과 운영 대시보드가 같은 함수를 본다.
    """
    units = grant_unit_count(db, festival_id, board)
    if board.total_tiles <= units:
        return None
    unit_label = "활성 부스" if board.grant_unit == GrantUnit.BOOTH else "활성 미션"
    return {
        "code": "BOARD_UNCOMPLETABLE",
        "message": (
            f"{board.total_tiles}조각 보드에 {unit_label}{subject_particle(unit_label)} "
            f"{units}개라 완성이 불가능합니다."
        ),
    }


#: 제안할 격자의 최소·최대 변 길이. DB 의 rows_range/cols_range 와 같아야 한다.
GRID_MIN, GRID_MAX = 2, 5


@dataclass(frozen=True)
class GridOption:
    """기획자에게 제시할 격자 후보 한 개."""

    rows: int
    cols: int
    #: 지급 단위 수와 정확히 맞는가 — 부스가 모두 조각 하나씩 갖는 구성
    exact: bool
    #: 조각을 못 받는 지급 단위 수(0 이면 남는 부스가 없다)
    leftover: int

    @property
    def total(self) -> int:
        return self.rows * self.cols


def grid_options(unit_count: int, *, limit: int = 3) -> list[GridOption]:
    """지급 단위 수에 맞춰 쪼갤 격자 후보를 만든다.

    조각 수는 단독으로 정할 값이 아니다. `rows*cols` 가 지급 단위 수보다 크면
    아무도 완성할 수 없고, 작으면 그만큼의 부스가 조각 없이 남는다. 그래서
    **단위 수를 넘지 않는 격자만** 제안하고, 정확히 맞는 것을 앞에 세운다.

    8개처럼 정사각이 안 되는 수도 2×4 로 정확히 나뉜다. 소수(5·7·11)는 정확한
    격자가 없어 가장 가까운 아래쪽 격자를 제안한다 — 그때 남는 부스 수를
    `leftover` 로 알려주고 숨기지 않는다.
    """
    if unit_count < GRID_MIN * GRID_MIN:
        return []

    seen: set[tuple[int, int]] = set()
    candidates: list[GridOption] = []
    for rows in range(GRID_MIN, GRID_MAX + 1):
        for cols in range(rows, GRID_MAX + 1):  # rows <= cols — 90도 회전은 같은 격자
            total = rows * cols
            if total > unit_count or (rows, cols) in seen:
                continue
            seen.add((rows, cols))
            candidates.append(
                GridOption(
                    rows=rows,
                    cols=cols,
                    exact=total == unit_count,
                    leftover=unit_count - total,
                )
            )

    # 남는 부스가 적은 순 → 조각이 많은 순. 정확히 맞는 격자가 자연히 1순위가 된다.
    candidates.sort(key=lambda g: (g.leftover, -g.total))
    return candidates[:limit]


@dataclass
class Progress:
    revealed_count: int
    total_tiles: int

    @property
    def is_complete(self) -> bool:
        return self.total_tiles > 0 and self.revealed_count >= self.total_tiles


def progress_of(db: Session, board: StampBoard, participant_id: int) -> Progress:
    count = db.execute(
        select(func.count(StampReveal.id)).where(
            StampReveal.board_id == board.id,
            StampReveal.board_version == board.version,
            StampReveal.participant_id == participant_id,
        )
    ).scalar_one()
    return Progress(revealed_count=count, total_tiles=board.total_tiles)


def _pick_tile(
    db: Session, board: StampBoard, participant_id: int, booth_id: int
) -> StampTile | None:
    """공개할 타일을 고른다. 없으면 None — 포인트 지급 자체는 막지 않는다."""
    revealed = reveals_of(db, board, participant_id)
    taken = {r.tile_id for r in revealed}
    tiles = current_tiles(db, board)

    if board.reveal_mode == RevealMode.BOOTH_ASSIGNED:
        assigned = next((t for t in tiles if t.assigned_booth_id == booth_id), None)
        if assigned is None:
            # 이 부스는 보드에 올라가 있지 않다. 포인트만 지급한다.
            return None
        if assigned.id in taken:
            raise ApiError(
                409,
                "NO_TILE_AVAILABLE",
                "이 부스의 조각은 이미 받았습니다.",
                {"tile_index": assigned.tile_index},
            )
        return assigned

    # random — 아직 안 받은 타일 중 하나. 보드를 이미 채웠으면 None.
    remaining = [t for t in tiles if t.id not in taken]
    if not remaining:
        return None
    return secrets.choice(remaining)


# ── 지급 ────────────────────────────────────────────────────────────────────


@dataclass
class GrantOutcome:
    participation: Participation
    revealed_tile: StampTile | None
    progress: Progress
    was_already_granted: bool


def _existing(
    db: Session, participant_id: int, mission_id: int, client_request_id: str | None
) -> Participation | None:
    stmt = select(Participation).where(
        Participation.participant_id == participant_id,
        Participation.mission_id == mission_id,
    )
    found = db.execute(stmt).scalar_one_or_none()
    if found is not None:
        return found
    if client_request_id:
        return db.execute(
            select(Participation).where(Participation.client_request_id == client_request_id)
        ).scalar_one_or_none()
    return None


def _already(db: Session, board: StampBoard, existing: Participation) -> GrantOutcome:
    """재전송·두 번 누름. 새로 지급하지 않고 지금 상태를 그대로 돌려준다."""
    reveal = db.execute(
        select(StampReveal).where(StampReveal.participation_id == existing.id)
    ).scalar_one_or_none()
    tile = db.get(StampTile, reveal.tile_id) if reveal is not None else None
    return GrantOutcome(
        participation=existing,
        revealed_tile=tile,
        progress=progress_of(db, board, existing.participant_id),
        was_already_granted=True,
    )


def grant(
    db: Session,
    *,
    festival: Festival,
    booth: Booth,
    mission: Mission,
    participant: Participant,
    verified_via: BoothVerifyMode,
    granted_by_staff_id: int | None = None,
    scan_window_index: int | None = None,
    client_request_id: str | None = None,
    queued_at: datetime | None = None,
    now: datetime | None = None,
) -> GrantOutcome:
    """미션 지급 + 조각 공개를 한 트랜잭션으로 처리한다.

    `queued_at` 이 있으면 `completed_at` 을 그 값으로 기록한다 — 오프라인 큐가
    복구된 시각에 완료가 몰려 보이면 운영 인사이트의 편중 판정이 망가진다.
    """
    at = now or datetime.now(UTC)
    board = get_board(db, festival.id)

    # ── 계약 §8.1 의 검증 순서 ──
    if mission.booth_id != booth.id:
        raise ApiError(409, "MISSION_NOT_IN_BOOTH", "이 미션은 해당 부스의 미션이 아닙니다.")
    if not booth.is_active or booth.archived_at is not None:
        raise ApiError(409, "BOOTH_INACTIVE", "중지된 부스입니다.")
    if not mission.is_active or mission.archived_at is not None:
        raise ApiError(409, "MISSION_INACTIVE", "중지된 미션입니다.")

    existing = _existing(db, participant.id, mission.id, client_request_id)
    if existing is not None:
        return _already(db, board, existing)

    # 스캔 사용 기록을 **지급보다 먼저** 넣는다. 1 스캔 = 1 미션이라
    # 유니크 제약이 여기서 걸려야 두 번째 미션이 같은 스캔으로 넘어가지 못한다.
    scan_use: BoothScanUse | None = None
    if scan_window_index is not None:
        scan_use = BoothScanUse(
            booth_id=booth.id,
            window_index=scan_window_index,
            participant_id=participant.id,
        )
        try:
            with db.begin_nested():
                db.add(scan_use)
                db.flush()
        except IntegrityError:
            _forget(db, scan_use)
            raise ApiError(
                409, "SCAN_ALREADY_USED", "이 부스에서 방금 스탬프를 받았습니다."
            ) from None

    campaign = pick_campaign(
        db, festival_id=festival.id, booth_id=booth.id, mission_id=mission.id, now=at
    )

    participation = Participation(
        festival_id=festival.id,
        participant_id=participant.id,
        mission_id=mission.id,
        booth_id=booth.id,
        status=ParticipationStatus.COMPLETED,
        completed_at=queued_at or at,
        base_points=mission.points,
        bonus_points=campaign.bonus_points if campaign else 0,
        reward_campaign_id=campaign.id if campaign else None,
        verified_via=verified_via,
        granted_by_staff_id=granted_by_staff_id,
        client_request_id=client_request_id,
        queued_at=queued_at,
        synced_at=at if queued_at else None,
    )
    try:
        with db.begin_nested():
            db.add(participation)
            db.flush()
    except IntegrityError:
        # 동시 요청이 먼저 넣었다. 조건문으로는 막을 수 없는 경로다.
        _forget(db, participation)
        raced = _existing(db, participant.id, mission.id, client_request_id)
        if raced is None:
            raise
        return _already(db, board, raced)

    tile = _pick_tile(db, board, participant.id, booth.id)
    if tile is not None:
        reveal = StampReveal(
            board_id=board.id,
            board_version=board.version,
            participant_id=participant.id,
            tile_id=tile.id,
            # grant_unit='mission' 이면 booth_id 를 비운다 — 부스당 1조각 유니크
            # 인덱스가 같은 부스의 두 번째 미션을 막아버리기 때문이다.
            booth_id=booth.id if board.grant_unit == GrantUnit.BOOTH else None,
            participation_id=participation.id,
        )
        try:
            with db.begin_nested():
                db.add(reveal)
                db.flush()
        except IntegrityError:
            # 부스당 1조각(grant_unit='booth')에서 이 부스 조각을 이미 받은 경우.
            # 포인트 지급은 유지하고 조각만 주지 않는다.
            _forget(db, reveal)
            tile = None

    db.flush()
    return GrantOutcome(
        participation=participation,
        revealed_tile=tile,
        progress=progress_of(db, board, participant.id),
        was_already_granted=False,
    )


# ── 부스 스캔 ───────────────────────────────────────────────────────────────


def verify_scan_token(booth: Booth, token: str, *, now: datetime | None = None) -> int:
    """토큰이 맞는 window 를 돌려준다. 계약 §8.3 의 오류 코드로 실패한다."""
    window = security.match_scan_window(booth.qr_secret, booth.id, token, now)
    if window is not None:
        return window

    # 만료와 위조를 구분한다 — 참여자 화면의 안내 문구가 달라야 한다.
    # 만료면 "다시 스캔", 위조면 다시 스캔해도 안 되므로 그렇게 안내하면 안 된다.
    for back in range(2, 12):
        candidate = security.current_window(now) - back
        if security.booth_scan_token(booth.qr_secret, booth.id, candidate) == token:
            raise ApiError(410, "SCAN_TOKEN_EXPIRED", "부스 화면의 QR 을 다시 스캔해 주세요.")
    raise ApiError(400, "SCAN_TOKEN_INVALID", "이 부스의 QR 토큰이 아닙니다.")


def scan_used_in_window(
    db: Session, *, booth_id: int, window_index: int, participant_id: int
) -> bool:
    return (
        db.execute(
            select(BoothScanUse.id).where(
                BoothScanUse.booth_id == booth_id,
                BoothScanUse.window_index == window_index,
                BoothScanUse.participant_id == participant_id,
            )
        ).scalar_one_or_none()
        is not None
    )
