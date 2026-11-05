"""RAG용 청킹·In-Memory 벡터 검색(7단계 실험과 서비스 공용). 임베딩은 호출자가 넣는다(Ollama bge-m3)."""

import re
from collections.abc import Sequence
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


# 질문 속 영문 이름("Void Pistol", "Arc Lance"). 한글이 바로 붙어도("Arc Lance의") 이름만 잡도록 영문·숫자만 본다
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9'’\-]*(?:[ \t]+[A-Za-z][A-Za-z0-9'’\-]*)*")
# 이름이 아닌 흔한 말(모든 패치 조각에 걸린다)
_NOT_NAMES = frozenset({"patch", "hotfix", "notes", "note", "update", "version", "dlc", "the", "ms", "hp", "dps"})


def target_names(question: str) -> list[str]:
    """값 질문의 대상 이름(영문). 한국어로만 물으면 빈 목록 — 이름 검색 없이 의미 검색만 한다."""
    names = []
    for m in _NAME.finditer(question):
        name = m[0].strip(" \t'’-")  # 'Patch 2.3.0 Hotfix'처럼 따옴표가 붙어도
        if len(name) >= 3 and name.lower() not in _NOT_NAMES:
            names.append(name)
    return list(dict.fromkeys(names))


def name_chunks(index: VectorIndex, names: Sequence[str], k: int, exclude: Sequence[Chunk] = ()) -> list[Chunk]:
    """이름이 글자 그대로 들어간 청크를 최근 문서부터 k개(PRD v6.12). 의미 검색은 이름이 한 줄만 나온 옛 패치
    조각을 순위에서 밀어내 여러 공지의 변경 기록을 놓쳤다. 최근부터 넣어 최신 기록을 먼저 지킨다.
    문서 ID는 오래된 글부터 N001…이라 ID 역순 = 최근 순."""
    if not names or k <= 0:
        return []
    patterns = [re.compile(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])", re.IGNORECASE) for n in names]
    hits = [c for c in index.chunks if c not in exclude and any(p.search(c.text) for p in patterns)]
    hits.sort(key=lambda c: c.doc_id, reverse=True)  # 안정 정렬: 같은 문서 안에서는 원래 순서
    return hits[:k]


def context_chunks(index: VectorIndex, query: list[float], top_k: int,
                   pinned_doc: str | None, pinned_k: int, recent_docs: Sequence[str] = (),
                   names: Sequence[str] = (), name_k: int = 0) -> list[Chunk]:
    """전체 Top-K + 고정 문서(최신 업데이트)에서 질문과 가까운 청크 pinned_k개
    + 최근 문서마다 질문과 가장 가까운 청크 1개 + 대상 이름이 든 청크 name_k개(겹치면 한 번만)."""
    chunks = [c for c, _ in index.search(query, top_k)]
    if pinned_doc is not None:
        chunks += [c for c, _ in index.search(query, pinned_k, pinned_doc) if c not in chunks]
    for doc_id in recent_docs:
        chunks += [c for c, _ in index.search(query, 1, doc_id) if c not in chunks]
    chunks += name_chunks(index, names, name_k, chunks)
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
