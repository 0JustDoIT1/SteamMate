# SteamMate — 제품 요구사항 및 통합 설계

> 통합 PRD v5.2에서 해당 프로젝트 요구사항을 분리하고 기존 상세 설계 초안을 병합한 문서. 변경 제안은 승인 전 문서에 직접 반영하지 않는다.
>
> **v6 (2026-11-03, 사용자 승인)**: Steam 로그인, 할인(위시리스트·DLC·미보유 게임 추천), 인기 대시보드, 점수 기반 추천 이유 추가. API 경로·응답 형식·데이터 모델·오류 코드 통일. 릴리스를 R1/R2로 분할.
>
> **v6.1 (2026-11-03, 사용자 승인)**: 로그인 필수 — 개인 데이터는 로그인한 본인 것만 조회(SteamID·URL 직접 입력 제거, `/me/*` API). 구현 순서를 로그인 → 대시보드 → 기능으로 재배치.
>
> **v6.2 (2026-11-03, 사용자 승인)**: F3 점수 확정(미플레이 우선 가중치, 장르 수집 중 임시 추천은 미플레이 제외). F3·F4ⓒ를 "내 취향 추천" 한 영역의 탭으로 표시. F4ⓒ를 정가 게임까지 확대(할인 중만 보기 필터).
>
> **v6.3 (2026-11-03, 사용자 승인)**: F4 확정 — 미보유 추천 API 분리(`/me/store-recommendations`), 점수 `0.7·장르 + 0.3·인기`(할인은 점수 미반영), 후보 = 최신 목록 + 최근 4주 판매 순위, DLC 할인은 2시간 이상 플레이한 게임만(게임당 3개). 가격은 100개 묶음 조회. F3 미플레이 우선 옵션 삭제(미플레이 게임은 항상 후보).
>
> **v6.4 (2026-11-03, 사용자 승인)**: F6 R1 확정 — 공식 공지 피드만, 화면은 제목·발췌(200자)·원문 링크(전문 표시 보류), 링크만 있는 공지는 외부 원문 주소로 연결, 진입점은 보유 게임 목록.
>
> **v6.5 (2026-11-03, 사용자 승인)**: 7단계 LLM·임베딩을 로컬 무료 모델로 결정 — Ollama + `bonsai-2:9b`(주 모델), `qwen3:4b`(32k까지 비교군), 임베딩 `bge-m3`. RTX 3080 12GB에서 100k까지 GPU 처리 확인되어 100k를 정식 실험 축에 포함.
>
> **v6.6 (2026-11-04, 사용자 승인)**: 7단계 실험 결과로 F6 모드 임계값 확정 — 정제 후 코퍼스 약 8k 토큰 이하는 Full Context, 초과는 RAG(주 모델 `bonsai-2:9b`, 실험용 합성 데이터 기준). 비교군 `qwen3:4b`는 Thinking 모델이라 출력 한도 안에서 답을 내지 못해 비교 불가로 기록.
>
> **v6.7 (2026-11-04, 사용자 승인)**: F6 R2 설계 확정 — 서비스 LLM은 로컬 Ollama `bonsai-2:9b`(+`bge-m3`), 질문 대상은 항상 공식 공지 최근 50건(기간 지정 없음), "최신 업데이트" = 제목에 버전·업데이트·패치가 들어간 가장 최근 공지, `/steam/news/ask` 응답 형식 확정, 질문 유형별 답변 틀(지시문 v5: 업데이트 요약·값·일정·기타, JSON 칸), 뉴스 목록에 `askEnabled`, 오류 코드 `AI_UNAVAILABLE` 추가. Ollama는 배포 대상이 아니며 배포 환경은 기능 OFF(서버는 Ollama 없이 기동).
>
> **v6.8 (2026-11-05, 사용자 승인)**: Steam 공지 종류(24개 게임 조사)에 맞춰 F6 답변 틀을 5종으로 개편 — 패치 요약에 규모·빌드(서버가 제목으로 판정), 일정은 최대 3건·종류·상태(서버가 한국 날짜로 판정), 신규 콘텐츠·DLC 틀 추가, 판별 순서 변경. "최신 업데이트"에서 상점·드롭·굿즈 글 제외, 테스트 빌드는 정식 빌드가 없을 때만. 일정·신규 콘텐츠 질문은 지시문에 오늘 날짜를 주고 RAG에 최근 공지 5건의 청크를 더 넣으며(실제 공지 확인에서 옛 이벤트·DLC를 고르던 문제), 지금·앞으로를 물었는데 끝난 일정만 찾으면 그렇다고 안내.
>
> **v6.9 (2026-11-06, 사용자 승인)**: 값 질문을 "변경 기록 추출 + 서버 계산"으로 — 모델은 문서의 변경 기록(문서·버전·이전·이후 값)만 옮기고, 지금 값·특정 버전 값·횟수·차이·바뀐 버전 목록은 서버가 질문 단어로 정해 계산(합성 실험 latest 62%·multi 12%의 원인인 날짜 비교·세기·계산을 모델에서 뺌).
>
> **v6.10 (2026-11-06, 사용자 승인)**: 업데이트 요약·신규 콘텐츠의 목록 항목 중 영어 원문 그대로 나온 줄만 같은 모델로 한 번 더 번역(이름·숫자는 원문 유지). 서버가 원문의 대문자 이름과 숫자가 번역에 그대로 있는지 확인하고, 아니면 그 줄은 원문을 보인다. 답을 만드는 지시문은 그대로(재실험 불필요).
>
> **v6.11 (2026-11-06, 사용자 승인 → 시험 후 되돌림)**: 값 질문만 RAG 검색 조각을 5개 → 10개로 늘려 시험했다(v8 재실험). RAG 전체 92/81/75/61% → 89/83/69/64%, multi 일부 상승·latest 하락(옛 공지 조각이 늘어 최신 기록을 놓침), 입력 토큰 약 2배 → 승인 조건(좋아지지 않으면 되돌림)대로 **조각 5개 유지**.
>
> **v6.12 (2026-11-06, 사용자 승인)**: 값 질문 RAG에 "이름 검색"을 더한다 — 질문 속 영문 이름(예: Void Pistol)이 글자 그대로 든 조각을 최근 문서부터 최대 6개(의미 검색 5개와 별도, 7단계 설계의 C 선택적 Hybrid). 이름이 한 줄만 나온 옛 패치 조각을 의미 검색이 밀어내 여러 공지의 변경 기록을 놓치던 문제. 이름이 없으면(한국어만) 지금과 같다. 재실험으로 효과를 확인하고 좋아지지 않으면 되돌린다.
>
> **v6.13 (2026-11-06, 사용자 승인)**: 값 질문의 변경 기록에 속성 이름(attribute, 공지 원문 예: Knockback)을 받아 화면에 함께 보이고, 질문의 속성(한국어)과 공지 쪽 이름을 잇는 서버 대응표로 다른 속성의 기록을 버린다(사거리를 물었는데 Knockback 값을 답하던 문제). 표에 없는 말이거나 속성을 적지 않은 기록은 거르지 않는다. 한 칸에 "300 to 400"처럼 온 값은 서버가 이전·이후로 나눈다.
>
> **v6.14 (2026-11-06, 사용자 승인)**: 화면 개편 — 어두운 남색·보라 강조 디자인, 아이콘 `lucide-react`(사용자 선택). 내 라이브러리의 탭을 사이드바 메뉴별 페이지로 분리(`/me`, `/me/store`, `/me/deals`, `/me/genres`, `/news`), 로그인 전에는 로그인이 필요한 메뉴를 숨긴다. 위쪽 바에 내 Steam 닉네임·프로필 사진(`GET /me/profile`, 공개 프로필 요약, 메모리 10분).
>
> **v6.15 (2026-11-06, 사용자 승인)**: ① AI 질문 미리 준비 — 질문 칸을 누르거나 질문 버튼에 마우스를 올리면 `POST /steam/news/{appid}/ask/warmup`으로 공지 수집과(필요하면) 검색 색인을 백그라운드로 준비(첫 질문 대기 단축, 페이지만 열어서는 시작하지 않음, 중복 준비 없음, 기능 OFF면 403). ② 내 게임 소식 — `GET /me/news-feed`: 최근 플레이한 보유 게임 10개의 최신 공지를 게임당 3개씩 모아 날짜순 20개, 패치 꼴 제목은 규모 표시. `/news` 맨 위에 둔다.
>
> **v6.16 (2026-11-06, 사용자 승인)**: "거의 다 깬 게임" — `GET /me/achievements`: 한 번이라도 실행한 보유 게임 전부(안전 상한 500개)의 Steam 업적 달성률로(사용자 요청으로 '플레이 상위 30개'에서 변경), 60% 이상 100% 미만을 달성률 순 5개(남은 업적 이름 최대 3개, 한국어) + 완료한 게임 수 + 업적 비공개 안내. 업적 없는 게임·오류는 건너뜀, 저장하지 않고 메모리 6시간. `/me`에 "마무리해 볼 게임" 칸.
>
> **v6.17 (2026-11-06, 사용자 승인)**: 마무리해 볼 게임의 남은 업적에 아이콘 — 업적 이름을 받던 GetSchemaForGame 응답의 미달성(회색) 아이콘 주소를 함께 내보낸다(추가 Steam 호출 없음, 이미지는 브라우저가 Steam CDN에서 직접). 숨겨진 업적(hidden)은 Steam처럼 이름을 감추고 "숨겨진 업적"으로 표시한다(서버가 이름·아이콘을 보내지 않음). 응답 `remaining[]` → `remaining[{name?, icon?, hidden}]`.
>
> **v6.18 (2026-11-07, 사용자 승인)**: 본문이 외부 링크뿐인 공지(PUBG·블루 아카이브는 패치 노트·점검 공지 대부분)를 AI 질문 근거에서 빼지 않고 "제목만 있는 공지"로 넣는다(제목의 날짜·종류로 일정 질문에 답함). 이런 공지는 엄격한 패치 제목일 때만 "최신 업데이트" 후보(개발자 편지·로드맵 소식 제외). 최신 업데이트가 제목만 있는 공지면 모델을 부르지 않고 "본문이 외부 사이트에 있어 요약할 수 없음" + 원문 링크로 답한다(요약을 지어내지 않게). 출처에 외부 원문 주소 `externalUrl?`, 화면은 원문 사이트 표시와 "제목만 보고 답함" 안내. 외부 페이지는 가져오지 않는다(이용 허가 없음).
>
> **v6.19 (2026-11-07, 사용자 승인)**: 일정 질문 다듬기 — ① "진행 중인 이벤트 있어?"처럼 "언제" 없이 이벤트·진행 중·예정만 물어도 일정 유형. ② 상점·드롭·굿즈를 묻지 않은 일정 답에서 상점 개편 글("November Store Update")을 뺀다. ③ 종료일 없이 시작일만 있는 이벤트는 시작 60일이 지나면 종료(작년 이벤트가 "알 수 없음"으로 나오던 문제). ④ 일정·콘텐츠 질문의 최근 공지 5건에서 핫픽스도 뺀다(최근 글이 모두 핫픽스면 이벤트 공지가 밀려남). 실험 판별은 36문제 모두 그대로, ④로 바뀌는 4개 기록만 다시 재서 `results/prompt_v11/`(정확도 동일).
>
> **v6.20 (2026-11-08, 사용자 승인)**: 본문에 날짜가 없는 "지금 시작" 공지(DST "Hallowed Nights Returns!")를 일정 답에 넣는다 — AI 지시문이 아니라 서버가 제목 규칙으로 정한다(지시문 시도는 없는 점검 날짜를 지어내 되돌림). 일정 질문 중 지금·다음·최근처럼 현재를 묻는 질문에서만, 최근 공지 5건(상점·핫픽스 제외) 가운데 제목이 Returns·Has Arrived·Is Live·Out Now 등 "이미 시작"이고 앞으로의 일(Coming·날짜)이 아니며 모델이 쓰지 않은 글을 시작일 = 게시일(한국 날짜)·종료일 없음으로 더한다. 업데이트·패치·버전이 든 제목과 Out Now는 출시, 나머지는 이벤트. 점검만 물으면 더하지 않고 이벤트·출시 중 하나만 물으면 그 종류만. 응답 `schedule.items[].fromPostDate`, 화면 "공지 게시일 기준, 종료일 미정". 지시문 그대로라 실험 무관.

