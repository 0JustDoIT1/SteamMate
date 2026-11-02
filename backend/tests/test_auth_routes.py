from urllib.parse import parse_qs, urlparse

import httpx

from tests.conftest import TEST_STEAM_ID
from tests.test_steam_openid import callback_params

RETURN_TO = "http://localhost:3000/api/auth/steam/callback"


async def test_login_redirects_to_steam(client):
    res = await client.get("/auth/steam/login")
    assert res.status_code == 302
    location = urlparse(res.headers["location"])
    assert location.netloc == "steamcommunity.com"
    assert parse_qs(location.query)["openid.return_to"] == [RETURN_TO]


async def test_callback_success_sets_session_cookie(client, steam_handler):
    steam_handler["fn"] = lambda r: httpx.Response(200, text="is_valid:true\n")
    res = await client.get("/auth/steam/callback", params=callback_params(**{"openid.return_to": RETURN_TO}))

    assert res.status_code == 302
    assert res.headers["location"] == "http://localhost:3000/me"
    cookie = res.headers["set-cookie"]
    assert cookie.startswith("sm_session=")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json() == {"steamId": "76561198000000001"}


async def test_callback_failure_redirects_without_cookie(client, steam_handler):
    steam_handler["fn"] = lambda r: httpx.Response(200, text="is_valid:false\n")
    res = await client.get("/auth/steam/callback", params=callback_params(**{"openid.return_to": RETURN_TO}))

    assert res.status_code == 302
    assert res.headers["location"] == "http://localhost:3000/?login=failed&code=AUTH_FAILED"
    assert "set-cookie" not in res.headers


async def test_me_requires_login(client):
    res = await client.get("/auth/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_logout_clears_cookie(client, steam_handler):
    # 서버가 발급한 쿠키로 로그인한 뒤(브라우저와 같은 흐름) 로그아웃한다.
    steam_handler["fn"] = lambda r: httpx.Response(200, text="is_valid:true\n")
    await client.get("/auth/steam/callback", params=callback_params(**{"openid.return_to": RETURN_TO}))
    assert (await client.get("/auth/me")).json() == {"steamId": TEST_STEAM_ID}

    res = await client.post("/auth/logout")

    assert res.status_code == 204
    assert 'sm_session=""' in res.headers["set-cookie"]
    assert (await client.get("/auth/me")).status_code == 401
