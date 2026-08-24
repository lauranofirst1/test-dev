"""전시 작품 · 심사 · 관객 투표.

세 종류의 접근이 한 파일에 있지만 **인증 경계가 전부 다릅니다.**

- 운영자 — 작품·항목 등록, 설정, 집계 (기관 스코프)
- 심사위원 — 점수 입력 (토큰 필수. 누가 매겼는지가 기록의 일부다)
- 관객 — 작품 보기, 투표 (`X-Participant-Secret`)

집계 결과는 **운영자에게만** 나갑니다. 투표 중에 순위가 보이면 표가 순위를
따라가고, 그건 더 이상 관객 투표가 아닙니다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, File, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from festaflow.core.deps import (
    CanOperate,
    CurrentJudge,
    CurrentOrg,
    CurrentParticipant,
    DbSession,
    FestivalAccess,
)
from festaflow.core.errors import ApiError, not_found
from festaflow.models import (
    AudienceVote,
    Exhibit,
    Festival,
    JudgeScore,
    VoteCriterion,
)
from festaflow.schemas.exhibit import (
    CriterionIn,
    CriterionOut,
    CriterionResultOut,
    ExhibitIn,
    ExhibitList,
    ExhibitOut,
    ExhibitResultOut,
    ExhibitionSettingsIn,
    JudgeProgressOut,
    JudgeSheetOut,
    MyScoreOut,
    PublicExhibit,
    ResultsOut,
    ScoreSheetIn,
    VoteResult,
    VotingStatus,
)
from festaflow.services import exhibits as svc
from festaflow.services import media

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["exhibits"])

OPERATOR = [FestivalAccess]


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
    f = db.execute(
        select(Festival).where(Festival.id == festival_id, Festival.archived_at.is_(None))
    ).scalar_one_or_none()
    if f is None:
        raise not_found("축제")
    return f


def _all_tags(exhibits: list[Exhibit]) -> list[str]:
    seen: list[str] = []
    for e in exhibits:
        for t in e.tags or []:
            if t not in seen:
                seen.append(t)
    return seen


# ── 운영자: 작품 ────────────────────────────────────────────────────────────


@router.get("/exhibits", response_model=ExhibitList, dependencies=OPERATOR)
def list_exhibits(festival_id: int, db: DbSession, org: CurrentOrg) -> ExhibitList:
    _owned(db, org.id, festival_id)
    items = list(
        db.execute(
            select(Exhibit)
            .where(Exhibit.festival_id == festival_id, Exhibit.archived_at.is_(None))
            .order_by(Exhibit.entry_no)
        ).scalars()
    )
    return ExhibitList(
        items=[ExhibitOut.model_validate(e) for e in items],
        total=len(items),
        tags=_all_tags(items),
    )


@router.post(
    "/exhibits",
    response_model=ExhibitOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*OPERATOR, CanOperate],
)
def create_exhibit(
    festival_id: int, payload: ExhibitIn, db: DbSession, org: CurrentOrg
) -> ExhibitOut:
    festival = _owned(db, org.id, festival_id)
    exhibit = Exhibit(
        festival_id=festival.id,
        entry_no=svc.next_entry_no(db, festival.id),
        **payload.model_dump(),
    )
    db.add(exhibit)
    db.commit()
    db.refresh(exhibit)
    return ExhibitOut.model_validate(exhibit)


@router.put(
    "/exhibits/{exhibit_id}", response_model=ExhibitOut, dependencies=[*OPERATOR, CanOperate]
)
def update_exhibit(
    festival_id: int, exhibit_id: int, payload: ExhibitIn, db: DbSession, org: CurrentOrg
) -> ExhibitOut:
    _owned(db, org.id, festival_id)
    exhibit = svc.get_exhibit(db, festival_id, exhibit_id)
    for k, v in payload.model_dump().items():
        setattr(exhibit, k, v)
    db.commit()
    db.refresh(exhibit)
    return ExhibitOut.model_validate(exhibit)


@router.post(
    "/exhibits/{exhibit_id}/poster",
    response_model=ExhibitOut,
    dependencies=[*OPERATOR, CanOperate],
)
def upload_poster(
    festival_id: int,
    exhibit_id: int,
    db: DbSession,
    org: CurrentOrg,
    file: UploadFile = File(...),
) -> ExhibitOut:
    """포스터 업로드. 조각 보드 그림과 같은 검사를 거친다 —
    매직 바이트로 형식을 판별하고, 확장자와 이름은 서버가 붙인다."""
    _owned(db, org.id, festival_id)
    exhibit = svc.get_exhibit(db, festival_id, exhibit_id)
    exhibit.poster_url = media.save_poster(file.file, festival_id)
    db.commit()
    db.refresh(exhibit)
    return ExhibitOut.model_validate(exhibit)


@router.post(
    "/exhibits/{exhibit_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[*OPERATOR, CanOperate],
)
def archive_exhibit(
    festival_id: int, exhibit_id: int, db: DbSession, org: CurrentOrg
) -> None:
    """삭제가 아니라 아카이브. 이미 받은 표와 점수를 지우면 집계가 흔들린다."""
    _owned(db, org.id, festival_id)
    exhibit = svc.get_exhibit(db, festival_id, exhibit_id)
    exhibit.archived_at = datetime.now(UTC)
    exhibit.is_active = False
    db.commit()


# ── 운영자: 심사 항목 ───────────────────────────────────────────────────────


@router.get("/criteria", response_model=list[CriterionOut], dependencies=OPERATOR)
def list_criteria(festival_id: int, db: DbSession, org: CurrentOrg) -> list[CriterionOut]:
    _owned(db, org.id, festival_id)
    return [CriterionOut.model_validate(c) for c in svc.active_criteria(db, festival_id)]


@router.post(
    "/criteria",
    response_model=CriterionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[*OPERATOR, CanOperate],
)
def create_criterion(
    festival_id: int, payload: CriterionIn, db: DbSession, org: CurrentOrg
) -> CriterionOut:
    festival = _owned(db, org.id, festival_id)
    c = VoteCriterion(festival_id=festival.id, **payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return CriterionOut.model_validate(c)


@router.post(
    "/criteria/{criterion_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[*OPERATOR, CanOperate],
)
def archive_criterion(
    festival_id: int, criterion_id: int, db: DbSession, org: CurrentOrg
) -> None:
    _owned(db, org.id, festival_id)
    c = db.get(VoteCriterion, criterion_id)
    if c is None or c.festival_id != festival_id:
        raise not_found("심사 항목")
    c.archived_at = datetime.now(UTC)
    c.is_active = False
    db.commit()


# ── 운영자: 설정과 집계 ─────────────────────────────────────────────────────


@router.put("/exhibition-settings", response_model=ResultsOut, dependencies=[*OPERATOR, CanOperate])
def update_settings(
    festival_id: int, payload: ExhibitionSettingsIn, db: DbSession, org: CurrentOrg
) -> ResultsOut:
    festival = _owned(db, org.id, festival_id)
    for k, v in payload.model_dump().items():
        setattr(festival, k, v)
    db.commit()
    db.refresh(festival)
    return _results(db, festival)


def _results(db: Session, festival: Festival) -> ResultsOut:
    rows = svc.results(db, festival)
    criteria = svc.active_criteria(db, festival.id)
    return ResultsOut(
        judge_weight_percent=festival.judge_weight_percent,
        audience_weight_percent=100 - festival.judge_weight_percent,
        votes_limit=festival.audience_votes_per_participant,
        voting_open=festival.voting_open,
        items=[
            ExhibitResultOut(
                exhibit=ExhibitOut.model_validate(r.exhibit),
                criteria=[
                    CriterionResultOut(
                        criterion_id=c.criterion_id,
                        label=c.label,
                        max_score=c.max_score,
                        weight=c.weight,
                        average=round(c.average, 2) if c.average is not None else None,
                        judge_count=c.judge_count,
                    )
                    for c in r.criteria
                ],
                judge_count=r.judge_count,
                votes=r.votes,
                judge_score=round(r.judge_score, 1) if r.judge_score is not None else None,
                audience_score=(
                    round(r.audience_score, 1) if r.audience_score is not None else None
                ),
                final_score=round(r.final_score, 1) if r.final_score is not None else None,
            )
            for r in rows
        ],
        warnings=svc.integrity_warnings(rows, len(criteria)),
    )


@router.get("/exhibition-results", response_model=ResultsOut, dependencies=OPERATOR)
def results(festival_id: int, db: DbSession, org: CurrentOrg) -> ResultsOut:
    """시상 근거. 최종 점수와 함께 그 점수가 나온 과정을 전부 내린다."""
    festival = _owned(db, org.id, festival_id)
    return _results(db, festival)


# ── 심사위원 ────────────────────────────────────────────────────────────────


@router.get("/judging", response_model=JudgeProgressOut, dependencies=OPERATOR)
def judging_sheets(
    festival_id: int, db: DbSession, org: CurrentOrg, judge: CurrentJudge
) -> JudgeProgressOut:
    """내가 매길 작품들과 **내가 준 점수만**. 남의 점수는 담지 않는다."""
    _owned(db, org.id, festival_id)
    exhibits = svc.active_exhibits(db, festival_id)
    criteria = svc.active_criteria(db, festival_id)

    mine = db.execute(
        select(JudgeScore).where(
            JudgeScore.staff_id == judge.id,
            JudgeScore.exhibit_id.in_([e.id for e in exhibits] or [0]),
        )
    ).scalars()
    by_exhibit: dict[int, list[JudgeScore]] = {}
    for row in mine:
        by_exhibit.setdefault(row.exhibit_id, []).append(row)

    sheets = []
    for e in exhibits:
        rows = by_exhibit.get(e.id, [])
        sheets.append(
            JudgeSheetOut(
                exhibit=ExhibitOut.model_validate(e),
                criteria=[CriterionOut.model_validate(c) for c in criteria],
                my_scores=[
                    MyScoreOut(criterion_id=r.criterion_id, score=r.score, comment=r.comment)
                    for r in rows
                ],
                is_complete=bool(criteria) and len(rows) == len(criteria),
            )
        )

    return JudgeProgressOut(
        total_exhibits=len(exhibits),
        scored_exhibits=sum(1 for s in sheets if s.is_complete),
        sheets=sheets,
    )


@router.put(
    "/exhibits/{exhibit_id}/scores", response_model=JudgeSheetOut, dependencies=OPERATOR
)
def submit_scores(
    festival_id: int,
    exhibit_id: int,
    payload: ScoreSheetIn,
    db: DbSession,
    org: CurrentOrg,
    judge: CurrentJudge,
) -> JudgeSheetOut:
    """심사표를 낸다. 다시 내면 **덮어쓴다** — 고치는 것은 새 점수가 아니다."""
    _owned(db, org.id, festival_id)
    exhibit = svc.get_exhibit(db, festival_id, exhibit_id)
    criteria = {c.id: c for c in svc.active_criteria(db, festival_id)}

    for item in payload.scores:
        c = criteria.get(item.criterion_id)
        if c is None:
            raise not_found("심사 항목")
        if item.score > c.max_score:
            raise ApiError(
                422,
                "SCORE_OUT_OF_RANGE",
                f"'{c.label}' 은 {c.max_score}점 만점입니다.",
                {"criterion_id": c.id, "max_score": c.max_score},
            )

        existing = db.execute(
            select(JudgeScore).where(
                JudgeScore.exhibit_id == exhibit.id,
                JudgeScore.criterion_id == c.id,
                JudgeScore.staff_id == judge.id,
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                JudgeScore(
                    exhibit_id=exhibit.id,
                    criterion_id=c.id,
                    staff_id=judge.id,
                    score=item.score,
                    comment=item.comment,
                )
            )
        else:
            existing.score = item.score
            existing.comment = item.comment

    db.commit()

    rows = list(
        db.execute(
            select(JudgeScore).where(
                JudgeScore.exhibit_id == exhibit.id, JudgeScore.staff_id == judge.id
            )
        ).scalars()
    )
    return JudgeSheetOut(
        exhibit=ExhibitOut.model_validate(exhibit),
        criteria=[CriterionOut.model_validate(c) for c in criteria.values()],
        my_scores=[
            MyScoreOut(criterion_id=r.criterion_id, score=r.score, comment=r.comment)
            for r in rows
        ],
        is_complete=bool(criteria) and len(rows) == len(criteria),
    )


# ── 관객 ────────────────────────────────────────────────────────────────────


@router.get("/exhibition", response_model=VotingStatus)
def voting_status(
    festival_id: int, db: DbSession, participant: CurrentParticipant
) -> VotingStatus:
    """관객이 보는 전시. **다른 사람의 표는 담지 않는다.**

    투표 중에 순위가 보이면 표가 순위를 따라가고, 그건 더 이상 관객 투표가
    아닙니다. 집계는 운영자 화면에만 있습니다.
    """
    festival = _live(db, festival_id)
    exhibits = svc.active_exhibits(db, festival.id)
    mine = svc.voted_exhibit_ids(db, festival.id, participant.id)

    reason: str | None = None
    can_vote = True
    if not festival.voting_open:
        can_vote, reason = False, "지금은 투표 기간이 아닙니다."
    elif festival.identity_mode.value != "student_id":
        can_vote, reason = (
            False,
            "이 축제는 익명 참여라 1인 1표를 보장할 수 없습니다.",
        )

    return VotingStatus(
        voting_open=festival.voting_open,
        can_vote=can_vote,
        reason=reason,
        votes_used=len(mine),
        votes_limit=festival.audience_votes_per_participant,
        exhibits=[
            PublicExhibit(
                id=e.id,
                entry_no=e.entry_no,
                title=e.title,
                team_name=e.team_name,
                summary=e.summary,
                poster_url=e.poster_url,
                tags=list(e.tags or []),
                location=e.location,
                voted=e.id in mine,
            )
            for e in exhibits
        ],
        tags=_all_tags(exhibits),
    )


@router.post("/exhibits/{exhibit_id}/vote", response_model=VoteResult)
def vote(
    festival_id: int, exhibit_id: int, db: DbSession, participant: CurrentParticipant
) -> VoteResult:
    festival = _live(db, festival_id)
    svc.assert_voting_open(festival)
    exhibit = svc.get_exhibit(db, festival_id, exhibit_id)
    svc.assert_can_vote(db, festival, participant)

    row = AudienceVote(
        festival_id=festival.id, exhibit_id=exhibit.id, participant_id=participant.id
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # 같은 작품에 두 번 눌렀다. 오류가 아니라 이미 준 상태를 그대로 돌려준다.
        if row in db:
            db.expunge(row)
        db.commit()
        return VoteResult(
            exhibit_id=exhibit.id,
            voted=True,
            votes_used=svc.votes_used(db, festival.id, participant.id),
            votes_limit=festival.audience_votes_per_participant,
        )

    db.commit()
    return VoteResult(
        exhibit_id=exhibit.id,
        voted=True,
        votes_used=svc.votes_used(db, festival.id, participant.id),
        votes_limit=festival.audience_votes_per_participant,
    )


@router.delete("/exhibits/{exhibit_id}/vote", response_model=VoteResult)
def unvote(
    festival_id: int, exhibit_id: int, db: DbSession, participant: CurrentParticipant
) -> VoteResult:
    """표를 거둔다. 표가 한정돼 있으니 옮길 수 있어야 한다."""
    festival = _live(db, festival_id)
    svc.assert_voting_open(festival)
    exhibit = svc.get_exhibit(db, festival_id, exhibit_id)

    db.execute(
        delete(AudienceVote).where(
            AudienceVote.exhibit_id == exhibit.id,
            AudienceVote.participant_id == participant.id,
        )
    )
    db.commit()
    return VoteResult(
        exhibit_id=exhibit.id,
        voted=False,
        votes_used=svc.votes_used(db, festival.id, participant.id),
        votes_limit=festival.audience_votes_per_participant,
    )
