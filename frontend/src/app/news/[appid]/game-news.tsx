"use client";

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
      <div className="flex items-center gap-4">
        <GameImage src={headerImage} className="aspect-[460/215] w-40 rounded" />
        <div className="min-w-0">
          <p className="text-sm text-zinc-500">
            <Link href="/me" className="hover:underline">
              내 라이브러리
            </Link>{" "}
            › 공식 뉴스
          </p>
          <h1 className="truncate text-2xl font-semibold tracking-tight">{name ?? `App ${appid}`}</h1>
          <a href={steamStoreUrl(appid)} target="_blank" rel="noopener noreferrer" className="text-sm text-zinc-500 hover:underline">
            Steam 상점에서 보기
          </a>
        </div>
      </div>

      {pages[0] ? <NewsAsk appid={appid} enabled={pages[0].askEnabled} /> : null}

      <section className="rounded-lg border border-zinc-200 dark:border-zinc-800">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h2 className="font-semibold">공식 공지</h2>
          <p className="text-xs text-zinc-500">개발사가 Steam에 올린 공지의 앞부분만 보여 줍니다. 전문은 원문에서 확인하세요.</p>
        </header>
        {query.isPending ? (
          <p className="px-4 py-3 text-sm text-zinc-500">뉴스를 불러오는 중…</p>
        ) : query.isError ? (
          <NewsError error={query.error} onRetry={() => query.refetch()} />
        ) : items.length === 0 ? (
          <p className="px-4 py-3 text-sm text-zinc-500">이 게임의 공식 공지가 없습니다.</p>
        ) : (
          <ol className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {items.map((item) => (
              <NewsRow key={item.gid} item={item} />
            ))}
          </ol>
        )}
        {query.hasNextPage ? (
          <div className="border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <button
              type="button"
              onClick={() => query.fetchNextPage()}
              disabled={query.isFetchingNextPage}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-50 dark:border-zinc-700"
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
    <li className="flex items-start gap-4 px-4 py-4">
      <div className="min-w-0 flex-1 space-y-1">
        <a href={href} target="_blank" rel="noopener noreferrer" className="block font-medium hover:underline">
          {item.title}
        </a>
        <p className="text-xs text-zinc-500">
          {formatDateTime(item.publishedAt)}
          {item.author ? ` · ${item.author}` : ""}
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
        className="shrink-0 rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 hover:border-zinc-500 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
      >
        {target} ↗
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
