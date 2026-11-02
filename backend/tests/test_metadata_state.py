from datetime import UTC, datetime, timedelta

import pytest

from app.metadata.state import (
    NO_GENRES_REASON,
    NOT_FOUND_REASON,
    MetadataPolicy,
    PreviousState,
    apply_result,
    is_due,
)
from app.models import FetchStatus
from app.steam.store_api import AppData, FetchResult, Genre, Outcome

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
POLICY = MetadataPolicy(
    success_ttl=timedelta(days=7),
    not_available_ttl=timedelta(days=30),
    retry_error=timedelta(minutes=5),
    retry_rate_limited=timedelta(minutes=15),
    retry_not_found=timedelta(hours=1),
    pending_stale=timedelta(minutes=10),
)
WITH_GENRES = AppData(name="Portal 2", type="game", genres=[Genre(id="1", description="Action")], dlc=[1, 2])
OK = FetchResult(Outcome.OK, WITH_GENRES)
NOT_FOUND = FetchResult(Outcome.NOT_FOUND, reason=NOT_FOUND_REASON)
RATE_LIMITED = FetchResult(Outcome.RATE_LIMITED, reason="http_429")
ERROR_5XX = FetchResult(Outcome.ERROR, reason="http_503")
TIMEOUT = FetchResult(Outcome.ERROR, reason="timeout")
SCHEMA = FetchResult(Outcome.ERROR, reason="schema")


def prev(status: FetchStatus, reason: str | None = None) -> PreviousState:
    return PreviousState(status, reason)


def test_ok_with_genres_is_success():
    v = apply_result(OK, None, NOW, POLICY)
    assert v["fetch_status"] is FetchStatus.SUCCESS
    assert v["genres_json"] == [{"id": "1", "description": "Action"}]
    assert v["app_type"] == "game" and v["dlc_appids_json"] == [1, 2]
    assert v["expires_at"] == NOW + timedelta(days=7)
    assert v["failure_reason"] is None and v["retry_after"] is None


def test_ok_without_genres_is_not_available():
    v = apply_result(FetchResult(Outcome.OK, AppData(name="OST", type="music")), None, NOW, POLICY)
    assert v["fetch_status"] is FetchStatus.NOT_AVAILABLE
    assert v["failure_reason"] == NO_GENRES_REASON
    assert v["expires_at"] == NOW + timedelta(days=30)


def test_first_not_found_is_temporary_then_confirmed():
    first = apply_result(NOT_FOUND, None, NOW, POLICY)
    assert first["fetch_status"] is FetchStatus.TEMPORARY_ERROR
    assert first["retry_after"] == NOW + timedelta(hours=1)

    second = apply_result(NOT_FOUND, prev(FetchStatus.TEMPORARY_ERROR, NOT_FOUND_REASON), NOW, POLICY)
    assert second["fetch_status"] is FetchStatus.NOT_AVAILABLE


def test_not_found_after_other_error_is_not_confirmed():
    v = apply_result(NOT_FOUND, prev(FetchStatus.TEMPORARY_ERROR, "rate_limited"), NOW, POLICY)
    assert v["fetch_status"] is FetchStatus.TEMPORARY_ERROR


@pytest.mark.parametrize(
    ("result", "delay"),
    [(RATE_LIMITED, timedelta(minutes=15)), (ERROR_5XX, timedelta(minutes=5)), (TIMEOUT, timedelta(minutes=5)), (SCHEMA, timedelta(minutes=5))],
)
@pytest.mark.parametrize(
    "previous",
    [None, prev(FetchStatus.PENDING), prev(FetchStatus.TEMPORARY_ERROR, NOT_FOUND_REASON), prev(FetchStatus.NOT_AVAILABLE, NOT_FOUND_REASON)],
)
def test_transient_failures_never_become_not_available(result, delay, previous):
    """PRD 불변조건: 429·5xx·타임아웃·스키마 불일치는 NOT_AVAILABLE이 되지 않는다."""
    v = apply_result(result, previous, NOW, POLICY)
    assert v["fetch_status"] is FetchStatus.TEMPORARY_ERROR
    assert v["retry_after"] == NOW + delay


@pytest.mark.parametrize("result", [RATE_LIMITED, ERROR_5XX, NOT_FOUND])
def test_stale_success_keeps_data_on_temporary_failure(result):
    v = apply_result(result, prev(FetchStatus.SUCCESS), NOW, POLICY)
    assert "fetch_status" not in v  # SUCCESS 유지
    assert "genres_json" not in v  # 기존 장르 유지
    assert v["expires_at"] > NOW  # 나중에 다시 시도


def due(status, **kw):
    base = {"expires_at": None, "retry_after": None, "last_checked_at": None, "now": NOW, "policy": POLICY}
    return is_due(status, **{**base, **kw})


def test_due_rules():
    assert due(None)
    assert not due(FetchStatus.SUCCESS, expires_at=NOW + timedelta(seconds=1))
    assert due(FetchStatus.SUCCESS, expires_at=NOW)
    assert not due(FetchStatus.NOT_AVAILABLE, expires_at=NOW + timedelta(days=1))
    assert not due(FetchStatus.TEMPORARY_ERROR, retry_after=NOW + timedelta(seconds=1))
    assert due(FetchStatus.TEMPORARY_ERROR, retry_after=NOW)


def test_stale_pending_is_due_again():
    assert not due(FetchStatus.PENDING, last_checked_at=NOW - timedelta(minutes=9))
    assert due(FetchStatus.PENDING, last_checked_at=NOW - timedelta(minutes=10))
    assert due(FetchStatus.PENDING, last_checked_at=None)
