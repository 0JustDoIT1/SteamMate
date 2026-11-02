import asyncio
import time
from collections.abc import Awaitable, Callable


class TokenBucket:
    """초당 rate개씩 채워지고 최대 capacity개까지 모이는 토큰 버킷.

    pause()는 상대 서버가 제한을 걸었을 때 전체 요청을 일정 시간 멈춘다.
    clock·sleep을 주입받아 테스트에서 시간을 조작할 수 있다.
    """

    def __init__(
        self,
        rate_per_second: float,
        capacity: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if rate_per_second <= 0 or capacity < 1:
            raise ValueError("rate_per_second > 0, capacity >= 1 이어야 합니다.")
        self._rate = rate_per_second
        self._capacity = capacity
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(capacity)
        self._updated = clock()
        self._paused_until = 0.0
        self._lock = asyncio.Lock()

    def pause(self, seconds: float) -> None:
        self._paused_until = max(self._paused_until, self._clock() + seconds)
        self._tokens = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = self._clock()
                if now < self._paused_until:
                    await self._sleep(self._paused_until - now)
                    continue
                self._tokens = min(self._capacity, self._tokens + (now - self._updated) * self._rate)
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await self._sleep((1 - self._tokens) / self._rate)
