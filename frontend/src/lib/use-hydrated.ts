"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * 서버 렌더링과 hydration 중에는 false, 그 이후에는 true.
 * 로그인 상태처럼 클라이언트 캐시에만 있는 값으로 화면이 달라지는 컴포넌트는
 * hydration이 끝날 때까지 서버와 같은 화면을 그려 hydration 불일치를 막는다.
 */
export function useHydrated() {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
