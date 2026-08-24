"""Background retention maintenance."""

import asyncio
import logging

from src.config import env_int
from src.stats_service import exception_kind, retention_policy_lock, stats_service

logger = logging.getLogger(__name__)

RETENTION_MAINTENANCE_SEC = env_int(
    "RETENTION_MAINTENANCE_SEC", default=86400, min_value=60, max_value=604800
)


async def retention_maintenance_loop():
    """Periodically purge play history older than the configured retention window."""
    while True:
        await asyncio.sleep(RETENTION_MAINTENANCE_SEC)
        try:
            async with retention_policy_lock():
                result = await stats_service.purge_retention()
            if result["deleted"]:
                logger.info("Retention purge removed %s records", result["deleted"])
        except Exception as exc:
            logger.error(
                "Retention maintenance failed (type=%s)",
                exception_kind(exc),
            )


async def run_startup_retention_purge():
    try:
        result = await stats_service.purge_retention()
        if result["deleted"]:
            logger.info("Startup retention purge removed %s records", result["deleted"])
    except Exception as exc:
        logger.error(
            "Startup retention purge failed (type=%s)",
            exception_kind(exc),
        )
