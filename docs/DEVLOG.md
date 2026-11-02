# SteamMate 개발 로그

> 진행 상황·결정·변경 내역·검증 결과를 기록한다. 설계 기준은 [PRD.md](PRD.md)이며, 이 문서는 "언제 무엇을 했고 왜 그렇게 결정했는가"를 남긴다.
> 표기: **[확인]** 실행·조회로 검증 / **[추정]** 외부 문서·추론 기반, 구현 시 검증 필요

---

## 현재 상태 (2026-11-03 기준)

| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | PRD v6 반영, Claude Code 가드레일 | ✅ 완료 |
| 1 | 실행 환경 정비, 테스트 기반, CI, 프론트 Provider·프록시 | ✅ 완료 (CI 통과) |
| 2 | Steam 로그인 + `/me/library` 기본 조회 | ✅ 완료 (실계정 로그인·로그아웃 확인) |
| 3a | 메타데이터 캐시(game_metadata, 레이트리미터) | ⏭ 다음 |
| 3b | 소스 스파이크 → 인기 대시보드 | 대기 |
| 4 | 라이브러리 분석 + 보유 게임 추천·이유 | 대기 |
| 5 | 가격·할인(위시리스트·DLC·미보유 추천) | 대기 |
| 6 | 뉴스 조회·정제 (R1 완료) | 대기 |
| 7 | Full Context vs RAG 실험 | 대기 (LLM 제공자 결정 필요) |
| 8 | 뉴스 AI 질문 (R2 완료) | 대기 |
| 9 | E2E·배포 | 대기 (배포 대상 결정 필요) |

> 11-03 PRD v6.1로 단계 재배치(로그인 → 대시보드 → 기능). 이전 계획의 "입력 파서" 단계는 삭제.

**커밋**: `b9aeec4` 기본 뼈대 → `b5f579a` 환경설정(0·1단계) → `677220c` 오류 코드 PRD 추가 → `3f62620` CI 타입 검사 수정

---

## 결정 로그

| 날짜 | 결정 | 이유 |
|---|---|---|
| 11-03 | 기능 범위 확장: Steam 로그인(F1), 할인(F4: 위시리스트·DLC·미보유 추천), 인기 대시보드(F5), 점수 기반 추천 이유 | 사용자 요청 |
| 11-03 | 릴리스 분할 R1(F1~F5 + 뉴스 목록) / R2(뉴스 AI 질문) | 기능이 3개→6개로 늘어 범위 관리 필요. 핵심 기술 과제(F6)는 R2에서 반드시 수행 |
| 11-03 | 미보유 할인 추천 후보 = Steam 할인·인기·신작 목록에 오른 게임, "후보 N개 기준" 표시 | 전체 할인 목록 공식 API 없음, 스크래핑 배제 |
| 11-03 | 프론트 상태: 서버 데이터 = TanStack Query, 전역 상태 = Zustand, 서버 데이터 복제 금지 | 사용자 선택 |
| 11-03 | 브라우저 → Next `/api/*` rewrites → FastAPI | 로그인 쿠키를 동일 출처로, CORS 불필요, 백엔드 URL 비노출 |
| 11-03 | 사용자 데이터는 DB 비저장(세션은 서명 쿠키), DB는 공개 게임·집계 데이터만 | PRD 개인정보 원칙 유지 |
| 11-03 | 주기 수집은 asyncio 태스크 + PostgreSQL advisory lock | 단일 인스턴스 전제, 스케줄러 라이브러리 불필요 |
| 11-03 | 쿠키 서명 `itsdangerous`(직접 hmac 구현 대신) | 보안 코드 직접 구현 위험 회피 |
| 11-03 | 가드레일: Claude Code hooks + CI 도입, pre-commit 보류 | 1인 개발에서 CI와 역할 중복 |
| 11-03 | 오류 코드에 `NOT_FOUND`, `INTERNAL_ERROR` 추가 | 라우팅·예상치 못한 오류도 공통 형식으로 응답 |
| 11-03 | LLM 제공자·배포 대상은 미정, 각각 7단계·9단계 직전에 결정 | 사용자 답변 |
| 11-03 | **로그인 필수, 본인 데이터만 조회** (PRD v6.1). SteamID·URL 입력과 `/steam/profile/resolve` 삭제, 개인 API는 `/me/*`이며 세션 steamId만 사용 | 타인 라이브러리를 꺼내 보는 구조는 개인정보 측면에서 부적절(사용자 지적) |
| 11-03 | 구현 순서: 로그인(+내 라이브러리) → 대시보드(3a 메타 캐시, 3b 수집·화면) → 분석·추천 → 할인 → 뉴스 | 서비스 시작점이 로그인, 첫 화면이 대시보드. 메타 캐시는 대시보드·추천 공용이라 대시보드 단계에 포함 |
| 11-03 | 대시보드·뉴스는 비로그인 열람 허용 | 공개 데이터 |
| 11-03 | 라이브러리 비공개 판별: GetOwnedGames 빈 응답 → GetPlayerSummaries로 프로필 비공개/게임 세부정보 비공개 구분 | 2단계 스파이크 결과 |
| 11-03 | 로그인은 같은 창 이동 유지(팝업 X), 로그인 후 `/me`로 이동 | 팝업 차단·모바일·보안 검증 부담. 사용자 결정 "그대로" |
| 11-03 | SteamID 직접 입력 기능 추가하지 않음(로그인만) | v6.1 원칙 유지. 입력 허용 시 타인 조회를 막을 수 없음. 사용자 결정 "그대로" |
| 11-03 | 로그인 상태는 TanStack Query `['me']`로 관리, Zustand에서 `steamId` 제거 | 서버 데이터는 Query 단독 관리 원칙 |

