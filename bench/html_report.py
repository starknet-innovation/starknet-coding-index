"""Generate the visual HTML report from benchmark runs (visual-QA gated).

  uv run python -m bench.html_report [runs.jsonl ...]

Writes results/report.html: a self-contained page (inline CSS + SVG charts,
no external assets; the only JS is a small inline sorter for the models
table). Brand assets in results/brand/ (Starknet Foundation logo, Inter
subset) are inlined at build time so the published artifact stays offline.
Publishing to an Artifact is a separate, manual step — this module never
publishes anything.
"""

import base64
import json
import re
import sys
from pathlib import Path

from . import config
from .report import load_runs
from .sci import SCI_SPEC, attempt_score, attempts, index_ci, leaderboard

# Starknet Foundation design tokens, read off starknet.org's stylesheet
# (snf-st.shared.css exposes them as --base-color-* custom properties).
SNF_BLUE = "#2e64d7"       # brand blue-70: primary accent, open-weight series
SNF_BLUE_LINK = "#3f8cff"  # blue-60
SNF_BLUE_DEEP = "#1c1c84"  # blue-90: tag text
SNF_LAVENDER = "#8f8ebb"   # neutral lavender-50: closed-weight series
SNF_CORAL = "#ec796b"      # warm stop of the SNF logo gradient, also in the
                           # site's own gradient set: deeper than orange-50, so
                           # fill and label can share it and still read on white
SNF_ORANGE_INK = "#a8524c" # orange-80: MCP gain text (contrast on white)
SNF_ORANGE_TINT = "#fddecf"
SNF_PINK_INK = "#573166"   # pink-100
SNF_PINK_TINT = "#fdd2fc"

SLATE = "#7c7ba2"          # lavender-60: baseline series in the effort curves
CORAL = SNF_CORAL          # "added by MCP": fills AND their labels
INK = "#080435"            # blue-110
MUTED = "#696989"          # lavender-70
LINE = "#e6e3f3"           # lavender-10
GROUND = "#f3f1f8"         # lavender-02: the site's page background
GOOD = "#2E9E6B"           # semantic (up-rank arrows), deliberately non-brand

BRAND_DIR = config.REPO_ROOT / "results" / "brand"


def inter_font_face():
    """@font-face for the Inter latin subset, inlined as a data URI."""
    woff2 = (BRAND_DIR / "inter-latin.woff2").read_bytes()
    b64 = base64.b64encode(woff2).decode()
    return (
        "@font-face{font-family:'Inter';font-style:normal;font-weight:400 700;"
        "font-display:swap;"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
    )


def snf_logo(width=190):
    """Starknet Foundation logo, inlined. Class names and gradient ids in the
    source file are generic (cls-1, linear-gradient), so they get namespaced to
    keep them from leaking into the report's own SVGs."""
    svg = (BRAND_DIR / "snf-logo.svg").read_text()
    svg = svg[svg.index("<svg"):]
    for old, new in [("cls-", "snfl-"), ("linear-gradient", "snf-lg"),
                     ("Layer_2", "snf-layer-2"), ("Layer_1-2", "snf-layer-1")]:
        svg = svg.replace(old, new)
    height = round(width * 158 / 679.58)
    return svg.replace(
        "<svg",
        f'<svg width="{width}" height="{height}" role="img" '
        f'aria-label="Starknet Foundation" class="snflogo"', 1
    )



def solve_pct(rs):
    return 100 * sum(r["solved"] for r in rs) / len(rs)


# ---------------------------------------------------------------- SVG helpers

def svg_open(w, h):
    return (
        f'<svg viewBox="0 0 {w} {h}" role="img" '
        f'style="width:100%;height:auto;font-family:var(--mono)">'
    )



