"""메타데이터 상태 전이 규칙(순수 함수). PRD 데이터 모델의 상태 전이 표를 코드로 옮긴 것.

핵심 불변조건: 429·5xx·타임아웃·스키마 불일치는 절대 NOT_AVAILABLE이 되지 않는다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.models import FetchStatus
from app.steam.store_api import FetchResult, Outcome

NOT_FOUND_REASON = "store_not_found"
NO_GENRES_REASON = "no_genres"


@dataclass(frozen=True)
class MetadataPolicy:
    success_ttl: timedelta
    not_available_ttl: timedelta
    retry_error: timedelta
    retry_rate_limited: timedelta
    retry_not_found: timedelta
    pending_stale: timedelta


@dataclass(frozen=True)
class PreviousState:
    status: FetchStatus
    failure_reason: str | None


def apply_result(
    result: FetchResult, previous: PreviousState | None, now: datetime, policy: MetadataPolicy
) -> dict[str, Any]:
    """조회 결과로 game_metadata에 쓸 컬럼 값을 계산한다."""
    if result.outcome is Outcome.OK and result.data is not None:
        data = result.data
        has_genres = bool(data.genres)
        return {
            "name": data.name or None,
            "app_type": data.type or None,
            "header_image": data.header_image or None,
            "genres_json": [g.model_dump() for g in data.genres],
            "categories_json": [c.model_dump() for c in data.categories],
            "dlc_appids_json": list(data.dlc),
            "fetch_status": FetchStatus.SUCCESS if has_genres else FetchStatus.NOT_AVAILABLE,
            "fetched_at": now,
            "expires_at": now + (policy.success_ttl if has_genres else policy.not_available_ttl),
            "last_checked_at": now,
            "retry_after": None,
            "failure_reason": None if has_genres else NO_GENRES_REASON,
        }

    if result.outcome is Outcome.NOT_FOUND:
        # 한 번의 success:false로는 확정하지 않는다(지역 제한 등 일시 원인 가능). 연속 2회면 확정.
        confirmed = previous is not None and previous.failure_reason == NOT_FOUND_REASON
        if confirmed:
            return {
                "fetch_status": FetchStatus.NOT_AVAILABLE,
                "expires_at": now + policy.not_available_ttl,
                "last_checked_at": now,
                "retry_after": None,
                "failure_reason": NOT_FOUND_REASON,
            }
        return _temporary(previous, now, now + policy.retry_not_found, NOT_FOUND_REASON)

    delay = policy.retry_rate_limited if result.outcome is Outcome.RATE_LIMITED else policy.retry_error
    reason = "rate_limited" if result.outcome is Outcome.RATE_LIMITED else (result.reason or "error")
    return _temporary(previous, now, now + delay, reason)


def _temporary(
    previous: PreviousState | None, now: datetime, retry_at: datetime, reason: str
) -> dict[str, Any]:
    # 이미 장르를 가진(SUCCESS) 행의 갱신이 일시 실패하면 기존 데이터를 유지하고 나중에 다시 시도한다.
    if previous is not None and previous.status is FetchStatus.SUCCESS:
        return {"expires_at": retry_at, "last_checked_at": now, "failure_reason": reason}
    return {
        "fetch_status": FetchStatus.TEMPORARY_ERROR,
        "last_checked_at": now,
        "retry_after": retry_at,
        "failure_reason": reason,
    }


def is_due(
    status: FetchStatus | None,
    *,
    expires_at: datetime | None,
    retry_after: datetime | None,
    last_checked_at: datetime | None,
    now: datetime,
    policy: MetadataPolicy,
) -> bool:
    """다시 조회해야 하는 행인지. status None은 행이 없는 경우."""
    if status is None:
        return True
    if status is FetchStatus.PENDING:
        # 서버 재시작 등으로 작업이 사라진 PENDING을 복구한다.
        return last_checked_at is None or now - last_checked_at >= policy.pending_stale
    if status is FetchStatus.TEMPORARY_ERROR:
        return retry_after is None or retry_after <= now
    return expires_at is None or expires_at <= now
