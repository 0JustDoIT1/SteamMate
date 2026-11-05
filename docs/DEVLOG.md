# SteamMate 개발 로그

> 진행 상황·결정·변경 내역·검증 결과를 기록한다. 설계 기준은 [PRD.md](PRD.md)이며, 이 문서는 "언제 무엇을 했고 왜 그렇게 결정했는가"를 남긴다.
> 표기: **[확인]** 실행·조회로 검증 / **[추정]** 외부 문서·추론 기반, 구현 시 검증 필요

---

## 현재 상태 (2026-11-06 기준)

| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | PRD v6 반영, Claude Code 가드레일 | ✅ 완료 |
| 1 | 실행 환경 정비, 테스트 기반, CI, 프론트 Provider·프록시 | ✅ 완료 (CI 통과) |
| 2 | Steam 로그인 + `/me/library` 기본 조회 | ✅ 완료 (실계정 로그인·로그아웃 확인) |
| 3a | 메타데이터 캐시(game_metadata, 레이트리미터) | ✅ 완료 |
| 3b | 소스 스파이크 → 인기 대시보드 | ✅ 완료 (브라우저 확인, 커밋) |
| 4 | 라이브러리 분석 + 보유 게임 추천·이유 | ✅ 완료 (화면 확인) |
| 5 | 가격·할인(위시리스트·DLC·미보유 추천) | ✅ 완료 (화면 확인) |
| 6 | 뉴스 조회·정제 (R1 완료) | ✅ 완료 (화면 확인) — R1 완료 |
| 7 | Full Context vs RAG 실험 | ✅ 완료 — 임계값 8k(PRD v6.6) |
| 8 | 뉴스 AI 질문 (R2 완료) | ✅ 답변 틀 v7(PRD v6.9) — 값 질문 서버 계산, 실제 공지·재실험 확인 |
| 9 | E2E·배포 | ✅ 로컬 Docker 운영 구성, E2E 10개 통과(개발·운영), API 제한 점검(빠진 3개 기록) |

> 11-03 PRD v6.1로 단계 재배치(로그인 → 대시보드 → 기능). 이전 계획의 "입력 파서" 단계는 삭제.

**다음 세션에서 이어서 할 일** (9단계 이후, 모든 단계 완료)
1. 공개 배포를 하게 되면: 출시 게이트(뉴스 권리·비문서화 store 엔드포인트 약관 검토), 빠진 API 제한 3개(9단계 기록), 개발과 다른 비밀값
2. 남은 한계 검토(선택): 본문이 링크뿐인 공지(Blue Archive), RAG에 안 걸린 공지의 값 기록, Full Context num_ctx 변동에 따른 모델 재로딩(미측정)
3. 미검증: 실제 Steam 로그인 화면을 거친 운영 모드 콜백(쿠키 Secure), E2E의 CI 실행(로컬 전용 결정)
- 운영 구성: `docker compose -f compose.prod.yml up --build -d` → http://localhost:8080 / E2E: `cd frontend && E2E_STEAMID=<17자리> npm run e2e` (운영 구성은 `E2E_BASE_URL=http://localhost:8080`)
- 실행 전 확인: Ollama 서버(`http://127.0.0.1:11434`), 모델 `bonsai-2:9b`·`qwen3:4b`·`bge-m3`(D:\ollama\models)

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
| 11-04 | 7단계 KV 캐시 f16 기본 유지 | 정확도 차이 원인 분리, 주 모델은 q8_0 이득 없음 |
| 11-04 | 실험 코퍼스 중첩형(2k⊂8k⊂32k⊂100k) | 같은 36문제로 길이만 변수 |
| 11-04 | qwen3:4b 비교 불가로 기록, 결론은 bonsai-2:9b로만 (PRD v6.6) | Thinking 모델이 출력 한도에서 답을 못 냄 |
| 11-04 | **F6 모드 임계값: 약 8k 토큰 이하 Full Context, 초과 RAG** (PRD v6.6) | 8k까지 정확도 동일·색인 불필요, 32k부터 A 급락. "항상 RAG"도 검토했으나 요약형 질문(미측정)은 Full Context가 유리해 유지 |
| 11-04 | 서비스 LLM = 로컬 Ollama bonsai-2:9b(+bge-m3), 배포 환경은 기능 OFF (PRD v6.7) | 임계값을 잰 모델 그대로, 무료·본문 외부 전송 없음. Ollama는 배포 대상 아님 |
| 11-04 | 질문 대상 = 공식 공지 최근 50건 또는 날짜 범위, 모드는 글자 수 어림(3자=1토큰) | 정확한 토큰 수는 LLM 호출이 필요 |
| 11-05 | 질문 유형별 답변 틀(업데이트 요약·값·일정·기타, JSON 칸), 최신 공지 고정은 요약에만 (PRD v6.7 갱신) | 사용자 제안: 게임 공지 질문은 유형이 정해져 있음. 나열·뭉뚱그림을 칸 개수로 막고 v4 부작용(Q13) 해소 |
| 11-05 | 뉴스 질문 기간 설정 제거, "최신 업데이트" = 제목에 버전·패치가 든 가장 최근 공지를 항상 함께 입력, 지시문 v4 (PRD v6.7 갱신) | 의미 검색은 날짜를 못 봐 "최신" 질문에 옛 공지가 걸림. 사용자 결정 |
| 11-04 | 오류 코드 `AI_UNAVAILABLE`(503), 뉴스 목록 `askEnabled` 추가 (PRD v6.7) | LLM 장애를 공통 형식으로, 프론트가 기능 여부를 미리 앎 |
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
- uvicorn `--reload`가 파일 변경 감지 후 재시작하지 못하고 멈춤(이전 프로세스가 계속 응답) → 서버 재기동으로 해결. 원인은 아래 "개발 서버 자동 재시작 멈춤 조사" 참조(콘솔 없는 실행 환경)

**검증**: pytest 181 passed(추천 순수 함수 10개: 점수·이유 정확값, 미플레이 우선, 최근 장르, 동점, 제외·미확인 메타데이터, PLAYTIME_BASED, 입력 순서 무관 재현성, 후보 없음, 임계값 경계 / API 7개: 로그인, 정상 응답, 제외·저수집률, 잘못된 입력 422, 제외 목록 상한, 비공개, Steam 429), ruff·FE lint·typecheck·build 통과 [확인] / 실계정 화면 사용자 확인 [확인]

### 5단계 — 가격·할인·살 만한 게임 (2026-11-03)

**스파이크** [확인]
| 확인 | 결과 |
|---|---|
| appdetails `filters=price_overview` 다중 appid | 50·100·200개 정상, 400개 HTTP 500 → 100개씩 묶음. 무료·미출시는 `data: []`, 없는 앱은 `success:false` |
| 다중 appid + 다른 filters(basic·name·dlc) | 모두 HTTP 400 → DLC 이름은 할인 중인 것만 개별 조회 |
| GetWishlist(사용자 본인 계정, 동의 후) | 키 없이 53개 조회, 비공개 전환 시 `{"response":{}}`, 개수 API도 동일 |
| 저장된 DLC 목록 | 장르 받은 게임 175개에 DLC 1,878개(게임당 최대 201) |
| 후보 풀 | 최신 목록 193개 → +최근 4주 판매 순위 227개(보유 제외 160) |

**결정 (사용자 선택, PRD v6.3 반영)**
| 항목 | 결정 |
|---|---|
| API | `/me/store-recommendations?onSaleOnly=` 분리, `/me/deals`는 위시리스트·DLC만 |
| 살 만한 게임 점수 | `0.7·genreMatch + 0.3·popularity`(1/최고 순위). 할인은 점수 미반영 — 동점 정렬·표시·필터에만 |
| 장르 수집 중(PLAYTIME_BASED) | 인기만으로, 이유에 안내(보유 게임 추천과 같은 모드 판정) |
| 후보 | 소스별 최신 목록 + 최근 4주 판매 순위, 게임으로 확인되고 장르 있는 것만 |
| DLC 범위 | 2시간 이상 플레이한 보유 게임의 DLC(처음 3시간으로 구현 → 사용자 요청으로 2시간), 본 게임당 최대 3개·전체 30개(실데이터에서 한 게임 DLC가 30개를 채워 추가) |

