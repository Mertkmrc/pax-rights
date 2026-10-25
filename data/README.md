# Corpus

Public documents only. The source of truth is [`sources.yaml`](sources.yaml): URL, language, jurisdiction, retrieval date.

| id | Document | Lang | Jurisdiction | Fetch |
|---|---|---|---|---|
| `thy-gcc-en` | Turkish Airlines General Conditions of Carriage | en | TR | auto |
| `thy-gcc-tr` | THY Yolcu ve Bagaj Taşıma Genel Şartları | tr | TR | auto |
| `pegasus-rules-en` | Pegasus General Rules | en | TR | auto |
| `pegasus-rules-tr` | Pegasus Genel Kurallar | tr | TR | auto |
| `lufthansa-gcc-en` | Lufthansa General Conditions of Carriage | en | EU | manual |
| `wizz-gcc-en` | Wizz Air General Conditions of Carriage | en | EU | manual |
| `eu261` | Regulation (EC) No 261/2004 | en | EU | manual |
| `shy-yolcu` | SHY-YOLCU passenger-rights regulation (SHGM) | tr | TR | auto |

## Why the raw files are not in the repo

The EU and Turkish regulations are public law, but the airlines' redistribution terms for their conditions of carriage are unclear. Rather than treat each source differently, the repo commits only the script and the source list. `data/raw/` and `data/processed/` are gitignored.

## Getting the files

```sh
uv run python scripts/fetch_corpus.py
```

This downloads every `fetch: auto` source to `data/raw/<id>.<format>` and writes `data/raw/manifest.json` (size and sha256 per file). Existing files are skipped unless you pass `--force`. Dead links on these sites often return HTTP 200 with an HTML page, so the script checks that a PDF actually starts with `%PDF`.

Three sites block scripts (bot checks, a JS challenge, a 405 for non-browser clients). The script doesn't try to get around them. Open the URL in a browser, save the document as `data/raw/<id>.pdf`, and set `retrieved` in `sources.yaml`. The script prints which ones are still missing.

## Known issues

- **THY versions may differ.** The English PDF is named 03-02-2025; the Turkish one is dated 24 July 2019. Both say the Turkish text prevails on conflict. Check for a newer Turkish edition.
- **Pegasus PDF text is broken** ("epidem ic"), so the HTML pages are used instead.
- **Versioned URLs.** The THY and Wizz links contain content hashes or edition folders and will break on the next upload.
- **EU261 may have been amended.** A single source reports Regulation (EU) 2026/2202 of 16 September 2026, applying from about October 2027. Not yet verified on EUR-Lex. If confirmed, add it as a separate, future-applicable document.
