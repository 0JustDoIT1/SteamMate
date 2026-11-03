"""장르 표시명(한국어). 내부 계산(취향·매칭)은 Steam 영어 장르명으로 일관되게 하고, 응답으로 내보낼 때만 바꾼다.

출처: Steam 상점 appdetails `l=koreana`가 주는 장르명(2026-11-03 수집, 장르 id 기준). 표에 없는 장르는 영어 그대로.
"""

from collections.abc import Iterable

KOREAN_GENRES = {
    "Action": "액션",
    "Indie": "인디",
    "Adventure": "어드벤처",
    "Simulation": "시뮬레이션",
    "RPG": "RPG",
    "Strategy": "전략",
    "Casual": "캐주얼",
    "Free To Play": "무료 플레이",
    "Massively Multiplayer": "대규모 멀티플레이어",
    "Sports": "스포츠",
    "Early Access": "앞서 해보기",
    "Racing": "레이싱",
    "Utilities": "유틸리티",
    "Animation & Modeling": "애니메이션과 모델링",
    "Design & Illustration": "디자인과 일러스트레이션",
    "Video Production": "동영상 제작",
    "Software Training": "소프트웨어 교육",
    "Photo Editing": "사진 편집",
    "Game Development": "게임 개발",
}


def korean_genre(name: str) -> str:
    return KOREAN_GENRES.get(name, name)


def korean_genres(names: Iterable[str]) -> list[str]:
    return [korean_genre(n) for n in names]
