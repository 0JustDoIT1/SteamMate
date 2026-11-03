from collections.abc import Iterable

from app.metadata.service import MetadataSnapshot, Priority


class FakeMetadata:
    """DB 없이 라우터를 테스트하기 위한 메타데이터 캐시 대역."""

    def __init__(self, snapshots: dict[int, MetadataSnapshot] | None = None) -> None:
        self.snapshots = snapshots or {}
        self.requested: list[list[int]] = []
        self.priorities: list[Priority] = []

    async def lookup(self, appids: Iterable[int], priority: Priority = Priority.HIGH) -> dict[int, MetadataSnapshot]:
        ids = list(appids)
        self.requested.append(ids)
        self.priorities.append(priority)
        return {a: self.snapshots[a] for a in ids if a in self.snapshots}
