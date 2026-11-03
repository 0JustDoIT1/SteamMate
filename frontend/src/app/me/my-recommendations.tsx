"use client";

import GameImage from "@/components/game-image";
import { FACTOR_LABEL, MODE_LABEL } from "@/features/library/labels";
import { type Recommendation, useMyRecommendations } from "@/features/library/queries";
import { formatDateTime, steamStoreUrl } from "@/lib/format";
import { useHydrated } from "@/lib/use-hydrated";
import { useAppStore } from "@/stores/app-store";

/** 보유 게임 추천(F3): 2시간 미만 플레이한 보유 게임 중 취향·덜 해본 정도로 TOP 3. */
export default function OwnedRecommendations() {
  // 제외 목록은 브라우저 저장소에서 복원되므로 hydration 뒤에 요청해야 첫 요청부터 반영된다.
  const hydrated = useHydrated();
  const excluded = useAppStore((s) => s.excludedAppids);
  const toggleExcluded = useAppStore((s) => s.toggleExcluded);
  const clearExcluded = useAppStore((s) => s.clearExcluded);
  const query = useMyRecommendations(hydrated, excluded);
  const data = query.data;
  // 장르 수집 중에는 순서 근거가 없는 미플레이 게임을 빼고 조금 해 본 게임만 추천한다("이어서 하기").
  const collecting = data?.recommendationMode === "PLAYTIME_BASED";

  return (
    <section className="rounded-lg border border-zinc-200 dark:border-zinc-800">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <div className="flex items-baseline gap-2">
          <h2 className="font-semibold">{collecting ? "이어서 하기" : "다음에 할 게임"}</h2>
          {data ? <span className="text-xs text-zinc-500">{MODE_LABEL[data.recommendationMode]}</span> : null}
        </div>
      </header>

      <div className="px-4 py-3">
        {query.isPending ? (
          <p className="text-sm text-zinc-500">추천을 계산하는 중…</p>
        ) : query.isError ? (
          <div role="alert" className="flex items-center gap-3 text-sm text-red-700 dark:text-red-300">
            <span>{query.error.message}</span>
            <button type="button" onClick={() => query.refetch()} className="rounded-md border border-red-400 px-2 py-1">
              다시 시도
            </button>
          </div>
        ) : data!.recommendations.length === 0 ? (
          <p className="text-sm text-zinc-500">
            {collecting
              ? "장르 정보를 모으는 중입니다. 조금 해 보다 멈춘 게임이 없어 지금은 추천할 게임이 없고, 수집이 끝나면 미플레이 게임까지 취향에 맞춰 추천합니다."
              : "추천할 게임이 없습니다. 보유 게임 중 2시간 미만으로 플레이한 게임이 후보입니다."}
          </p>
        ) : (
          <ol className={`grid gap-3 sm:grid-cols-3 ${query.isPlaceholderData ? "opacity-60" : ""}`}>
            {data!.recommendations.map((rec, i) => (
              <RecommendationCard key={rec.appid} rank={i + 1} rec={rec} onExclude={() => toggleExcluded(rec.appid)} />
            ))}
          </ol>
        )}

        {data ? (
          <p className="mt-3 text-xs text-zinc-500">
            후보 {data.candidateCount}개 중 상위 {data.recommendations.length}개 · 장르 정보 {data.metadataCoverage.success}/
            {data.metadataCoverage.total - data.metadataCoverage.notAvailable}
            {data.metadataCoverage.pending > 0 ? ` (수집 중 ${data.metadataCoverage.pending}개)` : ""}
            {data.metadataSnapshotAt ? ` · 메타데이터 기준 ${formatDateTime(data.metadataSnapshotAt)}` : ""} · 계산{" "}
            {formatDateTime(data.calculatedAt)}
          </p>
        ) : null}
        {excluded.length > 0 ? (
          <p className="mt-1 text-xs text-zinc-500">
            추천에서 뺀 게임 {excluded.length}개 (이 브라우저에만 저장){" "}
            <button type="button" onClick={clearExcluded} className="underline">
              모두 되돌리기
            </button>
          </p>
        ) : null}
      </div>
    </section>
  );
}

function RecommendationCard({ rank, rec, onExclude }: { rank: number; rec: Recommendation; onExclude: () => void }) {
  return (
    <li className="flex flex-col overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800">
      <a href={steamStoreUrl(rec.appid)} target="_blank" rel="noopener noreferrer">
        <GameImage src={rec.headerImage} className="aspect-[460/215] w-full" />
      </a>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-baseline justify-between gap-2">
          <p className="truncate font-medium">
            <span className="mr-1 text-zinc-500">{rank}.</span>
            {rec.name}
          </p>
          <span className="shrink-0 text-xs tabular-nums text-zinc-500">{Math.round(rec.score * 100)}점</span>
        </div>
        {rec.genres.length > 0 ? <p className="truncate text-xs text-zinc-500">{rec.genres.join(" · ")}</p> : null}
        <ul className="space-y-1 text-sm">
          {rec.reasons.map((r) =>
            r.factor === "LOW_GENRE_COVERAGE" ? (
              <li key={r.factor} className="text-xs text-amber-700 dark:text-amber-400">
                {r.detail}
              </li>
            ) : (
              <li key={r.factor} className="flex justify-between gap-2">
                <span className="truncate">
                  {FACTOR_LABEL[r.factor]}
                  {r.detail ? <span className="text-zinc-500"> · {r.detail}</span> : null}
                </span>
                <span className="shrink-0 tabular-nums text-zinc-500">+{Math.round(r.contribution * 100)}</span>
              </li>
            ),
          )}
        </ul>
        <button
          type="button"
          onClick={onExclude}
          className="mt-auto self-start text-xs text-zinc-500 underline hover:text-zinc-800 dark:hover:text-zinc-200"
        >
          추천에서 빼기
        </button>
      </div>
    </li>
  );
}
