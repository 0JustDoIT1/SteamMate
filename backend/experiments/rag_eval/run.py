"""A(전체 투입)·B(벡터 Top-K) 실행기. 결과는 질문 단위로 results/<모델>.jsonl에 추가한다.

사용: cd backend && python -m experiments.rag_eval.run [--model bonsai-2:9b] [--buckets 2k 8k]
- 중단 후 다시 실행하면 이미 기록된 (구간, 방식, 질문)은 건너뛴다.
- A는 지시문 → 코퍼스 → 질문 순서라 같은 구간의 다음 질문은 앞부분 캐시를 재사용한다.
  첫 요청 지연도 재기 위해 구간마다 앞 COLD_SAMPLES문제는 모델을 내렸다 올린 뒤 보낸다(로딩은 지연에서 뺀다).
  짧은 요청을 끼워 캐시를 밀어내는 방식은 Ollama가 이전 프롬프트 캐시를 다시 써서 효과가 없었다(2026-11-04 확인).
- --cold-only N: B 없이 구간마다 앞 N문제를 모두 첫 요청 조건으로 재서 <모델>_cold.jsonl에 쓴다(mode "A-cold").
- 지연은 모델 로딩을 뺀 값(total - load)을 주로 쓰고, 로딩·벽시계 시간도 함께 남긴다.
"""

import argparse
import json
import re
import time
from pathlib import Path
from typing import Protocol

import httpx

from experiments.rag_eval.build import OUT as DATASET
from experiments.rag_eval.dataset import Doc, render_corpus
from experiments.rag_eval.grading import grade
from experiments.rag_eval.retrieval import VectorIndex, chunk_doc, recall_at_k

OLLAMA = "http://127.0.0.1:11434"
EMBED_MODEL = "bge-m3"
RESULTS = Path(__file__).parent / "results"
MODELS = {"bonsai-2:9b": ["2k", "8k", "32k", "100k"], "qwen3:4b": ["2k", "8k", "32k"]}  # PRD v6.5
NUM_PREDICT = 1024  # Thinking 모델(qwen3:4b)의 추론이 길어 넉넉히. 두 모델에 같은 값.
TOP_K = 5
RECALL_KS = (1, 3, 5, 10)
COLD_SAMPLES = 3
B_NUM_CTX = 8_192
SYSTEM = (
    "너는 게임 뉴스 질의응답 도우미다. 아래 제공된 문서만 근거로 한국어로 답한다.\n"
    "문서에 없는 내용은 추측하지 말고 답을 '근거 없음'이라고 쓴다.\n"
    "문서마다 [N000] 형식의 ID와 날짜가 있다. 최신 값을 묻는 질문은 날짜가 가장 늦은 문서를 기준으로 한다.\n"
    "출력 형식(두 줄):\n답: <짧은 답>\n근거: <답에 사용한 문서 ID, 쉼표로 구분>"
)


class Client(Protocol):
    def chat(self, model: str, system: str, user: str, num_ctx: int, num_predict: int) -> dict: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def gpu_share(self, model: str) -> str | None: ...
    def unload(self, model: str) -> None: ...


class OllamaClient:
    def __init__(self, http: httpx.Client):
        self.http = http

    def chat(self, model: str, system: str, user: str, num_ctx: int, num_predict: int) -> dict:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        r = self.http.post("/api/chat", json={
            "model": model, "messages": messages, "stream": False, "think": False, "keep_alive": "10m",
            "options": {"num_ctx": num_ctx, "num_predict": num_predict, "temperature": 0, "seed": 1},
        })
        r.raise_for_status()
        return r.json()

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 32):
            r = self.http.post("/api/embed", json={"model": EMBED_MODEL, "input": texts[i:i + 32],
                                                   "keep_alive": "10m"})
            r.raise_for_status()
            vectors = r.json()["embeddings"]
            if len(vectors) != len(texts[i:i + 32]):
                raise RuntimeError("임베딩 개수가 입력과 다릅니다")
            out.extend(vectors)
        return out

    def unload(self, model: str) -> None:
        """모델을 내려 KV 캐시를 확실히 비운다. 내려갈 때까지 기다린다."""
        self.http.post("/api/generate", json={"model": model, "keep_alive": 0}).raise_for_status()
        for _ in range(60):
            if not any(m["name"] == model for m in self.http.get("/api/ps").json().get("models", [])):
                return
            time.sleep(0.5)
        raise RuntimeError(f"{model} 모델이 내려가지 않습니다")

    def gpu_share(self, model: str) -> str | None:
        for m in self.http.get("/api/ps").json().get("models", []):
            if m["name"] == model and m.get("size"):
                return f"{m['size'] / 1e9:.1f}GB {100 * m.get('size_vram', 0) / m['size']:.0f}% GPU"
        return None


