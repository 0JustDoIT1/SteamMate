import type { NextConfig } from "next";

// 브라우저는 /api/*만 호출하고 Next 서버가 FastAPI로 프록시한다(동일 출처 쿠키, 백엔드 URL 비노출).
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  reactCompiler: true,
  experimental: {
    // rewrites 프록시 기본 제한 30초. 뉴스 AI 첫 질문(공지 수집·색인·모델 로딩)은 30초를 넘길 수 있어
    // 백엔드 질문 제한(qa_timeout_seconds 120초)보다 길게 둔다.
    proxyTimeout: 130_000,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
