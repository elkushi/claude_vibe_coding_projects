"""Google PageSpeed Insights scores (mobile + desktop) for one or more URLs.

Free API. Works without a key at low volume; set PAGESPEED_API_KEY in .env for
higher quota. Each call takes 15-60 s. On 429 (quota) it backs off and retries.

Output per URL and strategy: performance / SEO / accessibility / best-practices
scores (0-100), lab metrics (LCP, CLS, TBT, FCP), and Chrome UX field data
category when Google has it.

Usage:
  python tools/pagespeed.py https://your-company.com https://competitor.com --out .tmp/run/pagespeed.json
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = ["performance", "seo", "accessibility", "best-practices"]
METRICS = {
    "lcp_s": ("largest-contentful-paint", 1000),
    "fcp_s": ("first-contentful-paint", 1000),
    "tbt_ms": ("total-blocking-time", 1),
    "cls": ("cumulative-layout-shift", 1),
}


def run(url: str, strategy: str, key: str | None, retries: int = 4) -> dict:
    params = [("url", url), ("strategy", strategy)] + [("category", c) for c in CATEGORIES]
    if key:
        params.append(("key", key))
    delay = 20
    for attempt in range(retries):
        try:
            r = requests.get(API, params=params, timeout=150)
        except requests.RequestException as e:
            if attempt == retries - 1:
                return {"error": f"{type(e).__name__}"}
            time.sleep(delay)
            continue
        if r.status_code == 429 and attempt < retries - 1:
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code != 200:
            msg = r.json().get("error", {}).get("message", "") if "json" in r.headers.get("content-type", "") else ""
            return {"error": f"HTTP {r.status_code}: {msg[:200]}"}
        data = r.json()
        lh = data.get("lighthouseResult", {})
        cats = lh.get("categories", {})
        audits = lh.get("audits", {})
        out = {c: round(cats[c]["score"] * 100) if cats.get(c, {}).get("score") is not None else None for c in CATEGORIES}
        for name, (audit, div) in METRICS.items():
            v = audits.get(audit, {}).get("numericValue")
            out[name] = round(v / div, 2) if v is not None else None
        field = data.get("loadingExperience", {})
        out["field_data"] = field.get("overall_category") if field.get("metrics") else None
        out["final_url"] = lh.get("finalUrl") or lh.get("finalDisplayedUrl")
        return out
    return {"error": "quota exhausted after retries"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--strategy", choices=["mobile", "desktop", "both"], default="both")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    key = os.getenv("PAGESPEED_API_KEY") or None
    strategies = ["mobile", "desktop"] if args.strategy == "both" else [args.strategy]

    results = []
    for url in args.urls:
        if not url.startswith("http"):
            url = "https://" + url
        entry = {"url": url, "checked": date.today().isoformat(), "source": "Google PageSpeed Insights"}
        for s in strategies:
            entry[s] = run(url, s, key)
            print(f"{url} [{s}]: {entry[s].get('performance', entry[s].get('error'))}", file=sys.stderr)
        results.append(entry)

    payload = json.dumps(results if len(results) > 1 else results[0], indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
