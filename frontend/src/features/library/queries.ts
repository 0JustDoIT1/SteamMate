"use client";

import { keepPreviousData, type Query, useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch, type Schemas } from "@/lib/api/client";

export type Library = Schemas["LibraryResponse"];
export type LibraryGame = Schemas["LibraryGame"];
export type Recommendations = Schemas["RecommendationsResponse"];
export type Recommendation = Schemas["Recommendation"];
export type ReasonFactor = Schemas["ReasonFactor"];

const POLL_MS = 5_000;
// 메타데이터가 계속 PENDING이어도 무한히 묻지 않도록 약 5분에서 멈춘다.
const MAX_POLLS = 60;

/** 서버가 장르 정보를 백그라운드로 채우는 동안(pending > 0) 주기적으로 다시 받아 coverage를 갱신한다. */
function pollWhilePending<T extends { metadataCoverage: { pending: number } }>(query: Query<T, Error>) {
  const { data, dataUpdateCount } = query.state;
  return data && data.metadataCoverage.pending > 0 && dataUpdateCount < MAX_POLLS ? POLL_MS : false;
}

// 비공개·로그인 필요 같은 사용자 상태 오류는 재시도해도 바뀌지 않는다.
const retryUnlessUserError = (count: number, error: Error) =>
  !(error instanceof ApiError && [401, 403, 404, 422].includes(error.status)) && count < 1;

export function useMyLibrary(enabled: boolean) {
  return useQuery({
    queryKey: ["library"],
    queryFn: () => apiFetch<Library>("/me/library"),
    enabled,
    refetchInterval: pollWhilePending,
    retry: retryUnlessUserError,
  });
}

export function useMyRecommendations(enabled: boolean, preferUnplayed: boolean, exclude: number[]) {
  return useQuery({
    queryKey: ["recommendations", preferUnplayed, exclude],
    queryFn: () => {
      const params = new URLSearchParams({ preferUnplayed: String(preferUnplayed) });
      for (const appid of exclude) params.append("exclude", String(appid));
      return apiFetch<Recommendations>(`/me/recommendations?${params}`);
    },
    enabled,
    // 옵션·제외를 바꾸는 동안 이전 결과를 유지해 화면이 비지 않게 한다.
    placeholderData: keepPreviousData,
    refetchInterval: pollWhilePending,
    retry: retryUnlessUserError,
  });
}
