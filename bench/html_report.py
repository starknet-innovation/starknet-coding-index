"""Generate the visual HTML report from benchmark runs (visual-QA gated).

  uv run python -m bench.html_report [runs.jsonl ...]

Writes results/report.html: a self-contained page (inline CSS + SVG charts,
no JS, no external assets). Publishing to an Artifact is a separate, manual
step — this module never publishes anything.
"""

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




def build(all_runs):
    # Does the effort pattern generalize? Small-multiple curves — every model
    # with at least two thinking tiers measured in BOTH conditions qualifies;
    # per-family y_min because Qwen lives far below everyone else's floor.
    FAMILIES = [
        ("GLM 5.2", "z-ai/glm-5.2@", ["disabled", "low", "medium", "high", "xhigh"], 60),
        ("Tencent Hy3", "tencent/hy3@", ["disabled", "low", "medium", "high", "xhigh"], 60),
        ("MiniMax M3", "minimax/minimax-m3@", ["minimal", "low", "medium", "high", "xhigh", "max"], 60),
        ("DeepSeek V4-Pro", "deepseek/deepseek-v4-pro@", ["disabled", "minimal", "low", "medium", "high", "xhigh"], 60),
        ("MiMo-V2.5-Pro", "xiaomi/mimo-v2.5-pro@", ["disabled", "minimal", "low", "medium", "high", "xhigh", "max"], 60),
        ("Qwen3.6-27B", "qwen/qwen3.6-27b@", ["high", "xhigh", "max"], 0),
    ]
    multiples = []
    for name, prefix, tiers, y_min in FAMILIES:
        series = []
        for cond, color in [("baseline", SLATE), ("mcp", CORAL)]:
            vals = []
            for t in tiers:
                rs = [r for r in all_runs if r["model"] == prefix + t and r["condition"] == cond]
                vals.append(solve_pct(rs) if rs else 0)
            series.append(("with MCP" if cond == "mcp" else "baseline", color, vals))
        labels = ["off" if t == "disabled" else t for t in tiers]
        chart = line_chart(labels, series, annotations=[], w=380, h=230, y_min=y_min)
        multiples.append(f'<div><h3 style="font-size:13px;margin-bottom:6px">{name}</h3>{chart}</div>')
    generalize_html = f"""
<section>
  <h2>Does the effort pattern generalize?</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline</span><span><span class="key" style="background:var(--mcp)"></span>with MCP</span><span>solve rate, 26–147 runs per point</span></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:18px">{"".join(multiples)}</div>
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
            "oneshot": 100 * sum(1 for r in rs if r["solved"] and r["turns"] == 1) / len(rs),
            "time": med([r["llm_time_s"] + (r.get("assist_time_s") or 0) for r in rs]),
            "cost": med([r["cost_usd"] for r in rs if r["cost_usd"] is not None]),
            "tokens": med([r["completion_tokens"] for r in rs if r["completion_tokens"]]),
            # attempts = assistant turns used; tasks are tiered by id prefix
            **{f"turns_{tier}": med([r["turns"] for r in rs if r["task"].startswith(tier)])
               for tier in ("e", "m", "h")},
        }

    sa, sb = h2h_stats(best_closed["spec"]), h2h_stats(best_open["spec"])
    pct = lambda v: f"{v:.0f}%"
    attempts = lambda v: f"{v:g}"
    h2h_metrics = [
        ("solve rate", sa["solve"], sb["solve"], pct),
        ("one-shot rate", sa["oneshot"], sb["oneshot"], pct),
        ("med. attempts — easy", sa["turns_e"], sb["turns_e"], attempts),
        ("med. attempts — medium", sa["turns_m"], sb["turns_m"], attempts),
        ("med. attempts — hard", sa["turns_h"], sb["turns_h"], attempts),
        ("med. model time", sa["time"], sb["time"], lambda v: f"{v:.0f}s"),
        ("med. cost / task", sa["cost"], sb["cost"], lambda v: f"${v:.4f}"),
        ("med. output tokens", sa["tokens"], sb["tokens"], lambda v: f"{v:,.0f}"),
    ]
    h2h_html = f"""
<section>
  <h2>Head to head — best closed vs best open weights</h2>
  <p class="takeaway" style="margin:0 0 14px">The ranking's two champions — <b>{best_closed["label"]} ({best_closed["variant"]})</b>, {best_closed["lab"]}, and <b>{best_open["label"]} ({best_open["variant"]})</b>, {best_open["lab"]} — both solve every task; the gap is in <i>how</i>. Baseline condition, {sa["n"]} and {sb["n"]} runs.</p>
  {head_to_head_chart(h2h_metrics)}
  <div class="legend legend-bottom"><span><span class="key" style="background:{SCI_CLOSED_COLOR};border-radius:2px"></span>{best_closed["label"]} ({best_closed["variant"]}) — closed</span><span><span class="key" style="background:{SCI_OPEN_COLOR};border-radius:2px"></span>{best_open["label"]} ({best_open["variant"]}) — open</span><span>bars scaled per row; all but solve &amp; one-shot: lower is better</span></div>
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

{score_html}

{sci_html}

{h2h_html}

{lift_html}

{findings_html}

{generalize_html}

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
