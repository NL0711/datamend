"""The single-use WebSocket ticket for a dashboard hosted on another site (Vercel cannot proxy WebSockets)."""
import time

from backend.app.api import stream as stream_api


def test_a_ticket_works_once_and_expires():
    stream_api._tickets.clear()
    stream_api._tickets["fresh"] = time.monotonic() + 30
    stream_api._tickets["old"] = time.monotonic() - 1
    assert stream_api._ticket_valid("fresh") is True
    assert stream_api._ticket_valid("fresh") is False      # single use
    assert stream_api._ticket_valid("old") is False
    assert stream_api._ticket_valid("never-issued") is False
    assert stream_api._ticket_valid(None) is False
    assert "old" not in stream_api._tickets


def test_purge_drops_expired_tickets_only():
    stream_api._tickets.clear()
    now = time.monotonic()
    stream_api._tickets.update({"a": now - 5, "b": now + 5})
    stream_api._purge_tickets(now)
    assert list(stream_api._tickets) == ["b"]
