/**
 * 순위 막대(한 계열의 크기 비교: 장르 취향·장르 순위). dataviz 지침: 한 색(--chart-1, 어두운 카드 바탕 대비 검증),
 * 둥근 막대 끝 4px, 흐린 트랙, 줄 전체가 마우스 대상, 값은 본문 글자색(계열 색 아님), 계열이 하나라 범례 없음.
 * 위 3개는 "대표" 카드로 한 번 더 보여 주고, 아래 목록은 전체를 같은 축(최댓값 기준)으로 비교한다.
 */
import type { LucideIcon } from "lucide-react";

/** icon: 항목을 알아보기 쉽게 하는 장식(장르 아이콘 등). 색은 글자색 계열이라 계열 색과 겹치지 않는다 */
export type RankedItem = { label: string; value: number; display: string; icon?: LucideIcon };

export default function RankedBars({ items, label, top = 3 }: { items: RankedItem[]; label: string; top?: number }) {
  if (items.length === 0) return null;
  const max = Math.max(...items.map((i) => i.value)) || 1;
  const leaders = items.slice(0, top);

  return (
    <div className="space-y-5">
      <ol className="grid gap-3 sm:grid-cols-3" aria-label={`${label} 상위 ${leaders.length}개`}>
        {leaders.map((item, i) => {
          const Icon = item.icon;
          return (
            <li key={item.label} className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-950/40 px-4 py-3">
              {Icon ? (
                <span className="grid size-10 shrink-0 place-items-center rounded-lg border border-zinc-700/80 bg-zinc-800/60 text-accent-soft">
                  <Icon className="size-5" aria-hidden />
                </span>
              ) : null}
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-zinc-500">{i + 1}위</p>
                <div className="mt-0.5 flex items-baseline justify-between gap-2">
                  <p className="truncate text-lg font-semibold text-zinc-50">{item.label}</p>
                  <p className="shrink-0 text-sm tabular-nums text-zinc-300">{item.display}</p>
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      <ol className="space-y-1" aria-label={label}>
        {items.map((item, i) => {
          const width = Math.max((item.value / max) * 100, 1.5);
          const Icon = item.icon;
          return (
            <li
              key={item.label}
              className="group relative grid grid-cols-[1.75rem_minmax(6.5rem,9.5rem)_1fr_3.75rem] items-center gap-3 rounded-lg px-2 py-2 hover:bg-white/[0.03]"
            >
              <span className="text-xs tabular-nums text-zinc-500">{i + 1}</span>
              <span className={`flex min-w-0 items-center gap-2 text-sm ${i < top ? "font-semibold text-zinc-100" : "text-zinc-300"}`}>
                {Icon ? <Icon className="size-4 shrink-0 text-zinc-400" aria-hidden /> : null}
                <span className="truncate">{item.label}</span>
              </span>
              <span className="relative">
                <span className="block h-3 overflow-hidden rounded-[4px] bg-zinc-800/80" aria-hidden>
                  <span className="block h-full rounded-[4px] bg-chart-1" style={{ width: `${width}%` }} />
                </span>
                {/* 마우스를 올리면 막대 끝에 값 풍선(줄 전체가 대상) */}
                <span
                  role="tooltip"
                  className="pointer-events-none absolute bottom-full z-10 mb-1.5 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100 shadow-lg group-hover:block"
                  style={{ left: `${width}%` }}
                >
                  {item.label} · {item.display}
                </span>
              </span>
              <span className="text-right text-sm tabular-nums text-zinc-300">{item.display}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
