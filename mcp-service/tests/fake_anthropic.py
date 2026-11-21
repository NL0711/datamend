"""A local stand-in for POST /v1/messages that speaks the Messages API shapes. It first asks for a tool, then answers using the tool result.
This tests the narrator's loop and guards, NOT the behaviour of a real model."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class State:
    requests = []
    mode = "tool_then_answer"      # tool_then_answer | direct | loop_forever | http_500 | ask_unknown_tool


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        State.requests.append({"headers": dict(self.headers), "body": body})
        if self.path != "/v1/messages":
            return self._send(404, {})
        if State.mode == "http_500":
            return self._send(500, {"error": "boom"})
        last = body["messages"][-1]
        got_result = isinstance(last["content"], list) and last["content"] and last["content"][0].get("type") == "tool_result"
        if State.mode == "loop_forever" or (State.mode in ("tool_then_answer", "ask_unknown_tool") and not got_result):
            name = "delete_everything" if State.mode == "ask_unknown_tool" else "get_row_context"
            return self._send(200, {"stop_reason": "tool_use", "content": [{"type": "text", "text": "Let me look."},
                                                                          {"type": "tool_use", "id": "tu_1", "name": name, "input": {"run_id": 1, "row_id": 101}}]})
        if got_result:
            text = "Context fetched: " + ("ERROR " if last["content"][0].get("is_error") else "") + last["content"][0]["content"][:60]
        else:
            text = "The counter jumped by 120 mm between two readings, which is above the design-choice limit of 50."
        self._send(200, {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]})


def start():
    State.requests, State.mode = [], "tool_then_answer"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
