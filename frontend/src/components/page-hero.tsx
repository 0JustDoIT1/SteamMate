import type { ReactNode } from "react";

/**
 * 페이지 맨 위 제목 배너. 참고 시안의 밤하늘 분위기를 그림 없이 그라데이션·빛 번짐·작은 별로 낸다
 * (실제 게임 그림은 저작물이라 쓰지 않는다).
 */
export default function PageHero({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="relative -mx-4 overflow-hidden px-4 pb-6 pt-8 sm:-mx-8 sm:px-8">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(600px_220px_at_80%_10%,rgb(124_92_255/0.28),transparent_70%),radial-gradient(500px_200px_at_100%_80%,rgb(79_123_255/0.18),transparent_70%)]" />
        <div className="absolute inset-0 opacity-60 [background-image:radial-gradient(1px_1px_at_70%_20%,#fff,transparent),radial-gradient(1px_1px_at_85%_45%,#cfd6ff,transparent),radial-gradient(1.5px_1.5px_at_92%_15%,#fff,transparent),radial-gradient(1px_1px_at_60%_60%,#b9c2ff,transparent),radial-gradient(1px_1px_at_78%_75%,#fff,transparent)]" />
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-b from-transparent to-background" />
      </div>
      <div className="relative">
        <div className="flex items-center gap-3">
          <span aria-hidden className="h-8 w-1.5 shrink-0 rounded-full bg-gradient-to-b from-[#a68bff] to-accent-2" />
          <h1 className="truncate text-2xl font-bold tracking-tight text-white sm:text-3xl">{title}</h1>
        </div>
        {subtitle ? <p className="mt-2 pl-[18px] text-sm text-zinc-300 sm:text-base">{subtitle}</p> : null}
        {children}
      </div>
    </div>
  );
}
