"""뉴스 AI 질문(F6 R2, PRD v6.10).

공식 공지 전문(최근 qa_max_docs건) → 정리 → 질문 유형 판별 → 분량으로 Full Context / RAG 선택 → 로컬 LLM이
유형별 칸(JSON)을 채움 → 근거 검증.
- 모드: 정제 후 코퍼스 토큰 어림값이 qa_full_context_max_tokens 이하면 Full Context. Full Context 입력이
  잘리면(어림이 빗나간 경우) 검색 모드로 바꿔 다시 묻는다(PRD "토큰 초과 시 안전하게 검색 모드로 전환").
- 유형(templates.py): 업데이트 요약·값·일정·신규 콘텐츠·기타. 요약의 규모·빌드는 공지 제목으로, 일정·콘텐츠의
  상태는 오늘 한국 날짜로 서버가 정한다. "최신 업데이트"(제목에 버전·업데이트·패치가 든 가장 최근 공지)
  표시와 RAG 고정 청크는 업데이트 요약에만 쓴다 — 의미 검색은 날짜를 보지 않아 "최신 업데이트에서 바뀐 점"에
  옛 공지 인사말만 걸리던 문제 대응. 값 질문에는 넣지 않는다(그 공지에 값이 없으면 "근거 없음"이 나오던 부작용).
- 문서 ID는 오래된 글부터 N001…, 입력은 최신 글이 먼저 — 7단계 실험과 같은 형식.
- 모델이 인용한 ID 중 넘기지 않은 문서는 버린다. 거절 답변에는 출처를 붙이지 않는다.
- 정리한 전문·임베딩은 qa_cache_seconds 동안 메모리에만 둔다(DB 저장·로그 없음).
- GPU 1개 전제라 LLM 호출은 한 번에 하나씩(asyncio.Lock).
"""

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated
from urllib.parse import urlparse

from cachetools import TTLCache
from pydantic import ConfigDict, Field, StringConstraints

from app.errors import AppError, ErrorCode
from app.news import FullNews, NewsService
from app.qa.llm import ChatResult, LlmClient
from app.qa.prompt import (
    DOC_SEPARATOR,
    asks_store,
    doc_header,
    is_patch_title,
    is_store_title,
    is_test_build,
    latest_update_id,
    mark_latest,
    recent_ids,
    strip_rules,
    title_version,
    update_scale,
    user_prompt,
)
from app.qa.retrieval import Chunk, VectorIndex, chunk_doc, context_chunks, target_names
from app.qa.templates import (
    RECENCY_INTENTS,
    ContentAnswer,
    QaIntent,
    ScheduleAnswer,
    Status,
    UpdateSummary,
    ValueAnswer,
    asks_current,
    classify,
    json_schema,
    parse,
    render,
    system_prompt,
    today_kst,
)
from app.qa.translate import needs_translation, translate_lines
from app.qa.value import DocInfo, ValueKind, compute_value
from app.schemas import CamelModel

logger = logging.getLogger(__name__)

NO_DOCS_ANSWER = "질문에 쓸 수 있는 공식 공지가 없습니다."
UNPARSED_ANSWER = "답변을 만들지 못했습니다. 질문을 조금 바꿔 다시 시도해 주세요."
NO_CURRENT_ANSWER = "진행 중이거나 예정된 일정을 공지에서 찾지 못했습니다. 최근 끝난 일정:"
# 근거가 없을 때 보이는 문장. 공지 대부분이 영어라 값 질문은 원문 이름으로 물으면 찾을 가능성이 높다
REFUSAL_ANSWERS = {
    QaIntent.UPDATE_SUMMARY: "최근 공지에서 업데이트 내용을 찾지 못했습니다.",
    QaIntent.VALUE: "최근 공지에서 이 수치를 찾지 못했습니다. 아이템·기능 이름을 공지에 쓰인 원문(영어) 그대로 "
                    "적으면 더 잘 찾습니다.",
    QaIntent.SCHEDULE: "최근 공지에서 해당 일정을 찾지 못했습니다.",
    QaIntent.CONTENT: "최근 공지에서 새 콘텐츠 소식을 찾지 못했습니다.",
    QaIntent.OTHER: "최근 공지에서 관련 내용을 찾지 못했습니다.",
}


