import asyncio
import socket

from internet_monitor.checker import check
from internet_monitor.config import Target


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_check_online_if_any_target_answers():
    async def run():
        server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            return await check(
                (Target("127.0.0.1", free_port()), Target("127.0.0.1", port)), timeout=1
            )

    result = asyncio.run(run())
    assert result.online
    assert result.latency_ms is not None
    assert "ok" in result.detail


def test_check_offline_if_no_target_answers():
    result = asyncio.run(check((Target("127.0.0.1", free_port()),), timeout=1))
    assert not result.online
    assert result.latency_ms is None


def test_target_parse():
    assert Target.parse("1.1.1.1:443") == Target("1.1.1.1", 443)
    assert Target.parse("[2606:4700::1111]:53") == Target("2606:4700::1111", 53)
    assert str(Target("2606:4700::1111", 53)) == "[2606:4700::1111]:53"
