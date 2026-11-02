"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

// 전역 클라이언트 상태만 둔다. 서버 데이터(라이브러리·추천·할인 등)는 TanStack Query 캐시에 둔다.
export type RecommendationOptions = {
  preferUnplayed: boolean;
};

type AppState = {
  steamId: string | null;
  cc: string;
  recOptions: RecommendationOptions;
  excludedAppids: number[];
  selectedAppid: number | null;
  setSteamId: (steamId: string | null) => void;
  setCc: (cc: string) => void;
  setRecOptions: (options: Partial<RecommendationOptions>) => void;
  toggleExcluded: (appid: number) => void;
  selectApp: (appid: number | null) => void;
};

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      steamId: null,
      cc: "kr",
      recOptions: { preferUnplayed: true },
      excludedAppids: [],
      selectedAppid: null,
      setSteamId: (steamId) => set({ steamId }),
      setCc: (cc) => set({ cc }),
      setRecOptions: (options) => set((s) => ({ recOptions: { ...s.recOptions, ...options } })),
      toggleExcluded: (appid) =>
        set((s) => ({
          excludedAppids: s.excludedAppids.includes(appid)
            ? s.excludedAppids.filter((id) => id !== appid)
            : [...s.excludedAppids, appid].sort((a, b) => a - b),
        })),
      selectApp: (selectedAppid) => set({ selectedAppid }),
    }),
    {
      name: "steammate",
      storage: createJSONStorage(() => localStorage),
      // 추천 제외 목록만 브라우저에 보관한다(PRD: 클라이언트 전용 저장).
      partialize: (s) => ({ excludedAppids: s.excludedAppids }),
    },
  ),
);
