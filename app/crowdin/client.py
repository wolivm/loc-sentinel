"""Crowdin API v2 client (verified endpoints, Nov 2025 docs).

  GET  /projects/{id}/strings                       list source strings
  POST /projects/{id}/translations  {stringId, languageId, text}   add translation
  GET  /projects/{id}/translations?stringId=&languageId=           list translations
  POST /projects/{id}/approvals     {translationId}                approve
  POST /projects/{id}/translations/builds                          build/export

Retry with exponential backoff + jitter, honoring Retry-After (LIMITATIONS:
Crowdin rate limits). Tokens are never logged.
"""

from __future__ import annotations

import logging
import time

import httpx

from app.config import get_settings, redact

log = logging.getLogger("crowdin")

# Deterministic-ish jitter without Math.random (which is unavailable in some
# sandboxes anyway): cycle through a small offset table by attempt.
_JITTER = [0.0, 0.13, 0.29, 0.07, 0.21]


class CrowdinError(RuntimeError):
    pass


class CrowdinClient:
    def __init__(self, token: str | None = None, project_id: str | None = None,
                 base: str | None = None, max_retries: int = 4):
        s = get_settings()
        self.token = token or s.crowdin_api_token
        self.project_id = project_id or s.crowdin_project_id
        self.base = (base or s.crowdin_api_base).rstrip("/")
        self.max_retries = max_retries
        if not self.token or not self.project_id:
            raise CrowdinError("Crowdin not configured (CROWDIN_API_TOKEN / CROWDIN_PROJECT_ID).")
        log.info("Crowdin client: project=%s token=%s base=%s",
                 self.project_id, redact(self.token), self.base)

    # --- low level ---------------------------------------------------------
    def _request(self, method: str, path: str, **kw) -> dict:
        url = f"{self.base}{path}"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                r = httpx.request(method, url, headers=headers, timeout=30, **kw)
            except httpx.HTTPError as e:
                last_exc = e
                self._sleep(attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After", 0)) or self._backoff(attempt)
                log.warning("Crowdin %s %s → %s; retry in %.1fs", method, path, r.status_code, wait)
                time.sleep(wait)
                continue
            if r.status_code >= 400:
                raise CrowdinError(f"{method} {path} → {r.status_code}: {r.text[:300]}")
            return r.json() if r.text else {}
        raise CrowdinError(f"{method} {path} failed after {self.max_retries} retries: {last_exc}")

    def _backoff(self, attempt: int) -> float:
        return min(1.0 * (2 ** attempt) + _JITTER[attempt % len(_JITTER)], 30.0)

    def _sleep(self, attempt: int) -> None:
        time.sleep(self._backoff(attempt))

    # --- endpoints ---------------------------------------------------------
    def list_strings(self, file_id: int | None = None, limit: int = 100) -> list[dict]:
        params = {"limit": limit}
        if file_id:
            params["fileId"] = file_id
        data = self._request("GET", f"/projects/{self.project_id}/strings", params=params)
        return [item["data"] for item in data.get("data", [])]

    def get_string(self, string_id: int) -> dict:
        data = self._request("GET", f"/projects/{self.project_id}/strings/{string_id}")
        return data.get("data", {})

    def add_translation(self, string_id: int, language_id: str, text: str) -> dict:
        """Add a translation (a proposal — NOT approved). Returns the translation data."""
        body = {"stringId": int(string_id), "languageId": language_id, "text": text}
        data = self._request("POST", f"/projects/{self.project_id}/translations", json=body)
        return data.get("data", {})

    def list_translations(self, string_id: int, language_id: str) -> list[dict]:
        params = {"stringId": int(string_id), "languageId": language_id}
        data = self._request("GET", f"/projects/{self.project_id}/translations", params=params)
        return [item["data"] for item in data.get("data", [])]

    def approve_translation(self, translation_id: int) -> dict:
        body = {"translationId": int(translation_id)}
        data = self._request("POST", f"/projects/{self.project_id}/approvals", json=body)
        return data.get("data", {})

    def approve_text(self, string_id: int, language_id: str, text: str) -> dict:
        """Convenience: ensure `text` is the translation, then approve it.

        Finds an existing matching translation (or adds one) and approves it —
        this is what the Slack Approve/Edit actions call."""
        translations = self.list_translations(string_id, language_id)
        match = next((t for t in translations if t.get("text") == text), None)
        if match is None:
            match = self.add_translation(string_id, language_id, text)
        return self.approve_translation(match["id"])

    def build(self) -> dict:
        """Trigger a translations build/export (= 'flow to production')."""
        data = self._request("POST", f"/projects/{self.project_id}/translations/builds", json={})
        return data.get("data", {})

    # --- stakeholder self-serve reads --------------------------------------
    def language_progress(self) -> list[dict]:
        """Per-language translation/approval progress (for /loc coverage & /loc pending).
        Each item: {languageId, translationProgress, approvalProgress, phrases:{total,translated,approved}}."""
        data = self._request("GET", f"/projects/{self.project_id}/languages/progress",
                             params={"limit": 100})
        return [item["data"] for item in data.get("data", [])]

    # --- demo string injection (dedicated file, never the GitHub-managed one) --
    def _upload_storage(self, filename: str, content: bytes) -> int:
        url = f"{self.base}/storages"
        headers = {"Authorization": f"Bearer {self.token}",
                   "Crowdin-API-FileName": filename,
                   "Content-Type": "application/octet-stream"}
        r = httpx.post(url, headers=headers, content=content, timeout=30)
        if r.status_code >= 400:
            raise CrowdinError(f"POST /storages → {r.status_code}: {r.text[:200]}")
        return r.json()["data"]["id"]

    def ensure_file(self, name: str) -> int:
        """Find a project file by name, or create an empty JSON file. Returns fileId."""
        data = self._request("GET", f"/projects/{self.project_id}/files", params={"limit": 500})
        for item in data.get("data", []):
            if item["data"].get("name") == name:
                return item["data"]["id"]
        storage_id = self._upload_storage(name, b"{}\n")
        created = self._request("POST", f"/projects/{self.project_id}/files",
                                json={"storageId": storage_id, "name": name})
        return created["data"]["id"]

    def add_source_string(self, file_id: int, identifier: str, text: str, context: str = "") -> dict:
        body = {"fileId": int(file_id), "identifier": identifier, "text": text}
        if context:
            body["context"] = context
        data = self._request("POST", f"/projects/{self.project_id}/strings", json=body)
        return data.get("data", {})

    def delete_source_string(self, string_id: int) -> None:
        self._request("DELETE", f"/projects/{self.project_id}/strings/{int(string_id)}")

    def delete_file(self, file_id: int) -> None:
        self._request("DELETE", f"/projects/{self.project_id}/files/{int(file_id)}")

    def untranslated_source_strings(self, language_id: str, limit: int = 200) -> list[dict]:
        """Source strings with NO translation yet in `language_id` (for /loc untranslated
        + [Localize now]). O(N) — fine for a project of this size; a CroQL filter
        (`count of translations where (language = "xx") = 0`) would scale this."""
        out = []
        for s in self.list_strings(limit=limit):
            sid = s.get("id")
            if not s.get("text"):
                continue
            try:
                if not self.list_translations(int(sid), language_id):
                    out.append({"id": sid, "identifier": s.get("identifier", ""),
                                "text": s.get("text", ""), "context": s.get("context", "")})
            except CrowdinError:
                continue
        return out


def get_client() -> CrowdinClient | None:
    """Return a client if Crowdin is configured, else None (demo-safe)."""
    try:
        return CrowdinClient()
    except CrowdinError as e:
        log.info("Crowdin disabled: %s", e)
        return None
