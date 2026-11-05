"""값 질문의 이름 검색(PRD v6.12): 질문 속 영문 이름 추출, 이름이 든 청크를 최근 문서부터."""

import pytest

from app.qa.retrieval import (
    Chunk,
    VectorIndex,
    context_chunks,
    name_chunks,
    target_names,
)


@pytest.mark.parametrize(("question", "names"), [
    ("최신 패치 기준 Void Pistol의 탄창 크기는 얼마인가요?", ["Void Pistol"]),  # 한글 조사가 붙어도
    ("'Patch 2.3.0 Hotfix'에서 Void Pistol의 탄창 크기는?", ["Void Pistol"]),  # 흔한 말·따옴표 제외
    ("Ember Bow의 시위 당김 시간은 몇 ms인가요?", ["Ember Bow"]),  # 단위 제외
    ("Scout's Sling 피해량", ["Scout's Sling"]),
    ("마나 포션 회복량은 얼마야?", []),  # 한국어로만 물으면 이름 검색 없음
])
def test_target_names(question, names):
    assert target_names(question) == names


def _index(texts: dict[str, list[str]]) -> VectorIndex:
    chunks = [Chunk(doc_id, f"[{doc_id}] t\n{t}") for doc_id, ts in texts.items() for t in ts]
    return VectorIndex(chunks, [[1.0, float(i)] for i in range(len(chunks))])


def test_name_chunks_latest_first_and_exact_word():
    index = _index({
        "N001": ["Void Pistol magazine 12 -> 10"],
        "N002": ["Void Pistolero skin added"],  # 이름의 일부만 같은 단어는 아니다
        "N003": ["Arc Lance damage 46 -> 48", "void pistol magazine 10 -> 11"],  # 대소문자 무시
        "N004": ["Bug fixes"],
    })
    hits = name_chunks(index, ["Void Pistol"], 5)
    assert [c.doc_id for c in hits] == ["N003", "N001"]  # 최근 문서부터
    assert name_chunks(index, ["Void Pistol"], 1) == hits[:1]  # 최신 기록을 먼저 지킨다
    assert name_chunks(index, [], 5) == [] and name_chunks(index, ["Void Pistol"], 0) == []


def test_context_adds_name_chunks_without_duplicates():
    index = _index({"N001": ["Void Pistol magazine 12 -> 10"], "N002": ["Bug fixes"], "N003": ["Void Pistol 10 -> 13"]})
    query = [1.0, 0.0]
    base = context_chunks(index, query, 1, None, 0)
    with_names = context_chunks(index, query, 1, None, 0, names=["Void Pistol"], name_k=6)
    assert with_names[: len(base)] == base  # 의미 검색 결과가 먼저
    assert sorted(c.doc_id for c in with_names) == sorted({c.doc_id for c in with_names})  # 겹치면 한 번만
    assert {"N001", "N003"} <= {c.doc_id for c in with_names}