def _seconds(ns: int | None) -> float:
    return round((ns or 0) / 1e9, 3)


def _timing(r: dict, wall: float) -> dict:
    return {
        "prompt_tokens": r.get("prompt_eval_count", 0),
        "output_tokens": r.get("eval_count", 0),
        "done_reason": r.get("done_reason"),
        "load_s": _seconds(r.get("load_duration")),
        "prompt_s": _seconds(r.get("prompt_eval_duration")),
        "gen_s": _seconds(r.get("eval_duration")),
        "latency_s": _seconds((r.get("total_duration") or 0) - (r.get("load_duration") or 0)),
        "wall_s": round(wall, 3),
    }


def _graded(r: dict, q: dict, context_ids: set[str]) -> dict:
    content = r["message"]["content"]
    g = grade(content, q["answer"])
    return {
        "content": content,
        "answer_line": g.answer_line,
        "correct": g.correct,
        "refused": g.refused,
        "cited": g.cited,
        "cited_valid": all(c in context_ids for c in g.cited),  # 받지 않은 문서를 인용하지 않았는가
        "evidence_cited": bool(set(g.cited) & set(q["evidence"])) if q["evidence"] else None,
    }


def _check_truncation(r: dict, num_ctx: int) -> None:
    # 넘치면 Ollama가 앞부분을 잘라 버린다(사전 측정에서 확인) → 결과를 기록하지 않고 멈춘다
    if r.get("prompt_eval_count", 0) >= num_ctx - NUM_PREDICT:
        raise RuntimeError(f"입력이 num_ctx({num_ctx})에 닿아 잘렸을 수 있습니다: {r.get('prompt_eval_count')}")


