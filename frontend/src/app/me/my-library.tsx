"use client";

import { CalendarDays, Clock, Gamepad, Gamepad2, Newspaper, Play, type LucideIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { Bar, BarChart, XAxis, YAxis } from "recharts";

import GameImage from "@/components/game-image";
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { STEAM_LOGIN_URL, useMe } from "@/features/auth/queries";
import { type Library, useMyLibrary } from "@/features/library/queries";
import { ApiError } from "@/lib/api/client";
import { useHydrated } from "@/lib/use-hydrated";

/*
 * 내 라이브러리 계열 화면(사이드바 메뉴마다 한 페이지)의 공용 부품.
 * LibraryGate가 로그인·불러오기·비공개 안내를 맡고, 페이지는 라이브러리가 준비된 뒤의 내용만 그린다.
 */

const PRIVACY_SETTINGS_URL = "https://steamcommunity.com/my/edit/settings";
const GENRES_SHOWN = 10;

function hours(minutes: number) {
  return minutes < 60 ? `${minutes}분` : `${(minutes / 60).toFixed(1)}시간`;
}

export default function LibraryGate({ children }: { children: (library: Library) => ReactNode }) {
  const hydrated = useHydrated();
  const { data: me, isPending: mePending } = useMe();
  const library = useMyLibrary(Boolean(me));

  if (!hydrated || mePending) return <p className="mt-6 text-zinc-500">확인 중…</p>;

  if (!me) {
    return (
      <div className="mt-6 space-y-3">
        <p>내 라이브러리를 보려면 Steam 로그인이 필요합니다.</p>
        <a href={STEAM_LOGIN_URL} className="btn-primary">
          Steam으로 로그인
        </a>
      </div>
    );
  }

  if (library.isPending) return <p className="mt-6 text-zinc-500">Steam에서 라이브러리를 불러오는 중…</p>;
  if (library.isError) return <LibraryError error={library.error} onRetry={() => library.refetch()} />;

  return (
    <div className="space-y-6">
      {children(library.data)}
      <p className="border-t border-zinc-800/70 pt-4 text-xs text-zinc-500">
        조회 시각 {new Date(library.data.fetchedAt).toLocaleString("ko-KR")} · 라이브러리는 저장하지 않으며 요청할 때마다
        Steam에서 조회합니다.
      </p>
    </div>
  );
}

function LibraryError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const code = error instanceof ApiError ? error.code : "UNKNOWN_ERROR";

  if (code === "LIBRARY_PRIVATE") {
    return (
      <div className="mt-6 space-y-3 rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
        <p className="font-medium">게임 목록을 볼 수 없습니다.</p>
        <p className="text-sm">{error.message.replace(` (${PRIVACY_SETTINGS_URL})`, "")}</p>
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          <li>Steam 공개 설정을 엽니다.</li>
          <li>&lsquo;내 프로필&rsquo;과 &lsquo;게임 세부 정보&rsquo;를 &lsquo;공개&rsquo;로 바꿉니다.</li>
          <li>이 페이지로 돌아와 다시 불러옵니다.</li>
        </ol>
        <div className="flex gap-2">
          <a href={PRIVACY_SETTINGS_URL} target="_blank" rel="noopener noreferrer" className="rounded-md border border-amber-400 px-3 py-1.5 text-sm">
            Steam 공개 설정 열기
          </a>
          <button type="button" onClick={onRetry} className="rounded-md border border-amber-400 px-3 py-1.5 text-sm">
            다시 불러오기
          </button>
        </div>
      </div>
    );
  }

  return (
    <div role="alert" className="mt-6 space-y-2 rounded-md border border-red-300 bg-red-50 p-4 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
      <p>{error.message}</p>
      <button type="button" onClick={onRetry} className="rounded-md border border-red-400 px-3 py-1.5 text-sm">
        다시 시도
      </button>
    </div>
  );
}

