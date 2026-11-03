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
| 3a | 메타데이터 캐시(game_metadata, 레이트리미터) | ✅ 완료 |
| 3b | 소스 스파이크 → 인기 대시보드 | ✅ 완료 (브라우저 확인, 커밋) |
| 4 | 라이브러리 분석 + 보유 게임 추천·이유 | ✅ 완료 (화면 확인) |
| 5 | 가격·할인(위시리스트·DLC·미보유 추천) | ⏭ 다음 |
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
| 11-03 | 메타데이터 캐시는 **게임 단위 공용 DB**(사용자 정보와 연결하지 않음), 백그라운드 보강 + 부분 응답 | appdetails 장르는 게임 1개당 요청 1번 → 요청 안에서 대형 라이브러리를 채울 수 없음 |
| 11-03 | 3a 값(임시): 0.6회/초·버스트 10·동시 4, 429/403 시 60초 정지, SUCCESS 7일, NOT_AVAILABLE 30일 재확인, 재시도 5분(오류)/15분(429)/1시간(success:false), PENDING 10분 초과 복구, `cc=kr`·`l=english` | 추정 한도 200회/5분에 여유. 사용자 승인 |
| 11-03 | `success:false`는 연속 2회일 때만 NOT_AVAILABLE, 장르 없는 정상 응답은 즉시 NOT_AVAILABLE | PRD "재확인으로 확정" |
| 11-03 | 만료된 SUCCESS의 갱신이 일시 실패하면 기존 장르 유지 | 일시 장애로 coverage가 떨어지지 않게 |
| 11-03 | `game_metadata.app_type` 컬럼 추가 (PRD 반영) | 사운드트랙·도구 등 비게임 제외용 |
| 11-03 | 대시보드 소스 5종: TOP_SELLERS(한국 주간 판매)·MOST_PLAYED(주간)·CONCURRENT(현재)·SPECIALS·NEW_RELEASES, coming_soon 제외 (PRD 반영) | 3b 스파이크에서 4개 API 모두 사용 가능 확인 |
| 11-03 | 순위 변화는 Steam `last_week_rank` 사용, 스냅샷 보관 12주 → 2주 (PRD 반영) | 직접 이력 계산 불필요 |
| 11-03 | `chart_entry`에 이름·지난주 순위·가격·할인율·이미지 컬럼 추가 (PRD 반영) | 대시보드 표시용 |
| 11-03 | 수집 1시간마다, 소스별 간격 CONCURRENT 1h / 기획·주간 6h, 주간 차트는 집계일이 같으면 저장 생략 (임시) | |
| 11-03 | 로그인 시 개인화는 백엔드에서 계산, 보유 목록은 메모리 5분 TTL 캐시(저장 X) (PRD 반영) | 취향 점수 정의를 4단계 추천과 공유 |
| 11-03 | 대시보드 판매·최다 플레이에 주간/월간/연간 탭. 월간=최근 4주, 연간=최근 52주 주간 순위 합산(주마다 101−순위점), "Steam 공식 순위 아님" 명시 (PRD 반영) | 사용자 요청. Steam에 월·연 순위 API 없음 |
| 11-03 | 판매 순위는 과거 52주 백필(`start_date` 지정 조회 가능), 최다 플레이는 과거 조회 불가라 쌓이는 만큼만. 주간 차트 보관 53주(집계 주 기준) (PRD 반영) | 3b 추가 스파이크 |
| 11-03 | `game_metadata.header_image`에 이미지 **주소만** 저장, 대시보드는 이 값 우선 → 추정 주소 → 로딩 실패 시 대체 칸 (PRD 반영) | 추정 주소가 차트 항목의 17~37% 404 |
| 11-03 | 메타데이터 대기열 우선순위: 사용자 화면(HIGH) > 수집 작업(LOW), 대기 중 LOW는 HIGH 요청 시 앞당김 (PRD 반영) | 1년치 차트 게임이 사용자 라이브러리 보강을 밀어내지 않도록 |
| 11-03 | 대시보드 공개 부분 2분 메모리 캐시, 개인화는 그 위에 덧붙임 | 52주 집계를 요청마다 재계산하지 않도록 |
| 11-03 | 순위 차트 기준 통일: 판매 순위도 **전 세계** (PRD 반영). 할인·신작은 상점 기획 목록이며 가격만 한국 상점 기준 | 사용자 지적. 최다 플레이·접속은 국가별 제공 없음 |
| 11-03 | 많이 플레이한 게임은 **주간만**(월·연 탭 제거), 보관 2주로 복귀 (PRD 반영) | 사용자 결정. 과거 기록이 없어 1년 뒤에야 의미가 생김 |
| 11-03 | **가드레일 추가**: 새 라이브러리는 "직접 구현" 포함 장단점 비교 후 사용자가 선택(CLAUDE.md), 패키지 설치 명령은 항상 확인 창(`permissions.ask`) | 사용자 요청 |
| 11-03 | 대시보드를 2단 세로 표 + 추이 그래프로 개편. 그래프는 **shadcn/ui Charts(recharts)**, 설치는 수동 복사 방식 (PRD 반영) | 사용자 선택(직접 SVG·recharts·uPlot 비교 후). CLI는 전체 테마·설정을 건드릴 위험 |
| 11-03 | 추이: 판매 순위 최근 12주 순위, 현재 접속 최근 7일(3시간 단위)·24시간 최고. 최다 플레이·할인·신작은 그래프 없음 | 보유 데이터 기준 |

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
- `/me/library` 응답의 장르 분포·`metadataCoverage`는 4단계에서 추가(PRD 명세상 포함 예정) → coverage·게임별 장르는 3a에서 추가됨

