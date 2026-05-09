# irisvision.ai SEO Toolkit

Public-web SEO toolkit for **[irisvision.ai](https://irisvision.ai)**.

All WordPress integrations, Google Analytics, Bing Search API, login screens,
and auto-fixers have been removed. Everything below works with **zero API
keys** and **zero credentials** — it only fetches publicly accessible pages.

## What's in here

| File              | What it does                                                                    |
| ----------------- | ------------------------------------------------------------------------------- |
| `sites_config.py` | Single-site config for `irisvision.ai` (domain, brand, tracked keywords).       |
| `crawl_script.py` | Crawls the site and writes a technical audit + keyword + cluster CSV per day.   |
| `bypass.py`       | Optional: opens `site:irisvision.ai` results on Google/Yahoo/Bing and counts clicks. |
| `dashboard.py`    | Streamlit dashboard that reads the CSVs (audit, keywords, clusters, click bot). |

## Output layout

```
seo_reports/
└── irisvision-ai/
    ├── irisvision.ai_technical_audit_2026-05-09.csv
    ├── irisvision.ai_page_keywords_2026-05-09.csv
    ├── irisvision.ai_keyword_clusters_2026-05-09.csv
    └── traffic_generated_2026-05-09.csv     # only if bypass.py is run
```

## Install

```bash
pip install -r requirements.txt

# Only needed for bypass.py
playwright install chromium
```

## Run

```bash
# 1. Crawl the site (no auth required)
python crawl_script.py

# 2. (Optional) run the search-engine click bot
python bypass.py

# 3. Open the dashboard
streamlit run dashboard.py
```

## Removed from the original toolkit

- WordPress REST API (`fix_issues.py`, `_auth_header`, `WP_USER`/`WP_APP_PASS`)
- Google Analytics 4 (`get_ga4_client`, GA4 service-account env vars)
- Bing Web Search API (`find_unlinked_mentions`, `BING_API_KEY`)
- Multi-site sidebar picker — this build is single-site
- Login wall (`check_password`)
- All "fixed issues" tabs and bulk fix actions
