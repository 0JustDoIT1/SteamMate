import PageHero from "@/components/page-hero";

import { LibraryHomeView } from "./views";

export default function Page() {
  return (
    <main className="w-full max-w-[1440px] flex-1 px-4 pb-12 sm:px-8">
      <PageHero title="내 라이브러리" subtitle="보유한 게임을 분석해, 지금 즐기기 좋은 게임을 추천해드려요." />
      <LibraryHomeView />
    </main>
  );
}
