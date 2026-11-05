"use client";

import { useState } from "react";
import { Bar, BarChart, XAxis, YAxis } from "recharts";

import GameImage from "@/components/game-image";
import Sparkline from "@/components/sparkline";
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { useMe } from "@/features/auth/queries";
import {
  type ChartSource,
  type Dashboard,
  type DashboardEntry,
  type DashboardSection,
  type PeriodRanking,
  useDashboard,
} from "@/features/dashboard/queries";
import { ApiError } from "@/lib/api/client";
import { formatCount, formatDateTime, formatPrice, steamStoreUrl } from "@/lib/format";
import { useHydrated } from "@/lib/use-hydrated";

const ROWS_COLLAPSED = 10;
const OUT_OF_CHART_RANK = 101;

// 순위 차트는 모두 전 세계 기준(최다 플레이·접속은 국가별 제공이 없어 판매 순위도 맞춤)
const SECTION_META: Record<ChartSource, { title: string; note: string }> = {
  TOP_SELLERS: { title: "판매 순위", note: "전 세계 Steam 주간 매출 기준" },
  CONCURRENT: { title: "실시간 접속 순위", note: "전 세계 현재 동시 접속 기준" },
  MOST_PLAYED: { title: "주간 접속 순위", note: "전 세계 주간 최고 동시 접속 기준" },
  SPECIALS: { title: "할인 게임", note: "Steam 상점 할인 기획 · 가격은 한국 상점 기준" },
  NEW_RELEASES: { title: "신작 게임", note: "Steam 상점 신작 기획 · 가격은 한국 상점 기준" },
};
// 추이 그래프가 있는 섹션을 위쪽에 둔다.
const LAYOUT_ORDER: ChartSource[] = ["TOP_SELLERS", "CONCURRENT", "MOST_PLAYED", "SPECIALS", "NEW_RELEASES"];

export default function DashboardView() {
  const hydrated = useHydrated();
  const { data: me, isPending: mePending } = useMe();
  const viewer = me?.steamId ?? "anon";
  const dashboard = useDashboard(viewer);

  if (!hydrated || mePending || dashboard.isPending) {
    return <p className="mt-10 text-zinc-500">인기 게임을 불러오는 중…</p>;
  }
  if (dashboard.isError) {
    const notReady = dashboard.error instanceof ApiError && dashboard.error.code === "DATA_NOT_READY";
    return (
      <p role="status" className="mt-10 rounded-md border border-zinc-200 p-4 text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
        {notReady ? "인기 게임 데이터를 처음 수집하는 중입니다. 잠시 후 자동으로 표시됩니다." : dashboard.error.message}
      </p>
    );
  }
  return <DashboardBody data={dashboard.data} />;
}

type MainTab = ChartSource | "GENRES";
const MAIN_TAB_LABEL: Record<MainTab, string> = {
  TOP_SELLERS: "판매 순위",
  CONCURRENT: "실시간 접속 순위",
  MOST_PLAYED: "주간 접속 순위",
  SPECIALS: "할인 게임",
  NEW_RELEASES: "신작 게임",
  GENRES: "장르 순위",
};

