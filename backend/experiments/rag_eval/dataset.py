"""7단계 Full Context vs RAG 실험용 합성 패치노트·질문 (고정 seed, 실험용 합성 데이터).

가상 게임 "Ashen Frontier"의 뉴스 목록을 만든다.
- 핵심 문서(C1~C5): 질문의 정답 근거. 사실은 CHANGES에 손으로 고정하고 모든 길이 구간에 들어간다.
- 방해 문서: seed로 생성. 길이 구간이 커질수록 같은 순서로 앞에서부터 더한다(중첩형: 2k ⊂ 8k ⊂ 32k ⊂ 100k).
  방해 문서는 핵심 문서의 대상 이름·버전을 쓰지 않고 비슷한 이름(Phantom Lance 등)만 쓴다
  → 어느 길이에서도 정답이 같고, 바뀌는 변수는 입력 길이뿐이다.
원문은 BBCode/HTML/평문으로 만들고 서비스와 같은 clean_news로 정제한 결과를 실험 입력으로 쓴다.
문서 ID는 날짜순 N001… 로 붙여 핵심 문서인지 드러나지 않게 한다.
"""

import html
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from app.news_cleaner import clean_news

SEED = 20261104
GAME = "Ashen Frontier"
TARGETS = {"2k": 2_000, "8k": 8_000, "32k": 32_000, "100k": 100_000}
FILLER_POOL = 150  # 100k를 채우고 남을 만큼. 실제 사용 수는 토큰 측정 후 정해진다.


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    date: str  # YYYY-MM-DD
    lang: str  # en | ko
    fmt: str  # bbcode | html | text (정제 전 원문 형식)
    text: str  # clean_news 결과
    core: bool


@dataclass(frozen=True)
class Question:
    id: str
    kind: str  # single | latest | multi | title | unanswerable
    text: str
    # 필요한 항목마다 허용 표기 묶음. 모든 항목이 답에 있어야 정답. 답 없음 질문은 빈 튜플.
    answer: tuple[tuple[str, ...], ...]
    evidence: tuple[str, ...]  # 핵심 문서 키(C1~C5). 데이터셋에는 문서 ID로 바꿔 저장한다.
    fact: tuple[str, str] | None = None  # (대상, 속성) — 테스트가 CHANGES로 정답을 다시 계산할 때 사용


# ---------------------------------------------------------------- 공통 렌더링

UNITS = {"cooldown": " seconds", "duration": " seconds", "draw time": " ms",
         "reload time": " seconds", "fire rate": " RPM", "range": " m"}
KO_UNITS = {"cooldown": "초", "duration": "초", "draw time": "ms",
            "reload time": "초", "fire rate": "RPM", "range": "m"}
KO_ATTR = {"damage": "피해량", "cooldown": "재사용 대기시간", "magazine size": "탄창 크기",
           "draw time": "시위 당김 시간", "max players": "최대 인원", "duration": "지속 시간",
           "reload time": "재장전 시간", "fire rate": "연사 속도", "range": "사거리", "spread": "탄 퍼짐"}

Section = tuple[str, list[str]]


def change_line(lang: str, entity: str, attr: str, old: object, new: object) -> str:
    if lang == "ko":
        u = KO_UNITS.get(attr, "")
        return f"{entity} {KO_ATTR[attr]}: {old}{u} → {new}{u}"
    u = UNITS.get(attr, "")
    return f"{entity}: {attr} changed from {old}{u} to {new}{u}."


