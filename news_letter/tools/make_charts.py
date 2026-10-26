"""Render the charts defined in an issue's content.json to brand-styled PNGs.

Usage:
    python tools/make_charts.py .tmp/<slug>

Reads  <issue_dir>/content.json  (the "charts" list) and config/brand.json.
Writes <issue_dir>/img/chart_<id>.png at 2x resolution (1020px wide, shown at 510px).

Brand rules applied: Inter type, ink + greys for data, brand red ONLY for the
highlighted item (the one thing the reader should notice), flat, no shadows.

Supported chart types and their "data" shape:
    bar      {"labels": [...], "values": [...], "unit": "%", "highlight": <index>}
    hbar     {"labels": [...], "values": [...], "unit": "%", "highlight": <index>}
    line     {"x": [...], "series": {"Name": [...], ...}, "unit": "", "highlight": "Name"}
    donut    {"labels": [...], "values": [...], "center": "text", "highlight": <index>}
    timeline {"events": [{"date": "2019", "label": "...", "highlight": true}, ...]}
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WIDTH_IN, DPI = 5.1, 200  # 510px display width at 2x


def load_brand():
    brand = json.loads((ROOT / "config" / "brand.json").read_text())
    for ttf in (ROOT / brand["font_dir"]).glob("Inter-*.ttf"):
        font_manager.fontManager.addfont(str(ttf))
    plt.rcParams["font.family"] = "Inter"
    return brand


def colors_for(n, highlight, brand):
    """Ink/grey for every item; brand red only for the highlighted one."""
    c = brand["colors"]
    if highlight is None:
        pal = c["chart_palette"]
        return [pal[i % len(pal)] for i in range(n)]
    return [c["chart_highlight"] if i == highlight else c["ink"] for i in range(n)]


def style_axes(ax, brand):
    c = brand["colors"]
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(c["border"])
    ax.tick_params(colors=c["secondary"], labelsize=8.5, length=0)
    ax.yaxis.grid(True, color=c["border"], linewidth=0.7)
    ax.set_axisbelow(True)


def new_fig(brand, height_in=3.0):
    fig, ax = plt.subplots(figsize=(WIDTH_IN, height_in), dpi=DPI)
    bg = brand["colors"]["white"]  # sits inside a bordered white card in the email
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)
    return fig, ax


def add_title(fig, chart, brand):
    if chart.get("title"):
        fig.suptitle(chart["title"], x=0.02, ha="left", fontsize=11.5, fontweight="heavy",
                     color=brand["colors"]["ink"])


def fmt(v, unit):
    v = int(v) if float(v).is_integer() else v
    return f"{v}{unit}"


def bar(chart, brand, horizontal=False):
    d, c = chart["data"], brand["colors"]
    unit = d.get("unit", "")
    labels, values = d["labels"], d["values"]
    colors = colors_for(len(values), d.get("highlight"), brand) if d.get("highlight") is not None \
        else [c["ink"]] * len(values)
    fig, ax = new_fig(brand, 0.45 * len(values) + 0.9 if horizontal else 3.0)
    if horizontal:
        bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1], height=0.6)
        style_axes(ax, brand)
        ax.yaxis.grid(False)
        ax.xaxis.set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="y", labelcolor=c["text"])
        for b_, v in zip(bars, values[::-1]):
            ax.text(b_.get_width(), b_.get_y() + b_.get_height() / 2, " " + fmt(v, unit),
                    va="center", fontsize=8.5, fontweight="bold", color=c["ink"])
    else:
        bars = ax.bar(labels, values, color=colors, width=0.6)
        style_axes(ax, brand)
        ax.yaxis.set_visible(False)  # values are labelled on the bars
        ax.yaxis.grid(False)
        for b_, v in zip(bars, values):
            ax.text(b_.get_x() + b_.get_width() / 2, b_.get_height(), fmt(v, unit),
                    ha="center", va="bottom", fontsize=8.5, fontweight="bold", color=c["ink"])
    return fig


def line(chart, brand):
    d, c = chart["data"], brand["colors"]
    names = list(d["series"])
    hl = names.index(d["highlight"]) if d.get("highlight") in names else None
    colors = colors_for(len(names), hl, brand)
    if hl is not None:  # non-highlighted series step back to grey
        colors = [col if i == hl else c["secondary"] for i, col in enumerate(colors)]
    fig, ax = new_fig(brand)
    for col, name in zip(colors, names):
        ys = d["series"][name]
        ax.plot(d["x"], ys, color=col, linewidth=2.2, marker="o", markersize=3.5, label=name)
        ax.annotate(fmt(ys[-1], d.get("unit", "")), (d["x"][-1], ys[-1]), xytext=(5, 0),
                    textcoords="offset points", fontsize=8.5, fontweight="bold", color=col, va="center")
    style_axes(ax, brand)
    if len(names) > 1:
        ax.legend(frameon=False, fontsize=8.5, labelcolor=c["text"])
    return fig


def donut(chart, brand):
    d, c = chart["data"], brand["colors"]
    colors = colors_for(len(d["values"]), d.get("highlight"), brand)
    if d.get("highlight") is not None:  # highlighted slice red, the rest in graded greys
        greys = [c["ink"], c["secondary"], c["caption"], c["border"]]
        it = iter(greys * 3)
        colors = [col if i == d["highlight"] else next(it) for i, col in enumerate(colors)]
    fig, ax = new_fig(brand)
    wedges, _ = ax.pie(d["values"], colors=colors, startangle=90, counterclock=False,
                       wedgeprops={"width": 0.36, "edgecolor": c["white"], "linewidth": 2})
    ax.set_aspect("equal")
    fig.subplots_adjust(left=0.02, right=0.6, top=0.86, bottom=0.04)
    if d.get("center"):
        ax.text(0, 0, d["center"], ha="center", va="center", fontsize=15, fontweight="heavy", color=c["ink"])
    total = sum(d["values"])
    labels = [f"{l}  {fmt(round(v / total * 100, 1), '%')}" for l, v in zip(d["labels"], d["values"])]
    ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=8.5,
              labelcolor=c["text"])
    return fig


def timeline(chart, brand):
    c = brand["colors"]
    events = chart["data"]["events"]
    fig, ax = new_fig(brand, 1.8)
    n = len(events)
    ax.plot([0, n - 1], [0, 0], color=c["border"], linewidth=2, zorder=1)
    for i, e in enumerate(events):
        up = i % 2 == 0
        ax.scatter([i], [0], s=60, color=c["chart_highlight"] if e.get("highlight") else c["ink"], zorder=2)
        ax.text(i, 0.25 if up else -0.25, e["date"], ha="center", va="bottom" if up else "top",
                fontsize=9.5, fontweight="heavy", color=c["ink"])
        ax.text(i, 0.55 if up else -0.55, e["label"], ha="center", va="bottom" if up else "top",
                fontsize=8, color=c["secondary"], wrap=True)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_ylim(-0.9, 0.9)
    ax.axis("off")
    return fig


RENDERERS = {
    "bar": bar,
    "hbar": lambda ch, b: bar(ch, b, horizontal=True),
    "line": line,
    "donut": donut,
    "timeline": timeline,
}


def main(issue_dir):
    issue_dir = Path(issue_dir)
    content = json.loads((issue_dir / "content.json").read_text())
    brand = load_brand()
    out = issue_dir / "img"
    out.mkdir(parents=True, exist_ok=True)
    for chart in content.get("charts", []):
        kind = chart["type"]
        if kind not in RENDERERS:
            sys.exit(f"Unknown chart type '{kind}' for chart '{chart['id']}'. Use one of {list(RENDERERS)}")
        fig = RENDERERS[kind](chart, brand)
        add_title(fig, chart, brand)
        if kind != "donut":  # donut sets its own margins to leave room for the legend
            fig.tight_layout(rect=(0.01, 0.01, 0.99, 0.9))
        path = out / f"chart_{chart['id']}.png"
        # no bbox cropping: every chart keeps the same width so they line up in the email
        fig.savefig(path, facecolor=fig.get_facecolor())
        plt.close(fig)
        print(f"wrote {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
