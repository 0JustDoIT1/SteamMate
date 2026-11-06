import { PageLayout } from "@/components/page-hero";

import { OwnedGamesView } from "@/app/me/views";

export default function Page() {
  return (
    <PageLayout title="공식 뉴스" subtitle="최근 플레이한 게임의 새 소식과, 보유 게임별 Steam 공식 공지를 확인하세요.">
      <OwnedGamesView />
    </PageLayout>
  );
}
