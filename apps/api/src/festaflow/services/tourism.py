"""관광 지표 수집.

세 가지 지역코드 체계를 잇습니다 — 실호출로 확인한 사실입니다.

    TourAPI areaCode2   광역 32(강원특별자치도) / 시군구 순번 1,2,3…
    법정동 코드          lDongRegnCd(51) + lDongSignguCd(110)
    DataLab signguCode  51110  ← 법정동 두 코드를 이어붙인 5자리

다리는 `areaBasedList2` 응답입니다. 콘텐츠 한 건만 조회하면 그 지역의
법정동 코드를 알 수 있고, 그걸로 방문자수 API를 부를 수 있습니다.

🚨 공모전 규정상 **실시간 호출**이 원칙입니다. 캐시로 호출을 0회로 만들지 않습니다.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from festaflow.core.config import KtoService
from festaflow.models.enums import TourismProvider
from festaflow.services.tourapi import (
    KtoError,
    KtoNoData,
    TourApiClient,
    category_code,
    coordinates,
    image_url,
    normalize_region,
)

log = logging.getLogger(__name__)

#: 대표 관광자원 최대 개수
MAX_RESOURCES = 8

#: 축제·행사 콘텐츠(15)는 areaBasedList2 만으로 종료일을 알 수 없어 제외한다.
#: 지난 축제를 "인근 볼거리"로 추천하는 사고를 막기 위해서다.
EXCLUDED_CONTENT_TYPES = {"15"}

#: lclsSystm1 코드 → 한국어 라벨
CATEGORY_LABELS = {
    "NA": "자연",
    "VE": "체험·문화",
    "FD": "음식",
    "SH": "쇼핑",
    "HS": "역사",
    "LS": "레포츠",
    "AC": "숙박",
    "EV": "행사",
}


@dataclass(slots=True)
class TourismIndicators:
    """진단이 소비하는 관광 지표 묶음.

    `sources` 에 지표별로 조회값인지 추정값인지 남깁니다.
    측정하지 않은 것을 측정했다고 말하지 않기 위해서입니다.
    """

    provider: TourismProvider
    region_key: str
    base_month: str

    area_code: str | None = None
    sigungu_code: str | None = None
    legal_dong_code: str | None = None

    content_count: int = 0
    category_count: int = 0
    resources: list[dict] = field(default_factory=list)

    #: 지역 일평균 방문자 수 (실측)
    daily_visitors_avg: float | None = None
    #: 외지인 비중 0~1 — 축제 유입 추정의 근거
    outsider_ratio: float | None = None
    #: 행사 월 방문자 ÷ 비수기 기준월 방문자. 1.0 이면 차이 없음.
    season_ratio: float | None = None
    baseline_month: str | None = None

    demand_index: float = 50.0  # 0~100
    season_fit: float = 0.5  # 0~1
    estimated_daily_capacity: int = 3000
    congestion_risk: float = 0.5  # 0~1
    local_link_readiness: float = 0.5  # 0~1

    sources: dict[str, str] = field(default_factory=dict)

    @property
    def is_demo(self) -> bool:
        return self.provider is TourismProvider.DEMO

    @property
    def source_note(self) -> str:
        if self.is_demo:
            return "데모 대체 데이터(API 연결 실패) — 실제 관광 데이터가 아닙니다"
        measured = [k for k, v in self.sources.items() if v == "조회"]
        estimated = [k for k, v in self.sources.items() if v == "추정"]
        parts = ["출처: ⓒ한국관광공사"]
        if measured:
            parts.append(f"조회: {', '.join(measured)}")
        if estimated:
            parts.append(f"FestaFlow 추정: {', '.join(estimated)}")
        parts.append(f"기준월 {self.base_month}")
        return " · ".join(parts)


# ── 지역코드 해석 ───────────────────────────────────────────────────────────


async def resolve_region(client: TourApiClient, region: str) -> tuple[str | None, str | None]:
    """지역명 → (광역 코드, 시군구 코드).

    `강원특별자치도 춘천시` → `("32", "3")`
    시군구를 못 찾으면 광역 코드만 반환합니다.
    """
    target = normalize_region(region)
    if not target:
        return (None, None)

    provinces = await client.call(KtoService.KOR, "areaCode2", {}, num_of_rows=50)
    area_code = None
    for item in provinces.items:
        if normalize_region(str(item.get("name", ""))) and target.startswith(
            normalize_region(str(item.get("name", "")))
        ):
            area_code = str(item["code"])
            break
    if area_code is None:
        log.info("지역코드 미해석: %s (정규화 %s)", region, target)
        return (None, None)

    remainder = target[len(normalize_region(str(next(
        i["name"] for i in provinces.items if str(i["code"]) == area_code
    )))):]
    if not remainder:
        return (area_code, None)

    districts = await client.call(
        KtoService.KOR, "areaCode2", {"areaCode": area_code}, num_of_rows=60
    )
    for item in districts.items:
        if normalize_region(str(item.get("name", ""))) == remainder:
            return (area_code, str(item["code"]))
    return (area_code, None)


# ── 지표 수집 ───────────────────────────────────────────────────────────────


def _pick_resources(items: list[dict]) -> list[dict]:
    """같은 유형에 몰리지 않도록 유형별 첫 자원을 먼저 뽑고 나머지를 채운다."""
    usable = [
        it
        for it in items
        if str(it.get("contenttypeid", "")) not in EXCLUDED_CONTENT_TYPES and it.get("title")
    ]
    by_type: dict[str, list[dict]] = {}
    for it in usable:
        by_type.setdefault(category_code(it) or "ETC", []).append(it)

    picked: list[dict] = []
    for bucket in by_type.values():  # 유형별 첫 자원
        picked.append(bucket[0])
        if len(picked) >= MAX_RESOURCES:
            break
    if len(picked) < MAX_RESOURCES:
        for bucket in by_type.values():
            for it in bucket[1:]:
                picked.append(it)
                if len(picked) >= MAX_RESOURCES:
                    break
            if len(picked) >= MAX_RESOURCES:
                break

    out = []
    for it in picked[:MAX_RESOURCES]:
        code = category_code(it) or "ETC"
        out.append(
            {
                "contentid": it.get("contentid"),
                "title": it.get("title"),
                "addr1": it.get("addr1"),
                "category": code,
                "category_label": CATEGORY_LABELS.get(code, "기타"),
                "image_url": image_url(it),
                "coordinates": coordinates(it),
            }
        )
    return out


#: 시군구 일평균 방문자의 현실 범위를 log10 으로 잡은 구간. 포화 방지용.
DEMAND_LOG_MIN = 4.0  # 1만 명
DEMAND_LOG_MAX = 6.0  # 100만 명

#: 계절 적합도 기준월 오프셋(개월). 행사 월과 비교할 비수기 표본.
SEASON_BASELINE_OFFSET_MONTHS = 6

#: 표본으로 쓸 일수. 늘릴수록 정확하지만 호출 수가 그만큼 는다.
VISITOR_SAMPLE_DAYS = 3

#: 하루치 전국 응답 행 수(약 800). 한 페이지에 담기도록 넉넉히 잡는다.
VISITOR_PAGE_SIZE = 1200


def _sample_days(target: date, count: int = VISITOR_SAMPLE_DAYS) -> list[str]:
    """작년 같은 달 초의 며칠. 방문자수 API 는 startYmd·endYmd 가 필수다."""
    first = date(target.year - 1, target.month, 1)
    return [(first + timedelta(days=i)).strftime("%Y%m%d") for i in range(count)]


async def _fetch_visitors(
    client: TourApiClient, legal_dong: str, when: date
) -> tuple[float | None, float | None]:
    """(일평균 방문자, 외지인 비중).

    ⚠ 이 API 는 **지역 필터 파라미터를 받지 않는다.** 실호출로 확인했다 —
      signguCode·signguCd·areaCd 전부 code 10(INVALID_REQUEST_PARAMETER).
      startYmd·endYmd 만 받고 전국 시군구를 반환하므로 클라이언트에서 걸러야 한다.
      하루치가 약 800행이라 일자별로 나눠 부른다.

    `touDivCd` 로 현지인/외지인이 구분된다 — 축제 유입 추정의 근거가 된다.
    """

    def _num(r: dict) -> float:
        try:
            return float(r.get("touNum") or 0)
        except (TypeError, ValueError):
            return 0.0

    daily_totals: list[float] = []
    outsider_total = 0.0
    grand_total = 0.0

    for ymd in _sample_days(when):
        try:
            res = await client.call(
                KtoService.DATALAB,
                "locgoRegnVisitrDDList",
                {"startYmd": ymd, "endYmd": ymd},
                num_of_rows=VISITOR_PAGE_SIZE,
            )
        except KtoNoData:
            continue
        except KtoError as exc:
            log.warning("방문자수 %s 조회 실패: %s", ymd, exc)
            continue

        rows = [r for r in res.items if str(r.get("signguCode", "")) == legal_dong]
        if not rows:
            continue
        day_sum = sum(_num(r) for r in rows)
        daily_totals.append(day_sum)
        grand_total += day_sum
        # touDivCd 1 = 현지인. 그 외를 외지인으로 본다.
        outsider_total += sum(_num(r) for r in rows if str(r.get("touDivCd")) != "1")

    if not daily_totals:
        return (None, None)

    daily_avg = grand_total / len(daily_totals)
    ratio = (outsider_total / grand_total) if grand_total > 0 else None
    return (daily_avg, ratio)


def _demo(region: str, base_month: str) -> TourismIndicators:
    """API 를 못 쓸 때의 안정적인 대체 데이터."""
    return TourismIndicators(
        provider=TourismProvider.DEMO,
        region_key=normalize_region(region) or region,
        base_month=base_month,
        content_count=120,
        category_count=5,
        resources=[],
        demand_index=52.0,
        season_fit=0.55,
        estimated_daily_capacity=5800,
        congestion_risk=0.48,
        local_link_readiness=0.62,
        sources={k: "데모" for k in
                 ("관광수요", "계절적합도", "일일수용력", "혼잡위험도", "지역연계준비도")},
    )


async def collect(
    client: TourApiClient, *, region: str, starts_on: date, expected_visitors: int, days: int
) -> TourismIndicators:
    """지역 관광 지표를 실시간으로 수집한다.

    개별 API 가 실패해도 나머지로 계속 진행합니다.
    전부 실패했을 때만 데모 공급자로 떨어집니다.
    """
    base_month = f"{starts_on.year - 1}{starts_on.month:02d}"

    try:
        area_code, sigungu_code = await resolve_region(client, region)
    except KtoError as exc:
        log.warning("지역코드 해석 실패 (%s) — 데모로 폴백: %s", region, exc)
        return _demo(region, base_month)

    if area_code is None:
        log.info("지역코드를 찾지 못해 데모로 폴백: %s", region)
        return _demo(region, base_month)

    ind = TourismIndicators(
        provider=TourismProvider.KTO_LIVE,
        region_key=normalize_region(region),
        base_month=base_month,
        area_code=area_code,
        sigungu_code=sigungu_code,
    )

    # ① 관광 콘텐츠 — 자원 수, 유형 수, 대표 자원, 법정동 코드
    try:
        params = {"areaCode": area_code, "arrange": "A"}
        if sigungu_code:
            params["sigunguCode"] = sigungu_code
        content = await client.call(
            KtoService.KOR, "areaBasedList2", params, num_of_rows=100
        )
        ind.content_count = content.total_count
        ind.category_count = len({category_code(i) for i in content.items if category_code(i)})
        ind.resources = _pick_resources(content.items)
        ind.sources["관광자원"] = "조회"

        for it in content.items:
            regn, sig = it.get("lDongRegnCd"), it.get("lDongSignguCd")
            if regn and sig:
                ind.legal_dong_code = f"{regn}{sig}"
                break
    except KtoNoData:
        ind.sources["관광자원"] = "데이터 없음"
    except KtoError as exc:
        log.warning("관광 콘텐츠 조회 실패: %s", exc)
        ind.sources["관광자원"] = "조회 실패"

    # ② 실측 방문자수 — 수요 지수와 계절 적합도의 근거
    if ind.legal_dong_code:
        try:
            daily, ratio = await _fetch_visitors(client, ind.legal_dong_code, starts_on)
            if daily:
                ind.daily_visitors_avg = daily
                ind.outsider_ratio = ratio
                ind.sources["관광수요"] = "조회"

                # 행사 월이 비수기 대비 붐비는지 — 기준월을 한 번 더 조회한다.
                baseline_month = starts_on.replace(day=1) - timedelta(days=1)
                for _ in range(SEASON_BASELINE_OFFSET_MONTHS - 1):
                    baseline_month = baseline_month.replace(day=1) - timedelta(days=1)
                base_daily, _ = await _fetch_visitors(
                    client, ind.legal_dong_code, baseline_month
                )
                if base_daily:
                    ind.season_ratio = daily / base_daily
                    ind.baseline_month = baseline_month.strftime("%Y%m")
                    ind.sources["계절적합도"] = "조회"
        except KtoError as exc:
            log.warning("방문자수 조회 실패: %s", exc)

    # ③ 파생 지표 계산
    _derive(ind, expected_visitors=expected_visitors, days=days)
    return ind


def _derive(ind: TourismIndicators, *, expected_visitors: int, days: int) -> None:
    """조회값에서 파생 지표를 계산한다. 조회값이 없으면 추정으로 채운다."""

    # 관광수요 지수 0~100
    if ind.daily_visitors_avg:
        # 시군구 일평균 방문자는 대략 1만~100만 범위다.
        # 그냥 log10×20 으로 두면 어지간한 지역이 전부 100 으로 포화된다.
        # log10 [4, 6] 구간을 [0, 100] 에 펴서 매핑한다.
        scaled = (math.log10(ind.daily_visitors_avg + 1) - DEMAND_LOG_MIN) / (
            DEMAND_LOG_MAX - DEMAND_LOG_MIN
        )
        ind.demand_index = min(100.0, max(0.0, scaled * 100.0))
    else:
        ind.demand_index = min(100.0, 30.0 + math.log1p(ind.content_count) * 8.0)
        ind.sources.setdefault("관광수요", "추정")

    # 계절 적합도 — 행사 월이 비수기 대비 얼마나 붐비는가.
    # 외지인 비중을 여기에 쓰면 안 된다. 그건 "누가 오는가"이지 "언제가 좋은가"가 아니다.
    if ind.season_ratio is not None:
        # 비수기 대비 2배 = 1.0, 같으면 0.5
        ind.season_fit = min(1.0, max(0.0, ind.season_ratio / 2.0))
    else:
        ind.season_fit = 0.5
        ind.sources.setdefault("계절적합도", "추정")

    # 추정 일일 수용력 — 관광 콘텐츠 수 기반. 공사가 제공하지 않는 값이다.
    ind.estimated_daily_capacity = int(
        max(3000, 2500 + math.sqrt(max(ind.content_count, 0)) * 300)
    )
    ind.sources["일일수용력"] = "추정"

    # 혼잡 위험도 — tarDecoList(혼잡도 예측)를 못 쓰므로 추정식으로 폴백한다.
    daily_expected = math.ceil(expected_visitors / max(days, 1))
    demand_norm = ind.demand_index / 100.0
    over = max(0.0, daily_expected / max(ind.estimated_daily_capacity, 1) - 1.0)
    ind.congestion_risk = min(1.0, max(0.0, 0.25 + demand_norm * 0.35 + min(over, 1.0) * 0.25))
    ind.sources["혼잡위험도"] = "추정"

    # 지역 연계 준비도 — TarRlteTarService1(연관 관광지)을 못 쓰므로 추정.
    ind.local_link_readiness = min(0.95, 0.45 + math.log1p(ind.content_count) / 10.0)
    ind.sources["지역연계준비도"] = "추정"