def render_raw(fmt: str, intro: list[str], sections: list[Section], outro: list[str], image: bool) -> str:
    if fmt == "bbcode":
        parts = ["[img]{STEAM_CLAN_IMAGE}/2914610/banner.png[/img]"] if image else []
        parts += [f"[p]{p}[/p]" for p in intro]
        for head, items in sections:
            parts.append(f"[h3]{head}[/h3]")
            parts.append("[list]\n" + "\n".join(f"[*]{i}" for i in items) + "\n[/list]")
        parts += [f"[p]{p}[/p]" for p in outro]
        return "\n".join(parts)
    if fmt == "html":
        e = html.escape
        parts = ['<img src="https://cdn.example.invalid/banner.jpg"/>'] if image else []
        parts += [f"<p>{e(p)}</p>" for p in intro]
        for head, items in sections:
            parts.append(f"<h3>{e(head)}</h3><ul>" + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>")
        parts += [f"<p>{e(p)}</p>" for p in outro]
        return "".join(parts)
    parts = list(intro)
    for head, items in sections:
        parts.append(head + "\n" + "\n".join(f"- {i}" for i in items))
    parts += outro
    return "\n\n".join(parts)


def render_doc(doc: Doc) -> str:
    return f"[{doc.id}] {doc.title} ({doc.date})\n{doc.text}"


def render_corpus(docs: list[Doc]) -> str:
    """실험 입력 형식. Steam 뉴스처럼 최신 글이 먼저."""
    ordered = sorted(docs, key=lambda d: d.date, reverse=True)
    return "\n\n---\n\n".join(render_doc(d) for d in ordered)


# ---------------------------------------------------------------- 핵심 문서 (정답 근거)

# (문서, 대상, 속성, 이전 값, 새 값). 질문 정답은 모두 여기서 나온다.
CHANGES: list[tuple[str, str, str, int, int]] = [
    ("C1", "Arc Lance", "damage", 42, 48),
    ("C1", "Void Pistol", "magazine size", 12, 10),
    ("C1", "Ember Bow", "draw time", 900, 750),
    ("C1", "Frost Hammer", "damage", 85, 80),
    ("C1", "Phantom Glaive", "cooldown", 14, 18),
    ("C1", "Siege", "max players", 10, 12),
    ("C2", "Arc Lance", "damage", 48, 46),
    ("C2", "Void Pistol", "magazine size", 10, 11),
    ("C3", "Phantom Glaive", "cooldown", 18, 22),
    ("C3", "Frost Hammer", "damage", 80, 88),
    ("C4", "Tide Caller", "damage", 55, 50),
    ("C4", "Ember Bow", "draw time", 750, 800),
    ("C4", "Phantom Glaive", "cooldown", 22, 20),
    ("C4", "Siege", "max players", 12, 10),
    ("C5", "Arc Lance", "damage", 46, 50),
    ("C5", "Void Pistol", "magazine size", 11, 13),
]
CORE_VERSIONS = {"C1": (2, 3, 0), "C2": (2, 3, 0), "C3": (2, 4, 0), "C4": (2, 4, 1), "C5": (2, 5, 0)}
CORE_ENTITIES = ["Arc Lance", "Void Pistol", "Ember Bow", "Frost Hammer", "Phantom Glaive", "Tide Caller",
                 "Siege", "Glass Canyon", "Echo Station", "Relic Hunt", "수확 축제"]
ABSENT_ENTITIES = ["Phantom Scythe"]  # 답 없음 질문용. 어느 문서에도 나오지 않아야 한다.


def _chg(key: str, entity: str, lang: str = "en") -> str:
    ((_, e, attr, old, new),) = [c for c in CHANGES if c[0] == key and c[1] == entity]
    return change_line(lang, e, attr, old, new)


def _core_specs() -> dict[str, dict]:
    return {
        "C1": {
            "title": "Patch 2.3.0 Notes", "date": "2025-09-02", "lang": "en", "fmt": "bbcode", "image": True,
            "intro": [("Patch 2.3.0 is live! This update focuses on weapon balance, the Ranked map rotation and "
                   "Siege lobbies. Servers were down for about 40 minutes during deployment.")],
            "sections": [
                ("WEAPONS", [_chg("C1", "Arc Lance"), _chg("C1", "Void Pistol"), _chg("C1", "Ember Bow"),
                             _chg("C1", "Frost Hammer")]),
                ("ABILITIES", [_chg("C1", "Phantom Glaive")]),
                ("RANKED MAP ROTATION", ["Glass Canyon has been added to the Ranked rotation.",
                                         ("Echo Station has been removed from the Ranked rotation while the map "
                                         "is reworked.")]),
                ("MODES", [_chg("C1", "Siege")]),
                ("BUG FIXES", ["Fixed an issue where Ember Bow arrows could pass through closed doors.",
                               "Fixed a crash when joining a Siege lobby from the friends list.",
                               "Fixed the scoreboard showing the wrong team colors after a reconnect.",
                               "Fixed missing footstep sounds on metal stairs."]),
            ],
            "outro": [f"Thank you for playing {GAME}. See you on the frontier!"],
        },
        "C2": {
            "title": "Patch 2.3.0 Hotfix", "date": "2025-09-05", "lang": "en", "fmt": "bbcode", "image": False,
            "intro": ["This hotfix follows up on Patch 2.3.0 after a weekend of feedback."],
            "sections": [
                ("WEAPONS", [_chg("C2", "Arc Lance"), _chg("C2", "Void Pistol")]),
                ("BUG FIXES", ["Fixed a spawn exploit in Glass Canyon near the north bridge.",
                               "Fixed Ranked matchmaking occasionally placing a full party on opposite teams.",
                               "Fixed a rare crash when opening the armory."]),
            ],
            "outro": [],
        },
        "C3": {
            "title": "2.4.0 업데이트 안내", "date": "2025-10-14", "lang": "ko", "fmt": "bbcode", "image": True,
            "intro": [(f"안녕하세요, {GAME} 개발팀입니다. 2.4.0 업데이트가 적용되었습니다. "
                   "이번 업데이트에서는 신규 무기와 시즌 이벤트가 추가됩니다.")],
            "sections": [
                ("신규 콘텐츠", ["신규 무기 Tide Caller가 추가됩니다. 출시 피해량은 55입니다.",
                                "Echo Station 개편이 완료되어 랭크 로테이션에 다시 추가됩니다."]),
                ("밸런스 조정", [_chg("C3", "Phantom Glaive", "ko"), _chg("C3", "Frost Hammer", "ko")]),
                ("이벤트", ["수확 축제 이벤트가 2025년 10월 20일부터 2025년 11월 3일까지 진행됩니다.",
                           "이벤트 기간 동안 일일 미션 보상이 두 배로 지급됩니다."]),
                ("버그 수정", ["일부 상황에서 관전 화면이 멈추는 문제를 수정했습니다.",
                              "한국어 자막이 일부 컷신에서 표시되지 않던 문제를 수정했습니다."]),
            ],
            "outro": ["앞으로도 많은 관심 부탁드립니다."],
        },
        "C4": {
            "title": "Patch 2.4.1 Notes", "date": "2025-11-04", "lang": "en", "fmt": "html", "image": False,
            "intro": ["Patch 2.4.1 adjusts the new weapon and reverts an unpopular Siege change."],
            "sections": [
                ("WEAPONS", [_chg("C4", "Tide Caller"), _chg("C4", "Ember Bow")]),
                ("ABILITIES", [_chg("C4", "Phantom Glaive")]),
                ("MODES", [_chg("C4", "Siege") + " Siege lobbies return to 5v5."]),
                ("KNOWN ISSUES", ["Echo Station: lighting may flicker in the underground tunnels on some GPUs."]),
                ("BUG FIXES", ["Fixed the Tide Caller reload animation playing out of sync.",
                               "Fixed an issue where the daily mission timer reset late."]),
            ],
            "outro": [],
        },
        "C5": {
            "title": "Patch 2.5.0 Notes", "date": "2025-12-09", "lang": "en", "fmt": "text", "image": False,
            "intro": ["Patch 2.5.0 introduces a new mode and another round of weapon tuning."],
            "sections": [
                ("NEW MODE", [("Relic Hunt: a new objective mode where two teams race to recover relics. "
                              "Available in Casual playlists.")]),
                ("WEAPONS", [_chg("C5", "Arc Lance"), _chg("C5", "Void Pistol")]),
                ("RANKED MAP ROTATION", [("Glass Canyon has been removed from the Ranked rotation. "
                                         "It remains available in Casual.")]),
                ("BUG FIXES", ["Fixed bots getting stuck on ladders.",
                               "Fixed the armory preview camera clipping into walls."]),
            ],
            "outro": [],
        },
    }


# ---------------------------------------------------------------- 질문 (한국어)

def _a(*items: str) -> tuple[tuple[str, ...], ...]:
    """허용 표기가 하나뿐인 항목들."""
    return tuple((i,) for i in items)


QUESTIONS: list[Question] = [
    # 단일 사실
    Question("Q01", "single", "2.3.0 패치에서 Ember Bow의 시위 당김 시간은 몇 ms로 바뀌었나요?", _a("750"), ("C1",)),
    Question("Q02", "single", "Tide Caller는 몇 버전에서 추가되었나요?", _a("2.4.0"), ("C3",)),
    Question("Q03", "single", "2.4.0의 수확 축제 이벤트는 언제 끝나나요?",
             (("11월 3일", "2025-11-03", "11/3", "November 3"),), ("C3",)),
    Question("Q04", "single", "2.3.0 핫픽스에서 고친 Glass Canyon 스폰 악용 문제는 어느 위치 근처였나요?",
             (("north bridge", "북쪽 다리"),), ("C2",)),
    Question("Q05", "single", "2.4.1 패치노트의 알려진 문제에서 Echo Station에는 어떤 문제가 있나요?",
             (("flicker", "깜빡"),), ("C4",)),
    Question("Q06", "single", "2.5.0에서 추가된 새 모드의 이름은 무엇인가요?", _a("Relic Hunt"), ("C5",)),
    Question("Q07", "single", "2.3.0 패치에서 Frost Hammer의 피해량은 얼마로 바뀌었나요?", _a("80"), ("C1",)),
    Question("Q08", "single", "Tide Caller의 출시 당시 피해량은 얼마였나요?", _a("55"), ("C3",)),
    Question("Q09", "single", "2.4.0에서 랭크 로테이션에 다시 추가된 맵은 무엇인가요?", _a("Echo Station"), ("C3",)),
    Question("Q10", "single", "2.3.0에서 랭크 로테이션에 새로 추가된 맵은 무엇인가요?", _a("Glass Canyon"), ("C1",)),
    Question("Q11", "single", "2.3.0 패치에서 Siege 모드의 최대 인원은 몇 명으로 바뀌었나요?", _a("12"), ("C1",)),
    Question("Q12", "single", "2.4.1 패치에서 Tide Caller의 피해량은 얼마로 바뀌었나요?", _a("50"), ("C4",)),
    # 버전 충돌: 여러 번 바뀐 값의 최신 값
    Question("Q13", "latest", "최신 패치 기준 Phantom Glaive의 재사용 대기시간은 몇 초인가요?", _a("20"), ("C4",),
             ("Phantom Glaive", "cooldown")),
    Question("Q14", "latest", "최신 패치 기준 Arc Lance의 피해량은 얼마인가요?", _a("50"), ("C5",),
             ("Arc Lance", "damage")),
    Question("Q15", "latest", "최신 패치 기준 Void Pistol의 탄창 크기는 얼마인가요?", _a("13"), ("C5",),
             ("Void Pistol", "magazine size")),
    Question("Q16", "latest", "최신 패치 기준 Ember Bow의 시위 당김 시간은 몇 ms인가요?", _a("800"), ("C4",),
             ("Ember Bow", "draw time")),
    Question("Q17", "latest", "최신 패치 기준 Frost Hammer의 피해량은 얼마인가요?", _a("88"), ("C3",),
             ("Frost Hammer", "damage")),
    Question("Q18", "latest", "최신 패치 기준 Siege 모드의 최대 인원은 몇 명인가요?", _a("10"), ("C4",),
             ("Siege", "max players")),
    Question("Q19", "latest", "Glass Canyon이 랭크 로테이션에서 제외된 버전은 무엇인가요?", _a("2.5.0"), ("C5",)),
    Question("Q20", "latest", "최신 패치 기준 Tide Caller의 피해량은 얼마인가요?", _a("50"), ("C4",),
             ("Tide Caller", "damage")),
    # 여러 문서 근거
    Question("Q21", "multi", "Phantom Glaive의 재사용 대기시간이 바뀐 버전을 모두 쓰세요.",
             _a("2.3.0", "2.4.0", "2.4.1"), ("C1", "C3", "C4"), ("Phantom Glaive", "cooldown")),
    Question("Q22", "multi", "Arc Lance의 피해량은 2.3.0 패치 이전 값에서 최신 패치까지 모두 몇 번 바뀌었나요?",
             _a("3"), ("C1", "C2", "C5"), ("Arc Lance", "damage")),
    Question("Q23", "multi", "Void Pistol의 탄창 크기는 2.3.0 패치 이전보다 최신 패치에서 얼마나 늘었나요?",
             _a("1"), ("C1", "C5"), ("Void Pistol", "magazine size")),
    Question("Q24", "multi", "Echo Station이 랭크 로테이션에서 빠진 버전과 다시 들어온 버전은 각각 무엇인가요?",
             _a("2.3.0", "2.4.0"), ("C1", "C3")),
    Question("Q25", "multi", "Ember Bow의 시위 당김 시간이 바뀐 버전을 모두 쓰세요.",
             _a("2.3.0", "2.4.1"), ("C1", "C4"), ("Ember Bow", "draw time")),
    Question("Q26", "multi", "Frost Hammer의 피해량은 2.3.0 패치 이전보다 최신 패치에서 얼마나 늘었나요?",
             _a("3"), ("C1", "C3"), ("Frost Hammer", "damage")),
    Question("Q27", "multi", "Siege 모드의 최대 인원이 바뀐 버전을 모두 쓰세요.",
             _a("2.3.0", "2.4.1"), ("C1", "C4"), ("Siege", "max players")),
    Question("Q28", "multi", "Tide Caller의 피해량은 출시 당시보다 최신 패치에서 얼마나 줄었나요?",
             _a("5"), ("C3", "C4"), ("Tide Caller", "damage")),
    # 비슷한 제목 구분: 같은 버전의 정규 패치노트와 핫픽스
    Question("Q29", "title", "'Patch 2.3.0 Hotfix'에서 Void Pistol의 탄창 크기는 얼마로 바뀌었나요?", _a("11"), ("C2",)),
    Question("Q30", "title", "핫픽스가 아닌 'Patch 2.3.0 Notes'에서 Arc Lance의 피해량은 얼마로 바뀌었나요?",
             _a("48"), ("C1",)),
    Question("Q31", "title", "2.3.0 핫픽스에서 Arc Lance의 피해량은 얼마로 바뀌었나요?", _a("46"), ("C2",)),
    Question("Q32", "title", "핫픽스가 아닌 2.3.0 정규 패치노트에서 Void Pistol의 탄창 크기는 얼마로 바뀌었나요?",
             _a("10"), ("C1",)),
    # 답 없음: 근거가 없으므로 답을 거절해야 한다
    Question("Q33", "unanswerable", "Phantom Scythe의 재사용 대기시간은 몇 초인가요?", (), ()),
    Question("Q34", "unanswerable", "2.4.0 업데이트에서 Void Pistol의 탄창 크기는 얼마로 바뀌었나요?", (), ()),
    Question("Q35", "unanswerable", "Relic Hunt 모드의 최대 인원은 몇 명인가요?", (), ()),
    Question("Q36", "unanswerable", "Arc Lance의 사거리는 몇 m인가요?", (), ()),
]


# ---------------------------------------------------------------- 방해 문서 (seed 생성)

# 핵심 대상과 비슷하지만 겹치지 않는 이름. 핵심 이름을 부분 문자열로 포함하면 안 된다(테스트로 확인).
F_WEAPONS = ["Phantom Lance", "Arc Rifle", "Void Carbine", "Ember Crossbow", "Frost Maul", "Tide Breaker",
             "Storm Blade", "Iron Repeater", "Rust Shotgun", "Nova Launcher", "Shard Dagger", "Ash Revolver"]
F_ABILITIES = ["Phantom Step", "Arc Shield", "Blink Dash", "Smoke Veil", "Ember Burst", "Frost Ward"]
F_MAPS = ["Glass Delta", "Echo Ridge", "Dust Harbor", "Red Orchard", "Salt Flats", "Ironworks",
          "Sunken Vault", "Cinder Pass"]
F_MODES = ["Outpost", "Deathmatch", "Convoy", "Relic Run", "Free for All"]
F_EVENTS = ["Frost Week", "Lunar Clash", "Founders' Weekend", "Spring Skirmish", "Night Ops"]
F_EVENTS_KO = ["겨울 축제", "설날 이벤트", "창립 기념 주간", "봄맞이 대전", "심야 작전"]
W_ATTRS = ["damage", "magazine size", "reload time", "fire rate", "range", "spread"]
A_ATTRS = ["cooldown", "duration"]
SPOTS = ["bridge", "tower", "gate", "ridge", "warehouse", "bunker", "rooftop", "tunnel"]
UI = ["shop", "loadout screen", "tooltip", "replay viewer", "armory"]
ACTIONS = ["leaving a match during the end screen", "changing graphics presets in a match",
           "opening the battle pass tab", "inviting a friend from the main menu", "spectating a teammate"]
TOPICS = ["matchmaking", "the ranked ladder", "weapon recoil", "the armory", "daily missions", "the battle pass",
          "spectator mode", "anti-cheat", "server tick rate", "new player onboarding", "cosmetic drops",
          "voice chat"]
TOPICS_KO = ["매치메이킹", "랭크 시스템", "무기 반동", "무기고", "일일 미션", "배틀 패스", "관전 모드", "부정행위 방지",
             "서버 성능", "신규 플레이어 안내", "치장 아이템", "음성 채팅"]
EN_SENTENCES = [
    "We have been reading your feedback on {topic} and want to share where things are heading.",
    "Our goal for this season is to make {topic} feel more rewarding without slowing down matches.",
    "A big thank you to everyone who joined the test sessions last week.",
    "Some of these changes are experimental, and we will keep a close eye on the data.",
    "If you run into problems, please report them through the in-game feedback tool.",
    "{topic} has been one of the most discussed topics in the community this month.",
    "We know the last few weeks have been rough for players on older hardware.",
    "Expect a follow-up post once we have more numbers to share.",
    "The team spent most of this sprint on stability and server performance.",
    "Matches on {map} were ending too quickly, so we are adjusting spawn timings.",
    "Players who logged in during the outage will receive a small compensation package.",
    "Our community managers will host a Q&A on the official forums on Friday.",
    "Balance is never finished, and this update is one more step rather than the final word.",
    "We are also working on a larger rework of {topic}, which we hope to show soon.",
    "The {weapon} has been overperforming in high-level play, and we are watching it closely.",
    "Several of you asked for more control over {topic}, and that request is now on our roadmap.",
]
KO_SENTENCES = [
    "{topic}에 대한 여러분의 의견을 꼼꼼히 읽고 있습니다.",
    "이번 시즌의 목표는 경기 속도를 해치지 않으면서 {topic}을 더 보람 있게 만드는 것입니다.",
    "지난주 테스트에 참여해 주신 모든 분께 감사드립니다.",
    "일부 변경 사항은 실험적이며 데이터를 보며 계속 조정할 예정입니다.",
    "문제가 발생하면 게임 내 의견 보내기 기능으로 알려 주세요.",
    "{map}에서 경기가 너무 빨리 끝나 부활 시간을 조정합니다.",
    "점검 중 접속하지 못한 분들께는 소정의 보상이 지급됩니다.",
    "{weapon}의 성능이 높은 구간에서 지나치게 강해 지켜보고 있습니다.",
    "더 많은 수치가 모이면 후속 공지로 다시 안내드리겠습니다.",
    "{topic} 개편도 준비 중이며 곧 소개해 드릴 수 있기를 바랍니다.",
]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


class _Gen:
    def __init__(self, rng: random.Random, lang: str):
        self.r = rng
        self.ko = lang == "ko"

    def sentence(self) -> str:
        t = self.r.choice(KO_SENTENCES if self.ko else EN_SENTENCES)
        return t.format(topic=self.r.choice(TOPICS_KO if self.ko else TOPICS), map=self.r.choice(F_MAPS),
                        weapon=self.r.choice(F_WEAPONS))

    def paragraph(self) -> str:
        return " ".join(self.sentence() for _ in range(self.r.randint(3, 5)))

    def _value(self, attr: str) -> tuple[str, str]:
        r = self.r
        if attr == "reload time":
            return f"{r.randint(12, 40) / 10:.1f}", f"{r.randint(12, 40) / 10:.1f}"
        if attr == "fire rate":
            return str(r.randrange(300, 900, 10)), str(r.randrange(300, 900, 10))
        return str(r.randint(5, 95)), str(r.randint(5, 95))

    def weapon_line(self) -> str:
        attr = self.r.choice(W_ATTRS)
        return change_line("ko" if self.ko else "en", self.r.choice(F_WEAPONS), attr, *self._value(attr))

    def ability_line(self) -> str:
        attr = self.r.choice(A_ATTRS)
        return change_line("ko" if self.ko else "en", self.r.choice(F_ABILITIES), attr, *self._value(attr))

    def map_line(self) -> str:
        m, s = self.r.choice(F_MAPS), self.r.choice(SPOTS)
        if self.ko:
            return self.r.choice([f"{m}: {s} 근처 조명을 조정했습니다.", f"{m}: {s} 근처에 엄폐물을 추가했습니다.",
                                  f"{m}: {s} 근처에서 끼이는 지점을 수정했습니다."])
        return self.r.choice([f"{m}: adjusted lighting near the {s}.", f"{m}: added cover near the {s}.",
                              f"{m}: removed an unintended sniper spot on the {s}.",
                              f"{m}: fixed a spot where players could get stuck near the {s}."])

    def mode_line(self) -> str:
        m, a, b = self.r.choice(F_MODES), self.r.randint(3, 12) * 30, self.r.randint(3, 12) * 30
        if self.ko:
            return f"{m}: 라운드 시간 {a}초 → {b}초"
        return self.r.choice([f"{m}: round time changed from {a} to {b} seconds.",
                              f"{m}: score limit changed from {a // 3} to {b // 3}."])

    def bugfix_line(self) -> str:
        r = self.r
        w, ab, m = r.choice(F_WEAPONS), r.choice(F_ABILITIES), r.choice(F_MAPS)
        if self.ko:
            return r.choice([f"{w}의 수치가 {r.choice(['상점', '무기고', '툴팁'])}에서 잘못 표시되던 문제를 수정했습니다.",
                             f"{m}의 {r.choice(SPOTS)} 근처에서 플레이어가 끼이던 문제를 수정했습니다.",
                             f"부활 직후 {ab}가 발동하지 않던 문제를 수정했습니다.",
                             "경기 종료 화면에서 나갈 때 발생하던 충돌을 수정했습니다."])
        return r.choice([(f"Fixed an issue where the {w} {r.choice(W_ATTRS)} was displayed incorrectly in the "
                         f"{r.choice(UI)}."),
                         f"Fixed a crash that could occur when {r.choice(ACTIONS)}.",
                         f"Fixed players getting stuck near the {r.choice(SPOTS)} on {m}.",
                         f"Fixed {ab} not triggering when used immediately after respawning.",
                         f"Fixed missing sound effects for the {w} in replays."])

    def known_issue_line(self) -> str:
        if self.ko:
            return f"{self.r.choice(F_MAPS)}: 첫 실행 시 일부 텍스처가 늦게 불러와질 수 있습니다."
        return self.r.choice([f"{self.r.choice(F_MAPS)}: some textures may load slowly on first launch.",
                              f"{self.r.choice(F_WEAPONS)}: the inspect animation can play twice."])

    def lines(self, fn: Callable[[], str], lo: int, hi: int) -> list[str]:
        return [fn() for _ in range(self.r.randint(lo, hi))]

    def heads(self) -> dict[str, str]:
        if self.ko:
            return {"w": "무기", "a": "능력", "m": "맵", "mo": "모드", "b": "버그 수정", "k": "알려진 문제"}
        return {"w": "WEAPONS", "a": "ABILITIES", "m": "MAPS", "mo": "MODES", "b": "BUG FIXES",
                "k": "KNOWN ISSUES"}

    def patch(self, kind: str) -> tuple[list[str], list[Section], list[str]]:
        h = self.heads()
        if kind == "hotfix":
            return [self.sentence()], [(h["w"], self.lines(self.weapon_line, 1, 3)),
                                       (h["b"], self.lines(self.bugfix_line, 2, 5))], []
        if kind == "patch":
            return [self.paragraph()], [
                (h["w"], self.lines(self.weapon_line, 15, 30)), (h["a"], self.lines(self.ability_line, 4, 8)),
                (h["m"], self.lines(self.map_line, 4, 10)), (h["mo"], self.lines(self.mode_line, 2, 4)),
                (h["b"], self.lines(self.bugfix_line, 15, 30)), (h["k"], self.lines(self.known_issue_line, 2, 4)),
            ], [self.sentence()]
        # major
        return [self.paragraph() for _ in range(self.r.randint(4, 8))], [
            (h["w"], self.lines(self.weapon_line, 40, 70)), (h["a"], self.lines(self.ability_line, 10, 18)),
            (h["m"], self.lines(self.map_line, 12, 20)), (h["mo"], self.lines(self.mode_line, 4, 8)),
            (h["b"], self.lines(self.bugfix_line, 40, 70)), (h["k"], self.lines(self.known_issue_line, 4, 8)),
        ], [self.paragraph()]

    def post(self, day: date) -> tuple[str, list[str], list[Section], list[str]]:
        r = self.r
        kind = r.choice(["event", "dev", "issues"])
        paras = [self.paragraph() for _ in range(r.randint(6, 12))]
        if kind == "event":
            end = day + timedelta(days=r.randint(5, 14))
            if self.ko:
                name = r.choice(F_EVENTS_KO)
                return (f"{name} 안내", paras[:5], [("보상", [f"{r.randint(2, 6)}일 접속 보상: 치장 아이템 상자",
                                                           f"{name} 기간 동안 경험치 {r.randint(2, 3)}배"])],
                        [f"이벤트는 {end.month}월 {end.day}일까지 진행됩니다."])
            name = r.choice(F_EVENTS)
            return (f"Community Event: {name}", paras[:5],
                    [("REWARDS", [f"Log in for {r.randint(2, 6)} days to earn a cosmetic crate.",
                                  f"Earn {r.randint(2, 3)}x XP during {name}."])],
                    [f"The event runs until {MONTHS[end.month - 1]} {end.day}."])
        if kind == "issues":
            title = "알려진 문제 안내" if self.ko else f"Known Issues — {MONTHS[day.month - 1]} {day.year}"
            return title, paras[:3], [(self.heads()["k"], self.lines(self.known_issue_line, 8, 14))], []
        title = "개발자 노트" if self.ko else f"Developer Update: {r.choice(TOPICS).capitalize()}"
        return title, paras, [], []


def _bump(cur: tuple[int, int, int], kind: str) -> tuple[int, int, int]:
    ma, mi, pa = cur
    if kind == "major":
        return (ma + 1, 0, 0) if mi >= 9 else (ma, mi + 1, 0)
    return (ma, mi, pa + 1)


def _filler_version(cur, kind, limit) -> tuple[tuple[int, int, int] | None, str]:
    """다음 핵심 버전(limit)을 넘지 않는 버전. 끝자리는 9까지(2.4.10이 '2.4.1'을 포함하지 않게)."""
    for k in ([kind, "patch"] if kind == "major" else [kind]):
        cand = _bump(cur, k)
        if cand[2] <= 9 and (limit is None or cand < limit):
            return cand, k
    return None, "post"  # 넣을 버전이 없으면 버전 없는 공지로 바꾼다


def _make_doc(doc_id: str, title: str, day: str, lang: str, fmt: str, raw: str, core: bool) -> Doc:
    return Doc(doc_id, title, day, lang, fmt, clean_news(raw), core)


@dataclass(frozen=True)
class Docs:
    docs: list[Doc]  # 날짜순
    core_ids: dict[str, str]  # C1 → 문서 ID
    filler_order: list[str]  # 길이 구간을 키울 때 더하는 순서(중첩형)


def build_docs(seed: int = SEED, pool: int = FILLER_POOL) -> Docs:
    rng = random.Random(seed)
    specs = _core_specs()
    core_dates = {s["date"] for s in specs.values()}
    start, span = date(2024, 9, 1), (date(2026, 3, 31) - date(2024, 9, 1)).days
    filler_days: set[date] = set()
    while len(filler_days) < pool:
        d = start + timedelta(days=rng.randrange(span))
        if d.isoformat() not in core_dates:
            filler_days.add(d)

    timeline: list[tuple[str, str | None]] = [(s["date"], k) for k, s in specs.items()]
    timeline += [(d.isoformat(), None) for d in filler_days]
    timeline.sort()

    core_order = sorted(specs, key=lambda k: specs[k]["date"])
    cur, docs, core_ids = (1, 0, 0), [], {}
    for i, (day, key) in enumerate(timeline):
        doc_id = f"N{i + 1:03d}"
        if key is not None:
            s = specs[key]
            cur = CORE_VERSIONS[key]
            raw = render_raw(s["fmt"], s["intro"], s["sections"], s["outro"], s["image"])
            docs.append(_make_doc(doc_id, s["title"], day, s["lang"], s["fmt"], raw, True))
            core_ids[key] = doc_id
            continue
        nxt = next((CORE_VERSIONS[k] for k in core_order if specs[k]["date"] > day), None)
        lang = "ko" if rng.random() < 0.15 else "en"
        fmt = rng.choices(["bbcode", "html", "text"], [0.6, 0.25, 0.15])[0]
        kind = rng.choices(["hotfix", "patch", "major", "post"], [0.15, 0.4, 0.2, 0.25])[0]
        version = None
        if kind != "post":
            version, kind = _filler_version(cur, kind, nxt)
        g = _Gen(rng, lang)
        if version is None:
            title, intro, sections, outro = g.post(date.fromisoformat(day))
        else:
            cur = version
            v = ".".join(map(str, version))
            intro, sections, outro = g.patch(kind)
            if lang == "ko":
                title = f"{v} 업데이트 안내" if kind == "major" else f"{v} 패치 노트"
            else:
                title = {"hotfix": f"Patch {v} Hotfix", "patch": f"Patch {v} Notes",
                         "major": f"Update {v}: {rng.choice(F_MAPS)} Season"}[kind]
        raw = render_raw(fmt, intro, sections, outro, image=fmt != "text" and rng.random() < 0.5)
        docs.append(_make_doc(doc_id, title, day, lang, fmt, raw, False))

    filler_order = [d.id for d in docs if not d.core]
    rng.shuffle(filler_order)
    return Docs(docs, core_ids, filler_order)


# ---------------------------------------------------------------- 길이 구간 선택

@dataclass(frozen=True)
class Selection:
    doc_ids: list[str]
    tokens: int  # 실제 측정한 코퍼스 토큰 수


def select_corpora(docs: Docs, count: Callable[[str], int],
                   targets: dict[str, int] = TARGETS) -> dict[str, Selection]:
    """구간마다 핵심 문서 + 방해 문서 앞 k개. k는 목표 토큰에 가장 가깝게.

    문서별 토큰 합으로 k를 어림한 뒤 전체를 한 번 재서 구분자 등 오차를 보정하고 다시 고른다.
    100k 측정은 수십 초가 걸려 구간당 측정은 최대 두 번만 한다.
    """
    by_id = {d.id: d for d in docs.docs}
    core = [d for d in docs.docs if d.core]
    fillers = [by_id[i] for i in docs.filler_order]
    per_doc = [count(render_doc(d)) for d in fillers]
    cum = [0]
    for n in per_doc:
        cum.append(cum[-1] + n)

    def closest_k(base: int, target: int) -> int:
        return min(range(len(cum)), key=lambda k: abs(base + cum[k] - target))

    def measure(k: int) -> int:
        return count(render_corpus(core + fillers[:k]))

    base = measure(0)
    result: dict[str, Selection] = {}
    for name, target in targets.items():
        if base + cum[-1] < target:
            raise ValueError(f"{name}: 방해 문서가 부족합니다 (최대 약 {base + cum[-1]} 토큰)")
        k = closest_k(base, target)
        actual = measure(k)
        corrected = closest_k(base + actual - (base + cum[k]), target)
        if corrected != k:
            k, actual = corrected, measure(corrected)
        result[name] = Selection([d.id for d in core + fillers[:k]], actual)
    return result
