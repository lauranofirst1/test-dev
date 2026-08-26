"""요청 의존성 — 인증과 기관 스코프.

`Authorization: Bearer <token>` 이 있으면 그것이 진실입니다. 토큰이 스태프를,
스태프가 축제를, 축제가 기관을 정합니다. 클라이언트가 기관을 고를 수 없습니다.

⚠ 아직 남은 구멍 — **기획자(planner) 자격증명이 스펙에 없습니다.**
   계약(§1)의 로그인은 축제별 스태프용이라 `festival_id` 가 필요한데,
   축제 목록·생성은 축제가 생기기 전에 호출됩니다. 기관 단위 계정 모델이
   정해지지 않아, 이 두 엔드포인트만 `X-Organization-Id` 헤더 폴백을 씁니다.

   폴백은 `APP_ENV=local` 또는 `DEMO_MODE=true` 에서만 삽니다. 그 밖의 환경에서는
   401 로 닫힙니다 — 헤더 폴백이 배포에 실려 나가면 헤더만 바꿔서 남의 기관
   데이터를 볼 수 있기 때문입니다. 기관 계정이 정해지면 폴백을 지우면 됩니다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from festaflow.core import security
from festaflow.core.config import settings
from festaflow.core.errors import ApiError
from festaflow.db.session import get_db
from festaflow.models import (
    Festival,
    FestivalStaff,
    Organization,
    OrganizationAccount,
    Participant,
)
from festaflow.models.enums import StaffRole

DbSession = Annotated[Session, Depends(get_db)]


def _looks_like_staff(token: str) -> bool:
    """서명을 검증하지 않고 종류만 엿본다.

    쿠키 하나에 두 종류의 세션이 들어올 수 있어서, 스태프 자리에서 기관 세션을
    만나면 401 이 아니라 "스태프 아님(None)" 으로 넘겨야 합니다. 그러려면 검증
    **전에** 종류를 알아야 하는데, 여기서 하는 판단은 분기용일 뿐이고 실제
    신뢰는 아래 `decode_staff_token` 의 서명 검증이 담당합니다.
    """
    try:
        import base64
        import json

        body = token.split(".")[1]
        body += "=" * (-len(body) % 4)
        return json.loads(base64.urlsafe_b64decode(body)).get("typ", "staff") == "staff"
    except Exception:  # noqa: BLE001 — 못 읽으면 스태프로 보고 아래에서 제대로 실패시킨다
        return True

#: 기관 스코프를 클라이언트가 고를 수 있는 환경. 로컬 개발과 데모뿐이다.
def _fallback_allowed() -> bool:
    return settings.app_env == "local" or settings.demo_mode


def _auth_required() -> ApiError:
    return ApiError(401, "AUTH_REQUIRED", "로그인이 필요합니다.")


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(
            401, "INVALID_TOKEN", "Authorization 헤더는 `Bearer <토큰>` 형식이어야 합니다."
        )
    return token.strip()


def get_optional_staff(
    db: DbSession,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> FestivalStaff | None:
    """토큰이 있으면 스태프를, 없으면 None. 토큰이 있는데 틀리면 401.

    **쿠키를 먼저 봅니다.** 브라우저는 세션을 httpOnly 쿠키로 받으므로 화면이
    토큰을 손에 쥘 일이 없고, XSS 가 나도 스크립트가 읽어갈 수 없습니다.
    `Authorization` 헤더는 브라우저가 아닌 클라이언트(테스트·스크립트)용으로
    남겨 둡니다.

    스태프 쿠키는 기관 계정 쿠키와 **이름이 다릅니다**(`staff_cookie_name`).
    한 브라우저에서 콘솔과 현장 화면을 함께 여는 것이 정상 동선이라, 둘이
    같은 자리를 쓰면 나중에 로그인한 쪽이 앞의 세션을 지웁니다.
    """
    token = request.cookies.get(settings.staff_cookie_name) or _bearer(authorization)
    if not token:
        return None

    # 한 자리에 두 종류의 세션이 들어올 수 있다(쿠키든 Bearer 든). 기관 세션을
    # 만나면 401 이 아니라 "스태프 아님(None)" 으로 넘겨야 한다 — 기관 계정으로
    # 로그인한 사람이 스태프 전용이 아닌 경로를 쓸 때 401 이 나면 안 된다.
    if not _looks_like_staff(token):
        return None

    claims = security.decode_staff_token(token)
    staff = db.execute(
        select(FestivalStaff).where(FestivalStaff.id == claims.staff_id)
    ).scalar_one_or_none()

    # 토큰은 발급 시점의 사실을 담는다. 그 뒤 비활성화되거나 축제가 옮겨졌으면
    # 서명이 맞아도 받지 않는다 — 해지가 즉시 듣지 않으면 해지가 아니다.
    if staff is None or not staff.is_active or staff.festival_id != claims.festival_id:
        raise ApiError(401, "INVALID_TOKEN", "세션이 더 이상 유효하지 않습니다. 다시 로그인하세요.")
    return staff


OptionalStaff = Annotated[FestivalStaff | None, Depends(get_optional_staff)]


def require_staff(staff: OptionalStaff) -> FestivalStaff:
    """스태프 세션을 반드시 요구하는 엔드포인트용."""
    if staff is None:
        raise _auth_required()
    return staff


CurrentStaff = Annotated[FestivalStaff, Depends(require_staff)]


def get_optional_account(
    db: DbSession,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> OrganizationAccount | None:
    """기관 계정 세션. 없으면 None, 있는데 틀리면 401.

    **이 함수가 `X-Organization-Id` 폴백을 닫습니다.** 폴백은 헤더 하나만 바꾸면
    남의 기관 데이터가 열리는 구멍이라, 로컬·데모에서만 살려 두고 있었습니다.
    """
    token = request.cookies.get(settings.session_cookie_name) or _bearer(authorization)
    if not token:
        return None
    # 스태프 세션이 들어왔다. 기관 계정은 아니므로 조용히 넘긴다 —
    # 스태프 토큰으로도 열리는 경로가 아래 `get_current_org` 에 있다.
    if _looks_like_staff(token):
        return None

    claims = security.decode_org_token(token)
    account = db.execute(
        select(OrganizationAccount).where(OrganizationAccount.id == claims.account_id)
    ).scalar_one_or_none()

    if account is None or not account.is_active:
        raise ApiError(401, "INVALID_TOKEN", "세션이 더 이상 유효하지 않습니다. 다시 로그인하세요.")
    if account.organization_id != claims.organization_id:
        # 계정이 다른 기관으로 옮겨졌다. 서명이 맞아도 받지 않는다.
        raise ApiError(401, "INVALID_TOKEN", "세션이 더 이상 유효하지 않습니다. 다시 로그인하세요.")

    # 비밀번호를 바꾼 시점보다 먼저 발급된 세션은 받지 않는다. 바꾼 이유가
    # 유출이면, 옛 세션이 살아 있는 한 바꾼 의미가 없다.
    #
    # **초 단위로 자른 뒤 비교한다.** JWT 의 `iat` 는 정수 초라 소수점이 버려지는데,
    # `password_changed_at` 은 마이크로초까지 남는다. 그대로 비교하면 가입 직후
    # 발급한 세션이 같은 초 안에서 "비밀번호 변경보다 먼저" 로 판정돼 즉시 취소된다.
    if int(claims.issued_at.timestamp()) < int(account.password_changed_at.timestamp()):
        raise ApiError(
            401, "SESSION_REVOKED", "비밀번호가 변경되어 이 세션은 만료됐습니다. 다시 로그인하세요."
        )
    return account


OptionalAccount = Annotated[OrganizationAccount | None, Depends(get_optional_account)]


def require_account(account: OptionalAccount) -> OrganizationAccount:
    if account is None:
        raise _auth_required()
    return account


CurrentAccount = Annotated[OrganizationAccount, Depends(require_account)]


def get_current_org(
    db: DbSession,
    staff: OptionalStaff,
    account: OptionalAccount,
    x_organization_id: Annotated[int | None, Header(alias="X-Organization-Id")] = None,
) -> Organization:
    """요청의 기관 스코프.

    순서가 곧 신뢰 순서다 — 기관 계정 → 스태프 토큰 → (로컬 한정) 헤더 폴백.
    """
    if account is not None:
        org = db.get(Organization, account.organization_id)
        if org is None or not org.is_active:
            raise ApiError(
                401, "INVALID_TOKEN", "세션이 더 이상 유효하지 않습니다. 다시 로그인하세요."
            )
        return org

    if staff is not None:
        org = db.execute(
            select(Organization)
            .join(Festival, Festival.organization_id == Organization.id)
            .where(Festival.id == staff.festival_id)
        ).scalar_one_or_none()
        if org is None or not org.is_active:
            raise ApiError(
                401, "INVALID_TOKEN", "세션이 더 이상 유효하지 않습니다. 다시 로그인하세요."
            )
        return org

    if not _fallback_allowed():
        raise _auth_required()

    if x_organization_id is not None:
        org = db.get(Organization, x_organization_id)
        if org is None or not org.is_active:
            raise ApiError(404, "NOT_FOUND", "기관을 찾을 수 없습니다.")
        return org

    # 헤더도 없으면 단일 기관 환경으로 본다(로컬 개발·데모).
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


def require_festival_access(
    festival_id: int, staff: OptionalStaff, account: OptionalAccount
) -> None:
    """스태프 토큰은 **자기 축제만** 만질 수 있다.

    기관 스코프만으로는 막히지 않는다 — 같은 기관에 축제가 여럿이면
    A 축제 운영자 토큰으로 B 축제를 읽을 수 있다.

    **기관 계정 세션이 있으면 스태프 쿠키는 보지 않는다.** 한 브라우저에 둘 다
    있는 것이 정상이라(콘솔 + 현장 화면), 그때 A 축제 스태프 쿠키가 남아 있다고
    B 축제 콘솔이 막히면 안 된다. 계정 쪽 권한은 `get_current_org` 의 기관
    스코프와 각 엔드포인트의 소유 검사가 이미 판정한다.
    """
    if account is not None:
        return
    if staff is not None and staff.festival_id != festival_id:
        raise ApiError(403, "FORBIDDEN", "이 축제에 대한 권한이 없습니다.")


#: 오류 문장에 쓰는 역할 이름. 화면은 서버 문장을 그대로 띄우므로 여기서
#: 영어 값이 나가면 "이 작업은 operator, planner 역할만 할 수 있습니다" 가
#: 그대로 보인다 — 읽는 사람은 자기가 그중 무엇인지 알 수 없다.
#: `details.required_roles` 는 값 그대로 둔다. 그쪽은 기계가 읽는 자리다.
ROLE_LABELS: dict[str, str] = {
    StaffRole.PLANNER.value: "기획자",
    StaffRole.OPERATOR.value: "운영자",
    StaffRole.BOOTH_MANAGER.value: "부스 관리자",
    StaffRole.JUDGE.value: "심사위원",
}


def require_role(*roles: StaffRole):
    """역할 제한. 토큰이 없는 폴백 환경에서는 검사할 역할이 없어 통과시킨다."""
    allowed = {r.value for r in roles}
    # 사람이 읽는 순서는 ROLE_LABELS 의 차례를 따른다(기획자 → 심사위원).
    labels = [label for value, label in ROLE_LABELS.items() if value in allowed]

    def _check(staff: OptionalStaff, account: OptionalAccount) -> None:
        # 기관 계정으로 들어온 요청은 스태프 역할로 막지 않는다 — 계정은 이
        # 기관의 주인이고, 만질 수 있는 축제는 기관 스코프가 이미 가른다.
        # (쿠키가 하나이던 때는 계정 세션이면 staff 가 늘 None 이라 결과가
        #  같았다. 쿠키를 가른 지금은 명시해야 한다.)
        if account is not None:
            return
        if staff is not None and staff.role.value not in allowed:
            raise ApiError(
                403,
                "FORBIDDEN",
                f"이 작업은 {'·'.join(labels)}만 할 수 있습니다.",
                {"required_roles": sorted(allowed)},
            )

    return _check


#: 기획을 고치고 진단을 돌리는 쪽. 부스 관리자는 읽기만 한다.
CanManagePlan = Depends(require_role(StaffRole.PLANNER, StaffRole.OPERATOR))


def require_judge(staff: OptionalStaff) -> FestivalStaff:
    """심사 점수를 매기는 쪽.

    **누가 매겼는지가 기록의 일부**라 토큰 없는 폴백을 허용하지 않습니다.
    `require_role` 은 토큰이 없으면 통과시키는데(로컬 개발용 폴백), 심사에서는
    그러면 `judge_scores.staff_id` 를 채울 수 없고 "한 심사위원이 같은 항목에
    두 번" 을 막는 유니크 제약도 무의미해집니다.

    기획자·운영자도 심사할 수 있게 둡니다 — 교내 행사에서는 사업단 담당자가
    심사위원을 겸하는 경우가 흔합니다.
    """
    if staff is None:
        raise ApiError(
            401,
            "JUDGE_AUTH_REQUIRED",
            "심사위원 로그인이 필요합니다. 누가 매겼는지가 점수의 일부입니다.",
        )
    allowed = {StaffRole.JUDGE, StaffRole.PLANNER, StaffRole.OPERATOR}
    if staff.role not in allowed:
        raise ApiError(
            403,
            "FORBIDDEN",
            "심사 권한이 없습니다.",
            {"role": staff.role.value},
        )
    return staff


CurrentJudge = Annotated[FestivalStaff, Depends(require_judge)]
FestivalAccess = Depends(require_festival_access)


# ── 참여자 ──────────────────────────────────────────────────────────────────


def get_participant(
    festival_id: int,
    db: DbSession,
    x_participant_secret: Annotated[str | None, Header(alias="X-Participant-Secret")] = None,
) -> Participant:
    """참여자 본인 조회용. 코드가 아니라 **비밀**로 인증한다.

    코드는 부스에서 스태프에게 보여주는 값이라 옆 사람도 볼 수 있다. 코드로 조회를
    허용하면 남의 수집 현황과 포인트가 들여다보인다.
    """
    if not x_participant_secret:
        raise ApiError(
            401,
            "PARTICIPANT_AUTH_REQUIRED",
            "참여자 인증이 필요합니다. 참여 코드를 다시 발급받으세요.",
        )

    hashed = security.hash_participant_secret(x_participant_secret)
    participant = db.execute(
        select(Participant).where(
            Participant.festival_id == festival_id,
            Participant.secret_hash == hashed,
        )
    ).scalar_one_or_none()
    if participant is None:
        raise ApiError(401, "PARTICIPANT_AUTH_FAILED", "참여자 정보를 확인할 수 없습니다.")
    return participant


CurrentParticipant = Annotated[Participant, Depends(get_participant)]


def get_optional_participant(
    festival_id: int,
    db: DbSession,
    x_participant_secret: Annotated[str | None, Header(alias="X-Participant-Secret")] = None,
) -> Participant | None:
    """참여자면 누구인지 알려주고, 아니어도 막지 않는다.

    현장 공지가 이걸 씁니다. 참여 코드를 아직 못 받은 사람도 우천 중단 공지는
    봐야 합니다 — 안내를 받으려면 먼저 등록하라고 요구하는 순간, 그 안내는
    가장 필요한 사람에게 닿지 않습니다.

    **틀린 secret 은 조용히 무시합니다.** 여기서 401 을 내면 공지가 안 보이는데,
    그건 인증이 목적이 아닌 화면에서 가장 나쁜 실패입니다.
    """
    if not x_participant_secret:
        return None
    hashed = security.hash_participant_secret(x_participant_secret)
    return db.execute(
        select(Participant).where(
            Participant.festival_id == festival_id,
            Participant.secret_hash == hashed,
        )
    ).scalar_one_or_none()


OptionalParticipant = Annotated[Participant | None, Depends(get_optional_participant)]


def require_booth_scope(
    staff: FestivalStaff | None,
    booth_id: int,
    account: OrganizationAccount | None = None,
) -> None:
    """`booth_manager` 는 **자기 부스의 미션만** 지급할 수 있다 — 계약 §1.

    역할 검사만으로는 부족하다. booth_manager 토큰이면 부스까지 봐야 한다.

    `account` 가 있으면 검사하지 않는다. 운영자가 콘솔에서 부스 화면을 열어
    보다가 담당자 코드로 로그인해 두면 그 쿠키가 남는데, 그 뒤 콘솔에서 다른
    부스를 여는 것까지 막히면 안 된다.
    """
    if account is not None:
        return
    if staff is None:
        return
    if staff.role != StaffRole.BOOTH_MANAGER:
        return
    if staff.booth_id != booth_id:
        raise ApiError(
            403,
            "FORBIDDEN",
            "담당 부스의 미션만 지급할 수 있습니다.",
            {"assigned_booth_id": staff.booth_id},
        )


#: 부스·미션·보드를 고치는 쪽. 부스 관리자는 조회와 자기 부스 지급만 한다.
CanOperate = Depends(require_role(StaffRole.PLANNER, StaffRole.OPERATOR))
