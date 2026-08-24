"""메일 발송 — 조용히 실패하지 않는다.

발송기가 없을 때 성공한 척하면 운영자는 메일이 갔다고 믿고 사용자는 영원히
기다립니다. 그래서 설정이 없으면 **보내지 않고 그 사실을 로그로 남깁니다.**

받는 주소는 사용자가 넣는 값입니다. 줄바꿈이 들어가면 헤더를 새로 쓸 수 있어
(`\\r\\nBcc: ...`) 재설정 요청 한 번으로 임의의 수신자에게 메일을 보낼 수 있습니다.
"""

from __future__ import annotations

import pytest

from festaflow.core.config import settings
from festaflow.services import mailer


@pytest.fixture
def smtp_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.kr", raising=False)
    monkeypatch.setattr(settings, "mail_from", "no-reply@festaflow.kr", raising=False)
    monkeypatch.setattr(settings, "app_env", "production", raising=False)


def test_설정이_없으면_보내지_않는다(monkeypatch, caplog) -> None:
    monkeypatch.setattr(settings, "smtp_host", "", raising=False)
    monkeypatch.setattr(settings, "mail_from", "", raising=False)
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    monkeypatch.setattr(settings, "demo_mode", False, raising=False)

    with caplog.at_level("ERROR"):
        sent = mailer.send_password_reset(
            to="사람@festaflow.kr", reset_url="https://x/reset?t=1"
        )

    assert sent is False
    # 조용히 실패하지 않는다. 운영자가 알아야 고친다.
    assert "SMTP 설정이 없어" in caplog.text


def test_로컬에서는_링크를_로그에_남긴다(monkeypatch, caplog) -> None:
    """개발에서는 링크를 봐야 흐름을 확인할 수 있다."""
    monkeypatch.setattr(settings, "smtp_host", "", raising=False)
    monkeypatch.setattr(settings, "app_env", "local", raising=False)

    with caplog.at_level("WARNING"):
        mailer.send_password_reset(to="a@festaflow.kr", reset_url="https://x/reset?t=abc")

    assert "https://x/reset?t=abc" in caplog.text


def test_줄바꿈이_든_주소는_거부한다(smtp_configured, monkeypatch) -> None:
    """`\\r\\nBcc:` 를 붙이면 요청 한 번으로 임의의 수신자에게 메일이 나간다."""
    sent_calls = []
    monkeypatch.setattr(
        mailer.threading, "Thread", lambda **kw: _FakeThread(sent_calls, **kw)
    )

    sent = mailer.send_password_reset(
        to="victim@festaflow.kr\r\nBcc: attacker@evil.kr",
        reset_url="https://x/reset?t=1",
    )

    assert sent is False
    assert sent_calls == []


def test_보내는_메일에_만료_시간이_적힌다(smtp_configured) -> None:
    """서비스와 문구가 다르면 사용자는 만료된 링크를 계속 누른다."""
    msg = mailer._build("a@festaflow.kr", "https://x/reset?t=abc")
    body = msg.get_content()

    assert f"{settings.reset_ttl_minutes}분" in body
    assert "https://x/reset?t=abc" in body
    # 본인이 요청하지 않았을 때 무엇을 해야 하는지 알려준다.
    assert "무시" in body
    # 자동응답이 되돌아오지 않게 한다.
    assert msg["Auto-Submitted"] == "auto-generated"


def test_응답을_기다리지_않는다(smtp_configured, monkeypatch) -> None:
    """SMTP 가 느려도 재설정 화면은 즉시 답해야 한다. 발송은 스레드로 넘긴다."""
    started = []
    monkeypatch.setattr(mailer.threading, "Thread", lambda **kw: _FakeThread(started, **kw))

    sent = mailer.send_password_reset(to="a@festaflow.kr", reset_url="https://x/reset?t=1")

    assert sent is True
    assert len(started) == 1
    assert started[0]["daemon"] is True


def test_로그에_주소를_통째로_남기지_않는다() -> None:
    """로그가 유출되면 그게 곧 가입자 명단이 된다."""
    assert mailer._mask("hanseoyeon@festaflow.kr") == "ha***@festaflow.kr"
    assert mailer._mask("a@festaflow.kr") == "a***@festaflow.kr"
    assert mailer._mask("이상한값") == "***"


class _FakeThread:
    """스레드를 띄우지 않고 호출만 기록한다."""

    def __init__(self, sink, **kwargs):
        self.sink = sink
        self.kwargs = kwargs

    def start(self):
        self.sink.append(self.kwargs)
