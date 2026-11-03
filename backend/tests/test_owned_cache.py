from app.owned_cache import OwnedGamesCache
from app.steam.web_api import OwnedGame, OwnedGamesBody


class CountingApi:
    def __init__(self, body: OwnedGamesBody) -> None:
        self.body = body
        self.calls = 0

    async def get_owned_games(self, steam_id: str) -> OwnedGamesBody:
        self.calls += 1
        return self.body


PUBLIC = OwnedGamesBody(game_count=1, games=[OwnedGame(appid=620)])


async def test_caches_public_library_per_steam_id():
    api = CountingApi(PUBLIC)
    cache = OwnedGamesCache(ttl_seconds=60)
    await cache.get(api, "a")
    await cache.get(api, "a")
    assert api.calls == 1
    await cache.get(api, "b")
    assert api.calls == 2


async def test_private_response_is_not_cached():
    api = CountingApi(OwnedGamesBody())
    cache = OwnedGamesCache(ttl_seconds=60)
    await cache.get(api, "a")
    await cache.get(api, "a")
    assert api.calls == 2  # 공개로 바꾸면 바로 반영되도록


async def test_expired_entry_refetches():
    api = CountingApi(PUBLIC)
    cache = OwnedGamesCache(ttl_seconds=0)
    await cache.get(api, "a")
    await cache.get(api, "a")
    assert api.calls == 2


async def test_invalidate():
    api = CountingApi(PUBLIC)
    cache = OwnedGamesCache(ttl_seconds=60)
    await cache.get(api, "a")
    cache.invalidate("a")
    await cache.get(api, "a")
    assert api.calls == 2
