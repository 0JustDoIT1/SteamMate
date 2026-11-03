from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.deps import get_news
from app.news import NewsResponse, NewsService

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
    return await news.get(appid, count, before)
