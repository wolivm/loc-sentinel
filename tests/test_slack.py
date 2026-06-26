"""Slack resolution + card-building tests (offline, no Slack/Crowdin)."""

import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    import app.config as config
    import app.planner.db as db
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "s.db")
    db._conn = None
    db.init_db(tmp_path / "s.db")
    db._conn = db.get_conn(tmp_path / "s.db")
    yield
    db._conn = None


def _make_unit(lang="de", source="Some brand new source", target="Irgendein Ziel"):
    from app.planner import tickets
    tid = tickets.create_ticket(type="string_translation", source="test", target_lang=lang)
    tickets.transition(tid, "triaged", actor="x")
    tickets.transition(tid, "in_progress", actor="x")
    uid = tickets.add_unit(ticket_id=tid, source_en=source, key="k", proposed_target=target,
                           confidence="high", confidence_score=0.9, tm_origin="new",
                           provenance={"confidence_badge": "🟢", "translation_origin": "model"})
    tickets.transition(tid, "awaiting_review", actor="x")
    return tid, uid


def test_approve_learns_to_tm(fresh_db, monkeypatch):
    import app.slack.actions as actions
    recorded = {}
    monkeypatch.setattr(actions.tm, "append",
                        lambda s, t, l, d: recorded.update(source=s, target=t, lang=l) or "new")
    tid, uid = _make_unit(target="Notiz speichern")
    out = actions.finalize_unit(uid, status="approved", final_target="Notiz speichern", actor="@willian")
    assert out["resolved"]["status"] == "approved"
    assert recorded == {"source": "Some brand new source", "target": "Notiz speichern", "lang": "de"}
    from app.planner import tickets
    assert tickets.get_ticket(tid)["status"] == "done"


def test_edit_learns_edited_pair(fresh_db, monkeypatch):
    import app.slack.actions as actions
    recorded = {}
    monkeypatch.setattr(actions.tm, "append",
                        lambda s, t, l, d: recorded.update(target=t) or "new")
    tid, uid = _make_unit(target="Salvar Sua Nota")
    out = actions.finalize_unit(uid, status="edited", final_target="Salvar sua nota", actor="@willian")
    assert out["unit"]["final_target"] == "Salvar sua nota"
    assert recorded["target"] == "Salvar sua nota"  # the EDITED pair is learned


def test_reject_routes_and_does_not_learn(fresh_db, monkeypatch):
    import app.slack.actions as actions
    called = {"n": 0}
    monkeypatch.setattr(actions.tm, "append", lambda *a, **k: called.update(n=called["n"] + 1))
    tid, uid = _make_unit()
    out = actions.finalize_unit(uid, status="rejected", final_target="x", actor="@willian",
                                reason="wrong register")
    assert out["resolved"]["status"] == "rejected"
    assert called["n"] == 0  # rejecting must NOT append to TM
    from app.planner import tickets
    assert tickets.get_ticket(tid)["status"] == "rejected"


def test_approve_idempotent(fresh_db, monkeypatch):
    import app.slack.actions as actions
    monkeypatch.setattr(actions.tm, "append", lambda *a, **k: "new")
    tid, uid = _make_unit()
    actions.finalize_unit(uid, status="approved", final_target="A", actor="@a")
    out2 = actions.finalize_unit(uid, status="approved", final_target="B", actor="@b")
    assert out2["resolved"]["note"] == "already resolved"


def test_build_card_shapes_and_color():
    from app.slack.cards import build_card
    ticket = {"id": 1, "target_lang": "es", "type": "string_translation"}
    unit = {"id": 9, "key": "loading_notes", "source_en": "Loading your notes",
            "proposed_target": "Cargando tus notas…", "final_target": "",
            "confidence": "low", "confidence_score": 0.2, "tm_origin": "new",
            "qa_flags": [{"severity": "ERROR", "code": "ellipsis", "message": "Ellipsis (…) is not allowed."}],
            "provenance": {"confidence_badge": "🔴", "confidence_color": "red",
                           "translation_origin": "cache", "escalate": True}}
    card = build_card(ticket, unit)
    att = card["attachments"][0]
    assert att["color"] == "#DA3633"  # red color bar for low confidence
    blocks = att["blocks"]
    assert blocks[0]["type"] == "header"
    assert any(b.get("type") == "actions" for b in blocks)
    # resolved card drops the action buttons
    resolved = build_card(ticket, unit, resolved={"status": "rejected", "actor": "@w", "note": "bad"})
    assert not any(b.get("type") == "actions" for b in resolved["attachments"][0]["blocks"])


def test_selfserve_commands(monkeypatch):
    import app.slack.bot as bot
    assert bot._resolve_lang("de") == "de"
    assert bot._resolve_lang("pt") == "pt-BR"
    assert bot._resolve_lang("es-ES") == "es"
    assert bot._resolve_lang("zz") is None
    # with no Crowdin client, the self-serve commands degrade gracefully (no crash)
    monkeypatch.setattr(bot, "get_client", lambda: None)
    assert "isn't configured" in bot._coverage_text(None)
    assert "isn't configured" in bot._pending_text(None)
    assert bot._untranslated_blocks(None)["text"].startswith("⚠️")


def test_channel_routing():
    from app.config import Settings
    s = Settings(_env_file=None, slack_channel_de="C_DE", slack_channel_es="C_ES",
                 slack_loc_channel_id="C_SUMMARY")
    assert s.channel_for("de") == "C_DE"
    assert s.channel_for("es") == "C_ES"
    assert s.channel_for("pt-BR") == "C_SUMMARY"  # unset per-lang → summary fallback
    assert s.summary_channel == "C_SUMMARY"
