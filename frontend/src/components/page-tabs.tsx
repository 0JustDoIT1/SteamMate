"use client";

/**
 * 대시보드와 같은 모양의 상단 탭. 한 번에 한 섹션만 보여 주는 화면에서 쓴다.
 * 선택 여부는 색·밑줄로만 구분한다(굵기를 바꾸면 탭 폭이 변해 옆 탭이 밀린다).
 */
export default function PageTabs<T extends string>({
  tabs,
  current,
  onSelect,
  label,
}: {
  tabs: { id: T; label: string }[];
  current: T;
  onSelect: (id: T) => void;
  label: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="flex gap-1 overflow-x-auto overflow-y-hidden shadow-[inset_0_-1px_0_var(--border)] [scrollbar-width:none]"
    >
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={current === t.id}
          onClick={() => onSelect(t.id)}
          className={`shrink-0 border-b-2 px-3 py-2 text-sm font-medium ${
            current === t.id
              ? "border-zinc-900 text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
              : "border-transparent text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