**변경**
- 마이그레이션 `d4e080ca6206`: `game_price((appid, cc) PK, …)` — 기존 `fetch_status` 타입 재사용(`create_type=False`)
- `StoreApi.prices()`: 묶음 가격 조회, 요청 실패는 묶음 전체 같은 결과
- `app/prices.py` `PriceService`: 요청 안에서 100개씩 받고 `max_batches`(기본 3)로 제한, 나머지 PENDING → 폴링이 이어 받음. 진행 중 appid 중복 조회 방지, 429면 남은 묶음 중단·일시정지. 일시 실패는 NOT_AVAILABLE이 되지 않고 기존 가격 유지. TTL 1시간
- 메타데이터·가격이 상점 레이트리미터 하나를 공유(`build_store_limiter`)
- 수집 작업: 차트 수집 후 후보 풀 가격을 미리 받음(제한 없음, 만료분만)
- `chart_queries.candidate_pool()`: 최신 + 최근 4주 판매 순위, appid별 최고 순위(동순위는 판매 순위 먼저)
- `SteamWebApi.get_wishlist()`: **API 키 없이** 호출(키 소유 계정의 비공개 우회 방지), 실패해도 추천·할인은 계속(`wishlistChecked`/`UNAVAILABLE`)
- `app/store_recs.py`(순수 함수 `recommend_store`), `app/deals.py`(`dlc_sources`, `rank_deals`), `MetadataSnapshot.dlc_appids`
- 프론트: "내 취향 추천" 탭(가진 게임 중 / 살 만한 게임 — 살 만한 게임은 처음 열 때 조회), 할인 중만 보기, 할인 영역(위시리스트·DLC, 비공개 안내, DLC 보유 미확인 안내), 가격·장르 수집 중 폴링

**겪은 문제**
- 가격 테스트 60초: 429 경우 레이트리미터가 실제로 60초 일시정지 → 테스트에서 일시정지 0.01초
- 후보 풀 동순위 정렬이 "소스 이름 순"이라는 가정이 틀림(PostgreSQL enum은 정의 순) → 주석·테스트 수정
- uvicorn `--reload` 멈춤 재현(2회째) → 아래 "개발 서버 자동 재시작 멈춤 조사"에서 원인 확인·조치

**검증**: pytest 210 passed(가격 캐시 8 · 살 만한 게임 13 · 할인 7 · 수집 작업 가격 선수집 1 추가), migration up/down·`alembic check`, ruff, FE lint·typecheck·build 통과 [확인]. 실데이터(사용자 계정, 동의 후 로컬 세션 발급): 후보 160 중 추천 10, 할인 중만 41, 위시리스트 할인 9/53, DLC 확인 440개 [확인] / 화면은 사용자 확인 대기

**문구 수정 (사용자 피드백)**: 탭 "가진 게임 중 / 살 만한 게임" → "보유 게임 / 구매 추천", 체크박스는 재피드백("미플레이 / 할인 중"으로 짧게, 켜짐·꺼짐 구분이 잘 보이게)에 따라 토글 칩(`components/toggle-chip.tsx`, 켜짐 = 채운 배경 + ✓, 꺼짐 = 테두리 + "+", 뜻은 마우스 설명)으로 교체. PRD 화면 구성 문구도 새 탭 이름으로. FE lint·typecheck 통과 [확인]

**미플레이 옵션 변경 (사용자 피드백)**: "켜도 꺼도 미플레이 게임이 이미 점수에 들어가 있어 무엇이 바뀌는지 모르겠다" → 가중치 상향(0.45/0.5/0.05)을 없애고 **포함/제외**로 변경. `preferUnplayed`(기본 false) → `includeUnplayed`(기본 true), 끄면 미플레이 게임을 후보에서 빼 "조금 해 본 게임"만 추천. 가중치는 항상 0.6/0.3/0.1. PRD v6.3 반영. pytest 211 passed, FE lint·typecheck 통과 [확인]

**`/me` 탭 구성·이미지 (사용자 피드백)**
- 대시보드처럼 상단 탭(보유 게임 추천 / 구매 추천 / 할인 / 장르 취향 / 보유 게임 목록 N)으로 한 섹션씩. 탭 막대는 `components/page-tabs.tsx`로 분리(대시보드는 기존 코드 유지). 구매 추천·할인은 처음 열 때 조회, 장르 차트는 보일 때만 그림(크기 0 경고 방지). 기존 "내 취향 추천" 안쪽 탭은 없앰
- 보유 게임 목록 이미지 깨짐: 실계정 58개 중 3개(HELLDIVERS 2·Aimlabs·Battlefield 6) 아이콘 주소 404 [확인] → 라이브러리 응답에 상점 대표 이미지(`headerImage`, 메타데이터) 추가, `GameImage`가 대표 이미지 → 아이콘 → 대체 칸 순으로 시도
- PRD `/me` 화면 구성 문구 갱신. pytest 211 passed, FE lint·typecheck·build 통과 [확인] / 화면은 사용자 확인 대기

**미플레이 옵션 삭제 (사용자 결정)**: 포함/제외 칩도 불필요하다는 판단 → 칩·`includeUnplayed` API 옵션·응답 필드·브라우저 설정값 삭제. 미플레이 게임은 항상 후보(장르 수집 중만 제외). PRD F3 표·API 표·점수 설계 갱신. pytest 207 passed(옵션 관련 4개 삭제), FE lint·typecheck·build 통과 [확인]


### 개발 서버 자동 재시작 멈춤 조사 (2026-11-03)

**증상**: `uvicorn --reload`가 파일 변경 후 "Reloading..."에서 멈추고 옛 프로세스가 계속 응답(4·5단계 중 4회, 매번 수동 재기동)

**원인** [확인]: uvicorn 0.54의 Windows 재시작은 워커에 `os.kill(pid, CTRL_C_EVENT)` 후 `join()`으로 대기. CTRL_C_EVENT는 **콘솔에 붙은 프로세스에만** 전달되는데, Claude가 서버를 콘솔 없는 백그라운드 셸에서 띄워 신호가 닿지 않음. 로그의 "Reloading..." 다음 줄이 공백으로 시작하는 것도 uvicorn의 `sys.stdout.write(" ")` 우회 코드 흔적
| 실험(최소 FastAPI 앱, 앱 코드 무관) | 결과 |
|---|---|
| 백그라운드 Bash(콘솔 없음) | 멈춤 — 재현 |
| PowerShell `Start-Process` 최소화 창(콘솔 있음) | 정상 재시작 |
| `Start-Process -WindowStyle Hidden -RedirectStandardOutput` | 멈춤 |
| `cmd.exe /c "... > log 2>&1"`를 최소화 창으로 | 정상 재시작 + 로그 파일 확보 |

**조치**: 앱 코드 변경 없음. 마지막 방식으로 실제 앱 재시작 1회 성공 [확인] → **6단계 중 같은 방식에서 다시 멈춤**("Reloading..." 뒤 "Shutting down" 없음 = 신호 미수신) [확인]. 콘솔이 있어도 간헐적이라 결론 수정: Claude가 띄우는 서버는 `--reload`를 끄고 백엔드 코드 변경 후 직접 재시작(`PYTHONUNBUFFERED=1`로 로그 버퍼링도 끔). 사용자가 직접 터미널에서 실행하는 경우는 미확인(키보드가 붙은 콘솔이라 다를 수 있음). 실행 방법은 Claude 메모리에 기록


### 6단계 — 게임 공식 뉴스 (2026-11-03)

**스파이크** [확인] — ISteamNews/GetNewsForApp v2 (키 불필요)
| 확인 | 결과 |
|---|---|
| 기본 응답 | 공식 공지 + 외부 언론 피드(PlayGround.ru·PCGamesN 등, 러시아어 다수) 섞임 |
| `feeds=steam_community_announcements` | 공식 공지만(7개 게임 확인) |
| `url` 필드 | `steamstore-a.akamaihd.net/news/externalpost/...` 중간 주소(커뮤니티로 리다이렉트) → `store.steampowered.com/news/app/{appid}/view/{gid}` 직접 구성(200) |
| 본문 형식 | 공식은 BBCode(`[p] [*] [b] [img] [url] [list] [h1~3] [previewyoutube] [dynamiclink]`, `{STEAM_CLAN_IMAGE}`), 외부는 HTML. 길이 200~42,000자 |
| `maxlength` | Steam이 서식을 지우며 문단을 붙여 버림("talk.Join") → 쓰지 않고 전문을 받아 직접 정리 |
| 없는 appid | HTTP 403 + `{}` |

**결정 (사용자 선택)**: 본문은 **제목 + 발췌(200자) + 원문 링크**만(PRD 권리 제약), 진입점은 보유 게임 목록의 "뉴스" 버튼

**변경**
- `app/news_cleaner.py`(순수 함수): BBCode/HTML → 평문. 이미지·영상·자리표시자 제거, 링크는 글자만, 목록 "• ", `\[` 이스케이프 보존, 잘린 태그·보이지 않는 문자(`​` 등) 처리. `excerpt()`는 단어 경계에서 자르고 "…"
- `app/news.py` `NewsService`: 공식 피드만, count+1로 다음 페이지 여부, `enddate`로 이전 글(`nextBefore` = 마지막 글 시각 − 1초), 비정상 gid 건너뜀, 403→`NOT_FOUND`·429·5xx·스키마·타임아웃 매핑. **발췌만** 메모리 TTL 캐시(10분), 본문 전문은 캐시·응답·로그에 남기지 않음. 게임 이름·대표 이미지는 메타데이터 캐시에서
- `GET /steam/news/{appid}?count=1~20&before=` (로그인 불필요)
- 프론트 `/news/[appid]`: 대표 이미지·이름, 공지 목록(제목→원문, 날짜·작성자, 발췌, "Steam에서 전문 보기"), "이전 공지 더 보기"(useInfiniteQuery). 보유 게임 목록 행에 "뉴스" 버튼

