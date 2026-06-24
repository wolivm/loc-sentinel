"""Business-impact analytics over the ticket store (stretch goal §18).

  python -m app.analytics

Prints the numbers a PM cares about: % auto-handled, TM hit rate, avg confidence,
edits learned, escalation rate. Reads whatever the pipeline has processed so far
(run scripts/simulate_event.py or the live webhook to populate it).
"""

from __future__ import annotations

from collections import Counter

from app.planner.db import get_conn
from app.planner.tickets import recent_audit


def compute() -> dict:
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM units").fetchall()]
    n = len(rows)
    bands = Counter(r["confidence"] for r in rows)
    statuses = Counter(r["status"] for r in rows)
    avg_conf = sum(r["confidence_score"] or 0 for r in rows) / n if n else 0.0
    auto = bands["reuse"] + bands["high"]
    return {
        "units": n,
        "bands": dict(bands),
        "statuses": dict(statuses),
        "auto_handled_pct": (auto / n * 100) if n else 0.0,
        "tm_hit_rate_pct": (bands["reuse"] / n * 100) if n else 0.0,
        "avg_confidence": avg_conf,
        "escalation_pct": (bands["low"] / n * 100) if n else 0.0,
        "edits_learned": statuses.get("edited", 0),
        "approvals": statuses.get("approved", 0),
        "rejects": statuses.get("rejected", 0),
        "tickets": conn.execute("SELECT COUNT(*) c FROM tickets").fetchone()["c"],
    }


def main() -> None:
    m = compute()
    if m["units"] == 0:
        print("No units yet. Populate the store first, e.g.:")
        print("  python scripts/simulate_event.py --lang pt-BR")
        return
    print("📊 Loc Sentinel — business impact\n")
    print(f"  Tickets processed        {m['tickets']}")
    print(f"  Strings (units)          {m['units']}")
    print(f"  Auto-handled (reuse+high) {m['auto_handled_pct']:.0f}%   ← rubber-stampable")
    print(f"  TM hit rate              {m['tm_hit_rate_pct']:.0f}%   ← free, instant, consistent")
    print(f"  Avg confidence           {m['avg_confidence']:.2f}")
    print(f"  Escalation rate (low)    {m['escalation_pct']:.0f}%   ← caught by QA, sent to a human")
    print(f"  Edits learned → TM       {m['edits_learned']}")
    print(f"  Approved / Rejected      {m['approvals']} / {m['rejects']}")
    print(f"\n  Confidence mix           {m['bands']}")
    print(f"  Review outcomes          {m['statuses']}")
    audit = recent_audit(5)
    if audit:
        print("\n  Recent activity:")
        for a in audit:
            print(f"    {a['at']}  {a['entity']}  {a['from_state']}→{a['to_state']}  {a['actor']}")


if __name__ == "__main__":
    main()