---

# 기획 및 요구사항

> 원문: 통합 PRD v5.2 해당 프로젝트 절을 분리한 파일. 새 요구사항이 확정되면 문서와 테스트 계약을 함께 갱신한다.

# 01 | SteamMate AI

Steam 로그인한 사용자의 공개 라이브러리에서 플레이 패턴과 장르를 분석해 보유 게임 중 다음 게임을 추천하고, 취향에 맞는 할인 게임과 Steam 인기 동향을 보여주며, 선택한 게임의 공식 뉴스 내용을 기반으로 근거 있는 답변을 제공한다.

## MVP 사용자 흐름

대시보드(이번 주 인기·할인, 비로그인 열람 가능) → Steam 로그인 → 본인 공개 라이브러리 조회 → 부분 메타데이터를 포함한 분석 → 보유 게임 TOP 3 추천(이유 포함) → 할인 정보(위시리스트·DLC·미보유 추천) → 게임 뉴스 선택 → 업데이트 질문 → 근거와 원문 링크 확인

| # | 기능 | 범위와 완료 기준 |
| --- | --- | --- |
| F1 | Steam 로그인 | Steam OpenID 로그인 필수(개인 기능). 로그인은 본인 SteamID 확인용이며 비공개 라이브러리 접근 권한을 주지 않음. 다른 사용자의 SteamID·URL 조회 기능은 제공하지 않음 |
| F2 | 라이브러리 분석 | 본인 GetOwnedGames 실조회; 플레이 시간·장르 분포; 비공개 시 설정 안내(프로필 비공개/게임 세부정보 비공개 구분); 커버리지 n/m 노출 |
| F3 | 보유 게임 추천 | 보유 게임 중 TOP 3(미플레이·저플레이 게임이 후보), 점수 요소별 이유·모드·조회 기준 시각 포함 |
| F4 | 할인 | ⓐ 위시리스트 할인 ⓑ 보유 게임 DLC 할인 ⓒ 미보유 게임 추천(정가 포함, 할인 중만 보기 필터; 취향 점수, 후보 풀 크기 표시) |
| F5 | 인기 대시보드 | 이번 주 인기·최다 플레이·할인·신작, 순위 변화; 비로그인 열람 가능, 로그인 시 보유·위시리스트·취향 매칭 표시 |
| F6 | 업데이트 AI | GetNewsForApp 요청 시 획득 → BBCode/HTML 정제 → 작은 코퍼스는 Full Context, 큰 경우 임시 RAG → 원문 링크; 근거 부족 시 응답 제한 |

