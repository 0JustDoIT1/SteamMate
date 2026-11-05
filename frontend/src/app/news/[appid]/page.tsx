import { notFound } from "next/navigation";
import { Suspense } from "react";

import PageHero from "@/components/page-hero";

import GameNews from "./game-news";

// cacheComponents: 경로 파라미터는 요청 때 정해지므로 Suspense 안에서 읽는다(바깥 틀은 미리 렌더링).
export default function NewsPage({ params }: PageProps<"/news/[appid]">) {
  return (
    <main className="w-full max-w-[1440px] flex-1 px-4 pb-12 sm:px-8">
      <PageHero title="공식 뉴스" subtitle="Steam의 공식 뉴스와 공지를 한곳에서 확인하세요." />
      <Suspense fallback={<p className="text-zinc-500">불러오는 중…</p>}>
        <NewsForApp params={params} />
      </Suspense>
    </main>
  );
}

async function NewsForApp({ params }: { params: PageProps<"/news/[appid]">["params"] }) {
  const { appid } = await params;
  // 숫자 appid만 받는다(백엔드도 검증하지만 잘못된 주소는 여기서 바로 404).
  if (!/^\d{1,10}$/.test(appid) || Number(appid) <= 0) notFound();
  return <GameNews appid={Number(appid)} />;
}
