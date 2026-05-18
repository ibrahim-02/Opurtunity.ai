# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Scraper

```bash
cd linked_job_scraper

# Full pipeline (all keywords, all countries)
python main.py

# Test mode — 1 keyword, N jobs, no full run
python main.py --test --keyword "Data Engineer" --max 5

# Runtime overrides (override .env without editing it)
python main.py --countries "United States,United Kingdom" --max-applicants 50 --pages 5
python main.py --skills "SQL,Python,dbt"   # replaces TARGET_SKILLS

# FastAPI server
uvicorn api.app:app --reload
# GET  /health  — DB + Ollama connectivity check + job count
# POST /scrape  — triggers run_pipeline() in a background task
```

## Architecture

```
main.py (orchestrator)
  ├── scraper/driver.py          — undetected-chromedriver + selenium-stealth, Windows Chrome version auto-detect
  ├── scraper/linkedin_scraper.py — virtual-list scroll, card collection, right-panel description extraction
  ├── scraper/card_parser.py     — BeautifulSoup: title / company / location / salary from card HTML
  ├── scraper/detail_scraper.py  — navigates to /jobs/view/<id>, extracts description as fallback
  ├── database/connection.py     — SQLAlchemy engine, init_db(), upgrade_schema()
  └── database/repository.py    — JobRepository: insert_job() with dedup + company/title filtering
```

### Description extraction (right-panel approach)

LinkedIn renders a split pane: left = scrollable job list, right = detail panel. The scraper clicks each card, scrolls the right panel with `ActionChains.scroll_from_origin()` (dispatches a real wheel event — `scrollTop` on the wrapper does nothing), then calls `_extract_description_from_html()`:

1. `execute_script` returns the panel's raw `innerHTML` (no CSS dependency)
2. BeautifulSoup parses it in Python — `get_text()` is layout-independent unlike `innerText`
3. Targets `id="job-details"` first (stable LinkedIn element ID confirmed in live DOM captures), then "About the job" heading walk-up, then `jobs-box__html-content` class

When extraction fails, the panel HTML is saved to `logs/debug_screenshots/panel_<job_id>.html` for selector inspection.

### Virtual list scrolling

LinkedIn only renders visible cards in the DOM (React virtual list). `_scrape_single_page()` does 60-step incremental scrolls, collecting `data-job-id` attributes at each step into `seen_ids_this_page`, then deduplicates globally via `self.seen_links`. Cards that scroll out of view are dropped from the DOM — this is why we collect HTML at each scroll step rather than after scrolling is complete.

### Live config reload

All modules import settings as a module reference (`import config.settings as _cfg`) so `importlib.reload()` propagates changes immediately. A daemon thread in `main.py` watches `settings.py` for file modification time changes and reloads on save — no restart needed.

### Filtering pipeline

Cards are filtered twice:
1. **Pre-filter** in `_scrape_single_page()` — skips reposted jobs, 100+ applicant jobs, and blocked companies via substring match on raw card HTML (fast, before DB)
2. **Post-filter** in `repository.insert_job()` — re-checks `EXCLUDED_COMPANIES` and validates title against `TITLE_KEYWORDS` allowlist; returns `'inserted'`, `'duplicate'`, `'blocked'`, or `'bad_title'`

Both filters read from `config/settings.py` live so blocklist changes take effect without restart.

### DB schema

```sql
CREATE TABLE jobsql (
    id            serial PRIMARY KEY,
    company_name  varchar,
    title         varchar NOT NULL,
    description   varchar,          -- full text from right panel HTML
    link          varchar NOT NULL UNIQUE,
    location      varchar,
    posted_date   timestamp,        -- set to UTC insertion time, not LinkedIn's "X days ago"
    salary        json              -- {"min": float, "max": float, "currency": "USD"} or null
);
CREATE TABLE scrape_log (
    id           serial PRIMARY KEY,
    keyword      varchar,
    cards_scraped integer, inserted integer, duplicate integer,
    blocked integer, bad_title integer, error integer,
    total_in_db  integer,
    completed_at timestamp DEFAULT now()
);
```