**접근 원칙**: 개인 데이터 API(`/me/*`)는 서버 세션의 steamId만 사용하며 클라이언트가 보낸 steamId를 받지 않는다. 대시보드와 게임 뉴스는 공개 데이터이므로 비로그인 열람을 허용한다.

**릴리스 분할**: R1 = F1~F5 + F6의 뉴스 목록·원문 링크 / R2 = F6 AI 질문. F6(Full Context vs RAG)은 핵심 기술 문제이므로 R2에서 반드시 수행한다.

**F4ⓒ 한계**: Steam 전체 게임·할인 목록을 제공하는 공식 API가 없다. 후보 풀은 Steam 할인·인기·신작 목록에 오른 게임으로 제한하고 응답에 후보 수를 표시한다. 상점 검색 HTML 스크래핑은 하지 않는다.

**`/me` 화면 구성**: 대시보드처럼 상단 탭으로 한 번에 한 섹션만 표시한다 — 보유 게임 추천(F3) / 구매 추천(F4ⓒ) / 할인(F4ⓐⓑ) / 장르 취향(F2) / 보유 게임 목록. API와 점수 계산은 섹션별로 분리하고, 가격을 조회하는 섹션은 처음 열 때 불러온다.

**제외**: 타인 SteamID 조회, 친구 비교, 알림, 사용자 계정 DB, 추천 이력 저장, Hybrid 검색(2차 실험).

## 데이터 소스 및 저장 정책

메타데이터 조회 상태 명세

fetch_status = PENDING | SUCCESS | TEMPORARY_ERROR | NOT_AVAILABLE; last_checked_at, retry_after, failure_reason을 보관한다. (game_metadata, game_price 공통)

NOT_AVAILABLE은 장르가 실제로 존재하지 않거나 대상이 상점 메타데이터를 제공하지 않음이 재확인으로 확정된 상태로만 지정한다. 네트워크 오류·429·5xx·응답 스키마 불일치는 TEMPORARY_ERROR로 처리한다.

| 데이터 | 처리 |
| --- | --- |
| 보유 게임·플레이 시간 | 로그인한 본인 SteamID만 조회. 개인 라이브러리 원본은 MVP 영구 저장하지 않음 |
| 위시리스트 | 본인 공개 위시리스트만 요청 시 조회(비문서화 IWishlistService). 영구 저장하지 않음 |
| 로그인 세션 | 서명 쿠키(steamId + 만료)만. 사용자 테이블 없음 |
| 게임 장르/카테고리/DLC | store appdetails를 appid 키로 PostgreSQL에 캐싱. 비문서화 엔드포인트의 이용 조건·실패·429·구조 변경에 대응 |
| 게임 가격 | appdetails `filters=price_overview`(다중 appid 허용, 100개씩 묶음)를 (appid, cc) 키로 단기 TTL 캐싱. 한 요청에서 받는 묶음 수를 제한하고 나머지는 PENDING으로 응답(화면 폴링이 이어 받음) |
| 인기·할인·신작 목록 | 주기 수집한 공개 집계 스냅샷을 일정 기간(기본 12주, 임시) 보관 후 삭제 |
| 뉴스 본문 | GetNewsForApp; 요청/짧은 세션에서만 전처리·임시 인덱싱. 원문 및 임베딩 영구 보관 금지(MVP). R1 화면·캐시에는 정리한 발췌만(메모리 TTL 10분) |
| 사용자 추천 | 요청 시 계산. metadataCoverage, recommendationMode, metadataSnapshotAt, calculatedAt 출력 |

## 추천 재현성 정책

metadataCoverage.ratio = SUCCESS / (SUCCESS + PENDING + TEMPORARY_ERROR) = success / (total − notAvailable). NOT_AVAILABLE는 유효 분석 대상에서 제외하고 notAvailable 건수를 별도로 표기한다. 영구 실패 판정은 HTTP 오류만으로 하지 않으며, 재확인 시점과 사유를 기록한다. 기존 임계값 90%는 임시 가정이다. 동일 입력·동일 메타데이터 행에서만 추천 재현성을 보장하며, 이를 순수 함수 테스트로 검증한다. 입력 스냅샷 해시는 MVP에서 제외한다.
장르 수집률이 임계값 미만이면 PLAYTIME_BASED, 이상이면 GENRE_AWARE로 표시한다.

## 기술 실험: Full Context vs RAG

| 항목 | 사양 |
| --- | --- |
| 주 실험 축 | 정제 후 입력 코퍼스 토큰 2k / 8k / 32k / 100k (토큰 수는 주 모델 토크나이저 기준, Ollama `prompt_eval_count`로 확인) |
| 보조 기록 | 뉴스 문서 수, 청크 수, 언어, 전체 텍스트 길이, 질문 난도 |
| 대조군 | A 전체 문서 투입 / B 임시 Vector Top-K / C 선택적 Hybrid |
| 평가 데이터 | 실존 뉴스 원문 장기 아카이브 대신 자체 생성한 가상 패치노트(예: 60~100건)·질문 30~50개·검증된 정답/근거 ID |
| 평가 방법 | 같은 모델·질문·온도(0)·seed·토큰 제한; 정확도, 근거충실도, 지연시간(첫 요청·캐시 재사용 구분), 입력/출력 토큰, GPU/CPU 분담, Recall@K. 로컬 모델이라 API 비용 대신 처리 시간으로 비교 |
| 보고 원칙 | 합성 평가 결과와 실제 Steam 뉴스에서의 기능 관측을 분리. 임계점은 측정 결과로만 선정 |

주요 주의: 평가용 합성 문서는 실제 Steam 패치노트의 길이·언어·형식 다양성을 가깝게 모사하되, 특정 제3자 문장을 복제하지 않는다. 100k 컨텍스트가 모델 한도를 넘으면 실행하지 않고 N/A로 표기한다.

## 출시 게이트

