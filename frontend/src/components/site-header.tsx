"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { STEAM_LOGIN_URL, useLogout, useMe } from "@/features/auth/queries";
import { useHydrated } from "@/lib/use-hydrated";

export default function SiteHeader() {
  const hydrated = useHydrated();
  const { data: me, isPending: mePending } = useMe();
  const isPending = !hydrated || mePending;
  const logout = useLogout();
  const router = useRouter();

  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link href="/" className="font-semibold tracking-tight">
          SteamMate
        </Link>
        <nav className="flex items-center gap-3 text-sm">
          {isPending ? null : me ? (
            <>
              <Link href="/me" className="hover:underline">
                내 라이브러리
              </Link>
              <button
                type="button"
                onClick={() => logout.mutate(undefined, { onSuccess: () => router.push("/") })}
                disabled={logout.isPending}
                className="rounded-md border border-zinc-300 px-3 py-1.5 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
              >
                로그아웃
              </button>
            </>
          ) : (
            <a
              href={STEAM_LOGIN_URL}
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              Steam으로 로그인
            </a>
          )}
        </nav>
      </div>
    </header>
  );
}
