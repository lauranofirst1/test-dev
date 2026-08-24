"""인증키·비밀값이 로그와 응답에 새지 않는지 검증.

스펙의 "참여 코드·접근 코드·secret 은 로그에 남기지 않는다"가
코드에서 참인지 확인합니다. 한 번 새면 되돌릴 수 없는 종류의 실수입니다.
"""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from festaflow.core.config import KtoService, settings
from festaflow.services.tourapi import TourApiClient

SECRET = "SUPER+SECRET/KEY=="


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setattr(settings, "kto_api_key", SECRET, raising=False)
    monkeypatch.setattr(settings, "kto_tour_api_key", "", raising=False)
    monkeypatch.setattr(settings, "kto_demand_api_key", "", raising=False)
    monkeypatch.setattr(settings, "kto_max_retries", 0, raising=False)


def test_httpx_request_logging_is_silenced():
    """httpx 는 요청 URL 을 통째로 INFO 로 남긴다 — serviceKey 가 거기 있다."""
    import festaflow.main  # noqa: F401  — 로깅 설정이 여기서 적용된다

    assert logging.getLogger("httpx").level >= logging.WARNING


@respx.mock
async def test_key_absent_from_error_messages(caplog):
    """실패 로그·예외 문자열에도 키가 들어가면 안 된다."""
    respx.get(url__startswith=settings.kto_base_url).mock(
        return_value=httpx.Response(
            200,
            text=(
                "<OpenAPI_ServiceResponse><cmmMsgHeader>"
                "<errMsg>SERVICE ERROR</errMsg>"
                "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
                "<returnReasonCode>30</returnReasonCode>"
                "</cmmMsgHeader></OpenAPI_ServiceResponse>"
            ),
        )
    )
    with caplog.at_level(logging.DEBUG):
        async with TourApiClient() as c:
            with pytest.raises(Exception) as exc:  # noqa: PT011
                await c.call(KtoService.KOR, "areaBasedList2")

    assert SECRET not in str(exc.value)
    assert "SUPER" not in caplog.text


@respx.mock
async def test_quota_log_does_not_contain_key(caplog):
    respx.get(url__startswith=settings.kto_base_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "22", "resultMsg": "LIMIT"},
                    "body": {"items": ""},
                }
            },
        )
    )
    with caplog.at_level(logging.DEBUG):
        async with TourApiClient() as c:
            with pytest.raises(Exception):  # noqa: PT011, B017
                await c.call(KtoService.DATALAB, "locgoRegnVisitrDDList")
    assert "SUPER" not in caplog.text
