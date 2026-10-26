# Competitor Analysis Workflow

A repeatable Claude Code workflow that researches a market and produces a **fully branded, source-cited PDF report** (≈30–50 pages):

Cover → Executive summary → Market overview → Competitor profiles → Comparison matrix → Opportunities & gaps → Recommendations → Sources.

Every claim in the report carries a source id, and a validator blocks rendering if anything is unsourced, a link is dead, placeholder text is left or a forbidden name appears. The first run covered 9 competitors in Bangladesh's A2P SMS market: 192 sources and ~412 cited claims.

- **How it was built:** [portfolio/ai-workflow-case-study.html](portfolio/ai-workflow-case-study.html) ([PDF](portfolio/ai-workflow-case-study.pdf))
- **Quick reference:** [portfolio/claude-workflow-cheat-sheet.html](portfolio/claude-workflow-cheat-sheet.html) ([PDF](portfolio/claude-workflow-cheat-sheet.pdf))

## How it works

```
You ──approve──▶ Claude (agent) ──reads──▶ workflows/competitor_analysis.md
                     │
                     ├─ parallel research sub-agents → data/competitors/*.json
                     ├─ tools/seo_snapshot.py, tools/pagespeed.py
                     ├─ tools/merge_research.py   (dedupe sources, renumber S1…Sn)
                     ├─ tools/validate_research.py (the gate)
                     └─ tools/render_report.py    (charts → HTML → WeasyPrint PDF)
```

There are four human checkpoints: **A** competitor list, **B** research findings, **C** analysis, **D** final PDF.

## Use it for your own company

1. **Set up.**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env                       # PAGESPEED_API_KEY (free Google key)
   cp project.example.json project.json       # company name, banned names, market checks
   cp business-profile.example.md business-profile.md
   ```
   WeasyPrint needs Pango installed (`apt install libpango-1.0-0` on Debian/Ubuntu).
2. **Brand.** Replace `brand/brand.json` and the logos with your own. Put licensed font files in `brand/fonts/` and list them in `brand.json` → `fonts.files`. The included brand is the original run's, as a working example. Its commercial font (Gilroy) isn't included, so add your own fonts.
3. **Check the design** with placeholder data:
   ```bash
   python tools/validate_research.py samples/sample_report.json --allow-sample
   python tools/render_report.py samples/sample_report.json --out .tmp/sample/report.pdf
   ```
4. **Adapt the SOP.** In `workflows/competitor_analysis.md`, replace the Bangladesh-specific search terms and edge cases with your market's.
5. **Run it.** Open the folder in Claude Code and say: *"Run workflows/competitor_analysis.md for [market], [month year]."* Claude stops at each checkpoint.

The step-by-step prompts for building this from an empty folder are in the cheat sheet and in section 09 of the case study.

## What's private and not in this repo

| File | Why | Public template |
|---|---|---|
| `project.json` | Banned names, company settings | `project.example.json` |
| `business-profile.md` | Internal company facts | `business-profile.example.md` |
| `research/` | Source checks of internal documents | none |
| `source_for_agents/` | Internal documents | none |
| `output/` | Report runs and research data | `samples/sample_report.json` |
| `brand/fonts/` | Commercial font licence | add your own |
| `.env` | API keys | `.env.example` |

## Layout

```
CLAUDE.md                  rules for the agent (WAT framework)
workflows/                 the SOP, with checkpoints, evidence rules and lessons learned
tools/                     deterministic Python: snapshot, speed, merge, validate, charts, render
schemas/report.schema.json data contract: every claim = {text, source_ids}
templates/                 Jinja2 + CSS Paged Media report template
samples/                   placeholder report data for design work
brand/                     brand.json, logos, icons
portfolio/                 case study and cheat sheet
```
