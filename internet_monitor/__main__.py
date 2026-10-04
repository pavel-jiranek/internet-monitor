from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from .config import Settings, Target
from .web import create_app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    d = Settings.from_env()
    p = argparse.ArgumentParser(
        prog="internet-monitor",
        description="Monitor internet connectivity and serve a dashboard. "
        "Defaults can also be set with IM_* environment variables.",
    )
    p.add_argument("--host", default=d.host, help=f"web server bind address (default {d.host})")
    p.add_argument("--port", type=int, default=d.port, help=f"web server port (default {d.port})")
    p.add_argument("--db", type=Path, default=d.db_path, help=f"SQLite database (default {d.db_path})")
    p.add_argument("--interval", type=float, default=d.interval, help="seconds between checks")
    p.add_argument("--timeout", type=float, default=d.timeout, help="per-target timeout in seconds")
    p.add_argument(
        "--target",
        dest="targets",
        action="append",
        type=Target.parse,
        help="HOST:PORT to probe over TCP; repeatable (default: %s)"
        % ", ".join(map(str, d.targets)),
    )
    p.add_argument("--retention-days", type=int, default=d.retention_days)
    p.add_argument("--no-monitor", action="store_true", help="only serve the dashboard")
    p.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    args = p.parse_args(argv)
    args.targets = tuple(args.targets) if args.targets else d.targets
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = Settings(
        db_path=args.db,
        interval=args.interval,
        timeout=args.timeout,
        targets=args.targets,
        host=args.host,
        port=args.port,
        retention_days=args.retention_days,
    )
    app = create_app(settings, run_monitor=not args.no_monitor)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=args.log_level,
                access_log=False)


if __name__ == "__main__":
    main()
