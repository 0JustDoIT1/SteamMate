"use client";

import { useState } from "react";

/**
 * Steam CDN 이미지. 주소만 받아 브라우저가 직접 불러오며(저장하지 않음), 실패하면 다음 주소, 그다음 대체 칸을 보여준다.
 * (일부 게임은 아이콘 주소가 404라 상점 대표 이미지 → 아이콘 순으로 시도한다)
 * next/image 원격 도메인 설정 없이 그대로 표시한다.
 */
export default function GameImage({
  src,
  fallbackSrc,
  className,
}: {
  src: string | null | undefined;
  fallbackSrc?: string | null;
  className: string;
}) {
  const candidates = [src, fallbackSrc].filter((s): s is string => Boolean(s));
  const [failed, setFailed] = useState(0);
  const current = candidates[failed];
  if (!current) {
    return <div aria-hidden className={`${className} bg-zinc-100 dark:bg-zinc-900`} />;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      key={current}
      src={current}
      alt=""
      loading="lazy"
      onError={() => setFailed((n) => n + 1)}
      className={`${className} bg-zinc-100 object-cover dark:bg-zinc-900`}
    />
  );
}