**겪은 문제**
- `cacheComponents` 설정에서 동적 경로 파라미터를 Suspense 밖에서 읽어 빌드 실패 → 파라미터 읽는 부분만 Suspense 안 컴포넌트로
- 정리 결과 실데이터 70건 점검에서 `[ GAMEPLAY ]`(CS2 이스케이프), `[*][p]…[/p][/*]` 목록 형식, 폭 없는 공백 발견 → 각각 처리·테스트 추가
- 개발 서버 자동 재시작 재발(위 조사 결론 수정)

**검증**: pytest 229 passed(정리 9 · 뉴스 API 13 추가), ruff, FE lint·typecheck·build 통과, 실데이터 공식 공지 70건 정리 시 남은 마크업 0(의도된 `[PC]` 등 글자 괄호 제외)·빈 결과 0, `/steam/news/105600` 실응답(Terraria, 다음 페이지 기준 시각) [확인] / 화면은 사용자 확인 대기. 잘못된 주소(`/news/abc`)는 스트리밍 때문에 HTTP 200 + 404 화면(소프트 404)

**사용자 피드백: "Read the full announcement here!" 반복** — PUBG 공식 공지 10개 중 5개가 이미지 + 자사 사이트 링크 한 줄뿐인 형식 [확인] → 정리 결과가 링크 글자만 남아 발췌가 매번 같았음. `link_only_target()`로 "링크 외 본문이 없는 공지"를 판별해 발췌 대신 `externalUrl`을 주고, 화면은 "전문은 pubg.com에서 보기 ↗". 실데이터에서 PUBG 공지 4건 모두 각자 다른 pubg.com 주소 확인. 표시 범위는 사용자 결정으로 발췌 유지(전문 표시 보류)

**뉴스 행 디자인 (사용자 피드백)**: 아래쪽 "전문 보기" 링크를 행 오른쪽 버튼(`Steam ↗` / `pubg.com ↗`)으로 이동, 제목도 같은 곳으로 연결, 발췌는 3줄까지(`line-clamp-3`), 링크만 있는 공지는 "본문은 pubg.com에 있습니다". FE lint·typecheck 통과 [확인]

**결정**: 디자인은 기능을 마친 뒤 레퍼런스를 참고해 전체를 한 번에 정리한다(사용자 결정). PRD v6.4로 뉴스 R1 반영. 뉴스 번역은 LLM 번역으로 보류(아래 참조)


### 6단계 추가 — 뉴스 한국어 번역 (2026-11-03, 보류)

브라우저 내장 번역(Chrome Translator API, 데스크톱 Chrome 138+)으로 제목·발췌 번역을 구현했으나 **사용자 결정으로 제외**(커밋하지 않고 되돌림). 번역은 나중에 서버 LLM 번역으로 다시 검토 — LLM 제공자를 정하는 7단계 이후, 뉴스 본문 AI 처리 권리(PRD 미확인)와 함께 판단. 참고: 내장 번역은 모바일·Firefox·Safari 미지원, 첫 사용 시 모델 다운로드 필요


### 7단계 준비 — LLM·임베딩 결정과 사전 측정 (2026-11-03)

**결정 과정**: Claude API(Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per 1M 토큰 — 실험 1회 추정 $3~80) 비교 제시 → 사용자 "무료 LLM" 요청 → 로컬(Ollama) / 무료 API 등급 / Haiku 비교 → **로컬 Ollama 선택**(무료·재현 가능·데이터 외부 전송 없음). 확인 사항: Claude API는 임베딩 미제공, 최신 Claude 모델·API 버전은 `temperature`를 400으로 거부(→ 로컬 모델은 temperature 0 + seed 가능하므로 PRD "같은 온도" 유지)

**설치** [확인]: `winget install Ollama.Ollama`(0.40.14, MIT), 설치 폴더 3.2GB(CUDA 라이브러리 포함, 예상 1~2GB보다 큼), 모델 저장 `OLLAMA_MODELS=D:\ollama\models`(사용자 환경 변수). 트레이 앱이 설치 직후 서버를 띄우지 않아 `ollama serve`를 최소화 cmd 창으로 실행. GPU 인식: RTX 3080 12GB(CUDA). 모델: `qwen3:4b` 2.5GB, `bonsai-2:9b` 3.2GB, `bge-m3` 1.2GB

**사전 측정** [확인] — 고정 seed 가상 패치노트에 사실 하나를 앞/중간/끝에 숨기고 한국어로 질문(스크립트는 scratchpad, 실험 본체 아님)
| 입력 | qwen3:4b | bonsai-2:9b |
|---|---|---|
| 2k | 3/3, ~3초, 3.2GB GPU | 3/3, ~1초, 2.8GB GPU |
| 8k | 3/3, 5~11초, 4.2GB GPU | 3/3, ~2초, 3.1GB GPU |
| 32k | 3/3, 11~16초, 8.0GB GPU | 3/3, 9~12초, 4.2GB GPU |
| 100k | 3/3, 질문당 ~5분, 18GB → CPU 44%/GPU 56% | 3/3, 질문당 ~36초, 6.8GB, 100% GPU |
- 같은 글도 토크나이저에 따라 토큰 수가 다름(100k 목표 글: qwen3 101,526 / bonsai-2 107,416)
- **측정 실수**: 처음엔 `num_ctx = 목표+2048`로 잡아 bonsai-2 입력이 넘침 → Ollama가 **뒤쪽 절반만 남기고 앞을 잘라**(로그 "truncating input prompt") 앞·중간 사실을 못 찾음. `num_ctx = 목표×1.2+2048`로 고쳐 재측정. 실험 본체에서도 응답의 `prompt_eval_count`로 잘림 여부를 반드시 검사할 것
- qwen3:4b는 `think: false`여도 답 앞에 추론 문장이 섞임 → 정답 판정은 마지막 숫자 기준으로 강화
- 첫 요청은 모델 로딩 포함 약 70초. 같은 글로 연속 질문하면 앞부분 캐시 재사용으로 입력 처리가 거의 0초인 경우 관측(실험에서 첫 요청·재사용을 구분해 기록해야 함)
- 한계: 사실 하나 찾기라 쉬운 문제. 여러 문서 근거·버전 충돌 질문, `bge-m3` 검색 정확도는 실험 본체에서 측정

**결정 (사용자 승인, PRD v6.5)**: 주 모델 `bonsai-2:9b`(2k~100k), 비교군 `qwen3:4b`(2k~32k), 임베딩 `bge-m3`, Ollama REST를 기존 `httpx`로 호출(새 SDK 없음), 100k 정식 실험 축 포함

**추가 확인 (2026-11-04)**
- `numpy` 2.5.4 설치(사용자 재확인, 직접 구현과 비교 후 선택), `requirements.txt`에 고정
- **flash attention은 이미 켜져 있었음** [확인]: Ollama 0.40 기본값 `--flash-attn auto` → 두 모델 모든 길이에서 "Flash Attention enabled". 따라서 성능 옵션의 실제 변수는 KV 캐시 정밀도(f16 기본 / q8_0)뿐
- 설치된 `qwen3:4b`는 "Qwen3 4B **Thinking** 2507" — `think: false`에도 추론 문장이 섞이는 원인으로 추정
- 서버는 트레이 앱(`ollama app.exe`)이 관리하며 서버 프로세스를 종료하면 즉시 다시 띄움. 환경 변수를 바꿔 측정하려면 트레이 앱을 끄고 직접 `ollama serve` 실행 → 측정 후 트레이 앱 재실행으로 복구함
- KV 캐시 q8_0 비교 [확인] (같은 스크립트·seed, f16 값은 11-03 측정, 정답은 모두 3/3)
| 모델·입력 | f16 메모리·처리 | q8_0 메모리·처리 | 질문당 시간 f16 → q8_0 |
|---|---|---|---|
| bonsai-2:9b 32k | 4.2GB, 100% GPU | 3.7GB, 100% GPU | 9~12초 → 9~12초 |
| bonsai-2:9b 100k | 6.8GB, 100% GPU | 5.4GB, 100% GPU | 35~37초 → 37~41초 |
| qwen3:4b 32k | 8.0GB, 100% GPU | 6.1GB, 100% GPU | 11~16초 → 9~13초 |
| qwen3:4b 100k | 18GB, CPU 44% | 13GB, CPU 23% | 272~347초 → 138~166초 |
- 해석: 주 모델은 이미 GPU에 다 들어가 q8_0의 속도 이득이 없음(입력 처리 속도 약 7% 감소). qwen3:4b 100k는 시간이 절반이 되지만 여전히 CPU로 넘침. 숨긴 사실 찾기는 쉬운 문제라 정확도 차이는 이 측정으로 판단 불가
- **결정 (사용자 승인)**: 본 실험은 KV 캐시 **f16 기본값 유지**, qwen3:4b는 계획대로 2k~32k. 이유: 정확도 차이의 원인(입력 길이 vs 캐시 압축)을 분리하기 위해 변수 1개 유지, 주 모델은 q8_0 이득 없음. q8_0은 8단계 서비스에서 GPU 메모리를 아껴야 할 때 재검토

