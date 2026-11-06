import { Suspense } from "react";

import { PageLayout } from "@/components/page-hero";

import DashboardView from "./dashboard-view";
import HomeLoginPanel from "./home-login-panel";

export default function Home() {
  return (
    <PageLayout title="SteamMate" subtitle="Steam 인기 순위와 흐름을 한눈에 보고, 로그인하면 내 플레이 기록에 맞춘 추천과 할인을 받아 보세요.">
      <Suspense fallback={null}>
        <HomeLoginPanel />
      </Suspense>
      <DashboardView />
    </PageLayout>
  );
}
