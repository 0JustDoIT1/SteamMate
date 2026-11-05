"""뉴스 질문용 LLM 호출부. 로컬 Ollama REST를 기존 httpx로 부른다(PRD v6.7).

- 서버 기동 시 연결하지 않고 HTTP 클라이언트도 첫 질문 때 만든다. Ollama가 없는 배포 환경에서도 서버는 뜬다.
- 연결 실패·시간 초과·모델 없음·응답 형식 이상은 모두 AI_UNAVAILABLE. 로그에 프롬프트·답변 본문을 남기지 않는다.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

EMBED_BATCH = 32


@dataclass(frozen=True)
class ChatResult:
    content: str
    prompt_tokens: int
    done_reason: str | None


class LlmClient(Protocol):
    model: str

    async def chat(self, system: str, user: str, num_ctx: int, schema: dict | None = None) -> ChatResult: ...
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Message(_Loose):
    content: str


class _ChatBody(_Loose):
    message: _Message
    prompt_eval_count: int = 0
    done_reason: str | None = None


class _EmbedBody(_Loose):
    embeddings: list[list[float]]


def _unavailable(message: str = "AI 답변 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.") -> AppError:
    return AppError(ErrorCode.AI_UNAVAILABLE, message, 503)


class OllamaLlm:
    def __init__(self, base_url: str, timeout: float, model: str, embed_model: str, num_predict: int,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url
        self._timeout = timeout  # 요청 한 번(채팅·임베딩 묶음)의 한도
        self._transport = transport  # 테스트용
        self._http: httpx.AsyncClient | None = None
        self.model = model
        self._embed_model = embed_model
        self._num_predict = num_predict

    async def chat(self, system: str, user: str, num_ctx: int, schema: dict | None = None) -> ChatResult:
        """schema를 주면 Ollama가 그 JSON 구조로만 답하게 강제한다(format)."""
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "think": False,
            "options": {"num_ctx": num_ctx, "num_predict": self._num_predict, "temperature": 0, "seed": 1},
        }
        if schema is not None:
            payload["format"] = schema
        body = await self._post("/api/chat", payload)
        try:
            parsed = _ChatBody.model_validate(body)
        except ValidationError as exc:
            logger.warning("ollama chat schema mismatch")
            raise _unavailable() from exc
        return ChatResult(parsed.message.content, parsed.prompt_eval_count, parsed.done_reason)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            body = await self._post("/api/embed", {"model": self._embed_model, "input": batch})
            try:
                vectors = _EmbedBody.model_validate(body).embeddings
            except ValidationError as exc:
                logger.warning("ollama embed schema mismatch")
                raise _unavailable() from exc
            if len(vectors) != len(batch):
                logger.warning("ollama embed count mismatch: %s != %s", len(vectors), len(batch))
                raise _unavailable()
            out.extend(vectors)
        return out

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def _post(self, path: str, payload: dict) -> object:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout, transport=self._transport)
        try:
            res = await self._http.post(path, json=payload)
        except httpx.TimeoutException as exc:
            logger.warning("ollama timeout: %s", path)
            raise _unavailable("AI 답변이 너무 오래 걸려 중단했습니다. 질문 범위를 줄여 다시 시도해 주세요.") from exc
        except httpx.HTTPError as exc:
            logger.warning("ollama request failed: %s %s", path, type(exc).__name__)
            raise _unavailable() from exc
        if res.status_code != 200:
            # 404 = 모델 미설치. 응답 본문에는 프롬프트가 없지만 길 수 있어 상태만 남긴다.
            logger.warning("ollama unexpected status: %s HTTP %s", path, res.status_code)
            raise _unavailable()
        try:
            return res.json()
        except ValueError as exc:
            logger.warning("ollama invalid json: %s", path)
            raise _unavailable() from exc