### 7단계 — 합성 평가 데이터 생성기 (2026-11-04)

**결정 (사용자 선택)**: 코퍼스는 **중첩형** — 정답 근거가 든 핵심 문서 5건(C1~C5)을 모든 길이에 넣고, 길이가 커질수록 같은 순서로 방해 문서를 앞에서부터 더함(2k ⊂ 8k ⊂ 32k ⊂ 100k). 모든 길이에서 같은 36문제를 풀어 변수를 입력 길이 하나로 둠

**변경**
- `backend/experiments/rag_eval/dataset.py`: 가상 게임 "Ashen Frontier". 핵심 사실은 `CHANGES` 표에 손으로 고정, 방해 문서는 seed `20261104`로 생성. 원문은 BBCode/HTML/평문, 영어·한국어 혼합이며 서비스의 `clean_news`로 정제한 결과를 입력으로 씀. 문서 ID는 날짜순 N001…(핵심 여부 비노출). 방해 문서는 핵심 대상 이름·버전을 쓰지 않고 비슷한 이름(Phantom Lance, Glass Delta 등)만 사용 → 길이와 무관하게 정답 고정. 방해 문서 버전은 다음 핵심 버전을 넘지 않고 끝자리 ≤9(`2.4.10`이 `2.4.1`을 포함하지 않게)
- 질문 36개(한국어): 단일 사실 12 / 최신 값(버전 충돌) 8 / 여러 문서 근거 8 / 비슷한 제목 구분(2.3.0 Notes vs Hotfix) 4 / 답 없음 4. 정답은 항목별 허용 표기 묶음 + 근거 문서 ID
- `build.py`: Ollama `num_predict=1` 호출의 `prompt_eval_count − 빈 메시지 템플릿(12)`으로 토큰 수 측정(Ollama에 토큰만 세는 API 없음, `/api/tokenize` 404). 반복 호출해도 값 동일 확인. `num_ctx` 131,072로 고정해 모델 재로딩 방지, 한도 근접 시 오류
- `data/dataset.json`(427KB) 커밋 대상: 100k 코퍼스에 쓰인 문서·질문·구간별 문서 ID와 토큰 수
- `numpy==2.5.4` requirements 추가

**결과** [확인] (bonsai-2:9b 토크나이저)
| 구간 | 토큰 | 문서 수 | 한국어 문서 |
|---|---|---|---|
| 2k | 2,156 | 7 | 2 |
| 8k | 8,692 | 12 | 3 |
| 32k | 32,682 | 40 | 5 |
| 100k | 99,255 | 110 | 13 |
- 앞에서부터 문서 단위로 더해 목표와 차이가 남(최대 +8.7%). 100k는 110건으로 PRD 예시(60~100건)보다 조금 많음 — 건수는 보조 통계
- 테스트 15개(`tests/test_rag_eval_dataset.py`): seed 재현, 정답이 근거 문서에 있음, 최신 값·변경 버전 목록·계산 답을 `CHANGES`로 재계산, 방해 문서에 핵심 이름·버전 없음, 답 없음 대상이 어디에도 없음, 버전 단조 증가, 정제 후 태그 없음, 중첩·목표 근접, 고정본 = 생성기 결과
- 한계: 방해 문서가 핵심 이름을 전혀 쓰지 않아 키워드 검색으로는 비교적 쉬움(비슷한 이름으로 일부 보완). 답 없음 질문 Q34("2.4.0에서 Void Pistol 탄창")는 "변경 없음"도 맞는 답이라 채점 시 거절·변경 없음을 모두 인정해야 함

### 7단계 — A·B 실행기와 실험 결과 (2026-11-04)

**구현** (`backend/experiments/rag_eval/`)
- `run.py`: A = 지시문 → 코퍼스 전체 → 질문(같은 구간 다음 질문은 앞부분 캐시 재사용). B = 문단 단위 약 1,200자 청크(머리줄 `[ID] 제목 (날짜)`) → `bge-m3` 임베딩 → `numpy` 코사인 Top-5. 공통: temperature 0, seed 1, 출력 한도 1024, 출력 형식 "답: / 근거:". 결과는 질문 단위 JSONL에 추가, 재실행 시 이어서 진행, 입력 잘림 감지 시 기록 없이 중단. `--cold-only N`(첫 요청만 측정), `--index-only`(색인 시간만 측정)
- `grading.py`: "답:" 줄만 채점, 숫자는 경계 검사("50"≠"150"), 글자는 공백 무시, 거절 표현 여러 개 인정, Thinking 모델의 `</think>` 앞부분 제거. `retrieval.py`: 청킹·벡터 색인·Recall@K. `report.py`: 리포트 생성 시 현재 채점 규칙으로 다시 채점
- 테스트 31개(`tests/test_rag_eval_run.py`): 채점 경계, 청킹 누락·중복 없음, 코사인 순서, 재개(전체·부분), 잘림 시 중단, 첫 요청/재사용 분류, 리포트 집계
- 결과: `results/*.jsonl`(524건), `results/report.md`, `results/index_timing.json`

**실행 중 발견·수정** [확인]
- 캐시 비우기용 짧은 요청("hi")은 효과 없음: Ollama(llama.cpp)가 이전 프롬프트 캐시를 다시 써 2·3번째 "cold"가 0.26초. → 모델을 내렸다 올리는 방식으로 변경(로딩은 지연에서 제외), 구간당 5문제 추가 측정. 본 실행 기록은 리포트에서 구간 첫 질문만 cold로 재분류
- 스모크 실행에서 자동 채점 보정: "2025 년 11 월 3 일" 띄어쓰기, "정보 없음" 거절, "북 브리지" 표기 → 공백 무시·거절 표현·허용 표기 추가(`build.py --questions-only`로 질문만 갱신)
- 본 실행 B의 색인 시간에 모델 로딩이 섞임(2k 26.7초) → `--index-only`로 재측정
- **qwen3:4b 비교 불가**: Thinking 모델이라 `think: false`에도 영어 추론을 이어 가 216건 중 119건이 출력 한도에서 잘리고 84건은 "답:" 줄 없음. 엄격 기준(답 줄 필수) 정확도 44~67%로 관대 기준(69~83%)과 크게 다름 → 결론에서 제외(사용자 결정)
- 재현성: 같은 질문을 캐시 재사용/모델 재시작 조건에서 비교하면 20건 중 19건 답이 동일, 1건 표현만 다름

**결과 (bonsai-2:9b, 실험용 합성 데이터, 자동 채점)** [확인]
| 구간 | A 정확도 | B 정확도 | A 첫 요청(5회 p50) | A 캐시 재사용 p50 | B 질문당 p50 | B 색인(1회) | B Recall@5 |
|---|---|---|---|---|---|---|---|
| 2k | 69% | 75% | 0.8초 | 0.5초 | 0.6초 | 0.14초 | 0.98 |
| 8k | 67% | 69% | 2.4초 | 0.6초 | 0.6초 | 0.42초 | 0.83 |
| 32k | 50% | 67% | 8.5초 | 0.6초 | 0.6초 | 1.8초 | 0.73 |
| 100k | 28% | 64% | 33.8초 | 0.9초 | 0.6초 | 5.3초 | 0.66 |
- A는 32k부터 급락. 100k에서 최신 값 질문 1/8, 근거 문서 인용 19%. B는 완만히 하락하며 한계는 검색(Recall@5 하락)
- 2k~8k의 A·B 차이는 1~2문제로 36문제 표본에서 의미 있는 차이 아님
- 여러 문서 근거 질문은 두 방식 모두 0~25% — 모델 한계. 제목 구분·답 없음은 B가 안정적(100k B 답 없음 4/4, A 1/4)
- GPU: A 100k 6.8GB, B 3.1GB(bge-m3 별도 약 1.2GB), 모두 100% GPU
- **수동 확인 표본** [확인]: 구간×방식별 5건(seed 1), 40건 중 40건 자동 채점과 판단 일치. 관찰된 오류 유형: 최신 값 대신 옛 값, 근거가 있는데 "근거 없음", 답 없음 질문에 지어낸 값, 버전 대신 날짜·문서 ID로 답함