- Steam API 키와 세션 서명 비밀값은 서버에서만 관리한다.
- Steam 뉴스 본문의 공개 AI 처리·저장·임베딩 권리는 미확정. 권리 확인 전 공개 RAG는 이용 허락된 자료로 제한하며 Steam 뉴스는 목록·발췌(앞부분 200자)·원문 링크로 분리한다(전문 표시는 이용 약관 확인 후 재검토). 뉴스 AI 질문은 기능 플래그로 두고 **공개 배포 기본 OFF**.
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
          routers : auth, me(library·recommendations·deals), dashboard, news
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
- 수집 작업: FastAPI lifespan의 asyncio 주기 태스크(1시간마다 실행, 소스별 갱신 간격 — CONCURRENT 1시간, SPECIALS·NEW_RELEASES 6시간, 주간 차트 6시간이며 집계일이 같으면 저장 생략, 임시) + `pg_try_advisory_lock` 중복 실행 방지 + 수동 실행 CLI `python -m app.jobs.collect`.
- 보유 게임 목록은 DB에 저장하지 않고 프로세스 메모리에 steamId별 5분 TTL로만 캐시한다(라이브러리·대시보드·추천·할인 공용, Steam 호출 절감).

## 외부 데이터 소스
| 용도 | 엔드포인트 | 상태 |
|---|---|---|
| 로그인 | steamcommunity.com/openid (OpenID 2.0) | 공식 |
| 보유 게임 | IPlayerService/GetOwnedGames | 공식 |
| 공개 상태 판별 | ISteamUser/GetPlayerSummaries (`communityvisibilitystate`) | 공식 |
| 동시 접속자 | ISteamUserStats/GetNumberOfCurrentPlayers | 공식 |
| 뉴스 | GetNewsForApp | 공식 |
| 위시리스트 | IWishlistService/GetWishlist/v1 | 비문서화(커뮤니티 문서만), 공개 위시리스트만 |
| 장르·DLC·가격 | store appdetails | 비문서화 |
| 할인·신작 목록 | store /api/featuredcategories (`specials` 10, `new_releases` 30) | 비문서화, 스키마 변경 가능 |
| 주간 판매 순위(전 세계) | IStoreTopSellersService/GetWeeklyTopSellers (`input_json`, 최상위 `country_code` 생략 = 전 세계) | 비문서화, 키 불필요, `last_week_rank` 제공 (2026-11-03 확인) |
| 주간 최다 플레이 | ISteamChartsService/GetMostPlayedGames | 비문서화, 키 불필요, 100위·`last_week_rank` 제공 (2026-11-03 확인) |
| 현재 동시 접속 순위 | ISteamChartsService/GetGamesByConcurrentPlayers | 키 필요, 100위 (2026-11-03 확인) |

순위 기준 통일: 판매·최다 플레이·현재 접속 차트는 모두 **전 세계** 기준(최다 플레이·접속은 국가별 제공이 없음). 할인·신작은 순위가 아닌 상점 기획 목록이며 가격만 한국 상점(KRW) 기준으로 표시한다.

모든 소스는 어댑터로 분리하고 응답을 Pydantic으로 검증한다. 구조 변경 시 TEMPORARY_ERROR + 경고 로그. 사용 불가로 확인된 소스는 해당 대시보드 섹션을 비표시한다.

### 1. 로그인
1. `/auth/steam/login` → Steam OpenID 리다이렉트(`return_to`=`{PUBLIC_BASE_URL}/api/auth/steam/callback`, `realm`=`PUBLIC_BASE_URL`).
2. 콜백에서 `check_authentication`으로 서명 재검증, `claimed_id`(`^https://steamcommunity.com/openid/id/(\d{17})$`)·`op_endpoint`·`return_to` 일치, nonce 재사용 차단.
3. `itsdangerous` 서명 쿠키 발급(`HttpOnly`, 운영 `Secure`, `SameSite=Lax`, 만료 7일 임시). 서명 키는 `SESSION_SECRET`.
4. `/me/*`는 쿠키가 없거나 서명·만료 검증 실패 시 `UNAUTHENTICATED`.

### 2. 라이브러리 및 추천
1. 세션의 steamId로 GetOwnedGames(`include_appinfo=1`, `include_played_free_games=1`)를 호출한다.
2. 응답에 `games`가 없으면(HTTP 200 빈 `response`) GetPlayerSummaries로 판별한다: `players` 비어 있음 → `PROFILE_NOT_FOUND`, `communityvisibilitystate != 3` → 프로필 비공개, `== 3` → 게임 세부정보 비공개. 둘 다 `LIBRARY_PRIVATE`로 응답하되 안내 문구를 구분한다.
3. appid별 캐시 일괄 조회 후 누락·만료 게임만 제한된 동시성으로 appdetails 조회. 오래된 PENDING은 재시도 대상.
4. 커버리지 = success / (total − notAvailable). 진행 중·일시 실패 수량도 명시. 기준 미달 시 PLAYTIME_BASED, 충족 시 GENRE_AWARE.
5. 추천 결과에 `metadataSnapshotAt`, `metadataCoverage`, `recommendationMode`, `calculatedAt`, 항목별 `reasons` 포함. 동점은 appid 오름차순.
6. 후보가 0개면 오류 대신 빈 `recommendations`와 `candidateCount: 0`을 응답하고 화면에서 후보 조건을 안내한다.

### 3. 할인·대시보드
1. collector가 featuredcategories·차트 스냅샷을 저장하고, 포함된 appid의 메타데이터·가격을 보강한다(후보 풀 가격을 미리 받음).
2. 미보유 게임 추천 후보 = (소스별 최신 스냅샷 + 최근 4주 판매 순위) − 보유 게임(정가 포함), 게임으로 확인되고 장르가 있는 것. "할인 중만 보기" 필터 시 `discount_percent > 0`.
3. 위시리스트는 API 키 없이 조회한다(키 소유 계정의 비공개 우회 방지). 비공개와 빈 위시리스트는 응답이 같아(`{"response":{}}`) 함께 안내하고, 위시리스트 조회 실패는 할인·추천 전체를 실패시키지 않는다.
4. DLC 할인 대상 = 2시간 이상 플레이한 보유 게임의 DLC. 이름·이미지는 할인 중인 DLC만 조회한다.
5. 대시보드는 소스별 `snapshotAt`과 이전 스냅샷 대비 순위 변화를 표시한다. 로그인 상태면 세션 steamId로 개인화한다.

