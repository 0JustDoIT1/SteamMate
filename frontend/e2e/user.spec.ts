import { expect, test } from "@playwright/test";

// 로그인 흐름(PRD DoD: Steam 로그인 → 내 게임 분석 → 보유 게임 추천(이유) → 할인 → 뉴스 → 질문 → 로그아웃).
// 실제 Steam API와 내 계정 데이터를 쓴다. E2E_STEAMID가 없으면 건너뛴다(global-setup 참조).
test.skip(!/^\d{17}$/.test(process.env.E2E_STEAMID ?? ""), "E2E_STEAMID(17자리)가 필요합니다");

test("내 라이브러리: 요약과 보유 게임 추천(점수·이유)", async ({ page }) => {
  await page.goto("/me");
  await expect(page.getByRole("heading", { level: 1, name: "내 라이브러리" })).toBeVisible();
  await expect(page.getByRole("button", { name: "로그아웃" })).toBeVisible();
  // 위쪽 바: 내 Steam 프로필(닉네임·사진), 누르면 Steam 프로필로
  await expect(page.getByRole("link", { name: /.+/ }).filter({ has: page.locator("img.rounded-full") })).toHaveAttribute(
    "href",
    /^https:\/\/steamcommunity\.com\//,
  );
  await expect(page.getByRole("list", { name: "주 메뉴" }).first().getByRole("link")).toHaveCount(6);
  await expect(page.getByText("플레이한 게임")).toBeVisible();

  const recs = page.getByRole("heading", { name: /다음에 할 게임|이어서 하기/ });
  await expect(recs).toBeVisible();
  const section = page.locator("section", { has: recs });
  await expect(section.getByText(/후보 \d+개 중 상위/)).toBeVisible({ timeout: 60_000 });
  await expect(section.locator("ol > li").first()).toContainText(/점/);
});

test("사이드바 메뉴마다 한 페이지: 구매 추천·할인·장르 취향", async ({ page }) => {
  await page.goto("/me");
  const nav = page.getByRole("list", { name: "주 메뉴" }).first();

  await nav.getByRole("link", { name: "구매 추천" }).click();
  await expect(page).toHaveURL(/\/me\/store$/);
  await expect(page.getByRole("heading", { name: "내 취향에 맞는 인기 게임" })).toBeVisible();

  await nav.getByRole("link", { name: "할인" }).click();
  await expect(page).toHaveURL(/\/me\/deals$/);
  const deals = page.locator("section", { has: page.getByRole("heading", { name: "할인", exact: true, level: 2 }) });
  await expect(deals).toBeVisible();
  await expect(deals.getByText("할인 정보를 불러오는 중…")).toBeHidden({ timeout: 60_000 });
  await expect(deals.getByRole("alert")).toHaveCount(0);

  await nav.getByRole("link", { name: "장르 취향" }).click();
  await expect(page).toHaveURL(/\/me\/genres$/);
  await expect(page.getByRole("heading", { name: "내 장르 취향" })).toBeVisible();
});

test("공식 뉴스: 보유 게임 목록에서 그 게임의 공지로 이동한다", async ({ page }) => {
  await page.goto("/news");
  const list = page.locator("section", { has: page.getByRole("heading", { name: "보유 게임 목록" }) });
  await list.getByRole("link", { name: "뉴스" }).first().click();
  await expect(page).toHaveURL(/\/news\/\d+$/);
  await expect(page.getByRole("heading", { name: "공식 공지" })).toBeVisible();
});

test("공지 질문: 켜진 환경이면 근거와 함께 답하고, 꺼진 환경이면 안내만 보인다", async ({ page }) => {
  test.setTimeout(180_000); // 첫 질문은 공지 수집·색인·모델 로딩으로 길다
  await page.goto("/news/105600");
  const disabled = page.getByText("이 환경에서는 공지 AI 질문을 제공하지 않습니다.");
  const ask = page.getByRole("button", { name: "최신 업데이트에서 바뀐 점은?" });
  await expect(disabled.or(ask)).toBeVisible();
  if (await disabled.isVisible()) return; // 운영 구성(NEWS_AI_ENABLED=false)

  await ask.click();
  await expect(page.getByText("답변 만드는 중…")).toBeHidden({ timeout: 150_000 });
  // 질문 영역 안에서만 본다(Next.js가 페이지마다 넣는 경로 안내 요소도 alert 역할이다)
  const askSection = page.locator("section", { has: page.getByRole("heading", { name: "공지에 질문하기" }) });
  await expect(askSection.getByRole("alert")).toHaveCount(0);
  // 업데이트 요약 틀(분야별 목록) + 원문 출처
  await expect(askSection.getByRole("heading", { name: "출처" })).toBeVisible();
  await expect(askSection.getByRole("heading", { name: /새 기능|밸런스 조정|버그 수정/ }).first()).toBeVisible();
});

test("로그아웃하면 세션이 사라진다", async ({ page }) => {
  await page.goto("/me");
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("link", { name: "Steam으로 로그인" })).toBeVisible();
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
});
