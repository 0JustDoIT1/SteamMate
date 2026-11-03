"use client";

import { useSearchParams } from "next/navigation";

/** 로그인 버튼은 헤더에 있다. 메인에서는 Steam 로그인 콜백 실패(/?login=failed) 알림만 보여준다. */
export default function HomeLoginPanel() {
  const searchParams = useSearchParams();
  if (searchParams.get("login") !== "failed") return null;
  return (
    <p
      role="alert"
      className="mt-6 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
    >
      Steam 로그인 확인에 실패했습니다. 오른쪽 위 &lsquo;Steam으로 로그인&rsquo;으로 다시 시도해 주세요.
    </p>
  );
}