function DashboardBody({ data }: { data: Dashboard }) {
  const sections = LAYOUT_ORDER.map((s) => data.sections.find((x) => x.source === s)).filter(
    (s): s is DashboardSection => s != null,
  );
  const tabs: MainTab[] = [...sections.map((s) => s.source), ...(data.genreDistribution.genres.length ? ["GENRES" as const] : [])];
  // 메인 탭 선택은 이 화면에서만 쓰는 상태라 컴포넌트 로컬 상태로 둔다.
  const [selected, setSelected] = useState<MainTab>(tabs[0]);
  const current = tabs.includes(selected) ? selected : tabs[0];

  return (
    <div className="mt-8 space-y-4">
      {/* 좁은 화면에서는 가로로만 넘긴다. 아래 구분선은 inset 그림자로 그려 탭 밑줄이 영역을 넘치지 않게 한다(세로 스크롤바 방지). */}
      <div
        role="tablist"
        aria-label="대시보드 섹션"
        className="flex gap-1 overflow-x-auto overflow-y-hidden shadow-[inset_0_-1px_0_var(--border)] [scrollbar-width:none]"
      >
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={current === t}
            onClick={() => setSelected(t)}
            className={`shrink-0 border-b-2 px-3 py-2 text-sm font-medium ${
              current === t
                ? "border-accent font-semibold text-white"
                : "border-transparent text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
            }`}
          >
            {MAIN_TAB_LABEL[t]}
          </button>
        ))}
      </div>
      {data.personalized ? (
        <p className="text-xs text-zinc-500">보유한 게임과 내 플레이 장르 기준 취향 매칭도를 함께 표시합니다.</p>
      ) : null}
      {/* 섹션도 미리 만들어 두고 보이기만 바꾼다(스크롤 보정 방지). 숨긴 섹션의 그래프는 그리지 않는다. */}
      {sections.map((section) => (
        <div key={section.source} className={current === section.source ? "block" : "hidden"}>
          <Panel section={section} visible={current === section.source} />
        </div>
      ))}
      {tabs.includes("GENRES") ? (
        <div className={current === "GENRES" ? "block" : "hidden"}>
          {current === "GENRES" ? <GenrePanel data={data} /> : null}
        </div>
      ) : null}
    </div>
  );
}

type Tab = "WEEK" | PeriodRanking["period"];
const TAB_LABEL: Record<Tab, string> = { WEEK: "주간", MONTH: "월간", YEAR: "연간" };

