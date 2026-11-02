# SteamMate — 제품 요구사항 및 통합 설계

> 통합 PRD v5.2에서 해당 프로젝트 요구사항을 분리하고 기존 상세 설계 초안을 병합한 문서. 변경 제안은 승인 전 문서에 직접 반영하지 않는다.
>
> **v6 (2026-11-03, 사용자 승인)**: Steam 로그인, 할인(위시리스트·DLC·미보유 게임 추천), 인기 대시보드, 점수 기반 추천 이유 추가. API 경로·응답 형식·데이터 모델·오류 코드 통일. 릴리스를 R1/R2로 분할.

---

# 기획 및 요구사항

> 원문: 통합 PRD v5.2 해당 프로젝트 절을 분리한 파일. 새 요구사항이 확정되면 문서와 테스트 계약을 함께 갱신한다.

# 01 | SteamMate AI

Steam 공개 라이브러리의 플레이 패턴과 장르를 분석해 보유 게임 중 다음 게임을 추천하고, 취향에 맞는 할인 게임과 Steam 인기 동향을 보여주며, 선택한 게임의 공식 뉴스 내용을 기반으로 근거 있는 답변을 제공한다.

## MVP 사용자 흐름

대시보드(이번 주 인기·할인) → Steam 로그인 또는 프로필 URL/SteamID 입력 → 공개 라이브러리 조회 → 부분 메타데이터를 포함한 분석 → 보유 게임 TOP 3 추천(이유 포함) → 할인 정보(위시리스트·DLC·미보유 추천) → 게임 뉴스 선택 → 업데이트 질문 → 근거와 원문 링크 확인

| # | 기능 | 범위와 완료 기준 |
| --- | --- | --- |
| F1 | 프로필 입력 / Steam 로그인 | URL·Vanity·SteamID64 입력 또는 Steam OpenID 로그인(선택). 로그인은 SteamID 확인용이며 비공개 라이브러리 접근 권한을 주지 않음 |
| F2 | 라이브러리 분석 | GetOwnedGames 실조회; 플레이 시간·장르 분포; 비공개 시 설정 안내; 커버리지 n/m 노출 |
| F3 | 보유 게임 추천 | 보유 게임 중 TOP 3, 점수 요소별 이유·모드·조회 기준 시각 포함; 미플레이/저플레이 우선 옵션 |
| F4 | 할인 | ⓐ 위시리스트 할인 ⓑ 보유 게임 DLC 할인 ⓒ 미보유 할인 게임 추천(취향 점수, 후보 풀 크기 표시) |
| F5 | 인기 대시보드 | 이번 주 인기·최다 플레이·할인·신작, 순위 변화; 로그인/입력 시 보유·위시리스트·취향 매칭 표시 |
| F6 | 업데이트 AI | GetNewsForApp 요청 시 획득 → BBCode/HTML 정제 → 작은 코퍼스는 Full Context, 큰 경우 임시 RAG → 원문 링크; 근거 부족 시 응답 제한 |

**릴리스 분할**: R1 = F1~F5 + F6의 뉴스 목록·원문 링크 / R2 = F6 AI 질문. F6(Full Context vs RAG)은 핵심 기술 문제이므로 R2에서 반드시 수행한다.

**F4ⓒ 한계**: Steam 전체 할인 목록을 제공하는 공식 API가 없다. 후보 풀은 Steam 할인·인기·신작 목록에 오른 게임으로 제한하고 응답에 후보 수를 표시한다. 상점 검색 HTML 스크래핑은 하지 않는다.

**제외**: 친구 비교, 알림, 사용자 계정 DB, 추천 이력 저장, Hybrid 검색(2차 실험).

## 데이터 소스 및 저장 정책

메타데이터 조회 상태 명세

fetch_status = PENDING | SUCCESS | TEMPORARY_ERROR | NOT_AVAILABLE; last_checked_at, retry_after, failure_reason을 보관한다. (game_metadata, game_price 공통)

NOT_AVAILABLE은 장르가 실제로 존재하지 않거나 대상이 상점 메타데이터를 제공하지 않음이 재확인으로 확정된 상태로만 지정한다. 네트워크 오류·429·5xx·응답 스키마 불일치는 TEMPORARY_ERROR로 처리한다.

