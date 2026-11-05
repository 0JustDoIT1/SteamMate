import PageHero from "@/components/page-hero";

import { OwnedGamesView } from "@/app/me/views";

export default function Page() {
  return (
    <main className="w-full max-w-[1440px] flex-1 px-4 pb-12 sm:px-8">
      <PageHero title="공식 뉴스" subtitle="보유한 게임을 골라 Steam 공식 공지를 확인하세요." />
      <OwnedGamesView />
    </main>
  );
}
