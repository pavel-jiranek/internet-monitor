from __future__ import annotations

import math
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from .checker import CheckResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    ts REAL NOT NULL,
    online INTEGER NOT NULL,
    latency_ms REAL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_ts ON checks(ts);
CREATE INDEX IF NOT EXISTS idx_checks_online_ts ON checks(online, ts);
"""


class Storage:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def insert(self, result: CheckResult) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO checks (ts, online, latency_ms, detail) VALUES (?, ?, ?, ?)",
                (result.ts, int(result.online), result.latency_ms, result.detail),
            )

    def prune(self, older_than: float) -> int:
        with closing(self._connect()) as conn, conn:
            return conn.execute("DELETE FROM checks WHERE ts < ?", (older_than,)).rowcount

    def status(self) -> dict | None:
        """Latest check plus the timestamp since which the connection has been in that state."""
        with closing(self._connect()) as conn:
            latest = conn.execute(
                "SELECT ts, online, latency_ms, detail FROM checks ORDER BY ts DESC LIMIT 1"
            ).fetchone()
            if latest is None:
                return None
            since = conn.execute(
                """
                SELECT MIN(ts) FROM checks WHERE ts > (
                    SELECT COALESCE(MAX(ts), 0) FROM checks WHERE online != ?
                )
                """,
                (latest["online"],),
            ).fetchone()[0]
        return {
            "last_check": latest["ts"],
            "online": bool(latest["online"]),
            "latency_ms": latest["latency_ms"],
            "detail": latest["detail"],
            "since": since,
        }

    def summary(self, start: float, end: float) -> dict:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total, COALESCE(SUM(online), 0) AS up,
                       AVG(latency_ms) AS avg_latency, MIN(ts) AS first, MAX(ts) AS last
                FROM checks WHERE ts >= ? AND ts < ?
                """,
                (start, end),
            ).fetchone()
        total, up = row["total"], row["up"]
        return {
            "checks": total,
            "failed_checks": total - up,
            "uptime": up / total if total else None,
            "avg_latency_ms": row["avg_latency"],
            "first_check": row["first"],
            "last_check": row["last"],
        }

    def buckets(
        self, start: float, end: float, bucket: float, tz_offset: float = 0
    ) -> list[dict]:
        """Aggregate checks into fixed-size buckets aligned to local time boundaries.

        `tz_offset` is the local timezone offset in seconds east of UTC, so that e.g. daily
        buckets start at local midnight.
        """
        first = math.floor((start + tz_offset) / bucket) * bucket - tz_offset
        count = max(1, math.ceil((end - first) / bucket))
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT CAST((ts - :first) / :bucket AS INTEGER) AS idx,
                       COUNT(*) AS total, SUM(online) AS up,
                       AVG(latency_ms) AS avg_latency, MAX(latency_ms) AS max_latency
                FROM checks WHERE ts >= :start AND ts < :end
                GROUP BY idx
                """,
                {"first": first, "bucket": bucket, "start": start, "end": end},
            ).fetchall()
        by_idx = {r["idx"]: r for r in rows}
        result = []
        for i in range(count):
            r = by_idx.get(i)
            total = r["total"] if r else 0
            result.append(
                {
                    "start": max(start, first + i * bucket),
                    "end": min(end, first + (i + 1) * bucket),
                    "checks": total,
                    "failed_checks": total - r["up"] if r else 0,
                    "uptime": r["up"] / total if total else None,
                    "avg_latency_ms": r["avg_latency"] if r else None,
                    "max_latency_ms": r["max_latency"] if r else None,
                }
            )
        return result

    def outages(
        self, start: float, end: float, max_gap: float, now: float | None = None
    ) -> list[dict]:
        """Periods of consecutive failed checks within [start, end).

        An outage lasts from its first failed check until the first successful one. If
        the monitor itself stopped running (gap between checks larger than `max_gap`),
        the outage is closed at the last failed check, since we don't know what happened
        afterwards. Outages already in progress at `start` are flagged as `clipped`.
        """
        now = time.time() if now is None else now
        with closing(self._connect()) as conn:
            events = conn.execute(
                """
                SELECT ts, online, prev_online, prev_ts FROM (
                    SELECT ts, online,
                           LAG(online) OVER w AS prev_online,
                           LAG(ts) OVER w AS prev_ts
                    FROM checks WHERE ts >= ? AND ts < ?
                    WINDOW w AS (ORDER BY ts)
                )
                WHERE prev_online IS NULL OR online != prev_online OR ts - prev_ts > ?
                ORDER BY ts
                """,
                (start, end, max_gap),
            ).fetchall()
            last = conn.execute(
                "SELECT MAX(ts) FROM checks WHERE ts >= ? AND ts < ?", (start, end)
            ).fetchone()[0]

        outages: list[dict] = []
        current: dict | None = None

        def close(at: float, ongoing: bool = False) -> None:
            nonlocal current
            assert current is not None
            current["end"] = None if ongoing else at
            current["duration"] = (now if ongoing else at) - current["start"]
            current["ongoing"] = ongoing
            outages.append(current)
            current = None

        for ev in events:
            gap = ev["prev_ts"] is not None and ev["ts"] - ev["prev_ts"] > max_gap
            if current is not None and gap:
                close(ev["prev_ts"])
            if ev["online"]:
                if current is not None:
                    close(ev["ts"])
            elif current is None:
                current = {"start": ev["ts"], "clipped": ev["prev_ts"] is None}

        if current is not None:
            close(last, ongoing=now - last <= max_gap)
        return outages
