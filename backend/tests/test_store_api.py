import httpx
import pytest

from app.steam.store_api import Outcome, StoreApi

DETAILS = {
    "620": {
        "success": True,
        "data": {
            "type": "game",
            "name": "Portal 2",
            "steam_appid": 620,
            "genres": [{"id": "1", "description": "Action"}, {"id": "25", "description": "Adventure"}],
            "categories": [{"id": 2, "description": "Single-player"}],
            "dlc": [323180],
            "about_the_game": "...",
        },
    }
}


def store(response: httpx.Response | Exception, seen: list | None = None) -> StoreApi:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if isinstance(response, Exception):
            raise response
        return response

    return StoreApi(httpx.AsyncClient(transport=httpx.MockTransport(handler)), cc="kr", language="english")


async def test_ok_parses_fields_and_sends_region_params():
    seen: list = []
    result = await store(httpx.Response(200, json=DETAILS), seen).app_details(620)
    assert result.outcome is Outcome.OK
    assert [g.description for g in result.data.genres] == ["Action", "Adventure"]
    assert result.data.type == "game" and result.data.dlc == [323180]
    params = seen[0].url.params
    assert (params["appids"], params["cc"], params["l"]) == ("620", "kr", "english")


async def test_success_false_is_not_found():
    result = await store(httpx.Response(200, json={"1": {"success": False}})).app_details(1)
    assert result.outcome is Outcome.NOT_FOUND


async def test_missing_genres_is_ok_with_empty_list():
    body = {"5": {"success": True, "data": {"type": "music", "name": "OST"}}}
    result = await store(httpx.Response(200, json=body)).app_details(5)
    assert result.outcome is Outcome.OK and result.data.genres == []


@pytest.mark.parametrize(
    ("response", "outcome", "reason"),
    [
        (httpx.Response(429), Outcome.RATE_LIMITED, "http_429"),
        (httpx.Response(403), Outcome.RATE_LIMITED, "http_403"),
        (httpx.Response(503), Outcome.ERROR, "http_503"),
        (httpx.Response(200, text="<html>"), Outcome.ERROR, "schema"),
        (httpx.Response(200, json={"999": {"success": True}}), Outcome.ERROR, "schema"),
        (httpx.Response(200, json={"620": {"success": True}}), Outcome.ERROR, "schema"),
        (httpx.Response(200, json=None), Outcome.ERROR, "schema"),
        (httpx.ReadTimeout("slow"), Outcome.ERROR, "timeout"),
        (httpx.ConnectError("down"), Outcome.ERROR, "network:ConnectError"),
    ],
)
async def test_failures_are_classified(response, outcome, reason):
    result = await store(response).app_details(620)
    assert (result.outcome, result.reason) == (outcome, reason)
