"""통합 검색 응답.

**참여자 secret 은 이 스키마에 자리가 없습니다.** 코드는 부스에서 스태프에게
보여주는 값이라 나가지만, secret 은 본인 인증용이라 여기 실리면 남의 수집
현황을 여는 열쇠가 됩니다. 스키마가 그 경계입니다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SearchHit(BaseModel):
    #: 화면이 이 값으로 어디로 보낼지 정한다. 서버가 주소를 만들지 않는다 —
    #: 만들면 프런트 라우팅이 바뀔 때마다 백엔드를 고쳐야 한다.
    kind: Literal["booth", "mission", "exhibit", "participant"]
    id: int
    title: str
    #: 어느 부스의 미션인지, 어느 팀의 작품인지. 없으면 None.
    subtitle: str | None = None


class SearchOut(BaseModel):
    query: str
    #: 몇 글자부터 찾는지. 화면이 같은 숫자를 따로 들고 있지 않게 한다.
    min_query: int
    #: 종류마다 상한이 있다. 잘렸으면 그 사실을 화면이 말해야 한다 —
    #: 조용히 자르면 "없다" 와 구분되지 않는다.
    truncated: bool
    hits: list[SearchHit]
