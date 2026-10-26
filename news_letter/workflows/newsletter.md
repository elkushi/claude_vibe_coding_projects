# Workflow: Newsletter

## Objective
Turn "newsletter about <topic>" into a researched, sourced HTML email with charts and an AI hero image, branded from `config/brand.json` and delivered as a Gmail draft for review.

## Brand (source of truth)
`config/brand.json` holds the brand. The repo ships a made-up example, Field Notes. Key rules the pipeline enforces:
- **Colours:** ink `#0F0F1A` and greys for structure; brand red `#DC2626` **only** for the one main action (CTA), eyebrows and key emphasis (`<em>` in the title, chart `highlight`). Never blue, purple, indigo, teal, violet, fuchsia or pink. `check_newsletter.py` fails on those.
- **Type:** Inter (400/600/700/800), tight display tracking. Gmail falls back to the system sans.
- **Logo:** `brand_assests/derived/logo.png`. Never recolour, stretch or redraw it.
- **Shape:** flat, 1px `#E5E7EB` borders, no shadows. 12px button radius, 16px card radius. Top nav and footer are always ink.
- **Icons:** emoji on a pastel (tint) tile, used for stat cards via `"emoji"`. No icon libraries.
- **Voice:** a patient friend who corrects you gently: direct, warm, precise, short sentences, second person. Sentence case for buttons, UPPERCASE for eyebrows. Glyphs: → for CTAs, ✓ / ✕ for answers, · between metadata.
- **Semantic colours** (positive, negative, warning) are not decoration. Don't use them in newsletters unless they carry that exact meaning.

## Inputs
- `topic`: what the issue is about (required, from the user)
- `audience`, `tone`, `length_words`, `sections`: optional; defaults are in `config/brand.json` → `defaults`
- `angle`: optional, e.g. "beginner explainer", "latest news", "contrarian take"
- `recipients`: optional; drafts don't need one, `--send` does

## Tools
1. Claude's WebSearch / WebFetch: research (no script)
2. `tools/make_charts.py <issue_dir>`: chart PNGs from `content.json`
3. `tools/kie_image.py`: hero image via kie.ai (Nano Banana 2). The brand style is appended to the prompt automatically. Uses `KIE_API_KEY` from `.env`
4. `tools/render_newsletter.py <issue_dir>` → `email.html`, `preview.html`, `email.txt`, `images.json`
5. `tools/check_newsletter.py <issue_dir> [--offline]`: QA gate
6. `tools/gmail_send.py <issue_dir> [--to ...] [--send]`: Gmail draft (default) or send, using an app password or OAuth; appends to `issues_log.json`

Run Python with `.venv/bin/python`.

## Steps
1. **Brief.** Confirm the topic and any non-default audience, tone or angle in one short message. Check `issues_log.json` so a recent topic isn't repeated. Choose a slug: `.tmp/<YYYY-MM-DD>-<topic-kebab>/`.
2. **Research.** Run 4–8 searches and read 5–10 strong sources: primary data, reputable outlets, recent dates. Save `research.json` with one entry per fact: `{claim, number, url, publisher, date}`. Never use a number you can't attach to a URL.
3. **Write `content.json`** (schema below). Draft 3 subject lines (≤50 chars), pick the best and keep the others in `subject_alternatives`. Target the configured word count. Choose 2–4 charts whose data comes straight from `research.json`. Keep chart data small: 3–7 points.
4. **Charts.** Run `make_charts.py`, then look at each PNG. Fix crowded labels by shortening them in `content.json`, not in code.
5. **Hero image.** Run `kie_image.py --balance` and tell the user the cost (~8 credits) before generating. Then run `kie_image.py --prompt "<subject only: one clear visual metaphor for the topic>" --out <issue_dir>/img/hero.png` (16:9, 1K). Open the result and check it: ink/red/white/grey only, flat, **no text**. If it's off-brand, regenerate once with a simpler subject; don't loop. If kie.ai is unavailable, drop `hero` from `content.json`; the template handles that. Note that the brand sheet says "no illustrations or stock art". The example keeps AI heroes anyway, so keep them flat, abstract and on-palette.
6. **Render.** Run `render_newsletter.py`. Screenshot `preview.html` with `google-chrome --headless --window-size=680,2600 --screenshot=...` and also at 390px, and review both.
7. **QA.** `check_newsletter.py` must PASS. Fix every ERROR. Read the WARNINGs and fix them where it makes sense.
8. **Deliver.** Run `gmail_send.py` to create a draft. Tell the user it's in Gmail › Drafts. Use `--send` only when the user explicitly asks.

## content.json schema
```json
{
  "slug": "2026-10-12-topic", "topic": "…", "kicker": "short label above title",
  "date": "12 Oct 2026", "issue_number": 1,
  "subject": "≤50 chars", "subject_alternatives": ["…", "…"],
  "preview_text": "40-90 chars shown in the inbox list",
  "title": "headline; wrap ONE key word in <em> to make it red", "intro": "1-2 sentence lede (inline HTML ok)",
  "read_minutes": 5,
  "hero": {"image": "hero.png", "alt": "describe the image"},
  "tldr": ["3-4 bullets"],
  "stats": [{"value": "42%", "label": "short label", "source": 1, "emoji": "📚"}],
  "charts": [{"id": "x", "type": "bar|hbar|line|donut|timeline", "title": "…", "caption": "optional",
              "alt": "what the chart shows, incl. key numbers", "source": 1, "data": {}}],
  "sections": [{"eyebrow": "optional UPPERCASE label", "heading": "…", "paragraphs": ["… <a href> / <strong> ok"], "chart": "x", "callout": "optional, shown as an ink card"}],
  "cta": {"label": "Read more →", "url": "optional per-issue override of brand.json cta"},
  "closing": "sign-off line",
  "sources": [{"id": 1, "title": "…", "publisher": "…", "url": "https://…", "date": "2026"}]
}
```
Chart `data` shapes are documented at the top of `tools/make_charts.py`. Charts are ink/grey by default. Set `"highlight"` to make **one** item brand red: an index for bar/hbar/donut, a series name for line, `true` on a timeline event. Use it for the single point the section is making. Keep 3 stats; with 4 or more, the stat boxes get cramped.

