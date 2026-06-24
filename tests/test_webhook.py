"""Webhook receiver tests (offline — no Crowdin/Slack needed)."""

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app.config as config
    import app.planner.db as db
    # isolate DB + set a webhook secret
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "wh.db")
    monkeypatch.setenv("CROWDIN_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("TARGET_LANGS", "de")
    config.get_settings.cache_clear()
    db._conn = None
    db.init_db(tmp_path / "wh.db")
    db._conn = db.get_conn(tmp_path / "wh.db")
    from app.main import app
    with TestClient(app) as c:
        yield c
    config.get_settings.cache_clear()
    db._conn = None


def _payload():
    return json.dumps({"events": [{
        "event": "string.added",
        "string": {"id": 5001, "identifier": "sync_now", "text": "Sync now",
                   "context": "Manual sync button."},
    }]}).encode()


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_webhook_rejects_bad_signature(client):
    r = client.post("/webhooks/crowdin", content=_payload(),
                    headers={"X-Crowdin-Signature": "deadbeef", "Content-Type": "application/json"})
    assert r.status_code == 401


def test_webhook_processes_signed_event(client):
    from app.crowdin.webhook import sign_payload
    body = _payload()
    sig = sign_payload(body, "test-secret")
    r = client.post("/webhooks/crowdin", content=body,
                    headers={"X-Crowdin-Signature": sig, "Content-Type": "application/json"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True and data["strings"] == 1
    assert data["results"][0]["lang"] == "de" and data["results"][0]["auto"] is True


def test_webhook_idempotent_replay(client):
    from app.crowdin.webhook import sign_payload
    body = _payload()
    sig = sign_payload(body, "test-secret")
    headers = {"X-Crowdin-Signature": sig, "Content-Type": "application/json"}
    r1 = client.post("/webhooks/crowdin", content=body, headers=headers)
    r2 = client.post("/webhooks/crowdin", content=body, headers=headers)
    assert r1.json().get("strings") == 1
    assert r2.json().get("duplicate") is True  # replay is a no-op
