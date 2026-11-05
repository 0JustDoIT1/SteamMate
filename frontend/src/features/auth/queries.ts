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

/** 위쪽 바의 닉네임·프로필 사진. 로그인했을 때만 묻고, 실패해도 화면은 기본 표시로 둔다(재시도 안 함). */
export function useMyProfile(enabled: boolean) {
  return useQuery({
    queryKey: ["me", "profile"],
    queryFn: () => apiFetch<Schemas["ProfileResponse"]>("/me/profile"),
    enabled,
    staleTime: 10 * 60_000,
    retry: false,
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