**보류 중인 결정**
- 추천 점수 가중치 확정 (4·7단계 착수 시)
- 수집 주기·보관 기간·대시보드 섹션 (6단계 스파이크 결과 후)
- 90% coverage 임계값, Full Context↔RAG 기준 (측정 후)
- 뉴스 AI 공개 여부 (권리 확인 전까지 공개 배포 기본 OFF)

---

## 단계별 변경 내역

### 0단계 — PRD 반영·가드레일 (2026-11-03)

**변경**
- `docs/PRD.md` v6: 기능 F1~F6, 릴리스 분할, API 표 통일, 데이터 모델 4개 테이블, 오류 코드, 점수식 초안, 프론트 상태관리, 기술 선정, 0~11단계 계획. 뉴스·개인 데이터 비저장 원칙과 RAG 실험 설계는 원문 유지
- `.claude/settings.json`: `docs/PRD.md` 편집 시 확인(`permissions.ask`), hooks 등록
- `.claude/hooks/guard-git.js`: `git push`·`reset --hard`·`rebase`·`branch -D`·`--force`·`commit --amend`·`clean -f` 차단
- `.claude/hooks/lint-changed.js`: 편집 후 `backend/**/*.py` → ruff, `frontend/**/*.ts(x)` → eslint

**검증** [확인]
- guard-git: 위험 명령 차단 / `status`·`commit`·`log` 통과, 세션 내 실제 차단 확인
- lint hook: 정상 파일 통과, 미사용 import 검출

**참고**: guard-git은 명령 문자열에 `git push`만 있어도 차단한다(넉넉한 차단). push는 사용자가 터미널에서 직접 실행.

### 1단계 — 실행 환경 정비 (2026-11-03)

**발견한 문제** [확인]
1. `.env`는 `backend/app/`, 설정은 실행 위치 기준 `.env`를 읽음 → 서버 기동 실패 가능
2. `CORS_ORIGINS`가 일반 문자열·빈 값이면 `SettingsError`
3. `db.py`가 import 시점에 엔진 생성 → 테스트에서 설정 주입 불가
4. Alembic `target_metadata=None`
5. 테스트·CI 없음

**변경**
- 백엔드
  - `app/config.py`: `backend/.env` 절대경로 고정, CORS 콤마/JSON 배열 파싱
  - `app/db.py`: `Base`, 엔진·세션 지연 생성(`get_engine`, `get_sessionmaker`, `dispose_engine`)
  - `app/main.py`: `create_app()`, lifespan(로그 마스킹 설정·엔진 정리), 오류 핸들러 등록
  - `app/errors.py` (신규): `ErrorCode`, `AppError`, `{"error":{"code","message"}}` 공통 응답, 내부 예외 메시지 비노출
  - `app/logging_config.py` (신규): 로그의 `?key=...`·Steam 키 값 마스킹
  - `migrations/env.py`: import 정리, `target_metadata = Base.metadata`
  - `.env.example`: `backend/`로 이동(사용자), 예시 값 채움. 실제 `.env`도 사용자가 `backend/.env`로 이동
  - `pytest.ini`, `tests/`: 설정 파싱·오류 형식·마스킹·health 테스트. DB 테스트는 `db` 마커 + `TEST_DATABASE_URL` 있을 때만 실행
- 프론트
  - 설치: `@tanstack/react-query`, `zustand`, (dev) `@tanstack/react-query-devtools`, `openapi-typescript`
  - `src/app/providers.tsx`: QueryClient를 컴포넌트 인스턴스마다 생성
  - `src/stores/app-store.ts`: Zustand 전역 상태, `excludedAppids`만 localStorage 저장
  - `next.config.ts`: `/api/:path*` → `BACKEND_URL` rewrites
  - `layout.tsx`: `lang="ko"`, 타이틀, Provider
  - `.gitignore`에 `!.env.example`, `.env.example`(`BACKEND_URL`)
  - 스크립트: `typecheck`(`next typegen && tsc --noEmit`), `gen:api`
