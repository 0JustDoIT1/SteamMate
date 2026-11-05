"""값 질문 서버 계산(PRD v6.9): 질문 꼴 판별, 기록 정리, 지금 값·버전·처음·횟수·차이·버전 목록."""

import pytest

from app.qa.templates import REFUSAL, ValueAnswer, ValueChange
from app.qa.value import DocInfo, ValueKind, compute_value, value_kind

# 실험 데이터와 같은 꼴: 2.3.0은 정규 패치와 핫픽스가 버전 번호를 함께 쓴다
DOCS = {
    "N097": DocInfo("2025-09-02", "Patch 2.3.0 Notes"),
    "N098": DocInfo("2025-09-05", "Patch 2.3.0 Hotfix"),
    "N110": DocInfo("2025-10-14", "2.4.0 업데이트 안내"),
    "N115": DocInfo("2025-11-04", "Patch 2.4.1 Notes"),
    "N122": DocInfo("2025-12-09", "Patch 2.5.0 Notes"),
}


def answer(*changes: tuple[str, str, str, str]) -> ValueAnswer:
    return ValueAnswer(target="대상", history=[ValueChange(doc=d, version=v, before=b, after=a)
                                               for d, v, b, a in changes])


# Arc Lance 피해량: 46 → 48(2.3.0) → 46(핫픽스) → 50(2.5.0). 모델이 순서를 섞어 적어도 서버가 날짜로 정렬한다
ARC = answer(("N122", "2.5.0", "46", "50"), ("N097", "2.3.0", "46", "48"), ("N098", "", "48", "46"))


@pytest.mark.parametrize(("question", "kind"), [
    ("최신 패치 기준 Arc Lance의 피해량은 얼마인가요?", ValueKind.CURRENT),
    ("2.3.0 패치에서 Frost Hammer의 피해량은 얼마로 바뀌었나요?", ValueKind.AT_VERSION),
    ("Tide Caller의 출시 당시 피해량은 얼마였나요?", ValueKind.FIRST),
    ("Tide Caller는 몇 버전에서 추가되었나요?", ValueKind.WHEN),
    ("Arc Lance 피해량은 언제 바뀌었나요?", ValueKind.WHEN),
    ("Arc Lance의 피해량은 2.3.0 패치 이전 값에서 최신 패치까지 모두 몇 번 바뀌었나요?", ValueKind.COUNT),
    ("Void Pistol의 탄창 크기는 2.3.0 패치 이전보다 최신 패치에서 얼마나 늘었나요?", ValueKind.DIFF),
    ("Phantom Glaive의 재사용 대기시간이 바뀐 버전을 모두 쓰세요.", ValueKind.VERSIONS),
    ("Ember Bow의 시위 당김 시간은 몇 ms인가요?", ValueKind.CURRENT),  # "몇 ms"는 횟수가 아니다
])
def test_value_kind(question, kind):
    assert value_kind(question) == kind


def test_current_is_latest_by_date_and_fills_version_from_title():
    out = compute_value(ARC, "최신 패치 기준 Arc Lance의 피해량은 얼마인가요?", DOCS)
    assert (out.value, out.changed_in, out.previous) == ("50", "2.5.0", "46")
    assert [h.doc for h in out.history] == ["N097", "N098", "N122"]
    assert out.history[1].version == "2.3.0" and out.history[1].date == "2025-09-05"  # 빈 버전은 제목에서
    assert out.sources == ["N122"]  # 답으로 고른 기록의 공지만 출처로


@pytest.mark.parametrize(("question", "value"), [
    ("핫픽스가 아닌 'Patch 2.3.0 Notes'에서 Arc Lance의 피해량은 얼마로 바뀌었나요?", "48"),
    ("2.3.0 핫픽스에서 Arc Lance의 피해량은 얼마로 바뀌었나요?", "46"),
    ("2.3.0 패치에서 Arc Lance의 피해량은 얼마로 바뀌었나요?", "48"),  # 말이 없으면 정규 패치
    ("2.4.0 업데이트에서 Arc Lance의 피해량은 얼마로 바뀌었나요?", REFUSAL),  # 그 버전 기록이 없다
])
def test_at_version_separates_notes_and_hotfix(question, value):
    assert compute_value(ARC, question, DOCS).value == value


