"use client";

import { ArrowUpRight, Rss } from "lucide-react";
import Link from "next/link";

import GameImage from "@/components/game-image";
import { LoadingStatus, RowListSkeleton } from "@/components/skeleton";
import { type NewsFeed, useNewsFeed } from "@/features/news/queries";
import { formatDateTime } from "@/lib/format";

type Scale = NonNullable<NewsFeed["items"][number]["scale"]>;

const SCALE: Record<Scale, { label: string; className: string }> = {
  MAJOR: { label: "대형 업데이트", className: "border-accent bg-accent/25 text-white" },
  PATCH: { label: "패치", className: "border-accent-2/60 bg-accent-2/15 text-zinc-100" },
  HOTFIX: { label: "핫픽스", className: "border-amber-400/60 bg-amber-400/10 text-amber-200" },
};

/** "3시간 전", "어제", "5일 전" — 30일이 넘으면 날짜 */
function relative(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 60) return `${Math.max(minutes, 1)}분 전`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.round(hours / 24);
  if (days === 1) return "어제";
  return days <= 30 ? `${days}일 전` : formatDateTime(iso);
}

/** 내 게임 소식(PRD v6.15): 최근 플레이한 게임들의 최신 공식 공지를 날짜순으로 */
export default function NewsFeedPanel() {
  const query = useNewsFeed(true);
  const data = query.data;
  return (
    <section className="panel">
      <header className="flex flex-wrap items-center gap-2 border-b border-zinc-800 px-5 py-4">
        <Rss className="size-5 text-accent-soft" aria-hidden />
        <h2 className="text-lg font-semibold text-white">내 게임 최근 소식</h2>
        <span className="text-xs text-zinc-500">최근 플레이한 게임의 공식 공지</span>
      </header>
      <div className="px-4 py-3 sm:px-5">
        {query.isPending ? (
          <LoadingStatus label="내 게임 소식을 불러오는 중…">
            <RowListSkeleton count={4} imageClass="w-20" />
          </LoadingStatus>
        ) : query.isError ? (
          <div role="alert" className="flex items-center gap-3 text-sm text-red-300">
            <span>{query.error.message}</span>
            <button type="button" onClick={() => query.refetch()} className="btn-ghost px-2 py-1 text-xs">
              다시 시도
            </button>
          </div>
        ) : data!.items.length === 0 ? (
          <p className="text-sm text-zinc-500">최근 플레이한 게임의 공식 공지가 없습니다.</p>
        ) : (
          <ol className="divide-y divide-zinc-800/80">
            {data!.items.map((item) => {
              const href = item.externalUrl ?? item.url;
              return (
                <li key={`${item.appid}-${item.gid}`} className="flex items-center gap-3 py-3 sm:gap-4">
                  <Link href={`/news/${item.appid}`} className="shrink-0" title={`${item.gameName} 공지 모두 보기`}>
                    <GameImage src={item.headerImage} className="aspect-[460/215] w-20 rounded-md sm:w-28" />
                  </Link>
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <Link href={`/news/${item.appid}`} className="font-medium text-info hover:text-white">
                        {item.gameName}
                      </Link>
                      {item.scale ? (
                        <span className={`rounded-full border px-2 py-0.5 ${SCALE[item.scale].className}`}>
                          {SCALE[item.scale].label}
                        </span>
                      ) : null}
                      <time dateTime={item.publishedAt} title={formatDateTime(item.publishedAt)} className="text-zinc-500">
                        {relative(item.publishedAt)}
                      </time>
                    </div>
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="line-clamp-2 font-semibold text-white hover:underline"
                    >
                      {item.title}
                    </a>
                  </div>
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`${item.title} 원문 보기`}
                    className="btn-ghost hidden shrink-0 px-2.5 py-1 text-xs sm:inline-flex"
                  >
                    원문
                    <ArrowUpRight className="size-3.5" aria-hidden />
                  </a>
                </li>
              );
            })}
          </ol>
        )}
        {data ? (
          <p className="mt-2 text-xs text-zinc-500">
            최근 플레이한 게임 {data.gameCount}개의 공지{data.failedCount > 0 ? ` · ${data.failedCount}개 게임은 불러오지 못했습니다` : ""}
          </p>
        ) : null}
      </div>
    </section>
  );
}
