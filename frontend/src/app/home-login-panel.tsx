"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { STEAM_LOGIN_URL, useMe } from "@/features/auth/queries";
import { useHydrated } from "@/lib/use-hydrated";

export default function HomeLoginPanel() {
  const searchParams = useSearchParams();
  const loginFailed = searchParams.get("login") === "failed";
  const hydrated = useHydrated();
  const { data: me, isPending: mePending } = useMe();
  const isPending = !hydrated || mePending;

  return (
    <section className="mt-8 space-y-4">
      {loginFailed && (
        <p role="alert" className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          Steam 로그인 확인에 실패했습니다. 다시 시도해 주세요.
        </p>
      )}
      {isPending ? null : me ? (
        <Link
          href="/me"
          className="inline-block rounded-md bg-zinc-900 px-4 py-2 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          내 라이브러리 보기
        </Link>
      ) : (
        <div className="space-y-2">
          <a
            href={STEAM_LOGIN_URL}
            className="inline-block rounded-md bg-zinc-900 px-4 py-2 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            Steam으로 로그인
          </a>
          <p className="text-sm text-zinc-500">
            Steam 공식 로그인 페이지에서 인증하며, SteamMate는 비밀번호를 받지 않습니다. 본인 계정의 공개
            정보만 조회합니다.
          </p>
        </div>
      )}
    </section>
  );
}
