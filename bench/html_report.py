"""Generate the visual HTML report from benchmark runs (visual-QA gated).

  uv run python -m bench.html_report [runs.jsonl ...]

Writes results/report.html: a self-contained page (inline CSS + SVG charts,
no JS, no external assets). Publishing to an Artifact is a separate, manual
step — this module never publishes anything.
"""

import statistics
import sys
from pathlib import Path

from . import config
from .report import load_runs
from .sci import SCI_SPEC, leaderboard

SLATE = "#7C8DB0"
CORAL = "#E2653E"
INK = "#1C2230"
MUTED = "#5C6572"
LINE = "#E3E6EC"
GOOD = "#2E9E6B"



def med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else 0


def solve_pct(rs):
    return 100 * sum(r["solved"] for r in rs) / len(rs)


def model_time(r):
    """Seconds spent waiting on remote services (LLM + doc tool). Wall time
    additionally includes local compile/test, which scales with runner
    concurrency and says nothing about the model."""
    return r["llm_time_s"] + (r.get("assist_time_s") or 0)


def group(runs, key):
    out = {}
    for r in runs:
        out.setdefault(key(r), []).append(r)
    return out


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
    for gv in range(y_min + (10 - y_min % 10) % 10, int(y_max) + 1, 10):
        y = sy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - pad_r}" y2="{y:.0f}" stroke="{LINE}"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y:.0f}" font-size="11" fill="{MUTED}" text-anchor="end" dominant-baseline="middle">{gv}%</text>')
    for i, lab in enumerate(x_labels):
        parts.append(f'<text x="{sx(i):.0f}" y="{h - 36}" font-size="12" fill="{INK}" text-anchor="middle">{lab}</text>')
    for name, color, vals in series:
        pts = " ".join(f"{sx(i):.0f},{sy(v):.1f}" for i, v in enumerate(vals))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for i, v in enumerate(vals):
            parts.append(f'<circle cx="{sx(i):.0f}" cy="{sy(v):.1f}" r="4.5" fill="{color}"/>')
            dy = -10 if name == "with MCP" else 16
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



SCI_OPEN_COLOR = "#3D5A96"    # open-weight models
SCI_CLOSED_COLOR = "#9AA3B2"  # closed-weight models


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
    pad_l, pad_r, pad_t, pad_b = 64, 40, 26, 115
    cw = w - pad_l - pad_r
    ch = h - pad_t - pad_b
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
        parts.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bar_w:.1f}" height="{sy(0) - top:.1f}" rx="3" fill="{color}"/>')
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


