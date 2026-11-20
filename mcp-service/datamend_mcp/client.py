"""Client of the DataMend platform's REST API (the only way this service touches the platform). Standard library only.

Authentication: send the platform's ADMIN_TOKEN, or sign in with the admin email and password (a session token is kept in memory and renewed once
on a 401). Only GET requests are ever made: ``get`` is the sole method, so no tool here can change platform data.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from .config import Settings

MAX_BODY = 2 * 1024 * 1024


class DataMendError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"DataMend answered {status}: {detail}")
        self.status, self.detail = status, detail


class DataMendClient:
    def __init__(self, cfg: Settings) -> None:
        cfg.validate_url()
        self.cfg, self._token, self._lock = cfg, cfg.datamend_admin_token, threading.Lock()

    # -- auth
    def _login(self) -> None:
        if not (self.cfg.datamend_admin_email and self.cfg.datamend_admin_password):
            return
        body = json.dumps({"email": self.cfg.datamend_admin_email, "password": self.cfg.datamend_admin_password}).encode()
        req = urllib.request.Request(self.cfg.datamend_base_url + "/api/auth/login", data=body, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.datamend_timeout_s) as r:
                self._token = json.loads(r.read(MAX_BODY))["token"]
        except urllib.error.HTTPError as e:
            raise DataMendError(e.code, "sign-in to DataMend failed (check DATAMEND_ADMIN_EMAIL / DATAMEND_ADMIN_PASSWORD)")
        except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
            raise DataMendError(0, f"cannot reach DataMend for sign-in ({type(e).__name__})")

    # -- the one request method
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if not path.startswith("/api/"):
            raise ValueError("only /api/ paths of the platform are reachable")
        q = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        url = self.cfg.datamend_base_url + path + ("?" + urllib.parse.urlencode(q) if q else "")
        for attempt in (0, 1):
            with self._lock:
                if not self.cfg.datamend_read_token and not self._token and attempt == 0:
                    self._login()
                token = self._token
            headers = {"Accept": "application/json"}
            if self.cfg.datamend_read_token:                  # the read-only credential wins: this server never needs the admin one
                headers["Authorization"] = "Bearer " + self.cfg.datamend_read_token
            elif token:
                headers["X-Admin-Token"] = token
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method="GET"), timeout=self.cfg.datamend_timeout_s) as r:
                    raw = r.read(MAX_BODY + 1)
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 0 and self.cfg.datamend_admin_email:
                    with self._lock:
                        self._token = ""
                        self._login()
                    continue
                try:
                    detail = json.loads(e.read(4096)).get("detail", "")
                except Exception:
                    detail = ""
                raise DataMendError(e.code, str(detail)[:200] or e.reason)
            except (urllib.error.URLError, OSError) as e:
                raise DataMendError(0, f"cannot reach DataMend at {self.cfg.datamend_base_url} ({type(e).__name__})")
            if len(raw) > MAX_BODY:
                raise DataMendError(502, "response larger than 2 MB refused")
            try:
                return json.loads(raw)
            except ValueError:
                raise DataMendError(502, "DataMend did not return JSON")
        raise DataMendError(401, "DataMend refused the credentials")
