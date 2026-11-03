import math

import pytest

from app.taste import affinity, genre_preference


def test_preference_weights_by_log_playtime_and_normalizes():
    pref = genre_preference(
        [(1, 1000), (2, 10), (3, 0)],
        {1: ["RPG", "Action"], 2: ["Action"], 3: ["Puzzle"]},
    )
    a, b = math.log1p(1000), math.log1p(10)
    total = 2 * a + b
    assert pref == pytest.approx({"Action": (a + b) / total, "RPG": a / total})
    assert "Puzzle" not in pref  # 미플레이 게임은 기여하지 않는다
    assert sum(pref.values()) == pytest.approx(1.0)


def test_unknown_genres_and_empty():
    assert genre_preference([(1, 100)], {}) == {}
    assert genre_preference([], {1: ["RPG"]}) == {}


def test_duplicate_genre_counted_once_per_game():
    assert genre_preference([(1, 100)], {1: ["RPG", "RPG"]}) == {"RPG": 1.0}


def test_affinity_sums_matching_weights_and_caps():
    pref = {"RPG": 0.6, "Action": 0.3, "Indie": 0.1}
    assert affinity(pref, ["RPG", "Indie"]) == 0.7
    assert affinity(pref, ["Puzzle"]) == 0.0
    assert affinity({}, ["RPG"]) == 0.0
    assert affinity(pref, ["RPG", "Action", "Indie", "RPG"]) == 1.0
