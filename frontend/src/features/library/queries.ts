"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError, apiFetch, type Schemas } from "@/lib/api/client";

export type Library = Schemas["LibraryResponse"];
export type LibraryGame = Schemas["LibraryGame"];

export function useMyLibrary(enabled: boolean) {
  return useQuery({
    queryKey: ["library"],
    queryFn: () => apiFetch<Library>("/me/library"),
    enabled,
    // 비공개·로그인 필요 같은 사용자 상태 오류는 재시도해도 바뀌지 않는다.
    retry: (count, error) =>
      !(error instanceof ApiError && [401, 403, 404].includes(error.status)) && count < 1,
  });
}
