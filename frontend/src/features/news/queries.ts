"use client";

import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch, type Schemas } from "@/lib/api/client";

export type News = Schemas["NewsResponse"];
export type NewsItem = Schemas["NewsItem"];
export type AskRequest = Schemas["AskRequest"];
export type AskResponse = Schemas["AskResponse"];
export type NewsFeed = Schemas["NewsFeedResponse"];

const PAGE_SIZE = 10;

/** 게임 공식 뉴스(발췌·원문 링크). 공개 데이터라 로그인과 무관하다. "더 보기"는 nextBefore로 이전 글을 받는다. */
export function useGameNews(appid: number) {
  return useInfiniteQuery({
    queryKey: ["news", appid],
    queryFn: ({ pageParam }) =>
      apiFetch<News>(`/steam/news/${appid}?count=${PAGE_SIZE}${pageParam ? `&before=${pageParam}` : ""}`),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.nextBefore,
    staleTime: 10 * 60_000,
    // 없는 게임(404)·잘못된 입력(422)은 다시 시도해도 같다.
    retry: (count, error) => !(error instanceof ApiError && [404, 422].includes(error.status)) && count < 1,
  });
}

/** 뉴스 AI 질문. 답변은 이 mutation 상태로만 보여 주고 다른 곳에 복제하지 않는다. */
export function useAskNews() {
  return useMutation({
    mutationFn: (body: AskRequest) =>
      apiFetch<AskResponse>("/steam/news/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
  });
}

/** 내 게임 소식: 최근 플레이한 게임들의 최신 공지(PRD v6.15). 서버가 10분 캐시를 쓰므로 화면도 그만큼 둔다. */
export function useNewsFeed(enabled: boolean) {
  return useQuery({
    queryKey: ["me", "news-feed"],
    queryFn: () => apiFetch<NewsFeed>("/me/news-feed"),
    enabled,
    staleTime: 10 * 60_000,
  });
}

/**
 * 질문 칸을 누르면 서버에 공지 수집·검색 색인을 미리 시켜 첫 질문 대기를 줄인다(PRD v6.15).
 * 결과를 기다리지 않고, 실패해도 무시한다(질문할 때 다시 준비하고 그때 오류를 알린다).
 */
export function warmupAsk(appid: number): void {
  apiFetch(`/steam/news/${appid}/ask/warmup`, { method: "POST" }).catch(() => undefined);
}
