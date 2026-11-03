"""차트 소스 응답 fixture. 2026-11-03 실제 응답 구조를 따르되 값은 가공했다."""

TOP_SELLERS = {
    "response": {
        "start_date": 1792454400,
        "ranks": [
            {"rank": 1, "appid": 730, "last_week_rank": 2, "consecutive_weeks": 300,
             "item": {"appid": 730, "name": "Counter-Strike 2", "item_type": 0, "type": 0}},
            {"rank": 2, "appid": 570, "last_week_rank": 1, "consecutive_weeks": 250,
             "item": {"appid": 570, "name": "Dota 2", "item_type": 0, "type": 0}},
            {"rank": 3, "appid": 999001, "consecutive_weeks": 1,
             "item": {"appid": 999001, "name": "New Hit", "item_type": 0, "type": 0}},
        ],
        "next_page_start": 3,
    }
}

MOST_PLAYED = {
    "response": {
        "rollup_date": 1793491200,
        "ranks": [
            {"rank": 1, "appid": 730, "last_week_rank": 1, "peak_in_game": 1288020},
            {"rank": 2, "appid": 440, "last_week_rank": 5, "peak_in_game": 90000},
        ],
    }
}

CONCURRENT = {
    "response": {
        "last_update": 1793500000,
        "ranks": [
            {"rank": 1, "appid": 730, "concurrent_in_game": 900000, "peak_in_game": 1288020},
            {"rank": 2, "appid": 578080, "concurrent_in_game": 300000, "peak_in_game": 500000},
        ],
    }
}


def _featured_item(appid: int, name: str, discount: int, final: int, original: int, type_: int = 0) -> dict:
    return {
        "id": appid, "type": type_, "name": name, "discounted": discount > 0, "discount_percent": discount,
        "original_price": original, "final_price": final, "currency": "KRW",
        "header_image": f"https://example.invalid/{appid}/header.jpg",
        "windows_available": True, "mac_available": False, "linux_available": False,
    }


FEATURED = {
    "0": {"id": "cat_spotlight", "name": "Spotlights", "items": []},
    "specials": {
        "id": "cat_specials",
        "name": "Specials",
        "items": [
            _featured_item(620, "Portal 2", 75, 275000, 1100000),
            _featured_item(620, "Portal 2", 75, 275000, 1100000),  # 중복
            _featured_item(888, "Some Bundle", 50, 100, 200, type_=2),  # 게임 아님
            _featured_item(1091500, "Cyberpunk 2077", 50, 3300000, 6600000),
        ],
    },
    "new_releases": {
        "id": "cat_newreleases",
        "name": "New Releases",
        "items": [_featured_item(999002, "Fresh Game", 0, 1500000, 1500000)],
    },
    "status": 1,
}
