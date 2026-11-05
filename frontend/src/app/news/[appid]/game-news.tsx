"use client";

import { ArrowUpRight, ExternalLink, Megaphone } from "lucide-react";
import Link from "next/link";

import GameImage from "@/components/game-image";
import { type NewsItem, useGameNews } from "@/features/news/queries";
import { ApiError } from "@/lib/api/client";
import { formatDateTime, steamStoreUrl } from "@/lib/format";

import NewsAsk from "./news-ask";

export default function GameNews({ appid }: { appid: number }) {
  const query = useGameNews(appid);
  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((p) => p.items);
  const name = pages[0]?.name;
  const headerImage = pages[0]?.headerImage;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-5">
        <GameImage src={headerImage} className="aspect-[460/215] w-56 rounded-lg border border-zinc-800 shadow-lg" />
        <div className="min-w-0 space-y-1">
          <p className="text-sm text-zinc-400">
            <Link href="/news" className="hover:text-white">
              공식 뉴스
            </Link>{" "}
            › 게임 공지
          </p>
          {/* 페이지 제목(h1)은 배너의 "공식 뉴스", 게임 이름은 그 아래 제목 */}
          <h2 className="truncate text-3xl font-bold tracking-tight text-white">{name ?? `App ${appid}`}</h2>
          <a
            href={steamStoreUrl(appid)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm text-[#8fa6ff] hover:text-white"
          >
            Steam 상점에서 보기
            <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </div>
      </div>

      {pages[0] ? <NewsAsk appid={appid} enabled={pages[0].askEnabled} /> : null}

      <section className="panel">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 px-5 py-4">
          <h2 className="text-lg font-semibold text-white">공식 공지</h2>
          <p className="text-xs text-zinc-500">개발사가 Steam에 올린 공지의 앞부분만 보여 줍니다. 전문은 원문에서 확인하세요.</p>
        </header>
        {query.isPending ? (
          <p className="px-4 py-3 text-sm text-zinc-500">뉴스를 불러오는 중…</p>
        ) : query.isError ? (
          <NewsError error={query.error} onRetry={() => query.refetch()} />
        ) : items.length === 0 ? (
          <p className="px-4 py-3 text-sm text-zinc-500">이 게임의 공식 공지가 없습니다.</p>
        ) : (
          <ol className="divide-y divide-zinc-800/80">
            {items.map((item) => (
              <NewsRow key={item.gid} item={item} />
            ))}
          </ol>
        )}
        {query.hasNextPage ? (
          <div className="border-t border-zinc-800 px-5 py-4">
            <button
              type="button"
              onClick={() => query.fetchNextPage()}
              disabled={query.isFetchingNextPage}
              className="btn-ghost"
            >
              {query.isFetchingNextPage ? "불러오는 중…" : "이전 공지 더 보기"}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function NewsRow({ item }: { item: NewsItem }) {
  // 본문이 개발사 사이트에만 있는 공지는 그쪽으로 바로 보낸다.
  const href = item.externalUrl ?? item.url;
  const target = item.externalUrl ? hostOf(item.externalUrl) : "Steam";
  return (
    <li className="flex items-center gap-4 px-5 py-4 hover:bg-white/[0.02]">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-accent/30 bg-accent/10 text-[#a68bff]">
        <Megaphone className="size-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <a href={href} target="_blank" rel="noopener noreferrer" className="block font-semibold text-white hover:underline">
          {item.title}
        </a>
        <p className="text-xs text-zinc-400">
          {formatDateTime(item.publishedAt)}
          {item.author ? <span className="ml-2 border-l border-zinc-700 pl-2">{item.author}</span> : null}
        </p>
        {item.excerpt ? (
          <p className="line-clamp-3 text-sm text-zinc-600 dark:text-zinc-400">{item.excerpt}</p>
        ) : item.externalUrl ? (
          <p className="text-sm text-zinc-500">본문은 {target}에 있습니다.</p>
        ) : null}
      </div>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`${item.title} 전문 보기(${target})`}
        className="btn-ghost shrink-0 border-accent-2/50 px-3 py-1.5 text-xs text-zinc-100"
      >
        {target}
        <ArrowUpRight className="size-3.5" aria-hidden />
      </a>
    </li>
  );
}

function NewsError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  if (error instanceof ApiError && error.status === 404) {
    return <p className="px-4 py-3 text-sm text-zinc-500">Steam에서 이 게임의 뉴스를 찾을 수 없습니다.</p>;
  }
  return (
    <div role="alert" className="flex items-center gap-3 px-4 py-3 text-sm text-red-700 dark:text-red-300">
      <span>{error.message}</span>
      <button type="button" onClick={onRetry} className="rounded-md border border-red-400 px-2 py-1">
        다시 시도
      </button>
    </div>
  );
}

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "외부 사이트";
  }
}
