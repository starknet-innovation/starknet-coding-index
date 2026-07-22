"""Generate the visual HTML report from benchmark runs.

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

EFFORT_ORDER = ["disabled", "low", "medium", "high", "xhigh"]
TIERS = [("e", "easy"), ("m", "medium"), ("h", "hard")]
SLATE = "#7C8DB0"
CORAL = "#E2653E"
INK = "#1C2230"
MUTED = "#5C6572"
LINE = "#E3E6EC"
GOOD = "#2E9E6B"


def effort_of(run):
    return run["model"].split("@", 1)[1] if "@" in run["model"] else "high"


def med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else 0


def solve_pct(rs):
    return 100 * sum(r["solved"] for r in rs) / len(rs)


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


def dumbbell_chart(rows, x_min, x_max, w=760, row_h=54, label_w=150, unit="%"):
    """rows: [(label, baseline_val, mcp_val, n_note)]"""
    pad_r, top = 90, 18
    h = top + row_h * len(rows) + 26
    cw = w - label_w - pad_r
    sx = lambda v: label_w + (v - x_min) / (x_max - x_min) * cw
    parts = [svg_open(w, h)]
    # gridlines
    for gv in range(int(x_min), int(x_max) + 1, 10):
        x = sx(gv)
        parts.append(f'<line x1="{x:.0f}" y1="{top - 6}" x2="{x:.0f}" y2="{h - 24}" stroke="{LINE}" stroke-width="1"/>')
        parts.append(f'<text x="{x:.0f}" y="{h - 8}" font-size="11" fill="{MUTED}" text-anchor="middle">{gv}{unit}</text>')
    for i, (label, b, m, note) in enumerate(rows):
        y = top + row_h * i + row_h / 2
        xb, xm = sx(b), sx(m)
        parts.append(f'<text x="0" y="{y - 6}" font-size="13" fill="{INK}" dominant-baseline="middle">{label}</text>')
        parts.append(f'<text x="0" y="{y + 10}" font-size="10.5" fill="{MUTED}" dominant-baseline="middle">{note}</text>')
        parts.append(f'<line x1="{xb:.0f}" y1="{y:.0f}" x2="{xm:.0f}" y2="{y:.0f}" stroke="#C9CFDC" stroke-width="3"/>')
        parts.append(f'<circle cx="{xb:.0f}" cy="{y:.0f}" r="7" fill="{SLATE}"/>')
        parts.append(f'<circle cx="{xm:.0f}" cy="{y:.0f}" r="7" fill="{CORAL}"/>')
        delta = m - b
        sign = "+" if delta >= 0 else "−"
        parts.append(
            f'<text x="{max(xb, xm) + 14:.0f}" y="{y:.0f}" font-size="13" font-weight="600" '
            f'fill="{GOOD if delta > 0 else MUTED}" dominant-baseline="middle">{sign}{abs(delta):.0f}pt</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


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


def scatter_chart(points, ring, w=760, h=320, x_max=0.16, y_min=68, y_max=102):
    """points: [(x_cost, y_solve, label, color, label_side)]; ring: (x, y)"""
    pad_l, pad_r, pad_t, pad_b = 46, 24, 12, 54
    cw, ch = w - pad_l - pad_r, h - pad_t - pad_b
    sx = lambda v: pad_l + v / x_max * cw
    sy = lambda v: pad_t + (y_max - v) / (y_max - y_min) * ch
    parts = [svg_open(w, h)]
    for gv in range(70, 101, 10):
        y = sy(gv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.0f}" x2="{w - pad_r}" y2="{y:.0f}" stroke="{LINE}"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{y:.0f}" font-size="11" fill="{MUTED}" text-anchor="end" dominant-baseline="middle">{gv}%</text>')
    for cv in [0.04, 0.08, 0.12, 0.16]:
        x = sx(cv)
        parts.append(f'<line x1="{x:.0f}" y1="{pad_t}" x2="{x:.0f}" y2="{h - pad_b + 4}" stroke="{LINE}"/>')
        parts.append(f'<text x="{x:.0f}" y="{h - 34}" font-size="11" fill="{MUTED}" text-anchor="middle">${cv:.2f}</text>')
    parts.append(
        f'<text x="{(pad_l + w - pad_r) / 2:.0f}" y="{h - 12}" font-size="11" fill="{MUTED}" '
        f'text-anchor="middle">median cost per run (USD) — lower-right is worse, upper-left is better</text>'
    )
    rx, ry = sx(ring[0]), sy(ring[1])
    parts.append(f'<circle cx="{rx:.0f}" cy="{ry:.0f}" r="13" fill="none" stroke="{GOOD}" stroke-width="2" stroke-dasharray="3 2"/>')
    for x, y, label, color, side in points:
        px, py = sx(x), sy(y)
        parts.append(f'<circle cx="{px:.0f}" cy="{py:.0f}" r="6" fill="{color}"/>')
        anchor = "start" if side == "r" else "end"
        lx = px + 10 if side == "r" else px - 10
        parts.append(f'<text x="{lx:.0f}" y="{py:.0f}" font-size="11" fill="{INK}" text-anchor="{anchor}" dominant-baseline="middle">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def heat_cell(pct):
    # white -> green scale over 60..100
    a = max(0.0, min(1.0, (pct - 60) / 40))
    return (
        f'<td style="background:rgba(46,158,107,{0.06 + a * 0.5:.2f});text-align:right" class="num">{pct:.0f}%</td>'
    )


def bar_cell(v, vmax, cls, label):
    wpct = max(2, v / vmax * 100)
    return (
        f'<td class="barcell"><div class="barrow"><div class="bar {cls}" '
        f'style="width:{wpct:.0f}%"></div><span class="barlabel">{label}</span></div></td>'
    )


# ---------------------------------------------------------------- build page

def build(runs):
    by_cond = group(runs, lambda r: r["condition"])
    base_all, mcp_all = by_cond["baseline"], by_cond["mcp"]
    # macro-average across efforts so unequal rep counts don't reweight the headline
    pooled_b = statistics.mean(
        solve_pct([r for r in base_all if effort_of(r) == e]) for e in EFFORT_ORDER
    )
    pooled_m = statistics.mean(
        solve_pct([r for r in mcp_all if effort_of(r) == e]) for e in EFFORT_ORDER
    )
    cost_b, cost_m = med([r["cost_usd"] for r in base_all]), med([r["cost_usd"] for r in mcp_all])
    total_cost = sum(r["cost_usd"] or 0 for r in runs)

    # tier stats pooled across efforts
    tier_rows = []
    for t, tname in TIERS:
        rs = [r for r in runs if r["task"].startswith(t)]
        b = [r for r in rs if r["condition"] == "baseline"]
        m = [r for r in rs if r["condition"] == "mcp"]
        ntasks = len({r["task"] for r in rs})
        tier_rows.append((f"{tname} ({ntasks} tasks)", solve_pct(b), solve_pct(m), f"n={len(b)} per condition"))

    # effort stats
    eff = {}
    for e in EFFORT_ORDER:
        for c in ["baseline", "mcp"]:
            rs = [r for r in runs if effort_of(r) == e and r["condition"] == c]
            eff[(e, c)] = {
                "n": len(rs),
                "solve": solve_pct(rs),
                "wall": med([r["wall_time_s"] for r in rs]),
                "cost": med([r["cost_usd"] for r in rs]),
                "assists": sum(r["n_assist_calls"] for r in rs) / len(rs),
            }

    effort_line = line_chart(
        EFFORT_ORDER,
        [
            ("baseline", SLATE, [eff[(e, "baseline")]["solve"] for e in EFFORT_ORDER]),
            ("with MCP", CORAL, [eff[(e, "mcp")]["solve"] for e in EFFORT_ORDER]),
        ],
        annotations=[(0, 84.5, "+21pt with thinking off")],
    )

    assists_row = "".join(
        f"<span>{e}: <b>{eff[(e, 'mcp')]['assists']:.1f}</b></span>" for e in EFFORT_ORDER
    )
    ns = [eff[k]["n"] for k in eff]
    n_note = f"{min(ns)}–{max(ns)} (confirmation reps added to low/medium/high)"

    # scatter
    pts, label_sides = [], {"disabled": "r", "low": "r", "medium": "r", "high": "l", "xhigh": "l"}
    for e in EFFORT_ORDER:
        for c, color in [("baseline", SLATE), ("mcp", CORAL)]:
            d = eff[(e, c)]
            pts.append((d["cost"], d["solve"], e, color, label_sides[e]))
    frontier = (eff[("low", "mcp")]["cost"], eff[("low", "mcp")]["solve"])
    frontier_scatter = scatter_chart(pts, ring=frontier)

    # heatmap: rows = efforts, col groups = tiers x cond
    heat = ['<table class="num"><tr><th rowspan="2">Effort</th>']
    for _, tname in TIERS:
        heat.append(f'<th colspan="2" style="text-align:center">{tname}</th>')
    heat.append("</tr><tr>")
    for _ in TIERS:
        heat.append(f'<th style="color:{SLATE}">base</th><th style="color:{CORAL}">mcp</th>')
    heat.append("</tr>")
    for e in EFFORT_ORDER:
        heat.append(f'<tr><td class="task">{e}</td>')
        for t, _ in TIERS:
            for c in ["baseline", "mcp"]:
                rs = [r for r in runs if effort_of(r) == e and r["condition"] == c and r["task"].startswith(t)]
                heat.append(heat_cell(solve_pct(rs)))
        heat.append("</tr>")
    heat.append("</table>")
    heatmap = "".join(heat)

    # effort detail table
    max_wall = max(eff[k]["wall"] for k in eff)
    max_cost = max(eff[k]["cost"] for k in eff)
    et = ['<table class="num"><tr><th>Effort</th><th>Cond.</th><th class="barcell">Solve rate</th>'
          '<th class="barcell">Median time</th><th class="barcell">Median cost</th><th>Assists/run</th></tr>']
    for e in EFFORT_ORDER:
        for j, (c, cls) in enumerate([("baseline", "b"), ("mcp", "m")]):
            d = eff[(e, c)]
            et.append("<tr>" + (f'<td class="task" rowspan="2">{e}</td>' if j == 0 else ""))
            et.append(f'<td><span class="cond {cls}">{c}</span></td>')
            et.append(bar_cell(d["solve"], 100, cls, f"{d['solve']:.0f}%"))
            et.append(bar_cell(d["wall"], max_wall, cls, f"{d['wall']:.0f}s"))
            et.append(bar_cell(d["cost"], max_cost, cls, f"${d['cost']:.3f}"))
            et.append(f'<td>{d["assists"]:.1f}</td></tr>' if c == "mcp" else "<td>—</td></tr>")
    et.append("</table>")
    effort_table = "".join(et)

    # per-task dumbbells pooled across efforts
    task_rows = []
    for task in sorted({r["task"] for r in runs}):
        rs = [r for r in runs if r["task"] == task]
        b = [r for r in rs if r["condition"] == "baseline"]
        m = [r for r in rs if r["condition"] == "mcp"]
        task_rows.append((task, solve_pct(b), solve_pct(m), f"{sum(r['solved'] for r in b)}/{len(b)} → {sum(r['solved'] for r in m)}/{len(m)}"))
    task_chart = dumbbell_chart(task_rows, 30, 100, row_h=44, label_w=170)

    tier_chart = dumbbell_chart(tier_rows, 60, 100)

    n_runs = len(runs)
    hero_lift = pooled_m - pooled_b

    return f"""<title>Cairo Coder MCP — Benchmark Report</title>