| 데이터 | 처리 |
| --- | --- |
| 보유 게임·플레이 시간 | 공개 SteamID만 조회. 개인 라이브러리 원본은 MVP 영구 저장하지 않음 |
| 위시리스트 | 공개 위시리스트만 요청 시 조회(비문서화 IWishlistService). 영구 저장하지 않음 |
| 로그인 세션 | 서명 쿠키(steamId + 만료)만. 사용자 테이블 없음 |
| 게임 장르/카테고리/DLC | store appdetails를 appid 키로 PostgreSQL에 캐싱. 비문서화 엔드포인트의 이용 조건·실패·429·구조 변경에 대응 |
| 게임 가격 | appdetails price_overview를 (appid, cc) 키로 단기 TTL 캐싱 |
| 인기·할인·신작 목록 | 주기 수집한 공개 집계 스냅샷을 일정 기간(기본 12주, 임시) 보관 후 삭제 |
| 뉴스 본문 | GetNewsForApp; 요청/짧은 세션에서만 전처리·임시 인덱싱. 원문 및 임베딩 영구 보관 금지(MVP) |
| 사용자 추천 | 요청 시 계산. metadataCoverage, recommendationMode, metadataSnapshotAt, calculatedAt 출력 |

## 추천 재현성 정책

metadataCoverage.ratio = SUCCESS / (SUCCESS + PENDING + TEMPORARY_ERROR) = success / (total − notAvailable). NOT_AVAILABLE는 유효 분석 대상에서 제외하고 notAvailable 건수를 별도로 표기한다. 영구 실패 판정은 HTTP 오류만으로 하지 않으며, 재확인 시점과 사유를 기록한다. 기존 임계값 90%는 임시 가정이다. 동일 입력·동일 메타데이터 행에서만 추천 재현성을 보장하며, 이를 순수 함수 테스트로 검증한다. 입력 스냅샷 해시는 MVP에서 제외한다.
장르 수집률이 임계값 미만이면 PLAYTIME_BASED, 이상이면 GENRE_AWARE로 표시한다.

## 기술 실험: Full Context vs RAG

| 항목 | 사양 |
| --- | --- |
| 주 실험 축 | 정제 후 입력 코퍼스 토큰 2k / 8k / 32k; 100k는 모델 컨텍스트·예산 허용 시 선택 실험 |
| 보조 기록 | 뉴스 문서 수, 청크 수, 언어, 전체 텍스트 길이, 질문 난도 |
| 대조군 | A 전체 문서 투입 / B 임시 Vector Top-K / C 선택적 Hybrid |
| 평가 데이터 | 실존 뉴스 원문 장기 아카이브 대신 자체 생성한 가상 패치노트(예: 60~100건)·질문 30~50개·검증된 정답/근거 ID |
| 평가 방법 | 같은 모델·질문·온도·토큰 제한; 정확도, 근거충실도, 지연시간, 입력/출력 토큰, 비용, Recall@K |
| 보고 원칙 | 합성 평가 결과와 실제 Steam 뉴스에서의 기능 관측을 분리. 임계점은 측정 결과로만 선정 |

주요 주의: 평가용 합성 문서는 실제 Steam 패치노트의 길이·언어·형식 다양성을 가깝게 모사하되, 특정 제3자 문장을 복제하지 않는다. 100k 컨텍스트가 모델 한도를 넘으면 실행하지 않고 N/A로 표기한다.

## 출시 게이트

- Steam API 키는 서버에서만 관리한다.
- Steam 뉴스 본문의 공개 AI 처리·저장·임베딩 권리는 미확정. 권리 확인 전 공개 RAG는 이용 허락된 자료로 제한하며 Steam 뉴스는 목록/원문 링크로 분리한다. 뉴스 AI 질문은 기능 플래그로 두고 **공개 배포 기본 OFF**.
- 비문서화 store 엔드포인트(appdetails, featuredcategories)·위시리스트·차트 데이터를 공개 서비스에서 사용하는 것도 출시 전 Steam 약관 검토 대상이다.
- 요청당 토큰·비용 상한과 타임아웃·API 제한을 적용한다.

---

# 아키텍처

## 공통 원칙
- 이 문서는 확정 PRD를 구현하기 위한 **설계**다. 요구사항 충돌 시 기획 절 우선, 모호한 점은 작업 전에 명시한다.
- 승인된 기능(F1~F6) 외로 사용자의 명시적 승인 없이 기능을 확장하지 않는다.
- 비밀키를 로그·프론트·Git에 포함하지 않는다. 검증하지 않은 결과를 검증 완료라고 쓰지 않는다.