### 3a단계 — 게임 메타데이터 캐시 (2026-11-03)

**스파이크** [확인] — store appdetails
| 확인 | 결과 |
|---|---|
| 단일 appid | `success:true`, `type`·`genres[{id,description}]`·`categories`·`dlc` 등 |
| 없는 appid | HTTP 200 `{"success": false}` |
| 다중 appid | 필터 없음·genres 필터 → HTTP 400. `price_overview` 필터만 다중 허용(5단계 가격에 활용) |
| 무료 게임 가격 | `data: []` |
| 레이트리밋 헤더 | 없음 (`cache-control: max-age` 120~7200만 있음) |

**변경**
- `app/models.py`: `GameMetadata`, `FetchStatus` (PostgreSQL enum `fetch_status`)
- `migrations/versions/25542961bbf2_create_game_metadata.py`: 첫 마이그레이션. 자동 생성본의 downgrade가 enum 타입을 남겨 재적용이 실패하는 문제를 수정
- `app/steam/store_api.py`: appdetails 클라이언트, 결과를 `OK/NOT_FOUND/RATE_LIMITED/ERROR`로 분류(403도 일시 제한으로 취급 [추정])
- `app/infra/rate_limit.py`: 토큰 버킷(시계 주입), `pause()`
- `app/metadata/state.py`: 상태 전이·재조회 판단 순수 함수
- `app/metadata/service.py`: `lookup()`(DB 조회 + 대상 PENDING 기록 + 대기열 등록, 즉시 반환), 워커(레이트리미터 → 조회 → upsert), 진행 중 중복 방지, 워커 예외 격리
- `app/metadata/coverage.py`: `metadataCoverage`·`metadataSnapshotAt` 계산
- `/me/library`: 게임별 `metadataStatus`·`appType`·`genres`, `metadataCoverage`, `metadataSnapshotAt` 추가
- `app/schemas.py`: `CamelModel` 공용화, 설정에 상점·캐시 값 추가
- CI: `alembic check`(모델과 마이그레이션 일치 검사) 추가
- 프론트: API 타입 재생성(화면 변경은 4단계)

**검증**
| 항목 | 결과 |
|---|---|
| pytest (DB 포함) | 114 passed / DB 없이 104 passed, 10 skipped [확인] |
| 상태 전이 표 테스트 | 429·5xx·타임아웃·스키마 불일치 × 이전 상태 4종 → 항상 TEMPORARY_ERROR [확인] |
| DB 통합 테스트 | 부분 응답 후 보강, 동시 5회 lookup → 게임당 1회 조회, 429 → 일시 오류 + 정지, success:false 2회 → 확정, stale PENDING 복구, 신선한 PENDING 중복 방지, 만료 SUCCESS 갱신 실패 시 장르 유지, 워커 예외 후 생존 [확인] |
| Alembic up→down→up, `alembic check` | 통과 [확인] |
| 실계정(58개) 보강 | 첫 응답 pending 58 → 약 90초 후 success 55 / 일시 오류 3(`store_not_found`, 1시간 뒤 재확인) / 429 0회. 상위 장르 Strategy·Action·Indie·Simulation [확인] |
| FE lint / typecheck | 통과 [확인] |