### 4. 업데이트 AI
1. 게임별 뉴스 API를 요청 시 호출, 컨텐츠 BBCode/HTML 정제 및 태그·URL 검증. 공식 공지 피드(`steam_community_announcements`)만 받고, `maxlength`는 쓰지 않는다(Steam이 서식을 지우며 문단을 붙임). 원문 링크는 appid·gid로 만든 상점 공지 주소, 본문이 외부 링크뿐인 공지는 그 주소(`externalUrl`)로 연결한다.
2. 총 입력 토큰에 따라 Full Context 또는 In-Memory RAG 중 사전 실험으로 정한 모드를 사용. 정제 후 코퍼스가 약 8k 토큰 이하면 Full Context, 초과하면 RAG(v6.6, 7단계 실험). 토큰 초과 시 안전하게 검색 모드로 전환. 8k는 `bonsai-2:9b` 기준이므로 서비스 LLM이 바뀌면 다시 확인한다.
3. 근거 없는 경우 답변 불가 알림, 원문 링크 출력. 대상은 항상 공식 공지 최근 50건이며 기간 지정은 두지 않는다(v6.7). "최신 업데이트"는 제목에 버전 번호(예: 1.4.5.7)나 업데이트·패치·핫픽스가 들어간 가장 최근 공지(없으면 가장 최근 글)로 본다. 제목에 상점(Store·Shop)·드롭(Drops)·굿즈(Merch·Plush·Figure 등) 단어가 든 글은 후보에서 빼고, 테스트 빌드(EXP·Experimental·PTB·Beta·Public Test)는 정식 빌드 후보가 없을 때만 고른다(v6.8). **일정·신규 콘텐츠 질문에만** 지시문에 오늘 날짜(한국)를 주고("다음·진행 중이면 오늘 이후·오늘 포함 일정을 먼저"), RAG에서 상점·굿즈 글을 뺀 최근 공지 5건(상점·굿즈·핫픽스 제외, v6.19)마다 질문과 가장 가까운 청크 1개를 더 넣는다(v6.8). RAG 검색 조각은 질문과 가까운 순으로 5개(값 질문 10개는 v6.11에서 시험 후 되돌림). 값 질문은 대상 영문 이름이 든 조각을 최근 문서부터 최대 6개 더 넣는다(v6.12). **업데이트 요약 질문에만** 프롬프트 제목에 "(최신 업데이트)"를 붙이고 RAG에서 그 공지의 청크를 질문과 가까운 순으로 3개 더 넣는다(의미 검색은 날짜를 보지 않아 옛 공지가 걸리는 문제 대응). 값 질문에는 넣지 않는다(그 공지에 값이 없으면 "근거 없음"으로 답하는 부작용, v4 재실험). 분량은 정제 후 글자 수로 어림해 모드를 고르고(약 3자 = 1토큰), 실제 입력 토큰은 응답에 기록한다.
4. 뉴스 전문·임베딩은 영구 DB에 적재하지 않음. 요청·임시 TTL 캐시 사용 후 만료 삭제. TTL은 법적 이용 허가를 대신하지 않음.
5. LLM(v6.7): 로컬 Ollama `bonsai-2:9b`, RAG 임베딩 `bge-m3`. **질문 유형별 답변 틀(지시문 v5)**: 서버가 질문 단어로 유형을 판별하고(값 → 일정 → 신규 콘텐츠 → 업데이트 요약 → 기타 순, v6.8), 모델은 유형별 JSON 칸만 채운다(Ollama `format`으로 구조 강제). 업데이트 요약 = 버전·날짜·새 기능·밸런스 조정·버그 수정(분야별 최대 2개, 구체적 이름·수치) + 규모(대형/패치/핫픽스)·빌드(정식/테스트)는 서버가 공지 제목으로 판정, 값 = 대상 + 변경 기록 최대 8건(문서 ID·속성 이름·버전·이전 값·이후 값; 질문의 속성과 다른 속성 기록은 서버 대응표로 버림(v6.13); 순서는 서버가 문서 날짜로, 넘기지 않은 문서의 기록은 버림, 빈 버전은 제목에서) → 서버가 계산 방식을 질문 단어로 정한다(v6.9): 기본 = 가장 늦은 기록의 이후 값, 질문에 버전 번호 = 그 버전 기록(없으면 근거 없음, 같은 버전의 정규 패치·핫픽스는 질문이 핫픽스를 말할 때만 핫픽스), "출시 당시·처음" = 첫 기록의 이전(없으면 이후) 값, "언제·몇 버전" = 마지막(추가를 물으면 첫) 기록의 버전, "몇 번·횟수" = 값이 바뀐 기록 수, "얼마나 늘/줄·차이" = 최신 값 − 처음 값의 크기(숫자를 못 읽으면 근거 없음), "바뀐 버전·버전을 모두" = 기록 버전 목록(날짜순), 일정 = 최대 3건(이름·종류(이벤트·시즌/출시/점검/테스트/할인)·시작·종료 YYYY-MM-DD) + 상태(진행 중/예정/종료/알 수 없음)는 서버가 한국 날짜(Asia/Seoul) 기준 날짜 단위로 판정해 진행 중·예정을 먼저 표시(시작일만 있으면 출시는 하루짜리, 이벤트 등은 시작 뒤 "알 수 없음", 단 시작한 지 60일이 넘으면 종료(v6.19)). 질문이 지금·앞으로(다음·진행·예정 등)를 묻는데 찾은 일정이 모두 종료면 "진행 중이거나 예정된 일정을 찾지 못함"을 알리고 끝난 일정은 흐리게 함께 보인다, 신규 콘텐츠·DLC = 이름·형태(무료 업데이트/DLC/확장)·출시일·핵심 내용 최대 3개 + 상태(서버 판정), 기타 = 자유 답(개발 일지·로드맵 포함). 칸 개수로 나열·뭉뚱그림을 막고 화면은 유형별로 같은 모양으로 그린다. 칸이 문서 번호뿐이면 그 공지 제목으로 바꾸고, JSON이 깨지면 다시 질문하라고 안내한다. 지시문을 바꿀 때마다 7단계 실험을 다시 돌려 임계값을 확인한다. 모델이 인용한 근거 ID 중 넘기지 않은 문서는 버린다. 요약·콘텐츠 목록에서 한글이 거의 없는 줄은 따로 한 번 더 번역하고(이름·숫자 유지 확인, 실패하면 원문, v6.10), 영어 줄이 없으면 추가 호출하지 않는다. GPU 1개 전제라 질문은 한 번에 하나씩 처리한다. 호출부는 인터페이스로 분리해 교체 가능하게 둔다(교체 시 임계값 재확인).
6. 배포: Ollama는 배포 대상이 아니다. 기능 플래그 `NEWS_AI_ENABLED`(기본 OFF)를 켠 환경에서만 질문 시점에 Ollama에 연결하며, 서버 기동은 Ollama 유무와 무관하다. 켜져 있는데 Ollama에 닿지 않으면 `AI_UNAVAILABLE`.

