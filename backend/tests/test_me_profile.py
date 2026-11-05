"""내 Steam 프로필(위쪽 바): 닉네임·사진, 안전한 주소만, 메모리 캐시, 로그인 필요."""

from tests.conftest import TEST_STEAM_ID
from tests.test_me_library import SUMMARIES, routes


def summary(**fields) -> dict:
    return {"response": {"players": [{"steamid": TEST_STEAM_ID, "communityvisibilitystate": 3, **fields}]}}


async def test_requires_login(client):
    assert (await client.get("/me/profile")).status_code == 401


async def test_profile_and_cache(client, login, steam_handler):
    handler = routes(**{SUMMARIES: summary(
        personaname="  Geralt  ",
        avatarmedium="https://avatars.steamstatic.com/abc_medium.jpg",
        profileurl="https://steamcommunity.com/id/geralt/",
    )})
    steam_handler["fn"] = handler
    login()

    body = (await client.get("/me/profile")).json()
    assert body == {"steamId": TEST_STEAM_ID, "personaName": "Geralt",
                    "avatarUrl": "https://avatars.steamstatic.com/abc_medium.jpg",
                    "profileUrl": "https://steamcommunity.com/id/geralt/"}
    await client.get("/me/profile")
    assert len(handler.calls) == 1  # 페이지를 옮길 때마다 Steam을 부르지 않는다


async def test_unsafe_urls_and_missing_player(client, login, steam_handler):
    steam_handler["fn"] = routes(**{SUMMARIES: summary(
        personaname="", avatarmedium="http://evil.example/a.jpg", profileurl="javascript:alert(1)")})
    login()
    body = (await client.get("/me/profile")).json()
    assert body["personaName"] is None and body["avatarUrl"] is None and body["profileUrl"] is None

    steam_handler["fn"] = routes(**{SUMMARIES: {"response": {"players": []}}})
    login("76561198000000009")
    body = (await client.get("/me/profile")).json()
    assert body["steamId"] == "76561198000000009" and body["personaName"] is None
