"""내 Steam 프로필(닉네임·프로필 사진) — 위쪽 바 표시용(사용자 요청, 9단계 이후).

Steam 공개 프로필 요약(GetPlayerSummaries)만 쓴다. 저장하지 않고 메모리에 잠시만 둔다(페이지를 옮길 때마다
Steam을 부르지 않게). 사진 주소는 Steam 아바타 CDN의 https 주소만 내보낸다(화면이 그대로 <img>로 쓰므로).
"""

from cachetools import TTLCache

from app.schemas import CamelModel
from app.steam.web_api import SteamWebApi

PROFILE_CACHE_SECONDS = 600
# 아바타 CDN(avatars.steamstatic.com, avatars.akamai.steamstatic.com 등)의 https 주소만 허용
_AVATAR_HOST_SUFFIX = ".steamstatic.com"
_PROFILE_PREFIXES = ("https://steamcommunity.com/",)


class ProfileResponse(CamelModel):
    steam_id: str
    # 공개 닉네임. Steam이 주지 않으면 None(화면은 기본 표시)
    persona_name: str | None
    avatar_url: str | None
    profile_url: str | None


def _safe_avatar(url: str | None) -> str | None:
    if not url or not url.startswith("https://"):
        return None
    host = url.removeprefix("https://").split("/", 1)[0]
    return url if host.endswith(_AVATAR_HOST_SUFFIX) else None


def _safe_profile(url: str | None) -> str | None:
    return url if url and url.startswith(_PROFILE_PREFIXES) else None


class ProfileCache:
    def __init__(self, ttl_seconds: float = PROFILE_CACHE_SECONDS, maxsize: int = 2048) -> None:
        self._cache: TTLCache[str, ProfileResponse] = TTLCache(maxsize=maxsize, ttl=ttl_seconds)

    async def get(self, api: SteamWebApi, steam_id: str) -> ProfileResponse:
        cached = self._cache.get(steam_id)
        if cached is not None:
            return cached
        player = await api.get_player_summary(steam_id)
        profile = ProfileResponse(
            steam_id=steam_id,
            persona_name=(player.personaname.strip() or None) if player else None,
            avatar_url=_safe_avatar(player.avatarmedium) if player else None,
            profile_url=_safe_profile(player.profileurl) if player else None,
        )
        self._cache[steam_id] = profile
        return profile
