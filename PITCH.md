# 🛡️ Loc Sentinel — the one-screen pitch

## The problem
Localization is a flood of repetitive, low-judgement work. The **same** English strings get
re-translated slightly differently every release — inconsistency, glossary drift, endless review
cycles — while stakeholders wait on a human just to ask "translate this" or "what's the status?"
Pure machine translation is fast but untrustworthy (wrong formality, broken placeholders, ignored
terminology), so humans re-check everything and the speed evaporates.

## The product
**A ~99%-automated localization pipeline with exactly ONE human touchpoint: a single rubber-stamp
in Slack.** Translations are produced by a deterministic, guidelines-grounded engine — the model is
*on a leash*, verified by machine-checkable rules — so the human is mostly approving, not fixing.

## Why a business person should care

| Lever | Today | With Loc Sentinel |
|---|---|---|
| **Time per string** | minutes of human translate + review | seconds to glance + Approve |
| **Repeat strings** | re-translated, drift creeps in | reused **verbatim** from TM (free, instant, consistent) |
| **Review cycles** | back-and-forth threads | one Slack card, one click |
| **Consistency** | "depends who did it" | same English → same target, **always** |
| **Stakeholder self-serve** | ping a human, wait | `/loc request`, `/loc status` in Slack |
| **Trust in MT** | "re-check everything" | bad output is **blocked by code** before a human sees it |

## The headline strengths (mapped to what the judges said they want)
- **Practical & real:** runs against real Crowdin + Slack, solving an actual loc-team pain end to end.
- **Deliberate, not left to the model:** TM-first reuse, glossary enforcement, a deterministic QA
  gate, confidence scoring — the model proposes, *rules dispose*. (See DECISIONS.md.)
- **Market fit & context:** each market is a data folder encoding its formality, punctuation, and
  locked terms. The same English string renders correctly *and differently* per market.
- **Choice & scalability:** add a market = drop a folder; add a request type = add a YAML row. No
  code change. Stateless engine, prompt-cached Source of Truth, idempotent webhook workers.
- **Self-aware:** we tell you where it's fragile, unprompted. (See LIMITATIONS.md.)

## The "wow" in the demo
1. Upload to Crowdin → a Slack review card appears automatically with confidence + QA + provenance.
2. **Approve** (rubber-stamp), **Edit** (it *learns* → TM), **Reject** (routes to a human).
3. **One** English string, **two** markets, two correct renderings (formal 🇩🇪 vs informal 🇧🇷).
4. Add a market / request type by editing **data only** — live, no code.
5. **Try it yourself**: a hosted, key-less console anyone can click.

## The ask
Give the loc team back the 99% of their day that is rubber-stampable, and give every stakeholder a
self-serve front door — without giving up a single quality guarantee.
