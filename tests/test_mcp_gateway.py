"""The platform's own MCP endpoint (POST /api/mcp): other people's agents (Claude and so on) connect with a token made in Settings and read the
platform's results through the same read-only tools as mcp-service. Tokens are stored as hashes. No network: everything runs in-process."""
import io
import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from backend.app.api import auth as auth_api
from backend.app.config import settings
from backend.app.db.database import async_session_factory
from backend.app.validation.models import McpToken

ADMIN = "a" * 32
H = {"X-Admin-Token": ADMIN}
DAILY = "station_id,day,mm\n" + "\n".join(f"S1,2026-03-{d:02d},{0.0 if d != 5 else -1.0}" for d in range(1, 11)) + "\n"      # a negative day: an impossible value, flagged


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADMIN_TOKEN", ADMIN)
    monkeypatch.setattr(settings, "MCP_AUDIT_LOG", str(tmp_path / "mcp_audit.jsonl"))
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "")
    auth_api._token_failures.clear()
    from backend.app import mcp_gateway
    mcp_gateway.reset()


@pytest_asyncio.fixture(autouse=True)
async def _no_tokens():
    """The test database is shared between tests: start each one with no MCP tokens."""
    async with async_session_factory() as s:
        await s.execute(delete(McpToken))
        await s.commit()


async def make_token(c: AsyncClient, label="Alice's Claude") -> dict:
    r = await c.post("/api/settings/mcp/tokens", json={"label": label}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()


def rpc(method, params=None, id_=1):
    return {"jsonrpc": "2.0", "id": id_, "method": method, **({"params": params} if params is not None else {})}


async def call(c: AsyncClient, token, body, **kw):
    return await c.post("/api/mcp", json=body, headers={"Authorization": f"Bearer {token}", **kw.pop("headers", {})}, **kw)


async def upload(c: AsyncClient) -> int:
    r = await c.post("/api/validation/runs", data={"profile": "daily", "synthetic": "true"}, files={"file": ("d.csv", io.BytesIO(DAILY.encode()), "text/csv")}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------- tokens
@pytest.mark.asyncio
async def test_a_token_is_shown_once_and_only_its_hash_is_stored(async_client: AsyncClient):
    t = await make_token(async_client)
    assert t["token"].startswith("dmcp_") and len(t["token"]) > 30 and t["prefix"] == t["token"][:12] and t["label"] == "Alice's Claude"
    listing = (await async_client.get("/api/settings/mcp", headers=H)).json()
    assert t["token"] not in json.dumps(listing) and listing["tokens"][0]["prefix"] == t["prefix"] and listing["active"] == 1
    async with async_session_factory() as s:
        row = (await s.execute(select(McpToken).where(McpToken.id == t["id"]))).scalar_one()
    assert t["token"] not in row.token_hash and len(row.token_hash) == 64 and row.revoked_at is None


@pytest.mark.asyncio
async def test_only_a_signed_in_admin_manages_tokens(async_client: AsyncClient):
    assert (await async_client.post("/api/settings/mcp/tokens", json={"label": "x"})).status_code in (401, 403)
    assert (await async_client.post("/api/settings/mcp/tokens", json={"label": "x"}, headers={"X-Admin-Token": "nope"})).status_code == 401
    t = await make_token(async_client)
    assert (await async_client.delete(f"/api/settings/mcp/tokens/{t['id']}")).status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["", "   ", "x" * 81, "bad\nlabel"])
async def test_a_bad_label_is_refused(async_client: AsyncClient, label):
    assert (await async_client.post("/api/settings/mcp/tokens", json={"label": label}, headers=H)).status_code == 422


@pytest.mark.asyncio
async def test_the_number_of_active_tokens_is_capped_and_a_revoked_one_frees_a_slot(async_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "MCP_MAX_TOKENS", 2)
    a, _b = await make_token(async_client, "a"), await make_token(async_client, "b")
    assert (await async_client.post("/api/settings/mcp/tokens", json={"label": "c"}, headers=H)).status_code == 409
    assert (await async_client.delete(f"/api/settings/mcp/tokens/{a['id']}", headers=H)).status_code == 200
    assert (await async_client.post("/api/settings/mcp/tokens", json={"label": "c"}, headers=H)).status_code == 201


@pytest.mark.asyncio
async def test_revoking_is_idempotent_and_an_unknown_id_is_404(async_client: AsyncClient):
    t = await make_token(async_client)
    assert (await async_client.delete(f"/api/settings/mcp/tokens/{t['id']}", headers=H)).status_code == 200
    assert (await async_client.delete(f"/api/settings/mcp/tokens/{t['id']}", headers=H)).status_code == 200
    assert (await async_client.delete("/api/settings/mcp/tokens/99999", headers=H)).status_code == 404
    assert (await async_client.get("/api/settings/mcp", headers=H)).json()["active"] == 0


# ---------------------------------------------------------------- the endpoint
@pytest.mark.asyncio
async def test_no_token_a_wrong_token_and_a_revoked_token_are_refused(async_client: AsyncClient):
    r = await async_client.post("/api/mcp", json=rpc("ping"))
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert (await call(async_client, "dmcp_wrong", rpc("ping"))).status_code == 401
    t = await make_token(async_client)
    assert (await call(async_client, t["token"], rpc("ping"))).status_code == 200
    await async_client.delete(f"/api/settings/mcp/tokens/{t['id']}", headers=H)
    assert (await call(async_client, t["token"], rpc("ping"))).status_code == 401


@pytest.mark.asyncio
async def test_the_session_and_the_admin_token_do_not_open_the_endpoint(async_client: AsyncClient):
    assert (await async_client.post("/api/mcp", json=rpc("ping"), headers=H)).status_code == 401           # only an MCP token does
    assert (await async_client.post("/api/mcp", json=rpc("ping"), headers={"Authorization": f"Bearer {ADMIN}"})).status_code == 401


@pytest.mark.asyncio
async def test_many_wrong_tokens_are_rate_limited(async_client: AsyncClient):
    codes = [(await call(async_client, f"dmcp_guess{i}", rpc("ping"))).status_code for i in range(auth_api.TOKEN_MAX_FAILURES + 3)]
    assert codes[0] == 401 and codes[-1] == 429


@pytest.mark.asyncio
async def test_a_browser_origin_is_refused_unless_allowed(async_client: AsyncClient, monkeypatch):
    t = await make_token(async_client)
    assert (await call(async_client, t["token"], rpc("ping"), headers={"Origin": "https://evil.example"})).status_code == 403
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "https://good.example, https://other.example")
    assert (await call(async_client, t["token"], rpc("ping"), headers={"Origin": "https://good.example"})).status_code == 200


