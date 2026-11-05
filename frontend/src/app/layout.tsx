import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import "./globals.css";
import AppSidebar, { MobileNav } from "@/components/app-sidebar";
import SiteHeader from "@/components/site-header";

import Providers from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SteamMate",
  description: "Steam 라이브러리 분석, 보유 게임 추천, 할인과 인기 게임 정보",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // 디자인은 어두운 테마 하나만 둔다(globals.css의 dark 변형이 html.dark를 본다)
    <html lang="ko" className={`dark ${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full">
        <Providers>
          <div className="flex min-h-screen">
            {/* 메뉴의 현재 위치는 요청 주소로 정한다(cacheComponents: 요청 때 정해지는 값이라 Suspense 안) */}
            <Suspense fallback={<div className="hidden w-60 shrink-0 lg:block" />}>
              <AppSidebar />
            </Suspense>
            <div className="flex min-w-0 flex-1 flex-col">
              <SiteHeader />
              <Suspense fallback={null}>
                <MobileNav />
              </Suspense>
              {children}
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
