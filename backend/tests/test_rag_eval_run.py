"""7단계 실행기: 채점·검색·재개·캐시 구분. Ollama 대신 가짜 클라이언트를 쓴다."""

import json

import pytest

from experiments.rag_eval import report, run
from experiments.rag_eval.grading import grade
from experiments.rag_eval.retrieval import (
    CHUNK_CHARS,
    VectorIndex,
    chunk_doc,
    recall_at_k,
)

# ---------------------------------------------------------------- 채점


@pytest.mark.parametrize(("content", "answer", "correct"), [
    ("답: 50\n근거: N010", [["50"]], True),
    ("답: 150\n근거: N010", [["50"]], False),  # 숫자 경계
    ("답: 2.50\n근거: N010", [["50"]], False),
    ("답: 50.5", [["50"]], False),
    ("답: 2.3.0, 2.4.0, 2.4.1", [["2.3.0"], ["2.4.0"], ["2.4.1"]], True),
    ("답: 2.3.0, 2.4.1", [["2.3.0"], ["2.4.0"], ["2.4.1"]], False),  # 항목 누락
    ("답: relic hunt", [["Relic Hunt"]], True),
    ("답: 11월 3일까지", [["11월 3일", "2025-11-03"]], True),
    ("<think>값은 46이다</think>\n답: 50", [["46"]], False),  # 추론 속 숫자는 보지 않는다
    ("Arc Lance는 50입니다.", [["50"]], True),  # 형식을 안 지키면 전체를 본다
    ("**답:** 50", [["50"]], True),
    ("답: 근거 없음", [["50"]], False),
    ("답: 2025 년 11 월 3 일", [["11월 3일"]], True),  # 띄어 쓴 날짜
    ("답: Relic  Hunt", [["Relic Hunt"]], True),
])
def test_grade_answerable(content, answer, correct):
    assert grade(content, answer).correct is correct


def test_grade_answer_line_only():
    # 근거 줄의 숫자(문서 ID)나 다른 줄의 숫자는 정답으로 치지 않는다
    assert not grade("답: 모르겠다\n근거: N050", [["50"]]).correct


def test_grade_unanswerable():
    assert grade("답: 근거 없음\n근거:", []).correct
    assert grade("답: 정보 없음\n근거: 근거 없음", []).correct  # 지시와 다른 거절 표현
    assert grade("답: 정보 없음", [["50"]]).refused
    assert grade("답: 2.4.0에서는 변경되지 않았습니다", []).correct
    assert not grade("답: 18초\n근거: N010", []).correct


def test_grade_citations():
    g = grade("답: 50\n근거: N010, N002, N010", [["50"]])
    assert g.cited == ["N002", "N010"]


# ---------------------------------------------------------------- 청킹·검색


def test_chunks_keep_header_and_limit():
    text = "\n\n".join(f"para {i} " + "x" * 300 for i in range(10))
    chunks = chunk_doc("N001", "Patch 1.0.0 Notes", "2025-01-01", text)
    assert len(chunks) > 1
    for c in chunks:
        assert c.text.startswith("[N001] Patch 1.0.0 Notes (2025-01-01)\n")
        assert len(c.text) - len(c.text.split("\n", 1)[0]) <= CHUNK_CHARS + 2
    assert "".join(c.text for c in chunks).count("para ") == 10  # 빠지거나 겹치는 문단 없음


def test_long_paragraph_split_by_lines():
    para = "\n".join(f"- line {i} " + "y" * 100 for i in range(30))
    chunks = chunk_doc("N002", "t", "2025-01-01", para)
    assert len(chunks) > 1
    assert sum(c.text.count("- line ") for c in chunks) == 30


def test_vector_index_cosine_order():
    chunks = [c for d in ("N1", "N2", "N3") for c in chunk_doc(d, "t", "d", "body")]
    index = VectorIndex(chunks, [[1, 0], [0, 1], [10, 1]])
    hits = index.search([1, 0], 2)
    assert [c.doc_id for c, _ in hits] == ["N1", "N3"]  # 크기가 아니라 방향으로 비교
    assert hits[0][1] == pytest.approx(1.0)


