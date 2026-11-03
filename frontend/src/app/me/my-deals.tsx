"use client";

import GameImage from "@/components/game-image";
import { type DealItem, type Deals, useMyDeals } from "@/features/library/queries";
import { formatDateTime, formatPrice } from "@/lib/format";

const PRIVACY_SETTINGS_URL = "https://steamcommunity.com/my/edit/settings";

/** 할인(F4ⓐⓑ): 위시리스트 할인, 2시간 이상 플레이한 보유 게임의 DLC 할인. */
export default function MyDeals() {
  const query = useMyDeals(true);
  const data = query.data;

  return (
    <section className="rounded-lg border border-zinc-200 dark:border-zinc-800">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h2 className="font-semibold">할인</h2>
        {data ? (
          <p className="text-xs text-zinc-500">
            {data.pricePending > 0 ? `가격 ${data.pricePending}개 수집 중, 자동 갱신 · ` : ""}
            {data.priceSnapshotAt ? `가격 기준 ${formatDateTime(data.priceSnapshotAt)}(한국 상점)` : ""}
          </p>
        ) : null}
      </header>
      <div className="grid gap-6 px-4 py-3 md:grid-cols-2">
        {query.isPending ? (
          <p className="text-sm text-zinc-500">할인 정보를 불러오는 중…</p>
        ) : query.isError ? (
          <div role="alert" className="flex items-center gap-3 text-sm text-red-700 dark:text-red-300">
            <span>{query.error.message}</span>
            <button type="button" onClick={() => query.refetch()} className="rounded-md border border-red-400 px-2 py-1">
              다시 시도
            </button>
          </div>
        ) : (
          <>
            <WishlistDeals data={data!} />
            <DlcDeals data={data!} />
          </>
        )}
      </div>
    </section>
  );
}

function WishlistDeals({ data }: { data: Deals }) {
  return (
    <div>
      <h3 className="text-sm font-semibold">
        위시리스트 할인
        {data.wishlistStatus === "OK" ? (
          <span className="ml-2 text-xs font-normal text-zinc-500">
            {data.wishlistCount}개 중 {data.wishlistDeals.length}개
          </span>
        ) : null}
      </h3>
      {data.wishlistStatus === "EMPTY_OR_PRIVATE" ? (
        <p className="mt-2 text-sm text-zinc-500">
          위시리스트가 비어 있거나 비공개입니다. 비공개라면{" "}
          <a href={PRIVACY_SETTINGS_URL} target="_blank" rel="noopener noreferrer" className="underline">
            Steam 공개 설정
          </a>
          에서 &lsquo;게임 세부 정보&rsquo;를 공개로 바꿔 주세요.
        </p>
      ) : data.wishlistStatus === "UNAVAILABLE" ? (
        <p className="mt-2 text-sm text-zinc-500">Steam에서 위시리스트를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.</p>
      ) : (
        <DealList items={data.wishlistDeals} empty="지금 할인 중인 위시리스트 게임이 없습니다." />
      )}
    </div>
  );
}

function DlcDeals({ data }: { data: Deals }) {
  return (
    <div>
      <h3 className="text-sm font-semibold">
        내 게임 DLC 할인
        <span className="ml-2 text-xs font-normal text-zinc-500">
          2시간 이상 플레이한 {data.dlcBaseGameCount}개 게임의 DLC {data.dlcCheckedCount}개 확인
        </span>
      </h3>
      <DealList items={data.dlcDeals} empty="지금 할인 중인 DLC가 없습니다." />
      {data.dlcDeals.length > 0 ? (
        <p className="mt-2 text-xs text-zinc-500">Steam이 DLC 보유 여부를 알려 주지 않아 이미 가진 DLC도 보일 수 있습니다.</p>
      ) : null}
    </div>
  );
}

function DealList({ items, empty }: { items: DealItem[]; empty: string }) {
  if (items.length === 0) return <p className="mt-2 text-sm text-zinc-500">{empty}</p>;
  return (
    <ul className="mt-2 divide-y divide-zinc-200 dark:divide-zinc-800">
      {items.map((d) => (
        <li key={d.appid} className="flex items-center gap-3 py-2">
          <a href={d.storeUrl} target="_blank" rel="noopener noreferrer" className="shrink-0">
            <GameImage src={d.headerImage} className="aspect-[460/215] w-24 rounded" />
          </a>
          <div className="min-w-0 flex-1">
            <a href={d.storeUrl} target="_blank" rel="noopener noreferrer" className="block truncate text-sm hover:underline">
              {d.name}
            </a>
            <p className="truncate text-xs text-zinc-500">
              {d.baseName ? `${d.baseName} DLC · 보유 여부 미확인` : null}
              {!d.baseName && d.affinity != null ? `취향 일치 ${Math.round(d.affinity * 100)}%` : null}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <span className="rounded bg-emerald-600 px-1 text-xs font-medium text-white">-{d.price.discountPercent}%</span>
            <p className="text-xs text-zinc-400 line-through">{formatPrice(d.price.initialPrice, d.price.currency)}</p>
            <p className="text-sm tabular-nums">{formatPrice(d.price.finalPrice, d.price.currency)}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
