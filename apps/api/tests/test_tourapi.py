"""TourAPI 클라이언트 테스트.

실제 응답에서 확인한 함정 8개가 전부 처리되는지 검증합니다.
인증키 없이 돌아갑니다 — 응답을 respx 로 가로챕니다.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from festaflow.core.config import KtoService, settings
from festaflow.services import tourapi
from festaflow.services.tourapi import (
    KtoConfigError,
    KtoNoData,
    KtoQuotaExceeded,
    TourApiClient,
    category_code,
    coordinates,
    image_url,
    normalize_region,
    normalize_service_key,
    region_codes,
)

BASE = settings.kto_base_url


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    """테스트 동안만 키가 있는 것처럼 만든다."""
    monkeypatch.setattr(settings, "kto_api_key", "TEST+KEY/abc==", raising=False)
    monkeypatch.setattr(settings, "kto_tour_api_key", "", raising=False)
    monkeypatch.setattr(settings, "kto_demand_api_key", "", raising=False)
    monkeypatch.setattr(settings, "kto_max_retries", 0, raising=False)


def _ok_body(items: list[dict] | dict | str, *, total: int | None = None, code: str = "0000"):
    return {
        "response": {
            "header": {"resultCode": code, "resultMsg": "OK"},
            "body": {
                "items": items,
                "numOfRows": 10,
                "pageNo": 1,
                "totalCount": total if total is not None else (len(items) if isinstance(items, list) else 1),
            },
        }
    }


# ── 함정 ① resultCode 가 0000 ───────────────────────────────────────────────


@respx.mock
async def test_result_code_0000_is_success():
    """문서에는 00 이라고 적혀 있지만 실제는 0000. 이걸 실패로 보면 전부 깨진다."""
    respx.get(url__startswith=f"{BASE}/{KtoService.KOR}/areaBasedList2").mock(
        return_value=httpx.Response(200, json=_ok_body([{"title": "가가책방"}], code="0000"))
    )
    async with TourApiClient() as c:
        res = await c.call(KtoService.KOR, "areaBasedList2")
    assert res.items[0]["title"] == "가가책방"


@respx.mock
async def test_result_code_00_also_success():
    respx.get(url__startswith=f"{BASE}/{KtoService.KOR}/areaBasedList2").mock(
        return_value=httpx.Response(200, json=_ok_body([{"title": "x"}], code="00"))
    )
    async with TourApiClient() as c:
        res = await c.call(KtoService.KOR, "areaBasedList2")
    assert len(res.items) == 1


# ── 포털 에러가 XML 로 오는 문제 ────────────────────────────────────────────

PORTAL_XML = """<OpenAPI_ServiceResponse>
<cmmMsgHeader>
<errMsg>SERVICE ERROR</errMsg>
<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
<returnReasonCode>30</returnReasonCode>
</cmmMsgHeader>
</OpenAPI_ServiceResponse>"""


@respx.mock
async def test_portal_error_arrives_as_xml_even_with_json_type():
    """_type=json 을 붙여도 포털 에러는 XML. JSON 파싱 실패로 뭉개면 원인을 못 찾는다."""
    respx.get(url__startswith=f"{BASE}/{KtoService.KOR}/areaBasedList2").mock(
        return_value=httpx.Response(200, text=PORTAL_XML)
    )
    async with TourApiClient() as c:
        with pytest.raises(KtoConfigError) as exc:
            await c.call(KtoService.KOR, "areaBasedList2")
    assert exc.value.code == "30"
    assert "SERVICE_KEY_IS_NOT_REGISTERED" in str(exc.value)


# ── 03 은 에러가 아니다 ─────────────────────────────────────────────────────


@respx.mock
async def test_nodata_is_its_own_exception():
    """데이터가 얇은 기초지자체에서 정상 발생. 실패로 처리하면 그 지역은 영원히 데모 데이터만 본다."""
    respx.get(url__startswith=f"{BASE}/{KtoService.DEMAND}/x").mock(
        return_value=httpx.Response(200, json=_ok_body([], code="03"))
    )
    async with TourApiClient() as c:
        with pytest.raises(KtoNoData):
            await c.call(KtoService.DEMAND, "x")


# ── 22 는 재시도 금지 + 당일 차단 ───────────────────────────────────────────


@respx.mock
async def test_quota_blocks_service_for_the_day():
    route = respx.get(url__startswith=f"{BASE}/{KtoService.DATALAB}/y").mock(
        return_value=httpx.Response(200, json=_ok_body([], code="22"))
    )
    async with TourApiClient() as c:
        with pytest.raises(KtoQuotaExceeded):
            await c.call(KtoService.DATALAB, "y")
        assert c.is_blocked(KtoService.DATALAB)
        # 두 번째 호출은 네트워크를 타지 않고 즉시 차단
        with pytest.raises(KtoQuotaExceeded):
            await c.call(KtoService.DATALAB, "y")
    assert route.call_count == 1


# ── items 형태가 제각각 ─────────────────────────────────────────────────────


@respx.mock
@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ("", 0),  # 빈 문자열
        ({"item": {"a": 1}}, 1),  # 단건이면 dict
        ({"item": [{"a": 1}, {"a": 2}]}, 2),  # 복수면 list
        ([{"a": 1}], 1),
    ],
)
async def test_items_shapes(items, expected):
    respx.get(url__startswith=f"{BASE}/{KtoService.KOR}/areaBasedList2").mock(
        return_value=httpx.Response(200, json=_ok_body(items, total=expected))
    )
    async with TourApiClient() as c:
        res = await c.call(KtoService.KOR, "areaBasedList2")
    assert len(res.items) == expected


# ── 인증키 이중 인코딩 ──────────────────────────────────────────────────────


def test_service_key_never_double_encodes():
    """Encoding 키를 넣어도 %252B 가 되지 않아야 한다."""
    decoding = "abc+def/ghi=="
    encoding = "abc%2Bdef%2Fghi%3D%3D"
    assert normalize_service_key(decoding) == normalize_service_key(encoding)
    assert "%25" not in normalize_service_key(encoding)


@respx.mock
async def test_missing_key_raises_config_error(monkeypatch):
    monkeypatch.setattr(settings, "kto_api_key", "", raising=False)
    async with TourApiClient() as c:
        with pytest.raises(KtoConfigError) as exc:
            await c.call(KtoService.KOR, "areaBasedList2")
    assert exc.value.code == "NO_KEY"


# ── 필드 헬퍼 (실측 응답 기준) ──────────────────────────────────────────────

# docs/07 §8.2 의 실제 응답에서 가져온 항목
REAL_ITEM_WITH_EMPTY_CAT = {
    "addr1": "충청남도 공주시 감영길 3 (반죽동)",
    "areacode": "",
    "cat1": "",
    "cat2": "",
    "cat3": "",
    "contentid": "2750144",
    "firstimage": "",
    "mapx": "127.121658480839",
    "mapy": "36.4528799330097",
    "sigungucode": "",
    "title": "가가상점",
    "lDongRegnCd": "44",
    "lDongSignguCd": "150",
    "lclsSystm1": "SH",
}

REAL_ITEM_FULL = {
    "areacode": "34",
    "cat1": "A02",
    "contentid": "2750143",
    "firstimage": "http://tong.visitkorea.or.kr/cms/resource/06/3564906_image2_1.jpg",
    "mapx": "127.1219749520",
    "mapy": "36.4521187744",
    "sigungucode": "1",
    "title": "가가책방",
    "lDongRegnCd": "44",
    "lDongSignguCd": "150",
    "lclsSystm1": "VE",
}


def test_region_codes_use_ldong_not_areacode():
    """areacode 가 비어도 법정동 코드는 있다."""
    assert region_codes(REAL_ITEM_WITH_EMPTY_CAT) == ("44", "150")


def test_category_falls_back_to_lcls_when_cat1_empty():
    """cat1 이 빈 항목이 12건 중 6건이었다. lclsSystm1 이 없으면 유형 집계에서 누락된다."""
    assert category_code(REAL_ITEM_WITH_EMPTY_CAT) == "SH"
    assert category_code(REAL_ITEM_FULL) == "VE"
    assert category_code({"cat1": "A01"}) == "A01"
    assert category_code({}) is None


def test_image_url_upgraded_to_https():
    assert image_url(REAL_ITEM_FULL).startswith("https://")
    assert image_url(REAL_ITEM_WITH_EMPTY_CAT) is None


def test_coordinates_tolerate_varied_precision_and_missing():
    assert coordinates(REAL_ITEM_FULL) == (127.121974952, 36.4521187744)
    assert coordinates({"mapx": "", "mapy": ""}) is None
    assert coordinates({}) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("강원특별자치도 춘천시", "강원춘천"),
        ("전남광주통합특별시", "전남광주"),
        ("서울특별시 종로구", "서울종로"),
        ("부산광역시 부산진구", "부산부산진"),
    ],
)
def test_region_normalization_handles_reorganized_names(raw, expected):
    assert normalize_region(raw) == expected


# ── 호출 카운터 (공모전 호출 이력) ──────────────────────────────────────────


@respx.mock
async def test_call_count_tracks_real_requests():
    respx.get(url__startswith=f"{BASE}/{KtoService.KOR}/areaBasedList2").mock(
        return_value=httpx.Response(200, json=_ok_body([{"a": 1}]))
    )
    async with TourApiClient() as c:
        await c.call(KtoService.KOR, "areaBasedList2")
        await c.call(KtoService.KOR, "areaBasedList2")
        assert c.call_count == 2


def test_cache_is_off_by_default():
    """공모전 규정상 실시간 호출이 원칙. 기본값이 켜져 있으면 안 된다."""
    assert tourapi.settings.tourism_snapshot_cache_enabled is False
