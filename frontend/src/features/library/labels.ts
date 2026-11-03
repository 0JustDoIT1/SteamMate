import type { ReasonFactor } from "./queries";

// 추천 이유·모드 표시명(보유 게임 추천과 살 만한 게임 공용)
export const FACTOR_LABEL: Record<ReasonFactor, string> = {
  GENRE_MATCH: "취향 장르",
  UNPLAYED: "덜 해본 게임",
  RECENT_GENRE: "최근 즐긴 장르",
  RECENTLY_PLAYED: "최근 실행",
  POPULAR: "인기",
  LOW_GENRE_COVERAGE: "참고",
};

export const MODE_LABEL = {
  GENRE_AWARE: "장르 취향 반영",
  PLAYTIME_BASED: "플레이 기록 기준",
} as const;
