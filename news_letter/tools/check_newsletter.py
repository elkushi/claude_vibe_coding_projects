"""QA checks for a rendered issue before it goes to Gmail.

Usage:
    python tools/check_newsletter.py .tmp/<slug> [--offline]

Checks:
    - email.html size under Gmail's ~102KB clipping limit (warns above 90KB)
    - every <img> has non-empty alt text
    - every cid: image exists in images.json and on disk
    - every stat and chart cites a source id that exists in "sources"
    - every source URL responds (skipped with --offline)
    - subject / preview text lengths are inbox-friendly
    - brand: every colour in email.html is a brand colour; none is blue/purple/teal/pink;
      the CTA has a URL
Exits 1 if any ERROR is found; WARNINGs don't fail.
"""
import colorsys
import json
import re
import sys
from pathlib import Path

import requests

CLIP_LIMIT_KB, WARN_KB = 102, 90
ROOT = Path(__file__).resolve().parent.parent


def brand_errors(email_html, brand):
    """Brand sheet: never blue, purple, indigo, teal, violet, fuchsia or pink."""
    allowed = {v.upper() for v in brand["colors"].values() if isinstance(v, str)}
    allowed |= {v.upper() for v in brand["semantic_colors"].values() if v.startswith("#")}
    errors, warnings = [], []
    for hexc in sorted({h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}\b", email_html)}):
        if hexc in allowed:
            continue
        r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
        hue, _, sat = colorsys.rgb_to_hls(r, g, b)
        if sat > 0.2 and 165 <= hue * 360 <= 345:
            errors.append(f"off-brand colour {hexc} (blue/purple/teal/pink family is banned)")
        else:
            warnings.append(f"colour {hexc} is not in config/brand.json")
    return errors, warnings


def main(issue_dir, offline=False):
    issue_dir = Path(issue_dir)
    content = json.loads((issue_dir / "content.json").read_text())
    email_html = (issue_dir / "email.html").read_text()
    images = json.loads((issue_dir / "images.json").read_text())
    errors, warnings = [], []

    size_kb = len(email_html.encode()) / 1024
    if size_kb > CLIP_LIMIT_KB:
        errors.append(f"email.html is {size_kb:.1f} KB; Gmail clips above {CLIP_LIMIT_KB} KB")
    elif size_kb > WARN_KB:
        warnings.append(f"email.html is {size_kb:.1f} KB; close to Gmail's {CLIP_LIMIT_KB} KB clip limit")

    for tag in re.findall(r"<img\b[^>]*>", email_html):
        alt = re.search(r'alt="([^"]*)"', tag)
        if not alt or not alt.group(1).strip():
            errors.append(f"image without alt text: {tag[:80]}")

    for cid in re.findall(r'src="cid:([^"]+)"', email_html):
        if cid not in images:
            errors.append(f"cid:{cid} not in images.json")
        elif not Path(images[cid]).exists():
            errors.append(f"image file missing for cid:{cid}: {images[cid]}")

    source_ids = {s["id"] for s in content.get("sources", [])}
    for s in content.get("stats", []):
        if s.get("source") not in source_ids:
            errors.append(f"stat '{s['value']} {s['label']}' has no valid source")
    for ch in content.get("charts", []):
        cited = ch.get("source") if isinstance(ch.get("source"), list) else [ch.get("source")]
        if not cited or any(s not in source_ids for s in cited):
            errors.append(f"chart '{ch['id']}' has no valid source")
    used_charts = {sec.get("chart") for sec in content.get("sections", [])}
    for ch in content.get("charts", []):
        if ch["id"] not in used_charts:
            warnings.append(f"chart '{ch['id']}' is defined but not placed in any section")

    brand = json.loads((ROOT / "config" / "brand.json").read_text())
    be, bw = brand_errors(email_html, brand)
    errors += be
    warnings += bw
    cta = content.get("cta") or brand.get("cta") or {}
    if cta.get("enabled", True) and not cta.get("url"):
        warnings.append("no CTA URL set (brand.json cta.url) - the red button is hidden")

    if len(content.get("subject", "")) > 60:
        warnings.append(f"subject is {len(content['subject'])} chars; mobile inboxes cut off around 40-60")
    if not content.get("preview_text"):
        warnings.append("no preview_text; Gmail will show the first body text instead")

    if not offline:
        headers = {"User-Agent": "Mozilla/5.0 (newsletter link check)"}
        for s in content.get("sources", []):
            try:
                r = requests.head(s["url"], allow_redirects=True, timeout=10, headers=headers)
                if r.status_code >= 400:  # some sites reject HEAD; retry with GET
                    r = requests.get(s["url"], allow_redirects=True, timeout=10, headers=headers, stream=True)
                if r.status_code >= 400:
                    warnings.append(f"source [{s['id']}] returned HTTP {r.status_code}: {s['url']}")
            except requests.RequestException as e:
                warnings.append(f"source [{s['id']}] unreachable ({type(e).__name__}): {s['url']}")

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR:   {e}")
    print(f"{'FAIL' if errors else 'PASS'} - {len(errors)} errors, {len(warnings)} warnings, {size_kb:.1f} KB")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    main(args[0], offline="--offline" in sys.argv)
