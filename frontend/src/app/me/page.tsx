import { PageLayout } from "@/components/page-hero";

import { LibraryHomeView } from "./views";

export default function Page() {
  return (
    <PageLayout title="내 라이브러리" subtitle="보유한 게임을 분석해, 지금 즐기기 좋은 게임을 추천해드려요.">
      <LibraryHomeView />
    </PageLayout>
  );
}
