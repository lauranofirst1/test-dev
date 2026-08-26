"""축제 통합 검색 — 운영자가 무언가를 찾는 유일한 자리.

축제 하나에 부스 스무 개, 미션 서른 개, 작품 서른 점, 참여자 천 명이 붙습니다.
"B7 이 어느 화면에 있었지" 를 메뉴로 되짚는 대신 이름을 치면 나와야 합니다.

## 무엇을 찾는가

부스 · 미션 · 작품 · 참여자(참여 코드와 학번). 넷 다 운영자가 현장에서 실제로
불려 다니는 이름입니다 — "B7 부스요", "3번 작품 포스터가 없대요",
"FF-00042917 인데 조각이 안 들어왔대요", "20231234 학생 공결 처리요".

## 학번을 넣은 이유와 그 경계

`Participant.student_no` 는 평문이고, 노출 경계는 **운영자 응답뿐** 입니다.
이 검색도 그 경계 안에 있습니다(라우터가 기관 세션을 요구합니다).

다만 학번은 **정확히 일치할 때만** 찾습니다. 앞자리 몇 개로 훑게 두면
`2023` 한 번에 그 해 입학생 전체가 목록으로 쏟아지고, 그건 검색이 아니라
명단입니다. 운영자가 아는 한 명을 확인하는 것과 모르는 여럿을 훑는 것은
다른 일입니다.

**참여자 secret 은 어떤 경우에도 나가지 않습니다.** 코드는 부스에서 스태프에게
보여주는 값이라 검색 결과에 실리지만, secret 은 본인 인증용이라 여기 실리면
남의 수집 현황을 열 수 있는 열쇠가 됩니다.

## 길이 하한

두 글자 미만은 찾지 않습니다. 한 글자로 훑으면 거의 모든 행이 걸려 검색이
목록이 되고, 타이핑 한 번마다 네 테이블을 훑습니다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from festaflow.models import Booth, Exhibit, Mission, Participant

#: 한 글자로는 찾지 않는다.
MIN_QUERY = 2
#: 종류마다 몇 개까지. 넘으면 잘린 사실을 화면에 알린다 — 조용히 자르면
#: 없는 것과 구분되지 않는다.
PER_KIND = 6


@dataclass
class Hit:
    kind: str
    id: int
    title: str
    subtitle: str | None = None


def _like(q: str) -> str:
    # `%` 와 `_` 는 LIKE 의 와일드카드다. 부스 이름에 들어 있으면 그대로
    # 패턴이 되어 엉뚱한 것이 걸린다.
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search(db: Session, festival_id: int, query: str) -> tuple[list[Hit], bool]:
    """축제 안에서 찾는다. 두 번째 값은 **잘렸는가** 다."""
    q = query.strip()
    if len(q) < MIN_QUERY:
        return [], False

    pattern = _like(q)
    # 출품번호는 정수 열이다. 숫자로 읽히면 그 번호도 함께 찾는다 —
    # 현장에서 작품은 "3번" 으로 불린다.
    entry_no = int(q) if q.isdigit() and len(q) <= 6 else None
    hits: list[Hit] = []
    truncated = False

    def take(rows: list, kind_hits: list[Hit]) -> None:
        nonlocal truncated
        if len(rows) > PER_KIND:
            truncated = True
        hits.extend(kind_hits[:PER_KIND])

    # ── 부스 ──
    booths = list(
        db.execute(
            select(Booth)
            .where(Booth.festival_id == festival_id, Booth.name.ilike(pattern, escape="\\"))
            .order_by(Booth.name)
            .limit(PER_KIND + 1)
        ).scalars()
    )
    take(
        booths,
        [
            Hit(
                kind="booth",
                id=b.id,
                title=b.name,
                subtitle=" · ".join(
                    x for x in [b.location, None if b.is_active else "중지됨"] if x
                )
                or None,
            )
            for b in booths
        ],
    )

    # ── 미션 ── 어느 부스의 미션인지가 함께 나와야 찾은 뜻이 있다.
    missions = list(
        db.execute(
            select(Mission, Booth.name)
            .outerjoin(Booth, Mission.booth_id == Booth.id)
            .where(
                Mission.festival_id == festival_id,
                Mission.title.ilike(pattern, escape="\\"),
            )
            .order_by(Mission.title)
            .limit(PER_KIND + 1)
        ).all()
    )
    take(
        missions,
        [
            Hit(
                kind="mission",
                id=m.id,
                title=m.title,
                subtitle=booth_name or "축제 공통",
            )
            for m, booth_name in missions
        ],
    )

    # ── 작품 ── 출품번호로도 찾는다. 현장에서는 번호로 불린다.
    exhibits = list(
        db.execute(
            select(Exhibit)
            .where(
                Exhibit.festival_id == festival_id,
                or_(
                    Exhibit.title.ilike(pattern, escape="\\"),
                    Exhibit.team_name.ilike(pattern, escape="\\"),
                    Exhibit.entry_no == entry_no if entry_no is not None else False,
                ),
            )
            .order_by(Exhibit.entry_no)
            .limit(PER_KIND + 1)
        ).scalars()
    )
    take(
        exhibits,
        [
            Hit(
                kind="exhibit",
                id=e.id,
                title=f"{e.entry_no} {e.title}",
                subtitle=e.team_name,
            )
            for e in exhibits
        ],
    )

    # ── 참여자 ──
    # 코드는 부분 일치, **학번은 정확히 일치할 때만**. 앞자리로 훑게 두면
    # `2023` 한 번에 그 해 입학생 전체가 쏟아지고, 그건 검색이 아니라 명단이다.
    upper = q.upper()
    participants = list(
        db.execute(
            select(Participant)
            .where(
                Participant.festival_id == festival_id,
                or_(
                    Participant.code.ilike(_like(upper), escape="\\"),
                    Participant.student_no == q,
                ),
            )
            .order_by(Participant.code)
            .limit(PER_KIND + 1)
        ).scalars()
    )
    take(
        participants,
        [
            Hit(
                kind="participant",
                id=p.id,
                title=p.code,
                # 학번은 운영자 응답에서만 나온다. 이 검색이 그 경계 안이다.
                subtitle=p.student_no,
            )
            for p in participants
        ],
    )

    return hits, truncated
