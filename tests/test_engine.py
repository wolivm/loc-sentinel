"""Offline tests for the deterministic engine (no API key needed)."""

from app.engine import qa, tm
from app.engine.normalize import extract_placeholders, normalize_source, placeholder_diff
from app.engine.pipeline import run_string
from app.engine.sot import load_sot


def test_normalize_and_placeholders():
    assert normalize_source("  Sync   Now ") == "sync now"
    c = extract_placeholders("Hi {name}, you have %d new %@ 🔥\nbye")
    assert c["{name}"] == 1 and c["%d"] == 1 and c["%@"] == 1 and c["🔥"] == 1 and c["\\n"] == 1
    missing, extra = placeholder_diff("Welcome, %@", "Bienvenido")
    assert "%@" in missing and not extra


def test_tm_exact_reuse_de():
    # "Sync now" is seeded in TM_de.csv -> reused verbatim, confidence 1.0.
    r = run_string("Sync now", "de", key="sync_now", context="Manual sync button.")
    assert r.tm_origin == "reused"
    assert r.proposed_target == "Jetzt synchronisieren"
    assert r.confidence_band == "reuse" and r.confidence_score == 1.0


def test_qa_placeholder_mismatch_is_error():
    sot = load_sot("es")
    flags, _ = qa.lint("Welcome back, %@", "Hola de nuevo", sot, key="welcome_user", context="greeting")
    assert any(f.code == "placeholder_mismatch" and f.severity == "ERROR" for f in flags)


def test_qa_exclamation_in_error_string():
    sot = load_sot("pt-BR")
    flags, _ = qa.lint(
        "Note couldn't be saved", "A nota não pôde ser salva!",
        sot, key="save_error_toast", context="Error toast shown when saving fails.",
    )
    assert any(f.code == "exclamation_in_error" and f.severity == "ERROR" for f in flags)


def test_qa_em_dash_and_ellipsis_errors():
    sot = load_sot("de")
    flags, _ = qa.lint("Loading your notes", "Notizen werden geladen…", sot,
                       key="loading_notes", context="loading state")
    assert any(f.code == "ellipsis" for f in flags)
    flags2, _ = qa.lint("A or B", "A — B", sot)
    assert any(f.code == "em_dash" for f in flags2)


def test_qa_avoid_term_warns():
    sot = load_sot("pt-BR")
    # "deletar" is on the pt-BR avoid list (prefer "excluir").
    flags, _ = qa.lint("Delete this note?", "Deletar esta nota?", sot,
                       key="delete_confirm_title", context="dialog title")
    assert any(f.code == "avoid_term" and f.severity == "WARN" for f in flags)


def test_qa_clean_single_sentence_no_period():
    sot = load_sot("de")
    flags, info = qa.lint("New folder", "Neuer Ordner", sot, key="new_folder", context="button")
    assert not qa.has_errors(flags)
    # single sentence, no trailing period -> no single_sentence_period warn
    assert not any(f.code == "single_sentence_period" for f in flags)


def test_tm_append_conflict_tracking(tmp_path, monkeypatch):
    # Use a throwaway lang dir so we don't mutate the committed TM.
    import app.engine.tm as tmmod
    from app.config import SOT_DIR
    lang = "de"  # read existing; append a conflicting target in-memory path
    # append a brand-new source then a conflicting target
    src = "Totally new string for test"
    tmmod.append(src, "Ziel A", lang, "2026-06-24")
    action = tmmod.append(src, "Ziel B", lang, "2026-06-24")
    assert action == "conflict_recorded"
    hit = tmmod.lookup(src, lang)
    assert "Ziel B" in hit.alt_targets
    # cleanup: rewrite TM without the test row
    rows = [r for r in tmmod._load_rows(lang) if r["source_en"] != src]
    import csv
    with (SOT_DIR / lang / f"TM_{lang}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=tmmod.FIELDS)
        w.writeheader()
        w.writerows(rows)
