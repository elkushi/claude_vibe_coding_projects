# Workflow: Competitor & Market Analysis → Branded PDF

**Objective:** Produce an evidence-backed competitor and market analysis for Ritorica Bangladesh as a branded PDF (≈30–50 pages) for investors and partners. Every factual claim cites a source URL and access date.

> **Reusing this SOP for another company or market:** fill in `project.json`, `business-profile.md` and `brand/`, then replace the Bangladesh-specific search terms and edge cases below with your market's. The tools, schema, validator and template stay the same.

**Run cadence:** on demand (typically quarterly). Each run is self-contained in `output/<YYYY-MM-DD>_<slug>/`.

**Checkpoints (⏸):** the agent stops and waits for the owner at each one. Never skip a checkpoint.

---

## Inputs

| Input | Where | Notes |
|---|---|---|
| Project settings | `project.json` (private; template `project.example.json`) | Company name and website, names that must never appear, market-specific website checks. |
| Business profile | `business-profile.md` (private; template `business-profile.example.md`) | Authoritative for internal facts. Re-read every run. |
| Brand tokens | `brand/brand.json` (+ `brand/logo/`, `brand/fonts/`) | Rebuild from the guidelines bundle with `tools/extract_brand_bundle.py` if the guidelines change. |
| Last source check | `research/source_check_*.md` (latest) | Starting point for facts and known-false claims. |
| Internal source files | `source_for_agents/` (gitignored) | Treat as **unverified**. Internal tariff/cost data is **never** shown in reports. |
| Previous run | `output/<last run>/report.json` | Optional: diff against it to report "what changed". |

## Tools

| Step | Tool | Output |
|---|---|---|
| Website snapshot | `tools/seo_snapshot.py <urls> --out <run>/data/seo.json` | Title/meta/H1, pricing/API/blog links, OTT mentions, sitemap cadence; plus the market checks set in `project.json` (here: Bengali share, BTRC number on homepage) |
| Speed & SEO scores | `tools/pagespeed.py <urls> --out <run>/data/pagespeed.json` | Mobile + desktop scores (free API; slow, ~30 s per URL per strategy) |
| Validation gate | `tools/validate_research.py <run>/report.json --check-links` | PASS/FAIL. **Render only on PASS.** |
| Charts + PDF | `tools/render_report.py <run>/report.json --out <run>/report.pdf` | Branded PDF + debug HTML |
| Data contract | `schemas/report.schema.json` | Shape of `report.json`; example in `samples/sample_report.json` |

Run Python with `.venv/bin/python`.

---

## Steps

### 1. Prepare the run
1. Create `output/<YYYY-MM-DD>_bd-a2p/` with `data/` inside.
2. Read `business-profile.md`, `brand/brand.json`, the latest `research/source_check_*.md`.
3. List open items from profile §9 that the research could resolve this time.

### 2. Identify competitors → ⏸ Checkpoint A
1. Start from profile §7 (core list) and §8 (exclusions). Never profile excluded companies or mobile operators.
2. Search for new entrants: BTRC enlistment news, "bulk SMS Bangladesh", "A2P SMS aggregator Bangladesh", "WhatsApp Business API Bangladesh", "RCS Bangladesh", plus the Bangla equivalents (বাল্ক এসএমএস).
3. Propose **5–8 direct** (local licensed aggregators selling to enterprises) and **2–3 indirect** (international CPaaS, platform vendors, OTT/RCS players) with a one-line rationale and source each. Everyone else goes to the long-tail table.
4. **⏸ Stop. Owner approves or edits the list.**

### 3. Research each competitor
Run one research sub-agent per approved competitor in parallel. Each returns the competitor object defined in `schemas/report.schema.json` plus its sources. Brief every sub-agent with:
- The dimensions: positioning (own words), segments and named clients, products and channels, pricing, licence status, website/SEO, content/social, reviews (praise and complaints), recent moves (last 18 months), strengths, weaknesses, where Ritorica can win.
- The evidence rules below.
- The known facts and corrections for that company from the latest source check.

Then, deterministically:
1. `seo_snapshot.py` on Ritorica's site and every competitor site → `data/seo.json`.
2. `pagespeed.py` on the same list → `data/pagespeed.json`. Copy scores into `web_seo.pagespeed_*` and `us.pagespeed_mobile`; cite Google PageSpeed Insights as the source.

### 4. Assemble `report.json` → ⏸ Checkpoint B
1. Merge sub-agent results; renumber sources as `S1…Sn` in first-use order; internal facts cite `INT`.
2. Fill `market_overview` from verified regulation/market facts (latest operator and subscriber numbers).
3. Run `validate_research.py report.json --check-links`. Fix every ERROR. Hand-check every link WARN (403s are often bot blocks, not dead pages).
4. **⏸ Stop. Owner reviews the findings (competitor profiles + market) and flags errors.**

