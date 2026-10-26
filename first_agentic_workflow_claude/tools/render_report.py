"""Render the branded competitor report PDF from a report JSON.

Steps: check every cited source id exists -> build charts (build_charts.py)
-> inject brand tokens from brand/brand.json -> Jinja2 template -> WeasyPrint PDF.

Usage:
  python tools/render_report.py samples/sample_report.json --out .tmp/sample/report.pdf
  python tools/render_report.py output/<run>/report.json --out output/<run>/report.pdf

Writes report.html next to the PDF for debugging. Exits non-zero if any claim
cites a source id that is not in the sources list.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from weasyprint import HTML

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_charts import build_all  # noqa: E402
import project_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def collect_cited_ids(node, found: set) -> set:
    """Walk the report and collect every id in any *source_ids list."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key.endswith("source_ids") and isinstance(value, list):
                found.update(value)
            else:
                collect_cited_ids(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_cited_ids(item, found)
    return found


def brand_css(brand: dict) -> str:
    c = brand["colors"]
    seq = brand["chart_palette"]["sequential"]
    fonts = brand["fonts"]
    faces = "\n".join(
        f"@font-face {{ font-family: '{fonts['display']['family']}'; font-weight: {w}; "
        f"src: url('{(ROOT / p).as_uri()}'); }}"
        for w, p in fonts["files"].items()
    )
    stack = lambda f: ", ".join([f"'{f['family']}'"] + [f"'{x}'" if " " in x else x for x in f["fallback"]])  # noqa: E731
    tokens = {
        "primary": c["primary"], "deep": c["deep"], "navy": c["navy"], "light": c["light"],
        "tint": c["tint"], "border": c["border"], "border-light": c["border_light"],
        "text": c["text"], "text-secondary": c["text_secondary"], "text-muted": c["text_muted"],
        "on-blue-secondary": c["on_blue_secondary"],
        "success-pale": c["success_pale"], "warning-pale": c["warning_pale"],
        "warning-text": c["warning_text"], "danger-pale": c["danger_pale"],
        **{f"seq-{i + 1}": v for i, v in enumerate(seq)},
    }
    root_vars = " ".join(f"--c-{k}: {v};" for k, v in tokens.items())
    return (f"{faces}\n:root {{ {root_vars} --font-display: {stack(fonts['display'])}; "
            f"--font-body: {stack(fonts['body'])}; }}")


def priority(rec: dict) -> tuple:
    # Highest impact-per-effort first; ties go to the higher impact.
    return (-(rec["impact"] / rec["effort"]), -rec["impact"])


def render(report_path: Path, out_pdf: Path) -> Path:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    brand = json.loads((ROOT / "brand" / "brand.json").read_text(encoding="utf-8"))

    known = [s["id"] for s in report["sources"]]
    missing = sorted(collect_cited_ids(report, set()) - set(known))
    if missing:
        raise SystemExit(f"ERROR: cited source ids not in sources list: {missing}")

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    charts = build_all(report, out_pdf.parent / "charts")
    charts = {k: Path(v).as_uri() for k, v in charts.items()}

    run_date = date.fromisoformat(report["meta"]["run_date"])
    report["meta"]["run_date_long"] = run_date.strftime("%-d %B %Y")
    report.setdefault("us", None)

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), undefined=StrictUndefined,
                      autoescape=True, trim_blocks=True, lstrip_blocks=True)
    html = env.get_template("report.html.j2").render(
        r=report, brand=brand, charts=charts,
        srcnum={sid: i + 1 for i, sid in enumerate(known)},
        recs_sorted=sorted(report["recommendations"], key=priority),
        brand_css=brand_css(brand), root=ROOT.as_uri(),
        company=(report.get("us") or {}).get("name") or project_config.load()["company"]["name"],
    )
    (out_pdf.with_suffix(".html")).write_text(html, encoding="utf-8")
    HTML(string=html, base_url=str(ROOT)).write_pdf(out_pdf)
    return out_pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    pdf = render(args.report, args.out)
    print(f"PDF written: {pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