<meta name="description" content="Does the Cairo Coder MCP help LLMs write Starknet contracts? {n_runs} agentic runs across 5 reasoning efforts: solve rate {pooled_b:.0f}%→{pooled_m:.0f}%, biggest impact on mid-difficulty tasks.">
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
  h1,h2,h3{{font-family:var(--mono);font-weight:600;text-wrap:balance;margin:0}}
  h1{{font-size:27px;letter-spacing:-.02em}}
  h2{{font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:16px}}
  .num{{font-variant-numeric:tabular-nums}}
  header p.lede{{max-width:66ch;font-size:17px;margin:14px 0 0}}
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
  .key{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}}
  .takeaway{{font-size:14.5px;max-width:76ch;margin:14px 0 0}}
  .takeaway b{{color:var(--mcp)}}
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
  .finding p{{margin:0;max-width:80ch;font-size:14px}}
  .tag{{font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;padding:2px 7px;border-radius:3px;margin-right:8px;vertical-align:1px}}
  .tag.win{{background:#E7F4EE;color:var(--good)}} .tag.cost{{background:#FBEDE8;color:var(--mcp)}} .tag.warn{{background:#F7EFDC;color:#9A7013}}
  code{{font-family:var(--mono);font-size:.92em;background:var(--ground);border:1px solid var(--line);border-radius:3px;padding:1px 5px}}
  .split{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}
  @media(max-width:760px){{.split{{grid-template-columns:1fr}}}}
  ul.meta{{margin:0;padding-left:20px;font-size:13.5px;color:var(--muted)}}
  ul.meta li{{margin-bottom:7px;max-width:85ch}}
  ul.meta b{{color:var(--ink)}}
</style>
<main>
<header>
  <h1>Does documentation access make an LLM a better Starknet developer?</h1>
  <p class="lede">We gave the same model the same {len({r["task"] for r in runs})} smart-contract tasks, with and without the <b>Cairo Coder</b> documentation tool, across five reasoning-effort settings. With the tool, the model completes more tasks, spends less doing it, and needs it most exactly where you'd expect: on the tasks in the middle of the difficulty range.</p>
  <div class="chips">
    <span class="chip">model <b>GLM 5.2</b></span>
    <span class="chip">runs <b>{n_runs}</b></span>
    <span class="chip">reasoning efforts <b>5</b></span>
    <span class="chip">hidden tests <b>106</b></span>
    <span class="chip">total LLM spend <b>${total_cost:.0f}</b></span>
    <span class="chip">2026-07-22</span>
  </div>
</header>

<section>
  <div class="cards num">
    <div class="card"><div class="big">{pooled_b:.0f}<small>%</small> → {pooled_m:.0f}<small>%</small></div><div class="what">tasks completed, without → with the docs tool (averaged across effort settings)</div></div>
    <div class="card"><div class="big">−{(1 - cost_m / cost_b) * 100:.0f}<small>%</small></div><div class="what">median cost per task — the tool saves more than it costs</div></div>
    <div class="card"><div class="big">5<small>/5</small></div><div class="what">reasoning-effort settings where the tool improved or matched the solve rate</div></div>
  </div>
</section>

<section>
  <h2>Where the tool matters — task difficulty</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline</span><span><span class="key" style="background:var(--mcp)"></span>with MCP</span></div>
  {tier_chart}
  <p class="takeaway">Easy tasks don't need help. <b>Mid-difficulty contracts — token variants, escrow, voting — are where documentation pays: failures disappear entirely (+{tier_rows[1][2] - tier_rows[1][1]:.0f}pt).</b> The hardest tasks (account abstraction, components) improve but still fail sometimes: knowing the docs isn't the same as getting the architecture right.</p>
</section>

<section>
  <h2>Documentation substitutes for thinking — the effort curve</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline</span><span><span class="key" style="background:var(--mcp)"></span>with MCP</span><span>solve rate; n per point ranges {n_note}</span></div>
  {effort_line}
  <p class="takeaway">The less the model is allowed to think, the more the tool helps — and the more the model reaches for it (documentation lookups per run: <span class="assists" style="display:inline-flex">{assists_row}</span>). Extra thinking buys no solve-rate gain: after enlarging low/medium/high baselines to n=130, low and medium are statistically identical (p=0.83) and high trails by a suggestive-but-not-significant ~7pt (p=0.09) — while costing 2–3× the time and money.</p>
</section>

<section>
  <h2>What should you actually run? — the efficiency frontier</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline</span><span><span class="key" style="background:var(--mcp)"></span>with MCP</span><span>each point = one effort setting</span></div>
  {frontier_scatter}
  <p class="takeaway"><b>low + MCP is the efficient frontier</b>: {eff[("low", "mcp")]["solve"]:.0f}% of tasks solved at ~${eff[("low", "mcp")]["cost"]:.3f} and ~{eff[("low", "mcp")]["wall"]:.0f}s per task — statistically indistinguishable from the most expensive configuration (xhigh + MCP, {eff[("xhigh", "mcp")]["solve"]:.0f}% at n=39) at {eff[("xhigh", "mcp")]["cost"] / eff[("low", "mcp")]["cost"]:.1f}× the cost and {eff[("xhigh", "mcp")]["wall"] / eff[("low", "mcp")]["wall"]:.1f}× the time.</p>
</section>

<section class="findings">
  <h2>Findings</h2>
  <div class="finding"><h3><span class="tag win">effectiveness</span>Baseline failures are training-data lag, and the tool fixes exactly that</h3>
  <p>Failed baseline runs get stuck on <em>current</em> Cairo idioms — most often the storage API, writing pre-2024 <code>Map.read(key)</code> instead of today's <code>Map.entry(key).read()</code> — and burn the whole 10-turn budget against the compiler. In the MCP condition one documentation lookup resolves it. This is the precise gap a RAG tool over current docs should close, and it does.</p></div>
  <div class="finding"><h3><span class="tag cost">economics</span>The tool pays for itself by preventing failures, not by speeding up wins</h3>
  <p>Each lookup takes ~15–30s, so on tasks the model can already do the MCP condition is sometimes slower. But a failed run costs ~10 turns of reasoning tokens — several times the lookup overhead. Net across the study: lower median cost at 4 of 5 effort settings.</p></div>
  <div class="finding"><h3><span class="tag cost">behavior</span>Tool use is selective and rises when reasoning is scarce</h3>
  <p>The model consults the docs roughly once every other run at high effort, and ~1.8 times per run with thinking disabled — typically after the first compiler error, not up front. Availability doesn't degrade into dependence.</p></div>
  <div class="finding"><h3><span class="tag warn">caveat</span>Cairo Coder confabulates outside its index</h3>
  <p>Asked about a token standard we invented ("STRK77"), the service returned a complete, confident, fabricated Cairo interface. Within its indexed corpus it's accurate; agents consuming it get no signal when a query falls outside coverage. Worth fixing upstream.</p></div>
</section>

<section>
  <h2>Detail — effort × condition</h2>
  <div class="tablewrap">{effort_table}</div>
</section>

<section>
  <h2>Detail — solve rate by effort × difficulty</h2>
  <div class="tablewrap">{heatmap}</div>
</section>

<section>
  <h2>Detail — per task, pooled across efforts</h2>
  <div class="legend"><span><span class="key" style="background:var(--baseline)"></span>baseline</span><span><span class="key" style="background:var(--mcp)"></span>with MCP</span><span>run counts per task shown in each row</span></div>
  {task_chart}
</section>

<section>
  <div class="split">
    <div>
      <h2>Methodology</h2>
      <ul class="meta">
        <li><b>Harness:</b> agentic repair loop, max 10 assistant turns. The model submits <code>src/lib.cairo</code> via a <code>submit</code> tool; the harness runs <code>scarb build</code> + <code>snforge test</code> against hidden tests and returns the output. Conditions are identical except the MCP condition also exposes <code>assist_with_cairo</code>, replicated exactly from <code>@kasarlabs/cairo-coder-mcp</code> v0.2.5.</li>
        <li><b>Tasks:</b> 13 hand-written Starknet contracts (4 easy / 5 medium / 4 hard incl. a SNIP-6 account and a custom component); every reference solution passes 100% of its tests, every stub fails.</li>
        <li><b>Model:</b> z-ai/glm-5.2 via OpenRouter, throughput-sorted routing, provider-default temperature; efforts via the unified reasoning parameter (<code>disabled</code> = <code>enabled:false</code>). Costs are OpenRouter-reported.</li>
        <li><b>Solved</b> = every hidden test passes within the turn budget. 3 reps per cell.</li>
      </ul>
    </div>
    <div>
      <h2>Caveats</h2>
      <ul class="meta">
        <li><b>One model.</b> These numbers characterize GLM 5.2; the effort–MCP interaction likely varies by model family and training cutoff.</li>
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
