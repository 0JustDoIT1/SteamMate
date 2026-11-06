import type { ReactNode } from "react";

/** 본문 폭. 배너 배경은 화면(본문 영역) 끝까지, 글자와 본문은 이 폭 안에서 가운데 정렬한다 */
const CONTAINER = "mx-auto w-full max-w-[1440px] px-4 sm:px-8";

/**
 * 페이지 맨 위 제목 배너. 밤하늘 분위기를 그림 없이 은은한 그라데이션과 작은 별로 낸다
 * (실제 게임 그림은 저작물이라 쓰지 않는다). 배경은 본문 영역 전체 폭을 채운다(넓은 화면에서 잘리지 않게).
 */
export default function PageHero({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="relative overflow-hidden pb-6 pt-8">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(70%_120%_at_85%_0%,rgb(110_100_200/0.16),transparent_70%),radial-gradient(50%_90%_at_100%_100%,rgb(90_120_200/0.08),transparent_70%)]" />
        <div className="absolute inset-0 opacity-40 [background-image:radial-gradient(1px_1px_at_72%_22%,#fff,transparent),radial-gradient(1px_1px_at_86%_48%,#d4d8e6,transparent),radial-gradient(1px_1px_at_93%_16%,#fff,transparent),radial-gradient(1px_1px_at_63%_58%,#c6cbdc,transparent)]" />
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-b from-transparent to-background" />
      </div>
      <div className={`relative ${CONTAINER}`}>
        <div className="flex items-center gap-3">
          <span aria-hidden className="h-7 w-1 shrink-0 rounded-full bg-accent" />
          <h1 className="truncate text-2xl font-bold tracking-tight text-zinc-50 sm:text-3xl">{title}</h1>
        </div>
        {subtitle ? <p className="mt-2 pl-4 text-sm text-zinc-400 sm:text-base">{subtitle}</p> : null}
        {children}
      </div>
    </div>
  );
}

/** 배너 + 본문을 같은 폭 규칙으로 감싼 페이지 틀 */
export function PageLayout({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <main className="w-full flex-1 pb-12">
      <PageHero title={title} subtitle={subtitle} />
      <div className={`${CONTAINER} space-y-6`}>{children}</div>
    </main>
  );
}
