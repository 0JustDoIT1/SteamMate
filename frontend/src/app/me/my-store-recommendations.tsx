"use client";

import { ChartColumn, Crown, Gamepad2, Heart, Sparkles } from "lucide-react";

import GameImage from "@/components/game-image";
import ToggleChip from "@/components/toggle-chip";
import { FACTOR_LABEL, MODE_LABEL } from "@/features/library/labels";
import { type StoreRecommendation, useStoreRecommendations } from "@/features/library/queries";
import { ApiError } from "@/lib/api/client";
import { formatDateTime, formatPrice } from "@/lib/format";
import { useAppStore } from "@/stores/app-store";
import { LoadingStatus, RowListSkeleton } from "@/components/skeleton";

/** 구매 추천(F4ⓒ): 대시보드 인기·할인·신작 목록 중 보유하지 않은 게임을 취향·인기로 추천. 정가 포함. */
export default function StoreRecommendationsPanel() {
  const onSaleOnly = useAppStore((s) => s.recOptions.onSaleOnly);
  const setRecOptions = useAppStore((s) => s.setRecOptions);
  const query = useStoreRecommendations(true, onSaleOnly);
  const data = query.data;

  return (
    <section className="panel">
      <header className="flex flex-wrap items-center justify-between gap-2 px-5 pt-5">
        <div className="flex items-center gap-2.5">
          <Gamepad2 className="size-6 text-[#a68bff]" aria-hidden />
          <h2 className="text-lg font-bold text-white sm:text-xl">내 취향에 맞는 인기 게임</h2>
          {data ? <span className="text-sm text-zinc-400">{MODE_LABEL[data.recommendationMode]}</span> : null}
        </div>
        <ToggleChip
          label="할인 중"
          pressed={onSaleOnly}
          onChange={(v) => setRecOptions({ onSaleOnly: v })}
          title="켜면 지금 할인 중인 게임만 보여 줍니다"
        />
      </header>

      <div className="px-5 py-4">
        {query.isPending ? (
          <LoadingStatus label="추천을 계산하는 중…">
            <RowListSkeleton count={6} />
          </LoadingStatus>
        ) : query.isError ? (
          <StoreError error={query.error} onRetry={() => query.refetch()} />
        ) : data!.recommendations.length === 0 ? (
          <p className="text-sm text-zinc-500">
            {onSaleOnly ? "지금 할인 중인 후보 게임이 없습니다. '할인 중'을 끄면 정가 게임도 보여 줍니다." : "추천할 게임이 없습니다."}
          </p>
        ) : (
          <ol className={`space-y-2 ${query.isPlaceholderData ? "opacity-60" : ""}`}>
            {data!.recommendations.map((rec, i) => (
              <StoreRow key={rec.appid} rank={i + 1} rec={rec} />
            ))}
          </ol>
        )}

        {data ? (
          <p className="mt-3 text-xs text-zinc-500">
            Steam 판매·접속 순위, 할인·신작 목록에 오른 게임 중 보유하지 않은 {data.candidatePoolSize}개가 후보입니다
            (Steam 전체 목록을 주는 공식 API가 없음).
            {data.metadataPending > 0 || data.pricePending > 0
              ? ` 장르 ${data.metadataPending}개 · 가격 ${data.pricePending}개 수집 중, 자동 갱신.`
              : ""}
            {data.priceSnapshotAt ? ` 가격 기준 ${formatDateTime(data.priceSnapshotAt)}(한국 상점).` : ""}
            {data.wishlistChecked ? "" : " 위시리스트를 확인하지 못했습니다."}
          </p>
        ) : null}
      </div>
    </section>
  );
}

function StoreError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  if (error instanceof ApiError && error.code === "DATA_NOT_READY") {
    return <p className="text-sm text-zinc-500">Steam 인기·할인 목록을 아직 모으지 못했습니다. 잠시 후 다시 확인해 주세요.</p>;
  }
  return (
    <div role="alert" className="flex items-center gap-3 text-sm text-red-700 dark:text-red-300">
      <span>{error.message}</span>
      <button type="button" onClick={onRetry} className="rounded-md border border-red-400 px-2 py-1">
        다시 시도
      </button>
    </div>
  );
}

