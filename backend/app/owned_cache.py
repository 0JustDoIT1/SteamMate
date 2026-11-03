"""보유 게임 목록의 프로세스 메모리 캐시(steamId별 짧은 TTL). DB에는 저장하지 않는다.

라이브러리·대시보드·추천·할인이 같은 목록을 쓰므로 Steam 호출을 줄인다. 실패(비공개 등)는 캐시하지 않는다.
"""

from cachetools import TTLCache

from app.steam.web_api import OwnedGamesBody, SteamWebApi


class OwnedGamesCache:
    def __init__(self, ttl_seconds: float, maxsize: int = 2048) -> None:
        self._cache: TTLCache[str, OwnedGamesBody] = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    async def get(self, api: SteamWebApi, steam_id: str) -> OwnedGamesBody:
        cached = self._cache.get(steam_id)
        if cached is not None:
            return cached
        body = await api.get_owned_games(steam_id)
        if body.games is not None or body.game_count is not None:
            self._cache[steam_id] = body
        return body

    def invalidate(self, steam_id: str) -> None:
        self._cache.pop(steam_id, None)