## 프론트엔드 상태 관리
- **TanStack Query**: 서버 데이터 전부(`['me']`(로그인 상태), `['library']`, `['recs',opts]`, `['deals',cc]`, `['dashboard',cc]`, `['news',appid]`, `useMutation(ask)`). coverage < 100%면 `refetchInterval` 폴링.
- **Zustand**: 전역 클라이언트 상태(`recOptions`, `excludedAppids`(persist), `selectedAppid`, `cc`). 로그인 상태·steamId를 포함한 서버 데이터를 복제하지 않는다. 클라이언트 컴포넌트에서만 사용.
- 화면(v6.14): 왼쪽 사이드바 메뉴마다 한 페이지 — `/` 인기 대시보드, `/me` 내 라이브러리(통계·보유 게임 추천·마무리해 볼 게임), `/me/store` 구매 추천, `/me/deals` 할인, `/me/genres` 장르 취향, `/news` 공식 뉴스(내 게임 소식 + 보유 게임 목록·검색·정렬) → `/news/[appid]` 뉴스·질문. 로그인 전에는 대시보드만 보이고 로그인 안내를 둔다. 위쪽 바에 내 Steam 닉네임·프로필 사진과 로그인·로그아웃.

---

# 데이터 모델

## 공통 원칙
- 스키마 변경은 Alembic 마이그레이션으로만 수행한다.
- PostgreSQL에는 공개 게임 데이터와 공개 집계 데이터만 저장한다.

## PostgreSQL
- `game_metadata(appid PK, name, app_type, header_image NULL, genres_json, categories_json, dlc_appids_json, fetch_status ENUM, fetched_at, expires_at, last_checked_at, retry_after, failure_reason)` — `app_type`은 Steam `type`(game·dlc·demo·music 등), 추천·대시보드에서 비게임 제외용. 게임 단위 공용 데이터이며 사용자 정보와 연결하지 않는다.
- `game_price((appid, cc) PK, currency, initial_price, final_price, discount_percent, is_free, fetch_status ENUM, fetched_at, expires_at, retry_after, failure_reason)` — TTL 기본 1시간(임시)
- `chart_snapshot(id PK, source ENUM(TOP_SELLERS|MOST_PLAYED|CONCURRENT|SPECIALS|NEW_RELEASES), cc, captured_at, period_start NULL, status, failure_reason)` — `period_start`는 Steam 주간 집계 기준일(주간 차트만).
- `chart_entry((snapshot_id FK, rank) PK, appid, name NULL, last_week_rank NULL, metric_value NULL, final_price NULL, original_price NULL, discount_percent NULL, currency NULL, image_url NULL)` + appid 인덱스. `metric_value`: TOP_SELLERS=연속 순위권 주 수, MOST_PLAYED=주간 최고 동시 접속, CONCURRENT=현재 동시 접속. 순위 변화는 Steam이 주는 `last_week_rank`로 계산한다. 보관: TOP_SELLERS는 기간 집계를 위해 53주(집계 주 기준), 그 외(MOST_PLAYED 포함)는 2주(임시). 소스별 최신 성공본은 보관 기간과 무관하게 유지.
- `header_image`: appdetails가 주는 정확한 헤더 이미지 **주소(URL)만** 저장(이미지 파일은 저장하지 않으며 브라우저가 Steam CDN에서 직접 받음). 대시보드는 이 값을 우선 사용하고, 없으면 추정 주소, 로딩 실패 시 대체 표시.

**대시보드 기간 집계(주/월/연)**: 판매 순위 섹션에만 주간·월간·연간 탭. 월간 = 최근 4주, 연간 = 최근 52주의 주간 순위를 합산(주마다 `101 − 순위`점, 같은 주는 최신 스냅샷 1개). Steam 공식 월간·연간 순위가 아님을 화면에 명시. 판매 순위는 과거 주차 조회가 가능해 52주를 백필한다. 최다 플레이는 Steam이 과거 기록을 제공하지 않아 주간만 표시한다(사용자 결정).

**메타데이터 보강 우선순위**: 사용자 요청(라이브러리·대시보드에 표시되는 게임)은 높은 우선순위, 수집 작업이 넣은 나머지는 낮은 우선순위로 처리한다.

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

프론트는 `/api` 프리픽스로 호출하고 Next.js rewrites가 FastAPI로 전달한다. `/me/*`는 로그인 필수이며 세션의 steamId만 사용한다.

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| GET | `/auth/steam/login` | — | Steam OpenID 리다이렉트 |
| GET | `/auth/steam/callback` | — | 서명 검증 후 쿠키 발급, `/me`로 리다이렉트 |
| GET | `/auth/me` | 선택 | `{steamId}` 또는 401 |
| POST | `/auth/logout` | — | 쿠키 삭제 |
| GET | `/me/profile` | 필수 | `{steamId, personaName?, avatarUrl?, profileUrl?}`(공개 프로필 요약, 메모리 10분, 사진·프로필 주소는 Steam 도메인 https만) |
| GET | `/me/news-feed` | 필수 | `{items[{appid, gameName, headerImage?, gid, title, publishedAt, url, externalUrl?, scale?(MAJOR·PATCH·HOTFIX)}], gameCount, failedCount, fetchedAt}`(최근 플레이 게임 10개 × 공지 3개, 날짜순 20개, 뉴스 발췌 캐시 공유, 일부 게임 실패 허용, v6.15) |
| GET | `/me/achievements` | 필수 | `{status(OK·PRIVATE), nearlyDone[{appid, name, headerImage?, achieved, total, remaining[{name?, icon?, hidden}]}], completedCount, checkedCount}`(실행한 보유 게임 전부·상한 500, 60~99%, 메모리 6시간, v6.16·v6.17 아이콘) |
| GET | `/me/library` | 필수 | 본인 공개 게임·플레이시간·장르 분포·`metadataCoverage` |
| GET | `/me/recommendations?exclude=` | 필수 | 보유 게임 TOP3 + reasons + 모드·스냅샷 |
| GET | `/me/store-recommendations?onSaleOnly=` | 필수 | 미보유 게임 TOP10 + reasons·가격·`wishlisted`, `candidatePoolSize`, `candidateCount`, `metadataPending`, `pricePending`, 모드, `poolSnapshotAt`, `priceSnapshotAt`. 수집 전 `DATA_NOT_READY` |
| GET | `/me/deals` | 필수 | `wishlistDeals`, `wishlistStatus`(OK·EMPTY_OR_PRIVATE·UNAVAILABLE), `dlcDeals`, `dlcBaseGameCount`, `dlcCheckedCount`, `pricePending`, `priceSnapshotAt` |
| GET | `/steam/dashboard?cc=kr` | 선택 | 섹션별 `{source, snapshotAt, entries[]}`, 장르 분포. 로그인 시 개인화 |
| GET | `/steam/news/{appid}?count=1~20&before=` | — | 공식 공지 `{appid, name, headerImage, items[{gid, title, author, publishedAt, excerpt, url, externalUrl}], nextBefore, askEnabled}`. 없는 게임 `NOT_FOUND` |
| POST | `/steam/news/ask` | — | `{appid, question(1~300자)}`(다른 항목은 거절) → `{answer(공용 문장), refused, intent(UPDATE_SUMMARY·VALUE·SCHEDULE·CONTENT·OTHER), summary{version, date, scale(MAJOR·PATCH·HOTFIX), build(STABLE·TEST), newFeatures[], balance[], bugFixes[]}?, value{target, kind(CURRENT·AT_VERSION·FIRST·WHEN·COUNT·DIFF·VERSIONS), value, changedIn, previous, history[{attribute, version, date, before, after}]}?, schedule{items[{name, kind(EVENT·RELEASE·MAINTENANCE·TEST·SALE), start, end, status(ONGOING·UPCOMING·ENDED·UNKNOWN), fromPostDate(v6.20)}], noCurrent}?, content{name, form(FREE_UPDATE·DLC·EXPANSION·OTHER), releaseDate, status, highlights[]}?, mode(FULL_CONTEXT·RAG), sources[{gid, title, publishedAt, url, externalUrl?(v6.18)}], dateRange{from, to}(사용한 글의 날짜 범위), latestUpdate{gid, title, publishedAt, url}?(업데이트 요약일 때), docCount, inputTokens, model, answeredAt}`. 플래그 OFF `FEATURE_DISABLED`, LLM 장애 `AI_UNAVAILABLE` |
| POST | `/steam/news/{appid}/ask/warmup` | — | `202 {status: STARTED·READY}` — 공지 수집·검색 색인을 백그라운드로 미리 준비(질문 칸 포커스 때, 중복 없음). 플래그 OFF `FEATURE_DISABLED` (v6.15) |

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
- 할인 항목: `{appid, name, headerImage, price: {currency, initialPrice, finalPrice, discountPercent}, affinity, storeUrl, baseAppid?, baseName?}` (DLC만 base*)
- 상점 기준 국가는 서버 설정(`store_cc`, 한국) 하나만 지원한다.
- 대시보드 항목: `{rank, appid, name, rankDelta, genres, owned?, wishlisted?, affinity?}`
- 뉴스 답변은 출처 링크와 사용한 날짜 범위 포함, 사실 없으면 추측 금지.