function Panel({ section, visible }: { section: DashboardSection; visible: boolean }) {
  const meta = SECTION_META[section.source];
  // 탭·펼치기는 이 패널에서만 쓰는 화면 상태라 컴포넌트 로컬 상태로 둔다.
  const [tab, setTab] = useState<Tab>("WEEK");
  const [expanded, setExpanded] = useState(false);
  const ready = section.periods.filter((p) => p.weeksIncluded > 1);
  const views: { tab: Tab; period: PeriodRanking | null; entries: DashboardEntry[] }[] = [
    { tab: "WEEK", period: null, entries: section.entries },
    ...ready.map((p) => ({ tab: p.period as Tab, period: p, entries: p.entries })),
  ];
  const active = views.find((v) => v.tab === tab) ?? views[0];
  const total = Math.max(...views.map((v) => v.entries.length));

  return (
    <section className="panel">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 px-5 py-4">
        <div className="flex items-center gap-3">
          <h2 className="sr-only">{meta.title}</h2>
          {views.length > 1 ? (
            <div role="tablist" className="flex rounded-md border border-zinc-200 text-xs dark:border-zinc-800">
              {views.map(({ tab: t }) => (
                <button
                  key={t}
                  type="button"
                  role="tab"
                  aria-selected={active.tab === t}
                  onClick={() => setTab(t)}
                  className={`px-2.5 py-1 first:rounded-l-md last:rounded-r-md ${
                    active.tab === t ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : ""
                  }`}
                >
                  {TAB_LABEL[t]}
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <p className="text-xs text-zinc-500">
          {active.period
            ? `최근 ${active.period.weeksIncluded}주 주간 순위 합산 · Steam 공식 ${TAB_LABEL[active.period.period]} 순위 아님`
            : `${meta.note} · ${formatDateTime(section.snapshotAt)}`}
        </p>
      </header>
      <ColumnHeader source={section.source} aggregated={active.period != null} />
      {/* 탭마다 목록을 미리 만들어 두고 보이기만 바꾼다(목록을 바꿔 끼우면 브라우저 스크롤 보정으로 페이지가 움직임). */}
      {views.map(({ tab: t, period, entries }) => (
        <ol key={t} aria-hidden={active.tab !== t} className={active.tab === t ? "block [overflow-anchor:none]" : "hidden"}>
          {entries.slice(0, expanded ? undefined : ROWS_COLLAPSED).map((entry) => (
            <Row key={entry.appid} entry={entry} section={section} aggregated={period != null} visible={visible && active.tab === t} />
          ))}
        </ol>
      ))}
      {total > ROWS_COLLAPSED ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="w-full border-t border-zinc-200 py-2 text-xs text-zinc-500 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
        >
          {expanded ? "접기" : `${total}위까지 보기`}
        </button>
      ) : null}
    </section>
  );
}

// 열 구성: 순위 | 이미지 | 이름·장르 | 수치 열(섹션별) | 추이
const ROW_GRID = "grid grid-cols-[1.75rem_5.5rem_minmax(0,1fr)_auto] items-center gap-3 px-4";

function ColumnHeader({ source, aggregated }: { source: ChartSource; aggregated: boolean }) {
  const cols = columnsFor(source, aggregated);
  return (
    <div className={`${ROW_GRID} py-2 text-[11px] text-zinc-500`}>
      <span>#</span>
      <span />
      <span>게임</span>
      <span className="flex gap-3 text-right">
        {cols.map((c) => (
          <span key={c} className={c === "추이" ? "w-36 text-center" : "w-20"}>
            {c}
          </span>
        ))}
      </span>
    </div>
  );
}

function columnsFor(source: ChartSource, aggregated: boolean): string[] {
  switch (source) {
    case "TOP_SELLERS":
      return [aggregated ? "순위권" : "변동", "추이"];
    case "CONCURRENT":
      return ["현재", "24h 최고", "추이"];
    case "MOST_PLAYED":
      return ["변동", "주간 최고"];
    default:
      return ["할인", "가격"];
  }
}

type RowProps = { entry: DashboardEntry; section: DashboardSection; aggregated: boolean; visible: boolean };

function Row({ entry, section, aggregated, visible }: RowProps) {
  return (
    <li className="border-t border-zinc-100 first:border-t-0 dark:border-zinc-900">
      <a
        href={steamStoreUrl(entry.appid)}
        target="_blank"
        rel="noopener noreferrer"
        className={`${ROW_GRID} py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-900`}
      >
        <span className="text-sm tabular-nums text-zinc-500">{entry.rank}</span>
        <GameImage src={entry.imageUrl} className="aspect-[460/215] w-full rounded-sm" />
        <span className="min-w-0">
          <span className="flex items-center gap-1.5">
            <span className="truncate text-sm" title={entry.name}>
              {entry.name}
            </span>
            {entry.owned ? <span className="shrink-0 rounded bg-zinc-200 px-1 text-[10px] dark:bg-zinc-800">보유</span> : null}
          </span>
          <span className="block truncate text-[11px] text-zinc-500">
            {[entry.genres.slice(0, 2).join(" · "), entry.affinity != null ? `취향 ${Math.round(entry.affinity * 100)}%` : ""]
              .filter(Boolean)
              .join("  ·  ") || " "}
          </span>
        </span>
        <span className="flex items-center gap-3 text-right text-xs tabular-nums">
          <Cells entry={entry} section={section} aggregated={aggregated} visible={visible} />
        </span>
      </a>
    </li>
  );
}

function Cells({ entry, section, aggregated, visible }: RowProps) {
  // 숨겨진 탭에서는 같은 크기의 빈 칸만 둔다(크기 0 상태로 차트를 그리지 않음, 레이아웃은 그대로).
  const trend = visible && entry.trend && section.trendTimes.length > 0 ? (
    <span className="flex w-36 justify-center">
      <Sparkline
        times={section.trendTimes}
        values={entry.trend}
        invert={section.source === "TOP_SELLERS"}
        // 판매 순위: 100위 밖인 주는 바닥선(101)으로 이어 그린다. 접속: 빠진 구간은 앞뒤를 잇는다.
        missing={section.source === "TOP_SELLERS" ? { value: OUT_OF_CHART_RANK, label: "100위 밖" } : "connect"}
        formatTime={section.source === "TOP_SELLERS" ? weekLabel : hourLabel}
        formatValue={section.source === "TOP_SELLERS" ? (v) => `${v}위` : (v) => `${v.toLocaleString("ko-KR")}명`}
        label={`${entry.name} ${section.source === "TOP_SELLERS" ? "최근 12주 순위" : "최근 7일 동시 접속"} 추이`}
      />
    </span>
  ) : (
    <span className="h-8 w-36" />
  );

  switch (section.source) {
    case "TOP_SELLERS":
      return (
        <>
          <span className="w-20">
            {aggregated ? (
              <span className="text-zinc-500" title={`최고 ${entry.bestRank}위`}>
                {entry.weeksCharted}주
              </span>
            ) : (
              <RankDelta entry={entry} />
            )}
          </span>
          {trend}
        </>
      );
    case "CONCURRENT":
      return (
        <>
          <span className="w-20">{formatCount(entry.metricValue) ?? "—"}</span>
          <span className="w-20 text-zinc-500">{formatCount(entry.dayPeak) ?? "—"}</span>
          {trend}
        </>
      );
    case "MOST_PLAYED":
      return (
        <>
          <span className="w-20">
            <RankDelta entry={entry} />
          </span>
          <span className="w-20">{formatCount(entry.metricValue) ?? "—"}</span>
        </>
      );
    default:
      return (
        <>
          <span className="w-20">
            {entry.discountPercent ? (
              <span className="rounded bg-emerald-500 px-1.5 text-white">-{entry.discountPercent}%</span>
            ) : null}
          </span>
          <span className="w-20">
            {entry.discountPercent && entry.originalPrice ? (
              <span className="block text-[10px] text-zinc-400 line-through">
                {formatPrice(entry.originalPrice, entry.currency)}
              </span>
            ) : null}
            {formatPrice(entry.finalPrice, entry.currency) ?? "—"}
          </span>
        </>
      );
  }
}

function RankDelta({ entry }: { entry: DashboardEntry }) {
  if (entry.isNew) return <span className="font-medium text-sky-600">NEW</span>;
  if (entry.rankDelta == null) return <span className="text-zinc-400">—</span>;
  if (entry.rankDelta > 0) return <span className="text-emerald-600">▲{entry.rankDelta}</span>;
  if (entry.rankDelta < 0) return <span className="text-rose-600">▼{-entry.rankDelta}</span>;
  return <span className="text-zinc-400">–</span>;
}

function weekLabel(iso: string) {
  return `${new Date(iso).toLocaleDateString("ko-KR", { month: "short", day: "numeric" })} 주`;
}

function hourLabel(iso: string) {
  return new Date(iso).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "numeric" });
}

const genreConfig = { count: { label: "게임 수", color: "var(--chart-1)" } } satisfies ChartConfig;

function GenrePanel({ data }: { data: Dashboard }) {
  const { genres, basedOn, withGenres } = data.genreDistribution;
  if (genres.length === 0) return null;
  return (
    <section className="panel">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 px-5 py-4">
        <h2 className="text-lg font-semibold text-white">이번 주 장르 순위</h2>
        <p className="text-xs text-zinc-500">
          판매 순위·주간 접속 순위 {basedOn}개 중 장르 정보가 있는 {withGenres}개 기준
        </p>
      </header>
      <div className="px-4 py-3">
        <ChartContainer config={genreConfig} className="aspect-auto h-72 w-full">
          <BarChart data={genres} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={6}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="genre" width={120} tickLine={false} axisLine={false} />
            <ChartTooltip cursor={false} content={<ChartTooltipContent hideIndicator />} />
            <Bar dataKey="count" fill="var(--color-count)" radius={4} isAnimationActive={false} />
          </BarChart>
        </ChartContainer>
      </div>
    </section>
  );
}
