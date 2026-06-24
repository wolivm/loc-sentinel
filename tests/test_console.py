"""Console API tests (offline; no key, no TM mutation)."""

from fastapi.testclient import TestClient


def _client():
    from app.web.console import app
    return TestClient(app)


def test_config_lists_markets():
    c = _client()
    cfg = c.get("/api/config").json()
    assert "de" in cfg["langs"]
    formal = [m for m in cfg["markets"] if m["formality"] == "formal"]
    informal = [m for m in cfg["markets"] if m["formality"] == "informal"]
    assert formal and informal  # the market-fit contrast exists


def test_translate_two_markets_differ():
    c = _client()
    r = c.post("/api/translate", json={"text": "You have {count} reminders today",
                                       "key": "reminders_today", "context": "home summary"})
    data = r.json()
    by_lang = {x["lang"]: x for x in data["results"]}
    # formal German uses "Sie", informal pt-BR uses "Você" — fit for each market
    assert "Sie" in by_lang["de"]["proposed_target"]
    assert "Você" in by_lang["pt-BR"]["proposed_target"]
    # placeholder preserved in both
    assert "{count}" in by_lang["de"]["proposed_target"]
    assert "{count}" in by_lang["pt-BR"]["proposed_target"]


def test_translate_es_ellipsis_is_error():
    c = _client()
    r = c.post("/api/translate", json={"text": "Loading your notes", "key": "loading_notes",
                                       "context": "loading state"})
    es = next(x for x in r.json()["results"] if x["lang"] == "es")
    assert es["confidence_band"] == "low"
    assert any(f["code"] == "ellipsis" for f in es["qa_flags"])


def test_samples_served():
    c = _client()
    s = c.get("/api/samples").json()
    assert len(s["strings"]) >= 20
