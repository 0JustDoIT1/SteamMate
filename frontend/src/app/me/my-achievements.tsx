"use client";

import { ExternalLink, Lock, Trophy } from "lucide-react";

import GameImage from "@/components/game-image";
import { LoadingStatus, RowListSkeleton } from "@/components/skeleton";
import { useMyAchievements } from "@/features/library/queries";
import { steamStoreUrl } from "@/lib/format";

const PRIVACY_SETTINGS_URL = "https://steamcommunity.com/my/edit/settings";

/** 마무리해 볼 게임(PRD v6.16): 업적을 60% 이상 달성했지만 아직 완료하지 않은 게임 */
export default function NearlyDoneGames() {
  const query = useMyAchievements(true);
  const data = query.data;

  return (
    <section className="panel">
      <header className="flex flex-wrap items-center gap-2.5 px-5 pt-5">
        <Trophy className="size-6 text-amber-300" aria-hidden />
        <h2 className="text-lg font-bold text-white sm:text-xl">마무리해 볼 게임</h2>
        <span className="text-sm text-zinc-400">업적을 거의 다 모은 게임</span>
      </header>
      <div className="px-5 py-4">
        {query.isPending ? (
          <LoadingStatus label="업적을 확인하는 중…">
            <RowListSkeleton count={3} imageClass="w-24 sm:w-32" />
          </LoadingStatus>
        ) : query.isError ? (
          <div role="alert" className="flex items-center gap-3 text-sm text-red-300">
            <span>{query.error.message}</span>
            <button type="button" onClick={() => query.refetch()} className="btn-ghost px-2 py-1 text-xs">
              다시 시도
            </button>
          </div>
        ) : data!.status === "PRIVATE" ? (
          <p className="text-sm text-zinc-400">
            Steam 업적이 비공개라 확인할 수 없습니다.{" "}
            <a href={PRIVACY_SETTINGS_URL} target="_blank" rel="noopener noreferrer" className="text-info underline">
              Steam 공개 설정
            </a>
            에서 &lsquo;게임 세부 정보&rsquo;를 공개로 바꾸면 보입니다.
          </p>
        ) : data!.nearlyDone.length === 0 ? (
          <p className="text-sm text-zinc-500">업적을 60% 이상 모았지만 아직 다 끝내지 않은 게임이 없습니다.</p>
        ) : (
          <ol className="space-y-2">
            {data!.nearlyDone.map((g) => {
              const percent = Math.floor((g.achieved / g.total) * 100);
              return (
                <li
                  key={g.appid}
                  className="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-x-4 gap-y-3 rounded-xl border border-zinc-800 bg-zinc-950/40 p-3 sm:grid-cols-[9rem_minmax(0,1fr)_auto] sm:gap-y-2"
                >
                  <GameImage src={g.headerImage} className="aspect-[460/215] w-full rounded-md sm:row-span-2" />
                  <div className="min-w-0 flex-1 space-y-2">
                    {/* 작은 화면은 달성 개수를 이름 아래 줄로(긴 이름이 잘리지 않게) */}
                    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-2">
                      <p className="truncate font-bold text-white">{g.name}</p>
                      <p className="shrink-0 text-sm tabular-nums text-zinc-300">
                        <span className="font-bold text-white">{g.achieved}</span>/{g.total} · {percent}%
                      </p>
                    </div>
                    <div
                      role="progressbar"
                      aria-label={`${g.name} 업적 달성률`}
                      aria-valuenow={percent}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      className="h-2 overflow-hidden rounded-full bg-zinc-800"
                    >
                      <div className="h-full rounded-full bg-accent" style={{ width: `${percent}%` }} />
                    </div>
                  </div>
                  {/* 남은 업적 줄: 작은 화면은 카드 전체 폭(좁은 열에 칩이 한 줄씩 쌓이지 않게) */}
                  <div className="col-span-2 flex flex-wrap items-center gap-2 sm:col-span-1 sm:col-start-2">
                      <span className="text-xs text-zinc-400">남은 업적 {g.total - g.achieved}개</span>
                      {/* 남은 업적: Steam처럼 미달성(회색) 아이콘 + 이름, 숨겨진 업적은 이름을 감춘다(PRD v6.17) */}
                      {g.remaining.map((r, i) => (
                        <span
                          key={`${r.name ?? "hidden"}-${i}`}
                          className="inline-flex max-w-full items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/80 py-1 pl-1 pr-2.5 text-xs text-zinc-300"
                        >
                          {r.hidden ? (
                            <span className="grid size-7 shrink-0 place-items-center rounded-md bg-zinc-800 text-zinc-500">
                              <Lock className="size-3.5" aria-hidden />
                            </span>
                          ) : r.icon ? (
                            <GameImage src={r.icon} className="size-7 shrink-0 rounded-md" />
                          ) : (
                            <span className="grid size-7 shrink-0 place-items-center rounded-md bg-zinc-800 text-zinc-500">
                              <Trophy className="size-3.5" aria-hidden />
                            </span>
                          )}
                          <span className={`truncate ${r.hidden ? "text-zinc-500" : ""}`}>{r.hidden ? "숨겨진 업적" : r.name}</span>
                        </span>
                      ))}
                      {g.total - g.achieved > g.remaining.length && g.remaining.length > 0 ? (
                        <span className="text-xs text-zinc-500">외 {g.total - g.achieved - g.remaining.length}개</span>
                      ) : null}
                  </div>
                  <a
                    href={steamStoreUrl(g.appid)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-ghost col-span-2 text-xs sm:col-span-1 sm:col-start-3 sm:row-span-2 sm:row-start-1"
                  >
                    Steam 보기
                    <ExternalLink className="size-3.5" aria-hidden />
                  </a>
                </li>
              );
            })}
          </ol>
        )}
        {data && data.status === "OK" ? (
          <p className="mt-3 text-xs text-zinc-500">
            보유 게임 {data.checkedCount}개의 업적 확인 · 모든 업적을 달성한 게임 {data.completedCount}개
          </p>
        ) : null}
      </div>
    </section>
  );
}
