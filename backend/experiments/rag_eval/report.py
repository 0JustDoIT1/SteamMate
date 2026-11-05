"""results/*.jsonl → results/report.md (자동 채점 요약). 수동 확인 표본은 별도로 기록한다.

사용: cd backend && python -m experiments.rag_eval.report
"""

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import median

from app.qa.templates import QaIntent
from experiments.rag_eval.grading import final_text, grade, structured_content
from experiments.rag_eval.run import DATASET, RECALL_KS, RESULTS

KINDS = ["single", "latest", "multi", "title", "unanswerable"]
BUCKETS = ["2k", "8k", "32k", "100k"]


def percentile(values: list[float], p: float) -> float:
    """최근접 순위 방식. 표본이 36개 안팎이라 보간하지 않는다."""
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "-"


def _lat(recs: list[dict]) -> str:
    if not recs:
        return "-"
    v = [r["latency_s"] for r in recs]
    return f"{median(v):.1f} / {percentile(v, 95):.1f}"


def summarize(records: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in records:
        groups[(r["model"], r["bucket"], r["mode"])].append(r)
    rows = []
    for (model, bucket, mode), recs in sorted(groups.items(),
                                              key=lambda g: (g[0][0], BUCKETS.index(g[0][1]), g[0][2])):
        answerable = [r for r in recs if r["evidence_cited"] is not None]
        row = {
            "model": model, "bucket": bucket, "mode": mode, "n": len(recs),
            "corpus_tokens": recs[0]["corpus_tokens"],
            "accuracy": _pct(sum(r["correct"] for r in recs), len(recs)),
            "by_kind": {k: _pct(sum(r["correct"] for r in recs if r["kind"] == k),
                                sum(1 for r in recs if r["kind"] == k)) for k in KINDS},
            "evidence_cited": _pct(sum(bool(r["evidence_cited"]) for r in answerable), len(answerable)),
            "cited_valid": _pct(sum(r["cited_valid"] for r in recs), len(recs)),
            "truncated_output": sum(r["done_reason"] == "length" for r in recs),
            "no_answer_line": sum(not r["has_answer_line"] for r in recs),
            "prompt_tokens": round(median(r["prompt_tokens"] for r in recs)),
            "output_tokens": round(median(r["output_tokens"] for r in recs)),
            "gpu": sorted({r["gpu"] for r in recs if r["gpu"]}),
        }
        if mode.startswith("A"):
            row["latency_cold"] = _lat([r for r in recs if r["cache"] == "cold"])
            row["latency_reuse"] = _lat([r for r in recs if r["cache"] == "reuse"])
        else:
            row["latency"] = _lat(recs)
            row["embed_s"] = round(median(r["embed_s"] for r in recs), 3)
            row["index_s"] = recs[0]["index_s"]
            row["chunks"] = recs[0]["chunks"]
            with_ev = [r for r in recs if r["recall"]]
            row["recall"] = {str(k): round(sum(r["recall"][str(k)] for r in with_ev) / len(with_ev), 2)
                             for k in RECALL_KS} if with_ev else {}
        rows.append(row)
    return rows


def render(rows: list[dict]) -> str:
    out = [
        "# Full Context vs RAG 실험 결과 (자동 채점)",
        "",
        "> **실험용 합성 데이터 기준.** 실제 Steam 뉴스로 일반화하지 않는다. 정답은 자동 채점이며 수동 확인 표본으로 보완한다.",
        "> 지연 = 모델 로딩 제외(total − load) p50 / p95 초. A의 cold = 캐시가 빈 첫 요청, reuse = 같은 코퍼스 앞부분 캐시 재사용.",
        ("> 본 실행 A의 cold는 구간 첫 질문 1개뿐이다(캐시 비우기용 짧은 요청이 효과가 없어 2·3번째는 reuse로 다시 분류). "
        "A-cold = 모델을 내렸다 올려 캐시를 비운 추가 측정(구간당 5문제)."),
        ("> **qwen3:4b는 비교 불가**: Thinking 모델이라 `think: false`에도 추론을 이어 가 출력 한도(1024)에서 잘리고 "
        "'답:' 줄이 없는 응답이 많다. 이때 채점이 추론 문장까지 보게 되어 정확도가 부풀 수 있다. 결론은 bonsai-2:9b로만 낸다."),
        "",
        "## 정확도·지연",
        "",
        "| 모델 | 구간 | 방식 | 정확도 | 지연 cold | 지연 reuse·B | 입력 토큰(p50) | 출력 토큰(p50) | GPU |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        cold = r.get("latency_cold", "-")
        warm = r.get("latency_reuse") or r.get("latency", "-")
        out.append(f"| {r['model']} | {r['bucket']} ({r['corpus_tokens']:,}) | {r['mode']} | {r['accuracy']} | "
                   f"{cold} | {warm} | {r['prompt_tokens']:,} | {r['output_tokens']} | {', '.join(r['gpu'])} |")
    out += ["", "## 질문 유형별 정확도", "",
            "| 모델 | 구간 | 방식 | " + " | ".join(KINDS) + " |", "|---|---|---|" + "---|" * len(KINDS)]
    for r in rows:
        out.append(f"| {r['model']} | {r['bucket']} | {r['mode']} | "
                   + " | ".join(r["by_kind"][k] for k in KINDS) + " |")
    out += ["", "## 근거·검색", "",
            "| 모델 | 구간 | 방식 | 근거 문서 인용 | 받은 문서만 인용 | 출력 잘림 | 답 줄 없음 | 청크 | 색인 s | 질문 임베딩 s | "
            + " | ".join(f"Recall@{k}" for k in RECALL_KS) + " |",
            "|---|---|---|---|---|---|---|---|---|---|" + "---|" * len(RECALL_KS)]
    for r in rows:
        rec = r.get("recall", {})
        out.append(f"| {r['model']} | {r['bucket']} | {r['mode']} | {r['evidence_cited']} | {r['cited_valid']} | "
                   f"{r['truncated_output']} | {r['no_answer_line']} | {r.get('chunks', '-')} | {r.get('index_s', '-')} | "
                   f"{r.get('embed_s', '-')} | " + " | ".join(str(rec.get(str(k), "-")) for k in RECALL_KS) + " |")
    return "\n".join(out) + "\n"


def render_index(timing: dict[str, dict]) -> str:
    out = ["", "## B 색인 시간 (bge-m3, 모델 로딩 제외, 3회 중앙값)", "",
           "위 표의 '색인 s'는 구간 첫 색인에 모델 로딩이 섞일 수 있어 이 값을 기준으로 한다.", "",
           "| 구간 | 청크 | 글자 수 | 색인 s |", "|---|---|---|---|"]
    out += [f"| {b} | {t['chunks']} | {t['chars']:,} | {t['seconds_median']} |" for b, t in timing.items()]
    return "\n".join(out) + "\n"


def regrade(records: list[dict], questions: list[dict], titles: dict[str, str] | None = None) -> list[dict]:
    """기록 당시가 아니라 현재 채점 규칙으로 다시 판정한다(규칙을 고쳐도 실험을 다시 돌리지 않게).

    v5·v6 기록(intent·raw 있음)은 모델 원문 JSON에서 채점용 문장을 다시 만든다.
    """
    answers = {q["id"]: q["answer"] for q in questions}
    out = []
    for r in records:
        if "raw" in r and "intent" in r:
            r = {**r, "content": structured_content(QaIntent(r["intent"]), r["raw"], titles or {})}
        g = grade(r["content"], answers[r["qid"]])
        has_line = re.search(r"답\s*\**\s*[:：]", final_text(r["content"])) is not None
        out.append({**r, "correct": g.correct, "refused": g.refused, "answer_line": g.answer_line,
                    "has_answer_line": has_line})
    return out


def relabel_cold(records: list[dict]) -> list[dict]:
    """본 실행 A에서 캐시가 실제로 빈 요청은 (모델, 구간)의 첫 요청뿐이다(기록 순서 기준)."""
    seen: set[tuple[str, str]] = set()
    out = []
    for r in records:
        if r["mode"] == "A":
            key = (r["model"], r["bucket"])
            r = {**r, "cache": "reuse" if key in seen else "cold"}
            seen.add(key)
        out.append(r)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", type=Path, default=RESULTS, help="결과 폴더(지시문 버전별)")
    results = p.parse_args().dir
    records = [json.loads(line) for p in sorted(results.glob("*.jsonl"))
               for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    titles = {d["id"]: d["title"] for d in data["docs"]}
    records = relabel_cold(regrade(records, data["questions"], titles))
    text = render(summarize(records))
    timing_path = results / "index_timing.json"
    if timing_path.exists():
        text += render_index(json.loads(timing_path.read_text(encoding="utf-8")))
    path = results / "report.md"
    path.write_text(text, encoding="utf-8")
    print(f"{len(records)}건 → {path}")


if __name__ == "__main__":
    main()
