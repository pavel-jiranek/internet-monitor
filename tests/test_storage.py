import pytest

from internet_monitor.checker import CheckResult
from internet_monitor.storage import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "test.db")


def add(storage, ts, online, latency=20.0):
    storage.insert(CheckResult(ts=ts, online=online, latency_ms=latency if online else None,
                               detail=""))


def test_summary_and_status(storage):
    for i in range(10):
        add(storage, 1000 + i * 10, online=i not in (4, 5))
    s = storage.summary(1000, 2000)
    assert s["checks"] == 10
    assert s["failed_checks"] == 2
    assert s["uptime"] == pytest.approx(0.8)
    assert s["avg_latency_ms"] == pytest.approx(20.0)

    st = storage.status()
    assert st["online"] is True
    assert st["last_check"] == 1090
    assert st["since"] == 1060


def test_buckets_fill_gaps(storage):
    add(storage, 1005, True)
    add(storage, 1015, False)
    add(storage, 1035, True)
    buckets = storage.buckets(1000, 1040, 10)
    assert [b["checks"] for b in buckets] == [1, 1, 0, 1]
    assert [b["uptime"] for b in buckets] == [1.0, 0.0, None, 1.0]
    assert buckets[0]["start"] == 1000 and buckets[-1]["end"] == 1040


def test_buckets_align_to_timezone(storage):
    buckets = storage.buckets(86400 + 5000, 3 * 86400, 86400, tz_offset=3600)
    assert buckets[0]["start"] == 86400 + 5000
    assert buckets[0]["end"] == 2 * 86400 - 3600


def test_outages(storage):
    states = [True, False, False, True, True, False, True]
    for i, online in enumerate(states):
        add(storage, 1000 + i * 10, online)
    outages = storage.outages(0, 5000, max_gap=30, now=1100)
    assert [(o["start"], o["end"]) for o in outages] == [(1010, 1030), (1050, 1060)]
    assert all(not o["ongoing"] for o in outages)


def test_outage_closed_when_monitor_stops(storage):
    add(storage, 1000, True)
    add(storage, 1010, False)
    add(storage, 1020, False)
    add(storage, 5000, False)  # monitor was down in between
    add(storage, 5010, True)
    outages = storage.outages(0, 9999, max_gap=30, now=6000)
    assert [(o["start"], o["end"]) for o in outages] == [(1010, 1020), (5000, 5010)]


def test_ongoing_and_clipped_outage(storage):
    for i in range(5):
        add(storage, 1000 + i * 10, False)
    outages = storage.outages(1000, 2000, max_gap=30, now=1045)
    assert len(outages) == 1
    o = outages[0]
    assert o["ongoing"] and o["clipped"] and o["end"] is None
    assert o["duration"] == 45

    # Long after the monitor stopped, it's no longer considered ongoing.
    o = storage.outages(1000, 2000, max_gap=30, now=9999)[0]
    assert not o["ongoing"] and o["end"] == 1040


def test_prune(storage):
    add(storage, 1000, True)
    add(storage, 2000, True)
    assert storage.prune(1500) == 1
    assert storage.summary(0, 5000)["checks"] == 1
