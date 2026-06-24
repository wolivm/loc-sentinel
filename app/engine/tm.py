"""Translation Memory — the system of record (one CSV per language).

TM-first is the deterministic core (DECISIONS #1): an exact match on the
normalized English source is reused VERBATIM with confidence 1.0, never
re-translated. Approved/edited pairs are appended so the next identical source
is instant and consistent — "same English source → same target, always."

CSV schema: source_en, target, lang, n_keys, projects, status, date_added, alt_targets
"""

from __future__ import annotations

import csv
import threading
from dataclasses import dataclass
from pathlib import Path

from app.config import SOT_DIR
from app.engine.normalize import normalize_source

FIELDS = [
    "source_en", "target", "lang", "n_keys",
    "projects", "status", "date_added", "alt_targets",
]

# Serialize writes — the CSV is a single-writer store (LIMITATIONS: CSV-as-TM).
_LOCK = threading.Lock()


@dataclass
class TMHit:
    source_en: str
    target: str
    lang: str
    alt_targets: list[str]
    status: str


def _tm_path(lang: str) -> Path:
    return SOT_DIR / lang / f"TM_{lang}.csv"


def _load_rows(lang: str) -> list[dict]:
    path = _tm_path(lang)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def lookup(source_en: str, lang: str) -> TMHit | None:
    """Exact-match lookup on the normalized English source. None = a TM miss."""
    key = normalize_source(source_en)
    for row in _load_rows(lang):
        if normalize_source(row.get("source_en", "")) == key:
            alts = [a for a in (row.get("alt_targets") or "").split("|") if a.strip()]
            return TMHit(
                source_en=row["source_en"],
                target=row["target"],
                lang=lang,
                alt_targets=alts,
                status=row.get("status", "approved"),
            )
    return None


def append(source_en: str, target: str, lang: str, date_added: str,
           projects: str = "Nimbus", status: str = "approved") -> str:
    """Append (or learn from) an approved/edited pair. Returns an action label.

    - New source        → new row.
    - Same source+target → bump n_keys (reuse count).
    - Same source, NEW target → keep the existing target, record the new one in
      alt_targets so conflicts are visible rather than silently overwritten.
    """
    key = normalize_source(source_en)
    path = _tm_path(lang)
    with _LOCK:
        rows = _load_rows(lang)
        action = "new"
        found = False
        for row in rows:
            if normalize_source(row.get("source_en", "")) == key:
                found = True
                if normalize_source(row.get("target", "")) == normalize_source(target):
                    row["n_keys"] = str(int(row.get("n_keys") or 0) + 1)
                    action = "reinforced"
                else:
                    alts = [a for a in (row.get("alt_targets") or "").split("|") if a.strip()]
                    if normalize_source(target) not in [normalize_source(a) for a in alts]:
                        alts.append(target)
                    row["alt_targets"] = "|".join(alts)
                    action = "conflict_recorded"
                break
        if not found:
            rows.append({
                "source_en": source_en, "target": target, "lang": lang,
                "n_keys": "1", "projects": projects, "status": status,
                "date_added": date_added, "alt_targets": "",
            })
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k, "") for k in FIELDS})
    return action


def stats(lang: str) -> dict:
    rows = _load_rows(lang)
    return {
        "rows": len(rows),
        "conflicts": sum(1 for r in rows if (r.get("alt_targets") or "").strip()),
    }