**임계값 (사용자 승인, PRD v6.6 반영)**: 정제 후 코퍼스 ≤ 약 8k 토큰이면 Full Context, 초과면 RAG. 근거: 8k까지는 정확도가 같고 첫 요청 2.4초 이하이며 색인이 필요 없음. 32k에서 정확도 −17%p·첫 요청 8.5초로 RAG가 우세. 8k~32k 사이는 측정하지 않아 보수적으로 8k에서 전환

### 8단계 — 뉴스 AI 질문 (2026-11-04~05)

**결정 (사용자 승인, PRD v6.7)**: 서비스 LLM 로컬 `bonsai-2:9b`. 배포 질문(Vercel 등)에 대한 답: Ollama는 배포하지 않고 배포 환경은 `NEWS_AI_ENABLED` OFF — 서버는 Ollama 없이 기동, 나머지 기능 정상. 배포에서 켜려면 권리 확인 + GPU 서버 또는 외부 API(호출부 교체, 임계값 재확인)

**변경**
- `app/qa/`: `prompt.py`(실험과 같은 지시문·"답:/근거:" 해석, 실험 채점도 이것을 사용), `retrieval.py`(실험에서 이동), `llm.py`(Ollama REST, 첫 질문 때 HTTP 클라이언트 생성, 장애 → `AI_UNAVAILABLE`), `service.py`(코퍼스 → 모드 선택 → LLM → 근거 검증)
- 동작: 공식 공지 전문(최근 50건/날짜 범위, 외부 링크뿐인 글 제외) → 글자 수/3 ≤ 8,000이면 Full Context, 아니면 RAG(Top-5). Full Context 입력이 잘리면 RAG로 다시 묻는다. 인용 ID 중 넘기지 않은 문서는 버리고 "근거 없음"이면 출처 없음. 코퍼스·임베딩 10분 메모리 캐시, LLM 호출은 Lock으로 한 번에 하나, 본문·답변은 로그에 남기지 않음
- `news.py`: `fetch_full` 추가(Steam 요청·오류 처리는 목록 조회와 공용), 목록 응답 `askEnabled`. `config.py`: `news_ai_enabled`(기본 False)·`ollama_url`·`qa_*`. `.env.example`에 안내
- 프론트: `/news/[appid]`에 질문 영역(질문 300자, 선택 기간, 답변·출처·모드·공지 수·기간·입력 토큰 표시, 기능 OFF면 안내), `useAskNews`(mutation), `next.config.ts` `experimental.proxyTimeout` 130초(기본 30초 — Next 소스에서 확인), API 타입 재생성
- 앱 생성 시 Ollama HTTP 클라이언트를 만들면 테스트당 약 0.5초(SSL 설정 로드) → 첫 질문 때 만들도록 변경(전체 테스트 25초 → 2.5초)

**검증** [확인]
- 테스트 28개(`tests/test_news_qa.py`): 플래그 OFF(Steam·LLM 미호출), `askEnabled`, Ollama 없는 서버 기동·`AI_UNAVAILABLE`, 근거 ID 검증, 거절 시 출처 없음, 긴 응답 자르기, 쓸 글 없음(LLM 미호출), RAG Top-K, Full Context 잘림 → RAG, 날짜 범위(enddate·필터), 입력 검증 6종, 없는 게임, 코퍼스·색인 캐시, 동시 질문 직렬화, 본문·답변 로그 비노출, Ollama 옵션·임베딩 묶음·장애 5종. 전체 306개 통과(DB 포함), ruff·eslint·tsc 통과
- DB 테스트와 함께 돌리면 Alembic `fileConfig`가 기존 로거를 꺼(`disable_existing_loggers`) 로그 검사 테스트만 실패 → 테스트에서 대상 로거를 다시 켬
- 실제 확인(Terraria 105600, 프론트 프록시 경유): 50건 = 58만 자 → RAG. 첫 질문 20초(모델 로딩·490조각 임베딩), 이후 2초. "최근 PC 출시 버전" → 1.4.5.7 정답, "출시일" → 2026-08-19 정답. 10월 1건 → Full Context 11초. 8월 2건(긴 글) → RAG, 요약에 1건만 인용
- **실제 뉴스 관측(합성 실험과 분리)**: 범위 없이 "최근 업데이트 버전"을 물으면 개발 중으로 언급된 1.4.5.8을 답한 경우가 있음(질문 모호성 + RAG 조각 선택). 요약형 질문은 RAG에서 일부 글만 반영 — 7단계에서 미측정이던 우려가 실제로 보임
- 미검증: 프론트 프로덕션 빌드(CI), 화면 직접 조작(사용자 확인 예정), 30초 넘는 첫 질문의 프록시 통과(설정만 확인)

**사용자 화면 확인 → 지시문 v2 (2026-11-05)**
- 문제: "가장 최근 업데이트에서 바뀐 점" → "2026년 8월 19일 문서에 포함된 변경 사항들입니다"(문서만 가리킴). 출처는 맞음 → 원인은 검색이 아니라 v1 지시문의 "답: <짧은 답>"
- 수정(사용자 승인, PRD v6.7 문구 갱신): 값·이름·날짜는 짧게, 설명형은 실제 내용 3~5개 요약, 문서만 가리키는 답 금지. "답:"부터 "근거:" 전까지 여러 줄을 답으로 읽음(실험 채점도 같은 함수 — v1 리포트 재생성 결과 변화 없음 확인). 입력창 예시를 "1.4.5.7 업데이트에서 바뀐 점은?"으로(모호한 "최근" 대신 버전·날짜 유도)
- 같은 질문 비교 [확인]: v1 문서 가리키기 → v2 실제 변경 내용 요약. "최근 PC 출시 버전"은 둘 다 1.4.5.7
- **v2 재실험** [확인] (`results/prompt_v2/`, bonsai-2:9b, 같은 데이터·질문): A 75/72/44/31%, B 81/72/64/61% (v1 A 69/67/50/28, B 75/69/67/64). 8k까지 동등·32k부터 A 하락 모양 동일 → **임계값 8k 유지**. v1→v2 정답 전환 12건을 직접 확인, 모두 실제 정답(긴 답에 숫자가 섞여 생긴 오판 없음), 반대 8건 — 오차 범위. 사실 질문 답 길이 중앙값 5자
- 지연은 v2 측정에서 전반적으로 약 1.4배(100k 첫 요청 31.7→41.3초). 출력 토큰은 같아(p50 35) 지시문보다 측정 환경(Docker·프론트 개발 서버·백엔드 동시 실행) 차이로 추정, 원인 미확인

**사용자 화면 확인 2 → 지시문 v3 (2026-11-05)**
- 문제: v2 답이 "아이템 스탯 변경, 새 아이템 추가, 여러 버그 수정"처럼 뭉뚱그림. 진단 [확인]: 검색은 정확(상위 5조각 모두 1.4.5.7 공지, "Unholy Trident 피해량 88→150" 등 구체 내용 포함) → 모델 요약 방식 문제. 1.4.5.7 공지는 4만 자(약 1.3만 토큰)라 5조각으로 전체 요약은 원래 불가
- 비교 [확인]: 이름·수치 강제만 하면 한 아이템 수치를 나열(요약 아님). "분야별 최대 5항목, 항목마다 대표 예시 이름·수치 1~2개"(v3)가 세 가지 질문 표현 모두에서 분야별 구체 예시로 안정적. v2는 표현에 따라 뭉뚱그림 또는 수십 개 나열
- **v3 재실험** [확인] (`results/prompt_v3/`): A 69/75/53/39%, B 72/69/67/58%. 8k까지 동등, 32k부터 B 우세(+14~19%p) → **임계값 8k 유지**. v1 대비 정답 전환 17건 모두 실제 정답, 반대 12건 — 오차 범위. 답 없음 질문은 A에서 개선(32k 4/4)
- 지연은 측정마다 느려짐(v3 100k 첫 요청 64초·색인 19초) — 측정 직후 GPU 사용률 40%, Ollama 외 약 3.7GB 사용 중이라 다른 프로그램과 GPU 경합으로 추정. 지연 비교는 깨끗한 환경에서 다시 재야 함(미검증)
- 남은 한계: 소형 모델이라 답에 영어 원문·깨진 글자(예: "코oldown")가 섞임, 대형 패치노트는 일부 조각만 반영