def test_first_and_when_use_first_record_for_added_items():
    tide = answer(("N115", "2.4.1", "55", "50"), ("N110", "2.4.0", "", "55"))
    assert compute_value(tide, "Tide Caller의 출시 당시 피해량은 얼마였나요?", DOCS).value == "55"
    assert compute_value(tide, "Tide Caller는 몇 버전에서 추가되었나요?", DOCS).value == "2.4.0"
    assert compute_value(tide, "Tide Caller 피해량은 언제 바뀌었나요?", DOCS).value == "2.4.1"


def test_count_versions_and_diff():
    out = compute_value(ARC, "Arc Lance의 피해량은 2.3.0 패치 이전 값에서 최신 패치까지 모두 몇 번 바뀌었나요?", DOCS)
    assert out.value == "3" and out.sources == ["N097", "N098", "N122"]
    out = compute_value(ARC, "Arc Lance 피해량이 바뀐 버전을 모두 쓰세요.", DOCS)
    assert out.value == "2.3.0, 2.5.0"  # 같은 버전(정규·핫픽스)은 한 번만
    pistol = answer(("N097", "2.3.0", "12", "10"), ("N098", "2.3.0", "10", "11"), ("N122", "2.5.0", "11", "13"))
    out = compute_value(pistol, "Void Pistol 탄창은 2.3.0 패치 이전보다 최신 패치에서 얼마나 늘었나요?", DOCS)
    assert out.value == "1" and out.note == "늘어남: 12 → 13"
    tide = answer(("N110", "2.4.0", "", "55"), ("N115", "2.4.1", "55", "50"))
    out = compute_value(tide, "Tide Caller의 피해량은 출시 당시보다 최신 패치에서 얼마나 줄었나요?", DOCS)
    assert out.value == "5" and out.note == "줄어듦: 55 → 50"
    # 새로 추가된 첫 기록은 "바뀐 횟수"에 넣지 않는다
    assert compute_value(tide, "Tide Caller 피해량은 몇 번 바뀌었나요?", DOCS).value == "1"


def test_units_and_unreadable_numbers():
    bow = answer(("N097", "2.3.0", "800ms", "750ms"), ("N115", "2.4.1", "750ms", "800ms"))
    assert compute_value(bow, "Ember Bow 시위 당김 시간은 처음보다 얼마나 늘었나요?", DOCS).value == "0"
    vague = answer(("N097", "2.3.0", "보통", "빠름"))
    out = compute_value(vague, "처음보다 얼마나 늘었나요?", DOCS)
    assert out.value == REFUSAL and out.sources == []  # 숫자를 못 읽으면 지어내지 않는다


def test_drops_records_from_docs_not_given_or_without_value():
    ghost = answer(("N999", "9.9", "1", "2"), ("N115", "2.4.1", "1", ""), ("N122", "2.5.0", "46", "50"))
    out = compute_value(ghost, "지금 피해량은?", DOCS, allowed={"N122"})
    assert [h.doc for h in out.history] == ["N122"] and out.value == "50"
    assert compute_value(answer(), "지금 피해량은?", DOCS).value == REFUSAL  # 기록이 없으면 근거 없음
    out = compute_value(answer(("N122", "2.5.0", "46", "50")), "지금 피해량은?", DOCS, allowed={"N097"})
    assert out.value == REFUSAL  # 넘기지 않은 문서의 기록만 있으면 근거 없음


