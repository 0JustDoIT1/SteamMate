"use client";

import { LogIn, LogOut, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";

import { STEAM_LOGIN_URL, useLogout, useMe, useMyProfile } from "@/features/auth/queries";
import { useHydrated } from "@/lib/use-hydrated";

import { Logo } from "./app-sidebar";

/** 위쪽 바: 내 Steam 프로필(닉네임·사진)과 로그인·로그아웃. 큰 화면에서 로고는 사이드바에 있다. */
export default function SiteHeader() {
  const hydrated = useHydrated();
  const { data: me, isPending: mePending } = useMe();
  const isPending = !hydrated || mePending;
  const logout = useLogout();
  const router = useRouter();

  return (
    <header className="border-b border-zinc-800/70 bg-zinc-950/40 backdrop-blur">
      <div className="flex h-16 items-center justify-between gap-4 px-4 sm:px-8">
        <div className="lg:invisible">
          <Logo />
        </div>
        <nav className="flex items-center gap-3 text-sm">
          {isPending ? null : me ? (
            <>
              <ProfileChip />
              <button
                type="button"
                onClick={() => logout.mutate(undefined, { onSuccess: () => router.push("/") })}
                disabled={logout.isPending}
                className="btn-ghost"
              >
                <LogOut className="size-4" aria-hidden />
                로그아웃
              </button>
            </>
          ) : (
            <a href={STEAM_LOGIN_URL} className="btn-primary">
              <LogIn className="size-4" aria-hidden />
              Steam으로 로그인
            </a>
          )}
        </nav>
      </div>
    </header>
  );
}

/** 프로필 사진 + 닉네임. 누르면 Steam 프로필로. 못 불러오면 기본 아이콘·"내 계정"으로 보인다. */
function ProfileChip() {
  const { data: profile } = useMyProfile(true);
  const name = profile?.personaName ?? "내 계정";
  const body = (
    <>
      {profile?.avatarUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- Steam 아바타 CDN 주소를 그대로 쓴다(서버가 https·도메인 확인)
        <img src={profile.avatarUrl} alt="" className="size-8 rounded-full ring-2 ring-accent/60" />
      ) : (
        <span className="grid size-8 place-items-center rounded-full bg-zinc-800 ring-2 ring-accent/40">
          <UserRound className="size-4 text-zinc-300" aria-hidden />
        </span>
      )}
      <span className="hidden max-w-40 truncate font-medium text-zinc-100 sm:inline">{name}</span>
    </>
  );
  return profile?.profileUrl ? (
    <a
      href={profile.profileUrl}
      target="_blank"
      rel="noopener noreferrer"
      title="Steam 프로필 열기"
      className="flex items-center gap-2.5 rounded-full py-1 pl-1 pr-3 hover:bg-white/5"
    >
      {body}
    </a>
  ) : (
    <span className="flex items-center gap-2.5 py-1 pl-1 pr-3">{body}</span>
  );
}
