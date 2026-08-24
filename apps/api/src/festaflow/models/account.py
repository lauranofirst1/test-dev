"""기관 계정 — 기획자가 로그인하는 자리.

**지금까지 기획자에게는 자격증명이 없었습니다.** 계약(§1)의 로그인은 축제별
스태프용이라 `festival_id` 를 요구하는데, 축제 목록·생성은 축제가 생기기 전에
호출됩니다. 그래서 그 경로들이 `X-Organization-Id` 헤더 폴백에 기대고 있었고,
그 폴백은 **헤더 하나만 바꾸면 남의 기관이 열리는 구멍**입니다.
(`core/deps.py` 가 그래서 `APP_ENV=local` 이나 데모에서만 폴백을 허용합니다.)

이 계정은 축제가 아니라 **기관**에 묶입니다. 축제가 없어도 로그인할 수 있고,
그래야 첫 축제를 만들 수 있습니다.

스태프 계정(`festival_staff`)과 나누어 둔 이유는 수명과 배포 방식이 다르기
때문입니다. 스태프는 축제마다 발급되고 끝나면 사라지며 6자리 코드를 종이로
받습니다. 기관 계정은 기관이 존재하는 동안 남고 이메일·비밀번호를 씁니다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from festaflow.db.base import Base, TimestampMixin


class OrganizationAccount(Base, TimestampMixin):
    __tablename__ = "organization_accounts"
    __table_args__ = (
        # 이메일은 시스템 전체에서 하나. 기관별로 두면 같은 이메일로 여러 기관에
        # 가입할 수 있고, 로그인할 때 어느 기관인지 물어야 한다.
        Index("uq_organization_accounts_email", "email", unique=True),
        Index("ix_organization_accounts_org", "organization_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )

    #: 소문자로 정규화해 저장한다. 대소문자가 다른 두 계정이 생기면
    #: 로그인할 때 어느 쪽인지 알 수 없다.
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    #: bcrypt-sha256. 평문은 어디에도 저장하지 않는다.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # ── 온라인 대입 방어 ──
    #: 스태프 접근 코드와 같은 장치. 비밀번호가 길다고 잠금을 빼면,
    #: 유출된 비밀번호 목록으로 훑는 공격(credential stuffing)이 그대로 통한다.
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: 비밀번호를 바꾸면 갱신한다. 이 시각보다 먼저 발급된 세션은 받지 않는다 —
    #: 바꾼 이유가 유출이면, 옛 세션이 살아 있는 한 바꾼 의미가 없다.
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordResetToken(Base):
    """비밀번호 재설정 표.

    **평문 토큰을 저장하지 않습니다.** 저장하는 것은 sha256 해시뿐이고, 평문은
    메일로 나간 링크에만 있습니다. DB 가 유출돼도 그 표로는 아무 계정도 못 엽니다.

    bcrypt 가 아니라 sha256 인 이유는 이 토큰이 서버가 만든 32바이트 난수라
    전수 대입이 애초에 불가능하기 때문입니다 — 저엔트로피 값(6자리 코드·비밀번호)
    에만 느린 해시가 필요합니다.

    **한 번 쓰면 죽습니다.** 링크가 메일함에 남아 있고 메일함은 종종 남에게
    열려 있습니다. 쓰고 나서도 유효하면 그 링크가 영구 열쇠가 됩니다.
    """

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("uq_password_reset_tokens_hash", "token_hash", unique=True),
        Index("ix_password_reset_tokens_account", "account_id", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organization_accounts.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: 쓴 시각. 채워지면 죽은 표다.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
