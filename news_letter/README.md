# Newsletter Workflow

A Claude Code workflow that turns *"newsletter about <topic>"* into a researched, sourced HTML email with charts and an AI hero image, branded and delivered as a **Gmail draft** for review. It ships with a made-up example brand, Field Notes, so you can see the whole pipeline before rebranding it.

- **Workflow (SOP):** [workflows/newsletter.md](workflows/newsletter.md)
- **Cheat sheet:** [docs/newsletter-cheatsheet.html](docs/newsletter-cheatsheet.html)

## Pipeline

```
topic ─▶ research (WebSearch/WebFetch → research.json, every number has a URL)
      ─▶ content.json ─▶ tools/make_charts.py      (brand PNG charts)
                      ─▶ tools/kie_image.py       (AI hero image, costs credits)
                      ─▶ tools/render_newsletter.py (email.html, preview.html, email.txt)
                      ─▶ tools/check_newsletter.py  (QA gate: size, alt text, sources, links, colours)
                      ─▶ tools/gmail_send.py        (Gmail draft; --send only on request)
```

## Use it for your own newsletter

1. **Set up.**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```
   Then fill in `KIE_API_KEY`, plus either `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD`, or an OAuth `credentials.json`.
2. **Rebrand.** Edit `config/brand.json`: name, tagline, colours, fonts, voice, image style and defaults. Replace the logo and fonts in `brand_assests/`. The tools read everything brand-related from that config. The colour bans in `check_newsletter.py` follow the brand rules, so update them too.
3. **Run it.** Open the folder in Claude Code and say: *"Newsletter about [topic]."* Claude confirms the brief, researches, renders, runs QA and leaves a draft in Gmail. It asks before spending image credits.

`workflows/_TEMPLATE.md` is a blank SOP for starting a new workflow in the same style.

## Not in this repo

`.env`, `credentials.json`, `token.json` and `.tmp/` (issue drafts) are gitignored.

The bundled fonts are Inter (SIL Open Font License, see `brand_assests/fonts/Inter-LICENSE.txt`). `SKILL.md` is a third-party image-generation skill (MIT licence, K-Dense Inc.).
