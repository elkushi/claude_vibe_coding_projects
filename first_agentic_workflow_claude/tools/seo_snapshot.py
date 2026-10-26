"""Deterministic website / on-page SEO snapshot for one or more sites.

For each URL: fetches the homepage, robots.txt and sitemap(s), then reports
title, meta description, H1s, language and hreflang, canonical, schema.org
types, links to pricing / API docs / blog / contact pages, social profiles, OTT
channel mentions, sitemap size and recent-content cadence. Market-specific checks
(local-script share, local-language URLs, a regulator's licence number) come from
the "market" block of project.json and are skipped when left empty.

Usage:
  python tools/seo_snapshot.py https://your-company.com https://competitor.com --out .tmp/run/seo.json
"""

import argparse
import gzip
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_config  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
MARKET = project_config.load()["market"]


def _market_rx(key: str):
    return re.compile(MARKET[key], re.I) if MARKET.get(key) else None


LOCAL_SCRIPT = _market_rx("local_script_regex")
CERTIFICATE = _market_rx("certificate_regex")
LOCAL_URL = _market_rx("local_language_url_regex")
REGULATOR = MARKET.get("regulator") or ""

# (pattern on the URL path, pattern on the link text) — whole words, so "corporate" never matches "rate".
LINK_HINTS = {
    "pricing": (r"\b(pricing|prices?|tariffs?|packages?|plans|rates)\b", r"\b(pricing|price|prices|tariff|packages?|plans)\b"),
    "api_docs": (r"(^|/)(api|apis|docs?|developers?|documentation|sdk)(/|$|\.)", r"\b(api (docs|documentation|reference)|developers?|documentation|sdk)\b"),
    "blog": (r"(^|/)(blog|news|articles?|insights?|resources)(/|$)", r"^(blog|news|articles|insights)$"),
    "contact": (r"(^|/)contacts?(/|$|-)", r"\bcontact\b"),
    "signup": (r"(^|/)(sign-?up|register|free-trial)(/|$)", r"\b(sign ?up|register|free trial|try (it )?free)\b"),
    "faq": (r"(^|/)faqs?(/|$|_|-)|sms_faq", r"\b(faq|frequently asked)\b"),
}
SOCIAL = {
    "linkedin": "linkedin.com", "facebook": "facebook.com", "youtube": "youtube.com",
    "x": ("twitter.com", "x.com"), "instagram": "instagram.com",
}
CHANNEL_TERMS = {
    "whatsapp": r"whats\s?app", "viber": r"\bviber\b", "telegram": r"\btelegram\b",
    "messenger": r"\bmessenger\b", "rcs": r"\bRCS\b", "imo": r"\bimo\b", "voice_otp": r"voice\s?(otp|call)",
}


class Deadline(Exception):
    pass


def get(session: requests.Session, url: str, deadline_s: float = 30, max_bytes: int = 15_000_000,
        attempts: int = 2):
    """GET with a hard wall-clock deadline (requests' timeout is per read, so a
    slow-trickling server could otherwise stall a run indefinitely). Retries once."""
    result = None
    for _ in range(attempts):
        result = _get_once(session, url, deadline_s, max_bytes)
        if not isinstance(result, Exception):
            return result
    return result


def _get_once(session, url, deadline_s, max_bytes):
    start = time.monotonic()
    try:
        r = session.get(url, timeout=(10, 10), allow_redirects=True, stream=True)
        chunks, size = [], 0
        for chunk in r.iter_content(65536):
            chunks.append(chunk)
            size += len(chunk)
            if time.monotonic() - start > deadline_s:
                r.close()
                return Deadline(f"no complete response within {deadline_s:.0f}s")
            if size > max_bytes:
                break
        r._content = b"".join(chunks)
        return r
    except requests.RequestException as e:
        return e


def sitemap_urls(session, base: str, robots_text: str, limit_maps: int = 6) -> tuple[list, list]:
    """Return (sitemap urls tried, [(loc, lastmod or None)])."""
    candidates = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_text or "")
    candidates += [urljoin(base, "/sitemap.xml"), urljoin(base, "/sitemap_index.xml"), urljoin(base, "/wp-sitemap.xml")]
    seen, queue, entries = [], list(dict.fromkeys(candidates)), []
    while queue and len(seen) < limit_maps:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.append(sm)
        r = get(session, sm)
        if isinstance(r, Exception) or r.status_code != 200:
            continue
        content = r.content
        if sm.endswith(".gz"):
            try:
                content = gzip.decompress(content)
            except OSError:
                continue
        soup = BeautifulSoup(content, "xml")
        for child in soup.find_all("sitemap"):
            loc = child.find("loc")
            if loc and loc.text.strip() not in seen:
                queue.append(loc.text.strip())
        for u in soup.find_all("url"):
            loc, mod = u.find("loc"), u.find("lastmod")
            if loc:
                entries.append((loc.text.strip(), mod.text.strip()[:10] if mod else None))
    return seen, entries


