"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

// 전역 클라이언트 상태만 둔다. 로그인 상태(steamId)를 포함한 서버 데이터는 TanStack Query 캐시에 둔다.
export type RecommendationOptions = {
  // 살 만한 게임: 할인 중인 게임만 보기
  onSaleOnly: boolean;
};

type AppState = {
  cc: string;
  recOptions: RecommendationOptions;
  excludedAppids: number[];
  selectedAppid: number | null;
  setCc: (cc: string) => void;
  setRecOptions: (options: Partial<RecommendationOptions>) => void;
  toggleExcluded: (appid: number) => void;
  clearExcluded: () => void;
  selectApp: (appid: number | null) => void;
};

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      cc: "kr",
      recOptions: { onSaleOnly: false },
      excludedAppids: [],
      selectedAppid: null,
      setCc: (cc) => set({ cc }),
      setRecOptions: (options) => set((s) => ({ recOptions: { ...s.recOptions, ...options } })),
      toggleExcluded: (appid) =>
        set((s) => ({
          excludedAppids: s.excludedAppids.includes(appid)
            ? s.excludedAppids.filter((id) => id !== appid)
            : [...s.excludedAppids, appid].sort((a, b) => a - b),
        })),
      clearExcluded: () => set({ excludedAppids: [] }),
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
