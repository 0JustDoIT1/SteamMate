import type { Recommendation, ReasonFactor } from "./queries";

// 추천 이유·모드 표시명(보유 게임 추천과 살 만한 게임 공용)
export const FACTOR_LABEL: Record<ReasonFactor, string> = {
  GENRE_MATCH: "취향 장르",
  UNPLAYED: "짧게 해본 게임",
  RECENT_GENRE: "최근 즐긴 장르",
  RECENTLY_PLAYED: "최근 실행",
  POPULAR: "인기",
  LOW_GENRE_COVERAGE: "참고",
};

export const MODE_LABEL = {
  GENRE_AWARE: "장르 취향 반영",
  PLAYTIME_BASED: "플레이 기록 기준",
} as const;

type Reason = Recommendation["reasons"][number];

/** 이유 이름. 2시간 미만 플레이(UNPLAYED)는 아예 안 했으면 "미플레이 게임", 조금 했으면 "짧게 해본 게임" */
export function reasonLabel(r: Reason): string {
  if (r.factor === "UNPLAYED" && r.detail === "미플레이") return "미플레이 게임";
  return FACTOR_LABEL[r.factor];
}

/** 이유 설명. 이름에 이미 담긴 "미플레이"는 되풀이하지 않는다 */
export function reasonDetail(r: Reason): string | null | undefined {
  return r.factor === "UNPLAYED" && r.detail === "미플레이" ? null : r.detail;
}
