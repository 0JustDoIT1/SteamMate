"use client";

import { useState } from "react";

/**
 * Steam CDN 이미지. 주소만 받아 브라우저가 직접 불러오며(저장하지 않음), 실패하면 대체 칸을 보여준다.
 * next/image 원격 도메인 설정 없이 그대로 표시한다.
 */
export default function GameImage({ src, className }: { src: string | null | undefined; className: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return <div aria-hidden className={`${className} bg-zinc-100 dark:bg-zinc-900`} />;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} className={`${className} bg-zinc-100 object-cover dark:bg-zinc-900`} />
  );
}
