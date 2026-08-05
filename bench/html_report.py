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
from collections import defaultdict
from pathlib import Path

from . import config
from .report import load_runs
from .sci import (CHART_TOP_N, LOCAL_QUANT,
                  LOCAL_RESERVE_GB, LOCAL_VRAM_GB, LOCAL_WEIGHT_BUDGET_GB,
                  SCI_SPEC, attempt_score, attempts, compute_sci, index_ci,
                  leaderboard, param_count, run_cost)

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


def chart(svg, small=False):
    """Wrap a chart so a narrow screen scrolls it instead of shrinking it.

    An SVG at width:100% is happy to render at any size, and on a phone that
    means a chart drawn for 760px lands at ~0.38 scale with 4px axis labels.
    The floor in .chartwrap keeps it legible and the reader swipes, which is
    what the tables on this page already do.

    assert_output_is_portable counts charts against wrappers, so a new chart
    that skips this fails the build. small=True is the 380px-wide small
    multiples of the thinking-dial section, which need a floor of their own.
    """
    return f'<div class="chartwrap{" small" if small else ""}">{svg}</div>'


def line_chart(x_labels, vals, win_i, color, w=380, h=200, y_min=0, y_max=100):
    """One model's index across its effort ladder, for the dial multiples.

    win_i rings the tier the leaderboard scores, so each mini chart answers
    "where on its ladder does this model actually live" without a caption.
    """
    pad_l, pad_r, pad_t, pad_b = 40, 16, 20, 30
    cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(x_labels)
    sx = lambda i: pad_l + (i * cw / (n - 1) if n > 1 else cw / 2)
    sy = lambda v: pad_t + (y_max - v) / (y_max - y_min) * ch
    parts = [svg_open(w, h)]
    step = 20 if y_max - y_min > 60 else 10
    for gv in range(y_min + (step - y_min % step) % step, int(y_max) + 1, step):
        y = sy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - pad_r}" y2="{y:.0f}" stroke="{LINE}"/>')
        parts.append(f'<text x="{pad_l - 6}" y="{y:.0f}" font-size="11" fill="{MUTED}" text-anchor="end" dominant-baseline="middle">{gv}</text>')
    for i, lab in enumerate(x_labels):
        parts.append(f'<text x="{sx(i):.0f}" y="{h - 10}" font-size="11" fill="{MUTED}" text-anchor="middle">{lab}</text>')
    pts = " ".join(f"{sx(i):.0f},{sy(v):.1f}" for i, v in enumerate(vals))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>')
    for i, v in enumerate(vals):
        parts.append(f'<circle cx="{sx(i):.0f}" cy="{sy(v):.1f}" r="4" fill="{color}"/>')
        if i == win_i:
            parts.append(f'<circle cx="{sx(i):.0f}" cy="{sy(v):.1f}" r="7.5" fill="none" '
                         f'stroke="{color}" stroke-width="1.5"/>')
        # the first point's label anchors right of its dot: centered, it lands
        # on the y-axis tick text when the line runs near a gridline (Grok's
        # flat 86 under the 90 tick printed as "9086")
        anchor = "start" if i == 0 else "middle"
        # one decimal: integer labels made ties look like errors (Gemini printed
        # 71/71/71/71 with the ring on 70.9)
        parts.append(f'<text x="{sx(i) + (2 if i == 0 else 0):.0f}" y="{sy(v) - 11:.1f}" '
                     f'font-size="11" fill="{INK}" text-anchor="{anchor}" font-weight="600">{v:.1f}</text>')
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
# hence the old 110. The floor for the then-64px margin is 53.1 degrees; 55
# clears it by 7.6px and costs 18px of label depth, where 60 would cost 25px for
# slack nothing needs. Below 64 the y-axis ticks ("$2.50", ~41px) start to bind.
#
# assert_output_is_portable enforces this geometry, so a future name long enough
# to break it fails the build instead of rendering clipped.
# Raised twice as the cut moved, both times for the same label. At the top
# twelve, pad 64 left "DeepSeek V4 Flash (off)" (152px) reaching 87.1px against
# 87px of clearance and the build guard caught it at 0.1px; 72 bought an 8px
# margin. The top fifteen narrows every column from 54 to 43px, which pulls
# column 0's centre 5.4px left and spends most of that margin again, so 80. A
# pixel of pad is worth 0.97px of clearance, not 1: the plot loses the width, so
# the columns narrow slightly too. The same worst case now clears by 13.9px, and
# the angle stays put, being already steep enough that every extra degree costs
# more label depth than it buys.
LABEL_ANGLE = 55
AXIS_PAD_L = 80
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


WORDS = ("zero one two three four five six seven eight nine ten eleven twelve "
         "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty "
         "twenty-one twenty-two twenty-three twenty-four").split()


def word(n):
    """Small counts spelled out, for prose that must track the data.

    Counts the report states in words ("eight models clear it") went stale every
    time the roster changed, and an audit check is a poor substitute for the
    number being derived in the first place.
    """
    return WORDS[n] if n < len(WORDS) else str(n)


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
    #
    # 64 rather than AXIS_PAD_L: this is the only chart drawn in rank order, so
    # column 0 always holds the leader, and a leader's label is short by the
    # nature of the thing ("Opus 5 (low)", 45px of reach against 86px of
    # clearance at fifteen columns). The charts that sort by cost or by time can
    # put any name first and pay the wider margin for it.
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
    """Paired horizontal bars, one group per metric: closed champion (lavender)
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
FITS_BG = "#dbe7fc"         # blue-05 wash: a quant that fits one local machine
# Warm neutral on purpose. It has to be legible in a band 2% tall (DeepSeek
# fails 1 run in 52), which ruled out the diagonal hatch tried first: at that
# height it was invisible. It also has to stay off the lavender ramp, so it
# cannot be misread as a fifth submission bucket, and off coral, which means
# "added by the MCP" in the charts below.


def attempts_dist_chart(rows, w=760, h=389, pad_l=AXIS_PAD_L):
    """Stacked column per model, covering 100% of that model's runs.

    Segments are how many submissions the working code took; the tan band on
    top is runs that never worked at all, so solve rate reads as everything
    below it. A column that is mostly dark blue is a model that just
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
            ly_pct, fill = sy(0) - 7, SNF_BLUE      # unsolved band, so ink not white
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


