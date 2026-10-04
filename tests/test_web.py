import time

import pytest
from fastapi.testclient import TestClient

from internet_monitor.checker import CheckResult
from internet_monitor.config import Settings
from internet_monitor.web import choose_bucket, create_app, parse_span


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(db_path=tmp_path / "test.db"), run_monitor=False)
    now = time.time()
    for i in range(60):
        app.state.storage.insert(
            CheckResult(ts=now - 600 + i * 10, online=i % 20 != 0, latency_ms=15.0, detail="")
        )
    with TestClient(app) as c:
        yield c


def test_status(client):
    st = client.get("/api/status").json()
    assert st["monitoring"] is True
    assert st["online"] is True


def test_report_range(client):
    r = client.get("/api/report", params={"range": "1h"}).json()
    assert r["summary"]["checks"] == 60
    assert r["summary"]["outages"] == 3
    assert r["end"] - r["start"] == 3600
    assert sum(b["checks"] for b in r["buckets"]) == 60


def test_report_rejects_bad_range(client):
    assert client.get("/api/report", params={"range": "forever"}).status_code == 400


def test_dashboard_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Internet Monitor" in r.text


def test_bucket_choice():
    assert parse_span("7d") == 7 * 86400
    assert choose_bucket(86400, 10) == 300
    assert choose_bucket(365 * 86400, 10) == 86400
    assert choose_bucket(3600, 30) == 30
