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
import math
import re
import sys
from pathlib import Path

from . import config
from .report import load_runs
from .sci import (LOCAL_FALLBACK_BITS, LOCAL_QUANT, LOCAL_RESERVE_GB,
                  LOCAL_VRAM_GB, LOCAL_WEIGHT_BUDGET_GB, SCI_SPEC, active_models,
                  attempt_score, attempts, index_ci, leaderboard, param_count,
                  run_cost)

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


# Angled column labels: one angle and one left margin for every chart in the
# report, because per-chart values drift. The three "Behind the score" charts
# ran at pad_l=110 while chart 1 ran at 64, which is 46px of plot width thrown
# away for a reason no reader can see.
#
# Those charts sort by cost and by time rather than by score, so a long name can
# land in column 0 where its label has nowhere to sweep: "MiMo-V2.5-Pro (xhigh)"
# is 139px and reaches W*cos(angle) to the left of cx_0=87. At -45 that is 98px,
# hence the old 110. The floor for a shared 64px margin is 53.1 degrees; 55
# clears it by 7.6px and costs 18px of label depth, where 60 would cost 25px for
# slack nothing needs. Below 64 the y-axis ticks ("$2.50", ~41px) start to bind.
#
# assert_output_is_portable enforces this geometry, so a future name long enough
# to break it fails the build instead of rendering clipped.
LABEL_ANGLE = 55
AXIS_PAD_L = 64
_LABEL_CH = 11 * 0.60      # px per character at font-size 11, measured exact
                           # against getComputedTextLength (scratchpad/measure_labels.py)


def label_width(text, font_px=11):
    """Rendered advance width of a chart label, in px."""
    return len(text) * font_px * 0.60


def rotated_label_pad(labels, font_px=11, gap=12, extra=0):
    """Bottom padding a block of angled column labels needs, from the longest.

    Every hardcoded pad_b in this file has been wrong at least once. A label
    that descends to the left puts the START of its text at the lowest point,
    so what a too-small pad_b cuts off is the first characters: at pad_b=115
    "Gemini 3.6 Flash (xhigh)" rendered as "emini 3.6 Flash (xhigh)" in three
    charts at once. Deriving the pad from the label set ends that.

    extra: pixels of non-text furniture on the label line (the rank-delta
    arrow and number in the MCP chart).
    """
    widest = max((label_width(s, font_px) for s in labels), default=0) + extra
    return int(gap + widest * math.sin(math.radians(LABEL_ANGLE)) + 10)


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
            f'<text transform="rotate(-{LABEL_ANGLE} {cx:.0f} {ly:.0f})" x="{cx:.0f}" y="{ly:.0f}" '
            f'font-size="11" fill="{INK}" text-anchor="end">{r["label"]}{variant}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def effort_suffix(efforts, label):
    """The '(low)' / '(xhigh / low)' parenthetical for one bar, as plain text.

    Each condition picks its own best thinking variant, so a bar can carry two.
    Baseline first, with-MCP second. Half the big models differ, and they almost
    all move DOWN the ladder with documentation, which is the point of showing
    this. ASCII only: assert_output_is_portable rejects non-ASCII inside an
    <svg>, so the separator is a slash, not an arrow.
    """
    pair = (efforts or {}).get(label.rstrip("*"))
    if not pair:
        return ""
    base, mcp = pair
    if not base and not mcp:
        return " (no dial)"   # Coder Next: no reasoning params exist at all, and
    if base == mcp:           # a blank where every sibling has one reads as a bug
        return f" ({base})"
    return f" ({base} / {mcp})"


