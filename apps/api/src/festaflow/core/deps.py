"""요청 의존성.

⚠ 현재 기관 스코프는 `X-Organization-Id` 헤더로 결정됩니다.
   이건 **인증이 아닙니다.** 실제 로그인은 BE-1(스태프 2단계 인증)에서 붙입니다.
   지금은 프런트가 붙을 계약을 먼저 확정하기 위한 자리입니다.

   배포 전에 반드시 JWT 검증으로 교체해야 합니다. 그대로 두면
   헤더만 바꿔서 남의 기관 데이터를 볼 수 있습니다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core.errors import ApiError
from festaflow.db.session import get_db
from festaflow.models import Organization

DbSession = Annotated[Session, Depends(get_db)]


def get_current_org(
    db: DbSession,
    x_organization_id: Annotated[int | None, Header(alias="X-Organization-Id")] = None,
) -> Organization:
    if x_organization_id is not None:
        org = db.get(Organization, x_organization_id)
        if org is None or not org.is_active:
            raise ApiError(404, "NOT_FOUND", "기관을 찾을 수 없습니다.")
        return org

    # 헤더가 없으면 단일 기관 환경으로 본다(로컬 개발·데모).
    org = db.execute(
        select(Organization).where(Organization.is_active.is_(True)).order_by(Organization.id)
    ).scalars().first()
    if org is None:
        raise ApiError(
            409,
            "NO_ORGANIZATION",
            "기관이 없습니다. 먼저 기관을 만들어 주세요.",
        )
    return org


CurrentOrg = Annotated[Organization, Depends(get_current_org)]
