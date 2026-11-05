from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.config import get_settings
from app.deps import get_news, get_qa
from app.errors import AppError, ErrorCode
from app.news import NewsResponse, NewsService
from app.qa.service import AskRequest, AskResponse, NewsQaService

# 게임 공식 뉴스는 공개 데이터라 로그인 없이 볼 수 있다.
router = APIRouter(prefix="/steam", tags=["news"])


@router.get("/news/{appid}", response_model=NewsResponse)
async def game_news(
    appid: Annotated[int, Path(gt=0, le=2_147_483_647)],
    news: Annotated[NewsService, Depends(get_news)],
    count: Annotated[int, Query(ge=1, le=20)] = 10,
    # 이 시각(유닉스 초) 이전 글만. 앞 응답의 nextBefore를 넘긴다.
    before: Annotated[int | None, Query(gt=0)] = None,
) -> NewsResponse:
    res = await news.get(appid, count, before)
    return res.model_copy(update={"ask_enabled": get_settings().news_ai_enabled})


@router.post("/news/ask", response_model=AskResponse)
async def ask_news(body: AskRequest, qa: Annotated[NewsQaService, Depends(get_qa)]) -> AskResponse:
    # 뉴스 본문 AI 처리 권리 확인 전에는 공개 배포에서 끈다(PRD 출시 게이트). Ollama도 켠 환경에서만 부른다.
    if not get_settings().news_ai_enabled:
        raise AppError(ErrorCode.FEATURE_DISABLED, "이 환경에서는 뉴스 AI 질문을 제공하지 않습니다.", 403)
    return await qa.ask(body)
