# Internet Monitor

While I am at work, my wife complains a lot afterwards about the internet connection outages in our house. I do not want to rush into my internet provider and complain directly without any evidence in my hand so I tried to make this.

This is small local service that continuously checks whether your internet connection is up, stores
the results in SQLite and shows the history in a web dashboard: uptime, outages, and latency for
the last hour, day, week, month, year, or any custom range.

## How it works

Every 10 seconds the monitor opens TCP connections to a few well-known public IPs
(`1.1.1.1:443`, `8.8.8.8:53`, `9.9.9.9:53` by default) concurrently. If at least one of them
answers within the timeout, the connection counts as **online**; the fastest connect time is
recorded as latency. Probing IPs directly means DNS problems don't skew the results.

- An **outage** lasts from the first failed check until the first successful one.
- Time when the monitor itself wasn't running (e.g. the computer was off) shows as
  **no data** and isn't counted as downtime.
- The dashboard has no external dependencies (no CDNs), so it works while you're offline.
- Data older than 400 days is pruned automatically.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/internet-monitor
```

Then open <http://127.0.0.1:8085/>.

## Running as a service

```bash
./scripts/install-service.sh
```

This creates the virtualenv, installs the package, and registers and starts a **systemd user
service**. Useful commands:

```bash
systemctl --user status internet-monitor
systemctl --user restart internet-monitor      # e.g. after pulling changes
journalctl --user -u internet-monitor -f       # logs, including online/offline transitions
./scripts/uninstall-service.sh                 # remove the service (keeps the data)
```

User services stop when you log out. To keep monitoring at all times, enable lingering once:

```bash
sudo loginctl enable-linger $USER
```

## Configuration

Settings can be passed as command-line options or environment variables (for the service, add
`Environment=` lines to `~/.config/systemd/user/internet-monitor.service`, or use
`systemctl --user edit internet-monitor`).

| Option             | Environment         | Default                                    |
| ------------------ | ------------------- | ------------------------------------------ |
| `--host`           | `IM_HOST`           | `127.0.0.1`                                |
| `--port`           | `IM_PORT`           | `8085`                                     |
| `--db`             | `IM_DB_PATH`        | `~/.local/share/internet-monitor/monitor.db` |
| `--interval`       | `IM_INTERVAL`       | `10` seconds                               |
| `--timeout`        | `IM_TIMEOUT`        | `3` seconds                                |
| `--target` (repeat)| `IM_TARGETS` (comma-separated) | `1.1.1.1:443,8.8.8.8:53,9.9.9.9:53` |
| `--retention-days` | `IM_RETENTION_DAYS` | `400`                                      |

## API

- `GET /api/status`: current state, latest latency, and since when it has been in that state.
- `GET /api/report?range=24h`: summary, time buckets, and outages. `range` accepts values like
  `1h`, `24h`, `7d`, `30d`, `1y`; alternatively pass `start`/`end` as Unix timestamps. Optional
  `bucket` (seconds) and `tz_offset` (seconds east of UTC, for aligning buckets to local time).

Interactive API docs are at <http://127.0.0.1:8085/docs>.

## Development

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```
