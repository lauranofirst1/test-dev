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
from datetime import UTC, datetime, timedelta

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
    BoothQrMode,
    BoothVerifyMode,
    GrantUnit,
    IdentityMode,
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


def normalize_student_no(raw: str) -> str:
    """학번 표기를 하나로 모은다.

    사람이 손으로 입력하는 값이라 공백과 하이픈이 섞입니다. 정규화하지 않으면
    `2025-1234` 와 `20251234` 가 서로 다른 학번이 되고, **1 학번 = 1 참여자**가
    그 순간 무너집니다 — 두 표기로 두 번 투표할 수 있게 됩니다.
    """
    return "".join(ch for ch in raw if ch.isalnum()).upper()


def find_by_student_no(
    db: Session, festival_id: int, student_no: str
) -> Participant | None:
    return db.execute(
        select(Participant).where(
            Participant.festival_id == festival_id,
            Participant.student_no == normalize_student_no(student_no),
        )
    ).scalar_one_or_none()


def reissue_for_student(
    db: Session, participant: Participant
) -> tuple[Participant, str]:
    """같은 학번으로 다시 들어온 경우 — **새 참여자를 만들지 않는다.**

    기기를 바꿨거나 브라우저 저장소를 지운 학생입니다. 여기서 새 참여자를 만들면
    학번 하나가 참여 코드 여러 개를 갖게 되고, 그건 스티커를 여러 장 붙이는
    것과 정확히 같습니다.

    대신 비밀만 새로 발급합니다. 옛 기기는 그 순간 로그아웃되고, 지금 기기가
    이어받습니다. 모은 조각도 투표도 그대로입니다.

    재발급 횟수를 셉니다. 남의 학번을 넣어 가로채는 시도는 이 숫자로 드러나며,
    운영자 화면이 그것을 보여줍니다.
    """
    secret = security.generate_participant_secret()
    participant.secret_hash = security.hash_participant_secret(secret)
    participant.recovery_attempts = (participant.recovery_attempts or 0) + 1
    participant.last_seen_at = datetime.now(UTC)
    db.flush()
    return participant, secret


