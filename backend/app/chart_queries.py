from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import distinct_on

from app.models import ChartSnapshot, SnapshotStatus


def latest_success_ids(cc: str | None = None) -> Select:
    """(source, cc)별 '최신' 성공 스냅샷 id. 수집 정리와 대시보드가 같은 정의를 쓴다.

    최신 = 집계 주가 가장 늦은 것, 같으면 가장 늦게 수집한 것. id 최댓값을 쓰면 안 된다:
    과거 주를 백필하면 오래된 주가 더 큰 id를 갖기 때문이다.
    """
    q = (
        select(ChartSnapshot.id)
        .where(ChartSnapshot.status == SnapshotStatus.SUCCESS)
        .ext(distinct_on(ChartSnapshot.source, ChartSnapshot.cc))
        .order_by(
            ChartSnapshot.source,
            ChartSnapshot.cc,
            ChartSnapshot.period_start.desc().nulls_last(),
            ChartSnapshot.captured_at.desc(),
        )
    )
    return q.where(ChartSnapshot.cc == cc) if cc else q