`upgrade_schema()` in `database/connection.py` runs idempotent `ALTER TABLE` statements on startup to handle column changes that SQLAlchemy's `create_all()` cannot apply to existing tables.

### LLM module (not yet wired into pipeline)

`llm/` contains `OllamaClient` (httpx, `qwen3:8b`, JSON-mode generation) and `JobExtractor` (LLM-based field extraction from raw HTML). Currently unused in the main pipeline — `card_parser.py` handles all extraction directly via BeautifulSoup. The LLM module is kept for the planned `pipeline/enrich_jobs.py` skill extraction pass.

## Roadmap

### Phase 1 — Data Pipeline (in progress)

| Step | What | Status |
|------|------|--------|
| 1A | Description extraction from right panel | ✅ Done |
| 1B | Schema evolution: `platform`, `applicant_count`, `skills_extracted`, `embedding`, `enriched_at`, `competition_score` | Pending |
| 1C | LLM skill extraction — `llm/skill_extractor.py` + `pipeline/enrich_jobs.py` (batch: jobs WHERE description IS NOT NULL AND skills_extracted IS NULL) | Pending |
| 1D | Embeddings + pgvector — `pipeline/embed_jobs.py`, HNSW index, `nomic-embed-text` (local) or `text-embedding-3-small` (OpenAI) | Pending |
| 1E | Greenhouse + Lever scrapers — public JSON APIs, no auth; `scraper/greenhouse_scraper.py`, `scraper/lever_scraper.py`, `config/company_list.py` | Pending |
| 1F | `--full-pipeline` orchestration + `pipeline/competition_scorer.py` | Pending |

### Phase 2 — AI Layer
- Semantic job clustering (HDBSCAN/k-means on embeddings)
- Resume parser → `UserProfile` Pydantic model
- Personalized ranking: cosine similarity × skill overlap × competition score
- Hidden opportunity detector: `score = skill_match × (1 - competition_score) × recency_weight`

### Phase 3 — Frontend
- Next.js + Tailwind (or Streamlit for fast MVP)
- Job feed, resume upload → ranked results, cluster map (t-SNE/UMAP), "hidden gems" tab

## Key Config

`config/settings.py` is the single source of truth. Edit it live — the watcher thread reloads it within 2 seconds.

| Variable | Default | Effect |
|----------|---------|--------|
| `SEARCH_COUNTRIES` | `["United States"]` | LinkedIn location filter strings |
| `MAX_APPLICANTS` | `100` | Skip jobs at or above this count (0 = disabled) |
| `MAX_PAGES_PER_SKILL` | `12` | Pages per keyword per country (25 jobs/page) |
| `TIME_FILTER` | `r86400` | `r86400`=24h, `r604800`=week, `r2592000`=month |
| `TARGET_SKILLS` | 11 skills | Skill-based search terms |
| `SEARCH_QUERIES` | 50+ titles | Job-title-based search terms |
| `EXCLUDED_COMPANIES` | set of ~80 | Substring blocklist (staffing agencies, job portals) |
| `TITLE_KEYWORDS` | ~40 keywords | Allowlist — job must match at least one |

Override `TARGET_SKILLS` / `SEARCH_QUERIES` without editing code by creating `config/search_terms.json`:
```json
{"skills": ["SQL", "Python"], "queries": ["Data Analyst", "ML Engineer"]}
```

## Debugging Broken Selectors

LinkedIn changes CSS class names regularly. When cards stop being collected or descriptions stop extracting:

1. Check `logs/debug_screenshots/` — `page_<keyword>.html` for card list DOM, `panel_<job_id>.html` for right-panel DOM
2. For card collection: update `CARD_CSS_SELECTORS` and `LINK_SELECTORS` in `linkedin_scraper.py`
3. For descriptions: `_extract_description_from_html()` in `linkedin_scraper.py` targets `id="job-details"` — verify this ID still exists in the saved panel HTML
