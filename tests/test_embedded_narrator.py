"""The dashboard's AI chat and "Explain (AI)" work with no separate narrator process: when NARRATOR_URL is empty the platform uses the narrator of
mcp-service in-process (grounded mode, no language model, unless ANTHROPIC_API_KEY is set), reading the platform through the same read-only tools.
A NARRATOR_URL still wins. No network."""
import io

import pytest
from httpx import AsyncClient

from backend.app import mcp_gateway
from backend.app import runtime_settings as rs
from backend.app.api import auth as auth_api
from backend.app.config import settings
from backend.app.validation import narrate

ADMIN = "a" * 32
H = {"X-Admin-Token": ADMIN}
DAILY = "station_id,day,mm\n" + "\n".join(f"S1,2026-03-{d:02d},{0.0 if d != 5 else -1.0}" for d in range(1, 11)) + "\n"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", ADMIN)
    monkeypatch.setattr(settings, "NARRATOR_URL", "")
    monkeypatch.setattr(settings, "NARRATOR_TOKEN", "")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "NARRATOR_EMBEDDED", True)
    monkeypatch.setattr(settings, "MCP_AUDIT_LOG", str(tmp_path / "mcp_audit.jsonl"))
    monkeypatch.setenv("RUNTIME_SETTINGS_PATH", str(tmp_path / "rt.json"))
    auth_api._token_failures.clear()
    mcp_gateway.reset()


async def flagged_row(c: AsyncClient):
    r = await c.post("/api/validation/runs", data={"profile": "daily"}, files={"file": ("d.csv", io.BytesIO(DAILY.encode()), "text/csv")}, headers=H)
    assert r.status_code == 201, r.text
    run_id = r.json()["id"]
    rows = (await c.get(f"/api/validation/runs/{run_id}/rows?page_size=5", headers=H)).json()["rows"]
    assert rows, "the negative day should be flagged"
    return run_id, rows[0]["id"]


@pytest.mark.asyncio
async def test_with_no_narrator_url_the_platform_uses_its_own_narrator(async_client: AsyncClient):
    st = (await async_client.get("/api/validation/narrator", headers=H)).json()
    assert st["connected"] is True and st["implemented"] is True and "embedded" in st["host"] and st["mode"] == "grounded"


@pytest.mark.asyncio
async def test_explain_with_the_narrator_works_and_says_it_is_not_a_language_model(async_client: AsyncClient):
    run_id, row_id = await flagged_row(async_client)
    r = await async_client.post(f"/api/validation/runs/{run_id}/rows/{row_id}/explain", json={"generator": "narrator"}, headers=H)
    assert r.status_code == 201, r.text
    ex = r.json()["explanations"][0]
    assert ex["generator"] == "mcp-narrator" and ex["model_id"] == "datamend-mcp-grounded-v1" and ex["text"].strip() and ex["generated"] is True
    assert "no language model" in ex["label"] and ex["check"] == "impossible_value"


@pytest.mark.asyncio
async def test_the_chat_answers_a_question_about_the_run_from_platform_data(async_client: AsyncClient):
    run_id, row_id = await flagged_row(async_client)
    r = await async_client.post(f"/api/validation/runs/{run_id}/chat", json={"message": "How many rows were flagged in this run?", "row_id": row_id}, headers=H)
    assert r.status_code == 201, r.text
    assert r.json()["text"].strip() and r.json()["model_id"] == "datamend-mcp-grounded-v1" and "no language model" in r.json()["label"]
    history = (await async_client.get(f"/api/validation/runs/{run_id}/chat", headers=H)).json()["messages"]
    assert len(history) == 1 and history[0]["question"].startswith("How many rows")


@pytest.mark.asyncio
async def test_a_question_the_grounded_narrator_cannot_answer_is_said_plainly_not_invented(async_client: AsyncClient):
    run_id, _ = await flagged_row(async_client)
    r = await async_client.post(f"/api/validation/runs/{run_id}/chat", json={"message": "Write me a poem about the monsoon."}, headers=H)
    assert r.status_code == 502 and "narrator" in r.json()["detail"].lower()
    assert (await async_client.get(f"/api/validation/runs/{run_id}/chat", headers=H)).json()["messages"] == []         # nothing was stored


@pytest.mark.asyncio
async def test_a_configured_narrator_url_still_wins(monkeypatch):
    monkeypatch.setattr(settings, "NARRATOR_URL", "https://narrator.example/narrate")
    n = narrate.get_narrator()
    assert n is not None and n.host == "narrator.example" and not isinstance(n, mcp_gateway.EmbeddedNarrator)


@pytest.mark.asyncio
async def test_without_the_mcp_service_files_the_narrator_is_not_connected_as_before(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(mcp_gateway, "AVAILABLE", False)
    st = (await async_client.get("/api/validation/narrator", headers=H)).json()
    assert st["connected"] is False
    run_id, row_id = await flagged_row(async_client)
    r = await async_client.post(f"/api/validation/runs/{run_id}/rows/{row_id}/explain", json={"generator": "narrator"}, headers=H)
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_an_anthropic_key_switches_the_embedded_narrator_to_language_model_mode(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test-not-real-0000000000")
    n = narrate.get_narrator()
    assert isinstance(n, mcp_gateway.EmbeddedNarrator) and n.mode == "llm"
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    mcp_gateway.reset()
    assert narrate.get_narrator().mode == "grounded"
