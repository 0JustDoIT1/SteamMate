import PageHero from "@/components/page-hero";

import { DealsView } from "../views";

export default function Page() {
  return (
    <main className="w-full max-w-[1440px] flex-1 px-4 pb-12 sm:px-8">
      <PageHero title="할인" subtitle="위시리스트 게임과, 즐겨 한 게임의 DLC 중 지금 할인 중인 것을 모았어요." />
      <DealsView />
    </main>
  );
}