def attempts_chart(groups, w=760, h=234, y_max=None, fmt=None, ticks=None):
    """Grouped columns per task difficulty, one pair (closed lavender, open blue)
    per tier.

    Started life as median attempts per tier, which v3 made useless: both
    champions one-shot the median task at every difficulty, so all six columns
    read "1". It now takes any per-tier metric, and the section feeds it the
    first-submission rate, which is what actually separates them.

    groups: [(tier_label, val_closed, val_open)]
    """
    # pad_t 42, not the 26 of the other titled charts: the champions post 100%,
    # so bars reach the top gridline and their labels ride 7px above it. The
    # extra headroom keeps the ink-to-title gap the .chart-title contract
    # expects (see the comment on .chart-title). h grew 210 -> 234 in step, so
    # the plot itself kept its height.
    pad_l, pad_r, pad_t, pad_b = 64, 40, 42, 30
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

    a = SCI_SPEC["anchors"]
    w_ = SCI_SPEC["weights"]

    # The headline charts draw the top CHART_TOP_N by index, and nothing about
    # a model's size or license affects whether it is in. They used to draw
    # every model that did NOT fit one 512 GB machine, which ranked the page by
    # memory footprint: MiniMax M3 placed 9th and was still kept off the
    # leaderboard for being runnable at home.
    #
    # Models that fit that machine keep their own section (the class is derived
    # in sci.fits_locally, never hand-set), so most of the models below the cut
    # are still charted there; deprecated models are already gone from sci_rows
    # entirely (see sci.active_models).
    chart_rows = sci_rows[:CHART_TOP_N]
    local_rows = [r for r in sci_rows if r.get("local")]
    charted_labels = {r["label"] for r in chart_rows}

    # A model whose weights are announced but not yet downloadable is classed
    # open with a display-time star on its label; raw labels stay untouched
    # because they key the mcp_rows lookups. No model carries the flag today
    # (K3's weights published 2026-07-27), so this renders nothing until one does.
    starred = lambda rows: [
        dict(r, label=r["label"] + "*") if r.get("weights_pending") else r for r in rows
    ]
    # The ONE place the report explains the star, by request: the legend of the
    # leaderboard chart, where a pending model first appears. Every later star
    # (the Behind-the-score charts, the MCP chart, the head-to-head paragraph,
    # the models table's `open*` cell) wears the mark unexplained on purpose.
    # If a pending model ever ranks below the chart cut this renders nothing
    # while the table still prints `open*`; the audit's exactly-once count then
    # fails loudly rather than shipping an unexplained star.
    pending_note = (
        '<span>* weights promised but not yet released</span>'
        if any(r.get("weights_pending") for r in chart_rows) else ""
    )

    # Chart 2: best-without vs best-with the MCP, per model. Each condition
    # picks its own best thinking variant (deployment framing), so labels
    # carry no effort. Models without MCP runs are omitted, not shown empty.
    mcp_rows = {r["label"]: r for r in leaderboard(all_runs, condition="mcp")}

    # Shared by the local-inference table and the models table further down, so
    # the two cannot print different throughput for the same model. Median
    # output tokens per second of model time, best baseline variant.
    def tokens_per_s(spec):
        tps = sorted(x["completion_tokens"] / x["llm_time_s"] for x in all_runs
                     if x["model"] == spec and x["condition"] == "baseline"
                     and x["completion_tokens"] and x["llm_time_s"])
        return tps[len(tps) // 2] if tps else None

    tps_by_label = {r["label"]: tokens_per_s(r["spec"]) for r in sci_rows}
    meta = json.loads((config.REPO_ROOT / "results" / "model_meta.json").read_text())

    # numeric cells carry their raw value in data-s so the sorter never has
    # to parse display strings; n/a cells carry none and always sort last
    num_td = lambda v, txt: (f'<td class="r" data-s="{v}">{txt}</td>' if v is not None
                             else '<td class="r">n/a</td>')

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
    lift_legend = f'<div class="legend legend-bottom">{keys_for(chart_rows)}</div>'
    lift_legend_local = f'<div class="legend legend-bottom">{keys_for(local_rows)}</div>'

    # The substitution count is field-wide and always was; the sentence below
    # used to justify it with "counting this chart and the local one together",
    # which stopped being true when the charts stopped drawing everyone. The
    # count is derived here and the prose says where the uncharted switchers are
    # rather than implying the charts cover the field.
    VARIANT_ORDER = ["off", "minimal", "low", "medium", "high", "xhigh", "max"]
    vpos = lambda v: VARIANT_ORDER.index(v) if v in VARIANT_ORDER else -1
    switched = [(lbl, b, m) for lbl, (b, m) in lift_efforts.items() if b != m]
    switched_down = [s for s in switched if vpos(s[2]) < vpos(s[1])]
    switched_offchart = [s for s in switched
                         if s[0] not in charted_labels
                         and s[0] not in {r["label"] for r in local_rows}]

    # The clause names the models, so it has to read for one of them and vanish
    # for none. Widening the cut to fifteen left GLM 5.2 alone in it, and at zero
    # the sentence printed "Zero of the eight switchers () rank below the cut":
    # an empty parenthetical wrapped around nothing.
    series = lambda ns: ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " and " + ns[-1]
    offchart_note = ""
    if switched_offchart:
        _n = [s[0] for s in switched_offchart]
        _s = "s" if len(_n) == 1 else ""
        offchart_note = (
            f' {word(len(_n)).capitalize()} of the {word(len(switched))} switchers '
            f'({series(_n)}) rank{_s} below the cut and change{_s} effort where no chart '
            f'on this page shows it.'
        )
    lift_html = f"""
<section>
  <h2>What does the Cairo Coder MCP add? <span style="text-transform:none">(best config without vs with)</span></h2>
  <p class="takeaway" style="margin:0 0 10px">Same index, second question: each model's <b>best configuration without the tool</b> (solid bar) versus its <b>best configuration with it</b>. Each condition picks its own best thinking level, and the labels show it: <b>{word(len(switched))} of the {word(len(sci_rows))} models win at a different effort with the tool than without</b>, and {word(len(switched_down))} of those {word(len(switched))} move <i>down</i> the ladder, not up. Documentation substitutes for thinking budget.{offchart_note}</p>
  <h3 class="chart-title">Top {CHART_TOP_N} of the {len(sci_rows)} models tested</h3>
  {chart(mcp_lift_chart(build_lift_pairs(chart_rows), efforts=lift_efforts))}
  {lift_legend}
</section>"""
    # Local-inference section: prose and the chart, no table of its own. It had
    # one for a day, listing memory per model, and it was a second answer to a
    # question "Open weights in detail" already answers below. One table.
    local_html = f"""
<section>
  <h2>Local-inference class</h2>
  <p class="takeaway" style="margin:0 0 10px">The models you could run yourself. The test is <b>memory rather than parameter count</b>: the published <code>{LOCAL_QUANT}</code> weight file has to fit the {LOCAL_VRAM_GB} GB of unified memory that today's biggest buyable machines top out at (a DGX Spark, a Strix Halo box, an M5 Max MacBook Pro), minus {LOCAL_RESERVE_GB} GB reserved for the OS and a KV cache. <b>Total parameters count, not active ones</b>, because every weight has to be resident even when a sparse model fires only a few experts per token.</p>
  <p class="takeaway" style="margin:0 0 10px"><code>{LOCAL_QUANT}</code> draws the line because it is the default 4-bit quant, <b>the file most people actually download and run</b>, and the sweet spot where memory halves against 8-bit while quality holds. Below 4-bit, degradation stops being minor, and coding feels it first. These scores were measured on the full-precision models, so the class stops at the quant level where <b>the local copy still resembles the model that was scored</b>.</p>
  {chart(mcp_lift_chart(build_lift_pairs(local_rows), h=394, pad_b=120, efforts=lift_efforts))}
  {lift_legend_local}
</section>"""
    tip_js = """<div id="tip" hidden></div><script>
/* Pointer and touch both open this. The mouse path follows the cursor; a tap
   has no cursor to follow, so it anchors to the bar's own box and dismisses on
   the next tap anywhere else. Without the tap path these numbers simply did
   not exist on a phone. */
(function () {
  var tip = document.getElementById("tip");
  function show(bar, x, y) {
    tip.innerHTML = "<b>1-shot:</b> " + bar.dataset.oneshot + "<br><b>cost:</b> " + bar.dataset.cost
      + "<br><b>time:</b> " + bar.dataset.time;
    tip.hidden = false;
    if (x + tip.offsetWidth > window.innerWidth - 8) x = window.innerWidth - tip.offsetWidth - 8;
    if (y + tip.offsetHeight > window.innerHeight - 8) y = y - tip.offsetHeight - 28;
    tip.style.left = Math.max(8, x) + "px"; tip.style.top = Math.max(8, y) + "px";
  }
  document.querySelectorAll(".scibar").forEach(function (bar) {
    bar.addEventListener("mousemove", function (e) { show(bar, e.clientX + 14, e.clientY + 14); });
    bar.addEventListener("mouseleave", function () { tip.hidden = true; });
    bar.addEventListener("click", function (e) {
      e.stopPropagation();          /* so the document handler does not close it again */
      var b = bar.getBoundingClientRect();
      show(bar, b.left + b.width / 2, b.top - 10);
    });
  });
  document.addEventListener("click", function () { tip.hidden = true; });
})();
</script>"""
    sci_html = f"""
<section>
  <h2>Starknet Coding Index <span style="text-transform:none">(baseline, no assistance)</span></h2>
  <p class="takeaway" style="margin:0 0 10px">One number per model for "how good is this LLM at writing Starknet smart contracts today", weighted toward the thing you actually get: <b>working code on the first submission</b>. Each model runs the full task suite alone, at its <b>best thinking variant</b> (labeled in parentheses), within a budget of 10 turns and 15 minutes of model time per task.</p>
  <h3 class="chart-title">Top {CHART_TOP_N} of the {len(sci_rows)} models tested</h3>
  {chart(sci_bar_chart(starred(chart_rows)))}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>open weights</span><span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>closed weights</span>{pending_note}</div>
  {tip_js}
</section>"""
    import math
    cost_max = math.ceil(max(r["tip"]["cost"] for r in chart_rows) / 0.5) * 0.5
    time_max_m = math.ceil(max(r["tip"]["secs"] for r in chart_rows) / 60 / 20) * 20
    # compact decimal minutes ("2.5m", "72m"): narrow enough that neighbors
    # never collide at 16 columns
    mins = lambda s: (f"{s / 60:.1f}m" if s < 600 else f"{s / 60:.0f}m")
    pass_html = f"""
<section>
  <h2>Behind the score</h2>
  <p class="takeaway" style="margin:0 0 10px">The same top {word(CHART_TOP_N)}, winning variants unpacked, baseline condition. The first chart is the whole distribution behind the effectiveness score: every column covers 100% of that model's runs, split by whether the code worked on submission one, two, three, or later, and topped by a warm-tan band ("never solved" in the legend) for the runs that never worked. Solve rate is everything below that band. Cost and time are the median of a complete pass over the 13-task suite. Each chart ranks best first.</p>
  <h3 class="chart-title">How many submissions it takes</h3>
  {chart(attempts_dist_chart(sorted(starred(chart_rows), key=lambda r: -r["dist"][0])))}
  <div class="legend legend-bottom">{"".join(
      f'<span><span class="key" style="background:{ATTEMPT_COLORS[k]};border-radius:2px"></span>{lbl}</span>'
      for k, lbl in enumerate(["1 submission", "2", "3", "4 or more"]))}<span><span class="key" style="background:{UNSOLVED_COLOR};border-radius:2px"></span>never solved</span><span>labels: first-submission share</span></div>
  <h3 class="chart-title">Cost per pass</h3>
  {chart(metric_bar_chart(sorted(starred(chart_rows), key=lambda r: r["tip"]["cost"]),
                    lambda r: r["tip"]["cost"], lambda v: f"${v:.2f}",
                    cost_max, [(t * 0.5, f"${t * 0.5:.2f}") for t in range(int(cost_max / 0.5) + 1)]))}
  <h3 class="chart-title">Model time per pass</h3>
  {chart(metric_bar_chart(sorted(starred(chart_rows), key=lambda r: r["tip"]["secs"]),
                    lambda r: r["tip"]["secs"], mins,
                    time_max_m * 60, [(t * 20 * 60, f"{t * 20}m") for t in range(int(time_max_m / 20) + 1)]))}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>open weights</span><span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>closed weights</span></div>
</section>"""

    # The thinking dial, baseline only: the four clearest top-15 examples of
    # each shape. Hand-picked, but direction-gated in audit so a data refresh
    # that flips one fails the build instead of mislabeling it. Descends from
    # the effort-curves section removed in faabe2a, which drew solve rate for
    # the whole field in both conditions and drowned. Tiers are DERIVED from
    # the data: a tier the API rejects (gpt-oss refuses @disabled) never
    # appears, and extending a ladder never goes stale.
    DIAL_PAYS = ["GPT-5.6 Sol", "Gemini 3.6 Flash", "MiniMax M3", "GPT-5.6 Terra"]
    DIAL_COSTS = ["Opus 5", "Sonnet 5", "Kimi K3", "DeepSeek V4 Flash"]
    EFFORT_ORDER = ["disabled", "minimal", "low", "medium", "default", "high", "xhigh", "max"]
    EFFORT_SHORT = {"disabled": "off", "minimal": "min", "medium": "med", "default": "def"}
    base_by_spec = defaultdict(list)
    for r in all_runs:
        if r["condition"] == "baseline":
            base_by_spec[r["model"]].append(r)
    # KeyError here = a pick fell out of the top 15; that should stop the build
    _by_label = {r["label"]: r for r in chart_rows}

    def dial_row(label):
        row = _by_label[label]
        pts = []
        for spec in row["specs"]:
            rs = base_by_spec.get(spec)
            if not rs:
                continue
            eff = spec.partition("@")[2] or "default"
            pts.append((EFFORT_ORDER.index(eff), eff, compute_sci(rs)["sci"], len(rs)))
        pts.sort()
        return (row["label"], row["open_weight"], pts, row["spec"].partition("@")[2] or "default")

    dial_rows = {lab: dial_row(lab) for lab in DIAL_PAYS + DIAL_COSTS}
    _ns = [p[3] for _, _, pts, _ in dial_rows.values() for p in pts]
    DIAL_SPAN = 25  # same span in every panel: slopes compare, no dead air

    def dial_grid(labels):
        out = []
        for lab in labels:
            label, open_w, pts, win_eff = dial_rows[lab]
            vals = [v for _, _, v, _ in pts]
            # a shared absolute axis left every panel mostly empty (each line
            # moves within 4-12 points of a 50-point scale); a fixed span
            # centered per ladder keeps points-per-pixel identical instead
            y_lo = 5 * math.floor(((min(vals) + max(vals)) / 2 - DIAL_SPAN / 2) / 5)
            out.append(
                f'<div class="multiple"><h3>{label}</h3>'
                + chart(line_chart([EFFORT_SHORT.get(e, e) for _, e, _, _ in pts],
                                   vals, [e for _, e, _, _ in pts].index(win_eff),
                                   SCI_OPEN_COLOR if open_w else SCI_CLOSED_COLOR,
                                   y_min=y_lo, y_max=y_lo + DIAL_SPAN), small=True)
                + "</div>")
        return f'<div class="multiples">{"".join(out)}</div>'

    dial_html = f"""
<section>
  <h2>The thinking dial</h2>
  <p class="takeaway" style="margin:0 0 10px">Same index, baseline runs only: the four clearest examples of each shape among the top {word(CHART_TOP_N)}, each drawn across its own effort ladder. <b>Effort pays</b> where a first-try deficit is left to close, and the ring marking the tier the leaderboard scores sits high on the ladder. <b>Effort costs</b> where delivery is already first-try, and the ring sits at the bottom.</p>
  <h3 class="chart-title">Effort pays</h3>
  {dial_grid(DIAL_PAYS)}
  <h3 class="chart-title">Effort costs</h3>
  {dial_grid(DIAL_COSTS)}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_OPEN_COLOR}"></span>open weights</span><span><span class="key" style="background:{SCI_CLOSED_COLOR}"></span>closed weights</span><span>ring: the tier the leaderboard scores (ties go to the deepest-measured tier)</span><span>every panel spans {DIAL_SPAN} index points, centered on its own ladder</span><span>x is the requested effort; some neighbouring tiers are the same provider setting</span><span>{min(_ns)}–{max(_ns)} runs per point</span></div>
</section>"""

    # Fair questions: the priors readers arrive with. The QUESTION is the hook a
    # reader scans for, so it leads the card; the number is evidence and sits
    # inside the answer. (The weights cards in "How the score is built" are the
    # opposite case, number-forward, and use .scorecard.)
    FAQ = [
        ("Why does Opus 5 win?", "100% one-shot",
         "Every task in every rep solved on the first submission, at the field's fastest "
         "median pass. Nothing else in the field is perfect on that measure, which is why a "
         "flagship price tag still leaves it 3.7 points clear."),
        ("Kimi K3 over MiMo? MiMo is far cheaper", "87% vs 40% one-shot",
         "This is the index working as intended. MiMo serves a pass 4.5× faster and 21× cheaper, "
         "and still loses 4.2 points, because it delivers broken code first about three runs in "
         "five. First-submission success carries twice the weight of the bill."),
        ("Kimi K3 and Qwen3.8 Max are the same size. Why 31 points apart?",
         "87% vs 9% first-try compiles",
         "Same class of MoE flagship, released a week apart, and both solve essentially every "
         "task; cost and speed differ by less than a point. <b>Thirty of the 31 points come "
         "from one place</b>: whether the first submission builds. Across both models no first "
         "submission compiled and then failed a test, so the gap is knowledge, not reasoning."),
        ("Sonnet 5 solves everything. Why 4th?", "67% vs 100% one-shot",
         "That first-try gap against Opus 5 is most of the 8.6 points between them. The dial "
         "does nothing until <code>max</code>, and that is a cliff, not a step: 88% one-shot, "
         "the best of any Sonnet setting, for 61k output tokens, $0.68 and nine minutes a task."),
        ("Which of these could I run myself?", "5 of 22",
         "They fit one 128 GB machine at Q4_K_M, from Qwen3.6-27B at 17 GB of weights to "
         "gpt-oss-120b at 63 GB, and they compare on their own footing in the section below. The "
         "rest need a rack or are closed."),
        ("Sol mid-pack? It rivals Fable elsewhere", "40% one-shot",
         "Cairo knowledge is not the problem (100% of hidden tests pass on delivered code); the "
         "habit is: a median of two submissions per task at $0.0895, nine times Grok's bill for "
         "half of Grok's first-try rate. The docs change the habit: 72% first-try and a median "
         "of one, the largest such shift in the study."),
    ]
    faq_cards = "".join(
        f'<div class="qcard"><h3>{q}</h3><p><b class="ans">{stat}.</b> {a}</p></div>'
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
  <p class="takeaway" style="margin:0 0 14px">The ranking's two champions, <b>{best_closed["label"]} ({best_closed["variant"]})</b> from {best_closed["lab"]} and <b>{best_open["label"]}{"*" if best_open.get("weights_pending") else ""} ({best_open["variant"]})</b> from {best_open["lab"]}, both solve every task; the gap is in <i>how</i>. The second chart is where it opens: they run close on easy and level on medium, then the hard tier separates them. Baseline condition, {sa["n"]} and {sb["n"]} runs.</p>
  {chart(head_to_head_chart(h2h_metrics))}
  <h3 class="chart-title">First-submission rate by task difficulty</h3>
  {chart(attempts_chart(h2h_attempts, y_max=100, fmt=lambda v: f"{v:.0f}%",
                  ticks=[(t * 25, f"{t * 25}%") for t in range(5)]))}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>{best_closed["label"]} ({best_closed["variant"]}), closed</span><span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>{best_open["label"]} ({best_open["variant"]}), open</span></div>
</section>"""

    # score definition applies to both charts above, so it gets its own section
    score_html = f"""
<section>
  <h2>How the score is built</h2>
  <div class="scorecards">
    <div class="scorecard"><div class="q">Effectiveness</div><div class="stat">{w_["effective"]:.0%}</div><p>Does it work without sending you back into the loop? A run scores 100 when the very first submission passes, then {SCI_SPEC["attempt_decay"]:.0%} of that per further attempt: 100 / 40 / 16 / 6 for 1 / 2 / 3 / 4 submissions, and 0 if it never works.</p></div>
    <div class="scorecard"><div class="q">Correctness</div><div class="stat">{w_["correct"]:.0%}</div><p>Average fraction of hidden tests passed per task. Partial credit on what was delivered: 90% passing is still broken, but it is closer than nothing.</p></div>
    <div class="scorecard"><div class="q">Cost</div><div class="stat">{w_["cost"]:.0%}</div><p>Median $ per task, scored on a fixed log scale (${a["cost"][0]} to ${a["cost"][1]}).</p></div>
    <div class="scorecard"><div class="q">Time</div><div class="stat">{w_["speed"]:.0%}</div><p>Median model latency per task, scored on a fixed log scale ({a["speed"][0]}s to {a["speed"][1]}s). Local compile/test time excluded.</p></div>
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

    fmt_price = lambda v: "n/a" if v is None else (f"${v:,.2f}" if v >= 0.01 else f"${v:.4f}")
    fmt_ctx = lambda v: "1M" if v >= 10**6 else f"{v // 1000}k"

    model_rows = []
    for r in sci_rows:
        api_id = r["spec"].partition("@")[0]
        mm = meta["models"][api_id]
        pm = mm["price_per_m"]
        tps_med = tps_by_label[r["label"]]
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
        # heaviest first: a reader scanning left to right meets full precision
        # before the compromises, and the fits-wash reads as a run in from the
        # right rather than a stub on the left
        for q in reversed(QUANT_LADDER):
            gb = gg.get(q)
            # A native-4-bit release (gpt-oss ships MXFP4) repacks to the same
            # ~63 GB at every level: rungs above Q4 that add <10% over Q4_K_M
            # are bigger containers, not more precision, so they print blank
            # instead of a flat row of the same number.
            if gb and gg.get(LOCAL_QUANT) and q in ("Q6_K", "Q8_0", "BF16") \
                    and gb < gg[LOCAL_QUANT] * 1.10:
                gb = None
            est = gb is None and q == LOCAL_QUANT and r["vram_gb"]
            if gb is None and not est:
                cells += '<td class="r"></td>'
                continue
            v = gb or r["vram_gb"]
            # two channels, not one: a lightness-only difference between "fits"
            # and "does not" was unreadable at this digit size. The wash also
            # draws a waterline across each row, so how far along the ladder a
            # model stays runnable reads without comparing any two numbers.
            fit = "fits" if v <= LOCAL_WEIGHT_BUDGET_GB else "nofit"
            cells += f'<td class="r {fit}" data-s="{v:.1f}">{"~" if est else ""}{v:,.0f}</td>'
        open_rows_html.append(
            f'<tr><td>{r["label"]}</td>'
            # the index rides along so this table can be read in score order too,
            # which is the order it ships in; the models table above has the rest
            + num_td(r["sci"], f'{r["sci"]:.1f}')
            + f'<td>{mm["type"] or "n/a"}</td>'
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
  <p class="takeaway" style="margin:0 0 10px">Every model tested, including the {word(len(sci_rows) - CHART_TOP_N)} below the chart cut. Use it to <b>shortlist by the constraint you actually have</b>: the index <b>with and without the documentation tool</b>, <b>price</b> (per million tokens, as listed on OpenRouter, {meta["snapshot_date"]}), <b>speed</b>, and <b>whether the weights are open</b>. Click a header to sort.</p>
  <div class="tablewrap"><table id="modeltable" class="sortable">
    <tr><th>Model</th><th class="r desc" data-num aria-sort="descending">SCI</th><th class="r" data-num>SCI (MCP)</th><th class="r" data-num>Δ</th><th>Lab</th><th>Weights</th><th class="r" data-num>Context</th><th class="r" data-num>$/M in</th><th class="r" data-num>$/M out</th><th class="r" data-num>Tok/s</th></tr>
    {"".join(model_rows)}
  </table></div>
  {sorter_js}
</section>

<section>
  <h2>Open weights in detail</h2>
  <p class="takeaway" style="margin:0 0 10px">What it takes to run the {len(open_rows)} open models yourself: every quantization published for each, in GB, from the <a href="https://huggingface.co/unsloth">unsloth</a> GGUF files. A blank means that quantization was never published; <b>~</b> marks an estimated size.</p>
  <p class="takeaway" style="margin:0 0 10px">Columns run heaviest first, and <span class="swatch" style="background:{FITS_BG}"></span> marks a file that <b>fits the {LOCAL_VRAM_GB} GB machine</b> from the section above, so the wash reads as a <b>waterline</b>: how far left a model stays runnable. <b>SCI</b> carries the leaderboard index across, so the table sorts by score as well as by size.</p>
  <div class="tablewrap"><table id="opentable" class="sortable">
    <tr><th>Model</th><th class="r desc" data-num aria-sort="descending">SCI</th><th>Type</th><th class="r" data-num>Params</th><th class="r" data-num>Active</th><th class="r" data-num>Context</th>{"".join(f'<th class="r" data-num>{q}</th>' for q in reversed(QUANT_LADDER))}</tr>
    {"".join(open_rows_html)}
  </table></div>
</section>"""

    # Same card grammar as Fair questions, by request: qcard grid, bold stat
    # lede, no tag chips. Declarative titles where the FAQ asks questions is
    # the one deliberate difference between the sections.
    FINDINGS = [
        ("Give the docs tool to a model that needs it", "+22.0 at the bottom",
         "The weaker the Cairo, the bigger the lift: Qwen3.6-27B goes from 15% of runs solved "
         "to 69%; frontier-sized Qwen3.8 Max gains +16.3; at the top it fades to zero and below "
         "(Sonnet 5 &minus;5.4)."),
        ("The thinking dial rarely buys correctness", "3 to 34x the tokens",
         "Most models are equally correct at every effort. Paying for <code>max</code> buys "
         "first-try polish at a lower score (Opus 5: 92.0 at low against 85.0 at max), and "
         "Kimi K3's <code>low</code> tier matches its default at a third of the price."),
        ("Pro-style serving modes are strictly dominated", "2 to 3x for less",
         "Both pro modes we funded scored below their model's <code>max</code> tier "
         "(terra-pro 53.8 against terra@max 55.2). Neither ever produced its model's best "
         "configuration, so sol-pro was not funded on that record."),
        ("Why the tool works: the models write an older Cairo", "one lookup",
         "Failing models write the pre-2024 <code>Map.read(key)</code> instead of "
         "<code>Map.entry(key).read()</code>, then burn their turns arguing with the compiler. "
         "One lookup fixes it, which is why the tool can make a model <i>cheaper</i>."),
        ("Cairo Coder confabulates outside its index", "no signal off-index",
         "Asked about a token standard we invented (\"STRK77\"), it returned a complete, "
         "confident, fabricated Cairo interface. Within its index it is accurate; agents get "
         "no signal when a query falls outside coverage. Worth fixing upstream."),
    ]
    findings_html = f"""
<section>
  <h2>Findings</h2>
  <div class="faq">{"".join(
      f'<div class="qcard"><h3>{q}</h3><p><b class="ans">{stat}.</b> {a}</p></div>'
      for q, stat, a in FINDINGS)}</div>
</section>"""

    # charset first: without it a browser guesses the encoding (file:// has no
    # Content-Type header to consult) and renders every multi-byte character as
    # mojibake, e.g. "9x cheaper" arriving as "9A- cheaper"
    # viewport second, and it is not optional: without it a phone lays the page
    # out at its default 980px and scales the result to ~40%, which also means
    # every max-width media query below never fires. The report shipped that way
    # until someone read it on a phone.
    return anchor_headings(f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Starknet Coding Index | A Starknet Foundation report</title>
<meta name="description" content="A Starknet Foundation benchmark: which LLM writes Starknet contracts best, and what does documentation access add? {len(all_runs)} agentic runs across {len(sci_rows)} models from {len({r["lab"] for r in sci_rows})} labs, on 13 hidden-test Cairo tasks, with and without the Cairo Coder documentation tool.">
<style>
  {inter_font_face()}
  :root{{
    --ground:{GROUND}; --panel:#FFFFFF; --ink:{INK}; --muted:{MUTED};
    --line:{LINE}; --mcp:{CORAL};
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
  /* Charts scroll rather than shrink below their floor, exactly like the wide
     tables. An SVG at width:100% will happily render a 760px chart at 290px,
     where an 11px axis label arrives at 4px; 660 keeps it at ~87% and a phone
     shows about 60% of the chart at a time. */
  .chartwrap{{overflow-x:auto}}
  .chartwrap>svg{{min-width:660px}}
  .chartwrap.small>svg{{min-width:300px}}
  /* "there is more to the right", for charts and for the 900px-wide tables.
     The cover gradients scroll with the content and hide the edge shadow
     whenever that edge is already in view, so the hint appears only when
     something really is cut off. Narrow screens only. rgba(255,255,255,0)
     rather than `transparent`, which Safari interpolates through grey. */
  @media(max-width:760px){{
    .chartwrap,.tablewrap{{background:
      linear-gradient(to right,var(--panel),rgba(255,255,255,0)) 0 0/26px 100% no-repeat local,
      linear-gradient(to left,var(--panel),rgba(255,255,255,0)) 100% 0/26px 100% no-repeat local,
      radial-gradient(farthest-side at 0 50%,rgba(8,4,53,.14),rgba(8,4,53,0)) 0 0/13px 100% no-repeat scroll,
      radial-gradient(farthest-side at 100% 50%,rgba(8,4,53,.14),rgba(8,4,53,0)) 100% 0/13px 100% no-repeat scroll}}
  }}
  .legend{{display:flex;gap:18px;font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:14px;flex-wrap:wrap}}
  .legend-bottom{{justify-content:center;margin:10px 0 0}}
  .key{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}}
  .takeaway{{font-size:14.5px;margin:14px 0 0}}
  .takeaway b{{color:var(--ink)}}
  .tablewrap{{overflow-x:auto;margin:24px 0 0}}
  table{{border-collapse:collapse;width:100%;min-width:900px;font-variant-numeric:tabular-nums}}
  th{{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:500;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}}
  table.sortable td:first-child{{white-space:nowrap}}
  table.sortable th{{cursor:pointer;user-select:none;white-space:nowrap}}
  table.sortable th:hover,table.sortable th:focus-visible{{color:var(--ink)}}
  table.sortable th.asc::after{{content:" \\25B2";font-size:9px}}
  table.sortable th.desc::after{{content:" \\25BC";font-size:9px}}
  /* runs on one machine vs does not: shaded ground plus ink, against no ground
     and muted text. Colour alone was too close to read at this size. */
  #opentable td.fits{{background:{FITS_BG};color:var(--ink);font-weight:600}}
  #opentable td.nofit{{color:var(--muted)}}
  .swatch{{display:inline-block;width:22px;height:12px;border-radius:2px;vertical-align:-1px}}
  td{{padding:7px 8px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}}
  th.r,td.r{{text-align:right}}
  .ci{{color:var(--muted);font-size:11px}}
  /* 35/4 is not arbitrary: the title's own chart provides ~26px of gap below
     (svg internal top padding for the value labels), so the margin above must
     stay comfortably larger than that for the title to read as belonging to
     the chart BELOW it, yet small enough that title and chart still hang
     together with the paragraph above. 48px read as disconnected; 35px keeps
     the above-gap bigger than the below-gap without the orphan look. */
  .chart-title{{font-size:12px;letter-spacing:.06em;text-transform:uppercase;
    color:var(--muted);margin:35px 0 4px;text-align:center}}
  .wchip{{font-family:var(--mono);font-size:11px;font-weight:600}}
  .wchip.ow{{color:{SCI_OPEN_COLOR}}} .wchip.cw{{color:{SCI_CLOSED_COLOR}}}
  .scibar{{touch-action:manipulation}}
  .scibar:hover{{filter:brightness(1.08)}}
  #tip{{position:fixed;z-index:10;background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:8px 11px;font-family:var(--mono);font-size:12px;color:var(--ink);box-shadow:0 4px 14px rgba(28,34,48,.14);pointer-events:none;white-space:nowrap}}
  #tip b{{font-weight:700}}
  .faq{{display:grid;grid-template-columns:1fr 1fr;gap:22px 28px;align-items:start}}
  .scorecards{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px 20px}}
  /* The span lives INSIDE the wide query on purpose. A `grid-column: span 2`
     outlives the grid-template-columns it was written for: at 1fr the browser
     satisfies the span by inventing an implicit second column, so the section
     rendered two-up on a phone (Correctness and Cost at ~160px each) while the
     stylesheet said one column. .faq and .split collapse correctly at the same
     breakpoint only because neither has a span to leak. */
  @media(min-width:761px){{.scorecards>:first-child{{grid-column:span 2}}}}
  @media(max-width:760px){{.scorecards{{grid-template-columns:1fr}}}}
  /* Weights cards: the number IS the content, so it leads. */
  .scorecard .q{{font-family:var(--mono);font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--ink)}}
  .scorecard .stat{{font-family:var(--mono);font-size:26px;font-weight:600;color:var(--accent);letter-spacing:-.02em;margin:4px 0 2px}}
  .scorecard p{{margin:0;font-size:13.5px}}
  /* Question cards: the opposite. The question carries the accent colour, which
     is what makes it the thing you land on; the figure is just bold inside the
     answer. Sentence case, not caps: caps read as a label and mangle a question
     with punctuation inside it. */
  .qcard h3{{font-size:16px;color:var(--accent);margin:0 0 6px}}
  .qcard p{{margin:0;font-size:13.5px}}
  .qcard .ans{{font-weight:700}}
  @media(max-width:760px){{.faq{{grid-template-columns:1fr}}}}
  /* row gap well above the h3's gap to its own chart, so a model name reads
     as a caption of the chart BELOW it, not the one above */
  .multiples{{display:grid;grid-template-columns:1fr 1fr;gap:32px 18px}}
  @media(max-width:760px){{.multiples{{grid-template-columns:1fr}}}}
  .multiple{{text-align:center}}
  .multiple h3{{font-size:13px;margin-bottom:2px}}
  code{{font-family:var(--mono);font-size:.92em;background:var(--ground);border:1px solid var(--line);border-radius:3px;padding:1px 5px}}
  .split{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}
  @media(max-width:760px){{.split{{grid-template-columns:1fr}}}}
  ul.meta{{margin:0;padding-left:20px;font-size:13.5px;color:var(--muted)}}
  ul.meta li{{margin-bottom:7px}}
  ul.meta b{{color:var(--ink)}}
  .snflogo{{display:block;margin-bottom:18px}}
  footer{{font-family:var(--mono);font-size:12px;color:var(--muted);text-align:center;padding-top:4px}}
  footer a{{color:var(--link);text-decoration:none}}
  /* Phones. The padding is the point: 20px of body and 30px of section on each
     side costs 100px of a 390px screen, which is a third of the width the
     charts and tables have to work with. */
  @media(max-width:600px){{
    body{{padding:20px 12px 60px}}
    section{{padding:18px 14px}}
    h1{{font-size:22px}}
    header p.lede{{font-size:15.5px}}
    .takeaway{{font-size:14px}}
  }}
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
    <span class="chip">2026-07-22 to 07-25</span>
  </div>
</header>

{score_html}

{sci_html}

{pass_html}

{dial_html}

{faq_html}

{h2h_html}

{lift_html}

{local_html}

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
        <li><b>Prices move after the runs do:</b> the runs were billed at the prices listed on 2026-07-24. Three models have been cut since and are re-scored at today's listing (GPT-5.6 Terra 0.40&times;, GPT-5.6 Luna 0.10&times;, GLM 5.2 0.90&times;); three more moved input and output by different amounts, which a single billed total cannot be re-based from, so they stand as billed. GPT-5.6 Sol is unchanged. All prices are the standard endpoint, not the cheaper deferred-latency <code>flex</code> tiers.</li>
        <li><b>Solved</b> = every hidden test passes within the budget: 10 turns and 15 minutes of model time (LLM + doc-tool wait; wall time is not used because it depends on harness concurrency). An <b>attempt is a submission</b>, not a turn, so lookups and extra thinking turns are free and only delivered-and-broken code costs.</li>
        <li><b>Not every requested effort is a distinct setting:</b> providers quietly map some levels onto others, so two neighbouring efforts can be the same configuration. GLM 5.2 is the clearest case: <code>minimal</code>, <code>low</code>, <code>medium</code> and <code>high</code> all spend about 10k output tokens a run and are one effective level, while <code>xhigh</code> (29.6k), <code>max</code> (53.6k) and thinking off (5.0k) are genuinely different. DeepSeek, Hy3 and Gemini flatten the same way. Effort labels in this report are what we <i>requested</i>.</li>
      </ul>
    </div>
    <div>
      <h2>Caveats</h2>
      <ul class="meta">
        <li><b>Unequal depth by design:</b> GLM 5.2 carries the deepest dataset, 993 runs across seven efforts and both conditions, and it anchors the substitution finding. Everything else carries 13 to 120 runs per setting, deepest where the score was noisiest and shallowest where a tier was measured only to rule it out.</li>
        <li><b>Eight cells abandoned:</b> host-sleep and network stalls killed six, one was cut when its batch was stopped by hand, and one Hy3 run was killed at 22m43s after grinding far past the time budget. All count as failures, which matches how their completed sibling runs scored. Time and cost medians exclude them.</li>
        <li><b>MCP backend, tested:</b> the first 3 reps used the hosted api.cairo-coder.com and everything else a self-hosted replica with the same corpus and models. A direct A/B of 39 runs each found identical effectiveness, 38/39 solved on both, so the two are pooled. Only lookup speed differs, about 5&times; faster locally.</li>
        <li><b>How precise any of this is:</b> each model's best setting was run until its score settled to within &plusmn;5 points, which took 2 to 10 passes of the 13 tasks. The widest interval in the table is &plusmn;4.9 and it is printed beside every score. Most adjacent pairs sit under 2 points apart, so read them as ties rather than as an order. GLM's apparent "low beats high" ordering at 3 reps did not survive the extra runs, which is the kind of thing 3 reps will do. The documentation runs are shallower at 2 to 3 passes, so those deltas are the least precise numbers here.</li>
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
    """Four things a screenshot at one width cannot check for us.

    1. The encoding declaration. Garbled symbols reported on 2026-07-25
       ("9A- cheaper", a mangled minus and delta in the models table) were
       mojibake, not missing glyphs: the file is valid UTF-8 but declared no
       charset, so browsers guessed a single-byte codepage. Chromium here
       sniffs UTF-8 correctly, which is exactly why the local render looked
       fine while David's browser did not.
    2. The viewport declaration. Same shape of bug, found the same way: without
       it a phone lays the page out at 980px and scales it down, so the render
       is uniformly tiny and every max-width media query in the stylesheet is
       inert. A desktop screenshot cannot see either symptom.
    3. Every chart inside a scroll container. A bare <svg> at width:100% shrinks
       to whatever the phone gives it, and an 11px axis label arrives at 4px.
    4. ASCII-only chart text. Belt and braces after the same incident: SVG
       chart text renders in whatever mono font the reader has, so symbols are
       drawn as geometry (see the rank arrows) rather than typed.
    """
    if 'charset="utf-8"' not in html[:1024]:
        raise SystemExit(
            'missing <meta charset="utf-8"> in the first 1024 bytes: browsers '
            "would guess the encoding and render multi-byte characters as mojibake"
        )
    if 'name="viewport"' not in html[:1024]:
        raise SystemExit(
            'missing <meta name="viewport"> in the first 1024 bytes: phones would '
            "lay the page out at 980px and scale it down, and none of the "
            "max-width media queries would ever fire"
        )
    # Charts are the SVGs svg_open() writes; the SNF logo is an SVG too and is
    # not a chart, so match on the opening tag svg_open produces rather than on
    # "<svg". The check is that no chart bypassed chart().
    charts = len(re.findall(r'<svg viewBox="0 0 \d+ \d+" role="img"', html))
    wrapped = len(re.findall(r'class="chartwrap[^"]*"><svg viewBox=', html))
    if (unwrapped := charts - wrapped):
        raise SystemExit(
            f"{unwrapped} chart SVG(s) not inside a .chartwrap: on a narrow screen "
            "they would shrink to fit instead of scrolling, and their labels would "
            "render at a few pixels. Wrap the call site in chart()."
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
