"""The language-model call, over the Anthropic Messages API (standard library only). Used only when ANTHROPIC_API_KEY is set.

NOT TESTED against the live Anthropic API in this repo's environment: the tests use a local stand-in server that speaks the same request and response
shapes. The key is read from the environment, sent only as the x-api-key header, and never logged.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

from ..config import Settings


class LlmError(RuntimeError):
    pass


class AnthropicLlm:
    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.model = cfg.narrator_llm_model

    def create(self, system: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], timeout: float, max_tokens: int = 900) -> Dict[str, Any]:
        body = {"model": self.model, "max_tokens": max_tokens, "system": system, "messages": messages}
        if tools:
            body["tools"] = tools
        req = urllib.request.Request(self.cfg.anthropic_base_url + "/v1/messages", data=json.dumps(body).encode(), method="POST",
                                     headers={"content-type": "application/json", "x-api-key": self.cfg.anthropic_api_key, "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=max(1.0, timeout)) as r:
                return json.loads(r.read(4 * 1024 * 1024))
        except urllib.error.HTTPError as e:
            raise LlmError(f"the language model API answered HTTP {e.code}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise LlmError(f"the language model API did not answer ({type(e).__name__})")
