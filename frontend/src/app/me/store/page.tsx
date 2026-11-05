import PageHero from "@/components/page-hero";

import { StoreView } from "../views";

export default function Page() {
  return (
    <main className="w-full max-w-[1440px] flex-1 px-4 pb-12 sm:px-8">
      <PageHero title="구매 추천" subtitle="Steam 인기·할인·신작 중 아직 갖고 있지 않은 게임을 내 취향에 맞춰 골랐어요." />
      <StoreView />
    </main>
  );
}
