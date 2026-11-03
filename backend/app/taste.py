"""장르 취향(순수 함수). 대시보드 매칭도와 4단계 추천이 같은 정의를 쓴다.

PRD 점수 설계: 장르별 Σ log1p(playtime_min), 합 1로 정규화.
"""

import math
from collections.abc import Iterable, Mapping


def genre_preference(playtimes: Iterable[tuple[int, int]], genres_by_appid: Mapping[int, Iterable[str]]) -> dict[str, float]:
    """(appid, 플레이시간 분) 목록 → {장르: 가중치}. 장르를 모르는 게임과 미플레이 게임은 기여하지 않는다."""
    weights: dict[str, float] = {}
    for appid, minutes in playtimes:
        if minutes <= 0:
            continue
        w = math.log1p(minutes)
        for genre in set(genres_by_appid.get(appid, ())):
            weights[genre] = weights.get(genre, 0.0) + w
    total = sum(weights.values())
    return {g: w / total for g, w in sorted(weights.items())} if total else {}


def affinity(preference: Mapping[str, float], game_genres: Iterable[str]) -> float:
    """게임 장르에 해당하는 취향 가중치의 합(0~1). 취향 정보가 없으면 0."""
    return round(min(1.0, sum(preference.get(g, 0.0) for g in set(game_genres))), 4)
