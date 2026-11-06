import { PageLayout } from "@/components/page-hero";

import { GenresView } from "../views";

export default function Page() {
  return (
    <PageLayout title="장르 취향" subtitle="플레이 시간으로 본 내 장르 취향이에요. 추천의 '취향 장르'와 같은 값입니다.">
      <GenresView />
    </PageLayout>
  );
}
