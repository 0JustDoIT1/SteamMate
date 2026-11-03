"use client";

import { useState } from "react";
import { Bar, BarChart, XAxis, YAxis } from "recharts";

import GameImage from "@/components/game-image";
import PageTabs from "@/components/page-tabs";
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { STEAM_LOGIN_URL, useMe } from "@/features/auth/queries";
import { type Library, useMyLibrary } from "@/features/library/queries";
import { ApiError } from "@/lib/api/client";
import { useHydrated } from "@/lib/use-hydrated";

import MyDeals from "./my-deals";
import OwnedRecommendations from "./my-recommendations";
import StoreRecommendationsPanel from "./my-store-recommendations";

const PRIVACY_SETTINGS_URL = "https://steamcommunity.com/my/edit/settings";
const GENRES_SHOWN = 10;

function hours(minutes: number) {
  return minutes < 60 ? `${minutes}분` : `${(minutes / 60).toFixed(1)}시간`;
}

export default function MyLibrary() {
  const hydrated = useHydrated();
  const { data: me, isPending: mePending } = useMe();
  const library = useMyLibrary(Boolean(me));

  if (!hydrated || mePending) return <p className="mt-6 text-zinc-500">확인 중…</p>;

  if (!me) {
    return (
      <div className="mt-6 space-y-3">
        <p>내 라이브러리를 보려면 Steam 로그인이 필요합니다.</p>
        <a href={STEAM_LOGIN_URL} className="inline-block rounded-md bg-zinc-900 px-4 py-2 text-white dark:bg-zinc-100 dark:text-zinc-900">
          Steam으로 로그인
        </a>
      </div>
    );
  }

  if (library.isPending) return <p className="mt-6 text-zinc-500">Steam에서 라이브러리를 불러오는 중…</p>;
  if (library.isError) return <LibraryError error={library.error} onRetry={() => library.refetch()} />;

  return <LibraryView library={library.data} />;
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

type MeTab = "RECS" | "STORE" | "DEALS" | "GENRES" | "GAMES";

function LibraryView({ library }: { library: Library }) {
  const { summary } = library;
  const [tab, setTab] = useState<MeTab>("RECS");
  // 가격·후보를 조회하는 탭은 처음 열 때 불러온다. 연 뒤에는 유지하고 보이기만 바꾼다(스크롤·상태 보존).
  const [opened, setOpened] = useState<Set<MeTab>>(() => new Set<MeTab>(["RECS"]));
  const stats = [
    ["보유 게임", `${library.gameCount}개`],
    ["총 플레이", hours(summary.totalPlaytimeMinutes)],
    ["플레이한 게임", `${summary.playedCount}개`],
    ["미플레이", `${summary.unplayedCount}개`],
    ["최근 2주 플레이", `${summary.recentlyPlayedCount}개`],
  ];
  const tabs: { id: MeTab; label: string }[] = [
    { id: "RECS", label: "보유 게임 추천" },
    { id: "STORE", label: "구매 추천" },
    { id: "DEALS", label: "할인" },
    { id: "GENRES", label: "장르 취향" },
    { id: "GAMES", label: `보유 게임 목록 ${library.gameCount}` },
  ];
  const select = (t: MeTab) => {
    setTab(t);
    setOpened((prev) => (prev.has(t) ? prev : new Set(prev).add(t)));
  };
  const panel = (t: MeTab, node: React.ReactNode) => (
    <div className={tab === t ? "" : "hidden"}>{opened.has(t) ? node : null}</div>
  );

  return (
    <div className="mt-6 space-y-6">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {stats.map(([label, value]) => (
          <div key={label} className="rounded-md border border-zinc-200 p-3 dark:border-zinc-800">
            <dt className="text-xs text-zinc-500">{label}</dt>
            <dd className="mt-1 text-lg font-semibold">{value}</dd>
          </div>
        ))}
      </dl>

      {library.gameCount === 0 ? (
        <p className="text-zinc-500">보유한 게임이 없습니다.</p>
      ) : (
        <div className="space-y-4">
          <PageTabs label="내 라이브러리 섹션" tabs={tabs} current={tab} onSelect={select} />
          {panel("RECS", <OwnedRecommendations />)}
          {panel("STORE", <StoreRecommendationsPanel />)}
          {panel("DEALS", <MyDeals />)}
          {panel("GENRES", <GenreDistribution library={library} visible={tab === "GENRES"} />)}
          {panel("GAMES", <GameList library={library} />)}
        </div>
      )}
      <p className="text-xs text-zinc-500">
        조회 시각 {new Date(library.fetchedAt).toLocaleString("ko-KR")} · 라이브러리는 저장하지 않으며 요청할 때마다
        Steam에서 조회합니다.
      </p>
    </div>
  );
}

function GameList({ library }: { library: Library }) {
  return (
    <section className="rounded-lg border border-zinc-200 dark:border-zinc-800">
      <header className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h2 className="font-semibold">보유 게임 목록</h2>
      </header>
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {library.games.map((game) => (
          <li key={game.appid} className="flex items-center gap-3 px-4 py-2">
            <GameImage src={game.headerImage} fallbackSrc={game.iconUrl} className="aspect-[460/215] w-20 rounded" />
            <span className="flex-1 truncate">{game.name}</span>
            {game.playtime2Weeks > 0 && (
              <span className="text-xs text-emerald-600">최근 {hours(game.playtime2Weeks)}</span>
            )}
            <span className="w-20 text-right text-sm tabular-nums text-zinc-600 dark:text-zinc-400">
              {game.playtimeForever > 0 ? hours(game.playtimeForever) : "미플레이"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

const genreConfig = { percent: { label: "취향 비중(%)", color: "var(--chart-1)" } } satisfies ChartConfig;

function GenreDistribution({ library, visible }: { library: Library; visible: boolean }) {
  const { metadataCoverage: c } = library;
  const eligible = c.total - c.notAvailable;
  const genres = library.genreDistribution
    .slice(0, GENRES_SHOWN)
    .map((g) => ({ genre: g.genre, percent: Math.round(g.share * 1000) / 10 }));

  return (
    <section className="rounded-lg border border-zinc-200 dark:border-zinc-800">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h2 className="font-semibold">내 장르 취향</h2>
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
        ) : !visible ? null : (
          // 숨긴 탭 안에서 그리면 차트 크기가 0이 되어 경고가 난다 → 보일 때만 그린다.
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