## 시스템 흐름
```
Browser ─ Next.js (App Router, client: TanStack Query + Zustand)
            │ /api/* → next.config rewrites (동일 출처: 쿠키 1st-party, CORS 불필요)
            ▼
        FastAPI
          routers : auth, profile, library, recommendations, deals, dashboard, news
          clients : steam_web_api(키), store_api(비문서화: appdetails·featuredcategories), charts_api
          services: metadata, price, recommender(순수 함수), deal_recommender(순수 함수),
                    dashboard, news_cleaner, qa(LLM 인터페이스), session(서명 쿠키)
          jobs    : collector — 주기 수집(차트·할인 목록 → 메타·가격 보강)
          infra   : store 공용 레이트리미터, 인메모리 TTL 캐시
            ▼
        PostgreSQL: game_metadata, game_price, chart_snapshot, chart_entry (공개 데이터만)
        Memory   : 뉴스·청크·임베딩, OpenID nonce
```
- 인메모리 상태 때문에 백엔드는 **단일 인스턴스 전제**.
- 수집 작업: FastAPI lifespan의 asyncio 주기 태스크(기본 6시간, 임시) + `pg_try_advisory_lock` 중복 실행 방지 + 수동 실행 CLI `python -m app.jobs.collect`.

## 외부 데이터 소스
| 용도 | 엔드포인트 | 상태 |
|---|---|---|
| Vanity 해석 / 보유 게임 | ResolveVanityURL / GetOwnedGames | 공식 |
| 동시 접속자 | ISteamUserStats/GetNumberOfCurrentPlayers | 공식 |
| 뉴스 | GetNewsForApp | 공식 |
| 로그인 | steamcommunity.com/openid (OpenID 2.0) | 공식 |
| 위시리스트 | IWishlistService/GetWishlist/v1 | 비문서화(커뮤니티 문서만), 공개 위시리스트만 |
| 장르·DLC·가격 | store appdetails | 비문서화 |
| 할인·인기·신작 목록 | store /api/featuredcategories | 비문서화, 스키마 변경 가능 |
| 주간 최다 플레이 | ISteamChartsService/GetMostPlayedGames | 공개 접근 불확실 — 구현 전 스파이크로 확인 |

모든 소스는 어댑터로 분리하고 응답을 Pydantic으로 검증한다. 구조 변경 시 TEMPORARY_ERROR + 경고 로그. 사용 불가로 확인된 소스는 해당 대시보드 섹션을 비표시한다.

### 1. 라이브러리 및 추천
1. 사용자가 Steam 프로필 URL·Vanity ID·SteamID64를 입력하거나 로그인한다. URL 형식을 검증하고 필요한 경우 ResolveVanityURL을 호출한다.
2. GetOwnedGames가 반환한 공개 보유 게임·플레이 시간 사용. 비공개 상태는 친절한 설정 안내와 함께 실패 처리.
3. appid별 캐시 일괄 조회 후 누락·만료 게임만 제한된 동시성으로 appdetails 조회. 오래된 PENDING은 재시도 대상.
4. 커버리지 = success / (total − notAvailable). 진행 중·일시 실패 수량도 명시. 기준 미달 시 PLAYTIME_BASED, 충족 시 GENRE_AWARE.
5. 추천 결과에 `metadataSnapshotAt`, `metadataCoverage`, `recommendationMode`, `calculatedAt`, 항목별 `reasons` 포함. 동점은 appid 오름차순.

### 2. 로그인
1. `/auth/steam/login` → Steam OpenID 리다이렉트(`return_to`=콜백, `realm`=사이트 출처).
2. 콜백에서 `check_authentication`으로 서명 재검증, `claimed_id`(`^https://steamcommunity.com/openid/id/(\d{17})$`)·`op_endpoint`·`return_to` 일치, nonce 재사용 차단.
3. `itsdangerous` 서명 쿠키 발급(`HttpOnly`, 운영 `Secure`, `SameSite=Lax`, 만료 7일 임시).

### 3. 할인·대시보드
1. collector가 featuredcategories·차트 스냅샷을 저장하고, 포함된 appid의 메타데이터·가격을 보강한다.
2. 미보유 할인 추천 후보 = 최신 스냅샷 풀 − 보유 게임, `discount_percent > 0`.
3. 대시보드는 소스별 `snapshotAt`과 이전 스냅샷 대비 순위 변화를 표시한다.