def test_vector_index_validates():
    chunks = chunk_doc("N1", "t", "d", "body")
    with pytest.raises(ValueError):
        VectorIndex(chunks, [[1, 0], [0, 1]])
    with pytest.raises(ValueError):
        VectorIndex(chunks, [[0, 0]])


def test_recall_at_k():
    assert recall_at_k(["N1", "N1", "N2", "N3"], ["N2", "N3"], 3) == 0.5
    assert recall_at_k(["N1", "N1", "N2", "N3"], ["N2", "N3"], 4) == 1.0


# ---------------------------------------------------------------- 실행기


DATA = {
    "corpora": {"2k": {"tokens": 100, "doc_ids": ["N001", "N002"]}},
    "docs": [
        {"id": "N001", "title": "Patch 1.0.0 Notes", "date": "2025-01-01", "lang": "en", "fmt": "text",
         "core": True, "text": "Arc Lance: damage changed from 42 to 48."},
        {"id": "N002", "title": "Patch 1.0.1 Notes", "date": "2025-02-01", "lang": "en", "fmt": "text",
         "core": False, "text": "Arc Rifle: damage changed from 10 to 20."},
    ],
    "questions": [
        {"id": f"Q{i:02d}", "kind": "single", "text": f"질문 {i}", "answer": [["48"]], "evidence": ["N001"]}
        for i in range(1, 6)
    ] + [{"id": "Q06", "kind": "unanswerable", "text": "없는 것", "answer": [], "evidence": []}],
}


class FakeClient:
    def __init__(self, prompt_tokens: int = 50):
        self.chats: list[tuple[str, int, int]] = []
        self.embeds = 0
        self.unloads = 0
        self.prompt_tokens = prompt_tokens

    def chat(self, model, system, user, num_ctx, num_predict):
        self.chats.append((user, num_ctx, num_predict))
        return {"message": {"content": "답: 48\n근거: N001"}, "prompt_eval_count": self.prompt_tokens,
                "eval_count": 5, "total_duration": 2_000_000_000, "load_duration": 500_000_000,
                "prompt_eval_duration": 1_000_000_000, "eval_duration": 400_000_000, "done_reason": "stop"}

    def embed(self, texts):
        self.embeds += len(texts)
        return [[1.0, 0.0] if "Arc Lance" in t or "질문" in t else [0.0, 1.0] for t in texts]

    def gpu_share(self, model):
        return "3.0GB 100% GPU"

    def unload(self, model):
        self.unloads += 1


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_run_writes_both_modes_and_marks_cache(tmp_path):
    out = tmp_path / "m.jsonl"
    client = FakeClient()
    assert run.run_model(client, DATA, "m", ["2k"], out) == 12
    recs = _records(out)
    a = [r for r in recs if r["mode"] == "A"]
    b = [r for r in recs if r["mode"] == "B"]
    assert [r["cache"] for r in a] == ["cold"] * run.COLD_SAMPLES + ["reuse"] * (6 - run.COLD_SAMPLES)
    # 캐시 밀어내기 요청: 첫 문제 뒤 cold 문제마다 1번, 출력 1토큰
    # 첫 요청 조건: 모델을 내려 캐시를 비운다(짧은 요청 끼우기는 Ollama 캐시에 효과 없음)
    assert client.unloads == run.COLD_SAMPLES
    assert len(client.chats) == 12  # 캐시 밀어내기용 요청은 없다
    assert a[0]["latency_s"] == 1.5 and a[0]["load_s"] == 0.5
    assert a[0]["correct"] and a[0]["evidence_cited"] and a[0]["cited_valid"]
    assert a[-1]["qid"] == "Q06" and not a[-1]["correct"] and a[-1]["evidence_cited"] is None
    assert b[0]["recall"]["1"] == 1.0 and b[0]["context_doc_ids"] == ["N001", "N002"]
    assert b[-1]["recall"] is None


