import { Suspense } from "react";

import HomeLoginPanel from "./home-login-panel";

// 대시보드(이번 주 인기·할인)는 3단계에서 이 화면에 추가된다.
export default function Home() {
  return (
    <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">SteamMate</h1>
      <p className="mt-3 max-w-2xl text-zinc-600 dark:text-zinc-400">
        내 Steam 라이브러리의 플레이 기록을 분석해 다음에 할 게임을 추천하고, 취향에 맞는 할인 게임과
        인기 동향을 보여줍니다.
      </p>
      <Suspense fallback={null}>
        <HomeLoginPanel />
      </Suspense>
    </main>
  );
}
