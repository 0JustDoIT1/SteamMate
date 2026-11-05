import { Suspense } from "react";

import PageHero from "@/components/page-hero";

import DashboardView from "./dashboard-view";
import HomeLoginPanel from "./home-login-panel";

export default function Home() {
  return (
    <main className="w-full max-w-[1440px] flex-1 px-4 pb-12 sm:px-8">
      <PageHero
        title="SteamMate"
        subtitle="내 Steam 라이브러리의 플레이 기록을 분석해 다음에 할 게임을 추천하고, 취향에 맞는 할인 게임과 인기 동향을 보여줍니다."
      />
      <Suspense fallback={null}>
        <HomeLoginPanel />
      </Suspense>
      <DashboardView />
    </main>
  );
}