- CI `.github/workflows/ci.yml`: 백엔드(ruff, alembic up/down/up, pytest + Postgres 17), 프론트(lint, typecheck, build)

**검증** [확인]
| 항목 | 결과 |
|---|---|
| ruff | 통과 |
| pytest (로컬 DB `steammate_test`) | 18 passed |
| 실제 `.env` 로드 | 값 존재, 드라이버 `postgresql+asyncpg` |
| `/health/db` | `{"db":"ok"}` |
| Alembic up→down→up | 통과 (마이그레이션 0개 — 연결·설정만 검증) |
| FE lint / typecheck / build | 통과 |
| `/api` 프록시 | `localhost:3000/api/health` → FastAPI 응답, 없는 경로 `NOT_FOUND` |
| CI (`3f62620`) | 백엔드·프론트 모두 성공 |

**겪은 문제**
- CI 첫 실행(`b5f579a`)에서 프론트 typecheck 실패: `LayoutProps` 등 Next 전역 타입은 `.next/types`에 생성되는데 CI는 빈 체크아웃. → `next typegen` 선행으로 해결(Next 16 문서 권장 방식)
- ruff 규칙이 기본보다 넓음(설정 파일 없음). ruff 0.17 기본값으로 추정 [추정], CI에서 동일 결과 확인 [확인]

### 2단계 — Steam API 스파이크 (2026-11-03, 진행 중)

실제 API 키로 응답 구조 확인(키·개인 데이터 미출력, 스크립트는 저장소 밖). [확인]

| 호출 | 결과 |
|---|---|
| GetOwnedGames — 공개 라이브러리(사용자 본인 계정) | HTTP 200, `response: {game_count, games[]}`. 게임 필드: `appid`, `name`, `img_icon_url`, `playtime_forever`, `rtime_last_played`, 플랫폼별 playtime(모든 게임), `playtime_2weeks`(최근 플레이한 게임만), `has_community_visible_stats`·`content_descriptorids`(일부) |
| GetOwnedGames — 프로필 공개·게임 세부정보 비공개(robinwalker) | HTTP 200, `response: {}` (오류 아님) |
| GetPlayerSummaries | `communityvisibilitystate`: 공개 = 3. 존재하지 않는 ID → `players: []` |
| ResolveVanityURL 실패 | `success: 42, message: "No match"` (v6.1에서 미사용) |
| 형식이 잘못된 steamid | HTTP 400 `text/html` |
| 잘못된 API 키 | HTTP 401 |

이후 PRD v6.1(로그인 필수)로 방향 전환 — 2단계를 로그인 + `/me/library`로 재정의.

### 2단계 — Steam 로그인 + 내 라이브러리 (2026-11-03)

**변경**
- 백엔드
  - `app/auth/session.py`: `itsdangerous` 서명 쿠키 `sm_session`(steamId + 만료 7일). 위조·만료·형식 오류는 None
  - `app/auth/steam_openid.py`: 로그인 URL 생성, 콜백 검증(mode·op_endpoint·return_to·claimed_id/identity 일치 → nonce 재사용·5분 초과 차단 → Steam `check_authentication` 서명 재검증)
  - `app/steam/web_api.py`: GetOwnedGames·GetPlayerSummaries 클라이언트, Pydantic 응답 검증, 오류 매핑(429→`STEAM_RATE_LIMITED` 503, 타임아웃→`STEAM_TIMEOUT` 504, 401/403·5xx·스키마 불일치→`STEAM_UNAVAILABLE` 502)
  - `app/library.py`: 본인 라이브러리 조회·정렬(플레이시간 desc, appid asc)·요약 통계, 빈 응답 시 비공개 사유 구분(`LIBRARY_PRIVATE`/`PROFILE_NOT_FOUND`)
  - `app/routers/auth.py`: `/auth/steam/login`, `/auth/steam/callback`(성공 → 쿠키 + `/me`, 실패 → `/?login=failed`), `/auth/me`, `/auth/logout`
  - `app/routers/me.py`: `/me/library` (세션 steamId만 사용)
  - `app/deps.py`: 의존성(HTTP 클라이언트·세션·`current_steam_id`)
  - `app/main.py`: 외부 HTTP 클라이언트·세션·nonce 저장소를 `create_app`에서 생성(테스트 주입 가능), 로그 마스킹에 `SESSION_SECRET` 추가
  - 설정: `SESSION_SECRET`(필수, 32자 이상), `PUBLIC_BASE_URL`, `SESSION_MAX_AGE_SECONDS`. `requirements.txt`에 `itsdangerous==2.2.0`. CI에 더미 `SESSION_SECRET`
