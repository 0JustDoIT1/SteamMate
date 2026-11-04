"""7단계 합성 평가 데이터의 정합성: 정답이 근거에 있고, 방해 문서가 정답을 바꾸지 않으며, seed로 재현된다."""

import itertools
import json
import re

import pytest

from experiments.rag_eval.build import OUT
from experiments.rag_eval.dataset import (
    ABSENT_ENTITIES,
    CHANGES,
    CORE_ENTITIES,
    CORE_VERSIONS,
    QUESTIONS,
    build_docs,
    render_corpus,
    render_doc,
    select_corpora,
)

DOCS = build_docs()
BY_ID = {d.id: d for d in DOCS.docs}
CORE = {k: BY_ID[i] for k, i in DOCS.core_ids.items()}
FILLER = [d for d in DOCS.docs if not d.core]
CORE_VERSION_STRINGS = sorted({".".join(map(str, v)) for v in CORE_VERSIONS.values()})


def _history(entity: str, attr: str) -> list[tuple[str, int, int]]:
    return [(k, old, new) for k, e, a, old, new in CHANGES if e == entity and a == attr]


def _version(key: str) -> str:
    return ".".join(map(str, CORE_VERSIONS[key]))


def test_same_seed_same_docs():
    again = build_docs()
    assert again.docs == DOCS.docs
    assert again.filler_order == DOCS.filler_order


def test_ids_are_chronological_and_hide_core():
    assert [d.id for d in DOCS.docs] == [f"N{i + 1:03d}" for i in range(len(DOCS.docs))]
    assert [d.date for d in DOCS.docs] == sorted(d.date for d in DOCS.docs)


def test_question_ids_unique_and_count():
    ids = [q.id for q in QUESTIONS]
    assert len(ids) == len(set(ids)) >= 30


def test_answers_appear_in_evidence():
    # 계산이 필요한 답(횟수·차이)은 아래 테스트에서 따로 확인한다
    computed = {"Q22", "Q23", "Q26", "Q28"}
    for q in QUESTIONS:
        if q.kind == "unanswerable" or q.id in computed:
            continue
        evidence = "\n".join(render_doc(CORE[k]) for k in q.evidence)
        for options in q.answer:
            assert any(o in evidence for o in options), (q.id, options)


def test_latest_answers_are_last_change():
    for q in QUESTIONS:
        if q.kind == "latest" and q.fact:
            key, _, new = _history(*q.fact)[-1]
            assert q.answer == ((str(new),),), q.id
            assert q.evidence == (key,), q.id


def test_changed_version_lists_match_history():
    for q in QUESTIONS:
        if q.kind == "multi" and q.fact and len(q.answer) > 1:
            keys = [k for k, _, _ in _history(*q.fact)]
            assert [a[0] for a in q.answer] == [_version(k) for k in keys], q.id
            assert list(q.evidence) == keys, q.id


def test_computed_answers():
    arc = _history("Arc Lance", "damage")
    pistol = _history("Void Pistol", "magazine size")
    hammer = _history("Frost Hammer", "damage")
    tide = _history("Tide Caller", "damage")
    answers = {q.id: q.answer[0][0] for q in QUESTIONS if q.answer}
    assert answers["Q22"] == str(len(arc))
    assert answers["Q23"] == str(pistol[-1][2] - pistol[0][1])
    assert answers["Q26"] == str(hammer[-1][2] - hammer[0][1])
    assert answers["Q28"] == str(55 - tide[-1][2])  # 출시 피해량 55는 C3 본문에 있다
    assert "출시 피해량은 55" in CORE["C3"].text


def test_hotfix_and_notes_differ_for_title_questions():
    # 같은 버전의 두 글이 같은 대상을 서로 다르게 바꿔야 제목 구분 질문이 의미가 있다
    assert CORE["C1"].title == "Patch 2.3.0 Notes"
    assert CORE["C2"].title == "Patch 2.3.0 Hotfix"
    for q in QUESTIONS:
        if q.kind == "title":
            (asked,) = q.evidence
            other = "C2" if asked == "C1" else "C1"
            value = f"to {q.answer[0][0]}."
            assert value in CORE[asked].text and value not in CORE[other].text, q.id


def test_filler_never_mentions_core_names_or_versions():
    names = CORE_ENTITIES + ABSENT_ENTITIES + CORE_VERSION_STRINGS
    for d in FILLER:
        text = render_doc(d).lower()
        hits = [n for n in names if n.lower() in text]
        assert not hits, (d.id, d.title, hits)


def test_absent_entities_nowhere():
    for d in DOCS.docs:
        for n in ABSENT_ENTITIES:
            assert n.lower() not in render_doc(d).lower()


def test_filler_versions_monotonic_and_single_digit_patch():
    versions = []
    for d in DOCS.docs:
        m = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", d.title)
        if m:
            versions.append(tuple(map(int, m.groups())))
    assert versions == sorted(versions)
    assert all(v[2] <= 9 for v in versions)


def test_formats_and_languages_mixed():
    assert {d.fmt for d in FILLER} == {"bbcode", "html", "text"}
    assert {d.lang for d in FILLER} == {"en", "ko"}
    # 정제 결과에 태그가 남지 않는다
    assert not any(re.search(r"\[/?(p|h3|list|img)\]|<[a-z/]", d.text) for d in DOCS.docs)


def _fake_count(text: str) -> int:
    return len(text) // 4


def test_select_corpora_nested_and_near_target():
    sel = select_corpora(DOCS, _fake_count, {"a": 3_000, "b": 20_000, "c": 60_000})
    core_ids = set(DOCS.core_ids.values())
    # 앞에서부터 문서 단위로 더하므로 오차는 가장 큰 문서의 절반(+구분자 여유) 안이다
    tolerance = max(_fake_count(render_doc(d)) for d in FILLER) // 2 + 50
    prev: set[str] = set()
    for name, target in {"a": 3_000, "b": 20_000, "c": 60_000}.items():
        ids = set(sel[name].doc_ids)
        assert core_ids <= ids and prev <= ids, name
        assert abs(sel[name].tokens - target) <= tolerance, (name, sel[name].tokens)
        assert sel[name].tokens == _fake_count(render_corpus([BY_ID[i] for i in sel[name].doc_ids]))
        prev = ids


def test_select_corpora_raises_when_pool_too_small():
    with pytest.raises(ValueError, match="부족"):
        select_corpora(DOCS, _fake_count, {"huge": 10_000_000})


@pytest.mark.skipif(not OUT.exists(), reason="dataset.json 생성 전")
def test_frozen_dataset_matches_generator():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    for d in data["docs"]:
        doc = BY_ID[d["id"]]
        assert (d["title"], d["date"], d["text"], d["core"]) == (doc.title, doc.date, doc.text, doc.core)
    assert [q["id"] for q in data["questions"]] == [q.id for q in QUESTIONS]
    names = list(data["corpora"])
    for small, big in itertools.pairwise(names):
        assert set(data["corpora"][small]["doc_ids"]) <= set(data["corpora"][big]["doc_ids"])