**참고**
- 58개에 약 90초 = 설정 속도(0.6회/초)대로 동작. 1,000개 라이브러리는 약 28분 예상 → 4단계 화면에서 진행률 표시 필요
- 단일 프로세스 전제: 대기열·진행 중 목록은 메모리. 서버 재시작 시 PENDING은 10분 뒤 다음 요청에서 복구

### 3b단계 — 인기 대시보드 (2026-11-03)

**스파이크** [확인]
| 소스 | 결과 |
|---|---|
| `IStoreTopSellersService/GetWeeklyTopSellers` | 파라미터를 `input_json`으로 보내야 동작(일반 쿼리는 빈 응답). 키 불필요. 1~100위, `last_week_rank`·`consecutive_weeks`·이름, `start_date` |
| `ISteamChartsService/GetMostPlayedGames` | 키 불필요. 100위, `last_week_rank`·`peak_in_game`, `rollup_date`. 이름 없음 |
| `ISteamChartsService/GetGamesByConcurrentPlayers` | 키 필요. 100위, `concurrent_in_game` |
| store `featuredcategories` | specials 10·new_releases 30(모두 `type=0`, 중복 없음), KRW 가격·할인율·이미지 |
| 헤더 이미지 | `shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg` 200 |

**변경**
- `app/models.py`: `ChartSnapshot`·`ChartEntry`, enum `chart_source`·`snapshot_status` / 마이그레이션 `eb78d475c786`(downgrade enum 정리 수정)
- `app/steam/charts_api.py`: 4개 소스 → `ChartFetch` 정규화, 실패·빈 목록은 failure로
- `app/jobs/collector.py`: 트랜잭션 단위 advisory lock, 소스별 간격·집계일 중복 생략, FAILED 스냅샷 기록, 2주 보관(소스별 최신 성공본은 유지), 수집 게임 메타데이터 보강 요청 / `app/jobs/collect.py`: 수동 실행 CLI
- `app/owned_cache.py`: 보유 목록 메모리 TTL 캐시(공개 응답만), `/me/library`도 사용
- `app/taste.py`: 장르 취향·매칭도 순수 함수(4단계 재사용)
- `app/dashboard.py`, `app/routers/dashboard.py`: `/steam/dashboard`(비로그인 가능), 섹션별 20개, 순위 변화·NEW, 장르 분포, 로그인 시 보유·매칭도. 비공개·Steam 오류면 개인화 없이 응답, 수집 전이면 `DATA_NOT_READY`
- `app/main.py`: lifespan에서 주기 수집 시작·종료, `create_app(dashboard_service=)` 주입
- 설정: 수집 간격·보관·보유 캐시 TTL, `requirements.txt`에 `cachetools==7.2.8`
- 프론트: `features/dashboard/queries.ts`(수집 전이면 30초 재확인), `app/dashboard-view.tsx`(섹션 가로 목록, 순위 변화, 가격·할인, 보유·취향 매칭, 장르 막대), `lib/format.ts`, 첫 화면에 대시보드 배치

**겪은 문제**
- 세션 단위 advisory lock은 중간 commit 시 연결이 풀에 반환되어 다른 연결에서 해제를 시도 → 잠금 누수 가능. 트랜잭션 단위(`pg_try_advisory_xact_lock`) + 단일 트랜잭션으로 변경
- 주간 차트 집계일이 바뀌지 않으면 새 스냅샷이 없어 2주 정리 시 유일한 성공본까지 삭제될 수 있음 → 소스별 최신 성공본 보존
- 마이그레이션 왕복 검증을 개발 DB에서 실행해 3a 메타데이터 55건이 삭제됨(공용 캐시라 재수집됨). 이후 왕복 검증은 테스트 DB에서만