def robots_blocks_all(robots_text: str) -> bool:
    """True if the `User-agent: *` group contains `Disallow: /`."""
    in_star_group, prev_was_agent = False, False
    for raw in robots_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = (p.strip() for p in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            in_star_group = (value == "*") or (prev_was_agent and in_star_group)
            prev_was_agent = True
            continue
        prev_was_agent = False
        if in_star_group and field == "disallow" and value == "/":
            return True
    return False


def parse_date(s):
    try:
        return datetime.fromisoformat(s[:10]).date()
    except (TypeError, ValueError):
        return None


def snapshot(url: str) -> dict:
    if not url.startswith("http"):
        url = "https://" + url
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "en,bn;q=0.8"})
    out = {"input_url": url, "checked": date.today().isoformat()}

    r = get(session, url)
    if isinstance(r, Exception):
        out["error"] = f"{type(r).__name__}: {str(r)[:160]}"
        return out
    out.update({
        "final_url": r.url, "status": r.status_code, "https": r.url.startswith("https://"),
        "redirected": r.url.rstrip("/") != url.rstrip("/"), "html_kb": round(len(r.content) / 1024, 1),
    })
    if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
        out["error"] = f"HTTP {r.status_code}"
        return out

    soup = BeautifulSoup(r.text, "html.parser")
    base = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"
    host = urlparse(r.url).netloc.removeprefix("www.")

    meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    canonical = soup.find("link", rel=lambda v: v and "canonical" in v)
    out["title"] = (soup.title.string or "").strip() if soup.title else None
    out["title_length"] = len(out["title"] or "")
    out["meta_description"] = meta_desc.get("content", "").strip() if meta_desc else None
    out["meta_description_length"] = len(out["meta_description"] or "")
    out["h1"] = [h.get_text(" ", strip=True)[:120] for h in soup.find_all("h1")][:5]
    out["h2_count"] = len(soup.find_all("h2"))
    out["html_lang"] = soup.html.get("lang") if soup.html else None
    out["hreflang"] = sorted({l.get("hreflang") for l in soup.find_all("link", hreflang=True)})
    out["canonical"] = canonical.get("href") if canonical else None
    out["og_tags"] = bool(soup.find("meta", property=re.compile("^og:")))
    out["viewport_meta"] = bool(soup.find("meta", attrs={"name": "viewport"}))

    types = set()
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                t = item.get("@type")
                types.update(t if isinstance(t, list) else [t] if t else [])
                stack.extend(item.get("@graph", []))
    out["schema_org_types"] = sorted(types)

    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    letters = [c for c in text if c.isalpha()]
    out["word_count"] = len(text.split())
    out["local_script_share"] = (round(sum(1 for c in letters if LOCAL_SCRIPT.match(c)) / len(letters), 3)
                                 if letters else 0.0) if LOCAL_SCRIPT else None

    links = []
    for a in soup.find_all("a", href=True):
        raw = a["href"].strip()
        if not raw or raw.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        href = urljoin(r.url, raw).split("#")[0]
        links.append((href, a.get_text(" ", strip=True).lower()))
    internal = [l for l in links if urlparse(l[0]).netloc.removeprefix("www.") == host]
    out["links_internal"] = len({l[0] for l in internal})
    out["links_external"] = len({l[0] for l in links if l not in internal and l[0].startswith("http")})
    out["likely_js_rendered"] = out["links_internal"] < 8  # content built by JavaScript; raw HTML undercounts
    found = {}
    local_terms = MARKET.get("local_link_terms", {})
    for key, (path_pat, text_pat) in LINK_HINTS.items():
        if local_terms.get(key):
            text_pat = f"{text_pat}|{local_terms[key]}"
        found[key] = next((h for h, t in internal
                           if re.search(path_pat, urlparse(h).path.lower()) or re.search(text_pat, t)), None)
    out["key_pages"] = found
    out["social"] = {}
    for name, dom in SOCIAL.items():
        doms = dom if isinstance(dom, tuple) else (dom,)
        out["social"][name] = next((h for h, _ in links if any(d in urlparse(h).netloc for d in doms)), None)
    out["whatsapp_contact_link"] = any("wa.me" in h or "api.whatsapp.com" in h for h, _ in links)

    out["channel_mentions"] = {k: bool(re.search(p, text, re.I)) for k, p in CHANNEL_TERMS.items()}
    if CERTIFICATE:
        certs = sorted({m.group(0).upper().replace(" ", "-") for m in CERTIFICATE.finditer(r.text)})
        out["regulator_certificate_on_homepage"] = certs or None
    if REGULATOR:
        out["mentions_regulator"] = bool(re.search(rf"\b{re.escape(REGULATOR)}\b", text))

    robots = get(session, urljoin(base, "/robots.txt"))
    robots_text = robots.text if not isinstance(robots, Exception) and robots.status_code == 200 else ""
    out["robots_txt"] = bool(robots_text)
    out["robots_blocks_all"] = robots_blocks_all(robots_text)

    maps, entries = sitemap_urls(session, base, robots_text)
    dated = [d for d in (parse_date(m) for _, m in entries) if d]
    recent_cut = date.today() - timedelta(days=90)
    blogish = [loc for loc, _ in entries if re.search(r"/(blog|news|article|insights?|post)s?/", loc, re.I)]
    out["sitemap"] = {
        "found": bool(entries), "maps_checked": len(maps), "url_count": len(entries),
        "latest_lastmod": max(dated).isoformat() if dated else None,
        "updated_last_90_days": sum(1 for d in dated if d >= recent_cut),
        "blog_like_urls": len(blogish),
        "local_language_urls": sum(1 for loc, _ in entries if LOCAL_URL.search(loc)) if LOCAL_URL else None,
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--out", type=Path, help="write JSON here (default: stdout)")
    args = parser.parse_args()
    results = [snapshot(u) for u in args.urls]
    payload = json.dumps(results if len(results) > 1 else results[0], indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