def mcp_lift_chart(pairs, w=760, h=359, pad_l=AXIS_PAD_L, pad_b=85, efforts=None):
    """Baseline-vs-MCP columns: solid bar = best baseline SCI, stacked coral
    segment = the gain when the best MCP config scores higher. No segment
    means the tool doesn't improve that model's best configuration (no
    downward marks by design).

    Each condition uses its own best thinking variant, so a label carries one
    effort when both conditions agree on it and two when they don't.

    pairs: (label, sci_base, sci_mcp_or_None, open_weight, rank_delta) where
    rank_delta is places moved vs the baseline-only ranking (+ = up).
    efforts: {label: (baseline_variant, mcp_variant)}; None labels bars by name
    only. Passed as its own argument rather than a sixth tuple field so the
    shape of `pairs` (and both call sites) stays put.
    """
    # pad_r balances the whitespace left of the tick labels (see sci_bar_chart).
    # pad_l is a param because the local-inference chart's first column carries a
    # longer name than chart 2's. pad_b is NOT the label clearance: that is always
    # derived below from the strings actually drawn, so the argument only sets how
    # much height is left for the bars. Passing a bigger one shortens the plot; it
    # cannot clip a label.
    pad_r, pad_t = 40, 26
    # measured on the strings actually drawn, suffix included: pad from the bare
    # names would shave the first characters off the longest label
    shown = {p[0]: p[0] + effort_suffix(efforts, p[0]) for p in pairs}
    pad_b_arg, pad_b = pad_b, rotated_label_pad(
        list(shown.values()), extra=26 if any(p[4] > 0 for p in pairs) else 0)
    cw, ch = w - pad_l - pad_r, h - pad_t - pad_b_arg
    h = pad_t + ch + pad_b
    n = len(pairs)
    col_w = cw / n
    # cap so a sparse chart (the local-inference section) doesn't render slabs;
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
        # the effort rides in the axis label, mono and muted, exactly as it does
        # in chart 1 and the "Behind the score" charts
        suffix = effort_suffix(efforts, label)
        eff = (f'<tspan fill="{MUTED}" font-family="var(--mono)">{suffix}</tspan>'
               if suffix else "")
        # Only upward moves are annotated (downward is mostly being overtaken).
        # The arrow is DRAWN, not typed. The garbling that prompted this was an
        # encoding bug (see assert_output_is_portable), but geometry is still the
        # better answer: it cannot depend on the reader's mono font coverage.
        if rank_delta > 0:
            tri_x, num_x = cx - 15, cx
            parts.append(
                f'<g transform="rotate(-{LABEL_ANGLE} {cx:.0f} {ly:.0f})">'
                f'<text x="{cx - 24:.0f}" y="{ly:.0f}" font-size="11" fill="{INK}" '
                f'text-anchor="end">{label}{eff}</text>'
                f'<polygon points="{tri_x:.1f},{ly - 8.5:.1f} {tri_x - 3.5:.1f},{ly - 2:.1f} '
                f'{tri_x + 3.5:.1f},{ly - 2:.1f}" fill="{GOOD}"/>'
                f'<text x="{num_x:.0f}" y="{ly:.0f}" font-size="11" font-weight="600" '
                f'fill="{GOOD}" text-anchor="end">{rank_delta}</text>'
                f"</g>"
            )
        else:
            parts.append(
                f'<text transform="rotate(-{LABEL_ANGLE} {cx:.0f} {ly:.0f})" x="{cx:.0f}" y="{ly:.0f}" '
                f'font-size="11" fill="{INK}" text-anchor="end">{label}{eff}</text>'
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




# Quantizations shown in the open-weight table, smallest first. IQ4_XS is the
# floor of what most people still call 4-bit; BF16 is the unquantized weight.
QUANT_LADDER = ["IQ4_XS", "Q4_K_M", "Q6_K", "Q8_0", "BF16"]

ATTEMPT_COLORS = [SNF_BLUE, "#7c7ba2", "#bab7df", "#cecde7"]  # 1, 2, 3, 4+ submissions
UNSOLVED_COLOR = "#bdb5ad"  # never solved: the band that tops every column
# Warm neutral on purpose. It has to be legible in a band 2% tall (DeepSeek
# fails 1 run in 52), which ruled out the diagonal hatch tried first: at that
# height it was invisible. It also has to stay off the lavender ramp, so it
# cannot be misread as a fifth submission bucket, and off coral, which means
# "added by the MCP" in the charts below.


def attempts_dist_chart(rows, w=760, h=389, pad_l=AXIS_PAD_L):
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
            f'<text transform="rotate(-{LABEL_ANGLE} {cx:.0f} {ly:.0f})" x="{cx:.0f}" y="{ly:.0f}" '
            f'font-size="11" fill="{INK}" text-anchor="end">{r["label"]}{variant}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def metric_bar_chart(rows, value_fn, fmt_fn, y_max, y_ticks, w=760, h=340,
                     pad_l=AXIS_PAD_L):
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
            f'<text transform="rotate(-{LABEL_ANGLE} {cx:.0f} {ly:.0f})" x="{cx:.0f}" y="{ly:.0f}" '
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
            "cost": med_of([sum(run_cost(x) or 0 for x in rs) for rs in passes]),
            "secs": secs,
            "time": f"{int(secs // 60)}m {int(secs % 60):02d}s",
        }
    EFFORT_ORDER = ["disabled", "minimal", "low", "medium", "high", "xhigh", "max"]
    # Five, not two or three. This section plots SOLVE RATE, which only carries a
    # model's story if most of the ladder is measured in both conditions. Sol and
    # Terra qualified at three tiers and were charted for one build; the result was
    # misleading on the page. Sol solves 100% at every tier in both conditions, so
    # its curve was two flat lines, and Terra's coral line DIPPED at max (92% vs
    # 97%) while the findings state +9.1 there, because its gain is entirely in
    # first submissions (0% to 27%), not in solves. A chart that contradicts the
    # prose two sections later is worse than an absence, and the absence is
    # explained in the section note.

    def measured_tiers(prefix):
        """Tiers with runs in both conditions, in canonical effort order."""
        have = {
            t for t in EFFORT_ORDER
            if all(any(r["model"] == prefix + t and r["condition"] == c for r in all_runs)
                   for c in ("baseline", "mcp"))
        }
        return [t for t in EFFORT_ORDER if t in have]

    # Which models appear is DERIVED, like the tiers inside each chart. The old
    # hardcoded list silently dropped models as coverage grew: Sol and Terra both
    # earned a curve tonight, and they are the two carrying the finding that the
    # tool's gain appears at the TOP of the ladder, so leaving them out hid the
    # evidence for the claim the law card makes. Gemini and Grok reach two tiers
    # and stay out on MIN_CURVE_TIERS; Gemini's pair does not even include the
    # tier its own winner uses.
    #
    # y_min keeps each family's shape readable and is derived per family below.
    # ordered by index score, like every other section, so a reader moving down
    # the page meets the models in the same sequence
    rank = {r["label"]: i for i, r in enumerate(sci_rows)}
    families = []
    for entry in sorted(active_models(), key=lambda e: rank.get(e["label"], 99)):
        # the prefix comes from a spec that HAS an effort, not specs[0]: Terra's
        # list starts with its pro serving mode, whose id is a different model
        effort_specs = [sp for sp in entry["specs"] if "@" in sp]
        if not effort_specs:
            continue                      # no dial at all (Coder Next)
        prefix = effort_specs[0].split("@")[0] + "@"
        tiers = measured_tiers(prefix)
        if len(tiers) < 5:
            continue
        # y_min comes from the data, not from the model's class: a floor of 60
        # keeps a saturated model's shape readable, but the models that live
        # below it need the full axis. Deriving it also stops chart geometry
        # depending on a classification that is about memory, not solve rate.
        lo = min(solve_pct([r for r in all_runs if r["model"] == prefix + t
                            and r["condition"] == c])
                 for t in tiers for c in ("baseline", "mcp"))
        families.append((entry["label"], prefix, 0 if lo < 60 else 60, tiers))

    multiples = []
    curve_points = []
    for name, prefix, y_min, tiers in families:
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
        multiples.append(f'<div class="multiple"><h3>{name}</h3>{chart}</div>')
    generalize_html = f"""
<section>
  <h2>Does the effort pattern generalize?</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline</span><span><span class="key" style="background:var(--mcp)"></span>with MCP</span><span>solve rate, {min(curve_points)}–{max(curve_points)} runs per point</span><span>x-axis is the effort we requested; some neighbours are the same setting (see methodology)</span><span>a model appears here when most of its ladder was run in both conditions</span></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">{"".join(multiples)}
    <div class="multiple"><h3>Qwen3 Coder Next</h3>
    <p class="takeaway" style="font-size:12.5px;color:var(--muted);margin:0">No curve, because there is no dial. OpenRouter exposes no reasoning parameters for this model at all, so there is nothing to sweep: it thinks the way it thinks. It sits in the local-inference chart above on its single configuration.</p></div>
  </div>
  <p class="takeaway" style="font-size:12.5px;color:var(--muted);margin:16px 0 0">The two OpenAI models whose documentation gain arrives at full effort, Sol (+7.9) and Terra (+9.1), are deliberately not here: this chart measures solve rate and theirs barely moves. Sol already solves every task at every tier, and Terra's solve rate <i>falls</i> at <code>max</code> even as its score rises, because the tool buys it first-try delivery (0% to 27%) rather than more solves. The findings section carries that result.</p>
</section>"""

    a = SCI_SPEC["anchors"]
    w_ = SCI_SPEC["weights"]

    # Models that fit one 512 GB machine at 4-bit get their own section (the
    # class is derived in sci.fits_locally, never hand-set); the main charts
    # show everything else; deprecated models are already gone from sci_rows
    # entirely (see sci.active_models)
    big_rows = [r for r in sci_rows if not r.get("local")]
    local_rows = [r for r in sci_rows if r.get("local")]

    # A model whose weights are announced but not yet downloadable is classed
    # open with a display-time star on its label; raw labels stay untouched
    # because they key the mcp_rows lookups. No model carries the flag today
    # (K3's weights published 2026-07-27), so this renders nothing until one does.
    starred = lambda rows: [
        dict(r, label=r["label"] + "*") if r.get("weights_pending") else r for r in rows
    ]
    pending_note = (
        '<span>* open classification based on an announced weights release, '
        'not yet published</span>'
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

    # Which thinking variant won, per condition, keyed by raw label. Half the big
    # models pick a different one with the tool than without, so the chart labels
    # carry both and effort_suffix decides how to render the pair.
    lift_efforts = {
        r["label"]: (r["variant"], mcp_rows[r["label"]]["variant"])
        for r in sci_rows if r["label"] in mcp_rows
    }

    key_open = f'<span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>best without MCP (open weights)</span>'
    key_closed = f'<span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>best without MCP (closed weights)</span>'
    key_mcp = f'<span><span class="key" style="background:{CORAL};border-radius:2px"></span>added by MCP</span>'
    # the pair convention is only worth explaining where a pair appears, so a
    # chart whose models all keep one effort says nothing about a second value
    # the reader cannot see
    def keys_for(rows):
        pairs = [lift_efforts.get(r["label"]) for r in rows]
        two = any(p and p[0] != p[1] for p in pairs)
        effort_key = ('<span>effort in parentheses; two values are baseline then '
                      'with-MCP</span>' if two else '<span>effort in parentheses</span>')
        return (key_open + (key_closed if any(not r["open_weight"] for r in rows) else "")
                + key_mcp + effort_key)
    lift_legend = f'<div class="legend legend-bottom">{keys_for(big_rows)}{pending_note}</div>'
    lift_legend_local = f'<div class="legend legend-bottom">{keys_for(local_rows)}</div>'
    lift_html = f"""
<section>
  <h2>What does the Cairo Coder MCP add? <span style="text-transform:none">(best config without vs with)</span></h2>
  <p class="takeaway" style="margin:0 0 10px">Same index, second question: each model's <b>best configuration without the tool</b> (solid bar) versus its <b>best configuration with it</b>. Each condition picks its own best thinking level, and the labels show it: <b>six of the twenty models win at a different effort with the tool than without</b>, counting this chart and the local-inference one below together, and four of those six move <i>down</i> the ladder, not up. Documentation substitutes for thinking budget.</p>
  {mcp_lift_chart(build_lift_pairs(big_rows), efforts=lift_efforts)}
  {lift_legend}
</section>"""
    local_html = f"""
<section>
  <h2>Local-inference class <span style="text-transform:none">(runs on one 512 GB machine)</span></h2>
  <p class="takeaway" style="margin:0 0 10px">Same chart, for the models you could run yourself. The test is memory rather than parameter count: the published <code>Q4_K_M</code> weight file against the {LOCAL_VRAM_GB} GB of unified memory a Mac Studio M3 Ultra holds, which is the largest such machine a person can buy, leaving {LOCAL_RESERVE_GB} GB for the OS and a KV cache. Total parameters count, not active ones, because every weight has to be resident even when a sparse model fires only a few experts per token. Seven models clear it, from Qwen3.6-27B at 17 GB up to <b>MiniMax M3 at 264 GB</b>. <b>GLM 5.2 is the nearest miss</b>, at 466 GB, though it comes within reach at <code>IQ4_XS</code> (365 GB); no closed model qualifies at all, since there are no weights to download. Two regimes show up inside the class: the Qwen family converts documentation into the study's largest gains (+6.3 to +22.0), while Gemma 4 31B and gpt-oss-120b sit below a competence floor where lookups rescue nothing.</p>
  {mcp_lift_chart(build_lift_pairs(local_rows), h=394, pad_b=120, efforts=lift_efforts)}
  {lift_legend_local}
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
    cost_max = math.ceil(max(r["tip"]["cost"] for r in big_rows) / 0.5) * 0.5
    time_max_m = math.ceil(max(r["tip"]["secs"] for r in big_rows) / 60 / 20) * 20
    # compact decimal minutes ("2.5m", "72m"): narrow enough that neighbors
    # never collide at 16 columns
    mins = lambda s: (f"{s / 60:.1f}m" if s < 600 else f"{s / 60:.0f}m")
    pass_html = f"""
<section>
  <h2>Behind the score</h2>
  <p class="takeaway" style="margin:0 0 10px">The winning variants unpacked, baseline condition. The first chart is the whole distribution behind the effectiveness score: every column covers 100% of that model's runs, split by whether the code worked on submission one, two, three, or later, and topped by a grey band for the runs that never worked. Solve rate is everything below the grey. Cost and time are the median of a complete pass over the 13-task suite. Each chart ranks best first.</p>
  <h3 class="chart-title">How many submissions it takes</h3>
  {attempts_dist_chart(sorted(starred(big_rows), key=lambda r: -r["dist"][0]))}
  <div class="legend legend-bottom">{"".join(
      f'<span><span class="key" style="background:{ATTEMPT_COLORS[k]};border-radius:2px"></span>{lbl}</span>'
      for k, lbl in enumerate(["1 submission", "2", "3", "4 or more"]))}<span><span class="key" style="background:{UNSOLVED_COLOR};border-radius:2px"></span>never solved</span><span>labels: first-submission share</span></div>
  <h3 class="chart-title">Cost per pass</h3>
  {metric_bar_chart(sorted(starred(big_rows), key=lambda r: r["tip"]["cost"]),
                    lambda r: r["tip"]["cost"], lambda v: f"${v:.2f}",
                    cost_max, [(t * 0.5, f"${t * 0.5:.2f}") for t in range(int(cost_max / 0.5) + 1)])}
  <h3 class="chart-title">Model time per pass</h3>
  {metric_bar_chart(sorted(starred(big_rows), key=lambda r: r["tip"]["secs"]),
                    lambda r: r["tip"]["secs"], mins,
                    time_max_m * 60, [(t * 20 * 60, f"{t * 20}m") for t in range(int(time_max_m / 20) + 1)])}
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
         "This is the index working as intended. MiMo serves a pass 4.5× faster and 21× cheaper, "
         "and still loses 4.2 points, because it delivers broken code first about three runs in "
         "five. First-submission success carries twice the weight of the bill."),
        ("Sonnet 5 solves everything. Why 4th?", "67% vs 100% one-shot",
         "It one-shots 67% of runs, against Opus 5's 100%, and that gap is most of the 8.6 points "
         "between them. Most of its dial does nothing: minimal through xhigh all land within one "
         "interval of each other on ~1.8k output tokens and 14 seconds. Only <code>max</code> is "
         "different, and it is a cliff, not a step: 88% one-shot, the best of any Sonnet setting, for "
         "61k output tokens at $0.68 a task and nine minutes of thinking."),
        ("Which of these could I run myself?", "7 of 20",
         "Seven fit one 512 GB machine at Q4_K_M, from Qwen3.6-27B at 17 GB of weights to "
         "MiniMax M3 at 264 GB, and they compare on their own footing in the section below. The "
         "rest need a rack or are closed. Documentation pays hardest down there: it nearly triples "
         "Qwen3.6-27B (13.3 to 35.3, solving 15% of runs without docs and 69% with) and doubles "
         "35B-A3B, though it bounces off Gemma 4 and gpt-oss."),
        ("Sol mid-pack? It rivals Fable elsewhere", "40% one-shot",
         "Its Cairo knowledge is not the problem (100% of hidden tests pass on delivered code). Its "
         "habit is: a median of two submissions per task at $0.0895, about nine times Grok's bill for "
         "half of Grok's first-try rate. Give it the documentation tool and the habit changes, to 72% "
         "and a median of one submission, which is the largest such shift in the study."),
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
            "cost": med([c for c in (run_cost(r) for r in rs) if c is not None]),
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
  <p class="takeaway" style="margin:0 0 14px">The ranking's two champions, <b>{best_closed["label"]} ({best_closed["variant"]})</b> from {best_closed["lab"]} and <b>{best_open["label"]}{"*" if best_open.get("weights_pending") else ""} ({best_open["variant"]})</b> from {best_open["lab"]}, both solve every task; the gap is in <i>how</i>. The second chart is where it opens: they run close on easy and level on medium, then the hard tier separates them. Baseline condition, {sa["n"]} and {sb["n"]} runs.{" * Weights announced but not yet published, as noted in the table below." if best_open.get("weights_pending") else ""}</p>
  {head_to_head_chart(h2h_metrics)}
  <h3 class="chart-title">First-submission rate by task difficulty</h3>
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
  <p class="takeaway" style="font-size:12.5px;color:var(--muted)">An attempt is a <b>submission</b>, not a turn: thinking, extra turns and documentation lookups never reach you, so they are free, while code that arrives broken is not. Runs over the 15-minute model-time budget count as failures. Where we sent no effort parameter, the label is the level OpenRouter documents as that model's default: <code>max</code> for Kimi K3, <code>high</code> for Hy3 and Sonnet 5. The scales are fixed, not relative: adding a new model later never changes an existing score.</p>
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
            + num_td(mm["context_length"], fmt_ctx(mm["context_length"]))
            + num_td(pm["input"], fmt_price(pm["input"]))
            + num_td(pm["output"], fmt_price(pm["output"]))
            + num_td(tps_med and round(tps_med, 1), f"{tps_med:.0f}")
            + "</tr>"
        )

    # Open-weight deep dive: architecture and what the published weight files
    # actually weigh. Only Q4_K_M ever falls back to arithmetic, because that is
    # the one figure the local-inference class depends on; every other cell is a
    # real file size or blank, since a ladder of numbers I derived myself would
    # be worth less than the honest gap.
    open_rows = [r for r in sci_rows if r["open_weight"]]
    open_rows_html = []
    for r in open_rows:
        mm = meta["models"][r["spec"].partition("@")[0]]
        gg = mm.get("gguf") or {}
        cells = ""
        for q in QUANT_LADDER:
            gb = gg.get(q)
            est = gb is None and q == LOCAL_QUANT and r["vram_gb"]
            if gb is None and not est:
                cells += '<td class="r"></td>'
                continue
            v = gb or r["vram_gb"]
            over = ' style="color:var(--muted)"' if v > LOCAL_WEIGHT_BUDGET_GB else ""
            cells += f'<td class="r" data-s="{v:.1f}"{over}>{"~" if est else ""}{v:,.0f}</td>'
        open_rows_html.append(
            f'<tr><td>{r["label"]}</td><td>{mm["type"] or "n/a"}</td>'
            + num_td(param_count(mm["params_total"]), mm["params_total"] or "n/a")
            + num_td(param_count(mm["params_active"]), mm["params_active"] or "n/a")
            + num_td(mm["context_length"], fmt_ctx(mm["context_length"]))
            + cells + "</tr>"
        )

    # every sortable table on the page, not one by id: the open-weight table
    # shipped unsortable because the sorter named "modeltable" directly
    sorter_js = """<script>
/* on DOMContentLoaded so it does not matter where on the page this lands */
document.addEventListener("DOMContentLoaded", function () {
document.querySelectorAll("table.sortable").forEach(function (table) {
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
});
});
</script>"""
    models_html = f"""
<section>
  <h2>The models</h2>
  <div class="tablewrap"><table id="modeltable" class="sortable">
    <tr><th>Model</th><th class="r desc" data-num aria-sort="descending">SCI</th><th class="r" data-num>SCI (MCP)</th><th class="r" data-num>Δ</th><th>Lab</th><th>Weights</th><th class="r" data-num>Context</th><th class="r" data-num>$/M in</th><th class="r" data-num>$/M out</th><th class="r" data-num>Tok/s</th></tr>
    {"".join(model_rows)}
  </table></div>
  {sorter_js}
  <p class="takeaway" style="font-size:12.5px;color:var(--muted)">Both SCI columns score each condition at its own best thinking variant, and the &plusmn; after a baseline index is its 95% interval, bootstrapped over that model's runs: two scores whose intervals overlap are a tie, not an ordering. Kimi K3 was API-only while these runs were collected; Moonshot published its weights on 2026-07-27, after the run window. Pricing and context as listed on OpenRouter, {meta["snapshot_date"]}, in $ per million tokens (Grok's prices double above 200k prompt tokens; cache pricing omitted for space). Tok/s is observed in this benchmark's best-variant baseline runs: median per-run output tokens over model time, so reasoning and queueing count against it. Architecture and memory for the open-weight models are in the next section; the closed ones disclose neither.</p>
</section>

<section>
  <h2>Open weights in detail</h2>
  <p class="takeaway" style="margin:0 0 10px">What it takes to run the {len(open_rows)} open models yourself. Sizes are the weight files as published, not arithmetic: a real <code>Q4_K_M</code> runs 4.8 to 5.0 bits per weight rather than the 4.5 a formula assumes, which understates a large model by about 10%, and gpt-oss-120b breaks the formula outright because it ships natively in 4-bit and weighs the same at every level. Cells past <b>{LOCAL_WEIGHT_BUDGET_GB} GB</b> are greyed: that is the weights budget on a {LOCAL_VRAM_GB} GB machine once the OS and a KV cache are paid for, and it is the line the local-inference class above is drawn on.</p>
  <div class="tablewrap"><table id="opentable" class="sortable">
    <tr><th>Model</th><th>Type</th><th class="r" data-num>Params</th><th class="r" data-num>Active</th><th class="r" data-num>Context</th>{"".join(f'<th class="r" data-num>{q}</th>' for q in QUANT_LADDER)}</tr>
    {"".join(open_rows_html)}
  </table></div>
  <p class="takeaway" style="font-size:12.5px;color:var(--muted)">Memory in GB, from the GGUF files published by <a href="https://huggingface.co/unsloth">unsloth</a>; a blank means that quantization was never published for that model, and <b>~</b> marks a size estimated at {LOCAL_FALLBACK_BITS} bits per weight, calibrated on the eight files that were measured. Four models need that estimate: Hy3, DeepSeek V4-Pro and Inkling have no GGUF at all (Inkling's only quantized repo is a different and much smaller model), and Kimi K3 publishes 1- and 2-bit quants and a <code>Q4_K_XL</code> but no <code>Q4_K_M</code>. <code>IQ4_XS</code> is the smallest quantization most people would still call 4-bit, and it is what puts GLM 5.2 within reach of a single machine even though its <code>Q4_K_M</code> is not.</p>
</section>"""

    findings_html = """
<section class="findings">
  <h2>Findings</h2>
  <div class="finding"><h3><span class="tag win">law</span>The tool's value tracks the knowledge gap, in any weight class</h3>
  <p>Documentation lift lines up with baseline weakness: +22.0 for Qwen3.6-27B and +15.6 for Qwen3.6-35B-A3B at the knowledge floor, then +9.1 for GPT-5.6 Terra, +7.9 for GPT-5.6 Sol, +6.4 for GLM 5.2, +6.3 for Qwen3 Coder Next, +5.2 for MiniMax M3, +2.3 for Hy3, +1.5 for GPT-5.6 Luna, fading to nothing and then to a penalty at the saturated top (Grok +0.6, Opus 5 &minus;0.1, K3 &minus;0.3, Fable &minus;1.6, MiMo &minus;2.6, Sonnet 5 &minus;5.4).</p>
  <p>Three refinements. The law applies per <i>variant</i>, and not in the direction we first reported: Terra's gain <i>grows</i> up its ladder (+2.0 with thinking off, +4.2 at <code>minimal</code>, <b>+9.1</b> at <code>max</code>), so a model can be saturated on its own and still have room the tool fills at full effort, and Sol behaves the same way (+7.9 at <code>max</code>). That is not a vendor effect, though: Luna, the third OpenAI model here, gains +3.0 at its top tier, which its own interval cannot separate from zero, against +0.1 and &minus;0.4 at its two other measured tiers. Also documentation raises MiniMax at four of its six tiers (+13.0, +12.3, +7.1, +3.2) while costing it 5.5 points at the one tier its baseline happens to win on, which is why the like-for-like gain above understates the tool. The lift is mostly bought in solves, not in polish: at the floor it converts runs that never worked into working ones (Qwen3.6-27B 15% to 69% solved, Qwen3.6-35B-A3B 11% to 59%, Coder Next 0% to 17%). And the law has a competence floor, because a model has to be able to exploit what it reads: Gemma 4 31B (−1.8) and gpt-oss-120b (−1.7, zero solves with documentation or without) sit below it.</p></div>
  <div class="finding"><h3><span class="tag win">thinking</span>The thinking dial rarely buys correctness, but it can buy first-try delivery</h3>
  <p>Four patterns across the field (the two small Qwen models are their own case, below): thinkers whose dial never moves correctness (Sonnet 5, Opus 5, Fable 5, and Grok 4.5, where it only nudges the first-submission rate from 69% to 74%), an indifferent one (MiMo, 100% at all seven tiers), an obedient one that spends budget without needing it (Gemini), and real curves where thinking buys solves (GLM, MiniMax, and Inkling, whose curve overshoots: 94% correctness at <code>low</code> down to 88% at <code>high</code>). One thing changed with this index. The best variant is no longer the cheapest tier that holds correctness, because a pricier tier that gets it right on the first submission now beats a cheap tier that iterates, and that moved five models along their own ladders: Gemini and Sol up to <code>max</code>, GLM to <code>xhigh</code>, Terra to <code>max</code>, MiniMax down to <code>medium</code>. Up is not the same as topmost, though: GLM's <code>max</code> tier is its worst, 10 points below the <code>xhigh</code> that wins.</p>
  <p>The top of the ladder is where Anthropic's three models change character, and every one of them pays for it. <code>max</code> lifts first-submission delivery (Fable to 100%, Sonnet to 88% from 67%) while spending three to thirty-four times the tokens: Opus 92.0 at <code>low</code> against 85.0 at <code>max</code>, Fable 88.4 against 83.7, Sonnet 83.4 against 73.2 on 61k output tokens and nine minutes a task. Buying reliability that way costs more than the reliability is worth here, which is the same trade the small models lose at the other end of the field. Kimi K3 shows the mirror image: its <code>low</code> tier ties its default (83.2 against 83.1, intervals well overlapped) at a third of the price and a third of the time, so the cheap setting is the one to run.</p>
  <p>The two small Qwen models invert the question, and not the way the index alone suggests. Thinking does buy them solves: Qwen3.6-27B goes from 15% of runs solved with thinking off to <b>31% at <code>low</code></b>, and 35B-A3B from 11% to 23% at <code>high</code>. What it cannot buy is value. Those extra solves cost three to five times the output tokens and four to fourteen times the wall clock (27B: 10.8k tokens and 181s off, against 51.5k and 864s at <code>low</code>), so the index refuses to pay and thinking off still wins on score. One tier is genuinely self-defeating rather than merely expensive: 35B-A3B at <code>xhigh</code> burns 94k tokens to solve 4% of runs. Documentation is the better purchase at this end of the field, and it pays most exactly where thinking is off (27B +22.0 there, +8 at <code>xhigh</code>).</p></div>
  <div class="finding"><h3><span class="tag cost">habits</span>One-shot ability is architectural; documentation can't buy it</h3>
  <p>GPT-5.6 Sol iterates against the compiler even at flagship scale and price: at its best tier it delivers on the first submission 40% of the time and takes a median of two submissions per task, where Opus 5 and Fable 5 land first-try nearly always (100% and 96%). But this is the one habit documentation does buy. Given the tool at that same tier, Sol jumps to <b>72% first-submission</b> (p=0.014, the only shift in this study that clears significance) and its score rises 69.5 to 77.4. We reported the opposite earlier from its two weakest tiers, which were the only ones we had measured in both conditions: at 19% and 15% the tool looked useless to it. Measured where the model is actually good, it is worth more to Sol than to almost anyone.</p>
  <p>Tool use splits the same way. Offered the docs, the three Anthropic models here never called them once, so the tool is pure schema overhead for them (Opus 5 gave that pattern its cleanest datapoint: zero calls, −0.1 points). Grok 4.5 consults them about once per run it does not obviously need, and no longer pays for the habit: +0.6 points, and a first-submission rate that moves the right way at the same tier, 74% to 88%. Under the previous index that same behaviour scored as a 13-point penalty, because a lookup consumed a turn and turns were what got counted. Nothing about Grok changed; the ruler did. Treat the direction as directional only, though: at the MCP condition's depth these first-submission shifts do not reach significance (Grok p=0.21, Sonnet's 67% to 50% drop p=0.15).</p></div>
  <div class="finding"><h3><span class="tag cost">economics</span>Pro-style serving modes are strictly dominated</h3>
  <p>Both pro serving modes we funded cost 2 to 3× their model's <code>max</code> tier and scored below it (terra-pro 53.8 against terra@max 55.2). Neither ever produced the best configuration of its model, so sol-pro was not funded on that record.</p></div>
  <div class="finding"><h3><span class="tag win">mechanism</span>Why the tool works: baseline failures are training-data lag</h3>
  <p>Failed baseline runs get stuck on <em>current</em> Cairo idioms (most often the storage API: pre-2024 <code>Map.read(key)</code> instead of today's <code>Map.entry(key).read()</code>) and burn the whole 10-turn budget against the compiler. One documentation lookup resolves it. The mechanism was diagnosed on the deepest dataset (993 runs): the tool often <em>lowered</em> median cost there, with lookups rising as the thinking budget fell (~0.7/run at high effort, ~1.9/run with thinking off), and the same signature shows up wherever the tool pays, from Qwen's knowledge floor to Hy3's over-budget grinds.</p>
  <p>The substitution is visible in which configuration wins. Six of the twenty models pick a different thinking level with the tool than without, and four of those six pick a <i>cheaper</i> one: Gemini <code>max</code> to <code>low</code>, MiniMax <code>medium</code> to <code>low</code>, Hy3 <code>high</code> to off, GLM <code>xhigh</code> to off. DeepSeek and Luna go the other way. Reference material buys what thinking budget was being spent on.</p></div>
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
  table.sortable td:first-child{{white-space:nowrap}}
  table.sortable th{{cursor:pointer;user-select:none;white-space:nowrap}}
  table.sortable th:hover,table.sortable th:focus-visible{{color:var(--ink)}}
  table.sortable th.asc::after{{content:" \\25B2";font-size:9px}}
  table.sortable th.desc::after{{content:" \\25BC";font-size:9px}}
  td{{padding:7px 8px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}}
  th.r,td.r{{text-align:right}}
  .ci{{color:var(--muted);font-size:11px}}
  /* 48/4 is not arbitrary: the title sat 22px under the legend above and 26px
     above its own chart's first drawn pixel (the svg carries ~26px of internal
     top padding for the value labels), so it read as belonging to the chart
     above. Measured, the gap above is now ~2x the gap below. */
  /* small multiples: title centred over its own chart, which means centring the
     wrapper so the inline svg moves with it. The note cell keeps its paragraph
     left-aligned, since centred body text reads badly. */
  .multiple{{text-align:center}}
  .multiple h3{{font-size:13px;margin-bottom:6px}}
  .multiple>p{{text-align:left}}
  .chart-title{{font-size:12px;letter-spacing:.06em;text-transform:uppercase;
    color:var(--muted);margin:48px 0 4px;text-align:center}}
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
  <p class="lede">{len(sci_rows)} models ran the same {len({r["task"] for r in all_runs if r["task"] != "fake"})} Starknet smart-contract tasks: the leading open-weight coders, large and small, alongside the current closed models from {closed_labs}. Most ran their full effort ladder, all ran at least one setting they expose, and every one ran with and without the <b>Cairo Coder</b> documentation tool.</p>
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

{local_html}

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
        <li><b>Prices move after the runs do:</b> the runs were billed at the prices listed on 2026-07-24, and three models have been cut since. Their cost scores are re-based to today's listing by rescaling what we were billed: GPT-5.6 Terra to 0.40&times;, GPT-5.6 Luna to 0.10&times;, GLM 5.2 to 0.90&times;. That is exact rather than approximate, because each of those cuts moved input, output and both cache rates by the identical factor, so the new cost of a recorded run does not depend on its mix of fresh, cached and output tokens. Three other models (Qwen3.6-27B, Gemma 4 31B, Qwen3 Coder Next) changed input and output by <i>different</i> factors and are therefore <b>not</b> re-based: recomputing them would need the cache read/write split, which a single billed total cannot reveal. GPT-5.6 Sol was checked and is unchanged. Prices throughout are the standard endpoint, not the cheaper deferred-latency <code>flex</code> tiers, which we did not benchmark and whose latency would not match the speed scores. Total spend below is what was actually paid, unrevised.</li>
        <li><b>Solved</b> = every hidden test passes within the budget: 10 turns and 15 minutes of model time (LLM + doc-tool wait; wall time is not used because it depends on harness concurrency). An <b>attempt is a submission</b>, not a turn, so lookups and extra thinking turns are free and only delivered-and-broken code costs.</li>
        <li><b>Not every requested effort is a distinct setting:</b> OpenRouter publishes a <code>supported_efforts</code> list per model, and several levels we swept fall outside it, where the provider maps the request to something else. Median output tokens per run show exactly that. GLM 5.2 (supports <code>xhigh</code>, <code>high</code>): <code>minimal</code> 10.1k, <code>low</code> 10.1k, <code>medium</code> 9.6k and <code>high</code> 10.6k are one effective level, while <code>xhigh</code> 29.6k, <code>max</code> 53.6k and thinking off 5.0k are genuinely distinct. DeepSeek and Hy3 flatten the same way in their middle, and Gemini's <code>xhigh</code> and <code>max</code> match its <code>high</code>. So on those curves some neighbouring points are the same configuration and the wiggle between them is sampling noise, not a dial response; the x-axis is what we <i>requested</i>. Qwen, MiMo and MiniMax publish no list, so nothing can be said either way for them. The list is unreliable in the other direction too: Inkling advertises six efforts, but <code>medium</code> and <code>max</code> return a server error on every request while <code>high</code> works in the same minute, so its three measured tiers are all it has. None of this moves a conclusion: "the dial rarely buys correctness" holds across the field, and the distinctions the substitution finding rests on (off, mid, <code>xhigh</code>, <code>max</code>) are the real ones.</li>
        <li><b>Reps and precision:</b> each model's best variant was sampled until its index confidence interval reached &plusmn;5 points (bootstrapped over its runs, 1,000 resamples), which took 2 to 10 passes of the suite depending on how noisy the model is. The interval is printed beside every score above, and <b>every model in the table now meets it</b>: the widest is &plusmn;4.9. &plusmn;5 is the floor on purpose. Most adjacent pairs in the ranking sit under 2 points apart, so they are ties that no affordable sample size resolves, and pricing &plusmn;3 for every variant that could plausibly win came to 2,086 further runs for one extra resolved pair. The MCP condition keeps its original 2 to 3 passes everywhere except GLM, whose MCP cells also reach 130 runs, so outside GLM the deltas are less precise than the headline scores.</li>
      </ul>
    </div>
    <div>
      <h2>Caveats</h2>
      <ul class="meta">
        <li><b>Unequal depth by design:</b> GLM 5.2 carries the deepest dataset (993 runs across seven efforts and both conditions, from the original pilot study); it anchors the substitution-law finding and the n=130 statistics. Newer entrants carry 25 to 120 runs per variant, deepest where the index was noisiest. GLM runs predate the streaming and reasoning-round-trip harness fixes, which its own data shows it did not need.</li>
        <li><b>Eight cells abandoned:</b> host-sleep and network stalls made six unrecoverable (five qwen/minimax baseline cells, one MiMo MCP cell), one qwen@high cell was cut when its batch was stopped manually, and one Hy3 run was killed at 22m43s after grinding far past the 900-second model-time budget, with its last delivered submission taken as the result (it scored zero either way, being over budget). All count as failures, consistent with their completed sibling reps. The stopped batch also skipped its tiebreaker pass, leaving 11 qwen high/max cells at 2 disagreeing reps (scored as the 2-rep mean). Time and cost medians exclude abandoned cells.</li>
        
        <li><b>MCP backend, tested:</b> @high's first 3 reps used the hosted api.cairo-coder.com; everything else used a self-hosted replica (same corpus re-ingested, same embedding/generation models). A direct A/B (39 runs each, identical tasks/effort) found <b>identical effectiveness</b> (38/39 solved on both, same turn counts), so hosted-index staleness did not skew results; only lookup speed differs (~5× faster locally). Data is pooled.</li>
        <li><b>Statistics:</b> GLM's confirmation batches raised its low/medium/high baseline cells to n=130 (its other tiers hold 26 to 39; report-wide, baseline cells run 25 to 120). The apparent "low beats high" ordering at 3 reps did not survive: low ~ medium (p=0.83), high trails non-significantly (p=0.09), both two-proportion z-tests on solve counts (Fisher's exact is more conservative still, at 1.00 and 0.14). Solve-rate claims here carry Wilson 95% CIs of roughly ±5pt at n=130 and ±9pt at n=39.</li>
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
    clipped = angled_labels_overhanging(html)
    if clipped:
        raise SystemExit(
            "angled chart labels run off the left edge:\n  "
            + "\n  ".join(f"{t!r} needs {need:.0f}px, has {have:.0f}px" for t, need, have in clipped)
            + f"\nA label reaches width*cos({LABEL_ANGLE}deg) left of its column centre. "
              "Steepen LABEL_ANGLE, raise AXIS_PAD_L, or shorten the label; the old "
              "answer was a per-chart pad_l, which is how they drifted apart."
        )


def angled_labels_overhanging(html, margin=4):
    """Angled labels whose text would cross the left edge of their own SVG.

    Third time this class of bug has come up (pad_b clipped "Gemini 3.6 Flash"
    twice, pad_l once), so it is checked rather than commented. Same width
    estimator the padding uses, verified exact against getComputedTextLength.
    """
    bad = []
    for svg in re.findall(r"<svg.*?</svg>", html, re.S):
        for m in re.finditer(
            r'rotate\(-[\d.]+ ([\d.]+) [\d.]+\)"[^>]*(?:x="([\d.]+)")?[^>]*>(.*?)</text>',
            svg, re.S,
        ):
            cx = float(m.group(1))
            anchor = float(m.group(2)) if m.group(2) else cx
            text = re.sub(r"<[^>]+>", "", m.group(3)).strip()
            if not text:
                continue
            need = label_width(text) * math.cos(math.radians(LABEL_ANGLE))
            if need > anchor - margin:
                bad.append((text, need, anchor - margin))
    return bad


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