**검증**
| 항목 | 결과 |
|---|---|
| pytest (DB 포함) | 145 passed — 차트 파싱 9, 취향 4, 보유 캐시 4, 수집 7(간격 생략·집계일 생략·실패 후 재시도·잠금·동시 실행·보관), 대시보드 7(수집 전 503·섹션·실패 섹션 숨김·개인화·비공개/오류 폴백·최신 스냅샷) [확인] |
| Alembic up→down→up, `alembic check` | 통과 [확인] |
| 실데이터 수집(CLI) | 5개 소스 저장(100/100/100/10/30), 메타데이터 약 200건 325초, 429 0회 [확인] |
| `/api/steam/dashboard` (프록시 경유) | 비로그인 5개 섹션·장르 분포(152개 중 147개), 로그인 시 판매 상위 20 중 보유 3개·매칭도 표시 [확인] |
| FE lint / typecheck / build | 통과 [확인] |
| 브라우저 화면 | 사용자 확인 대기 |

**참고**
- TOP_SELLERS의 `start_date`가 2026-10-20(약 2주 전)로 옴 — Steam이 집계 주 시작일을 주는 것으로 보이며 화면에는 수집 시각만 표시 [추정]
- 메타데이터 `success:false` 6건 존재(재확인 대기)

#### 3b 추가 — 이미지·기간 탭·우선순위 (2026-11-03)

**스파이크** [확인]
| 확인 | 결과 |
|---|---|
| 추정 이미지 주소(`.../apps/{appid}/header.jpg`) | 판매 37%·최다 플레이 18%·접속 17% 404. 최근 게임은 해시가 들어간 새 경로 사용 |
| appdetails `header_image` | 정확한 주소 제공(새 경로 포함) |
| GetWeeklyTopSellers `start_date` | 1·4·52주 전 지정 시 해당 주 순위 반환 |
| GetMostPlayedGames 과거 조회 | `rollup_date` 지정(쿼리·input_json 모두) 무시, 항상 최신 |

**변경**
- 마이그레이션 `02b117ec3418`: `game_metadata.header_image`. 기존 정상 응답 행(SUCCESS, 장르만 없는 NOT_AVAILABLE)은 한 번 보충 조회
- `MetadataService`: `PriorityQueue` + `Priority.HIGH/LOW`, 대기 중 항목 앞당기기(옛 사본은 워커가 건너뜀). 라이브러리·대시보드 표시·개인화 = HIGH, 수집 = LOW
- `Collector`: 판매 순위 과거 주 백필(판매 순위 갱신 주기에만, 보관 기간 안의 주만), 소스별 보관 기간(주간 53주·집계 주 기준 / 기타 14일)
- `app/chart_queries.py`: `latest_success_ids()` — "최신" = 집계 주가 가장 늦은 것(같으면 늦게 수집) — 수집 정리·대시보드 공용 (`postgresql.distinct_on`)
- `DashboardService`: 주간 차트 `periods`(MONTH 4주·YEAR 52주, 같은 주는 최신 수집 1개, 점수·순위권 주 수·최고 순위), 이미지 우선순위, 공개 부분 캐시
- `CamelModel`: 출력 스키마에서 기본값 필드도 필수로 표시(`json_schema_serialization_defaults_required`) → 프론트 타입과 실제 응답 일치
- 프론트: `components/game-image.tsx`(로딩 실패 시 대체 칸), 섹션별 주간/월간/연간 탭(1주만 모였으면 비활성), 합산 기준 문구, "순위권 N주 · 최고 M위"

**겪은 문제**
- **"최신 스냅샷 = id 최댓값"이 백필 후 틀림**: 과거 주를 1→51주 전 순서로 저장해 51주 전이 가장 큰 id → 대시보드가 1년 전 순위를 "이번 주"로 보여주고 정리도 엉뚱한 행을 보존할 뻔함. 테스트 실패로 발견, `DISTINCT ON (source, cc) ORDER BY period_start DESC, captured_at DESC`로 수정 + 회귀 테스트
- 백필과 보관 정리가 경계 주를 서로 지우고 다시 받는 반복 가능 → 백필도 보관 기간 안의 주만
- 백필이 매시간 실행되어 받지 못한 주를 반복 요청할 수 있음 → 판매 순위 갱신 주기에만 실행

