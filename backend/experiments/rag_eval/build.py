"""데이터셋 고정: 주 모델 토크나이저로 길이 구간을 정하고 data/dataset.json에 쓴다.

사용: cd backend && python -m experiments.rag_eval.build [--model bonsai-2:9b]
Ollama에는 토큰만 세는 API가 없어 num_predict=1로 호출해 prompt_eval_count를 읽는다.
같은 프롬프트를 반복해도 값이 같다(캐시 재사용과 무관, 2026-11-04 확인). 빈 메시지의 템플릿 토큰은 빼고 센다.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import httpx

from experiments.rag_eval.dataset import (
    QUESTIONS,
    SEED,
    TARGETS,
    build_docs,
    select_corpora,
)

OLLAMA = "http://127.0.0.1:11434"
NUM_CTX = 131_072  # 모든 측정에 같은 값 → 모델을 한 번만 올린다. 100k 코퍼스보다 커야 잘리지 않는다.
OUT = Path(__file__).parent / "data" / "dataset.json"


def ollama_counter(client: httpx.Client, model: str):
    def raw_count(text: str) -> int:
        r = client.post("/api/chat", json={
            "model": model,
            "messages": [{"role": "user", "content": text}],
            "stream": False,
            "think": False,
            "options": {"num_predict": 1, "temperature": 0, "seed": 1, "num_ctx": NUM_CTX},
            "keep_alive": "10m",
        })
        r.raise_for_status()
        n = r.json()["prompt_eval_count"]
        if n >= NUM_CTX - 16:
            raise RuntimeError(f"입력이 num_ctx({NUM_CTX})에 닿아 잘렸을 수 있습니다: {n}")
        return n

    overhead = raw_count("")
    return lambda text: raw_count(text) - overhead


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="bonsai-2:9b")
    args = p.parse_args()

    docs = build_docs()
    with httpx.Client(base_url=OLLAMA, timeout=600) as client:
        version = client.get("/api/version").json()["version"]
        selections = select_corpora(docs, ollama_counter(client, args.model))

    used = set(selections["100k"].doc_ids)
    by_id = {d.id: d for d in docs.docs}
    out = {
        "meta": {
            "note": "실험용 합성 데이터. 실제 Steam 뉴스가 아니며 결과를 실제 뉴스로 일반화하지 않는다.",
            "seed": SEED,
            "tokenizer_model": args.model,
            "ollama_version": version,
            "targets": TARGETS,
        },
        "corpora": {
            name: {
                "tokens": s.tokens,
                "doc_count": len(s.doc_ids),
                "langs": dict(Counter(by_id[i].lang for i in s.doc_ids)),
                "chars": sum(len(by_id[i].text) for i in s.doc_ids),
                "doc_ids": s.doc_ids,
            }
            for name, s in selections.items()
        },
        "docs": [
            {"id": d.id, "title": d.title, "date": d.date, "lang": d.lang, "fmt": d.fmt, "core": d.core,
             "text": d.text}
            for d in docs.docs if d.id in used
        ],
        "questions": [
            {"id": q.id, "kind": q.kind, "text": q.text, "answer": [list(a) for a in q.answer],
             "evidence": [docs.core_ids[k] for k in q.evidence]}
            for q in QUESTIONS
        ],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, c in out["corpora"].items():
        print(f"{name}: {c['tokens']} tokens, {c['doc_count']} docs, {c['langs']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