def test_run_resumes_without_repeating(tmp_path):
    out = tmp_path / "m.jsonl"
    run.run_model(FakeClient(), DATA, "m", ["2k"], out)
    again = FakeClient()
    assert run.run_model(again, DATA, "m", ["2k"], out) == 0
    assert again.chats == [] and again.embeds == 0
    assert len(_records(out)) == 12


def test_run_resumes_partial(tmp_path):
    out = tmp_path / "m.jsonl"
    run.run_model(FakeClient(), DATA, "m", ["2k"], out)
    lines = out.read_text(encoding="utf-8").splitlines()
    out.write_text("\n".join(lines[:4]) + "\n", encoding="utf-8")  # A 4문제까지만 남았다고 가정
    assert run.run_model(FakeClient(), DATA, "m", ["2k"], out) == 8
    recs = _records(out)
    assert sorted((r["mode"], r["qid"]) for r in recs) == sorted(
        (m, q["id"]) for m in ("A", "B") for q in DATA["questions"])


def test_run_stops_on_truncation(tmp_path):
    out = tmp_path / "m.jsonl"
    with pytest.raises(RuntimeError, match="잘렸을"):
        run.run_model(FakeClient(prompt_tokens=10**6), DATA, "m", ["2k"], out)
    assert out.read_text(encoding="utf-8") == ""  # 잘린 결과는 기록하지 않는다


# ---------------------------------------------------------------- 리포트


def test_percentile_nearest_rank():
    assert report.percentile(list(range(1, 11)), 50) == 5
    assert report.percentile(list(range(1, 11)), 95) == 10
    assert report.percentile([3.0], 95) == 3.0


def test_report_summarizes_run_and_regrades(tmp_path):
    out = tmp_path / "m.jsonl"
    run.run_model(FakeClient(), DATA, "m", ["2k"], out)
    records = _records(out)
    # 기록 당시 판정이 틀려 있어도 현재 규칙으로 다시 채점한다
    records = report.regrade([{**r, "correct": False} for r in records], DATA["questions"])
    rows = report.summarize(records)
    a, b = rows
    assert (a["mode"], b["mode"]) == ("A", "B")
    assert a["accuracy"] == "5/6 (83%)"  # Q06(답 없음)에 "48"로 답해 오답
    assert a["by_kind"]["unanswerable"] == "0/1 (0%)"
    assert a["latency_cold"] == "1.5 / 1.5" and a["latency_reuse"] == "1.5 / 1.5"
    assert b["recall"]["1"] == 1.0 and b["chunks"] == 2
    assert "| m | 2k (100) | A | 5/6 (83%)" in report.render(rows)


def test_cold_only_measures_first_n_without_b(tmp_path):
    out = tmp_path / "m_cold.jsonl"
    client = FakeClient()
    assert run.run_model(client, DATA, "m", ["2k"], out, cold_only=2) == 2
    recs = _records(out)
    assert [(r["mode"], r["qid"], r["cache"]) for r in recs] == [("A-cold", "Q01", "cold"), ("A-cold", "Q02", "cold")]
    assert client.unloads == 2 and client.embeds == 0
    assert run.run_model(FakeClient(), DATA, "m", ["2k"], out, cold_only=2) == 0  # 재개 시 반복하지 않는다


def test_relabel_cold_keeps_only_first_per_bucket():
    recs = [{"model": "m", "bucket": b, "mode": m, "cache": c}
            for b, m, c in [("2k", "A", "cold"), ("2k", "A", "cold"), ("2k", "A", "reuse"), ("2k", "B", None),
                            ("8k", "A", "cold"), ("8k", "A-cold", "cold")]]
    assert [r["cache"] for r in report.relabel_cold(recs)] == ["cold", "reuse", "reuse", None, "cold", "cold"]


def test_report_counts_missing_answer_line():
    recs = report.regrade([{"qid": "Q01", "content": "Okay, let's think... 48"}], DATA["questions"])
    assert recs[0]["has_answer_line"] is False and recs[0]["correct"] is True  # 관대 채점의 한계를 열로 드러낸다