def title_only_summary(news: FullNews) -> str:
    host = urlparse(news.external_url or "").netloc or "외부 사이트"
    return f"최신 업데이트 공지 '{news.title}'는 본문이 {host}에 있어 요약할 수 없어요. 원문에서 확인해 주세요."


class WarmupStatus(StrEnum):
    STARTED = "STARTED"  # 지금 준비를 시작했거나 이미 준비 중
    READY = "READY"  # 이미 준비돼 있음(공지·필요하면 색인까지)


class WarmupResponse(CamelModel):
    status: WarmupStatus


class QaMode(StrEnum):
    FULL_CONTEXT = "FULL_CONTEXT"
    RAG = "RAG"


class DateRange(CamelModel):
    from_: date = Field(alias="from")
    to: date


class AskRequest(CamelModel):
    # 모르는 항목은 거절한다(예: 없어진 dateRange를 보내면 조용히 무시하지 않고 422)
    model_config = ConfigDict(extra="forbid")

    appid: int = Field(gt=0, le=2_147_483_647)
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class AskSource(CamelModel):
    gid: str
    title: str
    published_at: datetime
    url: str
    # 본문이 외부 사이트에 있는 공지(제목만 보고 답함, PRD v6.18)면 그 원문 주소
    external_url: str | None = None


class UpdateScale(StrEnum):
    MAJOR = "MAJOR"
    PATCH = "PATCH"
    HOTFIX = "HOTFIX"


class BuildChannel(StrEnum):
    STABLE = "STABLE"
    TEST = "TEST"


class ScheduleKind(StrEnum):
    EVENT = "EVENT"
    RELEASE = "RELEASE"
    MAINTENANCE = "MAINTENANCE"
    TEST = "TEST"
    SALE = "SALE"


class ContentForm(StrEnum):
    FREE_UPDATE = "FREE_UPDATE"
    DLC = "DLC"
    EXPANSION = "EXPANSION"
    OTHER = "OTHER"


class SummaryDetail(CamelModel):
    version: str
    date: str
    # 요약한 공지 제목으로 서버가 어림한 규모·빌드
    scale: UpdateScale
    build: BuildChannel
    new_features: list[str]
    balance: list[str]
    bug_fixes: list[str]


class ValueChangeDetail(CamelModel):
    # 공지에 적힌 수치 이름 원문(예: Damage, Knockback). 모델이 속성을 헷갈려도 사용자가 알아볼 수 있게 보인다
    attribute: str
    version: str
    date: str
    before: str
    after: str


class ValueDetail(CamelModel):
    target: str
    # 서버가 질문 단어로 고른 계산 방식(value.py)
    kind: ValueKind
    value: str
    changed_in: str
    previous: str
    # 모델이 문서에서 옮긴 변경 기록(날짜순). 답의 근거로 화면에 보인다
    history: list[ValueChangeDetail]


class ScheduleItemDetail(CamelModel):
    name: str
    kind: ScheduleKind
    start: str
    end: str
    # 오늘(한국 날짜)과 비교해 서버가 정한 상태
    status: Status


class ScheduleDetail(CamelModel):
    items: list[ScheduleItemDetail]
    # 지금·앞으로를 물었는데 찾은 일정이 모두 끝났다(화면은 안내와 함께 흐리게 표시)
    no_current: bool = False


class ContentDetail(CamelModel):
    name: str
    form: ContentForm
    release_date: str
    status: Status
    highlights: list[str]


class AskResponse(CamelModel):
    # 화면 공용 답변 문장(유형별 칸을 이어 붙인 것)
    answer: str
    # 근거가 없어 답을 거절했는가
    refused: bool
    intent: QaIntent
    # 유형별 칸. 해당 유형이고 거절이 아닐 때만 채운다
    summary: SummaryDetail | None
    value: ValueDetail | None
    schedule: ScheduleDetail | None
    content: ContentDetail | None
    mode: QaMode
    sources: list[AskSource]
    # 질문에 쓴 글의 실제 날짜 범위(UTC). 글이 없으면 None
    date_range: DateRange | None
    # "최신 업데이트"로 본 공지(업데이트 요약 질문에서만 입력에 표시). 글이 없으면 None
    latest_update: AskSource | None
    doc_count: int
    # 모델이 실제로 처리한 입력 토큰(Ollama prompt_eval_count)
    input_tokens: int
    model: str
    answered_at: datetime


