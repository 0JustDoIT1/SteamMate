import { defineConfig, devices } from "@playwright/test";

/**
 * E2E(9단계, PRD DoD): 실제 Steam API + 내 계정으로 로컬에서만 돌린다(CI 제외 — 사용자 결정).
 *
 *   개발 서버:  npm run e2e                                  (http://localhost:3000)
 *   운영 구성:  E2E_BASE_URL=http://localhost:8080 npm run e2e  (compose.prod.yml)
 *   로그인 흐름까지: E2E_STEAMID=<내 17자리 SteamID> 를 함께 준다. 없으면 로그인 테스트는 건너뛴다.
 *
 * Steam 로그인 화면은 자동화할 수 없어 global-setup이 서명된 세션 쿠키를 직접 만든다(운영 코드 변경 없음).
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  // Steam 응답·첫 질문(공지 수집·색인)이 느릴 수 있어 넉넉히. 실제 외부 API라 재시도 1회
  timeout: 90_000,
  expect: { timeout: 30_000 },
  retries: 1,
  // 같은 계정으로 Steam을 동시에 두드리지 않게 한 번에 하나씩
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    locale: "ko-KR",
  },
  projects: [
    { name: "anon", testMatch: /anon\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "user",
      testMatch: /user\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/user.json" },
    },
  ],
});