**사용자 화면 확인 3 → 기간 제거·"최신 업데이트" 기준·지시문 v4 (2026-11-05)**
- 문제: "최신 업데이트에서 바뀐 점은?"이 여전히 뭉뚱그림. 진단 [확인]: 이번엔 검색 문제 — 의미 검색은 날짜를 보지 않아 1.4.5.7 공지는 인사말 조각 1개만, 나머지는 1월 1.4.5 출시 공지(중국어 안내 포함)·2025년 10월 글이 걸림. 모델은 받은 내용 안에서 정직하게 답한 것
- 공지 본문의 `---` 줄이 문서 구분자와 같아 한 문서가 쪼개져 보이는 버그도 발견
- 검토한 대안: 최신성 보정+문서 확장, 공지별 질문(모호함은 사라지나 여러 공지에 걸친 질문 불가) → **사용자 결정**: 기간 설정 없이 항상 최근 50건 전체, "최신"의 기준만 정한다
- **결정 (사용자 승인, PRD v6.7 갱신)**: "최신 업데이트" = 제목에 버전 번호·업데이트·패치·핫픽스가 들어간 가장 최근 공지(없으면 가장 최근 글). 범위를 좁히지 않고 항상 함께 넣음 — "최신 값" 질문은 값이 마지막으로 바뀐 다른 공지에 있을 수 있어서
- 변경: `prompt.py` `latest_update_id`·`mark_latest`·`strip_rules`, 지시문 v4(표시된 문서 = 최신 업데이트, 최신 값은 마지막으로 바뀐 문서 기준), `retrieval.py` 문서 한정 검색·`context_chunks`(Top-5 + 최신 공지 청크 3개), `qa_rag_num_ctx` 8,192 → 12,288, 요청에서 `dateRange` 제거(모르는 항목은 422), 응답에 `latestUpdate`, 답 속 내부 문서 번호("(N047)") 제거, 실험 실행기도 같은 규칙 적용. 프론트: 기간 입력 제거, "최신 업데이트 기준: …" 표시
- **v4 재실험** [확인] (`results/prompt_v4/`): A 69/72/47/36%, B 75/81/69/56%. 8k까지 B ≥ A, 32k부터 B 우세 → **임계값 8k 유지**. 다만 B 100k는 v1 64% → v4 56%, "최신 값" 질문 3/8로 하락 — 최신 공지를 항상 넣어 그 공지 기준으로 답하는 경우로 추정(3문제 차이, 오차일 수 있음)
- 실제 확인 [확인] (Terraria): "최신 업데이트에서 바뀐 점" → 1.4.5.7 기준 분야별 4항목(마나 재생 지연 제거, 초 마나 포션 300→400 등), "Unholy Trident 피해량" → 150, "최근 PC 출시 버전" → 1.4.5.7. 한계: "최근 패치 내용 알려줘"는 5항목 제한을 무시하고 수십 개 나열(내용은 정확)
- 테스트: 최근 50건 요청(기간 없음), 최신 공지 고정·소식 글 제외, 구분선 제거, `dateRange` 거절, 답 속 문서 번호 제거 등. 전체 259개 통과(DB 제외)

