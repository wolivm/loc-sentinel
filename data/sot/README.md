# 📚 The Source of Truth (SoT) — how to manage the guidelines

**A market is a data folder.** Everything that makes a translation correct for a market — its
guidelines, its locked terminology, its translation memory — lives under `data/sot/<lang>/`. Adding a
market or improving quality means **editing data here, never engine code.** A content owner (a loc
manager) can own this without an engineer.

> The engine loads these files as the grounded **Source of Truth** for every translation:
> guidelines + glossary become the cached system prompt; the TM is checked first; the QA linter and
> confidence score enforce the rules. (See the repo `README.md` → "Why it's different".)

## Folder layout (one per language)

```
data/sot/
  de/                      ← German market
    guidelines.md          prose rules: voice, register, punctuation, numbers/dates
    market.yaml            machine-readable conventions (formality, separators, quotes, flag)
    glossary.csv           locked term map + an "avoid" list
    TM_de.csv              translation memory (the system of record)
  pt-BR/  …                ← Brazilian Portuguese
  es/     …                ← Spanish
```

The folder name is the language id and **must match `TARGET_LANGS` in `.env`** and the Crowdin
locale (via `market.yaml: crowdin_locale`).

## The four files

### `guidelines.md` — the prose rules
Free-form Markdown describing how the product speaks to this market: voice & register (formal vs
informal), capitalization, punctuation conventions, number/date/currency formats, and any
market-specific do/don'ts. The **entire file is injected** into the translation prompt, so write it
for both a human and the model. (~1–2 pages is plenty.)

### `market.yaml` — machine-readable conventions
Structured fields the engine reads directly (so it can render the prompt and run checks):
```yaml
name: "German (Germany)"
locale: "de"
crowdin_locale: "de"          # the language id Crowdin uses (e.g. es → es-ES)
formality: "formal"           # formal | informal
formality_pronoun: "Sie"      # the pronoun to use
sentence_case: true
decimal_separator: ","
thousands_separator: "."
quotes_open: "„"
quotes_close: "“"
inverted_punctuation: false   # true for Spanish ¿ … ?
flag: "🇩🇪"                     # shown on Slack cards / Console
```

### `glossary.csv` — locked terms + avoid list
Columns: `source,target,kind,note`.
- `kind: locked` — a term that **must** be translated a specific way (brand names, feature names,
  core nouns). The QA linter verifies the target term is present when the English appears in the
  source; coverage feeds the confidence score.
- `kind: avoid` — a word to **avoid in the target** (anglicisms, false friends). `source` is the word
  to avoid, `target` is the preferred replacement; the linter raises a **WARN** if it appears.
```csv
source,target,kind,note
Nimbus,Nimbus,locked,Product name — never translate.
note,Notiz,locked,Core object.
deletar,excluir,avoid,Use "excluir" instead of the anglicism "deletar".
```

### `TM_<lang>.csv` — the translation memory (system of record)
Columns: `source_en,target,lang,n_keys,projects,status,date_added,alt_targets`.
An **exact match** on the normalized English source is reused **verbatim** (confidence 1.0, no model
call). Approving/editing in Slack appends here automatically — that's how the system *learns*. You
can also pre-seed known-good pairs by hand. Conflicting targets for the same source are recorded in
`alt_targets` (pipe-separated) instead of silently overwritten.

## How to… (common tasks)

**Add a brand-new market (e.g. French):**
1. `mkdir data/sot/fr` and add the four files (copy an existing market as a template).
2. Add `fr` to `TARGET_LANGS` in `.env`; set `crowdin_locale` in `market.yaml` to your Crowdin id.
3. (For Slack routing) add `SLACK_CHANNEL_FR` + a `channel_for` entry, and a `#fr-l10n` channel.
4. Restart the services. **No engine code changes.**

**Improve quality for a market:** edit `guidelines.md` (add a rule), `glossary.csv` (lock a term),
or `TM_<lang>.csv` (seed a preferred translation). Restart the process to pick it up.

**Where do these files live for the team?** They're **versioned in this git repo** — that *is* the
"upload location." A content owner edits them via a Pull Request (or directly), review happens in
git, and a merge ships the new guidelines. (If you'd rather a non-git surface, you could sync this
folder from a Google Drive / S3 bucket — the loader only needs the files on disk — but git gives you
review + history for free.)

## Important notes
- **Restart after editing.** The SoT is cached per-process for speed; restart `./run web` / the bot /
  the receiver to load changes.
- **The offline demo cache is separate.** `data/cache/translations.json` holds pre-generated
  translations so the no-key demo works. After changing guidelines, those cached samples are stale;
  re-run `python scripts/build_cache.py` (needs an Anthropic key) to refresh them, or just rely on
  live translation.
- **Keep it fictional & public-safe** in this repo — it's public. Real proprietary guidelines belong
  in a private deployment.
