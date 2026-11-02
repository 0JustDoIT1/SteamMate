import pytest

from app.infra.rate_limit import TokenBucket


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


async def test_burst_then_steady_rate():
    clock = FakeClock()
    bucket = TokenBucket(rate_per_second=2, capacity=3, clock=clock, sleep=clock.sleep)
    for _ in range(3):
        await bucket.acquire()
    assert clock.sleeps == []  # 버스트 3회는 즉시
    await bucket.acquire()
    assert clock.sleeps == [0.5]  # 이후는 초당 2회
    await bucket.acquire()
    assert clock.now == pytest.approx(1.0)


async def test_pause_blocks_until_deadline():
    clock = FakeClock()
    bucket = TokenBucket(rate_per_second=10, capacity=10, clock=clock, sleep=clock.sleep)
    bucket.pause(60)
    await bucket.acquire()
    assert clock.now >= 60


async def test_tokens_refill_but_cap_at_capacity():
    clock = FakeClock()
    bucket = TokenBucket(rate_per_second=1, capacity=2, clock=clock, sleep=clock.sleep)
    clock.now = 1000  # 오래 쉬어도 capacity까지만 쌓인다
    for _ in range(2):
        await bucket.acquire()
    assert clock.sleeps == []
    await bucket.acquire()
    assert clock.sleeps == [1.0]


def test_invalid_config():
    with pytest.raises(ValueError):
        TokenBucket(rate_per_second=0, capacity=1)