def _load_done(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            done.add((rec["bucket"], rec["mode"], rec["qid"]))
    return done


def _docs(data: dict, bucket: str) -> list[Doc]:
    by_id = {d["id"]: d for d in data["docs"]}
    return [Doc(**{k: by_id[i][k] for k in ("id", "title", "date", "lang", "fmt", "text", "core")})
            for i in data["corpora"][bucket]["doc_ids"]]


def run_model(client: Client, data: dict, model: str, buckets: list[str], out: Path,
              cold_only: int | None = None) -> int:
    """기록한 질문 수를 돌려준다. cold_only=N이면 A의 앞 N문제를 모두 첫 요청 조건으로만 잰다."""
    mode_a = "A-cold" if cold_only else "A"
    done = _load_done(out)
    written = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        def write(rec: dict) -> None:
            nonlocal written
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            written += 1

        for bucket in buckets:
            docs = _docs(data, bucket)
            ids = {d.id for d in docs}
            corpus = render_corpus(docs)
            tokens = data["corpora"][bucket]["tokens"]
            base = {"model": model, "bucket": bucket, "corpus_tokens": tokens, "doc_count": len(docs)}

            # A: 전체 투입
            num_ctx = int(tokens * 1.2) + 2048  # 모델마다 토크나이저가 달라 여유를 둔다
            questions = data["questions"][:cold_only] if cold_only else data["questions"]
            pending = [q for q in questions if (bucket, mode_a, q["id"]) not in done]
            for i, q in enumerate(pending):
                cold = bool(cold_only) or i < COLD_SAMPLES
                if cold:
                    client.unload(model)
                t = time.perf_counter()
                r = client.chat(model, SYSTEM, f"문서:\n{corpus}\n\n질문: {q['text']}", num_ctx, NUM_PREDICT)
                wall = time.perf_counter() - t
                _check_truncation(r, num_ctx)
                write({**base, "mode": mode_a, "qid": q["id"], "kind": q["kind"], "num_ctx": num_ctx,
                       "cache": "cold" if cold else "reuse", **_timing(r, wall), "gpu": client.gpu_share(model),
                       **_graded(r, q, ids)})

            # B: 청킹 → 임베딩 → Top-K
            pending = [q for q in data["questions"] if (bucket, "B", q["id"]) not in done]
            if cold_only or not pending:
                continue
            chunks = [c for d in docs for c in chunk_doc(d.id, d.title, d.date, d.text)]
            t = time.perf_counter()
            index = VectorIndex(chunks, client.embed([c.text for c in chunks]))
            index_s = round(time.perf_counter() - t, 3)
            for q in pending:
                t = time.perf_counter()
                (qvec,) = client.embed([q["text"]])
                hits = index.search(qvec, max(RECALL_KS))
                embed_s = time.perf_counter() - t
                ranked = [c.doc_id for c, _ in hits]
                context = [c for c, _ in hits[:TOP_K]]
                user = "문서:\n" + "\n\n---\n\n".join(c.text for c in context) + f"\n\n질문: {q['text']}"
                t = time.perf_counter()
                r = client.chat(model, SYSTEM, user, B_NUM_CTX, NUM_PREDICT)
                wall = time.perf_counter() - t
                _check_truncation(r, B_NUM_CTX)
                recall = ({str(k): recall_at_k(ranked, q["evidence"], k) for k in RECALL_KS}
                          if q["evidence"] else None)
                write({**base, "mode": "B", "qid": q["id"], "kind": q["kind"], "num_ctx": B_NUM_CTX,
                       "top_k": TOP_K, "chunks": len(chunks), "index_s": index_s, "embed_s": round(embed_s, 3),
                       "context_doc_ids": sorted({c.doc_id for c in context}), "recall": recall,
                       **_timing(r, wall), "gpu": client.gpu_share(model),
                       **_graded(r, q, {c.doc_id for c in context})})
    return written


def measure_index(client: Client, data: dict, repeats: int = 3) -> dict[str, dict]:
    """임베딩 모델을 먼저 올려 두고 구간별 색인(청크 임베딩) 시간만 잰다.

    본 실행의 index_s는 구간 첫 색인에 모델 로딩이 섞일 수 있어 이 값을 리포트에 쓴다.
    """
    client.embed(["warm-up"])
    out = {}
    for bucket in data["corpora"]:
        docs = _docs(data, bucket)
        texts = [c.text for d in docs for c in chunk_doc(d.id, d.title, d.date, d.text)]
        times = []
        for _ in range(repeats):
            t = time.perf_counter()
            client.embed(texts)
            times.append(time.perf_counter() - t)
        out[bucket] = {"chunks": len(texts), "chars": sum(map(len, texts)),
                       "seconds_median": round(sorted(times)[len(times) // 2], 3)}
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=list(MODELS), help="생략하면 두 모델 모두")
    p.add_argument("--buckets", nargs="+", help="생략하면 모델별 기본 구간")
    p.add_argument("--cold-only", type=int, metavar="N", help="A의 앞 N문제를 모두 첫 요청 조건으로만 잰다")
    p.add_argument("--index-only", action="store_true", help="색인 시간만 재서 results/index_timing.json에 쓴다")
    args = p.parse_args()
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    models = [args.model] if args.model else list(MODELS)
    with httpx.Client(base_url=OLLAMA, timeout=1800) as http:
        client = OllamaClient(http)
        if args.index_only:
            timing = measure_index(client, data)
            RESULTS.mkdir(parents=True, exist_ok=True)
            (RESULTS / "index_timing.json").write_text(json.dumps(timing, indent=1) + "\n", encoding="utf-8")
            print(timing)
            return
        for model in models:
            buckets = args.buckets or MODELS[model]
            suffix = "_cold" if args.cold_only else ""
            out = RESULTS / f"{re.sub(r'[^A-Za-z0-9.-]', '_', model)}{suffix}.jsonl"
            n = run_model(client, data, model, buckets, out, args.cold_only)
            print(f"{model}: {n}건 기록 → {out}", flush=True)


if __name__ == "__main__":
    main()