**검증**
| 항목 | 결과 |
|---|---|
| pytest (DB 포함) | 155 passed [확인] |
| 마이그레이션 왕복·`alembic check` | 테스트 DB에서 통과, 개발 DB는 upgrade만 [확인] |
| 실데이터 백필 | 51주 추가 → 판매 순위 52주(2025-10-28~2026-10-20) [확인] |
| 기간 집계 | 이번 주 1위 Call of Duty(최신 주 정상), 월간(4/4주)·연간(52/52주) 1위 PUBG, 최다 플레이 월·연 1/4·1/52주 [확인] |
| 이미지 | 보충 후 판매·할인·신작 100%, 최다 플레이·접속 각 2건 404 — FiveM(장르 없는 행, 보충 규칙 확장으로 해결) / 3393110(상점 `success:false`, 대체 칸 표시) [확인] |
| FE lint / typecheck / build | 통과 [확인] |
| 브라우저 화면 | 사용자 확인: 판매 순위 기준 불일치, 탭 전환 시 스크롤 튐 → 아래에서 수정 |

#### 3b 추가 — 기준 통일·스크롤 (2026-11-03)

**스파이크** [확인] — GetWeeklyTopSellers
| 요청 | 결과 |
|---|---|
| 최상위 `country_code` = KR / US | 국가별로 다른 목록 |
| `country_code` 생략·빈 값 + `context.country_code` KR/US/DE | **세 경우 동일한 100개 목록**, 국가별 목록과 다름 → 전 세계 순위로 판단. 과거 주 조회·`last_week_rank`도 동작 |
| `country_code` = GLOBAL·global·WW·XX, context 국가 없음 | 빈 응답 |

**변경**
- `charts_api.top_sellers()`: 최상위 `country_code` 제거(전 세계), context 국가는 유지
- 개발 DB의 한국 기준 판매 순위 52주 삭제 후 전 세계 기준으로 재수집·백필(52주) — 공개 집계 캐시라 재수집 가능
- 프론트: 섹션 설명 "전 세계 …", 할인·신작은 "가격은 한국 상점 기준"
- **스크롤 튐 수정**: 원인 ① 가로 목록 스크롤 위치가 탭 전환 후에도 남음 → 탭 전환 시 `scrollTo({left: 0})` ② 탭마다 카드 줄 수가 달라 섹션 높이 변화 → 카드 정보 영역을 5줄 고정(빈 줄은 공백)

**검증**: pytest 155 passed, FE lint·typecheck·build 통과, 대시보드 주간 상위 5개가 전 세계 목록과 일치(월간 1위 AION 2, 연간 1위 Counter-Strike 2) [확인]

**재수정 (사용자 확인: 스크롤 여전히 변동, 최다 플레이 탭 비활성이 고장처럼 보임)**
- 스크롤: 탭 전환 때 목록 내용을 바꿔 끼우는 방식 자체가 원인(브라우저 scroll anchoring이 위치 보정 + 강제 `scrollTo`도 위치 변경). → 탭별 목록을 미리 렌더링하고 `flex`/`hidden`으로 표시만 전환, 목록에 `overflow-anchor: none`, 강제 스크롤 제거(탭별 가로 위치 유지)
- 최다 플레이: 1주만 모인 기간은 비활성 탭 대신 "월간·연간은 데이터 수집 중 (1/4주) — Steam이 과거 기록을 제공하지 않아 매주 쌓는 중" 문구 표시, 2주 이상이면 탭 자동 표시
- FE lint·typecheck·build 통과 [확인], 스크롤 문제 해결 (사용자 확인) [확인]
- 이후 사용자 결정으로 최다 플레이의 월·연 집계 자체를 제거: `PERIOD_SOURCES = (TOP_SELLERS,)`, MOST_PLAYED 보관 14일. API에서 판매 순위만 `periods` 보유 확인, pytest 155 passed [확인]

#### 3b 추가 — 세로 표·추이 그래프 (2026-11-03)

**결정 과정**: 그래프 구현 선택지(직접 SVG / recharts / uPlot) 장단점 제시 → 사용자 "shadcn/ui Charts" 선택 → 실제 설치 내용(recharts 3.10.1 + react-is, clsx, tailwind-merge, 래퍼 소스) 확인 후 설치 방식(수동 / CLI) 재선택 → 수동

