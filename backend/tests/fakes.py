from collections.abc import Iterable

from app.metadata.service import MetadataSnapshot


class FakeMetadata:
    """DB 없이 라우터를 테스트하기 위한 메타데이터 캐시 대역."""

    def __init__(self, snapshots: dict[int, MetadataSnapshot] | None = None) -> None:
        self.snapshots = snapshots or {}
        self.requested: list[list[int]] = []

    async def lookup(self, appids: Iterable[int]) -> dict[int, MetadataSnapshot]:
        ids = list(appids)
        self.requested.append(ids)
        return {a: self.snapshots[a] for a in ids if a in self.snapshots}