## Outputs
- Intermediates: `.tmp/<slug>/` (research.json, content.json, img/, email.html, preview.html, email.txt)
- Deliverable: Gmail draft (or sent email) + a line in `issues_log.json`

## One-time setup
**Gmail, option A: app password (recommended, about 2 minutes)**
1. Turn on 2-Step Verification for the Google account (myaccount.google.com → Security).
2. Go to https://myaccount.google.com/apppasswords, create one named "newsletter", and copy the 16 characters.
3. Add `GMAIL_ADDRESS=you@gmail.com` and `GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx` to `.env`.
4. Drafts are saved over IMAP and sending goes over SMTP. Gmail has IMAP on by default for personal accounts. Workspace admins can turn it off.

**Gmail, option B: OAuth** (only if app passwords are blocked, e.g. on some Workspace accounts)
1. In Google Cloud Console, enable the Gmail API. Set up the OAuth consent screen (External) and add yourself as a test user.
2. Create an OAuth client ID of type **Desktop app** and save it as `credentials.json` in the project root. The first run opens a browser and creates `token.json`.

**Not usable:** a Google API key (`AIza…`). API keys only reach public data, and drafts or sends need the account owner's consent.

**Brand / CTA:** `cta.enabled` is `false` until there's a page to link to. Then set `enabled: true` and `url` in `config/brand.json`. Optionally set `default_to`.

## Edge cases & known issues
- **Gmail clipping:** HTML over ~102KB gets "[Message clipped]". CID images don't count toward that. A typical issue is ~15KB.
- **Gmail blocks `data:` base64 images.** That's why images go as CID attachments. The whole MIME message is ~200KB for 6 images.
- **Dark mode:** Gmail apps may invert colours. The ink nav and footer and the white chart cards hold up well.
- **Jinja autoescape vs CSS:** values injected into `<style>` must be marked `| safe`. Otherwise `'Segoe UI'` becomes `&#39;Segoe UI&#39;`, the font declaration breaks and text falls back to serif.
- **premailer fetches `<link>` stylesheets.** The Google Fonts link has `data-premailer="ignore"`. Without it, rendering needs network access and inlines a large @font-face block.
- **Logo crop:** the tile sits on a white card in the sheet. A plain rounded mask left a white fringe on the ink nav, so the corner alpha comes from how red each pixel is.
- **kie.ai timeouts and network drops:** a task can fail with `524 generate task timeout`. Failed tasks are **not charged**; confirm with `--balance`, then retry once. The tool retries network errors itself, but never re-sends a POST after a timeout, so a task can't be submitted twice.
- **Gmail OAuth first run:** run `gmail_send.py` with `python -u` in the background and read its output for the "Please visit this URL" line. Without `-u` the link is buffered, and if no browser opens, the user never sees it.
- **Link check 403s:** SEC (sec.gov), DOI/Wiley and Duolingo IR block automated requests. A 403 from these is a bot block, not a dead link.
- **Charts citing several sources:** `"source"` can be a list, e.g. `[4, 5]`; the caption then reads "Sources [4, 5]".
- **kie.ai** returns HTTP 200 even on errors, so the tool checks the body's `code`. Result files expire after 14 days, so download them straight away (the tool does).
- **Image models garble text.** Never put words or numbers in the hero image; all data goes in code-drawn charts.
- **Hallucinated stats:** QA fails if a stat or chart has no valid `source` id. You still have to check that the number actually appears at that URL.
- **Sending limits:** a personal Gmail account allows ~500 recipients a day, with no unsubscribe or list management. For a real subscriber list, replace only `gmail_send.py` with an ESP tool (Brevo, Resend or Beehiiv).
- **Source link checks:** some sites block HEAD and bot requests, which shows up as a WARNING. Open the link manually before ignoring it.
- **Chart sizing:** charts render at a fixed 1072px width (no bbox cropping) so they line up. Donut charts set their own margins.
- **Mobile padding:** the media query may override only left and right padding. A shorthand `padding` there wipes the vertical spacing.

## Changelog
- 2026-10-13: issue #1 produced end to end. Market-size figures were rejected as inconsistent; only 10-K, peer-reviewed meta-analyses and official announcements were used.
- 2026-10-13: first kie.ai hero generated (8 credits, 45s, on-brand on the first try). Added app-password Gmail transport (IMAP drafts / SMTP send). The CTA can be switched off with `cta.enabled` until the app launches.
- 2026-10-12: brand moved into `config/brand.json`. Hero moved from Freepik to kie.ai. Brand colour lint added to QA. Charts use Inter, ink/greys and a single red highlight.
- 2026-10-12: created. Pipeline tested end to end on a placeholder issue (`.tmp/_sample`), up to building the MIME message. Gmail OAuth not yet configured.