export function LibraryStats({ library }: { library: Library }) {
  const { summary } = library;
  const stats: [string, string, LucideIcon][] = [
    ["보유 게임", `${library.gameCount}개`, Gamepad2],
    ["총 플레이", hours(summary.totalPlaytimeMinutes), Clock],
    ["플레이한 게임", `${summary.playedCount}개`, Play],
    ["미플레이", `${summary.unplayedCount}개`, Gamepad],
    ["최근 2주 플레이", `${summary.recentlyPlayedCount}개`, CalendarDays],
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {stats.map(([label, value, Icon], i) => (
        <div
          key={label}
          className={`panel flex items-center gap-4 p-4 ${i % 2 === 1 ? "bg-[linear-gradient(135deg,rgb(76_52_160/0.45),rgb(20_25_56/0.8))]" : ""}`}
        >
          <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-accent-2/30 bg-accent-2/10 text-[#8fa6ff]">
            <Icon className="size-5" aria-hidden />
          </span>
          <div className="min-w-0">
            <dt className="text-xs text-zinc-400">{label}</dt>
            <dd className="mt-0.5 whitespace-nowrap text-xl font-bold text-white xl:text-2xl">{value}</dd>
          </div>
        </div>
      ))}
    </dl>
  );
}

export function GameList({ library }: { library: Library }) {
  return (
    <section className="panel">
      <header className="flex items-center gap-2 border-b border-zinc-800 px-5 py-4">
        <Gamepad2 className="size-5 text-[#a68bff]" aria-hidden />
        <h2 className="text-lg font-semibold text-white">보유 게임 목록</h2>
        <span className="text-xs text-zinc-500">{library.gameCount}개 · 뉴스 버튼으로 게임별 공식 공지를 봅니다</span>
      </header>
      <ul className="divide-y divide-zinc-800/80">
        {library.games.map((game) => (
          <li key={game.appid} className="flex items-center gap-4 px-5 py-2.5 hover:bg-white/[0.02]">
            <GameImage src={game.headerImage} fallbackSrc={game.iconUrl} className="aspect-[460/215] w-24 rounded-md" />
            <span className="flex-1 truncate font-medium text-zinc-100">{game.name}</span>
            {game.playtime2Weeks > 0 && (
              <span className="text-xs text-emerald-600">최근 {hours(game.playtime2Weeks)}</span>
            )}
            <span className="w-20 text-right text-sm tabular-nums text-zinc-600 dark:text-zinc-400">
              {game.playtimeForever > 0 ? hours(game.playtimeForever) : "미플레이"}
            </span>
            <Link href={`/news/${game.appid}`} className="btn-ghost shrink-0 px-3 py-1 text-xs">
              <Newspaper className="size-3.5" aria-hidden />
              뉴스
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

const genreConfig = { percent: { label: "취향 비중(%)", color: "var(--chart-1)" } } satisfies ChartConfig;

export function GenreDistribution({ library }: { library: Library }) {
  const { metadataCoverage: c } = library;
  const eligible = c.total - c.notAvailable;
  const genres = library.genreDistribution
    .slice(0, GENRES_SHOWN)
    .map((g) => ({ genre: g.genre, percent: Math.round(g.share * 1000) / 10 }));

  return (
    <section className="panel">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 px-5 py-4">
        <h2 className="text-lg font-semibold text-white">내 장르 취향</h2>
        <p className="text-xs text-zinc-500">
          장르 정보 {c.success}/{eligible}개 ({Math.round(c.ratio * 100)}%)
          {c.pending > 0 ? ` · ${c.pending}개 수집 중, 자동 갱신` : ""}
          {c.temporaryError > 0 ? ` · ${c.temporaryError}개 일시 실패(나중에 재시도)` : ""}
          {c.notAvailable > 0 ? ` · 장르 없음 ${c.notAvailable}개 제외` : ""}
        </p>
      </header>
      <div className="px-4 py-3">
        {genres.length === 0 ? (
          <p className="text-sm text-zinc-500">
            {c.pending > 0 ? "장르 정보를 모으는 중입니다…" : "플레이 기록이 있는 게임의 장르 정보가 없습니다."}
          </p>
        ) : (
          <>
            <ChartContainer config={genreConfig} className="aspect-auto w-full" style={{ height: genres.length * 28 + 16 }}>
              <BarChart data={genres} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={6}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="genre" width={120} tickLine={false} axisLine={false} />
                <ChartTooltip cursor={false} content={<ChartTooltipContent hideIndicator />} />
                <Bar dataKey="percent" fill="var(--color-percent)" radius={4} isAnimationActive={false} />
              </BarChart>
            </ChartContainer>
            <p className="mt-2 text-xs text-zinc-500">
              장르별 플레이 시간에 로그를 씌워 합한 비중입니다. 오래 한 게임 하나가 분포를 독차지하지 않게 하며, 추천의 &lsquo;취향
              장르&rsquo;와 같은 값입니다.
            </p>
          </>
        )}
      </div>
    </section>
  );
}