**v4 부작용 확인 → 질문 유형별 답변 틀(지시문 v5, 2026-11-05)**
- 사용자 질문: "3문제 차이면 큰 것 아닌가" → "오차" 표현이 부정확했음. 이 실험은 결정적(같은 조건이면 같은 답)이라 무작위 오차가 아니라 변경의 영향. 다만 지시문을 조금만 바꿔도 아슬아슬한 문제들이 양방향으로 뒤집혀 숫자만으로는 원인을 못 가림 → **떨어진 문제를 직접 열어 원인 확인**하는 절차로 판단. 유형별 문제가 8개뿐이라 1문제 = 12.5%p
- 확인 [확인]: 100k B "최신 값" 하락 중 Q13은 최신 공지를 인용하며 "근거 없음" → 최신 공지 고정의 부작용 맞음. Q19는 v3부터 버전 대신 "[N122]"로 답한 형식 문제. 이 과정에서 서비스 버그 발견: 답 속 문서 번호를 지우면 번호뿐인 답이 빈 답이 됨
- **사용자 제안·결정**: 게임 공지 질문은 유형이 거의 정해져 있으니 답변 틀을 정해 두자 → 유형 4개(업데이트 요약·값·일정·기타), 서버가 질문 단어로 판별, 모델은 유형별 JSON 칸만 채움(Ollama `format` 스키마 강제, 새 라이브러리 없음). 최신 공지 표시·고정은 업데이트 요약에만. PRD v6.7 갱신
- 구현: `app/qa/templates.py`(판별 규칙·유형별 지시문·스키마·해석·문장 만들기), `prompt.py`는 문서 표시·최신 판별·옛 형식 해석만 남김, `llm.chat`에 `schema`, 응답에 `intent`·`summary`·`value`·`schedule`, 칸이 문서 번호뿐이면 공지 제목으로 바꿈, JSON이 깨지면 "다시 시도" 안내. 화면: 유형별 표시(요약 = 분야별 목록, 값 = 큰 숫자 + 이전 → 현재·바뀐 버전, 일정 = 이름·기간), 질문 템플릿 버튼 3개, 긴 자유 답 "더 보기"
- 사전 확인 [확인]: "found(찾았는지)" 칸을 먼저 두면 모델이 내용을 채우기 전에 "없음"으로 정해 버림 → 칸을 없애고 값에 "근거 없음"을 쓰게 함. 판별 규칙은 실험 질문 36개에 적용해 확인(Q05 "패치노트의 알려진 문제"가 요약으로 잡혀 "패치노트" 단어 제외)
- 실제 확인 [확인] (Terraria): "최신 업데이트에서 바뀐 점" → 1.4.5.7 새 기능(Scout's Sling 등)·버그 수정 2건, **"최근 패치 내용 알려줘"도 같은 틀**(이전엔 수십 개 나열), "Unholy Trident 피해량" → 150 (88 → 150), "다음 점검" → 근거 없음, "1.4.5.7 출시일" → 일정 2026-08-19(하루짜리 일정은 "~ ?" 없이 표시하도록 수정). 한계: 버그 수정 항목이 영어 원문 그대로 나오기도 함
- **채점 버그 발견·수정** [확인]: v5 화면 문장 "50 (2.4.1에서 55 → 50)"에 이전 값이 들어 있어 Q08(정답 55)·Q32(정답 10)처럼 틀린 답이 정답 처리됨 → 값 질문은 **값 칸만** 채점(`grading.structured_content`), 기록의 `raw` JSON에서 다시 채점. v1~v4 리포트는 변화 없음 확인
- **v5 재실험** [확인] (`results/prompt_v5/`, 바로잡은 채점): A 69/67/47/47%, B 69/69/67/61%. 8k까지 동등, 32k부터 B 우세 → **임계값 8k 유지**. 100k B "최신 값" 3/8 → 5/8 회복(Q13 정답 "20초"). JSON 형식 오류 0건. 새 약점: "얼마나 줄었나/몇 번 바뀌었나" 같은 차이·횟수 질문에 값 칸에 현재 값을 넣음 → 여러 문서 근거 질문 0~12%(v1 0~25%)

**화면 정리와 질문 버튼 교체 (2026-11-05, 사용자 피드백)**
- 답 아래 "관련 부분 검색 · 공지 50건 · 입력 1,380토큰 · bonsai-2:9b" 줄을 화면에서 제거(사용자에게 불필요). 값은 API 응답에 남김(PRD: 입력 토큰은 응답에 기록)
- 일정 표시: 시작일 없으면 "? ~ 끝" 대신 "끝까지", "2026-08-31T19:00:00" 같은 ISO 날짜는 "2026. 8. 31. 19:00"으로(시간대 변환 없음). 입력창 예시를 Terraria 전용 이름 대신 일반 문구로
- 질문 버튼: 이벤트·점검은 Steam 게임 공지와 맞지 않음(사용자) → "최신 업데이트에서 바뀐 점은?", "새로 추가된 콘텐츠는?" 2개. 실제 확인 [확인] (Terraria): "새로 추가된 콘텐츠는?" → 1.4.5 새 아이템·보스 음악 등. "앞으로 나올 업데이트 계획은?"·"다음 대형 업데이트 계획 있어?"·"다음 업데이트는 언제 나와?" → 근거 없음, "개발팀이 다음에 준비 중인 건?" → 영어 한 구절 → **앞으로의 계획 질문은 약점**으로 기록. "진행 중인 이벤트"는 이미 끝난(8/31) 대회를 진행 중으로 답함
- 린트·타입 검사 통과 [확인]

**다음 작업 제안: Steam 공지 종류 기반 답변 틀 개편 (사용자 승인 "가": 현재 작업 커밋 후 시작)**
- 장르별 24개 게임의 최근 공지 제목 조사 [확인] (제목만 보고 저장하지 않음): 패치·핫픽스(거의 전부), 대형 업데이트·DLC 출시·예고(대부분), 개발 일지·로드맵(절반), 이벤트·시즌(라이브 게임), 베타·테스트 빌드(7DTD EXP, DbD PTB, Factorio Experimental 등), 할인·무료 주말, 점검·제재(가챠·온라인 일부), 굿즈·협업·트위치 드롭(Elden Ring은 최근 글 대부분이 굿즈)
- 제안 틀 5종: ① 패치 요약 + 규모(대형/패치/핫픽스)·빌드(정식/테스트) ② 일정 + 종류(이벤트/출시/점검/베타/할인), 진행 중·예정·종료는 **서버가 오늘 날짜로 판정** ③ 신규 콘텐츠·DLC(이름·형태·출시일·핵심 3개) ④ 값 ⑤ 기타. 개발 일지·로드맵은 기타로(시험 결과 약함)
- "최신 업데이트" 기준 보강: Store·Drops·굿즈 제목 제외(ARC "Store Update"는 상점 개편), 테스트 빌드는 정식보다 뒤로
- 검증: 합성 데이터에 DLC·베타 질문이 없어 실제 공지 5~6개 게임 수동 확인. PRD 수정안은 먼저 제안 후 승인

**Steam 공지 종류에 맞춘 답변 틀 개편 (지시문 v6, PRD v6.8, 2026-11-05~06)**
- 틀 5종: 패치 요약(+규모 MAJOR/PATCH/HOTFIX·빌드 STABLE/TEST, 서버가 공지 제목으로 판정), 일정(최대 3건·종류·상태), 신규 콘텐츠·DLC(이름·형태·출시일·핵심 3개), 값, 기타. 판별 순서 값 → 일정 → 콘텐츠 → 요약 → 기타. 실험 질문 36개 중 판별이 바뀐 것은 Q06(기타 → 콘텐츠) 1개
- 상태(진행 중/예정/종료/모름)는 **서버가 오늘 한국 날짜로 판정**(모델에 맡기지 않음, 고정 UTC+9 — Windows zoneinfo는 tzdata 필요). 시작일만 있으면 출시·점검은 하루짜리, 이벤트 등은 "모름"(Apex Blood Pact를 "종료"로 판정하던 문제). 지금·앞으로를 물었는데 끝난 일정만 찾으면 "진행 중이거나 예정된 일정을 찾지 못했습니다" + 흐리게 표시(`noCurrent`)
- "최신 업데이트": Store·Drops·굿즈 제목 제외(ARC "Store Update"는 상점 개편, Elden Ring은 최근 글 대부분이 굿즈), 테스트 빌드(EXP·PTB·Beta)는 정식이 없을 때만. 요약의 버전 칸이 비면 제목의 버전 번호로 채움
- 첫 실제 확인 [확인]: 요약은 좋았으나 일정·콘텐츠가 옛 공지를 고름(CK3 다음 DLC → 이미 나온 By God Alone, Apex 콘텐츠 → 8월 이벤트, DST 이벤트 → 6월). 원인: 의미 검색은 날짜를 보지 않고 모델은 오늘을 모름 → **일정·콘텐츠에만 지시문에 오늘 날짜, RAG에 최근 공지 5건(상점·굿즈 제외)마다 청크 1개**(사용자 승인). 재확인 [확인]: CK3 → Silk & Silver 11/17 출시 예정, Apex → Cipher, DST → Hallowed Nights 10/26부터
- 지시문 보정: 모델이 종료일 칸에 시작일을 베낌(DST 10/26 ~ 10/26 → "종료") → "종료일이 따로 없으면 비운다". 영어 원문 섞임은 "이름·수치를 그대로" 지시를 문장 통째 복사로 받아들인 탓 → "이름·수치만 원문, 설명은 한국어". 처음엔 공통 지시에 넣었다가 재실험에서 짧은 답의 장소명 오역("north bridge" → "북쪽 다락", Q04)·목록 대신 문장(Q27) → **요약·콘텐츠 칸에만** 둠
- Blue Archive "다음 점검" 조사 [확인]: 점검·패치 공지 본문이 약 210자로 외부 링크뿐이고 날짜는 제목에만 있음, 최근 점검(10/27)도 이미 지남 → "예정된 점검 없음" 안내는 맞고, 보조로 보이는 "최근 끝난 일정"만 8/20(유일하게 본문이 있는 글)로 틀림. **한계로 기록**(본문이 링크뿐인 공지)
- **v6 재실험** [확인] (`results/prompt_v6/`, 실험의 "오늘" = 데이터 마지막 공지 다음 날로 고정): A 69/67/47/47%, B 69/69/67/61% — **v5와 모든 칸 동일, 뒤집힌 문제 0개, JSON 형식 오류 0건 → 임계값 8k 유지**. 지연은 v5보다 짧음(100k A 첫 요청 50 → 32초, 이전 측정의 GPU 경합으로 추정). 중간본(한국어 지시를 공통에 둔 버전)은 7문제가 뒤집혀(나빠짐 5) 폐기
- 최종 실제 확인 [확인] (14개 질문): 요약 — CK3 1.20.1.2 패치, 7DTD 3.4.0 핫픽스·정식(한국어), Elden Ring 1.17 대형(한국어), DST 핫픽스, Terraria 1.4.5.7 / 일정 — CK3 Silk & Silver 11/17 예정, Apex Blood Pact 10/13부터, DST Hallowed Nights 10/26부터, Blue Archive "예정 없음" 안내 / 콘텐츠 — CK3 Silk & Silver, Apex Cipher, Terraria 1.4.5.7 / 값 — Unholy Trident 150(88 → 150). 한계: DST처럼 긴 영어 문장은 여전히 원문 그대로 나옴
- 테스트: 판별(콘텐츠·일정 순서, "DLC에는"처럼 한글이 붙은 영단어), 날짜 상태 판정(10경우), 일정 정렬·자르기·모르는 종류, 콘텐츠 상태, 제목 규모·빌드·버전, 최신 업데이트 제외 규칙, 최근 공지 청크(드롭 제외), 오늘 날짜 지시, `noCurrent`, v5 일정 기록 재채점 호환. 전체 312개 통과(DB 제외 51 skip), ruff·FE lint·typecheck 통과

**값 질문 = 변경 기록 추출 + 서버 계산 (지시문 v7, PRD v6.9, 2026-11-06)**
- 배경(사용자 질문 "60%대는 낮은 것 아닌가"): 36문제 중 multi 8문제가 0~12%라 평균을 끌어내림(multi 제외 8k B 86%, 100k B 75%). 데이터는 A·B 차이를 드러내려고 같은 수치가 버전마다 바뀌도록 어렵게 만든 것이라 절대 점수 = 서비스 품질은 아님. 다만 latest 62%·multi 12%는 실제 약점 — 공통 원인은 9B 모델이 여러 문서의 날짜 비교·세기·빼기를 직접 하다 틀림
- 결정(사용자 승인): 모델은 변경 기록 `history[{doc, version, before, after}]`(최대 8)만 옮기고, 서버(`app/qa/value.py`)가 넘긴 문서만 남기고 문서 날짜로 정렬한 뒤 질문 단어로 계산 방식을 고름 — 지금 값 / 특정 버전(정규 패치·핫픽스 구분) / 처음 값 / 언제·몇 버전 / 횟수 / 차이 / 버전 목록. 기준이 없거나 숫자를 못 읽으면 근거 없음. 출처는 답으로 고른 기록의 공지(횟수·차이·목록은 기록 전체). 화면: 계산 방식 이름 + 변경 기록 표. "바뀐 버전"을 값 질문 단어에 추가(Q25·Q27 기타 → 값)
- 실제 확인에서 고침 [확인]: 모델이 지시문 예시 버전 "2.4.1"을 베낌(Terraria) → 공지 제목의 버전 우선 + 예시 제거. 기록 1건·이전 값 없음에 "0, 변화 없음" → 근거 없음
- **재실험 1차에서 원인 발견** [확인]: 모델이 문서 ID를 "N115" 대신 "N0115"로 적어 서버가 기록을 통째로 버림(정답 기록이 있는데 근거 없음) → ID 정규화(`doc_ids`). 원문 JSON이 기록돼 있어 재실험 없이 다시 채점
- **v7 재실험** [확인] (`results/prompt_v7/`): A 89/81/50/36%, B 92/81/75/61% (v6: A 69/67/47/47, B 69/69/67/61). multi B 2k 0 → 75%, 8k 12 → 62%, 32k 12 → 50%. latest 2k A 88 → 100%. 문제별 v6 대비 36개 오르고 12개 내림 — 내린 것은 모델이 기록을 빠뜨리거나(서버가 지어내지 않고 근거 없음) 이전·이후 값을 뒤바꾼 경우. **임계값: 8k까지 A ≈ B(89 vs 92, 81 vs 81), 32k부터 B 우세 → 8k 유지.** 100k A는 36%로 하락(긴 입력에서 기록을 덜 찾음) — 서비스는 8k 초과에 RAG를 써서 영향 없음. 출력 토큰 p50 65 → 약 105(기록을 적느라), 지연 차이는 작음
- 실제 확인 [확인] (14개 질문): 이전과 같은 답(회귀 없음), Unholy Trident 150(1.4.5.7에서 88 → 150) + 변경 기록. "언제 바뀌었어?" → 1.4.5.7
- 테스트: 계산 방식 판별 9경우, 지금 값 정렬·제목 버전, 정규/핫픽스 구분, 처음·언제, 횟수·목록·차이, 단위·못 읽는 숫자, 넘기지 않은 문서, 제목 버전 우선·기준 없는 차이, ID 정규화, 옛 기록 호환(`tests/test_qa_value.py`). 전체 334개 통과(DB 제외 51 skip), ruff·FE lint·typecheck 통과. v5·v6 리포트는 새 채점 코드로 다시 만들어도 동일
- 남은 한계: 모델의 기록 추출 오류(빠뜨림·뒤바꿈), RAG Top-5에 안 걸린 공지의 기록은 못 셈(100k B multi 25%), 긴 영어 문장, 본문이 링크뿐인 공지

**화면 다듬기와 영어 줄 재번역 (PRD v6.10, 2026-11-06)**
- 사용자 피드백: 출처와 "최신 업데이트 기준"에 같은 공지가 두 번 보임 → 최신 업데이트 공지가 출처에 있으면 그 줄을 숨김(다른 공지를 요약했을 때만 보임). "공지에서 근거를 찾지 못했습니다. (근거 없음)"은 친화적이지 않음 → 유형별 안내 문장, 값 질문은 "원문(영어) 이름으로 물으면 더 잘 찾는다" 도움말. 판정용 "근거 없음"은 내부(채점·거절 판정)에만 (`4054f57`)
- 영어 원문 줄(DST 등): 사용자 질문 "이름은 두고 나머지만 번역할 수 없나" → 답은 그대로 두고, 요약·콘텐츠 목록에서 한글이 거의 없는 줄만 같은 모델에 번역만 따로 요청(`app/qa/translate.py`, 사용자 승인). 서버가 원문의 대문자 이름 단어(문장 첫 단어·소유격 's 제외)와 숫자가 번역에 그대로 있는지 확인하고 아니면 그 줄은 원문. 영어 줄이 없으면 호출 없음, 실패해도 원문으로 답함. 답을 만드는 지시문은 그대로라 재실험 불필요
- 실제 확인 [확인]: DST "Willow의 Shadow Fire가 때로는 타겟에 도달하지 않고 그 주위를 맴돌 때가 있습니다", "Frankenswine, Mermummy, 그리고 Vamphare는 개별적으로 애그로될 때 자동으로 서로에게 타겟을 공유하지 않습니다" — 이름 유지. 7DTD·Elden Ring·CK3·Apex·Terraria는 이미 한국어라 번역 호출 없음
- **성능 문제 발견·수정** [확인]: 번역 요청을 num_ctx 4096으로 보내자 Ollama가 답변 요청(12288)과 오가며 모델을 다시 올려, 번역이 없는 Terraria 값 질문까지 4초 → 13초. 번역도 `qa_rag_num_ctx`로 맞춰 해결(DST 번역 포함 4.8초, Terraria 값 3.4초). 참고: Full Context는 질문마다 num_ctx를 분량으로 정해 같은 재로딩이 생길 수 있음(미측정)
- 테스트: 번역 대상 고르기, 이름 단어 추출, 순서 유지·한국어 줄 미전송, 이름 바뀜·한글 없음·숫자 빠짐 거절, 호출 없음, 요청 실패·개수 다름은 원문, API 통합(두 번째 요청에 영어 줄만, 같은 num_ctx). 전체 347개 통과(DB 제외 51 skip), ruff 통과

### 9단계 — 운영 구성·API 제한 점검·E2E (2026-11-06)

**결정 (사용자 선택)**: 배포 대상 = **로컬 Docker 운영 구성만**(외부 공개 배포 없음, 비용 0, 나중에 어느 서버로든 옮길 수 있게). E2E = **실제 Steam API + 내 계정, 로컬 전용**(CI 제외). `@playwright/test`(PRD 기술 표 승인) 설치 직전 재확인 후 설치 — 1.64.1(10-14 배포), 개발 의존성, Chromium만. `npm audit` moderate 8건은 기존 ESLint 체인(`@typescript-eslint`·`minimatch`)이며 Playwright와 무관

**운영 구성** (`compose.prod.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `.dockerignore` 2개, `next.config.ts` `output: "standalone"`)
- db(postgres:17, 볼륨 분리) → migrate(`alembic upgrade head` 1회, 스키마는 마이그레이션으로만) → backend(healthcheck) → frontend(127.0.0.1:8080). 개발 환경(DB 5433, 3000·8000)과 포트·볼륨이 겹치지 않음
- 비밀값은 새 파일 없이 `backend/.env`를 실행 시 환경 변수로 넘김(이미지에 넣지 않음, Claude는 읽지 않음). 운영 값(`APP_ENV=production`, DB 주소, `PUBLIC_BASE_URL=http://localhost:8080`, `NEWS_AI_ENABLED=false`)은 compose가 덮어씀. 실제 서버에 올릴 때는 개발과 다른 비밀값을 따로 둘 것
- 백엔드 워커 1개(수집기·메모리 캐시·GPU 직렬화 잠금이 한 프로세스 전제), 루트가 아닌 사용자로 실행. 프론트 rewrites 대상은 빌드 인자 `BACKEND_URL=http://backend:8000`(rewrites는 빌드 때 정해짐)
- 확인 [확인]: 기동 순서·마이그레이션 5개 적용, `/api/health` env=production, 대시보드(수집기가 기동 직후 차트 수집), 뉴스, Steam 로그인 이동(return_to `localhost:8080/api/auth/steam/callback`), 비로그인 401

**API 제한 점검** — 적용됨: Steam 요청 타임아웃 10초, 상점 API 토큰 버킷(초당 0.6·순간 10)+동시 4+429 시 60초 정지, 실패 재시도 대기, 가격 요청당 묶음 3, 캐시(보유 5분·뉴스 10분·질문 공지 10분), 입력 검증(appid 범위·뉴스 1~20·제외 1000·질문 300자·모르는 항목 거절), 세션 7일·nonce 5분, AI(120초·출력 1024·공지 50·컨텍스트 12k·한 번에 하나). **빠진 것(공개 배포 전 필요, 사용자 결정: 기록만)**: ① 우리 API로 들어오는 요청 수 제한 없음(비로그인 뉴스 목록은 새 appid마다 Steam 호출) ② Steam Web API(뉴스·보유 게임)에 호출 속도 제한기 없음(한도 하루 10만) ③ AI 질문 대기열 길이 제한 없음(몰리면 130초 프록시 시간 초과 뒤에도 서버는 처리). 공개 배포 시 ①부터(IP별 토큰 버킷 재사용, 새 오류 코드 → PRD 수정 필요)

**E2E** (`frontend/playwright.config.ts`, `frontend/e2e/`, `npm run e2e`)
- 비로그인 6개: 대시보드·로그인 버튼, OpenID 이동 주소(return_to·realm), 비로그인 안내, 위조 쿠키 거부(401), 뉴스 목록·원문 링크, API 오류 형식(422). 로그인 4개: 내 라이브러리 요약·보유 게임 추천(점수)·구매 추천·할인(오류 없음)·장르, 목록 → 뉴스 이동, 공지 질문(켜진 환경 = 요약 틀·출처, 꺼진 환경 = 안내), 로그아웃 후 401
- 로그인: Steam 화면은 자동화할 수 없어 global-setup이 백엔드 `SessionManager`로 실제 콜백과 같은 서명 쿠키를 만듦(운영 코드 변경 없음). 쿠키는 `e2e/.auth/user.json`(gitignore)에만, 화면·로그에 출력 안 함. SteamID는 실행 때 `E2E_STEAMID`로만(커밋 안 함)
- 결과 [확인]: 개발 서버(3000, AI 켬) **10개 통과**, 운영 구성(8080, AI 꺼짐) **10개 통과**
- 도중에 겪은 일: ① PC 재시작 전 브라우저가 앱과 무관한 빈 페이지에서도 `requestAnimationFrame`을 실행하지 못해(Edge 포함, GPU·vsync 옵션 무관) React Suspense가 "불러오는 중…"에서 멈춤 — 재시작 후 정상. 원인 미확인(모니터 절전 추정은 사용자 확인으로 틀림) ② 세션이 끊긴 뒤 남은 개발 서버의 컴파일 워커가 죽어 500 → 재시작 ③ 재시작 후 Ollama가 꺼져 질문이 "AI 답변 서버에 연결할 수 없습니다"(오류 안내는 정상 동작) ④ 테스트 버그: Next.js 경로 안내 요소도 alert 역할이라 질문 영역 안에서만 셈 ⑤ Playwright 보고서 폴더를 ESLint가 읽어 3천여 건 → 무시 목록에 추가
- 미검증: 실제 Steam 로그인 화면을 거친 콜백(쿠키 Secure 속성 포함, 운영 모드), CI에서의 E2E(로컬 전용 결정), DoD의 "캐시 실패 시 부분 결과·통신 실패 시 오류 안내"는 pytest로만 확인(E2E에서 Steam 장애를 재현하지 않음), 외부 공개 배포(결정에 따라 하지 않음)
