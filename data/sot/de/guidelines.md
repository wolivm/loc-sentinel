# Nimbus — German (de-DE) content guidelines

> Nimbus is a fictional notes & habit-tracking app. These guidelines define how Nimbus speaks to
> the **German** market. The engine treats this file as part of the grounded Source of Truth.

## Voice & register
- **Formal address: use *Sie* / *Ihr* throughout.** German users of a productivity tool expect a
  respectful, professional register. Never use *du*.
- Calm, competent, encouraging. We are a helpful assistant, not a cheerleader.
- Prefer active voice and short sentences. Avoid filler.

## Capitalization
- **Sentence case** for UI copy (headings, buttons, labels) — only the first word and nouns are
  capitalized, per German orthography (all nouns are capitalized: *Notiz*, *Ordner*, *Erinnerung*).
- Do **not** Title-Case English-style ("Neue Notiz", not "Neue Notiz Erstellen").

## Punctuation (German market conventions; universal engine rules also apply)
- German quotation marks: „ … " (low-high). Do not use straight English quotes.
- Decimal separator is a **comma**; thousands separator is a **period**: `1.000` notes, `3,5` MB.
- A single standalone UI sentence takes **no** terminal period. Multi-sentence strings get a period
  on each sentence. (Universal rule — enforced by the QA linter.)
- At most one `!` in a string; **never** an `!` in an error/failure message.
- No em dash (—) and no ellipsis (…) — use a normal hyphen or rephrase.

## Numbers, dates, currency
- Date: `TT.MM.JJJJ` (e.g. `24.06.2026`). Time: 24-hour (`14:30`).
- Currency: `1.234,56 €` (symbol after the amount, with a non-breaking space).

## Terminology
- Locked terms live in `glossary.csv` (kind = `locked`) and **must** be used exactly.
- Avoid anglicisms listed in `glossary.csv` (kind = `avoid`) — the linter warns when they appear.
- The product name **Nimbus** is never translated or declined oddly; keep it as *Nimbus*.

## Placeholders
- Preserve every placeholder and markup verbatim: `%@`, `%lld`, `%1$@`, `%d`, `%s`, `{name}`,
  `{count}`, `<tag>`, `\n`, and emojis — same token, same count, same spacing. (Enforced by QA.)