@dataclass(frozen=True)
class QaPolicy:
    max_docs: int
    full_context_max_tokens: int
    chars_per_token: float
    top_k: int
    name_chunks: int
    pinned_chunks: int
    recent_docs: int
    rag_num_ctx: int
    num_predict: int
    cache_seconds: float


@dataclass(frozen=True)
class _Doc:
    id: str
    news: FullNews  # text는 구분선을 지운 본문

    @property
    def day(self) -> str:
        return self.news.published_at.date().isoformat()

    def render(self, latest: bool) -> str:
        title = mark_latest(self.news.title) if latest else self.news.title
        return f"{doc_header(self.id, title, self.day)}\n{self.news.text}"

    def source(self) -> AskSource:
        n = self.news
        return AskSource(gid=n.gid, title=n.title, published_at=n.published_at, url=n.url, external_url=n.external_url)


@dataclass
class _Corpus:
    docs: list[_Doc]  # 오래된 글부터
    latest_id: str | None
    recent_ids: list[str]  # 상점·굿즈 글을 뺀 최근 글(최신 먼저)
    index: VectorIndex | None = None  # RAG가 처음 필요할 때 만든다

    def text(self, mark_latest_doc: bool) -> str:
        """Full Context 입력(최신 글이 먼저)."""
        return DOC_SEPARATOR.join(
            d.render(mark_latest_doc and d.id == self.latest_id) for d in reversed(self.docs)
        )