- 프론트
  - `src/lib/api/schema.d.ts`: OpenAPI에서 생성한 타입, `src/lib/api/client.ts`: `/api` fetch + `ApiError`
  - `src/features/auth/queries.ts`(`useMe`, `useLogout`), `src/features/library/queries.ts`(`useMyLibrary`)
  - `src/components/site-header.tsx`: 로그인/로그아웃 헤더, `src/app/home-login-panel.tsx`: 첫 화면 로그인 안내·실패 메시지
  - `src/app/me/`: 내 라이브러리(요약 통계, 게임 목록, 비공개 안내·Steam 공개 설정 링크, 오류·재시도)
  - `src/lib/use-hydrated.ts`: hydration 중에는 서버와 같은 화면 유지
  - Zustand에서 `steamId` 제거

**검증**
| 항목 | 결과 |
|---|---|
| pytest | 59 passed (세션 6, OpenID 14, `/me/library` 16, 인증 라우트 5 등) [확인] |
| FE lint / typecheck / build | 통과 [확인] |
| 프록시 경유 `/api/auth/steam/login` | 302 → steamcommunity.com [확인] |
| 실계정 Steam 로그인 → `/me` 게임 목록 | 정상 표시 (사용자 확인) [확인] |
| 로그아웃 브라우저 동작 | 정상 (사용자 확인) [확인] |
| 비공개 안내 화면 | 테스트로 검증, 실계정 화면 확인은 생략(사용자 판단) |

**겪은 문제**
- 개발 서버가 다른 폴더에서 실행되어 실패 → `npm --prefix`로 경로 명시
- **Hydration 불일치**: `/me` 서버 HTML은 "확인 중…"인데, 헤더가 먼저 hydration되며 `useMe`가 완료된 뒤 `/me` 본문이 스트리밍으로 늦게 hydration되어 "불러오는 중…"으로 렌더 → `useHydrated()`(`useSyncExternalStore`)로 hydration 중에는 서버와 같은 화면을 그리도록 수정. 수정 후 개발 서버 로그·브라우저 콘솔 모두 재발 없음 (사용자 확인) [확인]
- 테스트에서 수동 설정한 쿠키와 서버 삭제 쿠키의 도메인이 달라 로그아웃 테스트 실패 → 실제 흐름(콜백으로 로그인)으로 테스트 수정

**참고**
- 타입 생성: 백엔드 실행 중 `npm run gen:api` (또는 OpenAPI JSON을 추출해 `npx openapi-typescript <file>`)
- `/me/library` 응답의 장르 분포·`metadataCoverage`는 4단계에서 추가(PRD 명세상 포함 예정)

---

## 미확인·추정 사항 (구현 시 검증)

| 항목 | 확인 시점 |
|---|---|
| ~~비공개 계정 GetOwnedGames가 오류 대신 빈 `response` 반환~~ | ✅ 2단계 스파이크로 확인 |
| `communityvisibilitystate` 1 = 프로필 비공개 (공개 = 3은 확인) | 2단계 |
| 게임 0개 계정의 GetOwnedGames 응답 형태(`game_count: 0` 여부) | 2단계 |
| 로그인해도 비공개 라이브러리 조회 불가 (서버는 API 키로 조회하므로 로그인 여부와 무관 — 구조상 성립) | 2단계, 실계정 비공개 전환 테스트는 생략 |
| store appdetails 레이트리밋(약 200회/5분) | 3a단계 |
| featuredcategories 스키마, GetMostPlayedGames 공개 접근 | 3b단계 스파이크 |
| appdetails `filters=price_overview` 다중 appid 지원 | 5단계 |
| IWishlistService/GetWishlist 공개 접근·응답 형식 (비문서화) | 5단계 |
| GetOwnedGames로 DLC 보유 여부 판별 불가 | 5단계 |
| 비문서화 엔드포인트·차트 데이터 공개 서비스 이용 약관 | 출시 전 |

---

## 로컬 개발 메모

- DB: `docker compose up -d db` (호스트 5433), 테스트 DB `steammate_test`는 컨테이너 안에 수동 생성
- DB 테스트 실행: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://steammate:steammate@localhost:5433/steammate_test pytest`
- 백엔드: `cd backend && source .venv/Scripts/activate && uvicorn app.main:app --reload` (`backend/.env`에 `SESSION_SECRET` 필요)
- 프론트: `cd frontend && npm run dev` (`/api/*`는 `BACKEND_URL`로 프록시)
- push는 사용자가 직접 (`git push origin main`), CI 결과는 GitHub Actions에서 확인