function StoreRow({ rank, rec }: { rank: number; rec: StoreRecommendation }) {
  const price = rec.price;
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border border-zinc-800 bg-zinc-950/40 p-3 transition-colors hover:border-accent/50 md:flex-nowrap">
      <div className="flex min-w-0 basis-full flex-wrap items-center gap-3 md:flex-1 md:basis-auto md:flex-nowrap md:gap-4">
      <span
        className={`grid h-8 w-9 shrink-0 place-items-center rounded-lg text-sm font-bold tabular-nums ${
          rank === 1 ? "bg-gradient-to-br from-accent to-accent-2 text-white" : "border border-accent/40 bg-accent/10 text-zinc-100"
        }`}
      >
        {rank === 1 ? (
          <span className="flex items-center gap-0.5">
            <Crown className="size-3.5" aria-label="1위" />1
          </span>
        ) : (
          rank
        )}
      </span>
      <a href={rec.storeUrl} target="_blank" rel="noopener noreferrer" className="shrink-0">
        <GameImage src={rec.headerImage} className="aspect-[460/215] w-28 rounded-md sm:w-40" />
      </a>
      <div className="min-w-0 basis-full space-y-2 md:flex-1 md:basis-auto">
        <a href={rec.storeUrl} target="_blank" rel="noopener noreferrer" className="block truncate font-bold text-white hover:underline sm:text-lg">
          {rec.name}
        </a>
        <div className="flex flex-wrap gap-1.5">
          {rec.genres.slice(0, 4).map((g) => (
            <span key={g} className="chip">
              {g}
            </span>
          ))}
          {rec.genres.length > 4 ? <span className="chip">+{rec.genres.length - 4}</span> : null}
          {rec.wishlisted ? (
            <span className="chip border-pink-400/50 text-pink-200">
              <Heart className="mr-1 size-3" aria-hidden />
              위시리스트
            </span>
          ) : null}
        </div>
      </div>
      </div>
      <ul className="w-full space-y-1.5 text-sm md:w-72 md:shrink-0">
        {rec.reasons.map((r) => {
          if (r.factor === "LOW_GENRE_COVERAGE") {
            return (
              <li key={r.factor} className="text-xs text-amber-300">
                {r.detail}
              </li>
            );
          }
          const Icon = r.factor === "POPULAR" ? ChartColumn : Sparkles;
          return (
            <li key={r.factor} className="flex items-center gap-2">
              <Icon className="size-4 shrink-0 text-[#a68bff]" aria-hidden />
              <span className="shrink-0 font-semibold text-zinc-100">{FACTOR_LABEL[r.factor]}</span>
              <span className="min-w-0 truncate text-zinc-400">{r.detail}</span>
              <span className="ml-auto shrink-0 tabular-nums text-[#8fa6ff]">+{Math.round(r.contribution * 100)}</span>
            </li>
          );
        })}
      </ul>
      <span className="ml-auto w-16 shrink-0 border-zinc-800 text-center text-xl font-bold tabular-nums text-white md:ml-0 md:border-l">
        {Math.round(rec.score * 100)}점
      </span>
      <div className="w-28 shrink-0 text-right md:border-l md:border-zinc-800">
        {price ? (
          <>
            {price.discountPercent > 0 ? (
              <div className="flex items-center justify-end gap-1.5">
                <span className="rounded bg-emerald-500 px-1.5 text-xs font-bold text-white">-{price.discountPercent}%</span>
                <span className="text-xs text-zinc-500 line-through">{formatPrice(price.initialPrice, price.currency)}</span>
              </div>
            ) : null}
            <p className="text-lg font-bold tabular-nums text-white">{formatPrice(price.finalPrice, price.currency)}</p>
          </>
        ) : (
          <p className="text-sm text-zinc-400">가격 정보 없음</p>
        )}
      </div>
    </li>
  );
}
