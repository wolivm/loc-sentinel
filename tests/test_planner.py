"""Planner + triage tests (offline; uses TM-hit strings so no API key needed)."""

import importlib

import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    # Point the DB at a temp file and reset the cached connection.
    import app.config as config
    import app.planner.db as db
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    db._conn = None
    db.init_db(tmp_path / "test.db")
    # also reset the module-level connection target
    db._conn = db.get_conn(tmp_path / "test.db")
    yield
    db._conn = None


def test_triage_routes_auto_vs_human():
    from app.planner import triage
    assert triage.classify_event("string.added").handler == "auto"
    assert triage.classify_event("file.added").handler == "auto"
    assert triage.classify_event("totally.unknown.event").handler == "human"
    assert triage.classify_text("we need a new language for Polish").handler == "human"
    assert triage.classify_text("please translate this string").handler == "auto"


def test_state_machine_rejects_illegal_transition(fresh_db):
    from app.planner import tickets
    tid = tickets.create_ticket(type="string_translation", source="cli")
    with pytest.raises(ValueError):
        tickets.transition(tid, "approved", actor="x")  # new → approved illegal
    tickets.transition(tid, "triaged", actor="x")
    tickets.transition(tid, "in_progress", actor="x")
    assert tickets.get_ticket(tid)["status"] == "in_progress"


def test_orchestrator_hero_flow_tm_reuse(fresh_db):
    from app import orchestrator
    out = orchestrator.open_translation_ticket(
        strings=[
            {"source_en": "Sync now", "key": "sync_now", "context": "button"},
            {"source_en": "Settings", "key": "settings_title", "context": "title"},
        ],
        lang="de", source="test", event_name="string.added",
    )
    assert out["auto"] is True
    assert out["ticket"]["status"] == "awaiting_review"
    assert len(out["units"]) == 2
    assert all(u["tm_origin"] == "reused" for u in out["units"])
    # audit log recorded the transitions
    from app.planner import tickets
    audit = tickets.audit_for(f"ticket:T{out['ticket']['id']}")
    states = [a["to_state"] for a in audit]
    assert "awaiting_review" in states


def test_unit_resolution_idempotent(fresh_db):
    from app.planner import tickets
    tid = tickets.create_ticket(type="string_translation", source="cli")
    uid = tickets.add_unit(ticket_id=tid, source_en="Sync now", proposed_target="Jetzt synchronisieren")
    r1 = tickets.resolve_unit(uid, status="approved", final_target="Jetzt synchronisieren", actor="willian")
    assert r1["changed"] is True
    r2 = tickets.resolve_unit(uid, status="approved", final_target="X", actor="someone")
    assert r2["changed"] is False  # concurrent-approval guard


def test_idempotent_event_marking(fresh_db):
    from app.planner import tickets
    assert tickets.already_processed("evt-1") is False
    tickets.mark_processed("evt-1")
    assert tickets.already_processed("evt-1") is True
