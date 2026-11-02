from collections.abc import Iterable, Mapping
from datetime import datetime

from app.metadata.service import MetadataSnapshot
from app.models import FetchStatus
from app.schemas import CamelModel


class MetadataCoverage(CamelModel):
    success: int
    pending: int
    temporary_error: int
    not_available: int
    total: int
    # success / (total - notAvailable). 유효 대상이 없으면 0.
    ratio: float


def compute_coverage(appids: Iterable[int], snapshots: Mapping[int, MetadataSnapshot]) -> MetadataCoverage:
    counts = dict.fromkeys(FetchStatus, 0)
    total = 0
    for appid in appids:
        total += 1
        snap = snapshots.get(appid)
        counts[snap.status if snap else FetchStatus.PENDING] += 1
    eligible = total - counts[FetchStatus.NOT_AVAILABLE]
    return MetadataCoverage(
        success=counts[FetchStatus.SUCCESS],
        pending=counts[FetchStatus.PENDING],
        temporary_error=counts[FetchStatus.TEMPORARY_ERROR],
        not_available=counts[FetchStatus.NOT_AVAILABLE],
        total=total,
        ratio=round(counts[FetchStatus.SUCCESS] / eligible, 4) if eligible else 0.0,
    )


def snapshot_at(snapshots: Iterable[MetadataSnapshot]) -> datetime | None:
    """추천 계산에 쓰인 메타데이터의 기준 시각 = SUCCESS 행의 max(fetched_at)."""
    times = [s.fetched_at for s in snapshots if s.status is FetchStatus.SUCCESS and s.fetched_at]
    return max(times, default=None)