@pytest.mark.asyncio
async def test_the_mcp_lifecycle_initialize_list_and_notifications(async_client: AsyncClient):
    tok = (await make_token(async_client))["token"]
    r = await call(async_client, tok, rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}))
    res = r.json()["result"]
    assert r.status_code == 200 and res["protocolVersion"] == "2025-06-18" and res["serverInfo"]["name"] == "datamend-mcp" and "tools" in res["capabilities"]
    note = await call(async_client, tok, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert note.status_code == 202 and note.content == b""
    tools = (await call(async_client, tok, rpc("tools/list"))).json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"list_runs", "get_run_summary", "list_flagged_rows", "get_row_evidence", "get_overview"} <= names and len(names) == 14
    assert all(t["annotations"]["readOnlyHint"] is True for t in tools)                                       # nothing here can change data


@pytest.mark.asyncio
async def test_a_tool_call_returns_the_platforms_real_results(async_client: AsyncClient):
    run_id = await upload(async_client)
    tok = (await make_token(async_client))["token"]
    runs = (await call(async_client, tok, rpc("tools/call", {"name": "list_runs", "arguments": {}}))).json()["result"]
    assert runs["isError"] is False and any(r["id"] == run_id for r in runs["structuredContent"]["data"]["runs"])
    flagged = (await call(async_client, tok, rpc("tools/call", {"name": "list_flagged_rows", "arguments": {"run_id": run_id}}))).json()["result"]
    assert flagged["isError"] is False and flagged["structuredContent"]["data"]["total"] >= 1                  # the negative day is flagged
    over = (await call(async_client, tok, rpc("tools/call", {"name": "get_overview", "arguments": {}}))).json()["result"]
    assert over["structuredContent"]["data"]["runs"]["total"] >= 1


