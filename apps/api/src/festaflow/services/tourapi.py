"""한국관광공사 OpenAPI 클라이언트.

docs/07-tourapi-catalog.md 의 §0 호출 규격, §6 에러 처리, §8 실측 응답 스키마를 구현합니다.
실제 응답을 호출해 확인한 함정 8개가 전부 반영돼 있습니다.

🚨 공모전 규정상 **실시간 호출**이 원칙입니다. 캐시로 호출을 0회로 만들면
   인증키 호출 이력이 남지 않아 심사 불이익 대상입니다 (docs/08-contest-submission.md §1).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import quote, unquote

import httpx
from defusedxml import ElementTree as ET

from festaflow.core.config import DEMAND_SERVICES, settings

log = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────

#: ⚠ 함정 ① — 문서 에러표에는 `00 NORMAL_CODE` 로 적혀 있지만 실제 응답은 `0000` 이다.
#: `== "00"` 으로 비교하면 정상 응답을 전부 실패로 처리하게 된다.
NORMAL_CODES = frozenset({"00", "0000", "0"})

#: 데이터 없음. **에러가 아니다.** 데이터가 얇은 기초지자체에서 정상적으로 발생한다.
NODATA_CODE = "03"

#: 요청제한 초과. 재시도하면 안 된다 — 자정까지 계속 실패한다.
QUOTA_CODE = "22"

#: 재시도해도 의미가 없는 설정·권한 문제.
FATAL_CODES = frozenset({"10", "11", "12", "20", "30", "31", "32", "33"})

#: 일시적 장애. 백오프 후 재시도한다.
RETRYABLE_CODES = frozenset({"01", "02", "04", "05", "99"})

#: ⚠ 함정 ⑧ — `전남광주통합특별시`, `강원특별자치도` 같은 개편 명칭이 실제로 나온다.
_REGION_NOISE = re.compile(
    r"(특별자치도|특별자치시|통합특별시|광역시|특별시|자치도|자치시|특별자치|자치구|[시군구도])$"
)
_NON_ALNUM_KO = re.compile(r"[^0-9A-Za-z가-힣]")


# ── 예외 ────────────────────────────────────────────────────────────────────


class KtoError(Exception):
    """TourAPI 호출 실패의 최상위 예외."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class KtoNoData(KtoError):
    """resultCode 03. 호출은 성공했고 결과가 비어 있을 뿐이다."""


class KtoQuotaExceeded(KtoError):
    """resultCode 22. 당일 해당 서비스 호출을 중단해야 한다."""


class KtoConfigError(KtoError):
    """인증키·권한·파라미터 문제. 재시도 무의미."""


class KtoTransientError(KtoError):
    """네트워크·타임아웃·일시 장애. 재시도 가능."""


# ── 응답 ────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class KtoResponse:
    """정상 응답 한 건."""

    items: list[dict[str, Any]]
    total_count: int
    page_no: int
    num_of_rows: int
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    def first(self) -> dict[str, Any] | None:
        return self.items[0] if self.items else None


# ── 인증키 ──────────────────────────────────────────────────────────────────


def normalize_service_key(raw: str) -> str:
    """⚠ 함정 ⑥ — 포털은 Encoding/Decoding 두 벌을 준다.

    HTTP 클라이언트가 쿼리스트링을 다시 인코딩하면 `%2B` 가 `%252B` 가 되어 인증이 깨진다.
    한 번 unquote 해서 원문으로 되돌린 뒤 정확히 한 번만 인코딩한다.
    """
    return quote(unquote(raw.strip()), safe="")


def _key_for(service: str) -> str:
    key = settings.demand_key if service in DEMAND_SERVICES else settings.tour_key
    if not key:
        raise KtoConfigError(
            f"{service} 호출에 필요한 인증키가 없습니다. .env 의 KTO_API_KEY 를 채우세요.",
            code="NO_KEY",
        )
    return key


# ── 응답 파싱 ───────────────────────────────────────────────────────────────


