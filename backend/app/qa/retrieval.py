"""RAG용 청킹·In-Memory 벡터 검색(7단계 실험과 서비스 공용). 임베딩은 호출자가 넣는다(Ollama bge-m3)."""

from dataclasses import dataclass

import numpy as np

CHUNK_CHARS = 1_200  # 영어 기준 약 300토큰. 문단 단위로 묶어 이 길이를 넘지 않게 한다.


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    text: str  # "[N012] 제목 (날짜)" 머리줄 + 본문 일부. 임베딩·답변 입력 모두 이 문자열을 쓴다.


def _pieces(text: str) -> list[str]:
    """문단으로 나누고, 한도를 넘는 문단은 줄 단위로 다시 나눈다."""
    out: list[str] = []
    for para in text.split("\n\n"):
        if len(para) <= CHUNK_CHARS:
            out.append(para)
        else:
            out.extend(line for line in para.split("\n") if line)
    return out


def chunk_doc(doc_id: str, title: str, date: str, text: str) -> list[Chunk]:
    header = f"[{doc_id}] {title} ({date})"
    chunks: list[Chunk] = []
    buf: list[str] = []
    size = 0
    for piece in _pieces(text):
        if buf and size + len(piece) > CHUNK_CHARS:
            chunks.append(Chunk(doc_id, header + "\n" + "\n\n".join(buf)))
            buf, size = [], 0
        buf.append(piece)
        size += len(piece) + 2
    if buf:
        chunks.append(Chunk(doc_id, header + "\n" + "\n\n".join(buf)))
    return chunks


class VectorIndex:
    """정규화한 벡터의 내적 = 코사인 유사도. 수백 개 규모라 전수 비교로 충분하다."""

    def __init__(self, chunks: list[Chunk], vectors: list[list[float]]):
        if len(chunks) != len(vectors) or not chunks:
            raise ValueError(f"청크 {len(chunks)}개와 벡터 {len(vectors)}개가 맞지 않습니다")
        self.chunks = chunks
        self.matrix = _normalize(np.asarray(vectors, dtype=np.float32))

    def search(self, query: list[float], k: int, doc_id: str | None = None) -> list[tuple[Chunk, float]]:
        """doc_id를 주면 그 문서의 청크 안에서만 찾는다."""
        q = _normalize(np.asarray([query], dtype=np.float32))[0]
        scores = self.matrix @ q
        order = np.argsort(-scores, kind="stable")
        picked = [i for i in order if doc_id is None or self.chunks[i].doc_id == doc_id][:k]
        return [(self.chunks[i], float(scores[i])) for i in picked]


def context_chunks(index: VectorIndex, query: list[float], top_k: int,
                   pinned_doc: str | None, pinned_k: int) -> list[Chunk]:
    """전체 Top-K + 고정 문서(최신 업데이트)에서 질문과 가까운 청크 pinned_k개(겹치면 한 번만)."""
    chunks = [c for c, _ in index.search(query, top_k)]
    if pinned_doc is not None:
        chunks += [c for c, _ in index.search(query, pinned_k, pinned_doc) if c not in chunks]
    return chunks


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    if (norms == 0).any():
        raise ValueError("길이가 0인 벡터가 있습니다")
    return m / norms


def recall_at_k(ranked_doc_ids: list[str], evidence: list[str], k: int) -> float:
    """상위 k개 청크가 근거 문서를 몇 개나 덮는가(문서 단위)."""
    found = set(ranked_doc_ids[:k]) & set(evidence)
    return len(found) / len(evidence)