### 5. Analysis → ⏸ Checkpoint C
1. Score the matrix (1–5 per dimension) **from the cited evidence only**; Ritorica's row from the profile. Keep dimensions stable between runs so scores are comparable.
2. Positioning map: enterprise focus × channel breadth, using the matrix scores.
3. Write what's working for them, weak spots, market gaps.
4. Recommendations: impact 1–5 × effort 1–5, horizon, sources. Quick win = impact ≥ 4 and effort ≤ 2.
5. Executive summary last: headline, 3–4 key numbers, 4–6 findings, bottom line.
6. **⏸ Stop. Owner reviews analysis and recommendations.**

### 6. Render & QA → ⏸ Checkpoint D
1. Validate again (must PASS), then render.
2. QA: page count 30–50; Gilroy embedded (`pdffonts`); no blank pages; every section non-empty; skim the PDF visually (rasterise with `pdftoppm -r 50` and view a contact sheet).
3. **⏸ Stop. Owner reviews the PDF.**

### 7. Close the run
1. Save a new `research/source_check_<date>.md` if facts changed materially.
2. Add lessons learned to the bottom of this file.

---

## Evidence rules (non-negotiable)

1. **Every factual claim has ≥ 1 source** with URL and access date. No source → drop the claim or write "not publicly disclosed".
2. **Only cite pages actually opened.** A search snippet is not a source; if only a snippet exists, say so in the source `note` and phrase the claim cautiously ("reported", "according to").
3. **Company self-claims are labelled.** "Claims 60+ banks" — not "serves 60+ banks". Licence numbers published by a company are self-published until checked against BTRC's list.
4. **Internal facts cite `INT`** (the business profile). Internal operator costs and margins are never shown.
5. **Do not name** any company listed in `forbidden_terms` in `project.json` (validator enforces this).
6. **Inference is labelled** ("likely", "suggests") and never stated as fact — e.g. "international players are unlikely to qualify for local tenders" not "cannot bid".
7. **Dates on everything time-sensitive** (subscriber counts, follower counts, prices).
8. **Brand voice:** plain, specific, calm; lead with the number; no hype or exclamation marks; mark modelled numbers as illustrative.

## Edge cases

| Situation | Handling |
|---|---|
| Site blocks bots (403/Cloudflare) | Try WebFetch; then search for cached/third-party coverage; record the block in the source note. Don't guess. |
| BTRC enlisted list won't load | State licence status as "self-published" or "not published"; list as an open item. |
| PageSpeed 429 / quota | Tool retries with backoff. If still failing, set `PAGESPEED_API_KEY` in `.env` (free key, Google Cloud console), re-run only failed URLs. |
| Competitor has no website | Long-tail table only, marked unverified. |
| Conflicting numbers between a company's pages | Report the range and both sources ("claims 12,000+ to 22,000+ clients"). |
| Ritorica's own public pages disagree | Use the owner-confirmed figures in the profile; list the website inconsistency as a recommendation. |

---

## Known facts & quirks (keep updated)

- **2026-10-19:** BTRC's enlisted-aggregator list could not be loaded; Infobip/Wintel licence status unconfirmed.
- **2026-10-19:** Published local prices run below the 0.30 BDT "floor" (0.25–0.28 at several sellers); the 2021 band excludes VAT. Don't write "price is fixed".
- **2026-10-19:** BTRC (Aug 2026) is moving SMS traffic toward masking-only; check for a formal directive each run.
- **2026-10-19:** ritorica.com.bd shows a placeholder page; ritorica.com has no Bengali version yet.
- **2026-10-19:** LinkedIn company pages open via `ae.linkedin.com/company/<slug>` when `www` blocks.

## Lessons learned

- **2026-10-19 (tool build):** `seo_snapshot.py` hung on a slow server — requests' `timeout` is per read, not total. Fixed with a hard 30 s wall-clock deadline + one retry per request. A regex for robots.txt caused catastrophic backtracking (5 min CPU); replaced with a line parser. Sitemap parsing needs `lxml`. Timing: ~15–25 s per site.
- **2026-10-19:** ritorica.com (apex) responds intermittently — sometimes 4 s, sometimes a read timeout; www.ritorica.com is reliable. Use the www host.
- **2026-10-19:** Keyless PageSpeed calls hit Google's shared daily quota (HTTP 429 "Queries per day"). A free `PAGESPEED_API_KEY` in `.env` is required for reliable runs.
- **2026-10-19:** Sites built with JavaScript (e.g. sslwireless.com) show few links in raw HTML; the snapshot flags `likely_js_rendered` — confirm those pages with WebFetch before stating "no pricing page" etc.
- *(add after each run: what broke, what fixed it, timings)*
