"""수동 실행: `python -m app.jobs.collect` — 차트를 한 번 수집하고 메타데이터 보강이 끝날 때까지 기다린다."""

import asyncio
import logging

import httpx

from app.config import get_settings
from app.db import dispose_engine
from app.logging_config import configure_logging
from app.main import build_collector, build_metadata_service


async def main() -> None:
    settings = get_settings()
    configure_logging(secrets=(settings.steam_api_key, settings.session_secret))
    async with httpx.AsyncClient(timeout=settings.steam_timeout_seconds) as http:
        metadata = build_metadata_service(settings, http)
        metadata.start()
        try:
            report = await build_collector(settings, http, metadata).run_once()
            logging.getLogger(__name__).info("report: %s", report)
            await metadata.drain()
        finally:
            await metadata.stop()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
