"""Validate a report JSON before rendering. Exit 0 = pass, 1 = errors found.

Checks (errors unless noted):
  1. Matches schemas/report.schema.json (every claim carries >= 1 source id).
  2. Every cited source id exists; unused sources are a warning.
  3. Every non-internal source has a URL; access dates are ISO, not in the future
     (older than --max-age days is a warning).
  4. Matrix: every row scores every dimension; exactly one row for your company (warning).
     Positioning points match matrix rows (warning).
  5. Competitor ids unique; 5-8 direct and 2-3 indirect (warning; error with --strict).
  6. Production runs: is_sample false, no "Sample." text, no example.com URLs
     (skipped with --allow-sample).
  7. No forbidden terms anywhere (default: forbidden_terms in project.json).
  8. --check-links: fetch every URL. 404/410/DNS failure = error; 401/403/429 and
     timeouts = warning (many sites block bots — verify by hand).

Usage:
  python tools/validate_research.py output/<run>/report.json --check-links
  python tools/validate_research.py samples/sample_report.json --allow-sample
"""

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schemas" / "report.schema.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def walk_strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_strings(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def cited_ids(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        for k, v in node.items():
            if k.endswith("source_ids") and isinstance(v, list):
                found.update(v)
            else:
                cited_ids(v, found)
    elif isinstance(node, list):
        for v in node:
            cited_ids(v, found)
    return found


def check_link(url: str) -> tuple[str, str, str]:
    """Return (level, url, message); level in ok/warn/error."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=15, headers={"User-Agent": UA})
        if r.status_code in (405, 403, 400) or r.status_code >= 500:
            r = requests.get(url, allow_redirects=True, timeout=20, headers={"User-Agent": UA}, stream=True)
            r.close()
        code = r.status_code
        if code < 400:
            return "ok", url, str(code)
        if code in (404, 410):
            return "error", url, f"HTTP {code} (page gone)"
        return "warn", url, f"HTTP {code} (blocked or unavailable — check by hand)"
    except requests.exceptions.SSLError:
        return "warn", url, "SSL certificate problem (site reachable, certificate invalid)"
    except requests.exceptions.ConnectionError as e:
        if "Name or service" in str(e) or "resolve" in str(e) or "nodename" in str(e):
            return "error", url, "DNS failure (domain does not resolve)"
        return "warn", url, "connection refused/reset (often a bot or network block — check by hand)"
    except requests.exceptions.Timeout:
        return "warn", url, "timeout"
    except requests.RequestException as e:
        return "warn", url, f"{type(e).__name__}"


def validate(report: dict, args) -> tuple[list, list]:
    errors, warnings = [], []

    # 1. Schema
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for e in sorted(Draft202012Validator(schema).iter_errors(report), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in e.path) or "(root)"
        errors.append(f"schema: {loc}: {e.message[:200]}")

    sources = report.get("sources", [])
    ids = [s.get("id") for s in sources]

    # 2. Citations
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"duplicate source ids: {sorted(dupes)}")
    cited = cited_ids(report)
    missing = sorted(cited - set(ids))
    if missing:
        errors.append(f"cited but not in sources: {missing}")
    unused = sorted(set(ids) - cited)
    if unused:
        warnings.append(f"sources never cited: {unused}")

    # 3. Source hygiene
    today = date.today()
    for s in sources:
        sid = s.get("id", "?")
        if not str(sid).startswith("INT") and not s.get("url"):
            errors.append(f"source {sid}: external source without URL")
        try:
            acc = date.fromisoformat(s.get("accessed", ""))
            if acc > today:
                errors.append(f"source {sid}: access date {acc} is in the future")
            elif (today - acc).days > args.max_age:
                warnings.append(f"source {sid}: accessed {acc}, older than {args.max_age} days — re-check")
        except ValueError:
            errors.append(f"source {sid}: access date not ISO (YYYY-MM-DD)")

    # 4. Matrix
    mx = report.get("matrix", {})
    keys = [d["key"] for d in mx.get("dimensions", [])]
    rows = mx.get("rows", [])
    for row in rows:
        gaps = [k for k in keys if k not in row.get("scores", {})]
        extra = [k for k in row.get("scores", {}) if k not in keys]
        if gaps:
            errors.append(f"matrix row '{row.get('name')}': missing scores for {gaps}")
        if extra:
            warnings.append(f"matrix row '{row.get('name')}': scores for unknown dimensions {extra}")
    if sum(1 for r in rows if r.get("is_us")) != 1:
        warnings.append("matrix: expected exactly one row with is_us = true")
    row_names = {r.get("name") for r in rows}
    for p in mx.get("positioning", {}).get("points", []):
        if p.get("name") not in row_names:
            warnings.append(f"positioning point '{p.get('name')}' has no matching matrix row")

    # 5. Competitors
    comps = report.get("competitors", [])
    cids = [c.get("id") for c in comps]
    if len(cids) != len(set(cids)):
        errors.append("duplicate competitor ids")
    n_direct = sum(1 for c in comps if c.get("type") == "direct")
    n_indirect = sum(1 for c in comps if c.get("type") == "indirect")
    for label, n, lo, hi in (("direct", n_direct, 5, 8), ("indirect", n_indirect, 2, 3)):
        if not lo <= n <= hi:
            (errors if args.strict else warnings).append(f"{n} {label} competitors (target {lo}-{hi})")
    comp_names = {c.get("name") for c in comps}
    for name in comp_names - row_names:
        warnings.append(f"competitor '{name}' is not in the comparison matrix")

    # 6. Production hygiene
    meta = report.get("meta", {})
    if not args.allow_sample:
        if meta.get("is_sample"):
            errors.append("meta.is_sample is true — set false for a real run")
        for path, text in walk_strings(report):
            if re.match(r"\s*(Sample|TODO)\b", text):
                errors.append(f"placeholder text left at {path}")
            if "example.com" in text:
                errors.append(f"example.com URL at {path}")

    # 7. Forbidden terms
    forbidden = [t for t in (args.forbid or project_config.load()["forbidden_terms"]) if t]
    # Case-sensitive on purpose: a company called "Acme Data" must not match the ordinary phrase "acme data".
    for path, text in walk_strings(report):
        for term in forbidden:
            if re.search(rf"\b{re.escape(term)}\b", text):
                errors.append(f"forbidden term '{term}' at {path}")

    # 8. Links
    if args.check_links:
        urls = sorted({s["url"] for s in sources if s.get("url")})
        with ThreadPoolExecutor(max_workers=8) as pool:
            for level, url, msg in pool.map(check_link, urls):
                if level == "error":
                    errors.append(f"link: {url} — {msg}")
                elif level == "warn":
                    warnings.append(f"link: {url} — {msg}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path)
    parser.add_argument("--check-links", action="store_true", help="fetch every source URL")
    parser.add_argument("--allow-sample", action="store_true", help="skip placeholder checks (sample data)")
    parser.add_argument("--strict", action="store_true", help="competitor-count targets become errors")
    parser.add_argument("--max-age", type=int, default=90, help="warn if a source was accessed more than N days ago")
    parser.add_argument("--forbid", action="append", help="term that must not appear (repeatable; replaces defaults)")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    errors, warnings = validate(report, args)

    n_claims = sum(1 for p, _ in walk_strings(report) if p.endswith(".text"))
    print(f"Report: {args.report}  ·  {len(report.get('sources', []))} sources  ·  "
          f"{len(report.get('competitors', []))} competitors  ·  ~{n_claims} claims")
    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  ERROR {e}")
    print("RESULT: " + ("FAIL" if errors else "PASS") + f" ({len(errors)} errors, {len(warnings)} warnings)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
