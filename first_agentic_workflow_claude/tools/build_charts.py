"""Build the report's charts as brand-styled SVGs.

Reads the report JSON (see samples/sample_report.json for the shape) and
brand/brand.json, writes one SVG per chart into --out, and prints a JSON
manifest {chart_name: path} that render_report.py consumes.

Charts follow the brand rules: blues only, your company highlighted in brand blue,
competitors in a neutral grey-blue, every mark directly labelled (the neutral
is low-contrast on white, so labels carry identity), no native channel colours.

Usage:
  python tools/build_charts.py samples/sample_report.json --out .tmp/sample/charts
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONTENT_WIDTH_IN = 6.85  # A4 minus 2 x 18 mm margins


def load_brand() -> dict:
    return json.loads((ROOT / "brand" / "brand.json").read_text(encoding="utf-8"))


def setup_style(brand: dict) -> dict:
    for path in brand["fonts"]["files"].values():
        font_manager.fontManager.addfont(str(ROOT / path))
    c = brand["colors"]
    plt.rcParams.update({
        "font.family": brand["fonts"]["body"]["family"],
        "font.size": 8.5,
        "svg.fonttype": "path",  # text as outlines: renders identically in any PDF engine
        "axes.edgecolor": brand["chart_palette"]["gridline"],
        "axes.labelcolor": c["text_secondary"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": c["text_muted"],
        "ytick.color": c["text_secondary"],
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "figure.facecolor": "none",
        "axes.facecolor": "none",
    })
    return {
        "us": brand["chart_palette"]["us_highlight"],
        "neutral": brand["chart_palette"]["competitor_neutral"],
        "single": c["deep"],
        "grid": brand["chart_palette"]["gridline"],
        "text": c["text"],
        "text2": c["text_secondary"],
        "muted": c["text_muted"],
        "tint": c["tint"],
    }


def chart_operators(report: dict, s: dict, out: Path) -> Path | None:
    ops = report.get("market_overview", {}).get("operators")
    if not ops:
        return None
    labels = [o["name"] for o in ops]
    values = [o["value"] for o in ops]
    fig, ax = plt.subplots(figsize=(CONTENT_WIDTH_IN, 0.42 * len(ops) + 0.5))
    ax.barh(range(len(ops))[::-1], values, height=0.56, color=s["single"], linewidth=0)
    ax.set_yticks(range(len(ops))[::-1])
    ax.set_yticklabels(labels, fontsize=9, color=s["text"])
    for i, v in enumerate(values):
        ax.text(v + max(values) * 0.015, len(ops) - 1 - i, f"{v:g}", va="center",
                fontsize=8.5, fontweight="bold", color=s["text"])
    ax.set_xlim(0, max(values) * 1.12)
    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_color(s["grid"])
    path = out / "operators.svg"
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)
    return path


def chart_pagespeed(report: dict, s: dict, out: Path) -> Path | None:
    rows = []
    us = report.get("us", {})
    if us.get("pagespeed_mobile") is not None:
        rows.append((us.get("name", "Us"), us["pagespeed_mobile"], True))
    for comp in report.get("competitors", []):
        score = comp.get("web_seo", {}).get("pagespeed_mobile")
        if score is not None:
            rows.append((comp["name"], score, False))
    if not rows:
        return None
    rows.sort(key=lambda r: -r[1])
    fig, ax = plt.subplots(figsize=(CONTENT_WIDTH_IN, 0.36 * len(rows) + 0.6))
    n = len(rows)
    for i, (name, score, is_us) in enumerate(rows):
        y = n - 1 - i
        ax.barh(y, score, height=0.56, color=s["us"] if is_us else s["neutral"], linewidth=0)
        ax.text(score + 1.2, y, str(score), va="center", fontsize=8.5,
                fontweight="bold", color=s["text"])
    ax.set_yticks(range(n))
    ax.set_yticklabels([r[0] for r in reversed(rows)], fontsize=9, color=s["text"])
    for label, (_, _, is_us) in zip(ax.get_yticklabels(), reversed(rows)):
        if is_us:
            label.set_fontweight("bold")
    ax.set_xlim(0, 105)
    for x in (50, 90):
        ax.axvline(x, color=s["grid"], linewidth=0.8, linestyle=(0, (2, 2)), zorder=0)
    ax.set_xticks([0, 50, 90, 100])
    ax.tick_params(axis="x", labelsize=7.5)
    ax.set_xlabel("Google PageSpeed score, mobile (0–100)", fontsize=8, labelpad=6)
    ax.spines["left"].set_color(s["grid"])
    path = out / "pagespeed.svg"
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)
    return path


def chart_positioning(report: dict, s: dict, out: Path) -> Path | None:
    pos = report.get("matrix", {}).get("positioning")
    if not pos or not pos.get("points"):
        return None
    fig, ax = plt.subplots(figsize=(CONTENT_WIDTH_IN, 4.3))
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.axvline(3, color=s["grid"], linewidth=1, zorder=0)
    ax.axhline(3, color=s["grid"], linewidth=1, zorder=0)
    quads = [
        (5.4, 5.4, "Enterprise · multichannel", "right", "top"),
        (0.6, 5.4, "Multichannel · SME", "left", "top"),
        (5.4, 0.6, "Enterprise · SMS-only", "right", "bottom"),
        (0.6, 0.6, "SME · SMS-only", "left", "bottom"),
    ]
    for x, y, text, ha, va in quads:
        ax.text(x, y, text.upper(), ha=ha, va=va, fontsize=6.5, fontweight="bold",
                color=s["muted"])
    for p in sorted(pos["points"], key=lambda p: p.get("is_us", False)):
        is_us = p.get("is_us", False)
        ax.scatter(p["x"], p["y"], s=150 if is_us else 80,
                   color=s["us"] if is_us else s["neutral"],
                   edgecolor="white", linewidth=2, zorder=3)
        ax.annotate(p["name"], (p["x"], p["y"]), xytext=(9, 0), textcoords="offset points",
                    va="center", fontsize=9 if is_us else 8,
                    fontweight="bold" if is_us else "normal",
                    color=s["text"] if is_us else s["text2"], zorder=4)
    ax.set_xlabel(f"{pos['x_label']}  →", fontsize=8.5, labelpad=6)
    ax.set_ylabel(f"{pos['y_label']}  →", fontsize=8.5, labelpad=6)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["left"].set_color(s["grid"])
    ax.spines["bottom"].set_color(s["grid"])
    path = out / "positioning.svg"
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)
    return path


def chart_impact_effort(report: dict, s: dict, out: Path) -> Path | None:
    recs = report.get("recommendations")
    if not recs:
        return None
    fig, ax = plt.subplots(figsize=(CONTENT_WIDTH_IN, 4.3))
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    # Quick-wins quadrant (high impact, low effort) gets the brand tint.
    ax.add_patch(plt.Rectangle((0.5, 3), 2.5, 2.5, color=s["tint"], zorder=0, linewidth=0))
    ax.axvline(3, color=s["grid"], linewidth=1, zorder=1)
    ax.axhline(3, color=s["grid"], linewidth=1, zorder=1)
    quads = [
        (0.6, 5.4, "Quick wins", "left", "top", s["us"]),
        (5.4, 5.4, "Big bets", "right", "top", s["muted"]),
        (0.6, 0.6, "Fill-ins", "left", "bottom", s["muted"]),
        (5.4, 0.6, "Deprioritise", "right", "bottom", s["muted"]),
    ]
    for x, y, text, ha, va, color in quads:
        ax.text(x, y, text.upper(), ha=ha, va=va, fontsize=7, fontweight="bold", color=color)
    # Nudge overlapping points apart so labels stay readable.
    seen: dict[tuple, int] = {}
    for r in recs:
        key = (r["effort"], r["impact"])
        k = seen.get(key, 0)
        seen[key] = k + 1
        x = r["effort"] + 0.18 * k
        y = r["impact"] - 0.12 * k
        ax.scatter(x, y, s=330, color=s["single"], edgecolor="white", linewidth=2, zorder=3)
        ax.text(x, y, r["id"], ha="center", va="center", fontsize=7, fontweight="bold",
                color="white", zorder=4)
    ax.set_xlabel("Effort  →", fontsize=8.5, labelpad=6)
    ax.set_ylabel("Impact  →", fontsize=8.5, labelpad=6)
    ax.set_xticks([1, 2, 3, 4, 5])
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.tick_params(labelsize=7.5)
    ax.spines["left"].set_color(s["grid"])
    ax.spines["bottom"].set_color(s["grid"])
    path = out / "impact_effort.svg"
    fig.savefig(path, bbox_inches="tight", transparent=True)
    plt.close(fig)
    return path


CHARTS = {
    "operators": chart_operators,
    "pagespeed": chart_pagespeed,
    "positioning": chart_positioning,
    "impact_effort": chart_impact_effort,
}


def build_all(report: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    style = setup_style(load_brand())
    manifest = {}
    for name, fn in CHARTS.items():
        path = fn(report, style, out)
        if path:
            manifest[name] = str(path.resolve())
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    print(json.dumps(build_all(report, args.out), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