class NewsQaService:
    def __init__(self, news: NewsService, llm: LlmClient, policy: QaPolicy) -> None:
        self._news = news
        self.llm = llm
        self._policy = policy
        self._cache: TTLCache[int, _Corpus] = TTLCache(maxsize=32, ttl=policy.cache_seconds)
        self._gpu = asyncio.Lock()
        # 같은 게임의 공지 수집이 겹치면(미리 준비 + 질문) 한 번만 받는다
        self._loading: dict[int, asyncio.Task[_Corpus]] = {}
        # 미리 준비 중인 게임(백그라운드 작업 참조를 쥐어 가비지 수집을 막는다)
        self._warming: dict[int, asyncio.Task[None]] = {}

    def warmup(self, appid: int) -> WarmupStatus:
        """질문 전에 공지 수집과(필요하면) 검색 색인을 백그라운드로 준비한다(PRD v6.15). 질문 칸을 누를 때 부른다 —
        첫 질문이 공지 수집·임베딩까지 기다리던 15~20초를 줄인다. 이미 준비 중이거나 준비됐으면 다시 하지 않는다."""
        if appid in self._warming:
            return WarmupStatus.STARTED
        corpus = self._cache.get(appid)
        if corpus is not None and (corpus.index is not None or not self._needs_rag(corpus)):
            return WarmupStatus.READY
        task = asyncio.create_task(self._warm(appid))
        self._warming[appid] = task
        task.add_done_callback(lambda _: self._warming.pop(appid, None))
        return WarmupStatus.STARTED

    async def _warm(self, appid: int) -> None:
        try:
            corpus = await self._corpus(appid)
            if corpus.docs and self._needs_rag(corpus):
                # 질문과 같은 GPU 잠금 안에서 만든다 — 질문이 오면 색인이 끝날 때까지 기다렸다가 그대로 쓴다
                async with self._gpu:
                    await self._ensure_index(corpus)
        except (AppError, ValueError) as exc:  # 준비는 실패해도 괜찮다(질문 때 다시 시도하고 그때 오류를 알린다)
            logger.warning("qa warmup failed: appid=%s %s", appid, type(exc).__name__)

    def _needs_rag(self, corpus: "_Corpus") -> bool:
        return self.estimate_tokens(corpus.text(mark_latest_doc=False)) > self._policy.full_context_max_tokens

    async def _ensure_index(self, corpus: "_Corpus") -> None:
        if corpus.index is None:
            chunks = [c for d in corpus.docs for c in chunk_doc(d.id, d.news.title, d.day, d.news.text)]
            corpus.index = VectorIndex(chunks, await self.llm.embed([c.text for c in chunks]))

    def estimate_tokens(self, text: str) -> int:
        return int(len(text) / self._policy.chars_per_token) + 1

    async def ask(self, req: AskRequest) -> AskResponse:
        corpus = await self._corpus(req.appid)
        intent = classify(req.question)
        now = datetime.now(UTC)
        empty = {"summary": None, "value": None, "schedule": None, "content": None, "intent": intent, "model": self.llm.model,
                 "answered_at": now}
        if not corpus.docs:
            return AskResponse(answer=NO_DOCS_ANSWER, refused=True, mode=QaMode.FULL_CONTEXT, sources=[],
                               date_range=None, latest_update=None, doc_count=0, input_tokens=0, **empty)

        summary = intent is QaIntent.UPDATE_SUMMARY
        latest = next((d for d in corpus.docs if d.id == corpus.latest_id), None)
        if summary and latest is not None and latest.news.title_only:
            # 최신 패치 공지의 본문이 외부 사이트에만 있다 — 제목만으로 요약을 지어내지 않고 원문으로 안내한다(PRD v6.18)
            dates = [d.news.published_at.date() for d in corpus.docs]
            return AskResponse(answer=title_only_summary(latest.news), refused=False, mode=QaMode.FULL_CONTEXT,
                               sources=[latest.source()], date_range=DateRange(from_=min(dates), to=max(dates)),
                               latest_update=latest.source(), doc_count=len(corpus.docs), input_tokens=0, **empty)
        today = today_kst()  # 지시문의 오늘과 상태 판정 기준을 같은 날로
        system, schema = system_prompt(intent, today), json_schema(intent)
        text = corpus.text(mark_latest_doc=summary)
        estimate = self.estimate_tokens(text)
        mode = QaMode.FULL_CONTEXT if estimate <= self._policy.full_context_max_tokens else QaMode.RAG
        async with self._gpu:
            result: ChatResult | None = None
            context_ids: set[str] = set()
            if mode is QaMode.FULL_CONTEXT:
                # 분량에 맞춘 길이(추정 × 1.2 + 2048) 대신 RAG·번역과 같은 길이로 고정한다. 요청마다 길이가 달라지면
                # Ollama가 모델을 다시 올려 약 4초씩 늦었다. Full Context는 약 8k 이하라 12k 안에 들어간다
                num_ctx = max(self._policy.rag_num_ctx, int(estimate * 1.2) + 2048)
                result = await self.llm.chat(system, user_prompt(text, req.question), num_ctx, schema)
                context_ids = {d.id for d in corpus.docs}
                if self._truncated(result, num_ctx):
                    logger.warning("full context truncated, falling back to RAG: appid=%s tokens=%s",
                                   req.appid, result.prompt_tokens)
                    mode = QaMode.RAG
            if mode is QaMode.RAG:
                result, context_ids = await self._rag(corpus, req.question, system, schema, intent)

        by_id = {d.id: d for d in corpus.docs}
        dates = [d.news.published_at.date() for d in corpus.docs]
        base = {
            "mode": mode,
            "date_range": DateRange(from_=min(dates), to=max(dates)),
            "latest_update": by_id[corpus.latest_id].source() if summary and corpus.latest_id else None,
            "doc_count": len(corpus.docs),
            "input_tokens": result.prompt_tokens,
            **empty,
        }
        filled = parse(intent, result.content, {d.id: d.news.title for d in corpus.docs}, today)
        if filled is None:
            logger.warning("structured answer unparsable: intent=%s done=%s", intent, result.done_reason)
            return AskResponse(answer=UNPARSED_ANSWER, refused=True, sources=[], **base)
        if isinstance(filled, ValueAnswer):
            # 최신 값·횟수·차이는 서버가 계산하고, 출처도 답으로 고른 기록의 문서로 정한다
            docs = {d.id: DocInfo(d.day, d.news.title) for d in corpus.docs}
            filled = compute_value(filled, req.question, docs, context_ids)
        if isinstance(filled, ScheduleAnswer) and not asks_store(req.question):
            filled = _without_store(filled, by_id)
        valid = [c for c in filled.sources if c in context_ids]
        if len(valid) != len(filled.sources):
            logger.info("dropped cited ids not given to the model: %s", len(filled.sources) - len(valid))
        # 규모·빌드(와 모델이 비운 버전)는 모델이 요약에 쓴 공지(첫 인용), 없으면 최신 업데이트 공지 제목으로 정한다
        summary_doc = by_id.get(valid[0] if valid else corpus.latest_id or "")
        summary_title = summary_doc.news.title if summary_doc else ""
        if isinstance(filled, UpdateSummary) and not filled.version:
            filled = filled.model_copy(update={"version": title_version(summary_title)})
        answer, refused = render(filled)
        if not refused and isinstance(filled, UpdateSummary | ContentAnswer):
            translated = await self._translate_lists(filled)
            if translated is not filled:
                filled = translated
                answer, refused = render(filled)
        if refused:
            # "근거 없음"은 채점·판정용 말이다. 사용자에게는 유형에 맞는 문장으로 보인다
            answer = REFUSAL_ANSWERS[intent]
        details = {} if refused else _details(filled, summary_title)
        schedule = details.get("schedule")
        only_ended = schedule is not None and all(i.status is Status.ENDED for i in schedule.items)
        if only_ended and asks_current(req.question):
            # 지금·앞으로를 물었는데 끝난 일정만 찾았다 — 끝난 일정을 답처럼 내밀지 않고 그렇다고 알린다
            details["schedule"] = schedule.model_copy(update={"no_current": True})
            answer = f"{NO_CURRENT_ANSWER}\n{answer}"
        return AskResponse(answer=answer, refused=refused,
                           sources=[] if refused else [by_id[c].source() for c in valid], **{**base, **details})

    async def _translate_lists(self, filled: UpdateSummary | ContentAnswer) -> UpdateSummary | ContentAnswer:
        """목록 항목 중 영어로 남은 줄만 다시 번역한다(PRD v6.10). 영어 줄이 없으면 호출 없이 그대로."""
        keys = ("new_features", "balance", "bug_fixes") if isinstance(filled, UpdateSummary) else ("highlights",)
        lists = [getattr(filled, k) for k in keys]
        flat = [line for items in lists for line in items]
        if not any(needs_translation(line) for line in flat):
            return filled
        async with self._gpu:
            out = await translate_lines(self.llm, flat, self._policy.rag_num_ctx)
        if out == flat:
            return filled
        update, start = {}, 0
        for key, items in zip(keys, lists, strict=True):
            update[key], start = out[start:start + len(items)], start + len(items)
        return filled.model_copy(update=update)

    def _truncated(self, result: ChatResult, num_ctx: int) -> bool:
        # 넘치면 Ollama가 입력 앞부분을 잘라 낸다(7단계 사전 측정에서 확인)
        return result.prompt_tokens >= num_ctx - self._policy.num_predict

    async def _rag(self, corpus: _Corpus, question: str, system: str, schema: dict,
                   intent: QaIntent) -> tuple[ChatResult, set[str]]:
        summary = intent is QaIntent.UPDATE_SUMMARY
        recent = corpus.recent_ids if intent in RECENCY_INTENTS else []
        try:
            await self._ensure_index(corpus)
            (query,) = await self.llm.embed([question])
            pinned = corpus.latest_id if summary else None
            names = target_names(question) if intent is QaIntent.VALUE else []
            context = context_chunks(corpus.index, query, self._policy.top_k, pinned, self._policy.pinned_chunks,
                                     recent, names, self._policy.name_chunks)
        except ValueError as exc:  # 벡터 개수·길이 이상
            logger.warning("embedding unusable: %s", exc)
            raise AppError(ErrorCode.AI_UNAVAILABLE, "AI 검색 색인을 만들 수 없습니다.", 503) from exc
        texts = [_mark_chunk(c, corpus) if summary else c.text for c in context]
        num_ctx = self._policy.rag_num_ctx
        result = await self.llm.chat(system, user_prompt(DOC_SEPARATOR.join(texts), question), num_ctx, schema)
        if self._truncated(result, num_ctx):
            logger.warning("rag context truncated: tokens=%s", result.prompt_tokens)
            raise AppError(ErrorCode.AI_UNAVAILABLE, "질문 처리 중 입력 길이 한도를 넘었습니다.", 503)
        return result, {c.doc_id for c in context}

    async def _corpus(self, appid: int) -> _Corpus:
        cached = self._cache.get(appid)
        if cached is not None:
            return cached
        task = self._loading.get(appid)
        if task is None:
            task = asyncio.create_task(self._load_corpus(appid))
            self._loading[appid] = task
            task.add_done_callback(lambda _: self._loading.pop(appid, None))
        return await task

    async def _load_corpus(self, appid: int) -> _Corpus:
        news = await self._news.fetch_full(appid, self._policy.max_docs, None)
        news.sort(key=lambda n: n.published_at)
        docs = [_Doc(f"N{i + 1:03d}", replace(n, text=strip_rules(n.text))) for i, n in enumerate(news)]
        titles = [(d.id, d.news.title) for d in docs]
        # 제목만 있는 공지는 엄격한 패치 제목일 때만 "최신 업데이트" 후보(PRD v6.18) — "[Dev Letter] … Update"나
        # "Update Roadmap" 같은 소식 글이 뽑히지 않게. 제목만 있는 공지가 없으면 이전과 같은 결과(실험 조건 유지)
        update_titles = [(i, t) for (i, t), d in zip(titles, docs, strict=True)
                         if not d.news.title_only or is_patch_title(t)]
        corpus = _Corpus(docs, latest_update_id(update_titles), recent_ids(titles, self._policy.recent_docs))
        self._cache[appid] = corpus
        return corpus


