import { PageLayout } from "@/components/page-hero";

import { DealsView } from "../views";

export default function Page() {
  return (
    <PageLayout title="할인" subtitle="위시리스트 게임과, 즐겨 한 게임의 DLC 중 지금 할인 중인 것을 모았어요.">
      <DealsView />
    </PageLayout>
  );
}