def line_chart(x_labels, series, annotations, w=760, h=300, y_min=60, y_max=101):
    """series: [(name, color, [values]), ...]; annotations: [(xi, y, text)]"""
    pad_l, pad_r, pad_t, pad_b = 46, 24, 16, 56
    cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(x_labels)
    sx = lambda i: pad_l + i * cw / (n - 1)
    sy = lambda v: pad_t + (y_max - v) / (y_max - y_min) * ch
    parts = [svg_open(w, h)]
    # 10%-gridlines get stripey when the panel spans most of 0–100
    step = 20 if y_max - y_min > 60 else 10
    for gv in range(y_min + (step - y_min % step) % step, int(y_max) + 1, step):
        y = sy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - pad_r}" y2="{y:.0f}" stroke="{LINE}"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y:.0f}" font-size="11" fill="{MUTED}" text-anchor="end" dominant-baseline="middle">{gv}%</text>')
    for i, lab in enumerate(x_labels):
        parts.append(f'<text x="{sx(i):.0f}" y="{h - 36}" font-size="12" fill="{INK}" text-anchor="middle">{lab}</text>')
    for si, (name, color, vals) in enumerate(series):
        pts = " ".join(f"{sx(i):.0f},{sy(v):.1f}" for i, v in enumerate(vals))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for i, v in enumerate(vals):
            parts.append(f'<circle cx="{sx(i):.0f}" cy="{sy(v):.1f}" r="4.5" fill="{color}"/>')
            # labels go outside the band the two lines span at this x, so
            # near-equal points can't collide: higher value above, lower below
            # (ties: later series wins the top slot)
            others = [s[2][i] for sj, s in enumerate(series) if sj != si]
            on_top = all(v > o for o in others) or (any(v == o for o in others) and si > 0)
            dy = -10 if on_top else 16
            # labels take their series colour: line, dots and numbers read as one
            parts.append(
                f'<text x="{sx(i):.0f}" y="{sy(v) + dy:.1f}" font-size="11" fill="{color}" '
                f'text-anchor="middle" font-weight="600">{v:.0f}</text>'
            )
    for xi, y, text in annotations:
        parts.append(
            f'<text x="{sx(xi) + 12:.0f}" y="{sy(y):.0f}" font-size="11.5" fill="{MUTED}" font-style="italic">{text}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)



SCI_OPEN_COLOR = SNF_BLUE      # open-weight models (brand blue-70)
SCI_CLOSED_COLOR = SNF_LAVENDER  # closed-weight models (neutral lavender-50)


def rotated_label_pad(labels, font_px=11, gap=12, extra=0):
    """Bottom padding a block of -45 degree column labels needs, from the
    longest one.

    Every hardcoded pad_b in this file has been wrong at least once. A label
    that descends to the left puts the START of its text at the lowest point,
    so what a too-small pad_b cuts off is the first characters: at pad_b=115
    "Gemini 3.6 Flash (xhigh)" rendered as "emini 3.6 Flash (xhigh)" in three
    charts at once. Deriving the pad from the label set ends that.

    extra: pixels of non-text furniture on the label line (the rank-delta
    arrow and number in the MCP chart).
    """
    widest = max((len(s) for s in labels), default=0) * font_px * 0.60 + extra
    return int(gap + widest * 0.7071 + 10)


def variant_suffixed(rows):
    """The label strings the rotated axis actually draws, for pad measurement."""
    return [f'{r["label"]} ({r["variant"]})' if r.get("variant") else r["label"]
            for r in rows]


def sci_bar_chart(rows, w=760, h=389):
    """Ranked vertical column chart of SCI rows (from bench.sci.leaderboard).

    One solid column per model, colored by open- vs closed-weight; SCI value
    above each column. Labels are one angled line per column — "Model (effort)"
    — so the roster can grow without neighbors colliding; the lab is omitted
    (it lives in the leaderboard prose). Reusable: pass any number of rows.
    """
    # pad_l sized for the leftmost column's angled label, not just the y-axis
    # ticks — rendered label widths run ~15% over naive char-count estimates
    # (mono parenthetical + sans fallback), which clipped "Opus" at pad_l=48.
    # pad_r balances the ~36px of whitespace left of the tick labels so the
    # bar block reads centered.
    pad_l, pad_r, pad_t = 64, 40, 26
    pad_b = rotated_label_pad(variant_suffixed(rows))
    cw = w - pad_l - pad_r
    ch = h - pad_t - 115          # plot height stays put as the pad grows
    h = pad_t + ch + pad_b
    n = len(rows)
    col_w = cw / n
    bar_w = col_w * 0.62
    sy = lambda v: pad_t + (100 - v) / 100 * ch
    parts = [svg_open(w, h)]
    for gv in range(0, 101, 20):
        y = sy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - pad_r}" y2="{y:.0f}" stroke="{LINE}"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y:.0f}" font-size="11" fill="{MUTED}" text-anchor="end" dominant-baseline="middle">{gv}</text>')
    for i, r in enumerate(rows):
        cx = pad_l + col_w * i + col_w / 2
        x = cx - bar_w / 2
        top = sy(r["sci"])
        color = SCI_OPEN_COLOR if r["open_weight"] else SCI_CLOSED_COLOR
        tip = r.get("tip", {})
        tip_attrs = (
            f' class="scibar" data-oneshot="{tip["oneshot"]:.0f}%"'
            f' data-cost="${tip["cost"]:.2f}" data-time="{tip["time"]}"'
        ) if tip else ""
        parts.append(f'<rect{tip_attrs} x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" height="{sy(0) - top:.1f}" rx="3" fill="{color}"/>')
        parts.append(f'<text x="{cx:.0f}" y="{top - 8:.0f}" font-size="11.5" font-weight="600" fill="{INK}" text-anchor="middle">{r["sci"]:.1f}</text>')
        ly = sy(0) + 12
        variant = (
            f' <tspan fill="{MUTED}" font-family="var(--mono)">({r["variant"]})</tspan>'
            if r.get("variant") else ""
        )
        parts.append(
            f'<text transform="rotate(-45 {cx:.0f} {ly:.0f})" x="{cx:.0f}" y="{ly:.0f}" '
            f'font-size="11" fill="{INK}" text-anchor="end">{r["label"]}{variant}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def mcp_lift_chart(pairs, w=760, h=359, pad_l=64, pad_b=85):
    """Baseline-vs-MCP columns: solid bar = best baseline SCI, stacked coral
    segment = the gain when the best MCP config scores higher. No segment
    means the tool doesn't improve that model's best configuration (no
    downward marks by design). Each condition uses its own best thinking
    variant, so labels carry the model name only.

    pairs: (label, sci_base, sci_mcp_or_None, open_weight, rank_delta) where
    rank_delta is places moved vs the baseline-only ranking (+ = up).
    """
    # pad_r balances the whitespace left of the tick labels (see sci_bar_chart);
    # pad_b is smaller than chart 1's — these labels carry no effort suffix, so
    # their rotated extent is shorter and 130 left a blank band above the legend.
    # pad_l/pad_b are params: the small-models chart carries longer names than
    # chart 2 (its rotated labels clipped at pad_b 85 and its first column at
    # pad_l 64), so it passes larger pads and a taller h to keep bar height
    pad_r, pad_t = 40, 26
    pad_b_arg, pad_b = pad_b, rotated_label_pad(
        [p[0] for p in pairs], extra=26 if any(p[4] > 0 for p in pairs) else 0)
    cw, ch = w - pad_l - pad_r, h - pad_t - pad_b_arg
    h = pad_t + ch + pad_b
    n = len(pairs)
    col_w = cw / n
    # cap so a sparse chart (the small-models section) doesn't render slabs;
    # never binds at the main chart's column count
    bar_w = min(col_w * 0.62, 80)
    sy = lambda v: pad_t + (100 - v) / 100 * ch
    parts = [svg_open(w, h)]
    for gv in range(0, 101, 20):
        y = sy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - pad_r}" y2="{y:.0f}" stroke="{LINE}"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y:.0f}" font-size="11" fill="{MUTED}" text-anchor="end" dominant-baseline="middle">{gv}</text>')
    def top_rounded(x, y1, y2, bw, fill, r=3):
        """Rect with only its top corners rounded — for the topmost piece of a
        stack, so segment bottoms sit flush on the piece below."""
        return (f'<path d="M{x:.1f},{y2:.1f} L{x:.1f},{y1 + r:.1f} Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f} '
                f'L{x + bw - r:.1f},{y1:.1f} Q{x + bw:.1f},{y1:.1f} {x + bw:.1f},{y1 + r:.1f} '
                f'L{x + bw:.1f},{y2:.1f} Z" fill="{fill}"/>')

    for i, (label, base, mcp, open_w, rank_delta) in enumerate(pairs):
        cx = pad_l + col_w * i + col_w / 2
        x = cx - bar_w / 2
        color = SCI_OPEN_COLOR if open_w else SCI_CLOSED_COLOR
        top_b = sy(base)
        gain = mcp is not None and mcp > base
        if gain:
            # sharp-topped base; the coral segment carries the rounded top
            parts.append(f'<rect x="{x:.1f}" y="{top_b:.1f}" width="{bar_w:.1f}" height="{sy(0) - top_b:.1f}" fill="{color}"/>')
        else:
            parts.append(top_rounded(x, top_b, sy(0), bar_w, color))
        if gain:
            top_m = sy(mcp)
            parts.append(top_rounded(x, top_m, top_b, bar_w, CORAL))
            # absolute with-tool score (comparable across all bars) + the gain
            parts.append(f'<text x="{cx:.0f}" y="{top_m - 20:.0f}" font-size="11.5" font-weight="600" fill="{INK}" text-anchor="middle">{mcp:.1f}</text>')
            # gain label takes the segment's own colour: bar and number are one thing
            parts.append(f'<text x="{cx:.0f}" y="{top_m - 8:.0f}" font-size="10.5" font-weight="600" fill="{CORAL}" text-anchor="middle">+{mcp - base:.1f}</text>')
        elif mcp is not None:
            # measured, no gain: bar stays at the (better) baseline; the red
            # sub-line quantifies what the tool would cost this model
            if mcp < base:
                parts.append(f'<text x="{cx:.0f}" y="{top_b - 20:.0f}" font-size="11.5" font-weight="600" fill="{INK}" text-anchor="middle">{base:.1f}</text>')
                parts.append(f'<text x="{cx:.0f}" y="{top_b - 8:.0f}" font-size="10.5" fill="{MUTED}" text-anchor="middle">-{base - mcp:.1f}</text>')
            else:
                parts.append(f'<text x="{cx:.0f}" y="{top_b - 8:.0f}" font-size="11.5" font-weight="600" fill="{INK}" text-anchor="middle">{base:.1f}</text>')
        else:
            # not yet measured with the tool: shown for scale, flagged as such
            parts.append(f'<text x="{cx:.0f}" y="{top_b - 20:.0f}" font-size="11.5" font-weight="600" fill="{INK}" text-anchor="middle">{base:.1f}</text>')
            parts.append(f'<text x="{cx:.0f}" y="{top_b - 8:.0f}" font-size="9" fill="{MUTED}" text-anchor="middle">no MCP</text>')
        ly = sy(0) + 12
        # Only upward moves are annotated (downward is mostly being overtaken).
        # The arrow is DRAWN, not typed. The garbling that prompted this was an
        # encoding bug (see assert_output_is_portable), but geometry is still the
        # better answer: it cannot depend on the reader's mono font coverage.
        if rank_delta > 0:
            tri_x, num_x = cx - 15, cx
            parts.append(
                f'<g transform="rotate(-45 {cx:.0f} {ly:.0f})">'
                f'<text x="{cx - 24:.0f}" y="{ly:.0f}" font-size="11" fill="{INK}" '
                f'text-anchor="end">{label}</text>'
                f'<polygon points="{tri_x:.1f},{ly - 8.5:.1f} {tri_x - 3.5:.1f},{ly - 2:.1f} '
                f'{tri_x + 3.5:.1f},{ly - 2:.1f}" fill="{GOOD}"/>'
                f'<text x="{num_x:.0f}" y="{ly:.0f}" font-size="11" font-weight="600" '
                f'fill="{GOOD}" text-anchor="end">{rank_delta}</text>'
                f"</g>"
            )
        else:
            parts.append(
                f'<text transform="rotate(-45 {cx:.0f} {ly:.0f})" x="{cx:.0f}" y="{ly:.0f}" '
                f'font-size="11" fill="{INK}" text-anchor="end">{label}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)



def head_to_head_chart(metrics, w=760):
    """Paired horizontal bars, one group per metric: closed champion (grey)
    over open champion (blue). Bars are scaled per row to the larger of the
    pair — the point is the ratio within a metric, not across metrics.

    metrics: [(label, val_closed, val_open, fmt)] with fmt a callable.
    """
    pad_l, pad_r, pad_t = 170, 76, 10
    bar_h, pair_gap, group_gap = 13, 4, 22
    group_h = bar_h * 2 + pair_gap
    h = pad_t * 2 + len(metrics) * group_h + (len(metrics) - 1) * group_gap
    bw_max = w - pad_l - pad_r
    parts = [svg_open(w, h)]
    for gi, (label, va, vb, fmt) in enumerate(metrics):
        gy = pad_t + gi * (group_h + group_gap)
        parts.append(
            f'<text x="{pad_l - 12}" y="{gy + group_h / 2:.0f}" font-size="11.5" fill="{INK}" '
            f'text-anchor="end" dominant-baseline="middle">{label}</text>'
        )
        top = max(va, vb) or 1
        for row, (v, color) in enumerate([(va, SCI_CLOSED_COLOR), (vb, SCI_OPEN_COLOR)]):
            y = gy + row * (bar_h + pair_gap)
            bw = max(2, v / top * bw_max)
            parts.append(f'<rect x="{pad_l}" y="{y}" width="{bw:.1f}" height="{bar_h}" rx="2" fill="{color}"/>')
            parts.append(
                f'<text x="{pad_l + bw + 7:.0f}" y="{y + bar_h / 2:.0f}" font-size="11" fill="{INK}" '
                f'font-family="var(--mono)" dominant-baseline="middle">{fmt(v)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)




ATTEMPT_COLORS = [SNF_BLUE, "#7c7ba2", "#bab7df", "#cecde7"]  # 1, 2, 3, 4+ submissions
UNSOLVED_COLOR = "#bdb5ad"  # never solved: the band that tops every column
# Warm neutral on purpose. It has to be legible in a band 2% tall (DeepSeek
# fails 1 run in 52), which ruled out the diagonal hatch tried first: at that
# height it was invisible. It also has to stay off the lavender ramp, so it
# cannot be misread as a fifth submission bucket, and off coral, which means
# "added by the MCP" in the charts below.


def attempts_dist_chart(rows, w=760, h=389, pad_l=110):
    """Stacked column per model, covering 100% of that model's runs.

    Segments are how many submissions the working code took; the grey band on
    top is runs that never worked at all, so solve rate reads as everything
    below the grey. A column that is mostly dark blue is a model that just
    works.
    """
    pad_r, pad_t = 40, 26
    pad_b = rotated_label_pad(variant_suffixed(rows))
    cw, ch = w - pad_l - pad_r, h - pad_t - 115
    h = pad_t + ch + pad_b
    col_w = cw / len(rows)
    bar_w = min(col_w * 0.62, 80)
    sy = lambda v: pad_t + (100 - v) / 100 * ch
    fills = ATTEMPT_COLORS + [UNSOLVED_COLOR]
    parts = [svg_open(w, h)]
    for gv in range(0, 101, 25):
        y = sy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - pad_r}" y2="{y:.0f}" stroke="{LINE}"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y:.0f}" font-size="11" fill="{MUTED}" text-anchor="end" dominant-baseline="middle">{gv}%</text>')
    for i, r in enumerate(rows):
        cx = pad_l + col_w * i + col_w / 2
        x = cx - bar_w / 2
        base = 0.0  # stack upward from the axis
        for k, share in enumerate(r["dist"]):
            if share <= 0:
                continue
            y0, y1 = sy(base), sy(base + share)
            parts.append(f'<rect x="{x:.1f}" y="{y1:.1f}" width="{bar_w:.1f}" '
                         f'height="{y0 - y1:.1f}" fill="{fills[k]}"/>')
            base += share
        # The number is the FIRST-submission share, so it is drawn inside that
        # segment wherever the segment can hold it. Floating every label at the
        # column top made it read as the column's own height: Terra showed "0%"
        # above a bar standing at 97%.
        first, solved_share = r["dist"][0], sum(r["dist"][:4])
        if first >= 14:                     # centered in its own segment
            ly_pct, fill = (sy(first) + sy(0)) / 2 + 4, "#FFFFFF"
        elif solved_share >= 14:            # too thin to fill: sits on the axis,
            ly_pct, fill = sy(0) - 7, "#FFFFFF"     # over a solid segment
        else:                               # barely solves: the axis sits in the
            ly_pct, fill = sy(0) - 7, SNF_BLUE      # grey band, so ink not white
        parts.append(f'<text x="{cx:.0f}" y="{ly_pct:.0f}" font-size="10.5" font-weight="600" '
                     f'fill="{fill}" text-anchor="middle">{first:.0f}%</text>')
        ly = sy(0) + 12
        variant = (f' <tspan fill="{MUTED}" font-family="var(--mono)">({r["variant"]})</tspan>'
                   if r.get("variant") else "")
        parts.append(
            f'<text transform="rotate(-45 {cx:.0f} {ly:.0f})" x="{cx:.0f}" y="{ly:.0f}" '
            f'font-size="11" fill="{INK}" text-anchor="end">{r["label"]}{variant}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def metric_bar_chart(rows, value_fn, fmt_fn, y_max, y_ticks, w=760, h=340,
                     pad_l=64):
    """Chart-1-styled column chart for an arbitrary per-model metric: same
    geometry, angled "Model (variant)" labels, value above each column,
    open/closed palette. y runs 0..y_max with (value, label) ticks supplied
    by the caller. Rows are rendered in the order given. pad_l must cover the
    FIRST column's rotated label (it can be the longest name here, unlike
    chart 1 where rank order puts a short one first). Value labels must stay
    narrow (<= ~5 chars) or neighbors collide at 16 columns.
    """
    pad_r, pad_t = 40, 26
    pad_b = rotated_label_pad(variant_suffixed(rows))
    cw, ch = w - pad_l - pad_r, h - pad_t - 115
    h = pad_t + ch + pad_b
    n = len(rows)
    col_w = cw / n
    bar_w = min(col_w * 0.62, 80)
    sy = lambda v: pad_t + (y_max - v) / y_max * ch
    parts = [svg_open(w, h)]
    for gv, glabel in y_ticks:
        y = sy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - pad_r}" y2="{y:.0f}" stroke="{LINE}"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y:.0f}" font-size="11" fill="{MUTED}" text-anchor="end" dominant-baseline="middle">{glabel}</text>')
    for i, r in enumerate(rows):
        v = value_fn(r)
        cx = pad_l + col_w * i + col_w / 2
        x = cx - bar_w / 2
        top = sy(v)
        color = SCI_OPEN_COLOR if r["open_weight"] else SCI_CLOSED_COLOR
        parts.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" height="{max(1, sy(0) - top):.1f}" rx="3" fill="{color}"/>')
        # fmt_fn may return a tuple of lines (e.g. minutes over seconds),
        # stacked upward from the bar top so neighbors never collide
        label = fmt_fn(v)
        lines = label if isinstance(label, (list, tuple)) else (label,)
        for k, ln in enumerate(lines):
            ly_val = top - 8 - (len(lines) - 1 - k) * 12
            parts.append(f'<text x="{cx:.0f}" y="{ly_val:.0f}" font-size="10.5" font-weight="600" fill="{INK}" text-anchor="middle">{ln}</text>')
        ly = sy(0) + 12
        variant = (
            f' <tspan fill="{MUTED}" font-family="var(--mono)">({r["variant"]})</tspan>'
            if r.get("variant") else ""
        )
        parts.append(
            f'<text transform="rotate(-45 {cx:.0f} {ly:.0f})" x="{cx:.0f}" y="{ly:.0f}" '
            f'font-size="11" fill="{INK}" text-anchor="end">{r["label"]}{variant}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def attempts_chart(groups, w=760, h=210, y_max=None, fmt=None, ticks=None):
    """Grouped columns per task difficulty, one pair (closed grey, open blue)
    per tier.

    Started life as median attempts per tier, which v3 made useless: both
    champions one-shot the median task at every difficulty, so all six columns
    read "1". It now takes any per-tier metric, and the section feeds it the
    first-submission rate, which is what actually separates them.

    groups: [(tier_label, val_closed, val_open)]
    """
    pad_l, pad_r, pad_t, pad_b = 64, 40, 18, 30
    cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
    fmt = fmt or (lambda v: f"{v:g}")
    y_max = y_max or max(3, max(max(a, b) for _, a, b in groups) + 1)
    sy = lambda v: pad_t + (y_max - v) / y_max * ch
    group_w = cw / len(groups)
    bar_w, bar_gap = 46, 10
    parts = [svg_open(w, h)]
    for gv, tick_label in (ticks or [(v, f"{v:g}") for v in range(0, int(y_max) + 1)]):
        y = sy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - pad_r}" y2="{y:.0f}" stroke="{LINE}"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y:.0f}" font-size="11" fill="{MUTED}" text-anchor="end" dominant-baseline="middle">{tick_label}</text>')
    for gi, (label, va, vb) in enumerate(groups):
        cx = pad_l + group_w * gi + group_w / 2
        for k, (v, color) in enumerate([(va, SCI_CLOSED_COLOR), (vb, SCI_OPEN_COLOR)]):
            x = cx - bar_w - bar_gap / 2 + k * (bar_w + bar_gap)
            parts.append(f'<rect x="{x:.1f}" y="{sy(v):.1f}" width="{bar_w}" height="{sy(0) - sy(v):.1f}" rx="3" fill="{color}"/>')
            parts.append(f'<text x="{x + bar_w / 2:.0f}" y="{sy(v) - 7:.0f}" font-size="11.5" font-weight="600" fill="{INK}" text-anchor="middle">{fmt(v)}</text>')
        parts.append(f'<text x="{cx:.0f}" y="{h - 8}" font-size="12" fill="{INK}" text-anchor="middle">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def build(all_runs):
    # Does the effort pattern generalize? Small-multiple curves, one per model
    # with at least two thinking tiers measured in BOTH conditions.
    #
    # Tiers are DERIVED from the data, not listed here. The old hardcoded lists
    # went stale every time a ladder was extended, and a tier with no runs got
    # solve_pct 0, drawing a line to the floor that was indistinguishable from a
    # model that genuinely solved nothing at that effort. Deriving them also
    # means a tier the API rejects (gpt-oss refuses @disabled: "Reasoning is
    # mandatory") simply never appears.
    EFFORT_ORDER = ["disabled", "minimal", "low", "medium", "high", "xhigh", "max"]
    # y_min per family: Qwen's small models live far below everyone else's floor
    FAMILIES = [
        ("GLM 5.2", "z-ai/glm-5.2@", 60),
        ("Tencent Hy3", "tencent/hy3@", 60),
        ("MiniMax M3", "minimax/minimax-m3@", 60),
        ("DeepSeek V4-Pro", "deepseek/deepseek-v4-pro@", 60),
        ("MiMo-V2.5-Pro", "xiaomi/mimo-v2.5-pro@", 60),
        ("Qwen3.6-27B", "qwen/qwen3.6-27b@", 0),
        ("Qwen3.6-35B-A3B", "qwen/qwen3.6-35b-a3b@", 0),
    ]

    def measured_tiers(prefix):
        """Tiers with runs in both conditions, in canonical effort order."""
        have = {
            t for t in EFFORT_ORDER
            if all(any(r["model"] == prefix + t and r["condition"] == c for r in all_runs)
                   for c in ("baseline", "mcp"))
        }
        return [t for t in EFFORT_ORDER if t in have]

    multiples = []
    curve_points = []
    for name, prefix, y_min in FAMILIES:
        tiers = measured_tiers(prefix)
        if len(tiers) < 2:
            continue
        series = []
        for cond, color in [("baseline", SLATE), ("mcp", CORAL)]:
            vals = []
            for t in tiers:
                rs = [r for r in all_runs if r["model"] == prefix + t and r["condition"] == cond]
                vals.append(solve_pct(rs))
                curve_points.append(len(rs))
            series.append(("with MCP" if cond == "mcp" else "baseline", color, vals))
        labels = ["off" if t == "disabled" else t for t in tiers]
        chart = line_chart(labels, series, annotations=[], w=380, h=230, y_min=y_min)
        multiples.append(f'<div><h3 style="font-size:13px;margin-bottom:6px">{name}</h3>{chart}</div>')
    generalize_html = f"""
<section>
  <h2>Does the effort pattern generalize?</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline</span><span><span class="key" style="background:var(--mcp)"></span>with MCP</span><span>solve rate, {min(curve_points)}–{max(curve_points)} runs per point</span></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">{"".join(multiples)}
    <div><h3 style="font-size:13px;margin-bottom:6px">Qwen3 Coder Next</h3>
    <p class="takeaway" style="font-size:12.5px;color:var(--muted);margin:0">No curve, because there is no dial. OpenRouter exposes no reasoning parameters for this model at all, so there is nothing to sweep: it thinks the way it thinks. It sits in the small-models chart above on its single configuration.</p></div>
  </div>
</section>"""


    # Starknet Coding Index leaderboard (baseline; reusable via MODEL_REGISTRY)
    sci_rows = leaderboard(all_runs)

    # Chart-1 tooltips: the median complete benchmark pass (one rep = all 13
    # tasks) of the winning variant, baseline condition. Adaptive tiebreaker
    # reps rerun only the disagreeing task, so partial passes are excluded.
    n_tasks = len({r["task"] for r in all_runs if r["task"] != "fake"})
    med_of = lambda v: (lambda s: s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2)(sorted(v))
    for r in sci_rows:
        by_rep = {}
        for x in all_runs:
            if x["model"] == r["spec"] and x["condition"] == "baseline":
                by_rep.setdefault(x["rep"], []).append(x)
        passes = [rs for rs in by_rep.values() if len(rs) == n_tasks]
        if not passes:
            continue
        secs = med_of([sum(x["llm_time_s"] + (x.get("assist_time_s") or 0) for x in rs) for rs in passes])
        # Share of ALL runs solved in 1 / 2 / 3 / 4+ submissions, then the share
        # never solved: five buckets that partition the runs and sum to 100.
        # Over-budget runs land in the last one, since load_runs clears their
        # solved flag exactly as the index does.
        all_rs = [x for x in all_runs if x["model"] == r["spec"] and x["condition"] == "baseline"]
        solved = [x for x in all_rs if x["solved"]]
        r["dist"] = [
            100 * sum(1 for x in solved if attempts(x) == k) / len(all_rs) for k in (1, 2, 3)
        ] + [100 * sum(1 for x in solved if attempts(x) >= 4) / len(all_rs),
             100 * (len(all_rs) - len(solved)) / len(all_rs)]
        r["tip"] = {
            "passes": len(passes),
            "oneshot": med_of([100 * sum(1 for x in rs if x["solved"] and attempts(x) == 1) / n_tasks for rs in passes]),
            "cost": med_of([sum(x["cost_usd"] or 0 for x in rs) for rs in passes]),
            "secs": secs,
            "time": f"{int(secs // 60)}m {int(secs % 60):02d}s",
        }
    a = SCI_SPEC["anchors"]
    w_ = SCI_SPEC["weights"]

    # Small models (registry small: True) get their own section; the main
    # charts show the regular-size field; deprecated models are already gone
    # from sci_rows entirely (see sci.active_models)
    big_rows = [r for r in sci_rows if not r.get("small")]
    small_rows = [r for r in sci_rows if r.get("small")]

    # weights_pending models (K3) get a display-time star on their label;
    # raw labels stay untouched because they key the mcp_rows lookups
    starred = lambda rows: [
        dict(r, label=r["label"] + "*") if r.get("weights_pending") else r for r in rows
    ]
    pending_note = (
        '<span>* open classification based on an announced weights release '
        '(Kimi K3: promised 2026-07-27, not yet published)</span>'
        if any(r.get("weights_pending") for r in big_rows) else ""
    )

    # Chart 2: best-without vs best-with the MCP, per model. Each condition
    # picks its own best thinking variant (deployment framing), so labels
    # carry no effort. Models without MCP runs are omitted, not shown empty.
    mcp_rows = {r["label"]: r for r in leaderboard(all_runs, condition="mcp")}

    def build_lift_pairs(rows):
        """(label, base, mcp, open_weight, rank_delta) per row, ordered by the
        top of the stack so the with-MCP ranking reads left to right; the
        delta is places moved vs the subset's baseline-only ranking."""
        pairs = [
            (r["label"], r["sci"], mcp_rows[r["label"]]["sci"] if r["label"] in mcp_rows else None,
             r["open_weight"], r.get("weights_pending", False))
            for r in rows
        ]
        rank = {r["label"]: i for i, r in enumerate(rows)}
        pairs.sort(key=lambda p: max(p[1], p[2] or p[1]), reverse=True)
        return [
            (label + ("*" if pending else ""), base, mcp, open_w, rank[label] - i)
            for i, (label, base, mcp, open_w, pending) in enumerate(pairs)
        ]

    key_open = f'<span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>best without MCP (open weights)</span>'
    key_closed = f'<span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>best without MCP (closed weights)</span>'
    key_mcp = f'<span><span class="key" style="background:{CORAL};border-radius:2px"></span>added by MCP</span>'
    keys_for = lambda rows: (key_open + (key_closed if any(not r["open_weight"] for r in rows) else "") + key_mcp)
    lift_legend = f'<div class="legend legend-bottom">{keys_for(big_rows)}{pending_note}</div>'
    lift_legend_small = f'<div class="legend legend-bottom">{keys_for(small_rows)}</div>'
    lift_html = f"""
<section>
  <h2>What does the Cairo Coder MCP add? <span style="text-transform:none">(best config without vs with)</span></h2>
  <p class="takeaway" style="margin:0 0 10px">Same index, second question: each model's <b>best configuration without the tool</b> (solid bar) versus its <b>best configuration with it</b>. The best thinking level may differ per condition, so bars carry no effort label.</p>
  {mcp_lift_chart(build_lift_pairs(big_rows))}
  {lift_legend}
</section>"""
    small_html = f"""
<section>
  <h2>Small models</h2>
  <p class="takeaway" style="margin:0 0 10px">Models with a fraction of the field's active compute (3B to 5B active for the MoEs, up to 31B dense) trade differently with the MCP, and two regimes show up. The Qwen family converts documentation into the study's largest gains (+6.3 to +22.0). Gemma 4 31B and gpt-oss-120b sit below a competence floor where lookups rescue nothing. Same chart as above, small models only.</p>
  {mcp_lift_chart(build_lift_pairs(small_rows), h=394, pad_l=110, pad_b=120)}
  {lift_legend_small}
</section>"""
    tip_js = """<div id="tip" hidden></div><script>
(function () {
  var tip = document.getElementById("tip");
  document.querySelectorAll(".scibar").forEach(function (bar) {
    bar.addEventListener("mousemove", function (e) {
      tip.innerHTML = "<b>1-shot:</b> " + bar.dataset.oneshot + "<br><b>cost:</b> " + bar.dataset.cost
        + "<br><b>time:</b> " + bar.dataset.time;
      tip.hidden = false;
      var x = e.clientX + 14, y = e.clientY + 14;
      if (x + tip.offsetWidth > window.innerWidth - 8) x = e.clientX - tip.offsetWidth - 14;
      tip.style.left = x + "px"; tip.style.top = y + "px";
    });
    bar.addEventListener("mouseleave", function () { tip.hidden = true; });
  });
})();
</script>"""
    sci_html = f"""
<section>
  <h2>Starknet Coding Index <span style="text-transform:none">(baseline, no assistance)</span></h2>
  <p class="takeaway" style="margin:0 0 10px">One number per model for "how good is this LLM at writing Starknet smart contracts today", weighted toward the thing you actually get: <b>working code on the first submission</b>. Each model runs the full task suite alone, at its <b>best thinking variant</b> (labeled in parentheses), within a budget of 10 turns and 15 minutes of model time per task.</p>
  {sci_bar_chart(starred(big_rows))}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>open weights</span><span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>closed weights</span>{pending_note}</div>
  {tip_js}
</section>"""
    import math
    h3_style = 'style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:22px 0 4px"'
    cost_max = math.ceil(max(r["tip"]["cost"] for r in big_rows) / 0.5) * 0.5
    time_max_m = math.ceil(max(r["tip"]["secs"] for r in big_rows) / 60 / 20) * 20
    # compact decimal minutes ("2.5m", "72m"): narrow enough that neighbors
    # never collide at 16 columns
    mins = lambda s: (f"{s / 60:.1f}m" if s < 600 else f"{s / 60:.0f}m")
    pass_html = f"""
<section>
  <h2>Behind the score</h2>
  <p class="takeaway" style="margin:0 0 10px">The winning variants unpacked, baseline condition. The first chart is the whole distribution behind the effectiveness score: every column covers 100% of that model's runs, split by whether the code worked on submission one, two, three, or later, and topped by a grey band for the runs that never worked. Solve rate is everything below the grey. Cost and time are the median of a complete pass over the 13-task suite. Each chart ranks best first.</p>
  <h3 {h3_style}>How many submissions it takes</h3>
  {attempts_dist_chart(sorted(starred(big_rows), key=lambda r: -r["dist"][0]))}
  <div class="legend legend-bottom">{"".join(
      f'<span><span class="key" style="background:{ATTEMPT_COLORS[k]};border-radius:2px"></span>{lbl}</span>'
      for k, lbl in enumerate(["1 submission", "2", "3", "4 or more"]))}<span><span class="key" style="background:{UNSOLVED_COLOR};border-radius:2px"></span>never solved</span><span>labels: first-submission share</span></div>
  <h3 {h3_style}>Cost per pass</h3>
  {metric_bar_chart(sorted(starred(big_rows), key=lambda r: r["tip"]["cost"]),
                    lambda r: r["tip"]["cost"], lambda v: f"${v:.2f}",
                    cost_max, [(t * 0.5, f"${t * 0.5:.2f}") for t in range(int(cost_max / 0.5) + 1)], pad_l=110)}
  <h3 {h3_style}>Model time per pass</h3>
  {metric_bar_chart(sorted(starred(big_rows), key=lambda r: r["tip"]["secs"]),
                    lambda r: r["tip"]["secs"], mins,
                    time_max_m * 60, [(t * 20 * 60, f"{t * 20}m") for t in range(int(time_max_m / 20) + 1)],
                    pad_l=110)}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>open weights</span><span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>closed weights</span></div>
</section>"""

    # Fair questions: the priors readers arrive with, answered by one number
    FAQ = [
        ("Why does Opus 5 win?", "100% one-shot",
         "Every task in every rep solved on the first submission, at the field's fastest "
         "median pass. Nothing else in the field is perfect on that measure, which is why a "
         "flagship price tag still leaves it 3.7 points clear."),
        ("Fable 5 or Grok 4.5?", "0.4 points apart",
         "Call it a tie: the gap is smaller than either model's confidence interval. Fable "
         "one-shots more (96% vs 74%), Grok bills 9× less ($0.0095 vs $0.0874 per task), and "
         "under these weights the two cancel almost exactly."),
        ("Kimi K3 over MiMo? MiMo is far cheaper", "87% vs 40% one-shot",
         "This is the index working as intended. MiMo serves a pass 4× faster and 18× cheaper, "
         "and still loses 4.2 points, because it delivers broken code first about three runs in "
         "five. First-submission success carries twice the weight of the bill."),
        ("A model that does best with thinking off?", "4th place",
         "Sonnet 5 scores highest with reasoning disabled: 67% one-shot at 14 seconds a task. "
         "Its thinking variants bill more time and money for no extra solves, and several models "
         "here get less reliable the more budget you grant them."),
        ("Where are the small models?", "+22.0 with docs",
         "The small class (3B to 31B active) lives at the knowledge floor, so baselines collapse. "
         "Documentation nearly triples the two Qwen3.6 entries (27B goes 13.3 to 35.3, solving 15% "
         "of runs without docs and 69% with) and bounces off Gemma 4 and gpt-oss. They compare on "
         "their own footing in the section below."),
        ("Sol mid-pack? It rivals Fable elsewhere", "25% one-shot",
         "Its Cairo knowledge is not the problem (100% of hidden tests pass on delivered code). "
         "Its habit is: a median of two submissions per task, at the highest price per task in "
         "the field. The index prices the whole workflow, not the eventual answer."),
    ]
    faq_cards = "".join(
        f'<div class="faqcard"><div class="q">{q}</div><div class="stat">{stat}</div><p>{a}</p></div>'
        for q, stat, a in FAQ
    )
    faq_html = f"""
<section>
  <h2>Fair questions</h2>
  <div class="faq">{faq_cards}</div>
</section>"""

    # Head to head: the ranking's best closed model vs best open model,
    # picked dynamically so a leaderboard shake-up updates the section
    best_closed = next(r for r in sci_rows if not r["open_weight"])
    best_open = next(r for r in sci_rows if r["open_weight"])

    def h2h_stats(spec):
        rs = [r for r in all_runs if r["model"] == spec and r["condition"] == "baseline"]
        med = lambda v: (lambda s: s[len(s) // 2] if len(s) % 2 else (s[len(s) // 2 - 1] + s[len(s) // 2]) / 2)(sorted(v))
        return {
            "n": len(rs),
            "solve": solve_pct(rs),
            "oneshot": 100 * sum(1 for r in rs if r["solved"] and attempts(r) == 1) / len(rs),
            "time": med([r["llm_time_s"] + (r.get("assist_time_s") or 0) for r in rs]),
            "cost": med([r["cost_usd"] for r in rs if r["cost_usd"] is not None]),
            "tokens": med([r["completion_tokens"] for r in rs if r["completion_tokens"]]),
            # per-difficulty first-submission rate; tasks are tiered by id prefix
            **{f"one_{tier}": 100 * sum(1 for r in rs if r["task"].startswith(tier)
                                        and r["solved"] and attempts(r) == 1)
                              / len([r for r in rs if r["task"].startswith(tier)])
               for tier in ("e", "m", "h")},
        }

    sa, sb = h2h_stats(best_closed["spec"]), h2h_stats(best_open["spec"])
    pct = lambda v: f"{v:.0f}%"
    h2h_metrics = [
        ("solve rate", sa["solve"], sb["solve"], pct),
        ("first-submission rate", sa["oneshot"], sb["oneshot"], pct),
        ("med. model time", sa["time"], sb["time"], lambda v: f"{v:.0f}s"),
        ("med. cost / task", sa["cost"], sb["cost"], lambda v: f"${v:.4f}"),
        ("med. output tokens", sa["tokens"], sb["tokens"], lambda v: f"{v:,.0f}"),
    ]
    h2h_attempts = [
        (name, sa[f"one_{t}"], sb[f"one_{t}"])
        for t, name in (("e", "easy"), ("m", "medium"), ("h", "hard"))
    ]
    h2h_html = f"""
<section>
  <h2>Head to head: best closed vs best open weights</h2>
  <p class="takeaway" style="margin:0 0 14px">The ranking's two champions, <b>{best_closed["label"]} ({best_closed["variant"]})</b> from {best_closed["lab"]} and <b>{best_open["label"]}{"*" if best_open.get("weights_pending") else ""} ({best_open["variant"]})</b> from {best_open["lab"]}, both solve every task; the gap is in <i>how</i>. The second chart is where it opens: they run close on easy and level on medium, then the hard tier separates them. Baseline condition, {sa["n"]} and {sb["n"]} runs.{" * K3's weights are announced but not yet published, as noted in the table below." if best_open.get("weights_pending") else ""}</p>
  {head_to_head_chart(h2h_metrics)}
  <h3 style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:24px 0 4px">First-submission rate by task difficulty</h3>
  {attempts_chart(h2h_attempts, y_max=100, fmt=lambda v: f"{v:.0f}%",
                  ticks=[(t * 25, f"{t * 25}%") for t in range(5)])}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>{best_closed["label"]} ({best_closed["variant"]}), closed</span><span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>{best_open["label"]} ({best_open["variant"]}), open</span><span>top chart: bars scaled per row, and lower is better on every row but the two rates</span></div>
</section>"""

    # score definition applies to both charts above, so it gets its own section
    score_html = f"""
<section>
  <h2>How the score is built</h2>
  <div class="scorecards">
    <div class="faqcard"><div class="q">Effectiveness</div><div class="stat">{w_["effective"]:.0%}</div><p>Does it work without sending you back into the loop? A run scores 100 when the very first submission passes, then {SCI_SPEC["attempt_decay"]:.0%} of that per further attempt: 100 / 40 / 16 / 6 for 1 / 2 / 3 / 4 submissions, and 0 if it never works.</p></div>
    <div class="faqcard"><div class="q">Correctness</div><div class="stat">{w_["correct"]:.0%}</div><p>Average fraction of hidden tests passed per task. Partial credit on what was delivered: 90% passing is still broken, but it is closer than nothing.</p></div>
    <div class="faqcard"><div class="q">Cost</div><div class="stat">{w_["cost"]:.0%}</div><p>Median $ per task, scored on a fixed log scale (${a["cost"][0]} to ${a["cost"][1]}).</p></div>
    <div class="faqcard"><div class="q">Time</div><div class="stat">{w_["speed"]:.0%}</div><p>Median model latency per task, scored on a fixed log scale ({a["speed"][0]}s to {a["speed"][1]}s). Local compile/test time excluded.</p></div>
  </div>
  <p class="takeaway" style="font-size:12.5px;color:var(--muted)">An attempt is a <b>submission</b>, not a turn: thinking, extra turns and documentation lookups never reach you, so they are free, while code that arrives broken is not. Runs over the 15-minute model-time budget count as failures. Models with one fixed mode show that mode (Kimi K3 always runs at <code>max</code>). The scales are fixed, not relative: adding a new model later never changes an existing score.</p>
</section>"""

    # The models: OpenRouter snapshot (pricing, context, disclosed architecture)
    # plus throughput observed in our own runs. Rows follow the SCI ranking.
    # index CI per model, bootstrapped over its runs: published beside the score
    # so a reader can see which orderings are real and which are ties
    ci_by_label = {}
    for r in sci_rows:
        ci = index_ci([x for x in all_runs
                       if x["model"] == r["spec"] and x["condition"] == "baseline"])
        if ci is not None:
            ci_by_label[r["label"]] = ci

    closed = sorted({r["lab"] for r in sci_rows if not r["open_weight"]},
                    key=lambda lab: -max(r["sci"] for r in sci_rows if r["lab"] == lab))
    closed_labs = ", ".join(closed[:-1]) + f" and {closed[-1]}"

    meta = json.loads((config.REPO_ROOT / "results" / "model_meta.json").read_text())
    fmt_price = lambda v: "n/a" if v is None else (f"${v:,.2f}" if v >= 0.01 else f"${v:.4f}")
    fmt_ctx = lambda v: "1M" if v >= 10**6 else f"{v // 1000}k"

    def param_num(s):
        """'1.02T' / '753B' / '~40B' -> absolute count, for the sort key."""
        if not s:
            return None
        return float(s.lstrip("~").rstrip("TB")) * (1e12 if s.endswith("T") else 1e9)

    # numeric cells carry their raw value in data-s so the sorter never has
    # to parse display strings; n/a cells carry none and always sort last
    num_td = lambda v, txt: (f'<td class="r" data-s="{v}">{txt}</td>' if v is not None
                             else '<td class="r">n/a</td>')
    model_rows = []
    for r in sci_rows:
        api_id = r["spec"].partition("@")[0]
        mm = meta["models"][api_id]
        pm = mm["price_per_m"]
        rs = [x for x in all_runs if x["model"] == r["spec"] and x["condition"] == "baseline"
              and x["completion_tokens"] and x["llm_time_s"]]
        tps = sorted(x["completion_tokens"] / x["llm_time_s"] for x in rs)
        tps_med = tps[len(tps) // 2] if tps else None
        wcls = "ow" if r["open_weight"] else "cw"
        wtxt = ("open" if r["open_weight"] else "closed") + ("*" if r.get("weights_pending") else "")
        mcp_sci = mcp_rows[r["label"]]["sci"] if r["label"] in mcp_rows else None
        delta = mcp_sci - r["sci"] if mcp_sci is not None else None
        delta_td = (
            f'<td class="r" data-s="{delta:.1f}"><span style="color:{"var(--mcp)" if delta > 0 else "var(--muted)"};'
            f'font-weight:{600 if delta > 0 else 400}">{"+" if delta > 0 else "−"}{abs(delta):.1f}</span></td>'
            if delta is not None else '<td class="r">n/a</td>'
        )
        model_rows.append(
            f'<tr><td>{r["label"]}</td>'
            + num_td(r["sci"], f'{r["sci"]:.1f}'
                     + (f' <span class="ci">&plusmn;{ci_by_label[r["label"]]:.1f}</span>'
                        if r["label"] in ci_by_label else ''))
            + num_td(mcp_sci, f"{mcp_sci:.1f}" if mcp_sci is not None else "n/a")
            + delta_td
            + f'<td>{r["lab"]}</td>'
            f'<td><span class="wchip {wcls}">{wtxt}</span></td>'
            f'<td>{mm["type"] or "n/a"}</td>'
            + num_td(param_num(mm["params_total"]), mm["params_total"] or "n/a")
            + num_td(param_num(mm["params_active"]), mm["params_active"] or "n/a")
            + num_td(mm["context_length"], fmt_ctx(mm["context_length"]))
            + num_td(pm["input"], fmt_price(pm["input"]))
            + num_td(pm["output"], fmt_price(pm["output"]))
            + num_td(tps_med and round(tps_med, 1), f"{tps_med:.0f}")
            + "</tr>"
        )
    sorter_js = """<script>
(function () {
  var table = document.getElementById("modeltable");
  var headers = table.querySelectorAll("th");
  headers.forEach(function (th, col) {
    th.tabIndex = 0;
    function activate() {
      var dir = th.classList.contains("asc") ? -1 : 1;
      headers.forEach(function (h) { h.classList.remove("asc", "desc"); h.removeAttribute("aria-sort"); });
      th.classList.add(dir === 1 ? "asc" : "desc");
      th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
      var rows = Array.prototype.slice.call(table.querySelectorAll("tr")).slice(1);
      var numeric = th.hasAttribute("data-num");
      rows.sort(function (a, b) {
        var ca = a.cells[col], cb = b.cells[col];
        if (numeric) {
          var va = ca.hasAttribute("data-s") ? parseFloat(ca.getAttribute("data-s")) : null;
          var vb = cb.hasAttribute("data-s") ? parseFloat(cb.getAttribute("data-s")) : null;
          if (va === null && vb === null) return 0;
          if (va === null) return 1;   /* n/a last in both directions */
          if (vb === null) return -1;
          return (va - vb) * dir;
        }
        return ca.textContent.trim().localeCompare(cb.textContent.trim()) * dir;
      });
      rows.forEach(function (row) { table.tBodies[0].appendChild(row); });
    }
    th.addEventListener("click", activate);
    th.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); }
    });
  });
})();
</script>"""
    models_html = f"""
<section>
  <h2>The models</h2>
  <div class="tablewrap"><table id="modeltable">
    <tr><th>Model</th><th class="r desc" data-num aria-sort="descending">SCI</th><th class="r" data-num>SCI (MCP)</th><th class="r" data-num>Δ</th><th>Lab</th><th>Weights</th><th>Type</th><th class="r" data-num>Params</th><th class="r" data-num>Active</th><th class="r" data-num>Context</th><th class="r" data-num>$/M in</th><th class="r" data-num>$/M out</th><th class="r" data-num>Tok/s</th></tr>
    {"".join(model_rows)}
  </table></div>
  {sorter_js}
  <p class="takeaway" style="font-size:12.5px;color:var(--muted)">Both SCI columns score each condition at its own best thinking variant, and the &plusmn; after a baseline index is its 95% interval, bootstrapped over that model's runs: two scores whose intervals overlap are a tie, not an ordering. * Kimi K3 is classed open on the strength of Moonshot's announced weights release (promised 2026-07-27); as of this snapshot the weights are not yet published. Pricing and context as listed on OpenRouter, {meta["snapshot_date"]}, in $ per million tokens (Grok's prices double above 200k prompt tokens; cache pricing omitted for space). Type and parameter counts from lab model cards and HuggingFace repo metadata; n/a means not disclosed (no closed lab discloses them), and ~ marks a third-party consensus figure with no lab statement. Tok/s is observed in this benchmark's best-variant baseline runs: median per-run output tokens over model time, so reasoning and queueing count against it.</p>
</section>"""

    findings_html = """
<section class="findings">
  <h2>Findings</h2>
  <div class="finding"><h3><span class="tag win">law</span>The tool's value tracks the knowledge gap, in any weight class</h3>
  <p>Documentation lift lines up with baseline weakness: +22.0 for Qwen3.6-27B and +15.6 for Qwen3.6-35B-A3B at the knowledge floor, +6.4 for GLM 5.2, +6.3 for Qwen3 Coder Next, +5.2 for MiniMax M3, +2.3 for Hy3, fading to nothing and then to a penalty at the saturated top (Opus 5 &minus;0.1, K3 &minus;0.3, Fable &minus;1.6, MiMo &minus;2.6, Sonnet 5 &minus;5.4).</p>
  <p>Three refinements. The law applies per <i>variant</i>, not per model: Terra gains only at its unsaturated tiers (+4.2 at <code>minimal</code>, +1.9 with thinking off, nothing at <code>max</code>), and documentation raises MiniMax at four of its six tiers (+13.0, +12.3, +7.1, +3.2) while costing it 5.5 points at the one tier its baseline happens to win on, which is why the like-for-like gain above understates the tool. The lift is mostly bought in solves, not in polish: at the floor it converts runs that never worked into working ones (Qwen3.6-27B 15% to 69% solved, Qwen3.6-35B-A3B 11% to 59%, Coder Next 0% to 17%). And the law has a competence floor, because a model has to be able to exploit what it reads: Gemma 4 31B (−1.8) and gpt-oss-120b (−1.7, zero solves with documentation or without) sit below it.</p></div>
  <div class="finding"><h3><span class="tag win">thinking</span>The thinking dial rarely buys correctness, but it can buy first-try delivery</h3>
  <p>Four patterns across the field (the small models are their own case, below): thinkers whose dial never moves correctness (Sonnet 5, Opus 5, Fable 5, and Grok 4.5, where it only nudges the first-submission rate from 69% to 74%), an indifferent one (MiMo, 100% at all seven tiers), an obedient one that spends budget without needing it (Gemini), and real curves where thinking buys solves (GLM, MiniMax, and Inkling, whose curve overshoots: 94% correctness at <code>low</code> down to 88% at <code>high</code>). One thing changed with this index. The best variant is no longer the cheapest tier that holds correctness, because a pricier tier that gets it right on the first submission now beats a cheap tier that iterates, and that moved five models up their own ladders (Gemini, Sol, Terra, GLM to their top tiers, MiniMax down to <code>medium</code>).</p>
  <p>The two small Qwen models invert the question: for them the dial is not neutral, it is harmful. Both score highest with thinking switched <b>off</b> and worst near the top of the ladder (Qwen3.6-27B 13.3 off against 9.3 at <code>xhigh</code>; Qwen3.6-35B-A3B 16.2 against 6.3, a 4% solve rate). Documentation follows the same shape, paying most where thinking is off (27B +22.0 there, +8 at <code>xhigh</code>). At the knowledge floor, thinking budget spent without the knowledge to spend it on makes things worse, and the fix is reference material, not more reasoning.</p></div>
  <div class="finding"><h3><span class="tag cost">habits</span>One-shot ability is architectural; documentation can't buy it</h3>
  <p>GPT-5.6 Sol iterates against the compiler even at flagship scale and price (25% first-submission, a median of two submissions per task), while Opus 5 and Fable 5 deliver on the first try nearly every time (100% and 96%). Documentation barely moves that habit: at the tiers where we ran both conditions, Sol reads Cairo docs and still lands at 19% and 15%. A habit is not a knowledge gap, and it is the habit this index prices.</p>
  <p>Tool use splits the same way. Offered the docs, Anthropic's models never called them once, so the tool is pure schema overhead for them (Opus 5 gave that pattern its cleanest datapoint: zero calls, −0.1 points). Grok 4.5 consults them about once per run it does not obviously need, and no longer pays for the habit: +0.6 points, and a first-submission rate that moves the right way at the same tier, 74% to 88%. Under the previous index that same behaviour scored as a 13-point penalty, because a lookup consumed a turn and turns were what got counted. Nothing about Grok changed; the ruler did. Treat the direction as directional only, though: at the MCP condition's depth these first-submission shifts do not reach significance (Grok p=0.21, Sonnet's 67% to 50% drop p=0.15).</p></div>
  <div class="finding"><h3><span class="tag cost">economics</span>Pro-style serving modes are strictly dominated</h3>
  <p>Both pro serving modes we funded cost 2 to 3× their model's <code>max</code> tier and scored below it (terra-pro 51.2 against terra@max 52.6). Neither ever produced the best configuration of its model, so sol-pro was not funded on that record.</p></div>
  <div class="finding"><h3><span class="tag win">mechanism</span>Why the tool works: baseline failures are training-data lag</h3>
  <p>Failed baseline runs get stuck on <em>current</em> Cairo idioms (most often the storage API: pre-2024 <code>Map.read(key)</code> instead of today's <code>Map.entry(key).read()</code>) and burn the whole 10-turn budget against the compiler. One documentation lookup resolves it. The mechanism was diagnosed on the deepest dataset (~1,300 runs): the tool often <em>lowered</em> median cost there, with lookups rising as the thinking budget fell (~0.5/run at high effort, ~1.8/run with thinking off), and the same signature shows up wherever the tool pays, from Qwen's knowledge floor to Hy3's over-budget grinds.</p></div>
  <div class="finding"><h3><span class="tag warn">caveat</span>Cairo Coder confabulates outside its index</h3>
  <p>Asked about a token standard we invented ("STRK77"), the service returned a complete, confident, fabricated Cairo interface. Within its indexed corpus it's accurate; agents consuming it get no signal when a query falls outside coverage. Worth fixing upstream.</p></div>
</section>"""

    # charset first: without it a browser guesses the encoding (file:// has no
    # Content-Type header to consult) and renders every multi-byte character as
    # mojibake, e.g. "9x cheaper" arriving as "9A- cheaper"
    return anchor_headings(f"""<meta charset="utf-8">
<title>Starknet Coding Index | A Starknet Foundation report</title>
<meta name="description" content="A Starknet Foundation benchmark: which LLM writes Starknet contracts best, and what does documentation access add? {len(all_runs)} agentic runs across {len(sci_rows)} models from {len({r["lab"] for r in sci_rows})} labs, on 13 hidden-test Cairo tasks, with and without the Cairo Coder documentation tool.">
<style>
  {inter_font_face()}
  :root{{
    --ground:{GROUND}; --panel:#FFFFFF; --ink:{INK}; --muted:{MUTED};
    --line:{LINE}; --baseline:{SLATE}; --mcp:{CORAL};
    --accent:{SNF_BLUE}; --link:{SNF_BLUE_LINK}; --good:{GOOD}; --bad:#B03A3A;
    --mono:"SF Mono","Cascadia Code","JetBrains Mono",Consolas,ui-monospace,monospace;
    --sans:"Inter",-apple-system,"Segoe UI",Roboto,sans-serif;
  }}
  *{{box-sizing:border-box}}
  body{{background:var(--ground);color:var(--ink);font-family:var(--sans);margin:0;padding:40px 20px 80px;line-height:1.55}}
  main{{max-width:980px;margin:0 auto;display:flex;flex-direction:column;gap:26px}}
  /* no text-wrap:balance anywhere: it hangs some Chromium builds on these headings */
  h1,h2,h3{{font-family:var(--mono);font-weight:600;margin:0}}
  h1{{font-size:27px;letter-spacing:-.02em}}
  h2{{font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:16px;scroll-margin-top:24px}}
  h2 a.anchor{{color:inherit;text-decoration:none}}
  h2 a.anchor:hover::after,h2 a.anchor:focus-visible::after{{content:" #";color:var(--link)}}
  header p.lede{{font-size:17px;margin:14px 0 0}}
  .chips{{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}}
  .chip{{font-family:var(--mono);font-size:12px;background:var(--panel);border:1px solid var(--line);padding:4px 10px;border-radius:3px;color:var(--muted)}}
  .chip b{{color:var(--ink);font-weight:600}}
  section{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:26px 30px}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0}}
  .card{{padding:2px 24px;border-left:1px solid var(--line)}}
  .card:first-child{{border-left:none;padding-left:0}}
  .card .big{{font-size:38px;font-weight:600;font-family:var(--mono);letter-spacing:-.02em}}
  .card .big small{{font-size:20px;color:var(--muted);font-weight:400}}
  .card .what{{font-size:13px;color:var(--muted);max-width:24ch}}
  .legend{{display:flex;gap:18px;font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:14px;flex-wrap:wrap}}
  .legend-bottom{{justify-content:center;margin:10px 0 0}}
  .key{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}}
  .takeaway{{font-size:14.5px;margin:14px 0 0}}
  .takeaway b{{color:var(--ink)}}
  .tablewrap{{overflow-x:auto}}
  table{{border-collapse:collapse;width:100%;min-width:900px;font-variant-numeric:tabular-nums}}
  th{{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:500;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}}
  #modeltable td:first-child{{white-space:nowrap}}
  #modeltable th{{cursor:pointer;user-select:none;white-space:nowrap}}
  #modeltable th:hover,#modeltable th:focus-visible{{color:var(--ink)}}
  #modeltable th.asc::after{{content:" \\25B2";font-size:9px}}
  #modeltable th.desc::after{{content:" \\25BC";font-size:9px}}
  td{{padding:7px 8px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}}
  th.r,td.r{{text-align:right}}
  .ci{{color:var(--muted);font-size:11px}}
  .wchip{{font-family:var(--mono);font-size:11px;font-weight:600}}
  .wchip.ow{{color:{SCI_OPEN_COLOR}}} .wchip.cw{{color:{SCI_CLOSED_COLOR}}}
  .scibar:hover{{filter:brightness(1.08)}}
  #tip{{position:fixed;z-index:10;background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:8px 11px;font-family:var(--mono);font-size:12px;color:var(--ink);box-shadow:0 4px 14px rgba(28,34,48,.14);pointer-events:none;white-space:nowrap}}
  #tip b{{font-weight:700}}
  .faq{{display:grid;grid-template-columns:1fr 1fr;gap:14px 28px}}
  .scorecards{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px 20px}}
  .scorecards>:first-child{{grid-column:span 2}}
  @media(max-width:760px){{.scorecards{{grid-template-columns:1fr}}}}
  .faqcard .q{{font-family:var(--mono);font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--ink)}}
  .faqcard .stat{{font-family:var(--mono);font-size:26px;font-weight:600;color:var(--accent);letter-spacing:-.02em;margin:4px 0 2px}}
  .faqcard p{{margin:0;font-size:13.5px}}
  @media(max-width:760px){{.faq{{grid-template-columns:1fr}}}}
  .findings{{display:flex;flex-direction:column;gap:18px}}
  .finding h3{{font-size:14px;margin-bottom:4px}}
  .finding p{{margin:0;font-size:14px}}
  .finding p + p{{margin-top:9px}}
  .tag{{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;padding:2px 7px;border-radius:3px;margin-right:8px;vertical-align:1px}}
  .tag.win{{background:{LINE};color:{SNF_BLUE_DEEP}}} .tag.cost{{background:{SNF_ORANGE_TINT};color:{SNF_ORANGE_INK}}} .tag.warn{{background:{SNF_PINK_TINT};color:{SNF_PINK_INK}}}
  code{{font-family:var(--mono);font-size:.92em;background:var(--ground);border:1px solid var(--line);border-radius:3px;padding:1px 5px}}
  .split{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}
  @media(max-width:760px){{.split{{grid-template-columns:1fr}}}}
  ul.meta{{margin:0;padding-left:20px;font-size:13.5px;color:var(--muted)}}
  ul.meta li{{margin-bottom:7px}}
  ul.meta b{{color:var(--ink)}}
  .snflogo{{display:block;margin-bottom:18px}}
  footer{{font-family:var(--mono);font-size:12px;color:var(--muted);text-align:center;padding-top:4px}}
  footer a{{color:var(--link);text-decoration:none}}
</style>
<main>
<header>
  {snf_logo()}
  <h1>The Starknet Coding Index (SCI)</h1>
  <p class="lede">{len(sci_rows)} models ran the same {len({r["task"] for r in all_runs if r["task"] != "fake"})} Starknet smart-contract tasks: the leading open-weight coders, large and small, alongside the current closed models from {closed_labs}. Every model ran at each useful thinking setting, with and without the <b>Cairo Coder</b> documentation tool.</p>
  <p class="lede">Each run is a bare agentic loop. The model gets the task, a fixed <code>Scarb.toml</code>, a stub <code>lib.cairo</code>, and exactly one tool: <b><code>submit</code></b>. Every submission is compiled with <code>scarb build</code> and run against hidden <code>snforge</code> tests. On failure the model sees the raw compiler errors and failing-test output (never the test code itself) and can resubmit, within a budget of 10 turns and 15 minutes of model time.</p>
  <p class="lede">In the MCP condition the model gets one extra tool, <b><code>assist_with_cairo</code></b>, which searches the Cairo and Starknet documentation corpus.</p>
  <div class="chips">
    <span class="chip">models <b>{len(sci_rows)}</b></span>
    <span class="chip">labs <b>{len({r["lab"] for r in sci_rows})}</b></span>
    <span class="chip">runs <b>{len(all_runs)}</b></span>
    <span class="chip">hidden tests <b>106</b></span>
    <span class="chip">total LLM spend <b>${sum(r["cost_usd"] or 0 for r in all_runs):.0f}</b></span>
    <span class="chip">2026-07-22 to 07-25</span>
  </div>
</header>

{score_html}

{sci_html}

{pass_html}

{faq_html}

{h2h_html}

{lift_html}

{small_html}

{generalize_html}

{models_html}

{findings_html}

<section>
  <div class="split">
    <div>
      <h2>Methodology</h2>
      <ul class="meta">
        <li><b>Harness:</b> agentic repair loop, max 10 assistant turns. The model submits <code>src/lib.cairo</code> via a <code>submit</code> tool; the harness runs <code>scarb build</code> + <code>snforge test</code> against hidden tests and returns the output. Conditions are identical except the MCP condition also exposes <code>assist_with_cairo</code>, replicated exactly from <code>@kasarlabs/cairo-coder-mcp</code> v0.2.5.</li>
        <li><b>Tasks:</b> 13 hand-written Starknet contracts (4 easy / 5 medium / 4 hard incl. a SNIP-6 account and a custom component); every reference solution passes 100% of its tests, every stub fails.</li>
        <li><b>Models:</b> all served via OpenRouter, throughput-sorted routing, provider-default temperature; efforts via the unified reasoning parameter (<code>disabled</code> = <code>enabled:false</code>). Costs are OpenRouter-reported.</li>
        <li><b>Solved</b> = every hidden test passes within the budget: 10 turns and 15 minutes of model time (LLM + doc-tool wait; wall time is not used because it depends on harness concurrency). An <b>attempt is a submission</b>, not a turn, so lookups and extra thinking turns are free and only delivered-and-broken code costs.</li>
        <li><b>Reps and precision:</b> each model's best variant was sampled until its index confidence interval reached &plusmn;5 points (bootstrapped over its runs, 1,000 resamples), which took 2 to 10 passes of the suite depending on how noisy the model is. The interval is printed beside every score above, and <b>every model in the table now meets it</b>: the widest is &plusmn;4.9. &plusmn;5 is the floor on purpose. Most adjacent pairs in the ranking sit under 2 points apart, so they are ties that no affordable sample size resolves, and pricing &plusmn;3 for every variant that could plausibly win came to 2,086 further runs for one extra resolved pair. The MCP condition keeps its original 2 to 3 passes, so its deltas are less precise than the headline scores.</li>
      </ul>
    </div>
    <div>
      <h2>Caveats</h2>
      <ul class="meta">
        <li><b>Unequal depth by design:</b> GLM 5.2 carries the deepest dataset (~1,300 runs across five efforts and both conditions, from the original pilot study); it anchors the substitution-law finding and the n=130 statistics. Newer entrants carry 25 to 120 runs per variant, deepest where the index was noisiest. GLM runs predate the streaming and reasoning-round-trip harness fixes, which its own data shows it did not need.</li>
        <li><b>Eight cells abandoned:</b> host-sleep and network stalls made six unrecoverable (five qwen/minimax baseline cells, one MiMo MCP cell), one qwen@high cell was cut when its batch was stopped manually, and one Hy3 run was killed at 22m43s after grinding far past the 900-second model-time budget, with its last delivered submission taken as the result (it scored zero either way, being over budget). All count as failures, consistent with their completed sibling reps. The stopped batch also skipped its tiebreaker pass, leaving 11 qwen high/max cells at 2 disagreeing reps (scored as the 2-rep mean). Time and cost medians exclude abandoned cells.</li>
        <li><b>MCP backend, tested:</b> @high's first 3 reps used the hosted api.cairo-coder.com; everything else used a self-hosted replica (same corpus re-ingested, same embedding/generation models). A direct A/B (39 runs each, identical tasks/effort) found <b>identical effectiveness</b> (38/39 solved on both, same turn counts), so hosted-index staleness did not skew results; only lookup speed differs (~5× faster locally). Data is pooled.</li>
        <li><b>Statistics:</b> GLM's confirmation batches raised its low/medium/high baseline cells to n=130 (others n=39). The apparent "low beats high" ordering at 3 reps did not survive: low ~ medium (p=0.83), high trails non-significantly (p=0.09). Solve-rate claims here carry Wilson 95% CIs of roughly ±5pt at n=130 and ±9pt at n=39.</li>
        <li><b>Hosted sunset:</b> api.cairo-coder.com shuts down 2026-07-31; the replica replaces it for reruns.</li>
      </ul>
    </div>
  </div>
</section>
<footer>A Starknet Foundation report · <a href="https://www.starknet.org">starknet.org</a> · benchmark snapshot 2026-07-25</footer>
</main>
""")


def anchor_headings(html):
    """Give every section title a stable id and make it a copyable link.

    Done as one pass over the assembled document rather than by editing a dozen
    section literals, and the id goes on the h2 (not the section) so the two
    headings nested in the Methodology/Caveats grid work the same way.
    """
    used = {}

    def slug_for(inner):
        text = re.sub(r"<span.*?</span>", "", inner, flags=re.S)  # drop subtitles
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\([^)]*\)\s*$", "", text)      # any leftover parenthetical
        text = text.split(":")[0].strip(" ?.!")        # "Head to head: ..." -> "Head to head"
        base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
        used[base] = used.get(base, 0) + 1
        return base if used[base] == 1 else f"{base}-{used[base]}"

    def sub(m):
        inner = m.group(1)
        sid = slug_for(inner)
        return f'<h2 id="{sid}"><a class="anchor" href="#{sid}">{inner}</a></h2>'

    return re.sub(r"<h2>(.*?)</h2>", sub, html, flags=re.S)


def assert_output_is_portable(html):
    """Two things screenshots in this sandbox cannot check for us.

    1. The encoding declaration. Garbled symbols reported on 2026-07-25
       ("9A- cheaper", a mangled minus and delta in the models table) were
       mojibake, not missing glyphs: the file is valid UTF-8 but declared no
       charset, so browsers guessed a single-byte codepage. Chromium here
       sniffs UTF-8 correctly, which is exactly why the local render looked
       fine while David's browser did not.
    2. ASCII-only chart text. Belt and braces after the same incident: SVG
       chart text renders in whatever mono font the reader has, so symbols are
       drawn as geometry (see the rank arrows) rather than typed.
    """
    if 'charset="utf-8"' not in html[:1024]:
        raise SystemExit(
            'missing <meta charset="utf-8"> in the first 1024 bytes: browsers '
            "would guess the encoding and render multi-byte characters as mojibake"
        )
    offenders = {
        f"U+{ord(ch):04X} {ch!r}"
        for svg in re.findall(r"<svg.*?</svg>", html, re.S)
        for ch in set(svg)
        if ord(ch) > 127
    }
    if offenders:
        raise SystemExit(
            "non-ASCII characters in chart SVG: " + ", ".join(sorted(offenders))
            + "\nDraw the symbol (polygon/path) instead of typing it: chart text "
              "renders in whatever mono font the reader happens to have."
        )


def main():
    paths = [Path(p) for p in sys.argv[1:]] or [config.RUNS_DIR / "main.jsonl"]
    runs = load_runs(paths)
    if not runs:
        print("no runs found")
        sys.exit(1)
    html = build(runs)
    assert_output_is_portable(html)
    out = config.RESULTS_DIR / "report.html"
    out.write_text(html, encoding="utf-8")
    print(f"{len(runs)} runs -> {out}")


if __name__ == "__main__":
    main()
