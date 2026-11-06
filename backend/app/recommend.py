"""보유 게임 추천(F3). 점수 계산은 순수 함수라 같은 입력·같은 메타데이터면 같은 결과가 나온다(PRD 재현성).

후보 = 플레이 2시간 미만이면서 게임으로 확인됐거나 아직 종류를 모르는 앱. 장르 수집 중(PLAYTIME_BASED)에는
미플레이 게임끼리 순서를 정할 근거가 없으므로 조금 해 본 게임만 후보로 둔다("이어서 하기"). 점수는 요소별 기여도의 합이고
이유 문구는 요소에서 만든다(LLM 미사용). 가중치는 PRD 점수 설계 초안을 4단계 착수 시 확정한 값(DEVLOG 4단계).
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.genre_labels import korean_genre
from app.library import load_owned_games
from app.metadata.coverage import MetadataCoverage, compute_coverage, snapshot_at
from app.metadata.service import MetadataLookup, MetadataSnapshot, Priority
from app.models import FetchStatus
from app.owned_cache import OwnedGamesCache
from app.schemas import CamelModel
from app.steam.web_api import OwnedGame, SteamWebApi
from app.taste import affinity, genre_preference

CANDIDATE_MAX_MINUTES = 120
RECENTLY_PLAYED_DAYS = 90
TOP_N = 3


class RecommendationMode(StrEnum):
    GENRE_AWARE = "GENRE_AWARE"
    PLAYTIME_BASED = "PLAYTIME_BASED"


class ReasonFactor(StrEnum):
    GENRE_MATCH = "GENRE_MATCH"  # 전체 플레이 기준 취향 장르와 겹침
    UNPLAYED = "UNPLAYED"  # 덜 해본 정도(0분 = 1, 2시간 = 0)
    RECENT_GENRE = "RECENT_GENRE"  # 최근 2주 플레이 장르와 겹침
    RECENTLY_PLAYED = "RECENTLY_PLAYED"  # 최근 90일 안에 실행(이어서 하기)
    POPULAR = "POPULAR"  # 미보유 추천: 대시보드 목록 최고 순위의 역수
    LOW_GENRE_COVERAGE = "LOW_GENRE_COVERAGE"  # 장르 정보 부족 안내(기여 0)


WEIGHTS: dict[RecommendationMode, dict[ReasonFactor, float]] = {
    RecommendationMode.GENRE_AWARE: {
        ReasonFactor.GENRE_MATCH: 0.6, ReasonFactor.UNPLAYED: 0.3, ReasonFactor.RECENT_GENRE: 0.1,
    },
    RecommendationMode.PLAYTIME_BASED: {ReasonFactor.UNPLAYED: 0.7, ReasonFactor.RECENTLY_PLAYED: 0.3},
}


class Reason(CamelModel):
    factor: ReasonFactor
    detail: str | None
    contribution: float


class Recommendation(CamelModel):
    appid: int
    name: str
    score: float
    playtime_forever: int
    last_played_at: datetime | None
    genres: list[str]
    header_image: str | None
    reasons: list[Reason]


class RecommendationsResponse(CamelModel):
    recommendations: list[Recommendation]
    candidate_count: int
    excluded_count: int
    recommendation_mode: RecommendationMode
    metadata_coverage: MetadataCoverage
    metadata_snapshot_at: datetime | None
    calculated_at: datetime


def choose_mode(coverage: MetadataCoverage, threshold: float) -> RecommendationMode:
    return RecommendationMode.GENRE_AWARE if coverage.ratio >= threshold else RecommendationMode.PLAYTIME_BASED


def is_candidate(
    game: OwnedGame,
    meta: MetadataSnapshot | None,
    exclude: frozenset[int],
    mode: RecommendationMode,
) -> bool:
    if game.playtime_forever >= CANDIDATE_MAX_MINUTES or game.appid in exclude:
        return False
    if game.playtime_forever == 0 and mode is RecommendationMode.PLAYTIME_BASED:
        return False
    # 종류를 모르면(메타데이터 수집 전) 후보로 두고, DLC·데모 등 게임이 아닌 것으로 확인되면 뺀다.
    return meta is None or meta.app_type is None or meta.app_type == "game"


def recommend(
    owned: Sequence[OwnedGame],
    snapshots: Mapping[int, MetadataSnapshot],
    *,
    mode: RecommendationMode,
    exclude: frozenset[int],
    coverage_ratio: float,
    now: datetime,
    genre_label: Callable[[str], str] = korean_genre,
    limit: int = TOP_N,
) -> tuple[list[Recommendation], int]:
    """(TOP N 추천, 후보 수). 정렬은 점수 내림차순, 동점은 appid 오름차순."""
    genres_by_appid = {a: s.genres for a, s in snapshots.items() if s.status is FetchStatus.SUCCESS}
    preference = genre_preference(((g.appid, g.playtime_forever) for g in owned), genres_by_appid)
    recent = genre_preference(((g.appid, g.playtime_2weeks or 0) for g in owned), genres_by_appid)
    weights = WEIGHTS[mode]

    candidates = [g for g in owned if is_candidate(g, snapshots.get(g.appid), exclude, mode)]
    scored: list[Recommendation] = []
    for game in candidates:
        genres = genres_by_appid.get(game.appid, ())
        values: dict[ReasonFactor, tuple[float, str | None]] = {
            ReasonFactor.UNPLAYED: (
                1 - game.playtime_forever / CANDIDATE_MAX_MINUTES,
                "미플레이" if game.playtime_forever == 0 else f"{game.playtime_forever}분 플레이",
            ),
        }
        if mode is RecommendationMode.GENRE_AWARE:
            values[ReasonFactor.GENRE_MATCH] = (affinity(preference, genres), _top_genres(preference, genres, genre_label))
            values[ReasonFactor.RECENT_GENRE] = (affinity(recent, genres), _top_genres(recent, genres, genre_label))
        else:
            days = _days_since_played(game, now)
            touched = days is not None and days <= RECENTLY_PLAYED_DAYS
            values[ReasonFactor.RECENTLY_PLAYED] = (1.0 if touched else 0.0, f"{days}일 전 실행" if touched else None)

        reasons = [
            Reason(factor=factor, detail=values[factor][1], contribution=round(weight * values[factor][0], 4))
            for factor, weight in weights.items()
        ]
        reasons = sorted((r for r in reasons if r.contribution > 0), key=lambda r: -r.contribution)
        score = round(sum(r.contribution for r in reasons), 4)
        if mode is RecommendationMode.PLAYTIME_BASED:
            reasons.append(
                Reason(
                    factor=ReasonFactor.LOW_GENRE_COVERAGE,
                    detail=f"내 게임의 장르를 확인하는 중({coverage_ratio:.0%})이라 조금 해 본 게임만 플레이 기록으로 골랐어요",
                    contribution=0.0,
                )
            )
        meta = snapshots.get(game.appid)
        scored.append(
            Recommendation(
                appid=game.appid,
                name=game.name or (meta.name if meta and meta.name else f"App {game.appid}"),
                score=score,
                playtime_forever=game.playtime_forever,
                last_played_at=datetime.fromtimestamp(game.rtime_last_played, UTC) if game.rtime_last_played else None,
                genres=[genre_label(g) for g in genres],
                header_image=meta.header_image if meta else None,
                reasons=reasons,
            )
        )
    scored.sort(key=lambda r: (-r.score, r.appid))
    return scored[:limit], len(candidates)


def _top_genres(
    preference: Mapping[str, float], genres: Iterable[str], label: Callable[[str], str], n: int = 2
) -> str | None:
    matched = sorted((g for g in set(genres) if preference.get(g, 0) > 0), key=lambda g: (-preference[g], g))
    return ", ".join(label(g) for g in matched[:n]) or None


def _days_since_played(game: OwnedGame, now: datetime) -> int | None:
    if not game.rtime_last_played:
        return None
    return max(0, (now - datetime.fromtimestamp(game.rtime_last_played, UTC)) // timedelta(days=1))


async def fetch_recommendations(
    api: SteamWebApi,
    metadata: MetadataLookup,
    owned_cache: OwnedGamesCache,
    steam_id: str,
    *,
    exclude: frozenset[int],
    genre_threshold: float,
) -> RecommendationsResponse:
    owned = await load_owned_games(api, owned_cache, steam_id)
    snapshots = await metadata.lookup((g.appid for g in owned), Priority.HIGH)
    coverage = compute_coverage((g.appid for g in owned), snapshots)
    mode = choose_mode(coverage, genre_threshold)
    now = datetime.now(UTC)
    recommendations, candidate_count = recommend(
        owned,
        snapshots,
        mode=mode,
        exclude=exclude,
        coverage_ratio=coverage.ratio,
        now=now,
    )
    return RecommendationsResponse(
        recommendations=recommendations,
        candidate_count=candidate_count,
        excluded_count=sum(1 for g in owned if g.appid in exclude),
        recommendation_mode=mode,
        metadata_coverage=coverage,
        metadata_snapshot_at=snapshot_at(snapshots.values()),
        calculated_at=now,
    )
