"use client";

import {
  ChartColumn,
  Gamepad2,
  LayoutDashboard,
  Layers,
  Library,
  ShoppingCart,
  Tag,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { STEAM_LOGIN_URL, useMe } from "@/features/auth/queries";
import { useHydrated } from "@/lib/use-hydrated";

// auth: 로그인해야 쓸 수 있는 메뉴(로그인 전에는 숨긴다 — 사용자 요청)
type NavItem = { label: string; href: string; icon: LucideIcon; match: (path: string) => boolean; auth?: boolean };

// 메뉴마다 한 페이지(사용자 요청: 내 라이브러리 안의 탭 대신 메뉴로 분리)
const NAV: NavItem[] = [
  { label: "인기 대시보드", href: "/", icon: LayoutDashboard, match: (p) => p === "/" },
  { label: "내 라이브러리", href: "/me", icon: Library, match: (p) => p === "/me", auth: true },
  { label: "구매 추천", href: "/me/store", icon: ShoppingCart, match: (p) => p === "/me/store", auth: true },
  { label: "할인", href: "/me/deals", icon: Tag, match: (p) => p === "/me/deals", auth: true },
  { label: "장르 취향", href: "/me/genres", icon: ChartColumn, match: (p) => p === "/me/genres", auth: true },
  // 보유 게임 목록 → 게임별 공지(/news/[appid])
  { label: "공식 뉴스", href: "/news", icon: Layers, match: (p) => p === "/news" || p.startsWith("/news/"), auth: true },
];

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5 text-xl font-bold tracking-tight">
      <span className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-accent to-accent-2 shadow-[0_6px_20px_-6px_rgb(124_92_255/0.8)]">
        <Gamepad2 className="size-5 text-white" aria-hidden />
      </span>
      <span>
        Steam<span className="bg-gradient-to-r from-[#a68bff] to-[#6f8fff] bg-clip-text text-transparent">Mate</span>
      </span>
    </Link>
  );
}

/** 왼쪽 메뉴(큰 화면). 작은 화면은 위쪽 바 아래의 가로 메뉴(MobileNav)를 쓴다. */
export default function AppSidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-zinc-800/70 bg-zinc-950/60 px-4 py-6 backdrop-blur lg:flex">
      <div className="px-2">
        <Logo />
      </div>
      <div className="my-6 h-px bg-zinc-800/70" />
      <NavLinks vertical />
      <LoginPrompt />
      <div className="mt-auto px-2 text-xs leading-relaxed text-zinc-600">
        Steam 공개 데이터로 분석합니다. Valve와 무관한 개인 프로젝트입니다.
      </div>
    </aside>
  );
}

export function MobileNav() {
  return (
    <nav className="border-b border-zinc-800/70 px-4 py-2 lg:hidden">
      <NavLinks />
    </nav>
  );
}

/** 로그인 여부. 확인 전(첫 렌더·요청 중)에는 로그인 메뉴를 그리지 않아, 보였다가 사라지는 깜빡임이 없다. */
function useLoggedIn(): boolean | null {
  const hydrated = useHydrated();
  const { data: me, isPending } = useMe();
  return !hydrated || isPending ? null : Boolean(me);
}

function NavLinks({ vertical = false }: { vertical?: boolean }) {
  const path = usePathname();
  const loggedIn = useLoggedIn();
  const items = NAV.filter((item) => !item.auth || loggedIn === true);
  return (
    <ul className={vertical ? "space-y-1" : "flex gap-1 overflow-x-auto [scrollbar-width:none]"} aria-label="주 메뉴">
      {items.map(({ label, href, icon: Icon, match }) => {
        const active = match(path);
        return (
          <li key={href} className="shrink-0">
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors ${
                active
                  ? "border border-accent/50 bg-gradient-to-r from-accent/30 to-accent-2/10 font-semibold text-white shadow-[0_0_24px_-10px_rgb(124_92_255/0.9)]"
                  : "border border-transparent text-zinc-300 hover:bg-white/5 hover:text-white"
              }`}
            >
              <Icon className="size-4.5" aria-hidden />
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** 로그인 전 사이드바 안내. 버튼 이름은 위쪽 바의 "Steam으로 로그인"과 겹치지 않게 다르게 둔다. */
function LoginPrompt() {
  if (useLoggedIn() !== false) return null;
  return (
    <div className="mt-6 rounded-xl border border-accent/30 bg-accent/10 p-4 text-sm text-zinc-200">
      <p>Steam으로 로그인하면 내 라이브러리 분석, 추천, 할인, 공식 뉴스를 볼 수 있어요.</p>
      <a href={STEAM_LOGIN_URL} className="btn-primary mt-3 w-full">
        로그인하고 시작하기
      </a>
    </div>
  );
}
