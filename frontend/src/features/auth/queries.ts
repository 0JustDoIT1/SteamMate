"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiFetch, type Schemas } from "@/lib/api/client";

export const meQueryKey = ["me"] as const;

/** 로그인 상태. 비로그인(401)은 오류가 아니라 null로 다룬다. */
export function useMe() {
  return useQuery({
    queryKey: meQueryKey,
    queryFn: async (): Promise<Schemas["MeResponse"] | null> => {
      try {
        return await apiFetch<Schemas["MeResponse"]>("/auth/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 5 * 60_000,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      // 개인 데이터 캐시를 모두 비운다.
      queryClient.clear();
      queryClient.setQueryData(meQueryKey, null);
    },
  });
}

// 전체 페이지 이동으로 Steam 로그인 화면에 간다(fetch가 아닌 링크).
export const STEAM_LOGIN_URL = "/api/auth/steam/login";