def _parse_portal_error(text: str) -> tuple[str, str] | None:
    """포털 레벨 에러를 꺼낸다.

    ⚠ 두 형태로 온다 — 실제 호출로 둘 다 확인했다.
      - XML  : `_type=json` 을 붙여도 XML 로 오는 경우
      - JSON : `{"OpenAPI_ServiceResponse": {"cmmMsgHeader": {...}}}`

    한 형태만 처리하면 인증 실패든 한도 초과든 전부 "파싱 실패"로 뭉개진다.

    Returns: (code, message) 또는 None
    """
    if "OpenAPI_ServiceResponse" not in text:
        return None

    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            header = json.loads(stripped)["OpenAPI_ServiceResponse"]["cmmMsgHeader"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return ("99", "포털 오류 응답(JSON)을 파싱하지 못했습니다.")
        return (
            str(header.get("returnReasonCode", "99")).strip(),
            str(header.get("returnAuthMsg") or header.get("errMsg") or "").strip(),
        )

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return ("99", "포털 오류 응답(XML)을 파싱하지 못했습니다.")
    code = (root.findtext(".//returnReasonCode") or "99").strip()
    msg = (root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or "").strip()
    return (code, msg)


def _raise_for_code(code: str, message: str, *, service: str, operation: str) -> None:
    where = f"{service}/{operation}"
    if code == NODATA_CODE:
        raise KtoNoData(f"{where}: 데이터 없음", code=code)
    if code == QUOTA_CODE:
        raise KtoQuotaExceeded(
            f"{where}: 일일 요청 한도({settings.kto_daily_quota}건)를 초과했습니다. "
            "자정까지 이 서비스 호출을 중단하고 캐시로 버팁니다.",
            code=code,
        )
    if code in FATAL_CODES:
        raise KtoConfigError(f"{where}: {message or '설정/권한 오류'} (code={code})", code=code)
    raise KtoTransientError(f"{where}: {message or '일시 오류'} (code={code})", code=code)


def _extract(payload: dict[str, Any], *, service: str, operation: str) -> KtoResponse:
    """제공기관 레벨 응답에서 items 를 꺼낸다.

    ⚠ 응답 봉투가 서비스마다 다르다 — 실제 호출로 확인했다.
      - KorService2 / PhotoGalleryService1 : {"response": {"header": …, "body": …}}
      - DataLabService                     : {"resultCode": "11", "resultMsg": …} (평평함)

    평평한 형태를 처리하지 않으면 DataLab 의 에러를 조용히 성공으로 읽는다.
    """
    if "response" in payload:
        response = payload.get("response") or {}
        header = response.get("header") or {}
        body = response.get("body") or {}
    else:
        # DataLabService 계열: 봉투 없이 최상위에 resultCode 와 items 가 함께 온다.
        header = payload
        body = payload

    code = str(header.get("resultCode", "")).strip()
    if code and code not in NORMAL_CODES:
        _raise_for_code(
            code,
            str(header.get("resultMsg", "")),
            service=service,
            operation=operation,
        )

    # items 는 빈 문자열 / dict / {"item": dict} / {"item": [dict]} 로 온다.
    raw_items = body.get("items")
    items: list[dict[str, Any]]
    if not raw_items:
        items = []
    elif isinstance(raw_items, dict):
        item = raw_items.get("item")
        if item is None:
            items = []
        elif isinstance(item, dict):
            items = [item]
        else:
            items = list(item)
    elif isinstance(raw_items, list):
        items = list(raw_items)
    else:
        items = []

    def _int(key: str, default: int = 0) -> int:
        try:
            return int(body.get(key, default))
        except (TypeError, ValueError):
            return default

    return KtoResponse(
        items=items,
        total_count=_int("totalCount", len(items)),
        page_no=_int("pageNo", 1),
        num_of_rows=_int("numOfRows", len(items)),
        raw=payload,
    )


# ── 클라이언트 ──────────────────────────────────────────────────────────────


class TourApiClient:
    """비동기 TourAPI 클라이언트.

    한도 초과(code 22)를 만난 서비스는 그날 자정까지 호출을 차단한다.
    재시도해봐야 계속 실패하고 로그만 더럽히기 때문이다.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None
        # service -> 차단 해제 날짜(그날 하루 차단)
        self._quota_blocked: dict[str, date] = {}
        self._call_count = 0

    async def __aenter__(self) -> TourApiClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=settings.kto_timeout_seconds)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def call_count(self) -> int:
        """이 클라이언트가 실제로 보낸 요청 수. 공모전 호출 이력 확인용."""
        return self._call_count

    def is_blocked(self, service: str) -> bool:
        return self._quota_blocked.get(service) == date.today()

    async def call(
        self,
        service: str,
        operation: str,
        params: dict[str, Any] | None = None,
        *,
        num_of_rows: int = 10,
        page_no: int = 1,
    ) -> KtoResponse:
        """오퍼레이션 1회 호출.

        Raises:
            KtoNoData: 결과가 비어 있음 (에러 아님 — 호출부가 흡수해야 한다)
            KtoQuotaExceeded: 일 한도 초과
            KtoConfigError: 인증키·권한·파라미터 문제
            KtoTransientError: 재시도해도 실패한 일시 장애
        """
        if self.is_blocked(service):
            raise KtoQuotaExceeded(
                f"{service}: 오늘 한도 초과로 차단된 상태입니다.", code=QUOTA_CODE
            )

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=settings.kto_timeout_seconds)
            self._owns_client = True

        key = normalize_service_key(_key_for(service))
        query = {
            "numOfRows": str(num_of_rows),
            "pageNo": str(page_no),
            "MobileOS": "ETC",
            "MobileApp": settings.kto_mobile_app,
            "_type": "json",
            **{k: str(v) for k, v in (params or {}).items() if v not in (None, "")},
        }
        # serviceKey 는 이미 인코딩돼 있으므로 httpx 의 params 에 넘기지 않고 직접 조립한다.
        qs = "&".join(f"{k}={quote(v, safe='')}" for k, v in query.items())
        url = f"{settings.kto_base_url}/{service}/{operation}?serviceKey={key}&{qs}"

        last: Exception | None = None
        for attempt in range(settings.kto_max_retries + 1):
            try:
                self._call_count += 1
                res = await self._client.get(url)
                # ⚠ raise_for_status() 를 먼저 부르면 안 된다.
                #   포털은 인증·서비스 오류를 **400 과 함께** 본문에 실어 보낸다.
                #   먼저 던지면 code 12/30 같은 진짜 원인을 영영 못 본다.
                return self._handle_body(
                    res.text, service=service, operation=operation, status=res.status_code
                )

            except (KtoNoData, KtoConfigError):
                raise  # 재시도 무의미

            except KtoQuotaExceeded:
                self._quota_blocked[service] = date.today()
                log.error("KTO 한도 초과 — %s 오늘 차단", service)
                raise

            except (KtoTransientError, httpx.HTTPError) as exc:
                last = exc
                if attempt < settings.kto_max_retries:
                    backoff = 0.5 * (2**attempt)
                    log.warning(
                        "KTO 일시 오류 %s/%s (%s/%s) — %.1fs 후 재시도",
                        service,
                        operation,
                        attempt + 1,
                        settings.kto_max_retries,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue

        raise KtoTransientError(
            f"{service}/{operation}: {settings.kto_max_retries + 1}회 시도 모두 실패 — {last}"
        )

    def _handle_body(
        self, text: str, *, service: str, operation: str, status: int = 200
    ) -> KtoResponse:
        # 포털 레벨 에러가 먼저다. 400 과 함께 오는 경우가 있다.
        portal = _parse_portal_error(text)
        if portal is not None:
            _raise_for_code(portal[0], portal[1], service=service, operation=operation)

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            if status >= 400:
                raise KtoTransientError(
                    f"{service}/{operation}: HTTP {status} — {text[:200]}"
                ) from exc
            raise KtoTransientError(
                f"{service}/{operation}: 응답을 JSON 으로 읽지 못했습니다 — {text[:200]}"
            ) from exc

        return _extract(payload, service=service, operation=operation)


# ── 응답 필드 헬퍼 (docs/07 §8.4) ───────────────────────────────────────────


def region_codes(item: dict[str, Any]) -> tuple[str | None, str | None]:
    """⚠ 함정 ④ — 지역 판별은 `areacode` 가 아니라 법정동 코드 기준.

    `areacode` / `sigungucode` 는 빈 항목이 매우 많다.
    `lDongRegnCd` / `lDongSignguCd` 는 항상 채워져 있다.
    """
    return (item.get("lDongRegnCd") or None, item.get("lDongSignguCd") or None)


def category_code(item: dict[str, Any]) -> str | None:
    """⚠ 함정 ③ — 유형 판별은 `lclsSystm1` 이 1순위.

    `cat1` 은 음식점·쇼핑 계열에서 빈 값이 많아 단독 기준으로 쓰면 자원이 통째로 누락된다.
    관측된 `lclsSystm1`: NA(자연) VE(체험·문화) FD(음식) SH(쇼핑)
    """
    return item.get("lclsSystm1") or item.get("cat1") or None


def image_url(item: dict[str, Any]) -> str | None:
    """⚠ 함정 ⑤ — 같은 응답 안에서도 http·https 가 섞여 온다.

    안 바꾸면 HTTPS 페이지에서 mixed content 로 차단된다.
    """
    url = (item.get("firstimage") or item.get("firstimage2") or "").strip()
    if not url:
        return None
    return url.replace("http://", "https://", 1)


def coordinates(item: dict[str, Any]) -> tuple[float, float] | None:
    """⚠ 함정 ⑦ — `mapx`/`mapy` 는 문자열이고 소수 자릿수가 제각각이며 빈 값도 온다."""
    try:
        return (float(item["mapx"]), float(item["mapy"]))
    except (KeyError, TypeError, ValueError):
        return None


def normalize_region(name: str) -> str:
    """지역명을 비교 가능한 형태로 정규화한다.

    `강원특별자치도 춘천시` → `강원춘천`
    `전남광주통합특별시`   → `전남광주`
    """
    parts = []
    for token in name.split():
        cleaned = _NON_ALNUM_KO.sub("", token)
        while True:
            stripped = _REGION_NOISE.sub("", cleaned)
            if stripped == cleaned:
                break
            cleaned = stripped
        if cleaned:
            parts.append(cleaned)
    return "".join(parts)
