"""Merge per-competitor research files into one report.json.

Inputs (in a run folder):
  data/base.json               market overview, analysis, your own matrix row, long tail, meta
                               (sources may use any local ids, e.g. M1, M2; INT = internal)
  data/competitors/*.json      one file per competitor from the research agents:
                               {"competitor": {...}, "sources": [...], "matrix_evidence": {...},
                                "long_tail_finds": [...], "open_questions": [...]}
  data/pagespeed.json          optional, from tools/pagespeed.py

Steps: dedupe sources by normalised URL -> renumber S1..Sn in first-use order
(base first, then competitors in --order) -> rewrite every source_ids list ->
fill PageSpeed scores -> append matrix rows from matrix_evidence -> add long-tail
finds -> write report.json, plus data/matrix_evidence.md and data/open_questions.md
for human review.

Usage:
  python tools/merge_research.py output/2026-10-19_bd-a2p --order ssl-wireless,reve,comjagat
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_config  # noqa: E402


def norm_url(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return f"{host}{path}{'?' + p.query if p.query else ''}"


def rewrite_ids(node, mapping: dict):
    if isinstance(node, dict):
        for k, v in node.items():
            if k.endswith("source_ids") and isinstance(v, list):
                new = []
                for sid in v:
                    m = mapping.get(sid, sid)
                    if m not in new:
                        new.append(m)
                node[k] = new
            else:
                rewrite_ids(v, mapping)
    elif isinstance(node, list):
        for v in node:
            rewrite_ids(v, mapping)


def first_use_order(node, out: list):
    if isinstance(node, dict):
        for k, v in node.items():
            if k.endswith("source_ids") and isinstance(v, list):
                out.extend(x for x in v if x not in out)
            else:
                first_use_order(v, out)
    elif isinstance(node, list):
        for v in node:
            first_use_order(v, out)
    return out


class SourceRegistry:
    """Assigns one global id per unique URL (internal sources keep their INT ids)."""

    def __init__(self):
        self.by_key, self.entries, self.counter = {}, [], 0

    def add(self, src: dict) -> str:
        sid = src["id"]
        if str(sid).startswith("INT"):
            key = ("INT", sid)
        else:
            key = norm_url(src.get("url")) or ("NOURL", src.get("title"))
        if key in self.by_key:
            return self.by_key[key]
        if str(sid).startswith("INT"):
            gid = sid
        else:
            self.counter += 1
            gid = f"S{self.counter}"
        entry = {k: v for k, v in src.items() if k in ("url", "title", "publisher", "accessed", "published", "note")}
        entry["id"] = gid
        self.by_key[key] = gid
        self.entries.append(entry)
        return gid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", type=Path)
    parser.add_argument("--order", help="comma-separated competitor ids (default: file name order)")
    parser.add_argument("--out", type=Path, help="default: <run>/report.json")
    args = parser.parse_args()

    data = args.run / "data"
    base = json.loads((data / "base.json").read_text(encoding="utf-8"))
    files = {p.stem: p for p in sorted((data / "competitors").glob("*.json"))}
    order = args.order.split(",") if args.order else list(files)
    missing = [c for c in order if c not in files]
    if missing:
        print(f"ERROR: no research file for {missing}", file=sys.stderr)
        return 1

    registry = SourceRegistry()
    internal = {s["id"]: s for s in base.get("sources", []) if str(s["id"]).startswith("INT")}

    # Base: register sources in order of first citation, then rewrite.
    base_sources = {s["id"]: s for s in base.get("sources", [])}
    base_map = {}
    for sid in first_use_order({k: v for k, v in base.items() if k != "sources"}, []):
        if sid in base_sources:
            base_map[sid] = registry.add(base_sources[sid])
    for sid, s in base_sources.items():  # uncited base sources still kept (validator warns)
        base_map.setdefault(sid, registry.add(s))
    rewrite_ids(base, base_map)

    competitors, evidence_md, questions_md = [], [], []
    cross_refs = {}  # "infobip:L1" -> global id, so analysis in base.json can cite competitor evidence
    long_tail = list(base.get("long_tail", []))
    seen_tail = {t["name"].lower() for t in long_tail}
    # Profiled competitors never appear again in the long tail.
    profiled = set()
    for cid in order:
        name = json.loads(files[cid].read_text(encoding="utf-8"))["competitor"]["name"].lower()
        profiled.update({name, name.split(" (")[0], name.split(" / ")[0], cid.replace("-", " ")})

    def already_covered(name: str) -> bool:
        n = name.lower()
        return n in seen_tail or any(p and (p in n or n in p) for p in profiled)
    for cid in order:
        doc = json.loads(files[cid].read_text(encoding="utf-8"))
        comp = doc["competitor"]
        local = {s["id"]: s for s in doc.get("sources", [])}
        mapping = {}
        for sid in first_use_order(comp, []) + [s for s in local]:
            if sid in local and sid not in mapping:
                mapping[sid] = registry.add(local[sid])
            elif str(sid).startswith("INT") and sid not in internal:
                print(f"WARN {cid}: cites {sid} but base.json has no such internal source", file=sys.stderr)
        rewrite_ids(comp, mapping)
        competitors.append(comp)
        cross_refs.update({f"{cid}:{lid}": gid for lid, gid in mapping.items()})

        ev = doc.get("matrix_evidence", {})
        if ev:
            row = {"name": comp["name"], "scores": {k: v["score"] for k, v in ev.items() if isinstance(v, dict) and "score" in v}}
            base["matrix"]["rows"] = [r for r in base["matrix"]["rows"] if r["name"] != comp["name"]] + [row]
            evidence_md.append(f"## {comp['name']}\n" + "\n".join(f"- **{k}** {v.get('score')}: {v.get('why', '')}" for k, v in ev.items()))
        for t in doc.get("long_tail_finds", []):
            if not already_covered(t["name"]):
                t = dict(t)
                t["source_ids"] = [mapping.get(s, s) for s in t.get("source_ids", [])]
                long_tail.append(t)
                seen_tail.add(t["name"].lower())
        if doc.get("open_questions"):
            questions_md.append(f"## {comp['name']}\n" + "\n".join(f"- {q}" for q in doc["open_questions"]))

    # Resolve cross-references in the base (analysis) sections.
    base_body = {k: v for k, v in base.items() if k not in ("sources", "competitors")}
    unresolved = sorted({sid for sid in first_use_order(base_body, []) if ":" in sid and sid not in cross_refs})
    if unresolved:
        print(f"ERROR: unresolved cross-references in base.json: {unresolved}", file=sys.stderr)
        return 1
    rewrite_ids(base_body, cross_refs)
    base.update(base_body)

    us_site = base.get("us", {}).pop("website", project_config.load()["company"]["website"]) if base.get("us") else None

    # PageSpeed scores by host.
    ps_path = data / "pagespeed.json"
    if ps_path.exists():
        ps = json.loads(ps_path.read_text(encoding="utf-8"))
        ps = ps if isinstance(ps, list) else [ps]
        by_host = {urlparse(e["url"]).netloc.lower().removeprefix("www."): e for e in ps}

        def scores(site: str):
            # A website field may list several domains ("revesms.com · revesoft.com"); use the first measured one.
            for part in re.split(r"\s*(?:/|·|,|\|)\s+|\s+", site or ""):
                if "." not in part:
                    continue
                host = urlparse(part if "//" in part else "https://" + part).netloc.lower().removeprefix("www.")
                e = by_host.get(host)
                if e:
                    return e.get("mobile", {}).get("performance"), e.get("desktop", {}).get("performance")
            return None, None

        for comp in competitors:
            m, d = scores(comp.get("website", ""))
            comp["web_seo"]["pagespeed_mobile"], comp["web_seo"]["pagespeed_desktop"] = m, d
        if base.get("us"):
            base["us"]["pagespeed_mobile"] = scores(us_site)[0]

    base["competitors"] = competitors
    base["long_tail"] = long_tail
    base["sources"] = registry.entries
    # Key order matching the schema, for readable diffs.
    keys = ["meta", "us", "sources", "executive_summary", "market_overview", "competitors", "long_tail",
            "matrix", "opportunities", "recommendations", "methodology"]
    report = {k: base[k] for k in keys if k in base}

    out = args.out or args.run / "report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (data / "matrix_evidence.md").write_text("# Matrix score evidence\n\n" + "\n\n".join(evidence_md) + "\n", encoding="utf-8")
    (data / "open_questions.md").write_text("# Open questions from research\n\n" + "\n\n".join(questions_md) + "\n", encoding="utf-8")
    print(f"Wrote {out}: {len(competitors)} competitors, {len(registry.entries)} unique sources, "
          f"{len(long_tail)} long-tail entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
