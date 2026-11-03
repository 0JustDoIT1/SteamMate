"use client";

import { keepPreviousData, type Query, useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch, type Schemas } from "@/lib/api/client";

export type Library = Schemas["LibraryResponse"];
export type LibraryGame = Schemas["LibraryGame"];
export type Recommendations = Schemas["RecommendationsResponse"];
export type Recommendation = Schemas["Recommendation"];
export type ReasonFactor = Schemas["ReasonFactor"];
export type StoreRecommendations = Schemas["StoreRecommendationsResponse"];
export type StoreRecommendation = Schemas["StoreRecommendation"];
export type Deals = Schemas["DealsResponse"];
export type DealItem = Schemas["DealItem"];

const POLL_MS = 5_000;
// 메타데이터가 계속 PENDING이어도 무한히 묻지 않도록 약 5분에서 멈춘다.
const MAX_POLLS = 60;

/** 서버가 장르·가격을 채우는 동안 주기적으로 다시 받는다. 수집 중인 항목이 없으면 멈춘다. */
function pollWhile<T>(collecting: (data: T) => boolean) {
  return (query: Query<T, Error>) => {
    const { data, dataUpdateCount } = query.state;
    return data && collecting(data) && dataUpdateCount < MAX_POLLS ? POLL_MS : false;
  };
}

function pollWhilePending<T extends { metadataCoverage: { pending: number } }>(query: Query<T, Error>) {
  return pollWhile((d: T) => d.metadataCoverage.pending > 0)(query);
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

export function useMyRecommendations(enabled: boolean, exclude: number[]) {
  return useQuery({
    queryKey: ["recommendations", exclude],
    queryFn: () => {
      const params = new URLSearchParams();
      for (const appid of exclude) params.append("exclude", String(appid));
      return apiFetch<Recommendations>(`/me/recommendations?${params}`);
    },
    enabled,
    // 제외 목록을 바꾸는 동안 이전 결과를 유지해 화면이 비지 않게 한다.
    placeholderData: keepPreviousData,
    refetchInterval: pollWhilePending,
    retry: retryUnlessUserError,
  });
}

export function useStoreRecommendations(enabled: boolean, onSaleOnly: boolean) {
  return useQuery({
    queryKey: ["store-recommendations", onSaleOnly],
    queryFn: () => apiFetch<StoreRecommendations>(`/me/store-recommendations?onSaleOnly=${onSaleOnly}`),
    enabled,
    placeholderData: keepPreviousData,
    refetchInterval: pollWhile(
      (d: StoreRecommendations) => d.pricePending > 0 || d.metadataPending > 0 || d.metadataCoverage.pending > 0,
    ),
    // 최초 수집 전(DATA_NOT_READY)은 재시도해도 바로 바뀌지 않는다.
    retry: (count, error) => !(error instanceof ApiError && error.code === "DATA_NOT_READY") && retryUnlessUserError(count, error),
  });
}

export function useMyDeals(enabled: boolean) {
  return useQuery({
    queryKey: ["deals"],
    queryFn: () => apiFetch<Deals>("/me/deals"),
    enabled,
    refetchInterval: pollWhile((d: Deals) => d.pricePending > 0),
    retry: retryUnlessUserError,
  });
}
