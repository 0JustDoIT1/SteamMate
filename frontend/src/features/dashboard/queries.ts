"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch, type Schemas } from "@/lib/api/client";

export type Dashboard = Schemas["DashboardResponse"];
export type DashboardSection = Schemas["DashboardSection"];
export type DashboardEntry = Schemas["DashboardEntry"];
export type ChartSource = Schemas["ChartSource"];
export type PeriodRanking = Schemas["PeriodRanking"];

/** 공개 데이터. 로그인 상태가 바뀌면 개인화(보유·취향) 여부가 달라지므로 키에 포함한다. */
export function useDashboard(viewer: string) {
  return useQuery({
    queryKey: ["dashboard", viewer],
    queryFn: () => apiFetch<Dashboard>("/steam/dashboard"),
    staleTime: 5 * 60_000,
    // 최초 수집 전(DATA_NOT_READY)이면 30초마다 다시 확인한다.
    refetchInterval: (query) =>
      query.state.error instanceof ApiError && query.state.error.code === "DATA_NOT_READY" ? 30_000 : false,
    retry: (count, error) => !(error instanceof ApiError && error.code === "DATA_NOT_READY") && count < 1,
  });
}
