from datetime import UTC, datetime

from app.metadata.coverage import compute_coverage, snapshot_at
from app.metadata.service import MetadataSnapshot
from app.models import FetchStatus

T1 = datetime(2026, 11, 1, tzinfo=UTC)
T2 = datetime(2026, 11, 2, tzinfo=UTC)


def snap(appid, status, fetched_at=None):
    return MetadataSnapshot(appid=appid, status=status, fetched_at=fetched_at)


def test_coverage_excludes_not_available_from_denominator():
    snaps = {
        1: snap(1, FetchStatus.SUCCESS),
        2: snap(2, FetchStatus.SUCCESS),
        3: snap(3, FetchStatus.TEMPORARY_ERROR),
        4: snap(4, FetchStatus.NOT_AVAILABLE),
        # 5: 캐시에 없음 → pending
    }
    c = compute_coverage([1, 2, 3, 4, 5], snaps)
    assert (c.success, c.pending, c.temporary_error, c.not_available, c.total) == (2, 1, 1, 1, 5)
    assert c.ratio == 0.5  # 2 / (5 - 1)


def test_coverage_empty_and_all_not_available():
    assert compute_coverage([], {}).ratio == 0.0
    c = compute_coverage([1], {1: snap(1, FetchStatus.NOT_AVAILABLE)})
    assert c.ratio == 0.0 and c.not_available == 1


def test_snapshot_at_uses_latest_success_only():
    snaps = [
        snap(1, FetchStatus.SUCCESS, T1),
        snap(2, FetchStatus.SUCCESS, T2),
        snap(3, FetchStatus.NOT_AVAILABLE, datetime(2026, 12, 1, tzinfo=UTC)),
    ]
    assert snapshot_at(snaps) == T2
    assert snapshot_at([snap(1, FetchStatus.PENDING)]) is None


def test_coverage_serializes_camel_case():
    c = compute_coverage([1], {1: snap(1, FetchStatus.TEMPORARY_ERROR)})
    assert c.model_dump(by_alias=True)["temporaryError"] == 1