def _without_store(filled: ScheduleAnswer, by_id: dict[str, _Doc]) -> ScheduleAnswer:
    """상점·드롭·굿즈 글은 일정이 아니다 — "다음 업데이트 언제야?"에 "November Store Update"(상점 개편)가 나열되던 문제.
    모델이 일정 이름에 공지 제목을 옮기는 경우가 많아 이름과 출처 제목으로 거른다. 남는 일정이 없으면 근거 없음."""
    items = [i for i in filled.items if not is_store_title(i.name)]
    sources = [c for c in filled.sources if not ((d := by_id.get(c)) and is_store_title(d.news.title))]
    return filled.model_copy(update={"items": items, "sources": sources})


def _mark_chunk(chunk: Chunk, corpus: _Corpus) -> str:
    """색인은 표시 없이 만들고, 업데이트 요약 입력에서만 최신 공지 청크 머리줄에 표시를 붙인다."""
    if chunk.doc_id != corpus.latest_id:
        return chunk.text
    prefix = f"[{chunk.doc_id}] "
    return chunk.text.replace(prefix, f"{prefix}{mark_latest('')}".rstrip() + " ", 1)


def _details(filled, summary_title: str) -> dict:
    if isinstance(filled, UpdateSummary):
        build = BuildChannel.TEST if is_test_build(summary_title) else BuildChannel.STABLE
        return {"summary": SummaryDetail(version=filled.version, date=filled.date,
                                         scale=UpdateScale(update_scale(summary_title)), build=build,
                                         new_features=filled.new_features, balance=filled.balance,
                                         bug_fixes=filled.bug_fixes)}
    if isinstance(filled, ValueAnswer):
        return {"value": ValueDetail(
            target=filled.target, kind=ValueKind(filled.kind), value=filled.value, changed_in=filled.changed_in,
            previous=filled.previous,
            history=[ValueChangeDetail(attribute=h.attribute, version=h.version, date=h.date, before=h.before, after=h.after)
                     for h in filled.history])}
    if isinstance(filled, ScheduleAnswer):
        return {"schedule": ScheduleDetail(items=[
            ScheduleItemDetail(name=i.name, kind=ScheduleKind(i.kind), start=i.start, end=i.end, status=i.status)
            for i in filled.items])}
    if isinstance(filled, ContentAnswer):
        return {"content": ContentDetail(name=filled.name, form=ContentForm(filled.form),
                                         release_date=filled.release_date, status=filled.status,
                                         highlights=filled.highlights)}
    return {}
