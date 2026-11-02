# SteamMate 개발 로그

> 진행 상황·결정·변경 내역·검증 결과를 기록한다. 설계 기준은 [PRD.md](PRD.md)이며, 이 문서는 "언제 무엇을 했고 왜 그렇게 결정했는가"를 남긴다.
> 표기: **[확인]** 실행·조회로 검증 / **[추정]** 외부 문서·추론 기반, 구현 시 검증 필요

---

## 현재 상태 (2026-11-03 기준)

| 단계 | 내용 | 상태 |
|---|---|---|
| 0 | PRD v6 반영, Claude Code 가드레일 | ✅ 완료 |
| 1 | 실행 환경 정비, 테스트 기반, CI, 프론트 Provider·프록시 | ✅ 완료 (CI 통과) |
| 2 | 입력 파서 + 공개 라이브러리 조회 | ⏭ 다음 |
| 3 | 메타데이터 캐시(game_metadata) | 대기 |
| 4 | 보유 게임 추천 + 이유 | 대기 |
| 5 | Steam 로그인 | 대기 |
| 6 | 소스 스파이크 → 인기 대시보드 | 대기 |
| 7 | 가격·할인(위시리스트·DLC·미보유 추천) | 대기 |
| 8 | 뉴스 조회·정제 (R1 완료) | 대기 |
| 9 | Full Context vs RAG 실험 | 대기 (LLM 제공자 결정 필요) |
| 10 | 뉴스 AI 질문 (R2 완료) | 대기 |
| 11 | E2E·배포 | 대기 (배포 대상 결정 필요) |

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
| 11-03 | LLM 제공자·배포 대상은 미정, 각각 9단계·11단계 직전에 결정 | 사용자 답변 |

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

---

## 미확인·추정 사항 (구현 시 검증)

| 항목 | 확인 시점 |
|---|---|
| 비공개 계정 GetOwnedGames가 오류 대신 빈 `response` 반환 | 2단계 |
| 로그인해도 비공개 라이브러리 조회 불가 | 5단계 |
| store appdetails 레이트리밋(약 200회/5분) | 3단계 |
| appdetails `filters=price_overview` 다중 appid 지원 | 7단계 |
| IWishlistService/GetWishlist 공개 접근·응답 형식 (비문서화) | 7단계 |
| featuredcategories 스키마, GetMostPlayedGames 공개 접근 | 6단계 스파이크 |
| GetOwnedGames로 DLC 보유 여부 판별 불가 | 7단계 |
| 비문서화 엔드포인트·차트 데이터 공개 서비스 이용 약관 | 출시 전 |

---

## 로컬 개발 메모

- DB: `docker compose up -d db` (호스트 5433), 테스트 DB `steammate_test`는 컨테이너 안에 수동 생성
- DB 테스트 실행: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://steammate:steammate@localhost:5433/steammate_test pytest`
- 백엔드: `cd backend && source .venv/Scripts/activate && uvicorn app.main:app --reload`
- 프론트: `cd frontend && npm run dev` (`/api/*`는 `BACKEND_URL`로 프록시)
- push는 사용자가 직접 (`git push origin main`), CI 결과는 GitHub Actions에서 확인
