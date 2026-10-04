from __future__ import annotations

import asyncio
import logging
import time

from .checker import check
from .config import Settings
from .storage import Storage

log = logging.getLogger(__name__)

PRUNE_EVERY = 3600


class Monitor:
    def __init__(self, settings: Settings, storage: Storage):
        self.settings = settings
        self.storage = storage

    async def run(self) -> None:
        s = self.settings
        log.info(
            "Monitoring %s every %ss (timeout %ss)",
            ", ".join(map(str, s.targets)),
            s.interval,
            s.timeout,
        )
        last_online: bool | None = None
        next_prune = 0.0
        while True:
            started = time.monotonic()
            try:
                result = await check(s.targets, s.timeout)
                await asyncio.to_thread(self.storage.insert, result)
                if result.online != last_online:
                    log.log(
                        logging.INFO if result.online else logging.WARNING,
                        "Connection is %s (%s)",
                        "ONLINE" if result.online else "OFFLINE",
                        result.detail,
                    )
                    last_online = result.online
                if time.time() >= next_prune:
                    cutoff = time.time() - s.retention_days * 86400
                    removed = await asyncio.to_thread(self.storage.prune, cutoff)
                    if removed:
                        log.info("Pruned %d checks older than %d days", removed, s.retention_days)
                    next_prune = time.time() + PRUNE_EVERY
            except Exception:
                log.exception("Check failed")
            await asyncio.sleep(max(0.0, s.interval - (time.monotonic() - started)))
