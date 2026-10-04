from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TARGETS = ("1.1.1.1:443", "8.8.8.8:53", "9.9.9.9:53")


def default_db_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "internet-monitor" / "monitor.db"


@dataclass(frozen=True)
class Target:
    host: str
    port: int

    @classmethod
    def parse(cls, value: str) -> Target:
        host, sep, port = value.strip().rpartition(":")
        if not sep or not host or not port.isdigit():
            raise ValueError(f"Invalid target {value!r}, expected HOST:PORT")
        return cls(host.strip("[]"), int(port))

    def __str__(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"


@dataclass
class Settings:
    db_path: Path = field(default_factory=default_db_path)
    interval: float = 10.0
    timeout: float = 3.0
    targets: tuple[Target, ...] = tuple(Target.parse(t) for t in DEFAULT_TARGETS)
    host: str = "127.0.0.1"
    port: int = 8085
    retention_days: int = 400

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from IM_* environment variables, falling back to defaults."""
        env = os.environ
        defaults = cls()
        targets = env.get("IM_TARGETS")
        return cls(
            db_path=Path(env["IM_DB_PATH"]) if "IM_DB_PATH" in env else defaults.db_path,
            interval=float(env.get("IM_INTERVAL", defaults.interval)),
            timeout=float(env.get("IM_TIMEOUT", defaults.timeout)),
            targets=(
                tuple(Target.parse(t) for t in targets.split(",") if t.strip())
                if targets
                else defaults.targets
            ),
            host=env.get("IM_HOST", defaults.host),
            port=int(env.get("IM_PORT", defaults.port)),
            retention_days=int(env.get("IM_RETENTION_DAYS", defaults.retention_days)),
        )