def issue_participant(
    db: Session, festival: Festival, *, student_no: str | None = None
) -> tuple[Participant, str]:
    """참여자를 발급하고 평문 비밀을 함께 돌려준다. 비밀은 이때만 나온다.

    `identity_mode` 가 `student_id` 면 학번이 필요합니다. 이미 발급된 학번이면
    새로 만들지 않고 기존 참여자의 비밀만 새로 냅니다.
    """
    if festival.identity_mode == IdentityMode.STUDENT_ID:
        if not student_no or not normalize_student_no(student_no):
            raise ApiError(
                422,
                "STUDENT_NO_REQUIRED",
                "학번을 입력해 주세요. 이 행사는 학번으로 1인 1참여를 확인합니다.",
                {"field": "student_no"},
            )
        normalized = normalize_student_no(student_no)
        existing = find_by_student_no(db, festival.id, normalized)
        if existing is not None:
            return reissue_for_student(db, existing)
    else:
        # 익명 축제에 학번이 들어와도 저장하지 않는다. 받지 않겠다고 한 것을
        # 조용히 받아 두면 그 약속이 거짓이 된다.
        normalized = None

    secret = security.generate_participant_secret()

    # 코드 충돌은 32^8 중 하나라 사실상 없지만, 있으면 조용히 실패하는 대신 다시 뽑는다.
    for _ in range(5):
        participant = Participant(
            festival_id=festival.id,
            code=security.generate_participant_code(),
            student_no=normalized,
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
            # 같은 학번이 방금 다른 요청으로 들어왔다. 코드 충돌과 달리 다시
            # 뽑아도 해결되지 않으므로, 그 참여자를 찾아 이어받는다.
            if normalized:
                raced = find_by_student_no(db, festival.id, normalized)
                if raced is not None:
                    return reissue_for_student(db, raced)
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


def autofit_board(db: Session, festival_id: int) -> StampBoard | None:
    """지급 단위 수가 바뀌었으니 격자를 다시 맞춘다. 바꿨으면 보드를 돌려준다.

    조각 수는 부스 수에서 나옵니다. 기획 단계에 한 번 골라 굳혀 두면 부스를 더
    만들었을 때 조각을 못 받는 부스가 생기고, 뒤늦게 고치면 이미 모은 조각이
    초기화됩니다. 그래서 부스를 만들고 지울 때마다 서버가 따라 맞춥니다.

    **두 가지 경우에는 손대지 않습니다.**

    1. 운영자가 후보를 직접 골랐을 때(`grid_auto = False`). 부스 8개에 6조각처럼
       일부러 고른 구성이 있고, 그것을 서버가 되돌리면 고른 의미가 없습니다.
    2. **누군가 이미 조각을 모았을 때.** 격자를 바꾸는 것은 타일 집합을 바꾸는
       일이라 그 순간 진행이 초기화됩니다. 그건 확인을 받고 할 일이지 부스를
       하나 추가했다고 조용히 벌어질 일이 아닙니다.

    맞출 격자가 없으면(단위가 4개 미만) 그대로 둡니다 — 지울 격자가 아니라
    아직 정할 수 없는 상태입니다.
    """
    board = get_board(db, festival_id)
    if not board.grid_auto:
        return None

    options = grid_options(grant_unit_count(db, festival_id, board))
    if not options:
        return None

    best = options[0]
    if (best.rows, best.cols) == (board.rows, board.cols):
        return None

    revealed = db.execute(
        select(func.count(StampReveal.id)).where(
            StampReveal.board_id == board.id,
            StampReveal.board_version == board.version,
        )
    ).scalar_one()
    if revealed:
        return None

    board.rows = best.rows
    board.cols = best.cols
    board.version += 1
    for idx in range(board.total_tiles):
        db.add(StampTile(board_id=board.id, board_version=board.version, tile_index=idx))
    db.flush()
    return board


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
            # **문구가 롤백 사실을 숨기면 안 된다.**
            #
            # 조각 공개가 실패하면 참여 완료까지 롤백된다(스펙 §8.1 — 미션만
            # 완료되고 조각은 없는 상태를 막기 위해서다). 즉 포인트도 안 나갔다.
            #
            # "조각은 이미 받았습니다" 만 말하면 스태프는 "포인트는 갔겠지" 로
            # 읽고 넘어가고, 참여자는 아무것도 못 받는다.
            raise ApiError(
                409,
                "NO_TILE_AVAILABLE",
                "이 부스의 조각을 이미 받아서 지급되지 않았습니다. "
                "포인트도 나가지 않았습니다 — 다른 부스 미션으로 안내해 주세요.",
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
    db: Session,
    festival_id: int,
    participant_id: int,
    mission_id: int,
    client_request_id: str | None,
) -> Participation | None:
    """이미 지급된 건을 찾는다. 참여자·미션으로 먼저, 없으면 재전송 키로.

    **재전송 키 조회에 축제 스코프가 붙어 있다.** `client_request_id` 는
    클라이언트가 만들어 보내는 값이고 유니크 제약은 전역이라, 스코프가 없으면
    남의 축제 지급 기록이 `was_already_granted: true` 와 함께 그대로 돌아온다 —
    포인트·미션·부스·완료 시각이 전부 실려서. 우연한 UUID 충돌은 없다시피 하지만
    이건 **공격자가 고르는 값**이다.
    """
    stmt = select(Participation).where(
        Participation.participant_id == participant_id,
        Participation.mission_id == mission_id,
    )
    found = db.execute(stmt).scalar_one_or_none()
    if found is not None:
        return found
    if client_request_id:
        return db.execute(
            select(Participation).where(
                Participation.client_request_id == client_request_id,
                Participation.festival_id == festival_id,
            )
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


#: `queued_at` 을 믿어 줄 범위. 이 값은 **클라이언트가 정하는 시각**이라
#: 그대로 쓰면 부스 폰 하나로 완료 시각을 마음대로 적을 수 있다.
#:
#: 뒤쪽은 폰 시계가 조금 빠른 경우를 위한 여유다. 앞쪽은 오프라인 큐가 하루를
#: 넘겨 남아 있을 일이 없다는 판단이다 — 축제 하루가 끝나면 그 큐는 의미가 없다.
QUEUED_AT_FUTURE_TOLERANCE = timedelta(minutes=2)
QUEUED_AT_MAX_AGE = timedelta(hours=24)


def _trusted_queued_at(value: datetime | None, at: datetime) -> datetime | None:
    """범위를 벗어난 `queued_at` 은 **버린다.**

    거부하지 않고 버리는 이유는 지급 자체는 반드시 성공해야 하기 때문이다.
    오프라인 우선 지급의 요점은 현장에서 줄이 멈추지 않는 것이고, 폰 시계가
    틀렸다고 스탬프를 못 주면 그 요점이 사라진다. 시각만 서버 시각으로
    떨어뜨리면 최악의 경우가 "오프라인 큐를 안 쓴 것과 같음" 이 된다.
    """
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    skew = (aware - at).total_seconds()
    if aware > at + QUEUED_AT_FUTURE_TOLERANCE or aware < at - QUEUED_AT_MAX_AGE:
        # **조용히 버리지 않는다.**
        #
        # 버리면 `queued_at` 도 `synced_at` 도 비어, 그 지급은 DB 에서 온라인
        # 지급과 구분되지 않는다. 부스 폰 시계가 3분만 빨라도 그 부스의 오프라인
        # 흔적이 통째로 사라지고, 아무도 그 사실을 모른다.
        #
        # 로그가 유일한 단서다. 운영자가 "저 부스만 시간대 분포가 이상하다" 를
        # 발견했을 때 여기서 답을 찾을 수 있어야 한다.
        log.warning(
            "queued_at 이 신뢰 범위를 벗어나 서버 시각을 씁니다 "
            "(오차 %.0f초). 부스 단말 시계를 확인하세요.",
            skew,
        )
        return None
    return aware


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
    response: dict | None = None,
    attempt_count: int = 1,
    now: datetime | None = None,
) -> GrantOutcome:
    """미션 지급 + 조각 공개를 한 트랜잭션으로 처리한다.

    `queued_at` 이 있으면 `completed_at` 을 그 값으로 기록한다 — 오프라인 큐가
    복구된 시각에 완료가 몰려 보이면 운영 인사이트의 편중 판정이 망가진다.

    `response` 와 `attempt_count` 는 **이미 통과한** 체험의 결과다. 채점은
    services/experience.py 가 하고 여기서는 하지 않는다 — 이 함수는 스태프
    지급에서도 불리는데, 그쪽은 체험 없이 사람이 확인해 지급한다.
    """
    at = now or datetime.now(UTC)
    queued_at = _trusted_queued_at(queued_at, at)
    board = get_board(db, festival.id)

    # ── 계약 §8.1 의 검증 순서 ──
    if mission.booth_id != booth.id:
        raise ApiError(409, "MISSION_NOT_IN_BOOTH", "이 미션은 해당 부스의 미션이 아닙니다.")
    # **이미 지급된 건은 활성 검사보다 먼저 답한다.**
    #
    # 오프라인 큐는 재전송한다. 그 사이 운영자가 부스를 중지하면, 이미 지급이
    # 끝난 건이 재전송에서 `BOOTH_INACTIVE` 로 거절된다. 스태프 화면에는
    # "보내지 못했다" 로 뜨지만 실제로는 이미 지급돼 있다 — 그 상태의 진실은
    # 실패가 아니라 **성공**이다.
    #
    # 지급은 일어난 시점에 일어난 것이고, 나중에 부스를 닫았다고 없던 일이
    # 되지 않는다. 그래서 멱등 조회를 앞에 둔다.
    existing = _existing(db, festival.id, participant.id, mission.id, client_request_id)
    if existing is not None:
        return _already(db, board, existing)

    if not booth.is_active or booth.archived_at is not None:
        raise ApiError(409, "BOOTH_INACTIVE", "중지된 부스입니다.")
    if not mission.is_active or mission.archived_at is not None:
        raise ApiError(409, "MISSION_INACTIVE", "중지된 미션입니다.")

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

    # 보너스는 **누른 시각** 기준으로 찾는다.
    #
    # 도달 시각으로 찾으면 통신이 끊겼다는 이유만으로 참여자가 보너스를 잃는다 —
    # 14시 50분에 "지금 두 배" 를 보고 미션을 했는데 큐가 15시 10분에 풀리면
    # 캠페인이 이미 끝나 있다. 참여자는 화면에서 약속받은 점수를 못 받고,
    # 그 사이 아무것도 잘못한 적이 없다.
    #
    # 완료 시각도 같은 값을 쓰므로(아래 `completed_at`), 이렇게 해야 리포트의
    # 캠페인 전후 분석에서 "캠페인 중 완료인데 보너스가 0" 인 행이 사라진다.
    effective_at = queued_at or at
    campaign = pick_campaign(
        db,
        festival_id=festival.id,
        booth_id=booth.id,
        mission_id=mission.id,
        now=effective_at,
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
        response=response,
        attempt_count=attempt_count,
    )
    try:
        with db.begin_nested():
            db.add(participation)
            db.flush()
    except IntegrityError:
        # 동시 요청이 먼저 넣었다. 조건문으로는 막을 수 없는 경로다.
        _forget(db, participation)
        raced = _existing(db, festival.id, participant.id, mission.id, client_request_id)
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


def verify_print_signature(booth: Booth, signature: str, *, now: datetime | None = None) -> int:
    """인쇄 QR 의 고정 서명을 확인한다. 성공하면 **현재** window 를 돌려준다.

    서명에는 시각이 들어 있지 않습니다. 인쇄물은 바뀌지 않으니까요. 그래서
    "언제 스캔했나"는 서버 시각으로 정합니다.

    현재 window 를 돌려주는 이유는 `booth_scan_uses` 때문입니다. 1 스캔 = 1 미션
    규칙이 인쇄 부스에서도 의미를 갖게 하려면 무언가로 묶어야 하는데, 토큰이
    고정이라 토큰으로는 묶을 수 없습니다. 서버 시각의 window 로 묶으면 한 부스에서
    30초에 한 건씩만 받게 되어, 한 번 찍고 그 부스 미션을 전부 쓸어담는 것을
    막습니다 — 줄을 선 사람들 사이에서 실제로 필요한 간격입니다.
    """
    if security.match_print_signature(booth.qr_secret, booth.id, signature):
        return security.current_window(now)
    raise ApiError(
        400,
        "SCAN_TOKEN_INVALID",
        "이 부스의 QR 이 아닙니다. 부스에 붙은 QR 을 다시 찍어 주세요.",
    )


def verify_scan_token(
    booth: Booth,
    token: str,
    *,
    windows: int = security.DEFAULT_ACCEPTED_WINDOWS,
    now: datetime | None = None,
) -> int:
    """토큰이 맞는 window 를 돌려준다. 계약 §8.3 의 오류 코드로 실패한다.

    `windows` 는 인정할 window 수다. 체험이 붙은 부스는 호출자가 늘려 넘긴다 —
    퀴즈를 30초 안에 못 풀면 지급이 막히기 때문이다.
    """
    window = security.match_scan_window(booth.qr_secret, booth.id, token, now, windows=windows)
    if window is not None:
        return window

    # 만료와 위조를 구분한다 — 참여자 화면의 안내 문구가 달라야 한다.
    # 만료면 "다시 스캔", 위조면 다시 스캔해도 안 되므로 그렇게 안내하면 안 된다.
    # 인정 범위 **바로 뒤**부터 훑는다. windows 를 늘렸는데 여기를 2 로 두면
    # 인정 범위 안의 토큰을 위조로 오판한다.
    for back in range(windows, windows + 10):
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


def verify_scan_proof(
    booth: Booth,
    *,
    token: str | None,
    signature: str | None,
    windows: int = security.DEFAULT_ACCEPTED_WINDOWS,
    now: datetime | None = None,
) -> int:
    """부스 모드에 맞는 증명을 확인한다 — 기획서 E4.

    **부스가 정한 모드만 받습니다.** 인쇄 부스가 회전 토큰도 받아 주면, 모드를
    `printed` 로 내려 둔 부스에서 예전 태블릿 QR 이 계속 통하게 됩니다.
    반대로 회전 부스가 고정 서명을 받으면 회전의 의미가 없어집니다.
    """
    if booth.qr_mode == BoothQrMode.PRINTED:
        if not signature:
            raise ApiError(
                400,
                "SCAN_SIGNATURE_REQUIRED",
                "이 부스는 인쇄된 QR 을 씁니다. 부스에 붙은 QR 을 찍어 주세요.",
                {"qr_mode": booth.qr_mode.value},
            )
        return verify_print_signature(booth, signature, now=now)

    if not token:
        raise ApiError(
            400,
            "SCAN_TOKEN_REQUIRED",
            "이 부스는 화면에 뜨는 QR 을 씁니다. 부스 화면의 QR 을 찍어 주세요.",
            {"qr_mode": booth.qr_mode.value},
        )
    return verify_scan_token(booth, token, windows=windows, now=now)
