"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState } from "react";

// 서버 데이터 캐시는 TanStack Query가 단독으로 관리한다(Zustand에 복제하지 않음).
export default function Providers({ children }: { children: React.ReactNode }) {
  // 컴포넌트 인스턴스마다 생성: 서버 렌더링 시 요청 간 캐시 공유를 막는다.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {process.env.NODE_ENV === "development" && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