**변경**
- 패키지: `recharts@3.10.1`, `react-is@19.3.0`, `clsx@2.1.1`, `tailwind-merge@3.7.0` (운영 의존성 취약점 0). shadcn 레지스트리의 `lucide-react`는 chart.tsx가 쓰지 않아 미설치
- `components/ui/chart.tsx`: 공식 레지스트리(new-york-v4) 소스를 검토 후 복사, `cn` import만 `@/lib/utils`로 교체. `dangerouslySetInnerHTML`은 코드 상수 색만 CSS 변수로 주입(사용자 입력 없음)
- `lib/utils.ts`(`cn`), `globals.css`에 shadcn 최소 토큰(muted·border)과 `--chart-1`(라이트 #2a78d6 / 다크 #3987e5 — dataviz 검증 스크립트 양 모드 PASS)
- 백엔드 `DashboardSection.trend_times` + `DashboardEntry.trend`(값 배열, 시간 축은 섹션에 한 번), `day_peak`(24시간 최고). 판매 순위 12주(합산 순위에도 같은 축), 현재 접속 7일을 3시간 구간별 최신 수집본으로 축약. 필드명 `peak_24h`는 camelCase가 `peak24H`가 되어 `day_peak`로 변경
- 프론트 `components/sparkline.tsx`(단일 계열, 범례 없음, 툴팁, 값 없는 구간은 끊김, 순위는 위가 1위), `dashboard-view.tsx`를 2단 패널·세로 표로 재작성(10개 → 펼치기 20개), 장르 분포를 가로 막대 차트로

**겪은 문제**
- 숨긴 탭 목록 안의 차트가 크기 0으로 그려져 recharts 경고 → 숨긴 탭은 같은 크기의 빈 칸만 두고 보일 때 그래프 렌더(레이아웃 불변이라 스크롤 수정 유지)

**검증**: pytest 158 passed(추이 3개 추가: 12주 순서·값, 3시간 구간·24시간 최고, 추이 없는 섹션), FE lint·typecheck·build 통과 [확인] / 화면은 사용자 확인 대기. 현재 접속 추이는 수집 시작 직후라 점이 2개 미만인 동안 "수집 중" 표시

**사용자 피드백 반영 (메인 정리)**
- 메인의 로그인 버튼·안내 제거(헤더에 있음). 로그인 실패(`/?login=failed`) 알림만 유지
- 2단 그리드 대신 **상단 탭**(판매 순위 / 지금 접속자 / 많이 플레이한 게임 / 할인 / 신작 / 인기 장르)으로 한 번에 한 섹션만 전체 폭 표시. 판매 순위 안의 주간·월간·연간 탭 유지
- 섹션도 미리 렌더링 후 표시만 전환, 숨긴 섹션의 그래프는 그리지 않음(스크롤 보정·크기 0 경고 방지)
- 전체 폭에 맞춰 이미지·추이 그래프 확대
- FE lint·typecheck·build 통과, 개발 서버 새 경고 없음 [확인] / 화면은 사용자 확인 대기

**사용자 피드백 반영 (스크롤바·그래프 끊김·장르 한글)**
- 탭 줄 오른쪽 세로 스크롤바: 가로 스크롤용 `overflow-x-auto`가 세로도 auto가 되는데, 선택 탭 밑줄용 `-mb-px`가 1px 넘쳐 생김 → `overflow-y-hidden`, 구분선을 inset 그림자로, 음수 여백 제거
- 판매 순위 추이 끊김: 그 주 100위 밖(값 없음)이라 선이 끊기고, 앞뒤가 모두 비면 점 하나라 보이지 않음(의도된 처리였으나 읽기 어려움) → 100위 밖은 바닥선(101)으로 이어 그리고 툴팁 "100위 밖". 현재 접속은 빠진 구간을 앞뒤로 연결. 표시 판정(2점 이상)은 실제 값 기준 유지
- 장르 한국어: Steam `l=koreana` 장르명 19개를 실제 수집해 `app/genre_labels.py` 대응표로. 내부 계산(취향·매칭)은 영어 장르명 유지, **응답 직전**에만 한국어로(대시보드는 개인화 계산 후 `_localize`, 라이브러리는 응답 생성 시). 표에 없는 장르는 영어 그대로
- pytest 160 passed(장르 표시 2개 추가, 기존 기대값 한국어로), API 응답 장르·장르 분포 한국어 확인, FE lint·typecheck·build 통과 [확인] / 화면은 사용자 확인 대기

**최종 화면 확인 (2026-11-03)**: 개발 서버(DB·백엔드·프론트) 재기동 후 사용자가 브라우저에서 전체 정상 동작 확인 [확인]. 디자인 다듬기는 이후로 미룸

**탭 전환 시 좌우 흔들림 수정**: ① 탭마다 페이지 높이가 달라 세로 스크롤바가 생겼다 사라지며 폭 변화 → 처음엔 `scrollbar-gutter: stable`로 고쳤으나 짧은 페이지에도 빈 스크롤바 자리가 남아(사용자 지적) `body { width: 100vw }` + `html { overflow-x: hidden }`로 변경(스크롤바가 내용 오른쪽 끝 위에 겹침) ② 선택 탭만 `font-medium`이라 탭 폭 변화 → 모든 탭 같은 굵기, 선택은 색·밑줄로만. FE lint·typecheck 통과 [확인] / 화면은 사용자 확인 대기

**탭·섹션 이름 개조식 통일**: 판매 순위 / 실시간 접속 순위(현재 동시 접속) / 주간 접속 순위(주간 최고 동시 접속, 기존 "많이 플레이한 게임") / 할인 게임 / 신작 게임 / 장르 순위. 섹션 제목·장르 기준 문구도 같은 이름으로. FE lint·typecheck 통과 [확인]

### 4단계 — 라이브러리 분석 + 보유 게임 추천 (2026-11-03)

**결정 (사용자 선택, PRD v6.2로 점수 설계 F3 확정)**
| 항목 | 결정 |
|---|---|
| 후보 | 플레이 120분 미만, 게임으로 확인됐거나 종류 미확인(DLC·데모 등 제외), 클라이언트 제외 목록 제외 |
| GENRE_AWARE | `0.6·genreMatch + 0.3·unplayed + 0.1·recentGenre` (미플레이 우선: 0.45 / 0.5 / 0.05) |
| PLAYTIME_BASED (장르 수집 중 임시 추천 "이어서 하기") | 후보에서 **미플레이(0분) 제외**(사용자 결정: 미플레이끼리 순서 근거 없음), `0.7·unplayed + 0.3·recentlyPlayed(90일 안 실행)`, 미플레이 우선 옵션 미적용(화면 토글 비활성), 이유에 `LOW_GENRE_COVERAGE`(기여 0) |
| 요소 값 | unplayed = 1 − 분/120, genreMatch·recentGenre = 취향 가중치 합(전체 / 최근 2주 플레이) |
| 장르 분포 | 취향 가중치(장르별 Σ log1p(분), 합 1) — 추천 genreMatch와 같은 값 |
| 모드 임계값 | coverage.ratio ≥ 0.9 → GENRE_AWARE (설정 `recommendation_genre_threshold`) |
- "최근 구매" 요소는 불가로 판단: Steam이 구매일을 주지 않고, 미플레이 게임은 `rtime_last_played = 0`이라 구분 안 됨 → "최근 실행"으로 대체
- 후보 0개는 오류(INSUFFICIENT_DATA) 대신 200 + 빈 목록 + `candidateCount: 0`(화면에서 후보 조건 안내)
- 화면 구성(사용자 결정): 보유 게임 추천(F3)과 미보유 추천(F4ⓒ)을 "내 취향 추천" 한 영역의 "가진 게임 중 / 살 만한 게임" 탭으로 합침. API·점수는 분리. 탭 구조는 5단계에서 두 번째 탭과 함께 적용(탭 하나짜리 UI는 만들지 않음). → PRD v6.2 반영
- 미보유 추천을 정가 게임까지 확대(할인 중만 보기 필터) → PRD v6.2 반영, 가중치·응답 형식·가격 수집 비용은 5단계 착수 시 확정

**변경**
- `app/recommend.py`: 순수 함수 `recommend()`(점수·이유·정렬, `now`·장르 표시 함수 주입), `choose_mode()`, `fetch_recommendations()`. `contribution` 합 = `score`, 동점 appid 오름차순
- `GET /me/recommendations?preferUnplayed=&exclude=`(반복 파라미터, 양수·최대 1000개 검증) → `recommendations`, `candidateCount`, `excludedCount`, `recommendationMode`, `metadataCoverage`, `metadataSnapshotAt`, `calculatedAt`
- `app/library.py`: `load_owned_games()`(비공개 판별 공용화), 응답에 `genreDistribution`
- 프론트: `/me`에 추천 카드 3개(이미지·점수·요소별 기여·추천에서 빼기), 미플레이 우선 토글, 제외 목록(Zustand persist, 모두 되돌리기), 장르 취향 가로 막대, coverage 문구. 라이브러리·추천 모두 `pending > 0`이면 5초 폴링(최대 60회)

**겪은 문제**
- uvicorn `--reload`가 파일 변경 감지 후 재시작하지 못하고 멈춤(이전 프로세스가 계속 응답) → 서버 재기동으로 해결. 원인 미확인(Windows에서 열린 연결 종료 대기 추정)

**검증**: pytest 181 passed(추천 순수 함수 10개: 점수·이유 정확값, 미플레이 우선, 최근 장르, 동점, 제외·미확인 메타데이터, PLAYTIME_BASED, 입력 순서 무관 재현성, 후보 없음, 임계값 경계 / API 7개: 로그인, 정상 응답, 제외·저수집률, 잘못된 입력 422, 제외 목록 상한, 비공개, Steam 429), ruff·FE lint·typecheck·build 통과 [확인] / 실계정 화면 사용자 확인 [확인]

---

## 미확인·추정 사항 (구현 시 검증)

| 항목 | 확인 시점 |
|---|---|
| ~~비공개 계정 GetOwnedGames가 오류 대신 빈 `response` 반환~~ | ✅ 2단계 스파이크로 확인 |
| `communityvisibilitystate` 1 = 프로필 비공개 (공개 = 3은 확인) | 2단계 |
| 게임 0개 계정의 GetOwnedGames 응답 형태(`game_count: 0` 여부) | 2단계 |
| 로그인해도 비공개 라이브러리 조회 불가 (서버는 API 키로 조회하므로 로그인 여부와 무관 — 구조상 성립) | 2단계, 실계정 비공개 전환 테스트는 생략 |
| store appdetails 레이트리밋(약 200회/5분) — 0.6회/초로 58건 무오류, 한도 자체는 미확인 | 운영 관찰 |
| 상점이 과다 요청 시 403을 주는지 | 운영 관찰 |
| `success:false` 3건(378120, 482750, 623990)이 1시간 뒤 재확인에서 NOT_AVAILABLE로 확정되는지 | 3b 작업 중 확인 |
| featuredcategories 스키마, GetMostPlayedGames 공개 접근 | 3b단계 스파이크 |
| appdetails `filters=price_overview` 다중 appid 지원 | 5단계 |
| IWishlistService/GetWishlist 공개 접근·응답 형식 (비문서화) | 5단계 |
| GetOwnedGames로 DLC 보유 여부 판별 불가 | 5단계 |
| 비문서화 엔드포인트·차트 데이터 공개 서비스 이용 약관 | 출시 전 |

---

## 로컬 개발 메모

- DB: `docker compose up -d db` (호스트 5433), 테스트 DB `steammate_test`는 컨테이너 안에 수동 생성
- 마이그레이션: `cd backend && alembic upgrade head` (서버 실행 전 필요), 모델 변경 후 `alembic revision --autogenerate -m "..."` → 생성 파일 검토(enum 정리 등) → `alembic check`
- DB 테스트 실행: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://steammate:steammate@localhost:5433/steammate_test pytest`
- 백엔드: `cd backend && source .venv/Scripts/activate && uvicorn app.main:app --reload` (`backend/.env`에 `SESSION_SECRET` 필요)
- 프론트: `cd frontend && npm run dev` (`/api/*`는 `BACKEND_URL`로 프록시)
- push는 사용자가 직접 (`git push origin main`), CI 결과는 GitHub Actions에서 확인
