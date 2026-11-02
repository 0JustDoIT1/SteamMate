# SteamMate — Claude Code 개발 규칙

> 이 저장소에만 적용. 사용자 홈 전역 설정에 복사하지 않는다.

## 공통 개발 행동 규칙
- 해당 저장소 `docs/PRD.md`의 **현재 작업과 관련된 섹션만** 읽고 기준으로 삼는다. 다른 프로젝트 문서는 참조하지 않는다.
- `docs/PRD.md`는 승인된 기준선이다. Claude는 직접 수정하지 않고 변경 이유·수정안·영향 범위를 제안한다. 승인 후 사용자가 명시적으로 수정 요청한 경우에만 편집한다.
- 요청 범위와 관련 코드·현재 git 상태를 먼저 확인한다. MVP 외 기능, 불필요한 추상화, 새 라이브러리를 임의로 추가하지 않는다.
- 수정 전 영향 파일을 파악하고 복잡한 작업은 간단한 계획을 제시한다. 사용자의 기존 미커밋 변경을 덮어쓰지 않는다.
- 입력·외부 API 응답을 검증하고 오류를 조용히 무시하지 않는다. API 키·토큰·개인정보를 로그, 출력, 커밋에 남기지 않는다.
- 핵심 규칙, 실패/경계조건, 중복 요청·상태 복구 등에 테스트를 작성한다. 실패한 테스트를 임의 삭제·skip하지 않는다. 실행하지 않은 검증은 통과했다고 주장하지 않는다.
- 작업을 마치면 변경 파일, 구현 이유, 실행한 명령/결과, 미검증 사항을 간단히 보고한다. 핵심 기술의 원리·트레이드오프를 사용자가 이해할 수 있게 설명한다.

## 개발 환경
- OS: Windows. 기본 셸: Git Bash. 실행 명령은 Git Bash 문법으로 작성하며 PowerShell과 섞지 않는다.
- Python 프로젝트에서는 `source .venv/Scripts/activate`를 사용한다.
- 설치 전이거나 초기화되지 않은 단계라면 Commands 항목은 **예상 명령**이다. 프로젝트 파일을 확인하고 실제 스크립트·Gradle wrapper 유무에 맞춰 확정한다.

## Git
- 커밋은 기본적으로 **사용자가 명시적으로 요청할 때만** 실행한다. 요청받으면 기능 단위로 작게 나누고 `feat|fix|refactor|test|docs|chore: 요약` 형식을 따른다.
- 커밋 전 `git status`와 staged diff를 확인하고 `.env*`(예시 파일 제외), `.venv/`, `node_modules/`, 빌드 산출물, 비밀값을 포함하지 않는다.
- push, 브랜치 삭제, rebase, reset, force push, 기존 커밋 수정은 반드시 사전 승인을 받는다. 승인 없이 destructive Git 명령 금지.

## DB 스키마
- 스키마 변경은 버전 관리되는 마이그레이션 파일로만 수행한다. 운영 DB에서 `create_all`, `ddl-auto=create/update`, 무계획 자동 sync에 의존하지 않는다.
- 이미 커밋되어 적용 가능한 마이그레이션은 수정하지 않고 새로운 마이그레이션을 추가한다.
- 스키마·마이그레이션·모델·테스트의 정합성을 함께 검증한다.

## 프로젝트 기술 스택
- Next.js + FastAPI + PostgreSQL

## 프로젝트 핵심 불변조건
- Steam 뉴스·임베딩은 권한이 확인되지 않은 장기 저장·공개 아카이브로 만들지 않는다. TTL 캐시도 이용 허가를 대신하지 않는다.
- Steam Web API Key는 서버에만 두고 공개 라이브러리 권한과 API 오류를 검증한다.
- 게임 메타데이터 coverage, 제외 항목, metadataSnapshotAt, 추천 모드를 응답에 표시한다.
- Full Context/RAG 실험은 총 토큰 규모와 근거 정확도를 기준으로 비교한다.

## 기술별 규칙
- Next.js: App Router/TypeScript 타입 검사와 서버/클라이언트 경계 준수.
- FastAPI: Pydantic으로 외부 입력·출력 검증; async 작업에서 blocking I/O 주의.
- DB: Alembic 마이그레이션 사용(선정 후 확정).

## Commands (프로젝트 초기화 후 실명령으로 점검)
- 프론트엔드: `cd frontend && npm run dev`
- 백엔드: `cd backend && source .venv/Scripts/activate && uvicorn app.main:app --reload`
- 테스트: `cd backend && pytest`
- 린트: `cd frontend && npm run lint`

## 참조 문서
- `docs/PRD.md` 하나를 설계 기준으로 사용하며, 현재 작업과 관련된 절만 확인한다.
