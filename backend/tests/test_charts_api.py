import json
from datetime import UTC, datetime

import httpx
import pytest

from app.models import ChartSource
from app.steam.charts_api import ChartsApi
from tests.fixtures.steam.charts import CONCURRENT, FEATURED, MOST_PLAYED, TOP_SELLERS

PATHS = {
    "/IStoreTopSellersService/GetWeeklyTopSellers/v1/": TOP_SELLERS,
    "/ISteamChartsService/GetMostPlayedGames/v1/": MOST_PLAYED,
    "/ISteamChartsService/GetGamesByConcurrentPlayers/v1/": CONCURRENT,
    "/api/featuredcategories": FEATURED,
}


def charts(handler=None, seen: list | None = None) -> ChartsApi:
    def default(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=PATHS[request.url.path])

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler or default))
    return ChartsApi(http, api_key="k", cc="kr", language="english")


async def test_top_sellers_parses_and_sends_input_json():
    seen: list = []
    fetch = await charts(seen=seen).top_sellers()
    assert fetch.failure is None and fetch.source is ChartSource.TOP_SELLERS
    assert [(i.rank, i.appid, i.name, i.last_week_rank, i.metric_value) for i in fetch.items] == [
        (1, 730, "Counter-Strike 2", 2, 300),
        (2, 570, "Dota 2", 1, 250),
        (3, 999001, "New Hit", None, 1),
    ]
    assert fetch.period_start == datetime.fromtimestamp(1792454400, UTC)
    sent = json.loads(seen[0].url.params["input_json"])
    # 최상위 country_code를 보내지 않아야 전 세계 순위가 온다(국가를 넣으면 그 나라 순위)
    assert "country_code" not in sent and sent["context"]["country_code"] == "KR"
    assert sent["page_count"] == 100
    assert "key" not in seen[0].url.params  # 키 불필요 소스에는 키를 보내지 않는다


async def test_most_played_and_concurrent():
    api = charts()
    mp = await api.most_played()
    assert [(i.appid, i.last_week_rank, i.metric_value) for i in mp.items] == [(730, 1, 1288020), (440, 5, 90000)]
    assert mp.items[0].image_url.endswith("/apps/730/header.jpg")
    cur = await api.concurrent()
    assert cur.period_start is None and cur.items[1].metric_value == 300000


async def test_featured_splits_dedupes_and_drops_non_games():
    specials, new = await charts().featured()
    assert [(i.rank, i.appid) for i in specials.items] == [(1, 620), (2, 1091500)]
    portal = specials.items[0]
    assert (portal.discount_percent, portal.final_price, portal.original_price, portal.currency) == (75, 275000, 1100000, "KRW")
    assert [i.appid for i in new.items] == [999002]


@pytest.mark.parametrize(
    ("response", "failure"),
    [
        (httpx.Response(503), "http_503"),
        (httpx.Response(200, text="<html>"), "schema"),
        (httpx.Response(200, json={"response": {"ranks": [{"rank": 1}]}}), "schema"),
        (httpx.Response(200, json={"response": {"ranks": []}}), "empty"),
        (httpx.ConnectError("down"), "network:ConnectError"),
        (httpx.ReadTimeout("slow"), "timeout"),
    ],
)
async def test_failures_become_failed_fetch(response, failure):
    def handler(request):
        if isinstance(response, Exception):
            raise response
        return response

    api = charts(handler)
    assert (await api.most_played()).failure == failure
    specials, new = await api.featured()
    assert specials.failure and new.failure  # 한 번의 호출이 실패하면 두 소스 모두 실패