오류 응답: `{"error": {"code": "...", "message": "..."}}`
| 코드 | 의미 |
|---|---|
| INVALID_INPUT | 입력 형식 오류 |
| PROFILE_NOT_FOUND | 세션의 Steam 계정을 찾을 수 없음 |
| LIBRARY_PRIVATE | 라이브러리 비공개(프로필 비공개/게임 세부정보 비공개 안내 구분) |
| WISHLIST_PRIVATE | 위시리스트 비공개 |
| STEAM_RATE_LIMITED | Steam 429 |
| STEAM_UNAVAILABLE | Steam 5xx·응답 구조 이상 |
| STEAM_TIMEOUT | Steam 타임아웃 |
| INSUFFICIENT_DATA | 추천에 필요한 데이터 부족 |
| DATA_NOT_READY | 수집 데이터 없음(최초 수집 전) |
| UNAUTHENTICATED | 로그인 필요 |
| AUTH_FAILED | OpenID 검증 실패 |
| FEATURE_DISABLED | 기능 플래그 OFF |
| AI_UNAVAILABLE | 로컬 LLM(Ollama) 연결 실패·시간 초과·응답 이상 |
| NOT_FOUND | 존재하지 않는 경로 |
| INTERNAL_ERROR | 예상치 못한 서버 오류(내부 메시지 비노출) |

---

# 점수 설계 (F3·F4 확정)

- **장르 선호도**: 장르별 `Σ log1p(playtime_min)`, 합 1 정규화 (F3·F4·F5 공용, 라이브러리 장르 분포도 같은 값). 미플레이 게임은 기여하지 않는다.
- **보유 게임 추천(F3, 확정)**: 후보 = 플레이시간 < 120분(임시), 게임이 아닌 것으로 확인된 앱(DLC·데모 등)·사용자 제외 게임 제외
  - 요소: `unplayed = 1 − 분/120`, `genreMatch`·`recentGenre` = 게임 장르의 선호도 합(전체 / 최근 2주 플레이 기준), `recentlyPlayed` = 90일 안에 실행 시 1
  - GENRE_AWARE: `0.6·genreMatch + 0.3·unplayed + 0.1·recentGenre`
  - 미플레이 게임은 항상 후보에 포함한다(사용자 옵션 없음 — v6.2의 "미플레이 우선 가중치"는 v6.3에서 삭제)
  - PLAYTIME_BASED(장르 수집 중 임시 추천 "이어서 하기"): 미플레이(0분) 게임은 순서 근거가 없어 후보에서 제외, `0.7·unplayed + 0.3·recentlyPlayed`. 이유에 "장르 정보 수집 중" 명시
  - `contribution` 합 = `score`
- **미보유 게임 추천(F4ⓒ, 확정)**: 정가 게임 포함 `0.7·genreMatch + 0.3·popularity` (popularity = 풀 내 최고 순위 역수, 할인·신작 목록은 목록 내 위치). 할인은 점수에 넣지 않고 동점 정렬(할인율 desc)·표시·"할인 중만 보기" 필터에만 쓴다. 장르 수집 중(PLAYTIME_BASED)은 popularity만, 이유에 안내. reasons: `GENRE_MATCH`, `POPULAR`; 위시리스트 여부는 `wishlisted` 표시. 정렬: score desc → 할인율 desc → appid
- **위시리스트·DLC 할인 정렬**: affinity desc → 할인율 desc → appid. DLC affinity는 본 게임 장르 기준이라 같은 게임의 DLC가 동점이 되므로 본 게임당 최대 3개, 전체 최대 30개. DLC 보유 여부는 Steam이 제공하지 않아 "미확인" 표시.
- 동점은 appid 오름차순.

---

# Full Context vs RAG 실험 설계

## 질문
어느 입력 토큰 범위부터 검색형 RAG가 정확도·지연·비용 면에서 유리한가?

## 데이터 준비
- 권리 문제 없는 **합성 패치노트**를 생성하되 실험 데이터 생성 시 난수 seed, 버전, 주요 사실을 고정한다.
- 약 2k/8k/32k/100k 토큰 구간. 뉴스 건수는 보조 통계.
- 긴 변경 로그·중복 제목·버전별 상충 사실·복수 문서 근거가 필요한 질문을 포함한다.
- 예상 정답과 근거 문서 ID를 별도 검증하여 30개 이상의 평가 질의로 고정한다.

## 대조 실험
- A: 모든 문서를 입력 컨텍스트에 제공.
- B: 청킹→임베딩→In-Memory Vector Top-K→답변.
- C: Hybrid 검색은 2차 실험으로 제한. 동일 모델/온도/질문·데이터·환경에서 비교.
- 기록: 정답 정확도(수동 확인 표본), 근거 충실도, 근거 검색 Recall@K, 토큰, p50/p95 지연, API 비용 추정.
- 결과에 *실험용 합성 데이터 기준*임을 명시. 실제 Steam 뉴스로 일반화하지 않는다.
- 운영 임계값은 실험 후 설정으로 확정하며 지금 숫자를 임의로 확정하지 않는다.
- LLM·임베딩(v6.5 결정): 로컬 Ollama. 주 모델 `bonsai-2:9b`(2k~100k), 비교군 `qwen3:4b`(2k~32k — 100k는 RTX 3080에서 CPU로 넘쳐 질문당 약 5분이라 제외), 임베딩 `bge-m3`(다국어). 사전 측정(2026-11-03, 숨긴 사실 찾기): bonsai-2:9b 100k 6.8GB·100% GPU·질문당 약 36초, qwen3:4b 100k 18GB·CPU 44%. 데이터가 외부로 나가지 않아 뉴스 권리 제약과도 충돌하지 않는다. 서비스 단계(8단계)의 LLM은 이 실험 결과를 보고 다시 정한다.

