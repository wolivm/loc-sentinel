# Nimbus — Brazilian Portuguese (pt-BR) content guidelines

> Nimbus is a fictional notes & habit-tracking app. These guidelines define how Nimbus speaks to
> the **Brazilian** market. The engine treats this file as part of the grounded Source of Truth.

## Voice & register
- **Informal address: use *você* (implied), warm and friendly.** Brazilian consumer apps speak to
  the user like a helpful friend. Never use *tu* or the formal *o senhor / a senhora*.
- Encouraging and human. A little warmth is welcome; never stiff or bureaucratic.
- Active voice, short sentences.

## Capitalization
- **Sentence case** — only the first word and proper nouns are capitalized.
- Do **not** Title-Case ("Nova nota", not "Nova Nota").

## Punctuation (Brazilian conventions; universal engine rules also apply)
- Standard quotation marks: " … " (or « » in formal prose — not for UI).
- Decimal separator is a **comma**; thousands separator is a **period**: `1.000` notas, `3,5` MB.
- A single standalone UI sentence takes **no** terminal period. Multi-sentence strings get a period
  on each sentence. (Universal rule — enforced by the QA linter.)
- At most one `!` in a string; **never** an `!` in an error/failure message. (Brazilian copy loves
  exclamation — the linter keeps it in check.)
- No em dash (—) and no ellipsis (…).

## Numbers, dates, currency
- Date: `DD/MM/AAAA` (e.g. `24/06/2026`). Time: 24-hour (`14:30`).
- Currency: `R$ 1.234,56` (symbol before the amount, with a space).

## Terminology
- Locked terms live in `glossary.csv` (kind = `locked`) and **must** be used exactly.
- Avoid the words in `glossary.csv` (kind = `avoid`) — the linter warns when they appear.
- The product name **Nimbus** is never translated.

## Placeholders
- Preserve every placeholder and markup verbatim: `%@`, `%lld`, `%1$@`, `%d`, `%s`, `{name}`,
  `{count}`, `<tag>`, `\n`, and emojis — same token, same count, same spacing. (Enforced by QA.)
