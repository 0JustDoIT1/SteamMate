"""Steam 상점 appdetails 클라이언트(비문서화 엔드포인트).

장르를 받으려면 게임 1개당 요청 1번이 필요하다(다중 appid는 price_overview 필터에서만 허용, 2026-11-03 확인).
가격은 `filters=price_overview`로 여러 게임을 한 번에 받는다(200개 정상, 400개는 HTTP 500 — 2026-11-03 확인).
결과는 예외 대신 FetchResult로 돌려주고, 상태 판정은 app.metadata.state가 맡는다.
"""

import logging
from dataclasses import dataclass, field
from enum import StrEnum

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

logger = logging.getLogger(__name__)

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"


class Outcome(StrEnum):
    OK = "OK"
    NOT_FOUND = "NOT_FOUND"  # success:false
    RATE_LIMITED = "RATE_LIMITED"
    ERROR = "ERROR"


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Genre(_Loose):
    id: str
    description: str


class Category(_Loose):
    id: int
    description: str


class AppData(_Loose):
    name: str = ""
    type: str = ""
    header_image: str = ""
    genres: list[Genre] = []
    categories: list[Category] = []
    dlc: list[int] = []


class _AppEntry(_Loose):
    success: bool
    data: AppData | None = None


@dataclass(frozen=True)
class FetchResult:
    outcome: Outcome
    data: AppData | None = None
    reason: str = field(default="")


class PriceOverview(_Loose):
    currency: str
    initial: int
    final: int
    discount_percent: int


class _PriceData(_Loose):
    price_overview: PriceOverview | None = None


class _PriceEntry(_Loose):
    success: bool
    # 가격이 없는 게임(무료·미출시)은 data가 빈 배열([])로 온다.
    data: _PriceData | list[object] | None = None


@dataclass(frozen=True)
class PriceResult:
    outcome: Outcome
    price: PriceOverview | None = None  # OK인데 None이면 가격 없음
    reason: str = ""


class StoreApi:
    def __init__(self, http: httpx.AsyncClient, cc: str, language: str) -> None:
        self._http = http
        self._cc = cc
        self._language = language

    async def app_details(self, appid: int) -> FetchResult:
        try:
            res = await self._http.get(
                APPDETAILS_URL, params={"appids": appid, "cc": self._cc, "l": self._language}
            )
        except httpx.TimeoutException:
            return FetchResult(Outcome.ERROR, reason="timeout")
        except httpx.HTTPError as exc:
            return FetchResult(Outcome.ERROR, reason=f"network:{type(exc).__name__}")

        # 상점은 과다 요청 시 429 또는 403을 준다[추정]. 둘 다 일시 제한으로 취급한다.
        if res.status_code in (429, 403):
            return FetchResult(Outcome.RATE_LIMITED, reason=f"http_{res.status_code}")
        if res.status_code != 200:
            return FetchResult(Outcome.ERROR, reason=f"http_{res.status_code}")

        try:
            entry = _AppEntry.model_validate(res.json()[str(appid)])
        except (ValueError, KeyError, TypeError, ValidationError):
            logger.warning("appdetails schema mismatch: appid=%s", appid)
            return FetchResult(Outcome.ERROR, reason="schema")

        if not entry.success:
            return FetchResult(Outcome.NOT_FOUND, reason="store_not_found")
        if entry.data is None:
            return FetchResult(Outcome.ERROR, reason="schema")
        return FetchResult(Outcome.OK, data=entry.data)

    async def prices(self, appids: list[int], cc: str) -> dict[int, PriceResult]:
        """한 번의 요청으로 여러 게임의 가격을 받는다. 요청 자체가 실패하면 모든 게임에 같은 결과를 준다."""

        def all_(outcome: Outcome, reason: str) -> dict[int, PriceResult]:
            return {a: PriceResult(outcome, reason=reason) for a in appids}

        try:
            res = await self._http.get(
                APPDETAILS_URL,
                params={"appids": ",".join(map(str, appids)), "filters": "price_overview", "cc": cc},
            )
        except httpx.TimeoutException:
            return all_(Outcome.ERROR, "timeout")
        except httpx.HTTPError as exc:
            return all_(Outcome.ERROR, f"network:{type(exc).__name__}")
        if res.status_code in (429, 403):
            return all_(Outcome.RATE_LIMITED, f"http_{res.status_code}")
        if res.status_code != 200:
            return all_(Outcome.ERROR, f"http_{res.status_code}")
        try:
            body = res.json()
            if not isinstance(body, dict):
                raise TypeError
        except (ValueError, TypeError):
            logger.warning("price response schema mismatch: %s appids", len(appids))
            return all_(Outcome.ERROR, "schema")

        results: dict[int, PriceResult] = {}
        for appid in appids:
            try:
                entry = _PriceEntry.model_validate(body[str(appid)])
            except (KeyError, ValidationError):
                results[appid] = PriceResult(Outcome.ERROR, reason="schema")
                continue
            if not entry.success:
                results[appid] = PriceResult(Outcome.NOT_FOUND, reason="store_not_found")
            elif isinstance(entry.data, _PriceData):
                results[appid] = PriceResult(Outcome.OK, price=entry.data.price_overview)
            else:
                results[appid] = PriceResult(Outcome.OK)
        return results
