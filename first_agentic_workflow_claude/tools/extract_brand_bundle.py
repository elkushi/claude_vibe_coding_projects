"""Unpack a self-contained "bundler" HTML page (e.g. the brand guidelines export).

The page stores every asset (images, fonts) as base64 (optionally gzipped) in a
<script type="__bundler/manifest"> JSON block, and the real page HTML as a JSON
string in <script type="__bundler/template">, referencing assets by UUID.

This tool writes:
  <out>/assets/<uuid>.<ext>   every embedded asset
  <out>/template.html         the real page, with UUIDs rewritten to assets/ paths
  <out>/template.txt          visible text only (for reading the guidelines)
  <out>/manifest.json         uuid -> {file, mime, bytes}

Usage:
  python tools/extract_brand_bundle.py "brand/guidelines/<file>.html" --out brand/extracted
"""

import argparse
import base64
import gzip
import html
import json
import re
import sys
from pathlib import Path

EXT_BY_MIME = {
    "image/svg+xml": "svg",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "font/woff2": "woff2",
    "font/woff": "woff",
    "font/ttf": "ttf",
    "font/otf": "otf",
    "application/font-woff": "woff",
    "application/font-woff2": "woff2",
    "application/x-font-ttf": "ttf",
    "application/x-font-otf": "otf",
    "text/css": "css",
    "text/javascript": "js",
    "application/javascript": "js",
    "text/html": "html",
}


def read_block(source: str, block_type: str) -> str | None:
    match = re.search(
        r'<script type="__bundler/' + block_type + r'"[^>]*>(.*?)</script>',
        source,
        re.DOTALL,
    )
    return match.group(1).strip() if match else None


def visible_text(page_html: str) -> str:
    page_html = re.sub(r"<(script|style)\b.*?</\1>", " ", page_html, flags=re.DOTALL | re.I)
    page_html = re.sub(r"<br\s*/?>|</(p|div|h[1-6]|li|tr|section)>", "\n", page_html, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page_html))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--out", type=Path, default=Path("brand/extracted"))
    args = parser.parse_args()

    source = args.bundle.read_text(encoding="utf-8")
    manifest_raw = read_block(source, "manifest")
    template_raw = read_block(source, "template")
    if not manifest_raw or not template_raw:
        print("ERROR: manifest or template block not found", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_raw)
    template = json.loads(template_raw)

    assets_dir = args.out / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    index = {}
    for uuid, entry in manifest.items():
        data = base64.b64decode(entry["data"])
        if entry.get("compressed"):
            data = gzip.decompress(data)
        mime = entry.get("mime", "application/octet-stream")
        ext = EXT_BY_MIME.get(mime.split(";")[0].strip(), "bin")
        filename = f"{uuid}.{ext}"
        (assets_dir / filename).write_bytes(data)
        index[uuid] = {"file": f"assets/{filename}", "mime": mime, "bytes": len(data)}
        template = template.replace(uuid, f"assets/{filename}")

    (args.out / "template.html").write_text(template, encoding="utf-8")
    (args.out / "template.txt").write_text(visible_text(template), encoding="utf-8")
    (args.out / "manifest.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    by_mime = {}
    for item in index.values():
        by_mime[item["mime"]] = by_mime.get(item["mime"], 0) + 1
    print(f"Extracted {len(index)} assets to {assets_dir}: {by_mime}")
    print(f"Template: {args.out / 'template.html'} ({len(template):,} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
