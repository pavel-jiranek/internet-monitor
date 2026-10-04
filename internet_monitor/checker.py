from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass

from .config import Target


@dataclass
class ProbeResult:
    target: Target
    latency_ms: float | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.latency_ms is not None


@dataclass
class CheckResult:
    ts: float
    online: bool
    latency_ms: float | None
    detail: str


async def probe(target: Target, timeout: float) -> ProbeResult:
    """Open (and immediately close) a TCP connection to the target."""
    start = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(target.host, target.port), timeout
        )
    except TimeoutError:
        return ProbeResult(target, None, "timeout")
    except OSError as exc:
        return ProbeResult(target, None, exc.strerror or type(exc).__name__)
    latency_ms = (time.perf_counter() - start) * 1000
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()
    return ProbeResult(target, latency_ms)


async def check(targets: tuple[Target, ...], timeout: float) -> CheckResult:
    """Probe all targets concurrently; the connection is online if any target answers."""
    ts = time.time()
    results = await asyncio.gather(*(probe(t, timeout) for t in targets))
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    detail = "; ".join(
        f"{r.target} {'ok %.1fms' % r.latency_ms if r.ok else r.error}" for r in results
    )
    return CheckResult(
        ts=ts,
        online=bool(latencies),
        latency_ms=min(latencies) if latencies else None,
        detail=detail,
    )
