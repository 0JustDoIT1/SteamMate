/**
 * 불러오는 동안 보이는 자리 표시(실제 카드 모양). "불러오는 중…" 문장은 화면 읽기 프로그램과
 * 테스트를 위해 보이지 않게 남긴다(role="status").
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse rounded-md bg-zinc-800/70 ${className}`} />;
}

export function LoadingStatus({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/** 보유 게임 추천 카드 3장 모양 */
export function CardGridSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950/40">
          <Skeleton className="aspect-[460/215] w-full rounded-none" />
          <div className="space-y-3 p-4">
            <Skeleton className="h-5 w-2/3" />
            <div className="flex gap-1.5">
              <Skeleton className="h-5 w-12 rounded-full" />
              <Skeleton className="h-5 w-14 rounded-full" />
              <Skeleton className="h-5 w-10 rounded-full" />
            </div>
            <Skeleton className="h-20 w-full rounded-lg" />
            <Skeleton className="h-9 w-full rounded-lg" />
          </div>
        </div>
      ))}
    </div>
  );
}

/** 이미지 + 두 줄 글자 목록 모양(구매 추천·할인·뉴스) */
export function RowListSkeleton({ count = 5, imageClass = "w-28 sm:w-40" }: { count?: number; imageClass?: string }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex items-center gap-4 rounded-xl border border-zinc-800/60 p-3">
          <Skeleton className={`aspect-[460/215] shrink-0 ${imageClass}`} />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-3 w-1/3" />
          </div>
          <Skeleton className="hidden h-6 w-16 sm:block" />
        </div>
      ))}
    </div>
  );
}

/** 내 라이브러리 통계 카드 5개 + 큰 칸 */
export function LibrarySkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-20 rounded-[0.875rem]" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-[0.875rem]" />
    </div>
  );
}
