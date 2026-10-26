"""Render an issue's content.json into email-ready HTML.

Usage:
    python tools/render_newsletter.py .tmp/<slug>

Writes to <issue_dir>:
    email.html    CSS inlined, images referenced as cid:<name>  (what Gmail receives)
    preview.html  same layout, images referenced as img/<file>  (open locally in a browser)
    email.txt     plain-text alternative
    images.json   manifest {cid: file path} used by gmail_send.py
"""
import html
import json
import logging
import re
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from premailer import transform

ROOT = Path(__file__).resolve().parent.parent


def cid_for(filename):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", Path(filename).stem)


def render(content, brand, img_fn):
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    tpl = env.get_template("newsletter.html.j2")
    charts = {ch["id"]: ch for ch in content.get("charts", [])}
    cta = content.get("cta") or brand.get("cta")  # per-issue CTA overrides the brand default
    return tpl.render(c=content, b=brand, charts=charts, cta=cta, img=img_fn)


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def plain_text(content, brand):
    lines = [brand["newsletter_name"].upper(), content.get("date", ""), "",
             content.get("title") or content["subject"], ""]
    if content.get("intro"):
        lines += [strip_tags(content["intro"]), ""]
    if content.get("tldr"):
        lines += ["THE SHORT VERSION"] + [f"- {strip_tags(t)}" for t in content["tldr"]] + [""]
    for s in content.get("stats", []):
        lines.append(f"* {s['value']} - {s['label']}" + (f" [{s['source']}]" if s.get("source") else ""))
    if content.get("stats"):
        lines.append("")
    for sec in content.get("sections", []):
        lines += [sec["heading"].upper(), ""] + [strip_tags(p) + "\n" for p in sec["paragraphs"]]
        if sec.get("callout"):
            lines += [f'  "{strip_tags(sec["callout"])}"', ""]
    if content.get("closing"):
        lines += [strip_tags(content["closing"]), ""]
    cta = content.get("cta") or brand.get("cta")
    if cta and cta.get("enabled", True) and cta.get("url"):
        lines += [f"{cta['label']} {cta['url']}", ""]
    if content.get("sources"):
        lines += ["SOURCES"] + [f"[{s['id']}] {s['title']} - {s['url']}" for s in content["sources"]]
    return "\n".join(lines) + "\n"


def main(issue_dir):
    issue_dir = Path(issue_dir)
    content = json.loads((issue_dir / "content.json").read_text())
    brand = json.loads((ROOT / "config" / "brand.json").read_text())
    (issue_dir / "img").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / brand["logo_file"], issue_dir / "img" / "logo.png")  # exact brand file, never redrawn

    used = {}

    def email_img(filename):
        cid = cid_for(filename)
        used[cid] = str(issue_dir / "img" / filename)
        return f"cid:{cid}"

    email_html = render(content, brand, email_img)
    # premailer warns about CSS it can't inline (e.g. media queries); those stay in <style>, which is fine.
    logging.getLogger("premailer").setLevel(logging.ERROR)
    email_html = transform(email_html, keep_style_tags=True, strip_important=False,
                           cssutils_logging_level=logging.CRITICAL)
    preview_html = transform(render(content, brand, lambda f: f"img/{f}"), keep_style_tags=True,
                             strip_important=False, cssutils_logging_level=logging.CRITICAL)

    (issue_dir / "email.html").write_text(email_html)
    (issue_dir / "preview.html").write_text(preview_html)
    (issue_dir / "email.txt").write_text(plain_text(content, brand))
    (issue_dir / "images.json").write_text(json.dumps(used, indent=2))

    missing = [p for p in used.values() if not Path(p).exists()]
    print(f"wrote email.html ({len(email_html.encode()) / 1024:.1f} KB), preview.html, email.txt, images.json")
    if missing:
        print("WARNING: missing images (run make_charts.py / save hero first):\n  " + "\n  ".join(missing))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
