"""Offline checks of the Gemini adapter and the MCP adapter package. NO live call: construction with a made-up key does no network I/O."""
import importlib

import pytest

pytest.importorskip("langchain_google_genai")

from backend.app.agent.gemini_model import AgentNotConnected, GeminiAgentModel


def test_no_key_means_agent_not_connected(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("AGENT_MODEL", "some-model")
    with pytest.raises(AgentNotConnected):
        GeminiAgentModel()


def test_no_model_setting_means_agent_not_connected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real-0000")
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    with pytest.raises(AgentNotConnected):
        GeminiAgentModel()


def test_adapter_constructs_offline_and_satisfies_the_model_protocol():
    from backend.app.agent.interfaces import AgentModel
    m = GeminiAgentModel(api_key="test-key-not-real-0000", model="made-up-model-name")
    assert m.model_id == "made-up-model-name" and isinstance(m, AgentModel)


def test_langchain_mcp_adapters_imports():
    mod = importlib.import_module("langchain_mcp_adapters.client")
    assert hasattr(mod, "MultiServerMCPClient")
    importlib.import_module("langchain_mcp_adapters.tools")


def test_graph_module_has_no_module_level_model_or_network():
    import backend.app.agent.graph as g
    from backend.app.agent.interfaces import AgentModel
    assert not [v for v in vars(g).values() if isinstance(v, AgentModel)]
