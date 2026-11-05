import { expect, test } from "@playwright/test";

// 비로그인 흐름(PRD DoD: 대시보드 표시 → 뉴스 표시, 로그인 진입)
const TERRARIA = 105600;

test("대시보드는 로그인 없이 보이고 로그인 버튼이 있다", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "SteamMate" })).toBeVisible();
  const sections = page.getByRole("tablist", { name: "대시보드 섹션" });
  await expect(sections).toBeVisible();
  await expect(sections.getByRole("tab").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Steam으로 로그인" })).toHaveAttribute("href", /\/api\/auth\/steam\/login/);
});

test("Steam 로그인은 이 사이트로 돌아오는 OpenID 주소로 보낸다", async ({ request, baseURL }) => {
  const res = await request.get("/api/auth/steam/login", { maxRedirects: 0 });
  expect(res.status()).toBe(302);
  const location = new URL(res.headers()["location"]);
  expect(location.origin).toBe("https://steamcommunity.com");
  expect(location.searchParams.get("openid.return_to")).toBe(`${baseURL}/api/auth/steam/callback`);
  expect(location.searchParams.get("openid.realm")).toBe(baseURL);
});

test("로그인하지 않으면 내 라이브러리 대신 로그인 안내를 보인다", async ({ page }) => {
  await page.goto("/me");
  await expect(page.getByText("내 라이브러리를 보려면 Steam 로그인이 필요합니다.")).toBeVisible();
});

test("위조한 세션 쿠키는 로그인으로 인정하지 않는다", async ({ page, context, baseURL }) => {
  await context.addCookies([{ name: "sm_session", value: "forged.token.value", url: baseURL! }]);
  await page.goto("/me");
  await expect(page.getByText("내 라이브러리를 보려면 Steam 로그인이 필요합니다.")).toBeVisible();
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
});

test("게임 뉴스는 공식 공지 목록과 원문 링크를 보인다", async ({ page }) => {
  await page.goto(`/news/${TERRARIA}`);
  await expect(page.getByRole("heading", { level: 1, name: "Terraria" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "공식 공지" })).toBeVisible();
  // 공지마다 Steam(또는 외부) 원문으로 가는 링크
  const originals = page.getByRole("link", { name: /전문 보기/ });
  await expect(originals.first()).toBeVisible();
  await expect(originals.first()).toHaveAttribute("href", /^https:\/\//);
});

test("API 오류는 정해진 형식으로 알린다", async ({ request }) => {
  const res = await request.get("/api/steam/news/0");
  expect(res.status()).toBe(422);
  expect((await res.json()).error.code).toBeTruthy();
});
