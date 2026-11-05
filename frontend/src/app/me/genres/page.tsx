import PageHero from "@/components/page-hero";

import { GenresView } from "../views";

export default function Page() {
  return (
    <main className="w-full max-w-[1440px] flex-1 px-4 pb-12 sm:px-8">
      <PageHero title="장르 취향" subtitle="플레이 시간으로 본 내 장르 취향이에요. 추천의 '취향 장르'와 같은 값입니다." />
      <GenresView />
    </main>
  );
}
