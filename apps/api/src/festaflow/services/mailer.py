"""메일 발송.

지금 보내는 것은 비밀번호 재설정 링크 하나뿐입니다.

## 설정이 없으면 보내지 않습니다 — 조용히 실패하지도 않습니다

SMTP 설정이 비어 있으면 로컬에서는 링크를 로그에 남기고, 그 밖에서는 **보내지
못했다는 사실을 오류 로그로 남깁니다.** 조용히 성공한 척하면 운영자는 메일이
갔다고 믿고 사용자는 영원히 기다립니다.

## 응답을 기다리게 하지 않습니다

SMTP 연결은 느립니다. 서버가 응답하지 않으면 30초씩 매달릴 수 있는데, 그 사이
요청이 붙잡혀 있으면 재설정 화면이 멈춘 것처럼 보입니다. 그래서 발송은
**백그라운드 스레드**로 던지고 요청은 즉시 돌아옵니다.

응답이 발송 성공 여부에 좌우되면 안 되는 이유가 하나 더 있습니다 — 가입되지
않은 이메일과 가입된 이메일의 응답이 갈리면, 그 화면이 곧 "이 이메일이
가입돼 있나" 를 확인해 주는 도구가 됩니다. 어차피 같은 응답을 내야 하므로
기다릴 이유가 없습니다.

## 헤더 주입을 막습니다

받는 주소에 줄바꿈이 들어가면 헤더를 새로 쓸 수 있습니다(`\\r\\nBcc: ...`).
이메일은 사용자가 넣는 값이라 그대로 헤더에 붙이지 않습니다.
"""

from __future__ import annotations

import logging
import smtplib
import threading
from email.message import EmailMessage
from email.utils import formataddr

from festaflow.core.config import settings

log = logging.getLogger(__name__)

#: SMTP 연결·전송 제한. 넉넉하면 스레드가 오래 남고, 짧으면 느린 서버에서 실패한다.
SMTP_TIMEOUT_SECONDS = 15


def _configured() -> bool:
    return bool(settings.smtp_host and settings.mail_from)


def _safe_address(value: str) -> str:
    """헤더에 넣어도 되는 주소인지 본다.

    줄바꿈이 있으면 헤더를 새로 쓸 수 있다. 여기서 거르지 않으면 재설정 요청
    한 번으로 임의의 수신자에게 메일을 보낼 수 있다.
    """
    cleaned = value.strip()
    if any(c in cleaned for c in "\r\n") or len(cleaned) > 254:
        raise ValueError("메일 주소에 넣을 수 없는 문자가 있습니다.")
    return cleaned


def _build(to: str, reset_url: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "FestaFlow 비밀번호 재설정"
    msg["From"] = formataddr((settings.mail_from_name, _safe_address(settings.mail_from)))
    msg["To"] = _safe_address(to)
    # 자동 발송 메일임을 밝힌다. 없으면 부재중 자동응답이 되돌아온다.
    msg["Auto-Submitted"] = "auto-generated"

    minutes = settings.reset_ttl_minutes
    msg.set_content(
        "FestaFlow 비밀번호를 재설정하려면 아래 주소를 여세요.\n\n"
        f"{reset_url}\n\n"
        f"이 링크는 {minutes}분 뒤에 만료되며 한 번만 쓸 수 있습니다.\n"
        "본인이 요청한 것이 아니라면 이 메일을 무시하세요. "
        "링크를 열지 않으면 비밀번호는 그대로입니다.\n"
    )
    return msg


def _send_now(msg: EmailMessage, to: str) -> None:
    """실제 전송. 백그라운드 스레드에서 돈다."""
    try:
        if settings.smtp_use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
            )
        else:
            server = smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS
            )
        with server:
            if settings.smtp_use_tls and not settings.smtp_use_ssl:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
    except Exception:
        # 주소를 로그에 남기지 않는다 — 로그가 곧 가입자 명단이 된다.
        log.exception("비밀번호 재설정 메일 발송에 실패했습니다 (수신자 %s)", _mask(to))
        return
    log.info("비밀번호 재설정 메일을 보냈습니다 (%s)", _mask(to))


def _mask(address: str) -> str:
    """로그용 마스킹. 로그가 유출돼도 가입자 명단이 되지 않게 한다."""
    local, _, domain = address.partition("@")
    if not domain:
        return "***"
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}***@{domain}"


def send_password_reset(*, to: str, reset_url: str) -> bool:
    """재설정 링크를 보낸다. **큐에 넣었으면** True.

    돌려주는 값은 호출자가 화면 문구를 바꾸는 데 쓰지 않습니다 — 보냈든 못
    보냈든 응답은 같아야 이메일 존재가 드러나지 않습니다. 운영 로그와
    모니터링을 위한 값입니다.
    """
    if not _configured():
        if settings.app_env == "local" or settings.demo_mode:
            # 개발에서는 링크를 봐야 흐름을 확인할 수 있다.
            log.warning("[개발용] 비밀번호 재설정 링크 (%s): %s", to, reset_url)
            return False
        log.error(
            "SMTP 설정이 없어 비밀번호 재설정 링크를 보내지 못했습니다 (%s). "
            "SMTP_HOST 와 MAIL_FROM 을 채우기 전까지 이 기능은 동작하지 않습니다.",
            _mask(to),
        )
        return False

    try:
        msg = _build(to, reset_url)
    except ValueError:
        log.warning("메일 주소 형식이 헤더에 넣을 수 없어 발송을 건너뜁니다.")
        return False

    # 응답을 붙잡지 않는다. SMTP 가 느려도 재설정 화면은 즉시 답해야 한다.
    threading.Thread(
        target=_send_now, args=(msg, to), name="password-reset-mail", daemon=True
    ).start()
    return True
