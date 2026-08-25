"""축제 통합 검색.

**기관 세션만 엽니다.** 학번과 참여 코드가 결과에 실리므로, 스태프 토큰에도
열면 부스 담당자 한 명이 축제 전체 참여자를 훑을 수 있게 됩니다. 부스 담당자가
필요한 것은 자기 앞에 선 사람의 코드 하나이고, 그건 지급 화면이 이미 합니다.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core.deps import CurrentAccount, DbSession
from festaflow.core.errors import not_found
from festaflow.models import Festival
from festaflow.schemas.search import SearchHit, SearchOut
from festaflow.services import search as svc

router = APIRouter(prefix="/api/festivals/{festival_id}", tags=["search"])


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


@router.get("/search", response_model=SearchOut)
def search_festival(
    festival_id: int,
    db: DbSession,
    account: CurrentAccount,
    q: str = Query(default="", max_length=120),
) -> SearchOut:
    """부스 · 미션 · 작품 · 참여자를 한 번에 찾는다.

    두 글자 미만이면 **빈 결과**를 줍니다. 오류가 아닙니다 — 타이핑 중인
    상태를 오류로 알리면 글자를 칠 때마다 빨간 글씨가 깜빡입니다.
    """
    _owned(db, account.organization_id, festival_id)
    hits, truncated = svc.search(db, festival_id, q)
    return SearchOut(
        query=q.strip(),
        min_query=svc.MIN_QUERY,
        truncated=truncated,
        hits=[
            SearchHit(kind=h.kind, id=h.id, title=h.title, subtitle=h.subtitle)
            for h in hits
        ],
    )
