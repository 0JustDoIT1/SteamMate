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

  // 마무리해 볼 게임(업적): 진행 막대 또는 비공개·없음 안내 중 하나
  const nearly = page.locator("section", { has: page.getByRole("heading", { name: "마무리해 볼 게임" }) });
  await expect(nearly.getByRole("progressbar").first().or(nearly.getByText(/비공개|게임이 없습니다/))).toBeVisible({
    timeout: 60_000,
  });
  await expect(nearly.getByRole("alert")).toHaveCount(0);
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

test("공식 뉴스: 내 게임 최근 소식이 최신순으로 보인다", async ({ page }) => {
  await page.goto("/news");
  const feed = page.locator("section", { has: page.getByRole("heading", { name: "내 게임 최근 소식" }) });
  // 첫 항목이 나올 때까지(화면이 데이터를 받기 전에 "로딩 끝"으로 오판하지 않게)
  await expect(feed.locator("ol > li").first()).toBeVisible({ timeout: 60_000 });
  await expect(feed.getByRole("alert")).toHaveCount(0);
  const times = await feed.locator("time").evaluateAll((els) => els.map((e) => e.getAttribute("datetime") ?? ""));
  expect(times.length).toBeGreaterThan(0);
  expect([...times].sort().reverse()).toEqual(times); // 최신 먼저
});

test("공식 뉴스: 보유 게임 목록에서 그 게임의 공지로 이동한다", async ({ page }) => {
  await page.goto("/news");
  const list = page.locator("section", { has: page.getByRole("heading", { name: "보유 게임 목록" }) });
  // 이름 검색: 첫 게임 이름 일부로 찾으면 그 게임이 남고, 없는 이름이면 안내
  const firstName = (await list.locator("li p.font-medium").first().innerText()).trim();
  const search = list.getByRole("searchbox", { name: "게임 이름 검색" });
  await search.fill(firstName.slice(0, 4));
  await expect(list.locator("li").filter({ hasText: firstName })).toHaveCount(1);
  await search.fill("zzzz-없는-게임");
  await expect(list.getByText("일치하는 게임이 없습니다")).toBeVisible();
  await search.fill("");
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

  // 질문 칸을 누르면 서버에 미리 준비를 한 번 시킨다(PRD v6.15)
  const warmup = page.waitForRequest((r) => r.url().endsWith("/api/steam/news/105600/ask/warmup") && r.method() === "POST");
  await page.getByRole("textbox", { name: "질문" }).focus();
  expect((await (await warmup).response())?.status()).toBe(202);

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
