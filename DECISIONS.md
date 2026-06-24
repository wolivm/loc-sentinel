# DECISIONS — deliberate engineering choices

> Judging criterion (c): *"making deliberate choices is quite important — that they don't just
> leave it to a model."* This log records every intentional choice, **why**, and the alternative
> we rejected. The theme: **the model is steered, not steering.**

Each entry: **Decision · Why · Rejected alternative.**

---

### 1. TM-first, verbatim reuse (deterministic core)
- **Decision:** Before any model call, look up the normalized English source in the Translation
  Memory (CSV). An exact hit is reused **verbatim** with confidence `1.0` — never re-translated.
- **Why:** The single biggest loc pain is *inconsistency* — the same string translated three ways.
  Verbatim reuse makes "same English → same target, always" a guarantee, not a hope. It's also
  free and instant (no token cost, no latency).
- **Rejected:** Always calling the LLM (even with low temperature). Rejected because identical
  inputs can still yield drift across releases, and it burns money/latency on solved work.

### 2. The Source of Truth is *data*, not code
- **Decision:** A language = a folder: `guidelines.md` + `glossary.csv` + `TM_<lang>.csv`. Adding a
  market or improving quality means editing **data**, never engine code.
- **Why:** Satisfies the hackathon's "flexible / scalable / market-fit" requirements directly, and
  lets a non-engineer (the loc manager) own quality. The engine stays stateless and generic.
- **Rejected:** Per-language code branches / prompt templates baked into Python. Rejected because
  it doesn't scale to N markets and locks quality behind engineering.

### 3. Glossary enforcement is *checked*, not *requested*
- **Decision:** Locked glossary terms are injected into the prompt **and** verified in the QA
  linter after generation. Coverage feeds the confidence score.
- **Why:** "Please use these terms" is a suggestion to a model; a post-hoc check is a guarantee.
- **Rejected:** Trusting the model to honor the glossary from the prompt alone.

### 4. Deterministic QA linter with an ERROR / WARN split
- **Decision:** Every model output passes a rule-based linter before it reaches Crowdin or Slack.
  **ERROR** (placeholder mismatch, `!` in an error string, >1 `!`, em dash, ellipsis) blocks or
  escalates. **WARN** (sentence/period heuristic, ALL-CAPS / Title Case, glossary "Avoid" term) is
  surfaced for the human but **never auto-"fixed."**
- **Why:** Trust comes from *machine-checkable* guarantees. The ERROR/WARN split encodes a real
  judgement: some violations are unambiguous and must block; others are heuristics a human should
  judge — auto-fixing them would be the model "steering" again.
- **Rejected:** (a) Asking the model to self-check — non-deterministic. (b) Auto-fixing WARNs —
  removes the human's judgement and risks "correcting" correct text.

### 5. Constrain *and verify* the LLM — never trust it blindly
- **Decision:** The model gets the Guidelines + Glossary as a stable system prefix and strict
  output rules; its output is then validated by the deterministic linter. Only linter-clean output
  is allowed downstream.
- **Why:** This is the whole pitch. Hallucination/format-break risk is mitigated by code, not by
  bigger prompts. The model proposes; deterministic rules dispose.
- **Rejected:** "Prompt engineering only" — relying on instructions without a verification gate.

### 6. Prompt caching on the Source-of-Truth prefix
- **Decision:** The large, stable Guidelines+Glossary block is sent as a cached system prefix
  (Anthropic prompt caching); only the per-string user turn varies.
- **Why:** The SoT is large and reused on every miss. Caching cuts cost and latency materially at
  scale, and keeps grounding identical across calls (more determinism).
- **Rejected:** Re-sending the full SoT uncached every call. Rejected on cost + latency.

### 7. Confidence score *modulates the review*, but the human is never removed
- **Decision:** Confidence = `1.0` for TM reuse; **high** for new translations that pass all ERROR
  gates with full glossary coverage and no WARN; **medium** for any WARN; **low** for any unresolved
  ERROR → escalate. The score changes how the Slack card is framed (green vs amber) and routing —
  but there is **always exactly one human review.**
- **Why:** "99% automated, 1 human touchpoint" is the differentiator. Confidence directs human
  *attention*, it doesn't replace human *authority*.
- **Rejected:** Auto-approving high-confidence strings with no human. Rejected because a single
  silent bad auto-approval destroys trust — the one human review is cheap insurance.

### 8. Request types & routing are a config registry (YAML)
- **Decision:** `config/request_types.yaml` maps a request type → handler (`auto` runs the RAG
  pipeline; `human` opens a ticket and @-routes in Slack). New types are added as **rows**, not code.
- **Why:** "Flexible: supports an increasing number of use cases automatically" — by data. Also
  encodes the human-in-the-loop rule declaratively (SLA, default assignee per type).
- **Rejected:** `if request_type == ...` chains in code. Doesn't scale; needs a deploy per new type.

### 9. Idempotent, signature-verified webhook
- **Decision:** The Crowdin webhook handler verifies the signature and dedupes by event id, so a
  replayed/duplicate event is a no-op, never a double-translate or a crash.
- **Why:** Webhooks retry. A demo (or production) must survive duplicates gracefully.
- **Rejected:** Trusting one-delivery-exactly. Webhooks don't guarantee that.

### 10. SQLite now, Postgres-ready; stateless engine
- **Decision:** Tickets/units/audit in SQLite via a thin repository layer; the translation engine
  holds no per-request state. TM is a CSV (the system of record + a Crowdin TM seed).
- **Why:** Zero-setup for a hackathon, but the repository boundary + stateless engine mean swapping
  to Postgres and scaling workers horizontally is a config change, not a rewrite.
- **Rejected:** An ORM + Postgres from day one (setup tax for a 2-day build) or in-memory state
  (loses tickets on restart, can't scale out).

### 11. Demo mode = a committed translation cache (honest, not faked)
- **Decision:** Sample-string translations are committed as a cache so the public Console works with
  **no API key**; new/arbitrary strings require a (bring-your-own) key. The cache is a curated seed
  (`data/cache/_curated.json`) authored to the same SoT guidelines; `scripts/build_cache.py`
  regenerates it from the **live model** when a key is set. Either way it is genuine,
  guideline-following text — never canned nonsense.
- **Two entries deliberately preserve common *raw model* mistakes** so the QA gates fire visibly in
  the demo: `es/loading_notes` adds an ellipsis (an extremely common model habit → caught by the
  **ERROR** gate), and `pt-BR/save_button` is Title-Cased (→ caught by the **WARN** gate). These are
  exactly the failure modes the linter exists to catch; in production it blocks them before Slack.
  This is labelled here and in LIMITATIONS — not hidden.
- **Why:** Lets judges/peers try the *real* deterministic pipeline (TM, QA, market rendering) in 30
  seconds with zero setup — without exposing our key, and while still demonstrating the gates working.
- **Rejected:** (a) Requiring everyone to bring a key (kills the "just try it" magic). (b) A mock
  translator that returns canned nonsense (dishonest; QA gates wouldn't fire on real text). (c) A
  perfectly-clean cache (then the gates never visibly fire and the trust story is invisible).
