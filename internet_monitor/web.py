from __future__ import annotations

import asyncio
import contextlib
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .monitor import Monitor
from .storage import Storage

STATIC_DIR = Path(__file__).parent / "static"

UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 365 * 86400}

NICE_BUCKETS = (
    10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200,
    86400, 2 * 86400, 7 * 86400,
)
MAX_BUCKETS = 400


def parse_span(value: str) -> int:
    m = re.fullmatch(r"(\d+)([mhdwy])", value.strip().lower())
    if not m:
        raise ValueError(f"Invalid range {value!r}, expected e.g. 1h, 24h, 7d, 30d, 1y")
    return int(m.group(1)) * UNIT_SECONDS[m.group(2)]


def choose_bucket(span: float, min_bucket: float) -> int:
    target = max(span / MAX_BUCKETS, min_bucket)
    return next((b for b in NICE_BUCKETS if b >= target), NICE_BUCKETS[-1])


def create_app(settings: Settings, run_monitor: bool = True) -> FastAPI:
    storage = Storage(settings.db_path)
    # Beyond this gap between checks, we assume the monitor wasn't running.
    max_gap = max(settings.interval * 3, settings.interval + settings.timeout * 2)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(Monitor(settings, storage).run()) if run_monitor else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Internet Monitor", lifespan=lifespan)
    app.state.storage = storage

    @app.get("/api/status")
    def status() -> dict:
        st = storage.status()
        now = time.time()
        return {
            "now": now,
            "interval": settings.interval,
            "targets": [str(t) for t in settings.targets],
            # A stale last check means the monitor isn't running; report state as unknown.
            "monitoring": st is not None and now - st["last_check"] <= max_gap,
            **(st or {"online": None, "last_check": None, "since": None,
                      "latency_ms": None, "detail": None}),
        }

    @app.get("/api/report")
    def report(
        range: str | None = Query(None, description="Span ending now, e.g. 24h, 7d, 30d"),
        start: float | None = Query(None, description="Unix timestamp (seconds)"),
        end: float | None = Query(None, description="Unix timestamp (seconds)"),
        bucket: int | None = Query(None, ge=1, description="Bucket size in seconds"),
        tz_offset: int = Query(0, description="Local UTC offset in seconds east of UTC"),
    ) -> dict:
        now = time.time()
        if start is None:
            try:
                span = parse_span(range or "24h")
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            end = now if end is None else end
            start = end - span
        elif end is None:
            end = now
        if end <= start:
            raise HTTPException(400, "end must be after start")

        size = bucket or choose_bucket(end - start, settings.interval)
        if (end - start) / size > 5000:
            raise HTTPException(400, "Too many buckets; use a larger bucket size")

        outages = storage.outages(start, end, max_gap, now=now)
        summary = storage.summary(start, end)
        summary.update(
            outages=len(outages),
            downtime=sum(o["duration"] for o in outages),
            longest_outage=max((o["duration"] for o in outages), default=0),
        )
        return {
            "start": start,
            "end": end,
            "bucket": size,
            "summary": summary,
            "buckets": storage.buckets(start, end, size, tz_offset),
            "outages": outages[::-1],
        }

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