### 4. 업데이트 AI
1. 게임별 뉴스 API를 요청 시 호출, 컨텐츠 BBCode/HTML 정제 및 태그·URL 검증.
2. 총 입력 토큰에 따라 Full Context 또는 In-Memory RAG 중 사전 실험으로 정한 모드를 사용. 토큰 초과 시 안전하게 검색 모드로 전환.
3. 질문 범위/날짜 필터 적용, 근거 없는 경우 답변 불가 알림, 원문 링크 출력.
4. 뉴스 전문·임베딩은 영구 DB에 적재하지 않음. 요청·임시 TTL 캐시 사용 후 만료 삭제. TTL은 법적 이용 허가를 대신하지 않음.

## 프론트엔드 상태 관리
- **TanStack Query**: 서버 데이터 전부(`['me']`, `['library',id]`, `['recs',id,opts]`, `['deals',id,cc]`, `['dashboard',cc,id?]`, `['news',appid]`, `useMutation(ask)`). coverage < 100%면 `refetchInterval` 폴링.
- **Zustand**: 전역 클라이언트 상태(`steamId`, `recOptions`, `excludedAppids`(persist), `selectedAppid`, `cc`). 서버 데이터를 복제하지 않는다. 클라이언트 컴포넌트에서만 사용.
- 화면: `/` 대시보드 + 입력·로그인 → `/u/[steamId]` 분석·추천·할인 → `/u/[steamId]/news/[appid]`.

---

# 데이터 모델

## 공통 원칙
- 스키마 변경은 Alembic 마이그레이션으로만 수행한다.
- PostgreSQL에는 공개 게임 데이터와 공개 집계 데이터만 저장한다.

## PostgreSQL
- `game_metadata(appid PK, name, genres_json, categories_json, dlc_appids_json, fetch_status ENUM, fetched_at, expires_at, last_checked_at, retry_after, failure_reason)`
- `game_price((appid, cc) PK, currency, initial_price, final_price, discount_percent, is_free, fetch_status ENUM, fetched_at, expires_at, retry_after, failure_reason)` — TTL 기본 1시간(임시)
- `chart_snapshot(id PK, source ENUM(MOST_PLAYED|TOP_SELLERS|SPECIALS|NEW_RELEASES), cc, captured_at, status, failure_reason)`
- `chart_entry((snapshot_id FK, rank) PK, appid, metric_value NULL)` + appid 인덱스. 12주(임시) 후 삭제.

상태 전이(fetch_status 공통):
| 상황 | 결과 |
|---|---|
| 정상 응답 | SUCCESS |
| 재확인으로 확정된 부재 | NOT_AVAILABLE (만료 후 재검사) |
| 429·5xx·타임아웃·스키마 불일치 | TEMPORARY_ERROR (`retry_after` 후 재시도, NOT_AVAILABLE 전환 금지) |
| 오래된 PENDING(서버 재시작 등) | 재시도 대상 |

`metadataSnapshotAt`: 추천 계산에 사용된 SUCCESS 행의 max(fetched_at). snapshotVersion은 사용하지 않는다.

## 비영속 데이터
- Steam 개인 라이브러리·위시리스트: 요청 단위 조회, 별도 동의 없이 장기 보관하지 않음.
- 뉴스 원문/청크/임베딩: 프로세스 메모리 또는 단기 TTL 메모리 캐시만 사용. 원문 전체를 로깅하지 않음.
- 추천 제외 목록: 클라이언트(Zustand persist)에만 저장.
- 평가용 합성 패치 데이터: 별도 `tests/fixtures`에 두고 운영 데이터와 혼합 금지.

---

# API 명세