def test_title_version_wins_over_model_version_and_diff_needs_a_baseline():
    # 모델이 지시문 예시 버전을 베껴도 제목의 버전을 쓴다(실제 Terraria에서 "2.4.1"이 나왔다)
    docs = {"N050": DocInfo("2026-08-19", "Terraria 1.4.5.7 - Out Now for PC!"), "N051": DocInfo("2026-09-01", "Hotfix 761239")}
    out = compute_value(answer(("N050", "2.4.1", "88", "150")), "Unholy Trident 피해량은 언제 바뀌었어?", docs)
    assert out.value == "1.4.5.7"
    assert compute_value(answer(("N051", "3.1", "1", "2")), "언제 바뀌었어?", docs).value == "3.1"  # 제목에 없으면 모델 값
    # 모델이 버전 칸에 제목·날짜를 통째로 쓰면 버리고 날짜로 보인다(Apex "Cipher Patch Notes (2026-11-02)")
    out = compute_value(answer(("N051", "Apex Legends: Cipher Patch Notes (2026-11-02)", "", "56")), "지금 피해량은?", docs)
    assert out.history[0].version == "" and out.changed_in == "2026-09-01"
    # 기록 하나에 이전 값도 없으면 비교 기준이 없다 — "0, 변화 없음"이라고 하지 않는다
    out = compute_value(answer(("N050", "", "", "300")), "Super Mana Potion 회복량은 얼마나 늘었어?", docs)
    assert out.value == REFUSAL


def test_padded_doc_ids_are_normalized():
    """모델이 "N115"를 "N0115"로 적어도 같은 문서로 본다(v7 재실험에서 기록이 통째로 버려지던 원인)."""
    import json

    from app.qa.templates import QaIntent, doc_ids, parse

    assert doc_ids("[N0115] Patch 2.4.1, N012, N0115") == ["N115", "N012"]
    raw = json.dumps({"target": "Tide Caller 피해량", "sources": ["N0115"],
                      "history": [{"doc": "N0115", "version": "", "before": "55", "after": "50"}]})
    filled = parse(QaIntent.VALUE, raw)
    assert filled.history[0].doc == "N115" and filled.sources == ["N115"]
    assert compute_value(filled, "2.4.1 패치에서 Tide Caller의 피해량은 얼마로 바뀌었나요?", DOCS).value == "50"


def test_attribute_filter_drops_other_stats_of_same_item():
    """사거리를 묻는데 모델이 Knockback 기록을 옮기면 서버가 버린다(PRD v6.13, Terraria·Q36)."""
    from app.qa.value import question_attribute

    docs = {"N050": DocInfo("2026-08-19", "Terraria 1.4.5.7 - Out Now for PC!")}
    knock = ValueAnswer(target="Unholy Trident 사거리", history=[
        ValueChange(doc="N050", attribute="Knockback", version="", before="6.5", after="6.66")])
    assert compute_value(knock, "Unholy Trident 사거리는 얼마야?", docs).value == REFUSAL
    assert compute_value(knock, "Unholy Trident 넉백은 얼마야?", docs).value == "6.66"
    dmg = ValueAnswer(target="피해량", history=[ValueChange(doc="N050", attribute="Damage", before="88", after="150")])
    assert compute_value(dmg, "Unholy Trident 피해량은 지금 얼마야?", docs).value == "150"
    # 속성을 적지 않았거나 표에 없는 말로 물으면 걸러내지 않는다
    assert compute_value(dmg, "Unholy Trident 성능은 지금 얼마야?", docs).value == "150"
    no_attr = ValueAnswer(target="x", history=[ValueChange(doc="N050", before="6.5", after="6.66")])
    assert compute_value(no_attr, "사거리는 얼마야?", docs).value == "6.66"
    assert question_attribute("재사용 대기시간은 몇 초?")[0] == "cooldown"  # 긴 말부터


def test_from_to_in_one_field_is_split():
    docs = {"N050": DocInfo("2026-08-19", "Terraria 1.4.5.7")}
    mana = ValueAnswer(target="회복량", history=[ValueChange(doc="N050", attribute="Mana recovery", after="300 to 400")])  # 실제 응답 그대로
    out = compute_value(mana, "Super Mana Potion 회복량은 얼마야?", docs)
    assert (out.value, out.previous) == ("400", "300")


def test_legacy_record_with_direct_value_is_kept():
    """v5·v6 실험 기록(모델이 value를 직접 채움)은 다시 채점할 때 그대로 둔다."""
    legacy = ValueAnswer(target="대상", value="48", changed_in="2.3.0")
    assert compute_value(legacy, "지금 피해량은?", DOCS) is legacy