## 결과 (v6.6, 2026-11-04 — 실험용 합성 데이터 기준)
- 데이터: 가상 게임 패치노트(중첩형 2k⊂8k⊂32k⊂100k, 100k = 110건), 질문 36개(단일 사실·최신 값·여러 문서 근거·제목 구분·답 없음). 코드·결과는 `backend/experiments/rag_eval/`, 상세 리포트 `results/report.md`.
- `bonsai-2:9b` 정확도 A(전체 투입) / B(Top-5): 2k 69%/75%, 8k 67%/69%, 32k 50%/67%, 100k 28%/64%. A 첫 요청 지연 p50 0.8 / 2.4 / 8.5 / 33.8초, 같은 코퍼스 연속 질문은 1초 안팎. B 질문당 약 0.6초, 색인 0.1~5.3초, Recall@5 0.98 → 0.66. 수동 확인 표본 40건 모두 자동 채점과 일치.
- **임계값**: 약 8k 토큰 이하 Full Context, 초과 RAG. 8k까지는 정확도 차이가 없고(36문제 중 1~2문제) 색인이 필요 없으며, 32k부터 A의 정확도·첫 요청 지연이 크게 나빠진다. 8k~32k는 측정하지 않아 보수적으로 8k에서 전환한다.
- 한계: 여러 글을 훑는 요약형 질문은 측정하지 않았다(작은 코퍼스에서 Full Context를 유지하는 이유). 여러 문서 근거 질문은 두 방식 모두 0~25%로 모델 한계. B의 정확도는 검색 Recall이 상한이다.
- `qwen3:4b`: Thinking 모델이라 `think: false`에도 추론을 이어 가 출력 한도(1024)에서 216건 중 119건이 잘리고 84건은 답이 없어 **비교 불가**. 결론은 주 모델로만 낸다.

---

# 기술 선정

| 용도 | 선택 | 도입 시점 |
|---|---|---|
| FE 서버 데이터 / 전역 상태 | `@tanstack/react-query`, `zustand` | 1단계 |
| FE↔BE 타입 동기화 | `openapi-typescript`(dev) | 1단계 |
| Steam HTTP / 테스트 모킹 | `httpx` / `httpx.MockTransport` | 설치됨 |
| 쿠키 서명 | `itsdangerous` | 2단계 |
| OpenID 2.0 | 직접 구현(httpx) | 2단계 |
| 레이트리미터·동시성 | 직접 구현(asyncio 토큰버킷 + Semaphore) | 3단계 |
| 메모리 TTL 캐시 | `cachetools` | 3단계 |
| 주기 작업 | asyncio 태스크 + advisory lock | 3단계 |
| BBCode/HTML 정제 | stdlib `html.parser` (한계 시 `beautifulsoup4`) | 6단계 |
| 벡터 검색 | `numpy` | 7단계 |
| LLM·임베딩·토크나이저 | Ollama 로컬 서버(REST, 기존 `httpx`로 호출 — 새 SDK 없음), 모델 `bonsai-2:9b`·`qwen3:4b`·`bge-m3`, 토큰 수는 Ollama 응답 값 사용 (사용자 승인) | 7단계 |
| 아이콘 | `lucide-react` 1.61.0(쓴 아이콘만 번들, 사용자 선택) | 9단계 이후 |
| 대시보드 그래프 | shadcn/ui Charts(`components/ui/chart.tsx` 수동 복사) + `recharts`·`react-is`, 유틸 `clsx`·`tailwind-merge` (사용자 선택, CLI 미사용) | 3b단계 |
| E2E | `@playwright/test` | 9단계 |

위 목록 외 라이브러리는 사용자 승인 후 추가한다. 버전·호환성은 설치 시 확인한다.

---

# 구현 단계 및 완료 기준

각 단계 = 백엔드 + 해당 화면 + 테스트. 순서: 로그인 → 대시보드 → 기능.

| 단계 | 범위 | 완료 조건 |
|---|---|---|
| 0 | PRD 반영, Claude Code hooks | 문서 갱신, 가드레일 동작 |
| 1 | 실행 환경(설정·DB 지연 생성·오류 핸들러·로그 마스킹·pytest), CI, FE Query/Zustand·rewrites | BE 기동·`/health/db`·pytest·FE lint/tsc·CI 통과 |
| 2 | Steam 로그인(OpenID·서명 쿠키·me/logout) + `/me/library` 기본 조회, FE 로그인 버튼·`/me` 게임 목록 | 로그인→내 게임 목록 표시, 비공개 `LIBRARY_PRIVATE`(사유 구분), 위조 서명·nonce 재사용·만료 쿠키 거부 |
| 3a | game_metadata 캐시, store 레이트리미터·제한 동시 요청, 상태 전이, 부분 응답 | 429가 NOT_AVAILABLE이 되지 않음, migration up/down |
| 3b | 소스 스파이크 → 차트 스냅샷·collector·대시보드 화면, 로그인 시 개인화 | 소스별 snapshotAt, 실패 소스 섹션 비표시 |
| 4 | 라이브러리 분석(장르 분포·coverage 폴링) + 보유 게임 추천·이유, metadataSnapshotAt 재현성 | TOP3·이유·모드·스냅샷 |
| 5 | game_price, 위시리스트·DLC 할인, 미보유 게임 추천(정가 포함), "내 취향 추천" 탭 화면 | 3종 목록, 후보 풀 크기, `DATA_NOT_READY` |
| 6 | 뉴스 조회·BBCode/HTML 정제·원문 URL 보존 | 목록·원문 링크 (**R1 완료**) |
| 7 | 합성 평가 데이터로 Full Context·RAG 구현 및 토큰 축 실험 | 실험 리포트, 임계값 제안 |
| 8 | `/steam/news/ask`: TTL 메모리·출처 인용·LLM 실패 대응·기능 플래그 | 근거·출처 답변 (**R2 완료**) |
| 9 | 전체 E2E·API 제한·배포(Dockerfile·compose·운영 설정, 배포 대상 결정) | DoD 충족, 미검증 항목 문서화 |

### Definition of Done
대시보드 표시(비로그인) → Steam 로그인 → 내 게임 분석 → 보유 게임 추천(이유 포함) → 할인 정보 → 뉴스 표시 성공. 권리 충족 시 질문→근거 응답. 캐시 실패 시 부분 결과, 통신 실패 시 오류 안내. 실제 테스트 결과와 미검증 항목을 기록.