프론트는 `/api` 프리픽스로 호출하고 Next.js rewrites가 FastAPI로 전달한다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/auth/steam/login` | Steam OpenID 리다이렉트 |
| GET | `/auth/steam/callback` | 서명 검증 후 쿠키 발급 |
| GET | `/auth/me` | `{steamId}` 또는 401 |
| POST | `/auth/logout` | 쿠키 삭제 |
| GET | `/steam/profile/resolve?input=` | URL/Vanity/SteamID64 → `{steamId}` |
| GET | `/steam/library/{steamId}` | 공개 게임·플레이시간·장르 분포·`metadataCoverage` |
| GET | `/steam/recommendations/{steamId}?preferUnplayed=&exclude=` | 보유 게임 TOP3 + reasons + 모드·스냅샷 |
| GET | `/steam/deals/{steamId}?cc=kr` | `wishlistDeals`, `dlcDeals`, `storeDeals`, `candidatePoolSize`, `priceSnapshotAt` |
| GET | `/steam/dashboard?cc=kr&steamId=` | 섹션별 `{source, snapshotAt, entries[]}`, 장르 분포 |
| GET | `/steam/news/{appid}` | 뉴스 목록·원문 링크 |
| POST | `/steam/news/ask` | `{appid, question, dateRange?}` → 답변·근거·출처·모드 |

추천 응답 예:
```json
{
  "recommendations": [
    {"appid": 1, "name": "...", "score": 0.82,
     "reasons": [{"factor": "GENRE_MATCH", "detail": "RPG", "contribution": 0.48},
                 {"factor": "UNPLAYED", "contribution": 0.30},
                 {"factor": "RECENT_GENRE", "contribution": 0.04}]}
  ],
  "metadataCoverage": {"success": 83, "pending": 10, "temporaryError": 3, "notAvailable": 4, "total": 100, "ratio": 0.865},
  "recommendationMode": "GENRE_AWARE",
  "metadataSnapshotAt": "2026-11-03T00:00:00Z",
  "calculatedAt": "..."
}
```
- `contribution` 합 = `score`. 이유 문구는 요소로 생성하며 LLM을 사용하지 않는다.
- 할인 항목: `{appid, name, initialPrice, finalPrice, discountPercent, currency, storeUrl, affinity, source: "WISHLIST"|"DLC"|"STORE", baseAppid?, score?, reasons?}`
- 대시보드 항목: `{rank, appid, name, rankDelta, genres, owned?, wishlisted?, affinity?}`
- 뉴스 답변은 출처 링크와 사용한 날짜 범위 포함, 사실 없으면 추측 금지.

오류 응답: `{"error": {"code": "...", "message": "..."}}`
| 코드 | 의미 |
|---|---|
| INVALID_INPUT | 입력 형식 오류 |
| PROFILE_NOT_FOUND | Vanity/ID 해석 실패 |
| LIBRARY_PRIVATE | 라이브러리 비공개 |
| WISHLIST_PRIVATE | 위시리스트 비공개 |
| STEAM_RATE_LIMITED | Steam 429 |
| STEAM_UNAVAILABLE | Steam 5xx·응답 구조 이상 |
| STEAM_TIMEOUT | Steam 타임아웃 |
| INSUFFICIENT_DATA | 추천에 필요한 데이터 부족 |
| DATA_NOT_READY | 수집 데이터 없음(최초 수집 전) |
| UNAUTHENTICATED | 로그인 필요 |
| AUTH_FAILED | OpenID 검증 실패 |
| FEATURE_DISABLED | 기능 플래그 OFF |

---

# 점수 설계 (초안 — 해당 단계 착수 시 확정)

- **장르 선호도**: 장르별 `Σ log1p(playtime_min)`, 합 1 정규화 (F3·F4·F5 공용)
- **보유 게임 추천(F3)**: 후보 = 플레이시간 < 120분(임시)
  - GENRE_AWARE: `0.6·genreMatch + 0.3·unplayed + 0.1·recentGenre`
  - PLAYTIME_BASED: 장르 요소 제외, 이유에 "장르 정보 부족" 명시
- **미보유 할인 추천(F4ⓒ)**: `0.5·genreMatch + 0.3·discountNorm + 0.2·popularity` (popularity = 풀 내 최고 순위 역수). reasons: `GENRE_MATCH`, `DISCOUNT`, `POPULAR`, `WISHLISTED`
- **위시리스트·DLC 할인 정렬**: affinity desc → 할인율 desc → appid. DLC 보유 여부는 확인 불가 시 "미확인" 표시.
- 동점은 appid 오름차순.

---

# Full Context vs RAG 실험 설계

## 질문
어느 입력 토큰 범위부터 검색형 RAG가 정확도·지연·비용 면에서 유리한가?

## 데이터 준비
- 권리 문제 없는 **합성 패치노트**를 생성하되 실험 데이터 생성 시 난수 seed, 버전, 주요 사실을 고정한다.
- 약 2k/8k/32k 토큰 구간. 100k는 모델 컨텍스트·비용 여유 시 선택적 확장. 뉴스 건수는 보조 통계.
- 긴 변경 로그·중복 제목·버전별 상충 사실·복수 문서 근거가 필요한 질문을 포함한다.
- 예상 정답과 근거 문서 ID를 별도 검증하여 30개 이상의 평가 질의로 고정한다.

## 대조 실험
- A: 모든 문서를 입력 컨텍스트에 제공.
- B: 청킹→임베딩→In-Memory Vector Top-K→답변.
- C: Hybrid 검색은 2차 실험으로 제한. 동일 모델/온도/질문·데이터·환경에서 비교.
- 기록: 정답 정확도(수동 확인 표본), 근거 충실도, 근거 검색 Recall@K, 토큰, p50/p95 지연, API 비용 추정.
- 결과에 *실험용 합성 데이터 기준*임을 명시. 실제 Steam 뉴스로 일반화하지 않는다.
- 운영 임계값은 실험 후 설정으로 확정하며 지금 숫자를 임의로 확정하지 않는다.
- LLM·임베딩 제공자는 이 단계 착수 전에 결정한다.

---

# 기술 선정

| 용도 | 선택 | 도입 시점 |
|---|---|---|
| FE 서버 데이터 / 전역 상태 | `@tanstack/react-query`, `zustand` | 1단계 |
| FE↔BE 타입 동기화 | `openapi-typescript`(dev) | 1단계 |
| Steam HTTP / 테스트 모킹 | `httpx` / `httpx.MockTransport` | 설치됨 |
| 레이트리미터·동시성 | 직접 구현(asyncio 토큰버킷 + Semaphore) | 3단계 |
| 메모리 TTL 캐시 | `cachetools` | 3단계 |
| 쿠키 서명 | `itsdangerous` | 5단계 |
| OpenID 2.0 | 직접 구현(httpx) | 5단계 |
| 주기 작업 | asyncio 태스크 + advisory lock | 6단계 |
| BBCode/HTML 정제 | stdlib `html.parser` (한계 시 `beautifulsoup4`) | 8단계 |
| 벡터 검색 | `numpy` | 9단계 |
| LLM·임베딩·토크나이저 | 제공자 결정 후 공식 SDK | 9단계 |
| 대시보드 그래프 | 표 우선, 필요 시 `recharts` | 보류 |
| E2E | `@playwright/test` | 11단계 |

위 목록 외 라이브러리는 사용자 승인 후 추가한다. 버전·호환성은 설치 시 확인한다.

---

# 구현 단계 및 완료 기준

각 단계 = 백엔드 + 해당 화면 + 테스트.

| 단계 | 범위 | 완료 조건 |
|---|---|---|
| 0 | PRD 반영, Claude Code hooks | 문서 갱신, 가드레일 동작 |
| 1 | 실행 환경(설정·DB 지연 생성·오류 핸들러·로그 마스킹·pytest), CI, FE Query/Zustand·rewrites | BE 기동·`/health/db`·pytest·FE lint/tsc·CI 통과 |
| 2 | SteamID/URL 파서 + 공개 라이브러리 API, FE 입력·목록 | 공개 조회, 비공개 `LIBRARY_PRIVATE` |
| 3 | game_metadata 캐시, 레이트리미터·제한 동시 요청, 상태 전이, 부분 응답, FE coverage 폴링 | 429가 NOT_AVAILABLE이 되지 않음, migration up/down |
| 4 | 보유 게임 추천 + 이유, metadataSnapshotAt 재현성 | TOP3·이유·모드·스냅샷 |
| 5 | Steam 로그인 | 위조 서명·nonce 재사용·만료 쿠키 거부 |
| 6 | 소스 스파이크 → 차트 스냅샷·collector·대시보드 | 소스별 snapshotAt, 실패 소스 섹션 비표시 |
| 7 | game_price, 위시리스트·DLC·미보유 할인 추천 | 3종 할인 목록, 후보 풀 크기, `DATA_NOT_READY` |
| 8 | 뉴스 조회·BBCode/HTML 정제·원문 URL 보존 | 목록·원문 링크 (**R1 완료**) |
| 9 | 합성 평가 데이터로 Full Context·RAG 구현 및 토큰 축 실험 | 실험 리포트, 임계값 제안 |
| 10 | `/news/ask`: TTL 메모리·출처 인용·LLM 실패 대응·기능 플래그 | 근거·출처 답변 (**R2 완료**) |
| 11 | 전체 E2E·API 제한·배포(Dockerfile·compose·운영 설정, 배포 대상 결정) | DoD 충족, 미검증 항목 문서화 |

### Definition of Done
대시보드 표시 → SteamID/프로필 URL 또는 로그인 → 게임 분석 → 보유 게임 추천(이유 포함) → 할인 정보 → 뉴스 표시 성공. 권리 충족 시 질문→근거 응답. 캐시 실패 시 부분 결과, 통신 실패 시 오류 안내. 실제 테스트 결과와 미검증 항목을 기록.