@pytest.mark.asyncio
async def test_the_tools_work_even_when_the_platform_requires_sign_in(async_client: AsyncClient, monkeypatch):
    """The loopback read is authenticated internally; nothing needs a user session, and a signed-out caller still cannot read the platform directly."""
    monkeypatch.setattr(settings, "REQUIRE_LOGIN", True)
    run_id = await upload(async_client)
    assert (await async_client.get(f"/api/validation/runs/{run_id}")).status_code == 401
    tok = (await make_token(async_client))["token"]
    res = (await call(async_client, tok, rpc("tools/call", {"name": "get_run_summary", "arguments": {"run_id": run_id}}))).json()["result"]
    assert res["isError"] is False and res["structuredContent"]["data"]["id"] == run_id


@pytest.mark.asyncio
async def test_a_tool_error_is_an_mcp_error_not_a_crash(async_client: AsyncClient):
    tok = (await make_token(async_client))["token"]
    bad_args = (await call(async_client, tok, rpc("tools/call", {"name": "get_run_summary", "arguments": {"run_id": "x"}}))).json()["result"]
    assert bad_args["isError"] is True
    missing = (await call(async_client, tok, rpc("tools/call", {"name": "get_run_summary", "arguments": {"run_id": 99999}}))).json()["result"]
    assert missing["isError"] is True and "not found" in missing["content"][0]["text"]
    unknown = (await call(async_client, tok, rpc("tools/call", {"name": "delete_everything", "arguments": {}}))).json()
    assert unknown["error"]["code"] == -32602 and "unknown tool" in unknown["error"]["message"]


@pytest.mark.asyncio
async def test_resources_prompts_and_batches(async_client: AsyncClient):
    tok = (await make_token(async_client))["token"]
    res = (await call(async_client, tok, rpc("resources/read", {"uri": "datamend://guidelines/narration"}))).json()["result"]["contents"][0]
    assert "NOT a trained model" in res["text"]
    prompts = (await call(async_client, tok, rpc("prompts/list"))).json()["result"]["prompts"]
    assert {"explain_flag", "triage_run"} <= {p["name"] for p in prompts}
    batch = (await call(async_client, tok, [rpc("ping", id_=1), rpc("tools/list", id_=2), {"jsonrpc": "2.0", "method": "notifications/initialized"}])).json()
    assert [b["id"] for b in batch] == [1, 2]


@pytest.mark.asyncio
async def test_bad_bodies_get_clear_answers(async_client: AsyncClient):
    tok = (await make_token(async_client))["token"]
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    r = await async_client.post("/api/mcp", content=b"{not json", headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700
    assert (await async_client.post("/api/mcp", content=b"", headers=h)).status_code == 400
    assert (await async_client.post("/api/mcp", content=b" " * (1024 * 1024 + 1), headers=h)).status_code == 413
    nope = (await call(async_client, tok, rpc("tools/frobnicate"))).json()
    assert nope["error"]["code"] == -32601
    g = await async_client.get("/api/mcp", headers={"Authorization": f"Bearer {tok}"})
    assert g.status_code == 405 and g.headers["allow"] == "POST"
    assert (await async_client.delete("/api/mcp", headers={"Authorization": f"Bearer {tok}"})).status_code == 405


@pytest.mark.asyncio
async def test_last_used_is_recorded_and_the_audit_log_names_the_call_but_not_the_token(async_client: AsyncClient, tmp_path):
    t = await make_token(async_client)
    await call(async_client, t["token"], rpc("tools/call", {"name": "list_runs", "arguments": {}}))
    listing = (await async_client.get("/api/settings/mcp", headers=H)).json()
    assert listing["tokens"][0]["last_used_at"] is not None
    log = (tmp_path / "mcp_audit.jsonl").read_text()
    assert "list_runs" in log and t["token"] not in log


@pytest.mark.asyncio
async def test_the_settings_view_lists_the_tools_and_says_it_is_read_only(async_client: AsyncClient):
    v = (await async_client.get("/api/settings/mcp", headers=H)).json()
    assert v["available"] is True and v["read_only"] is True and v["endpoint_path"] == "/api/mcp" and len(v["tools"]) == 14 and v["active"] == 0
