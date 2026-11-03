from app.genre_labels import korean_genre, korean_genres


def test_known_genres_use_steam_korean_names():
    assert korean_genres(["Action", "Free To Play", "Early Access", "RPG"]) == ["액션", "무료 플레이", "앞서 해보기", "RPG"]


def test_unknown_genre_falls_back_to_original():
    assert korean_genre("Brand New Genre") == "Brand New Genre"