def mcp_lift_chart(pairs, w=760, h=359):
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
    # their rotated extent is shorter and 130 left a blank band above the legend
    pad_l, pad_r, pad_t, pad_b = 64, 40, 26, 85
    cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(pairs)
    col_w = cw / n
    bar_w = col_w * 0.62
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
            parts.append(f'<text x="{cx:.0f}" y="{top_m - 8:.0f}" font-size="10.5" font-weight="600" fill="{CORAL}" text-anchor="middle">+{mcp - base:.1f}</text>')
        elif mcp is not None:
            # measured, no gain: bar stays at the (better) baseline; the red
            # sub-line quantifies what the tool would cost this model
            if mcp < base:
                parts.append(f'<text x="{cx:.0f}" y="{top_b - 20:.0f}" font-size="11.5" font-weight="600" fill="{INK}" text-anchor="middle">{base:.1f}</text>')
                parts.append(f'<text x="{cx:.0f}" y="{top_b - 8:.0f}" font-size="10.5" fill="{MUTED}" text-anchor="middle">−{base - mcp:.1f}</text>')
            else:
                parts.append(f'<text x="{cx:.0f}" y="{top_b - 8:.0f}" font-size="11.5" font-weight="600" fill="{INK}" text-anchor="middle">{base:.1f}</text>')
        else:
            # not yet measured with the tool: shown for scale, flagged as such
            parts.append(f'<text x="{cx:.0f}" y="{top_b - 20:.0f}" font-size="11.5" font-weight="600" fill="{INK}" text-anchor="middle">{base:.1f}</text>')
            parts.append(f'<text x="{cx:.0f}" y="{top_b - 8:.0f}" font-size="9" fill="{MUTED}" text-anchor="middle">no MCP</text>')
        ly = sy(0) + 12
        # only upward moves are annotated — downward is mostly being overtaken
        move = (
            f' <tspan fill="{GOOD}" font-weight="600">▲{rank_delta}</tspan>'
            if rank_delta > 0 else ""
        )
        parts.append(
            f'<text transform="rotate(-45 {cx:.0f} {ly:.0f})" x="{cx:.0f}" y="{ly:.0f}" '
            f'font-size="11" fill="{INK}" text-anchor="end">{label}{move}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)



def bar_cell(v, vmax, cls, label):
    wpct = max(2, v / vmax * 100)
    return (
        f'<td class="barcell"><div class="barrow"><div class="bar {cls}" '
        f'style="width:{wpct:.0f}%"></div><span class="barlabel">{label}</span></div></td>'
    )


# ---------------------------------------------------------------- build page

# Best open-weight coder per top Chinese lab, at max thinking (label, spec)
ROSTER = [
    ("Moonshot · Kimi K3", "moonshotai/kimi-k3"),
    ("Xiaomi · MiMo-V2.5-Pro", "xiaomi/mimo-v2.5-pro@xhigh"),
    ("DeepSeek · V4-Pro", "deepseek/deepseek-v4-pro@xhigh"),
    ("Tencent · Hy3", "tencent/hy3"),
    ("Z.ai · GLM 5.2", "z-ai/glm-5.2@xhigh"),
    ("MiniMax · M3", "minimax/minimax-m3@xhigh"),
    ("Alibaba · Qwen3.6-27B", "qwen/qwen3.6-27b@xhigh"),
]


def build(all_runs):
    # Does the effort pattern generalize? Small-multiple curves per model.
    FAMILIES = [
        ("GLM 5.2", "z-ai/glm-5.2@", ["disabled", "low", "medium", "high", "xhigh"]),
        ("DeepSeek V4-Pro", "deepseek/deepseek-v4-pro@", ["low", "xhigh"]),
        ("Tencent Hy3", "tencent/hy3@", ["low", "high"]),
        ("MiMo-V2.5-Pro", "xiaomi/mimo-v2.5-pro@", ["low", "xhigh"]),
    ]
    multiples = []
    for name, prefix, tiers in FAMILIES:
        series = []
        for cond, color in [("baseline", SLATE), ("mcp", CORAL)]:
            vals = []
            for t in tiers:
                rs = [r for r in all_runs if r["model"] == prefix + t and r["condition"] == cond]
                vals.append(solve_pct(rs) if rs else 0)
            series.append(("with MCP" if cond == "mcp" else "baseline", color, vals))
        chart = line_chart(tiers, series, annotations=[], w=380, h=230, y_min=60)
        multiples.append(f'<div><h3 style="font-size:13px;margin-bottom:6px">{name}</h3>{chart}</div>')
    generalize_html = f"""
<section>
  <h2>Does the effort pattern generalize? — four labs' effort curves</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline</span><span><span class="key" style="background:var(--mcp)"></span>with MCP</span><span>solve rate, 39 runs per point</span></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">{"".join(multiples)}</div>
  <p class="takeaway">Yes — and the 15-minute model-time budget settles the one apparent exception. <b>"Extra thinking buys no solve-rate gain" holds for DeepSeek</b> (94.9% at both tiers, but the low tier answers ~2.2× faster for ~25% less money) <b>and trivially for MiMo</b> (100% everywhere — knowledge-saturated, effort irrelevant). <b>Tencent Hy3 looked like the counterexample, but its high-tier edge was built on marathon runs</b>: with over-budget solves (some past 40 minutes of thinking) counted as the failures they are, high scores 89.7% vs low's 87.2% — one run apart. What the budget reveals instead is a real MCP lift for Hy3 (87.2%→94.9% at bare/low): the documentation tool converts its over-budget grinds into in-budget solves, exactly what the substitution law predicts. MCP lift appears where reasoning or knowledge falls short — never where the model is already saturated.</p>
</section>"""

    # Full effort curves: every benchmarked thinking tier, baseline only.
    def tier_table(tier_spec_pairs):
        rows = []
        for tier, spec in tier_spec_pairs:
            rs = [r for r in all_runs if r["model"] == spec and r["condition"] == "baseline"]
            if not rs:
                continue
            oneshot = 100 * sum(1 for r in rs if r["solved"] and r["turns"] == 1) / len(rs)
            rows.append(
                f'<tr><td class="task">{tier}</td>'
                + bar_cell(solve_pct(rs), 100, "b", f"{solve_pct(rs):.0f}%")
                + bar_cell(oneshot, 100, "b", f"{oneshot:.0f}%")
                + f'<td class="num">{med([r["turns"] for r in rs]):.0f}</td>'
                f'<td class="num">{med([model_time(r) for r in rs]):.0f}s</td>'
                f'<td class="num">${med([r["cost_usd"] for r in rs]):.4f}</td>'
                f'<td class="num">{med([r["completion_tokens"] for r in rs]):,.0f}</td></tr>'
            )
        return ('<div class="tablewrap"><table class="num"><tr><th>Thinking</th>'
                '<th class="barcell">Solve rate</th><th class="barcell">One-shot</th>'
                '<th>Med. turns</th><th>Med. model time</th><th>Med. cost</th>'
                f'<th>Med. output toks</th></tr>{"".join(rows)}</table></div>')

    SONNET_TIERS = [
        ("off", "anthropic/claude-sonnet-5"),
        ("minimal", "anthropic/claude-sonnet-5@minimal"),
        ("low", "anthropic/claude-sonnet-5@low"),
        ("medium", "anthropic/claude-sonnet-5@medium"),
        ("high", "anthropic/claude-sonnet-5@high"),
    ]
    MIMO_TIERS = [
        ("off", "xiaomi/mimo-v2.5-pro@disabled"),
        ("minimal", "xiaomi/mimo-v2.5-pro@minimal"),
        ("low", "xiaomi/mimo-v2.5-pro@low"),
        ("medium", "xiaomi/mimo-v2.5-pro@medium"),
        ("high", "xiaomi/mimo-v2.5-pro@high"),
        ("xhigh", "xiaomi/mimo-v2.5-pro@xhigh"),
        ("max", "xiaomi/mimo-v2.5-pro@max"),
    ]
    GEMINI_TIERS = [
        ("minimal", "google/gemini-3.6-flash@minimal"),
        ("low", "google/gemini-3.6-flash@low"),
        ("medium", "google/gemini-3.6-flash@medium"),
        ("high", "google/gemini-3.6-flash@high"),
        ("xhigh", "google/gemini-3.6-flash@xhigh"),
        ("max", "google/gemini-3.6-flash@max"),
    ]
    LUNA_TIERS = [
        ("off", "openai/gpt-5.6-luna@disabled"),
        ("minimal", "openai/gpt-5.6-luna@minimal"),
        ("low", "openai/gpt-5.6-luna@low"),
        ("medium", "openai/gpt-5.6-luna@medium"),
        ("high", "openai/gpt-5.6-luna@high"),
        ("xhigh", "openai/gpt-5.6-luna@xhigh"),
        ("max", "openai/gpt-5.6-luna@max"),
        ("pro", "openai/gpt-5.6-luna-pro"),
    ]
    GROK_TIERS = [
        ("minimal", "x-ai/grok-4.5@minimal"),
        ("low", "x-ai/grok-4.5@low"),
        ("high", "x-ai/grok-4.5@high"),
        ("xhigh", "x-ai/grok-4.5@xhigh"),
        ("max", "x-ai/grok-4.5@max"),
    ]
    FABLE_TIERS = [
        ("minimal", "anthropic/claude-fable-5@minimal"),
        ("low", "anthropic/claude-fable-5@low"),
        ("high", "anthropic/claude-fable-5@high"),
        ("xhigh", "anthropic/claude-fable-5@xhigh"),
        ("max", "anthropic/claude-fable-5@max"),
    ]
    OPUS_TIERS = [
        ("off", "anthropic/claude-opus-4.8@disabled"),
        ("low", "anthropic/claude-opus-4.8@low"),
        ("high", "anthropic/claude-opus-4.8@high"),
        ("xhigh", "anthropic/claude-opus-4.8@xhigh"),
        ("max", "anthropic/claude-opus-4.8@max"),
    ]
    HAIKU_TIERS = [
        ("off", "anthropic/claude-haiku-4.5"),
        ("low", "anthropic/claude-haiku-4.5@low"),
        ("high", "anthropic/claude-haiku-4.5@high"),
        ("xhigh", "anthropic/claude-haiku-4.5@xhigh"),
        ("max", "anthropic/claude-haiku-4.5@max"),
    ]
    SOL_TIERS = [
        ("off", "openai/gpt-5.6-sol@disabled"),
        ("low", "openai/gpt-5.6-sol@low"),
        ("high", "openai/gpt-5.6-sol@high"),
        ("xhigh", "openai/gpt-5.6-sol@xhigh"),
        ("max", "openai/gpt-5.6-sol@max"),
    ]
    TERRA_TIERS = [
        ("off", "openai/gpt-5.6-terra@disabled"),
        ("minimal", "openai/gpt-5.6-terra@minimal"),
        ("low", "openai/gpt-5.6-terra@low"),
        ("medium", "openai/gpt-5.6-terra@medium"),
        ("high", "openai/gpt-5.6-terra@high"),
        ("xhigh", "openai/gpt-5.6-terra@xhigh"),
        ("max", "openai/gpt-5.6-terra@max"),
        ("pro", "openai/gpt-5.6-terra-pro"),
    ]
    QWEN_TIERS = [
        ("high", "qwen/qwen3.6-27b@high"),
        ("xhigh", "qwen/qwen3.6-27b@xhigh"),
        ("max", "qwen/qwen3.6-27b@max"),
    ]
    MINIMAX_TIERS = [
        ("minimal", "minimax/minimax-m3@minimal"),
        ("low", "minimax/minimax-m3@low"),
        ("medium", "minimax/minimax-m3@medium"),
        ("high", "minimax/minimax-m3@high"),
        ("xhigh", "minimax/minimax-m3@xhigh"),
        ("max", "minimax/minimax-m3@max"),
    ]
    HY3_TIERS = [
        ("off", "tencent/hy3@disabled"),
        ("minimal", "tencent/hy3@minimal"),
        ("low", "tencent/hy3@low"),
        ("medium", "tencent/hy3@medium"),
        ("high", "tencent/hy3@high"),
        ("xhigh", "tencent/hy3@xhigh"),
        ("max", "tencent/hy3@max"),
    ]
    GLM_TIERS = [
        ("off", "z-ai/glm-5.2@disabled"),
        ("minimal", "z-ai/glm-5.2@minimal"),
        ("low", "z-ai/glm-5.2@low"),
        ("medium", "z-ai/glm-5.2@medium"),
        ("high", "z-ai/glm-5.2@high"),
        ("xhigh", "z-ai/glm-5.2@xhigh"),
        ("max", "z-ai/glm-5.2@max"),
    ]
    DEEPSEEK_TIERS = [
        ("off", "deepseek/deepseek-v4-pro@disabled"),
        ("minimal", "deepseek/deepseek-v4-pro@minimal"),
        ("low", "deepseek/deepseek-v4-pro@low"),
        ("medium", "deepseek/deepseek-v4-pro@medium"),
        ("high", "deepseek/deepseek-v4-pro@high"),
        ("xhigh", "deepseek/deepseek-v4-pro@xhigh"),
    ]
    effort_curve_takeaway = (
        "<b>For both leaders the thinking knob buys nothing on this suite — including switching it off.</b> "
        "Sonnet 5 solves 195/195 at identical cost (~$0.024) and output (~1,700 tokens) at every tier because "
        "its thinking is adaptive: granted any budget, it declines to spend reasoning tokens on tasks it already "
        "knows. </p><p class='takeaway'>MiMo-V2.5-Pro solves 273/273 across all seven tiers with equally flat cost (~$0.005) and output "
        "(~1,500 tokens) — knowledge saturation again, this time in an open-weight model with a hard off switch. "
        "MiMo's apparent latency spread (19s at xhigh vs ~45s at the tiers benchmarked in a later batch) is a "
        "provider artifact, not an effort effect: the earlier batch was served at ~81 tok/s, the later at ~33 tok/s, "
        "and within a batch the tiers are flat. One-shot rates wobble without a monotone trend (MiMo 18–41%, "
        "Sonnet 46–67%) — binomial noise at n=39. <b>Gemini 3.6 Flash is the third pattern: an obedient thinker.</b> "
        "It spends whatever budget it is granted (2k→7.7k output tokens, $0.023→$0.061 per task, minimal→max) and "
        "the spend does buy something — one-shot rate climbs steadily from 10% to 46% — but not solves: it is at "
        "100% from <code>low</code> upward regardless. </p><p class='takeaway'><b>GPT-5.6 Luna is the fourth pattern — and the first "
        "closed model that is NOT Cairo-saturated</b>: its solve rate genuinely climbs with the dial (79.5% with "
        "thinking off → 100% at <code>max</code>), it never one-shots at any tier (median 3–4 compiler round-trips), "
        "and its <code>pro</code> serving mode burns 14.5k output tokens and ~$0.11 per task to score <i>below</i> "
        "<code>max</code>. </p><p class='takeaway'><b>Terra, Luna's 2.5×-price sibling, shows what that money buys: knowledge, not habits.</b> "
        "Its thinking-off correctness jumps to 89.7% (Luna: 79.5%) and its curve flattens to noise (only "
        "<code>medium</code> reaches 100%), but it still never one-shots and its <code>pro</code> mode is again "
        "strictly dominated ($0.21/task for less than <code>max</code>). Net effect on the index: +0.6 points over "
        "Luna. </p><p class='takeaway'>Completing the open-model ladders sharpened the split. <b>DeepSeek V4-Pro turns out "
        "not to need its thinking at all</b>: ~95–97% at every tier including off, where it runs 2–4× faster and "
        "cheaper — the off tier jumps it to #5 on the index. <b>Hy3's ladder is erratic</b>: thinking off "
        "collapses it (87%→67%, the GLM pattern), but the dial isn't even monotone — <code>minimal</code> reasons "
        "longer than <code>medium</code> (303s vs 242s median) and both drown in over-budget grinds; "
        "<code>low</code> stays its sweet spot. <b>MiniMax M3 genuinely needs its thinking</b> (87%→74% descending "
        "the ladder) and its off switch is fake — the API accepts <code>disabled</code> and reasons anyway, so "
        "that pseudo-variant is excluded. </p><p class='takeaway'><b>Haiku 4.5 adds a fifth pattern — the overthinker — and the dataset's first inverted "
        "curve</b>: thinking off solves 88.9% at 29s/$0.05, while <code>high</code> collapses to 65.6% at "
        "102s/$0.17, burning ~18k output tokens spiraling through full 10-turn slogs. Granting the small model a "
        "big budget makes it strictly worse on every axis; per the bracket protocol its ladder was not extended "
        "further upward. </p><p class='takeaway'><b>Opus 4.8 completes the Anthropic ladder at the opposite extreme</b>: all three bracket "
        "tiers are indistinguishable at 100% solve, ~15s, ~1,400 tokens — its adaptive thinking simply doesn't "
        "engage on tasks it has mastered — and at <code>high</code> it one-shots the entire suite, 26 for 26. "
        "One family, four fates for the same dial: the small model overthinks itself into failure, the mid model "
        "ignores the dial, the big models transcend it — <b>Fable 5's dial is inert until <code>max</code></b> "
        "(<code>minimal</code> and <code>high</code> return byte-identical cost/token medians at the adaptive "
        "floor; <code>max</code> finally engages real thinking for +4pt one-shot at 3× the cost), and its 78-run "
        "bracket produced zero errors, zero tiebreaks, and zero refusals.</p><p class='takeaway'><b>GPT-5.6 Sol completes the rival "
        "ladder</b>: full "
        "correctness saturation at flagship scale (100% at every bracket tier), a one-shot habit that finally "
        "cracks but only to 12–23%, and an interior best tier (<code>low</code>) — the first bracket where "
        "neither edge won, so the ladder was not extended in either direction.</p><p class='takeaway'>The practical rule survives every pattern: run the cheapest tier that holds correctness; the thinking dial buys solve rate only where knowledge runs out (GLM, Hy3, MiniMax, Qwen — and Luna)."
    )
    sonnet_html = f"""
<section>
  <h2>Full effort curves — what does the thinking knob actually buy?</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline only (no documentation tool)</span><span>39 runs per tier; times are model latency</span></div>
  <h3 style="font-size:13px;margin-bottom:6px">Sonnet 5 (closed weights, adaptive thinking)</h3>
  {tier_table(SONNET_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">MiMo-V2.5-Pro (open weights)</h3>
  {tier_table(MIMO_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">Gemini 3.6 Flash (closed weights, thinking mandatory — no off tier)</h3>
  {tier_table(GEMINI_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">GPT-5.6 Luna (closed weights; <code>pro</code> is the same model in reasoning.mode=pro)</h3>
  {tier_table(LUNA_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">Grok 4.5 (closed weights; thinking mandatory — no off tier)</h3>
  {tier_table(GROK_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">Fable 5 (closed weights; thinking mandatory — no off tier. Disclosure: this model also operates the harness; measurement is submissions + hidden tests only)</h3>
  {tier_table(FABLE_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">Opus 4.8 (closed weights; Anthropic's top tier — bracket tiers, bare spec skipped as adaptive/unnameable)</h3>
  {tier_table(OPUS_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">Haiku 4.5 (closed weights; Sonnet 5's small sibling — bracket tiers, extended only if an edge wins)</h3>
  {tier_table(HAIKU_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">GPT-5.6 Sol (closed weights; the flagship — bracket tiers)</h3>
  {tier_table(SOL_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">GPT-5.6 Terra (closed weights; Luna's mid-tier sibling, <code>pro</code> = reasoning.mode=pro)</h3>
  {tier_table(TERRA_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">MiniMax M3 (open weights; <code>disabled</code> accepted but ignored — omitted)</h3>
  {tier_table(MINIMAX_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">Tencent Hy3 (open weights; bare spec ≡ <code>high</code>)</h3>
  {tier_table(HY3_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">GLM 5.2 (open weights; the pilot model — deepest per-effort dataset)</h3>
  {tier_table(GLM_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">Qwen3.6-27B (open weights; the knowledge-floor case — upper tiers only)</h3>
  {tier_table(QWEN_TIERS)}
  <h3 style="font-size:13px;margin:18px 0 6px">DeepSeek V4-Pro (open weights)</h3>
  {tier_table(DEEPSEEK_TIERS)}
  <p class="takeaway">{effort_curve_takeaway}</p>
</section>"""

    # Lab roster: best open-weight coder per lab at max thinking
    roster_rows, roster_stats = [], {}
    for label, spec in ROSTER:
        rs = [r for r in all_runs if r["model"] == spec]
        if not rs:
            continue
        st = {}
        for c in ["baseline", "mcp"]:
            crs = [r for r in rs if r["condition"] == c]
            st[c] = {
                "n": len(crs),
                "solve": solve_pct(crs),
                "wall": med([model_time(r) for r in crs]),
                "cost": med([r["cost_usd"] for r in crs]),
                "assists": sum(r["n_assist_calls"] for r in crs) / len(crs),
            }
        roster_stats[label] = st
    for label, st in sorted(roster_stats.items(), key=lambda kv: -kv[1]["baseline"]["solve"]):
        b, m = st["baseline"], st["mcp"]
        delta = m["solve"] - b["solve"]
        roster_rows.append(
            f'<tr class="taskrow"><td class="task" rowspan="2">{label}</td>'
            f'<td><span class="cond b">baseline</span></td>'
            + bar_cell(b["solve"], 100, "b", f"{b['solve']:.0f}%")
            + f'<td class="num">{b["wall"]:.0f}s</td><td class="num">${b["cost"]:.3f}</td>'
            f'<td class="num" rowspan="2">{"+" if delta >= 0 else "−"}{abs(delta):.0f}pt</td>'
            f'<td class="num" rowspan="2">{m["assists"]:.1f}</td></tr>'
            f'<tr class="taskrow2"><td><span class="cond m">mcp</span></td>'
            + bar_cell(m["solve"], 100, "m", f"{m['solve']:.0f}%")
            + f'<td class="num">{m["wall"]:.0f}s</td><td class="num">${m["cost"]:.3f}</td></tr>'
        )
    k3_html = f"""
<section>
  <h2>The lab roster — best open-weight coder per lab, max thinking</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline</span><span><span class="key" style="background:var(--mcp)"></span>with MCP</span><span>39 runs per condition per model</span></div>
  <div class="tablewrap"><table class="num"><tr><th>Lab · model</th><th>Cond.</th><th class="barcell">Solve rate</th><th>Med. model time</th><th>Med. cost</th><th>MCP lift</th><th>Assists/run</th></tr>{"".join(roster_rows)}</table></div>
  <p class="takeaway">The knowledge-gap law holds across seven labs: <b>MCP lift tracks baseline weakness</b> — zero for the saturating frontier (Kimi K3, MiMo), +5pt in the 95% tier (DeepSeek, GLM), +8pt for Hy3, +18pt for the weakest entrant (Qwen3.6-27B, 23%→41%). <b>Xiaomi's MiMo-V2.5-Pro is the efficiency standout</b>: 100% baseline at ~19s and ~$0.004 per task — 14× cheaper and 5× faster than Kimi K3 for the same solve rate. Qwen3.6-27B, despite strong general-coding benchmarks, collapses on Cairo — the clearest demonstration that language-specific knowledge, not coding skill, is what the MCP substitutes for.</p>
</section>"""

    # Starknet Coding Index leaderboard (baseline; reusable via MODEL_REGISTRY)
    sci_rows = leaderboard(all_runs)
    a = SCI_SPEC["anchors"]
    w_ = SCI_SPEC["weights"]

    # Chart 2: best-without vs best-with the MCP, per model. Each condition
    # picks its own best thinking variant (deployment framing), so labels
    # carry no effort. Models without MCP runs are omitted, not shown empty.
    mcp_rows = {r["label"]: r for r in leaderboard(all_runs, condition="mcp")}
    lift_pairs = [
        (r["label"], r["sci"], mcp_rows[r["label"]]["sci"] if r["label"] in mcp_rows else None,
         r["open_weight"])
        for r in sci_rows
    ]
    # order by the top of the stack (best-with-tool where it gains, baseline
    # otherwise) so the with-MCP ranking reads left to right; annotate each
    # bar with how many places it moved vs the baseline-only ranking
    base_rank = {r["label"]: i for i, r in enumerate(sci_rows)}
    lift_pairs.sort(key=lambda p: max(p[1], p[2] or p[1]), reverse=True)
    lift_pairs = [
        (label, base, mcp, open_w, base_rank[label] - i)
        for i, (label, base, mcp, open_w) in enumerate(lift_pairs)
    ]
    lift_html = f"""
<section>
  <h2>What does the Cairo Coder MCP add? <span style="text-transform:none">(best config without vs with)</span></h2>
  <p class="takeaway" style="margin:0 0 10px">Same index, second question: each model's <b>best configuration without the tool</b> (solid bar) versus its <b>best configuration with it</b> — possibly a different thinking level, so bars carry no effort label.</p>
  {mcp_lift_chart(lift_pairs)}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>best without MCP (open weights)</span><span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>best without MCP (closed weights)</span><span><span class="key" style="background:{CORAL};border-radius:2px"></span>added by MCP</span></div>
</section>"""
    sci_html = f"""
<section>
  <h2>Starknet Coding Index <span style="text-transform:none">(baseline, no assistance)</span></h2>
  <p class="takeaway" style="margin:0 0 10px">One number per model for "how good is this LLM at writing Starknet smart contracts today" — each model runs the full task suite alone, at its <b>best thinking variant</b> (labeled in parentheses), within a budget of 10 turns and 15 minutes of model time per task.</p>
  {sci_bar_chart(sci_rows)}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>open weights</span><span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>closed weights</span></div>
</section>"""
    # score definition applies to both charts above, so it gets its own section
    score_html = f"""
<section>
  <h2>How the score is built</h2>
  <ul class="meta" style="margin-bottom:8px">
    <li><b>Correctness ({w_["correct"]:.0%})</b> — average fraction of hidden tests passed per task. Half the index: a fast, cheap model that writes wrong contracts cannot rank well.</li>
    <li><b>One-shot rate ({w_["oneshot"]:.0%})</b> — share of runs solved on the very first submission, no compiler feedback needed.</li>
    <li><b>Speed ({w_["speed"]:.0%})</b> and <b>cost ({w_["cost"]:.0%})</b> — median model latency (time spent waiting on the model's API, excluding this harness's local compile/test) and median $ per task, scored 100→0 on fixed log scales ({a["speed"][0]}s→{a["speed"][1]}s, ${a["cost"][0]}→${a["cost"][1]}).</li>
    <li><b>Token efficiency ({w_["tokens"]:.0%})</b> — median output tokens per task ({a["tokens"][0] // 1000}k→{a["tokens"][1] // 1000}k), penalizing verbosity independent of price.</li>
  </ul>
  <p class="takeaway" style="margin:0">Runs over the 15-minute model-time budget count as failures. Models with one fixed mode show that mode (Kimi K3 always runs at <code>max</code>). 26–130 runs per entry. The scales are fixed, not relative — adding a new model later never changes an existing score.</p>
</section>"""

    findings_html = """
<section class="findings">
  <h2>Findings</h2>
  <div class="finding"><h3><span class="tag win">law</span>The tool's value tracks the knowledge gap — in any weight class</h3>
  <p>Documentation lift lines up with baseline weakness across all thirteen measured models: +12.1 for the weakest entrant (Qwen3.6-27B), +4.3 for Haiku 4.5 (the first closed-model gain), fading to zero at the saturated top (MiMo, K3, Opus-class models).</p>
  <p>Two refinements from the closed models: the law applies per <i>variant</i> (Terra gains only at its unsaturated <code>off</code> tier), and saturated models can still gain a little when lookups shorten their repair loops (Gemini +1.1, Sol +0.6).</p></div>
  <div class="finding"><h3><span class="tag win">thinking</span>The thinking dial rarely buys correctness — run the cheapest tier that holds it</h3>
  <p>Five patterns across fifteen models: adaptive thinkers that ignore the dial (Sonnet 5, Opus 4.8, Fable 5), an indifferent one (MiMo — 100% at all seven tiers), an obedient one that spends budget without needing it (Gemini), real curves where thinking buys solves (GLM, Luna, MiniMax), and one inverted curve (Haiku overthinks itself from 89% to 66%). In twelve of fifteen models the index-best variant is the cheapest tier that holds correctness.</p></div>
  <div class="finding"><h3><span class="tag cost">habits</span>One-shot ability is architectural — documentation can't buy it</h3>
  <p>OpenAI's entire ladder iterates against the compiler at every scale and price (0–23% one-shot from Luna to Sol), while Anthropic's flagships one-shot nearly everything (96–100%). The tool never changed a model's one-shot rate: GPT-5.6 Luna knows Cairo (97% correct) yet measured −1.4 with docs — a habit is not a knowledge gap.</p>
  <p>Tool discipline is a habit too, and the costliest one to lack: offered the same docs, Anthropic's flagships never called them once (−1.2 to −1.9, pure schema overhead) while Grok 4.5 dutifully consulted them about once per run it didn't need — worth −13.1, the largest penalty in the study.</p></div>
  <div class="finding"><h3><span class="tag cost">economics</span>Pro-style serving modes are strictly dominated</h3>
  <p>Both measured pro modes (luna-pro, terra-pro) cost 2–3× their model's <code>max</code> tier and scored below it. Neither ever produced the best configuration of its model; sol-pro was not funded on that record.</p></div>
  <div class="finding"><h3><span class="tag win">effectiveness</span>In the GLM study, baseline failures are training-data lag — and the tool fixes exactly that</h3>
  <p>GLM 5.2's failed baseline runs get stuck on <em>current</em> Cairo idioms — most often the storage API, writing pre-2024 <code>Map.read(key)</code> instead of today's <code>Map.entry(key).read()</code> — and burn the whole 10-turn budget against the compiler. One documentation lookup resolves it; net effect was lower median cost at 4 of 5 effort settings, with lookups rising as thinking budget fell (~0.5/run at high effort, ~1.8/run with thinking off).</p></div>
  <div class="finding"><h3><span class="tag warn">caveat</span>Cairo Coder confabulates outside its index</h3>
  <p>Asked about a token standard we invented ("STRK77"), the service returned a complete, confident, fabricated Cairo interface. Within its indexed corpus it's accurate; agents consuming it get no signal when a query falls outside coverage. Worth fixing upstream.</p></div>
</section>"""

    return f"""<title>Starknet Coding Index — Cairo Coder Benchmark</title>
<meta name="description" content="Which LLM writes Starknet contracts best, and what does documentation access add? {len(all_runs)} agentic runs, 16 models: Grok 4.5 leads the index at 90.8; the Cairo Coder MCP pays exactly where a model's Cairo knowledge runs out.">
<style>
  :root{{
    --ground:#F6F7F9; --panel:#FFFFFF; --ink:{INK}; --muted:{MUTED};
    --line:{LINE}; --baseline:{SLATE}; --mcp:{CORAL}; --good:{GOOD}; --bad:#B03A3A;
    --mono:"SF Mono","Cascadia Code","JetBrains Mono",Consolas,ui-monospace,monospace;
    --sans:"Avenir Next",-apple-system,"Segoe UI",Roboto,sans-serif;
  }}
  *{{box-sizing:border-box}}
  body{{background:var(--ground);color:var(--ink);font-family:var(--sans);margin:0;padding:40px 20px 80px;line-height:1.55}}
  main{{max-width:980px;margin:0 auto;display:flex;flex-direction:column;gap:26px}}
  /* no text-wrap:balance anywhere: it hangs some Chromium builds on these headings */
  h1,h2,h3{{font-family:var(--mono);font-weight:600;margin:0}}
  h1{{font-size:27px;letter-spacing:-.02em}}
  h2{{font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:16px}}
  .num{{font-variant-numeric:tabular-nums}}
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
  table{{border-collapse:collapse;width:100%;min-width:640px}}
  th{{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:500;text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}}
  td{{padding:7px 10px;border-bottom:1px solid var(--line);font-size:13.5px;vertical-align:middle}}
  td.task{{font-family:var(--mono);font-size:12.5px;white-space:nowrap}}
  .cond{{font-family:var(--mono);font-size:11px}}
  .cond.b{{color:var(--baseline)}} .cond.m{{color:var(--mcp)}}
  .barcell{{min-width:170px}}
  .bar{{height:9px;border-radius:2px}}
  .bar.b{{background:var(--baseline)}} .bar.m{{background:var(--mcp)}}
  .barrow{{display:flex;align-items:center}}
  .barlabel{{font-family:var(--mono);font-size:11px;color:var(--muted);margin-left:8px;white-space:nowrap}}
  .assists{{display:flex;gap:22px;font-family:var(--mono);font-size:12.5px;color:var(--muted);margin-top:6px;flex-wrap:wrap}}
  .findings{{display:flex;flex-direction:column;gap:18px}}
  .finding h3{{font-size:14px;margin-bottom:4px}}
  .finding p{{margin:0;font-size:14px}}
  .tag{{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;padding:2px 7px;border-radius:3px;margin-right:8px;vertical-align:1px}}
  .tag.win{{background:#E7F4EE;color:var(--good)}} .tag.cost{{background:#FBEDE8;color:var(--mcp)}} .tag.warn{{background:#F7EFDC;color:#9A7013}}
  code{{font-family:var(--mono);font-size:.92em;background:var(--ground);border:1px solid var(--line);border-radius:3px;padding:1px 5px}}
  .split{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}
  @media(max-width:760px){{.split{{grid-template-columns:1fr}}}}
  ul.meta{{margin:0;padding-left:20px;font-size:13.5px;color:var(--muted)}}
  ul.meta li{{margin-bottom:7px}}
  ul.meta b{{color:var(--ink)}}
</style>
<main>
<header>
  <h1>The Starknet Coding Index</h1>
  <p class="lede">Sixteen models — the best open-weight coders from seven labs and the current closed models from Anthropic, Google, OpenAI, and xAI — each ran the same {len({r["task"] for r in all_runs if r["task"] != "fake"})} hidden-test smart-contract tasks at every useful thinking setting, with and without the <b>Cairo Coder</b> documentation tool. Two headlines: <b>Grok 4.5 leads the index at 90.8</b>, a statistical tie with Opus 4.8 decided by economics; and <b>the tool's value tracks the model's Cairo knowledge gap</b> — from +23 index points for the weakest entrant to nothing at the saturated top.</p>
  <div class="chips">
    <span class="chip">models <b>16</b></span>
    <span class="chip">labs <b>11</b></span>
    <span class="chip">runs <b>{len(all_runs)}</b></span>
    <span class="chip">hidden tests <b>106</b></span>
    <span class="chip">total LLM spend <b>${sum(r["cost_usd"] or 0 for r in all_runs):.0f}</b></span>
    <span class="chip">2026-07-22 → 24</span>
  </div>
</header>

{sci_html}

{lift_html}

{score_html}

{findings_html}

{sonnet_html}

{generalize_html}

{k3_html}

<section>
  <div class="split">
    <div>
      <h2>Methodology</h2>
      <ul class="meta">
        <li><b>Harness:</b> agentic repair loop, max 10 assistant turns. The model submits <code>src/lib.cairo</code> via a <code>submit</code> tool; the harness runs <code>scarb build</code> + <code>snforge test</code> against hidden tests and returns the output. Conditions are identical except the MCP condition also exposes <code>assist_with_cairo</code>, replicated exactly from <code>@kasarlabs/cairo-coder-mcp</code> v0.2.5.</li>
        <li><b>Tasks:</b> 13 hand-written Starknet contracts (4 easy / 5 medium / 4 hard incl. a SNIP-6 account and a custom component); every reference solution passes 100% of its tests, every stub fails.</li>
        <li><b>Model:</b> z-ai/glm-5.2 via OpenRouter, throughput-sorted routing, provider-default temperature; efforts via the unified reasoning parameter (<code>disabled</code> = <code>enabled:false</code>). Costs are OpenRouter-reported.</li>
        <li><b>Solved</b> = every hidden test passes within the budget: 10 turns and 15 minutes of model time (LLM + doc-tool wait; wall time is not used — it depends on harness concurrency). 2–3 reps per cell: a third rep breaks 1–1 ties (entries benchmarked before 2026-07-24 used a fixed 3).</li>
      </ul>
    </div>
    <div>
      <h2>Caveats</h2>
      <ul class="meta">
        <li><b>Unequal depth by design:</b> GLM 5.2 carries the deepest dataset (~1,300 runs across five efforts and both conditions, from the original pilot study) — it anchors the substitution-law finding and the n=130 statistics; newer entrants carry 26–39 runs per variant. GLM runs predate the streaming and reasoning-round-trip harness fixes, which its own data shows it did not need.</li>
        <li><b>Six cells abandoned, one batch truncated:</b> host-sleep/network stalls made 5 qwen/minimax baseline cells unrecoverable, and 1 qwen@high cell was cut when its batch was stopped manually; all are counted as failures, consistent with their completed sibling reps. The stopped batch also skipped its tiebreaker pass, leaving 11 qwen high/max cells at 2 disagreeing reps (scored as the 2-rep mean). Time/cost medians exclude abandoned cells.</li>
        <li><b>MCP backend, tested:</b> @high's first 3 reps used the hosted api.cairo-coder.com; everything else used a self-hosted replica (same corpus re-ingested, same embedding/generation models). A direct A/B (39 runs each, identical tasks/effort) found <b>identical effectiveness</b> — 38/39 solved on both, same turn counts — so hosted-index staleness did not skew results; only lookup speed differs (~5× faster locally). Data is pooled.</li>
        <li><b>Statistics:</b> confirmation batches raised low/medium/high baseline cells to n=130 (others n=39). The apparent "low beats high" ordering at 3 reps did not survive: low ≈ medium (p=0.83), high trails non-significantly (p=0.09). Solve-rate claims here carry Wilson 95% CIs of roughly ±5pt at n=130 and ±9pt at n=39.</li>
        <li><b>Hosted sunset:</b> api.cairo-coder.com shuts down 2026-07-31; the replica replaces it for reruns.</li>
      </ul>
    </div>
  </div>
</section>
</main>
"""


def main():
    paths = [Path(p) for p in sys.argv[1:]] or [config.RUNS_DIR / "main.jsonl"]
    runs = load_runs(paths)
    if not runs:
        print("no runs found")
        sys.exit(1)
    out = config.RESULTS_DIR / "report.html"
    out.write_text(build(runs))
    print(f"{len(runs)} runs -> {out}")


if __name__ == "__main__":
    main()
