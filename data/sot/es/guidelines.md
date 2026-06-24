# Nimbus — Spanish (es) content guidelines

> Nimbus is a fictional notes & habit-tracking app. These guidelines define how Nimbus speaks to
> the **Spanish** market. The engine treats this file as part of the grounded Source of Truth.

## Voice & register
- **Informal address: use *tú*.** Modern Spanish consumer apps address the user as *tú*. Avoid the
  formal *usted* unless a string is explicitly legal/formal.
- Clear, friendly, concise.

## Capitalization
- **Sentence case** — only the first word and proper nouns are capitalized.
- Do **not** Title-Case ("Nueva nota", not "Nueva Nota").

## Punctuation (Spanish conventions; universal engine rules also apply)
- **Inverted opening marks are required**: questions open with `¿` and close with `?`; exclamations
  open with `¡` and close with `!`. A question/exclamation that lacks its opening mark is wrong.
- Decimal separator is a **comma**; thousands separator is a **period**: `1.000` notas, `3,5` MB.
- A single standalone UI sentence takes **no** terminal period. Multi-sentence strings get a period
  on each sentence. (Universal rule — enforced by the QA linter.)
- At most one `!` in a string; **never** an `!` (or `¡`) in an error/failure message.
- No em dash (—) and no ellipsis (…).

## Numbers, dates, currency
- Date: `DD/MM/AAAA`. Time: 24-hour (`14:30`).
- Currency: `1.234,56 €` (symbol after the amount, with a space).

## Terminology
- Locked terms live in `glossary.csv` (kind = `locked`) and **must** be used exactly.
- Avoid the words in `glossary.csv` (kind = `avoid`) — the linter warns when they appear.
- The product name **Nimbus** is never translated.

## Placeholders
- Preserve every placeholder and markup verbatim: `%@`, `%lld`, `%1$@`, `%d`, `%s`, `{name}`,
  `{count}`, `<tag>`, `\n`, and emojis — same token, same count, same spacing. (Enforced by QA.)
