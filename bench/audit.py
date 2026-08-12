"""Re-verify every published number in the report against the run data.

  uv run python -m bench.audit

Prints OK or FAIL per claim and exits non-zero if any fails, so it can gate a
rebuild or a release. Every figure quoted in results/report.html is checked here
against results/runs/main.jsonl: the leaderboard and its intervals, each FAQ card,
every findings claim, the methodology and caveat numbers, and the chips. If you
change the data, run this before believing the report.
"""
import json as _json
import math
import os
import re
import statistics as st
import sys

from bench.html_report import word
from bench.report import load_runs
from bench.sci import (BUDGET_RESERVE, CHART_TOP_N, LOCAL_QUANT,
                       LOCAL_WEIGHT_BUDGET_GB, PRICE_REVISIONS, SCI_SPEC,
                       VRAM_BUDGETS, active_models, attempts, best_quant_for,
                       compute_sci, fits_locally, index_ci, leaderboard,
                       price_ratio, run_cost)

runs = load_runs(["results/runs/main.jsonl"])
# a few claims are about the rendered prose, not just the data behind it
report_html = open("results/report.html", encoding="utf-8").read()
lb = leaderboard(runs)
by = {r["label"]: r for r in lb}
mcp = {r["label"]: r for r in leaderboard(runs, condition="mcp")}
NT = len({x["task"] for x in runs if x["task"] != "fake"})
# Who the headline charts draw. Several claims are scoped to the charts rather
# than to the field ("Opus has the fastest median pass"), and they used to be
# written as "not local", which was only ever a proxy for charted and stopped
# being one when the charts moved to the top CHART_TOP_N by index.
charted = {r["label"] for r in lb[:CHART_TOP_N]}

C = lambda s, c="baseline": [x for x in runs if x["model"] == s and x["condition"] == c]
one = lambda rs: 100 * sum(1 for x in rs if x["solved"] and attempts(x) == 1) / len(rs)
solve = lambda rs: 100 * sum(1 for x in rs if x["solved"]) / len(rs)
sci = lambda rs: compute_sci(rs)["sci"]
med_cost = lambda s: st.median([c for c in (run_cost(x) for x in C(s)) if c is not None])


def ncalls(x):
    v = x.get("assist_calls")
    return len(v) if isinstance(v, list) else (v or 0)


def passes(spec):
    d = {}
    for x in C(spec):
        d.setdefault(x["rep"], []).append(x)
    return [rs for rs in d.values() if len(rs) == NT]


def pass_med(spec, fn):
    p = passes(spec)
    return st.median([fn(rs) for rs in p]) if p else float("nan")


pass_cost = lambda s: pass_med(s, lambda rs: sum(run_cost(x) or 0 for x in rs))
pass_time = lambda s: pass_med(s, lambda rs: sum(x["llm_time_s"] + (x.get("assist_time_s") or 0) for x in rs))

fails = []


def check(claim, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + claim + ("  |  " + detail if detail else ""))
    if not cond:
        fails.append(claim)


print("== leaderboard shape")
print("   " + "  ".join(f"{r['label']}={r['sci']:.1f}({r['variant']})" for r in lb[:8]))

print("\n== chips and coverage")
check("13 tasks", NT == 13, f"{NT}")
# Not a typed roster size: every active registry entry must reach the
# leaderboard. Typing the count made it a chore on every deliberate addition,
# while this still catches the failure that matters, an active model producing
# no rows because its runs never landed.
check("every active model is charted", len(lb) == len(active_models()),
      f"{len(lb)} charted, {len(active_models())} active"
      + (f" | missing: {', '.join(sorted({e['label'] for e in active_models()} - {r['label'] for r in lb}))}"
         if len(lb) != len(active_models()) else ""))

print("\n== price revisions")
# A revision is applied as one multiplier to a recorded total, which is only
# valid when every component of the price vector moved by the same factor. A
# non-uniform entry would score silently wrong, so price_ratio raises and this
# check makes that visible rather than waiting for an import to blow up.
for spec, (was, now) in PRICE_REVISIONS.items():
    try:
        rs = [n / w for w, n in zip(was, now) if w and n]
        check(f"{spec} revision is uniform ({price_ratio(spec):.3f}x)",
              max(rs) - min(rs) <= 1e-9, " ".join(f"{r:.6f}" for r in rs))
    except ValueError as e:
        check(f"{spec} revision is uniform", False, str(e))
# revised costs must actually reach the scores: the report and this file both
# have to be reading run_cost, not the raw figure
_t = [x for x in runs if x["model"] == "openai/gpt-5.6-terra@max" and x["condition"] == "baseline"]
check("Terra scored at revised prices",
      abs(st.median([run_cost(x) for x in _t]) / st.median([x["cost_usd"] for x in _t]) - 0.40) < 1e-9,
      f"{st.median([run_cost(x) for x in _t]):.4f} vs {st.median([x['cost_usd'] for x in _t]):.4f} billed")

print("\n== index precision")
worst = max(((index_ci(C(r["spec"])) or 0), r["label"]) for r in lb)
check("every model within +/-5", worst[0] <= 5.0, f"widest {worst[0]:.1f} ({worst[1]})")

print("\n== FAQ cards")
o, f, k, mi, s5, sol = (by[n] for n in
    ["Opus 5", "Fable 5", "Kimi K3", "MiMo-V2.5-Pro", "Sonnet 5", "GPT-5.6 Sol"])
check("Opus 100% one-shot", one(C(o["spec"])) == 100, f"{one(C(o['spec'])):.0f}%")
check("Opus has the fastest median pass of the charted models",
      min((pass_time(by[r["label"]]["spec"]), r["label"])
          for r in lb if r["label"] in charted)[1] == "Opus 5")
check("Opus is 2.7 clear of second", abs(o["sci"] - f["sci"] - 2.7) < 0.06, f"{o['sci']-f['sci']:.2f}")
check("Kimi 71% vs MiMo 40% one-shot",
      round(one(C(k["spec"]))) == 71 and round(one(C(mi["spec"]))) == 40,
      f"{one(C(k['spec'])):.0f}/{one(C(mi['spec'])):.0f}")
check("Kimi beats MiMo by 4.3", abs(k["sci"] - mi["sci"] - 4.3) < 0.06, f"{k['sci']-mi['sci']:.2f}")
check("MiMo 1.4x faster, 6x cheaper per pass",
      abs(pass_time(k["spec"]) / pass_time(mi["spec"]) - 1.4) < 0.2
      and abs(pass_cost(k["spec"]) / pass_cost(mi["spec"]) - 6) < 1,
      f"{pass_time(k['spec'])/pass_time(mi['spec']):.1f}x / {pass_cost(k['spec'])/pass_cost(mi['spec']):.0f}x")
# The K3-vs-Qwen3.8 card: same class of model, 31 points apart. Every figure it
# quotes is recomputed here, including the negative claim, which is the one most
# likely to rot as reps are added.
q38 = by["Qwen3.8 Max"]
_meta = _json.load(open("results/model_meta.json"))["models"]
check("K3 and Qwen3.8 Max are the same class: 2.8T/104B vs 2.4T/95B",
      (_meta["moonshotai/kimi-k3"]["params_total"], _meta["moonshotai/kimi-k3"]["params_active"],
       _meta["qwen/qwen3.8-max"]["params_total"], _meta["qwen/qwen3.8-max"]["params_active"])
      == ("2.8T", "104B", "2.4T", "95B"))
check("K3 is 31 points clear of Qwen3.8 Max",
      abs(k["sci"] - q38["sci"] - 31.0) < 0.5, f"{k['sci']-q38['sci']:.2f}")
_ck, _cq = compute_sci(C(k["spec"]))["components"], compute_sci(C(q38["spec"]))["components"]
_eff = SCI_SPEC["weights"]["effective"] * (_ck["effective"] - _cq["effective"])
check("25 of the 31 points are effectiveness, the rest serving",
      24.0 <= _eff <= 26.0 and all(
          abs(SCI_SPEC["weights"][w] * (_ck[c] - _cq[c])) < 3.5
          for w, c in (("correct", "correct"), ("cost", "cost"), ("speed", "speed"))),
      f"eff {_eff:+.1f}, others "
      + ", ".join(f"{c} {SCI_SPEC['weights'][w] * (_ck[c] - _cq[c]):+.2f}"
                  for w, c in (("correct", "correct"), ("cost", "cost"), ("speed", "speed"))))
check("K3 71% vs Qwen3.8 Max 9% first-try compiles",
      round(one(C(k["spec"]))) == 71 and round(one(C(q38["spec"]))) == 9,
      f"{one(C(k['spec'])):.0f}%/{one(C(q38['spec'])):.0f}%")

check("Sonnet is 4th", [r["label"] for r in lb].index("Sonnet 5") == 3)
check("Opus-Sonnet gap 8.6", abs(o["sci"] - s5["sci"] - 8.6) < 0.06, f"{o['sci']-s5['sci']:.2f}")
check("Sonnet 67% one-shot", round(one(C(s5["spec"]))) == 67, f"{one(C(s5['spec'])):.0f}%")
q27 = by["Qwen3.6-27B"]
check("27B +22.0 with docs", abs(mcp["Qwen3.6-27B"]["sci"] - q27["sci"] - 22.0) < 0.06,
      f"{mcp['Qwen3.6-27B']['sci']-q27['sci']:+.1f}")
check("27B 15% -> 69% solved",
      round(solve(C(q27["spec"]))) == 15 and round(solve(C(q27["spec"], "mcp"))) == 69,
      f"{solve(C(q27['spec'])):.0f}->{solve(C(q27['spec'],'mcp')):.0f}")
check("Sol 40% one-shot at its winner", round(one(C(sol["spec"]))) == 40, f"{one(C(sol['spec'])):.0f}%")
check("Sol $0.0895 per task", abs(med_cost(sol["spec"]) - 0.0895) < 0.002, f"${med_cost(sol['spec']):.4f}")
solm = C("openai/gpt-5.6-sol@max", "mcp")
check("Sol 72% one-shot with the tool", round(one(solm)) == 72, f"{one(solm):.0f}%")
check("Sol +7.9 with the tool", abs(mcp["GPT-5.6 Sol"]["sci"] - by["GPT-5.6 Sol"]["sci"] - 7.9) < 0.06,
      f"{mcp['GPT-5.6 Sol']['sci']-by['GPT-5.6 Sol']['sci']:+.1f}")
lb_, lm_ = C("openai/gpt-5.6-luna@max", "baseline"), C("openai/gpt-5.6-luna@max", "mcp")
check("Luna's top tier gains +3.0, inside its own noise",
      abs((sci(lm_) - sci(lb_)) - 3.0) < 0.06 and (index_ci(lm_) + index_ci(lb_)) > 3.0,
      f"{sci(lm_)-sci(lb_):+.1f} vs interval sum {index_ci(lm_)+index_ci(lb_):.1f}")
check("Luna is charted, and is the third OpenAI model",
      "GPT-5.6 Luna" in charted
      and len([r for r in lb if r["lab"] == "OpenAI" and r["label"] in charted]) == 3,
      f"{[r['label'] for r in lb if r['lab'] == 'OpenAI']}")
check("Terra +9.1 with the tool at max", abs(mcp["GPT-5.6 Terra"]["sci"] - by["GPT-5.6 Terra"]["sci"] - 9.1) < 0.06,
      f"{mcp['GPT-5.6 Terra']['sci']-by['GPT-5.6 Terra']['sci']:+.1f}")
check("Sonnet max: 88% one-shot, 61k tokens",
      round(one(C("anthropic/claude-sonnet-5@max"))) == 88
      and 58000 < st.median([x["completion_tokens"] for x in C("anthropic/claude-sonnet-5@max") if x["completion_tokens"]]) < 64000)
check("Kimi low ties the default at a third of the cost",
      abs(compute_sci(C("moonshotai/kimi-k3@low"))["sci"] - compute_sci(C("moonshotai/kimi-k3"))["sci"]) < 0.5
      and med_cost("moonshotai/kimi-k3") / med_cost("moonshotai/kimi-k3@low") > 2.5,
      f"{med_cost('moonshotai/kimi-k3')/med_cost('moonshotai/kimi-k3@low'):.1f}x cheaper")

print("\n== findings: documentation lift at each condition's own best")
for lab, want in (("Qwen3.6-27B", 22.0), ("Qwen3.8 Max", 16.3), ("Qwen3.6-35B-A3B", 15.6),
                  ("GLM 5.2", 6.4), ("GPT-5.6 Terra", 9.1),
                  ("GPT-5.6 Sol", 7.9), ("Qwen3 Coder Next", 6.3), ("MiniMax M3", 5.2), ("Hy3", 2.3),
                  ("Opus 5", -0.1), ("Kimi K3", -0.4), ("Fable 5", -2.5),
                  ("MiMo-V2.5-Pro", -2.6), ("Sonnet 5", -5.4),
                  ("Gemma 4 31B", -1.8), ("gpt-oss-120b", -1.7)):
    got = mcp[lab]["sci"] - by[lab]["sci"]
    check(f"{lab} {want:+.1f}", abs(got - want) < 0.06, f"{got:+.1f}")

print("\n== findings: mechanism and habits")
# the claim is about the three Anthropic models the report charts; Haiku 4.5 and
# Opus 4.8 are deprecated and absent from it, so they do not bear on it
CHARTED_ANTHROPIC = ("anthropic/claude-opus-5", "anthropic/claude-sonnet-5", "anthropic/claude-fable-5")
check("Anthropic (charted) never called the tool",
      sum(ncalls(x) for x in runs if x["condition"] == "mcp"
          and x["model"].split("@")[0] in CHARTED_ANTHROPIC) == 0)
gb, gm = C("x-ai/grok-4.5@max"), C("x-ai/grok-4.5@max", "mcp")
check("Grok ~0.9 lookups/run, 74->88 one-shot",
      abs(st.mean([ncalls(x) for x in gm]) - 0.88) < 0.1 and round(one(gm)) == 88,
      f"{st.mean([ncalls(x) for x in gm]):.2f} calls, {one(gb):.0f}->{one(gm):.0f}")
check("terra-pro 53.8 below terra@max 55.2, and the prose quotes those",
      abs(sci(C("openai/gpt-5.6-terra-pro")) - 53.8) < 0.06
      and abs(sci(C("openai/gpt-5.6-terra@max")) - 55.2) < 0.06
      and "terra-pro 53.8 against terra@max 55.2" in report_html,
      f"{sci(C('openai/gpt-5.6-terra-pro')):.1f} vs {sci(C('openai/gpt-5.6-terra@max')):.1f}")
glm = [x for x in runs if x["model"].startswith("z-ai/glm-5.2")]
check("GLM 993 runs across 7 efforts",
      len(glm) == 993 and len({x["model"] for x in glm}) == 7,
      f"{len(glm)} runs, {len({x['model'] for x in glm})} efforts")
for t, want in (("high", 0.7), ("disabled", 1.9)):
    got = st.mean([ncalls(x) for x in C(f"z-ai/glm-5.2@{t}", "mcp")])
    check(f"GLM lookups @{t} ~{want}/run", abs(got - want) < 0.2, f"{got:.2f}")
check("Qwen dial buys solves: 27B off 15% -> low 31%",
      round(solve(C("qwen/qwen3.6-27b@disabled"))) == 15 and round(solve(C("qwen/qwen3.6-27b@low"))) == 31,
      f"{solve(C('qwen/qwen3.6-27b@disabled')):.0f}->{solve(C('qwen/qwen3.6-27b@low')):.0f}")

print("\n== caveats")
ab = [x for x in runs if x.get("abandoned") or x.get("abandoned_note")]
for t in ("low", "medium", "high"):
    check(f"GLM @{t} n=130", len(C(f"z-ai/glm-5.2@{t}")) == 130, f"{len(C(f'z-ai/glm-5.2@{t}'))}")


def ztest(k1, n1, k2, n2):
    p1, p2, p = k1 / n1, k2 / n2, (k1 + k2) / (n1 + n2)
    z = (p1 - p2) / math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


kn = {t: (sum(1 for x in C(f"z-ai/glm-5.2@{t}") if x["solved"]), len(C(f"z-ai/glm-5.2@{t}")))
      for t in ("low", "medium", "high")}
check("p=0.83 low~medium", abs(ztest(*kn["low"], *kn["medium"]) - 0.83) < 0.02,
      f"{ztest(*kn['low'], *kn['medium']):.3f}")
check("p=0.09 low~high", abs(ztest(*kn["low"], *kn["high"]) - 0.09) < 0.02,
      f"{ztest(*kn['low'], *kn['high']):.3f}")

print("\n== claims added after the second consistency pass")
tok = lambda rs: st.median([x["completion_tokens"] for x in rs if x["completion_tokens"]])
med_time = lambda rs: st.median([x["llm_time_s"] for x in rs])

# methodology
npass = sorted({-(-len(C(r["spec"])) // 13) for r in lb})
check("methodology: 2 to 10 passes", min(npass) == 2 and max(npass) == 10, str(npass))
# caveats: per-variant depth outside GLM
ns = [len(C(sp)) for e in lb if e["label"] != "GLM 5.2" for sp in e["specs"] if C(sp)]
check("caveats: 13 to 120 runs per variant", min(ns) == 13 and max(ns) == 120, f"{min(ns)}-{max(ns)}")
# The local-inference class is derived, so check it in BOTH directions against
# the rule: nothing inside it exceeds the weights budget, and nothing outside it
# would have fitted. A one-way check would pass a class that quietly lost members.
loc = [r for r in lb if r.get("local")]
_by_rule = {e["label"] for e in active_models() if fits_locally(e)}
check(f"local class: {len(_by_rule)} models by the rule, all within "
      f"{LOCAL_WEIGHT_BUDGET_GB:.0f} GB at {LOCAL_QUANT}",
      {r["label"] for r in loc} == _by_rule
      and all(r["vram_gb"] <= LOCAL_WEIGHT_BUDGET_GB for r in loc),
      f"{len(loc)} models, largest {max(r['vram_gb'] for r in loc):.0f} GB "
      f"({max(loc, key=lambda r: r['vram_gb'])['label']})")
out = [r for r in lb if not r.get("local") and r["open_weight"] and r["vram_gb"]]
check("Hy3 is the nearest miss, at 181 GB",
      all(r["vram_gb"] > LOCAL_WEIGHT_BUDGET_GB for r in out)
      and min(out, key=lambda r: r["vram_gb"])["label"] == "Hy3"
      and round(min(r["vram_gb"] for r in out)) == 181,
      f"nearest miss {min(r['vram_gb'] for r in out):.0f} GB "
      f"({min(out, key=lambda r: r['vram_gb'])['label']})")
check("no closed model is in the class", not any(not r["open_weight"] for r in loc))
# Sizes are snapshotted from third-party GGUF repos, so the snapshot has to
# defend itself: every block names where it came from, and quant sizes must
# increase with quant level. A loose stem match once put Coder Next's Q8_0
# below its Q6_K, and the Inkling search hit was a different, smaller model.
LADDER = ["IQ4_XS", "Q4_K_M", "Q6_K", "Q8_0", "BF16"]
_mm = _json.load(open("results/model_meta.json"))["models"]
bad_src = [k for k, v in _mm.items() if v.get("gguf") and not v["gguf"].get("repo")]
check("every GGUF snapshot names its source repo", not bad_src, ", ".join(bad_src) or "none")
nonmono = []
for k, v in _mm.items():
    sizes = [(q, (v.get("gguf") or {}).get(q)) for q in LADDER]
    sizes = [(q, s) for q, s in sizes if s]
    nonmono += [f"{k}:{qb}" for (qa, a), (qb, b) in zip(sizes, sizes[1:]) if b <= a]
check("GGUF sizes increase with quant level", not nonmono, ", ".join(nonmono) or "none")

# Who each chart actually draws, read off the shipped SVG rather than inferred
# from the code that wrote it. Membership is a claim the prose makes ("the top
# twelve"), and the failure mode is silent: a chart drawn from the wrong row set
# still renders perfectly. Text checks would not have caught it either.
def section_html(prefix):
    for sec in re.findall(r"<section.*?</section>", report_html, re.S):
        h = re.search(r"<h2[^>]*>(.*?)</h2>", sec, re.S)
        if h and re.sub(r"<[^>]+>", "", h.group(1)).strip().startswith(prefix):
            return sec
    return ""


def chart_labels(svg):
    """Model names off a chart's angled axis labels, in drawn order.

    Two shapes: a bare rotated <text>, and a rotated <g> wrapping the label plus
    a rank-delta arrow and number (the number is dropped as non-label).
    """
    out = []
    for g, t in re.findall(r'<g transform="rotate\([^"]*\)">(.*?)</g>'
                           r'|<text transform="rotate\([^"]*\)"[^>]*>(.*?)</text>',
                           svg, re.S):
        inner = g or t
        if g:
            m = re.search(r"<text[^>]*>(.*?)</text>", g, re.S)
            inner = m.group(1) if m else ""
        txt = re.sub(r"<[^>]+>", "", inner).replace("&plusmn;", "").strip()
        txt = re.sub(r"\s*\([^)]*\)$", "", txt).rstrip("*").strip()
        if txt and not txt.replace(".", "").isdigit():
            out.append(txt)
    return out


svgs = lambda prefix: re.findall(r"<svg.*?</svg>", section_html(prefix), re.S)
top_n = [r["label"] for r in lb[:CHART_TOP_N]]
sci_svg = svgs("Starknet Coding Index")
check(f"index chart draws the top {CHART_TOP_N}, in rank order",
      len(sci_svg) == 1 and chart_labels(sci_svg[0]) == top_n,
      " > ".join(chart_labels(sci_svg[0])) if sci_svg else "no chart found")
cut_titles = re.findall(r"top (\d+) of the (\d+) models tested", report_html, re.IGNORECASE)
check("the index and MCP chart titles state the cut",
      len(cut_titles) == 2
      and all([int(a), int(b)] == [CHART_TOP_N, len(lb)] for a, b in cut_titles),
      "; ".join(f"Top {a} of the {b}" for a, b in cut_titles) or "no titles")
behind = svgs("Behind the score")
check("all three 'Behind the score' charts draw the same top models",
      len(behind) == 3 and all(sorted(chart_labels(s)) == sorted(top_n) for s in behind),
      f"{len(behind)} charts, sizes {[len(chart_labels(s)) for s in behind]}")
# The one headline chart that does NOT share the baseline cut. It ranks by the
# best of either condition, because ranking the documentation chart by the score
# without documentation dropped the models it exists to show. Recomputed here
# from the data rather than copied from the report, then read back off the
# shipped SVG, so a chart built from the wrong row set still fails.
_mcp_lb = {r["label"]: r for r in leaderboard(runs, condition="mcp")}
_best = lambda r: (max(r["sci"], _mcp_lb[r["label"]]["sci"])
                   if r["label"] in _mcp_lb else r["sci"])
lift_n = [r["label"] for r in sorted(lb, key=_best, reverse=True)[:CHART_TOP_N]]
mcp_svg = svgs("What does the Cairo Coder MCP add")
check(f"the MCP chart draws the top {CHART_TOP_N} by best-of-either condition",
      len(mcp_svg) == 1 and sorted(chart_labels(mcp_svg[0])) == sorted(lift_n),
      ", ".join(sorted(set(chart_labels(mcp_svg[0])) ^ set(lift_n)) or ["exact"]) if mcp_svg else "no chart")
dial_names = re.findall(r'<div class="multiple"><h3>([^<]+)</h3>', section_html("The thinking dial"))
check("the dial section draws the top 8 by index, in rank order",
      dial_names == top_n[:8], " > ".join(dial_names) or "no multiples")
# the intro's look-for pointers; Opus and Sonnet's are covered by the
# winner-vs-max checks below
mus = {t: sci(C(f"meta/muse-spark-1.2@{t}")) for t in ("minimal", "low", "medium", "high", "xhigh")}
check("Muse Spark's dial splits in two: 66-71 below high, 80 at high and xhigh",
      all(66 <= mus[t] < 72 for t in ("minimal", "low", "medium"))
      and all(79.5 <= mus[t] < 81 for t in ("high", "xhigh")),
      ", ".join(f"{t} {v:.1f}" for t, v in mus.items()))
grok = [sci(C(f"x-ai/grok-4.5@{t}")) for t in ("minimal", "low", "medium", "high", "max")]
check("Grok's five tiers land within 3 points",
      max(grok) - min(grok) < 3, f"span {max(grok) - min(grok):.1f}")
fable = {t: sci(C(f"anthropic/claude-fable-5@{t}")) for t in ("xhigh", "max")}
check("Fable's max drops 5.6 below its xhigh plateau",
      abs(fable["xhigh"] - fable["max"] - 5.6) < 0.15,
      f"{fable['xhigh']:.1f} vs {fable['max']:.1f}")
kimi = {t: sci(C(f"moonshotai/kimi-k3@{t}")) for t in ("disabled", "low", "high")}
kimi["max"] = sci(C("moonshotai/kimi-k3"))  # bare spec = documented max default
check("Kimi is level at off, low and max, and dips only at high",
      max(kimi["disabled"], kimi["low"], kimi["max"])
      - min(kimi["disabled"], kimi["low"], kimi["max"]) < 1
      and all(kimi["high"] < kimi[t] - 2 for t in ("disabled", "low", "max")),
      ", ".join(f"{t} {v:.1f}" for t, v in kimi.items()))
local_svg = svgs("Local-inference class")
check(f"the local chart draws all {len(loc)} models that fit one machine",
      len(local_svg) == 1 and sorted(chart_labels(local_svg[0])) == sorted(r["label"] for r in loc),
      ", ".join(sorted(set(chart_labels(local_svg[0])) ^ {r["label"] for r in loc}) or ["exact"])
      if local_svg else "no chart")
check(f"FAQ: {len(loc)} of {len(lb)} runnable, largest gpt-oss-120b at 63 GB",
      f"{len(loc)} of {len(lb)}" in report_html
      and max(loc, key=lambda r: r["vram_gb"])["label"] == "gpt-oss-120b"
      and round(max(r["vram_gb"] for r in loc)) == 63,
      f"{len(loc)} in class, largest {max(loc, key=lambda r: r['vram_gb'])['label']} "
      f"{max(r['vram_gb'] for r in loc):.0f} GB")

# The five ladder rungs the report prints are picks out of a much longer list
# (13 to 38 files per repo), so check the pick rather than trusting it: each
# canonical size must be exactly the plain build, or the UD- build where the repo
# publishes no plain one. This is what caught Gemma 4 31B, whose Q8_0 and BF16
# were inflated by half a gigabyte of `mtp-` draft head summed into them.
bad_pick = []
for k, v in _mm.items():
    files = (v.get("gguf") or {}).get("files")
    if not files:
        continue
    # Case-insensitive, matching snapshot_meta: repos disagree on case
    # (bartowski publishes bf16 where unsloth publishes BF16), and this check
    # exists to catch a wrong FILE, not a differently-cased name.
    lower = {q.lower(): s for q, s in files.items()}
    for q in LADDER:
        want = lower.get(q.lower()) or lower.get(f"UD-{q}".lower())
        if v["gguf"].get(q) != want:
            bad_pick.append(f"{k}:{q} prints {v['gguf'].get(q)}, ladder has {want}")
check("every printed quant size is the one in the published ladder",
      not bad_pick, "; ".join(bad_pick) or
      f"{sum(len((v.get('gguf') or {}).get('files') or {}) for v in _mm.values())} files across "
      f"{sum(1 for v in _mm.values() if (v.get('gguf') or {}).get('files'))} repos")

# The per-machine table recommends a file to download, so every cell is checked
# back against the published ladder rather than trusted: the name must be a real
# file in that model's repo, the size must be the size that repo lists, and it
# must fit the machine after its reserve. Read out of the shipped HTML, because a
# cell built from the wrong pick renders perfectly.
print("\n== which quantization for my machine")
open_sec = section_html("Which quantization")
cells = re.findall(r"<tr><td>(.*?)</td>(.*?)</tr>", open_sec, re.S)
bad_cell, n_cell = [], 0
for label, rest in cells:
    spec = next((r["spec"] for r in lb if r["label"] == label), None)
    if spec is None:
        bad_cell.append(f"{label}: not a leaderboard row")
        continue
    files = (_mm.get(spec.partition("@")[0], {}).get("gguf") or {}).get("files") or {}
    # SCI and Context lead, so the budget columns are the last len(VRAM_BUDGETS)
    # cells, in that order. Taken from the END rather than by a fixed offset, so
    # another reference column added in front cannot shift which cells are read.
    tds = re.findall(r'<td class="r[^"]*"[^>]*>(.*?)</td>', rest, re.S)[-len(VRAM_BUDGETS):]
    if len(tds) != len(VRAM_BUDGETS):
        bad_cell.append(f"{label}: {len(tds)} budget cells, expected {len(VRAM_BUDGETS)}")
        continue
    for budget, td in zip(VRAM_BUDGETS, tds):
        want = best_quant_for(spec, budget)
        # the quant and its cost are separate spans now; read them separately so a
        # cell that loses one of them fails rather than reparsing as the other
        qm = re.search(r'<span class="q">(.*?)</span>', td, re.S)
        gm = re.search(r'<span class="gb">([\d,]+) GB</span>', td, re.S)
        if not qm:
            if want:
                bad_cell.append(f"{label} at {budget} GB: blank, expected {want[0]}")
            continue
        n_cell += 1
        if not gm:
            bad_cell.append(f"{label} at {budget} GB: names a quant with no size")
            continue
        name, size = qm.group(1).strip(), int(gm.group(1).replace(",", ""))
        if not want or name != want[0] or round(want[1]) != size:
            bad_cell.append(f"{label} at {budget} GB: prints {name} {size}, "
                            f"picker says {want}")
        elif name not in files:
            bad_cell.append(f"{label} at {budget} GB: {name} is not in the published ladder")
        elif files[name] > budget - BUDGET_RESERVE[budget]:
            bad_cell.append(f"{label} at {budget} GB: {name} is {files[name]} GB, over budget")
check("every recommended quant is a real file that fits its machine",
      not bad_cell, "; ".join(bad_cell[:6]) or f"{n_cell} cells across {len(cells)} models")

# Which open models are measured is not a number to type, it is a consequence of
# which repos got snapshotted: a model is estimated exactly when no GGUF repo was
# found for it. Stating it that way self-updates as the roster grows, and it
# fails loudly if a snapshot silently stops supplying a size.
def _gguf(r):
    return (_mm.get(r["spec"].partition("@")[0], {}) or {}).get("gguf") or {}


# Models whose snapshotted repo publishes no plain Q4_K_M, so they fall back to
# the bit-width estimate even though a repo exists. Nobody quantizes a 2.8T or a
# 304B model to that rung, so this is upstream's choice and not a snapshot bug.
# Listed by name rather than tolerated in general, because the same shape is a
# REAL bug when a plain quant exists elsewhere: unsloth's Muse Glimmer repo stops
# at UD-Q4_K_XL and would have sent the class rule to the estimate while a repo
# sat in the snapshot looking authoritative, when bartowski publishes the plain
# file. A new name appearing here should be investigated, not added.
NO_PLAIN_Q4 = {"Kimi K3", "DeepSeek V4 Flash 0731"}

estimated = sorted(r["label"] for r in lb if r["open_weight"] and not r.get("vram_measured"))
no_size = sorted({r["label"] for r in lb if r["open_weight"] and not _gguf(r).get("repo")}
                 | NO_PLAIN_Q4)
measured = [r["label"] for r in lb if r["open_weight"] and r.get("vram_measured")]
check("an open model is estimated exactly when no repo supplies its size",
      estimated == no_size,
      f"{len(measured)} measured, estimated: {', '.join(estimated) or 'none'}"
      + (f" | mismatch: {', '.join(sorted(set(estimated) ^ set(no_size)))}"
         if estimated != no_size else ""))
ladder_gap = [r["label"] for r in lb
              if r["open_weight"] and _gguf(r).get("repo")
              and not _gguf(r).get(LOCAL_QUANT) and r["label"] not in NO_PLAIN_Q4]
check(f"every snapshotted repo publishes the {LOCAL_QUANT} the class rule reads",
      not ladder_gap, ", ".join(ladder_gap) or "none")
# head to head
closed = next(r for r in lb if not r["open_weight"]); openw = next(r for r in lb if r["open_weight"])
check("head-to-head: 26 and 52 runs",
      len(C(closed["spec"])) == 26 and len(C(openw["spec"])) == 52,
      f"{len(C(closed['spec']))} and {len(C(openw['spec']))}")
def by_tier(spec):
    out = []
    for t in ("e", "m", "h"):
        g = [x for x in C(spec) if x["task"].startswith(t)]
        out.append(round(100 * sum(1 for x in g if x["solved"] and attempts(x) == 1) / len(g)))
    return out
check("head-to-head: Opus 100/100/100, K3 69/75/69",
      by_tier(closed["spec"]) == [100, 100, 100] and by_tier(openw["spec"]) == [69, 75, 69],
      f"{by_tier(closed['spec'])} vs {by_tier(openw['spec'])}")
# thinking card, Anthropic top tier
for lab, win, mx, sw, sm_ in (("Opus", "anthropic/claude-opus-5@low", "anthropic/claude-opus-5@max", 92.0, 85.0),
                              ("Fable", "anthropic/claude-fable-5@high", "anthropic/claude-fable-5@max", 88.4, 83.7),
                              ("Sonnet", "anthropic/claude-sonnet-5", "anthropic/claude-sonnet-5@max", 83.4, 73.2)):
    check(f"{lab} winner {sw} vs max {sm_}",
          abs(sci(C(win)) - sw) < 0.06 and abs(sci(C(mx)) - sm_) < 0.06,
          f"{sci(C(win)):.1f} / {sci(C(mx)):.1f}")
ratios = [tok(C(m)) / tok(C(w)) for w, m in
          (("anthropic/claude-opus-5@low", "anthropic/claude-opus-5@max"),
           ("anthropic/claude-fable-5@high", "anthropic/claude-fable-5@max"),
           ("anthropic/claude-sonnet-5", "anthropic/claude-sonnet-5@max"))]
check("three to thirty-four times the tokens", 3.0 <= min(ratios) and 33 <= max(ratios) <= 35,
      ", ".join(f"{r:.1f}x" for r in ratios))
check("Sonnet max: 61k tokens, nine minutes",
      59000 < tok(C("anthropic/claude-sonnet-5@max")) < 63000
      and 8.5 < med_time(C("anthropic/claude-sonnet-5@max")) / 60 < 9.5,
      f"{tok(C('anthropic/claude-sonnet-5@max')):.0f}tok {med_time(C('anthropic/claude-sonnet-5@max'))/60:.1f}min")
# Kimi's "a third of the price and a third of the time"
kd, kl = "moonshotai/kimi-k3", "moonshotai/kimi-k3@low"
check("Kimi low: ~3x cheaper and ~3x faster",
      2.6 < med_cost(kd) / med_cost(kl) < 3.4 and 2.6 < med_time(C(kd)) / med_time(C(kl)) < 3.4,
      f"{med_cost(kd)/med_cost(kl):.1f}x, {med_time(C(kd))/med_time(C(kl)):.1f}x")
# habits: Sonnet's drop with the tool
def fisher(a, b, c, d):
    from math import comb
    n = a + b + c + d; r1 = a + b; c1 = a + c
    pf = lambda x: comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    obs = pf(a); lo = max(0, c1 - (n - r1)); hi = min(r1, c1)
    return sum(pf(x) for x in range(lo, hi + 1) if pf(x) <= obs + 1e-12)
sb, smc = C("anthropic/claude-sonnet-5"), C("anthropic/claude-sonnet-5", "mcp")
kb = sum(1 for x in sb if x["solved"] and attempts(x) == 1)
km = sum(1 for x in smc if x["solved"] and attempts(x) == 1)
check("Sonnet 67% -> 50% with the tool, p=0.15",
      round(one(sb)) == 67 and round(one(smc)) == 50 and abs(fisher(kb, len(sb)-kb, km, len(smc)-km) - 0.15) < 0.01,
      f"p={fisher(kb, len(sb)-kb, km, len(smc)-km):.3f}")
# economics: both pro modes 2-3x their max tier
for pro, mx in (("openai/gpt-5.6-terra-pro", "openai/gpt-5.6-terra@max"),
                ("openai/gpt-5.6-luna-pro", "openai/gpt-5.6-luna@max")):
    r = med_cost(pro) / med_cost(mx)
    check(f"{pro.split('/')[-1]} costs 2-3x its max tier", 2.0 <= r <= 3.0, f"{r:.1f}x")
# mechanism: substitution count
ORDER = ["off", "", "minimal", "low", "medium", "high", "xhigh", "max"]
diff = [(r["label"], r["variant"] or "off", mcp[r["label"]]["variant"] or "off")
        for r in lb if r["label"] in mcp
        and (r["variant"] or "off") != (mcp[r["label"]]["variant"] or "off")]
down = [d for d in diff if ORDER.index(d[2]) < ORDER.index(d[1])]
# Read back from the shipped sentence rather than typing the pair: the report
# already derives both numbers, and the typed version drifted silently, still
# claiming "twenty-three" while the prose said twenty-four and the assertion
# only ever looked at the two counts.
_sw = re.search(r"(\w+) of the \d+ models win at a different effort", section_html("What does"))
_dn = re.search(r"and (\w+) of those \w+ move", section_html("What does"))
check(f"the switcher counts match the prose: {len(diff)} differ, {len(down)} downward",
      bool(_sw) and bool(_dn)
      and word(len(diff)) == _sw.group(1) and word(len(down)) == _dn.group(1),
      f"{len(diff)} differ, {len(down)} down")
# chips
check("13 labs", len({r["lab"] for r in lb}) == 13, str(len({r["lab"] for r in lb})))

# The star on a label and the footnote explaining it are set in two different
# places, so they can drift apart: K3's footnote was hardcoded prose while the
# star came from a registry flag, and clearing the flag would have left the
# report explaining an asterisk it no longer printed.
print("\n== weights-pending annotation")
pending = [e["label"] for e in active_models() if e.get("weights_pending")]
noted = report_html.count("weights promised but not yet released")
check("the pending-weights star is explained exactly once, and only when flagged",
      noted == (1 if pending else 0),
      f"flagged: {', '.join(pending) or 'none'}; explanations in report: {noted}")
starred = [e["label"] for e in active_models()
           if e["label"] + "*" in report_html and not e.get("weights_pending")]
check("no unexplained star on a model label", not starred, ", ".join(starred) or "none")

# The README quotes the top of the leaderboard, and it is the first thing anyone
# reads. Nothing else regenerates it, so a sweep that moves a score would leave it
# silently contradicting the report: check it against the same leaderboard() the
# report uses, row by row.
print("\n== README front page")
readme = open("README.md", encoding="utf-8").read()
ROW = re.compile(r"^\| *(\d+) *\| *(.+?) *\| *(.*?) *\| *([\d.]+) ±([\d.]+) *\| *(\d+)% *\|$", re.M)
rows = ROW.findall(readme)
check("README quotes a top-5 table", len(rows) == 5, f"{len(rows)} rows")
for rank, label, variant, score, ci, onesub in rows:
    i = int(rank) - 1
    r = lb[i] if i < len(lb) else None
    ok = bool(r) and r["label"] == label and (r["variant"] or "") == variant \
        and abs(r["sci"] - float(score)) < 0.05 \
        and r["ci"] is not None and abs(r["ci"] - float(ci)) < 0.05 \
        and round(r["raw"]["one_sub_pct"]) == int(onesub)
    check(f"README row {rank}: {label} {variant} {score} +/-{ci} {onesub}%", ok,
          (f"data: {r['label']} {r['variant']} {r['sci']:.1f} +/-{r['ci']:.1f} "
           f"{r['raw']['one_sub_pct']:.0f}%") if r else "no such rank")
# the lede's scale numbers, and the record counts the data section promises
n_lines = sum(1 for _ in open("results/runs/main.jsonl", encoding="utf-8"))
# Modal count, not max: three runs shipped a #[test] inside lib.cairo, which
# snforge collects, so their totals sit one above the task's real test count.
n_tests = sum(st.mode([x["tests_passed"] + x["tests_failed"] for x in runs
                       if x["task"] == t and x["compiled"]])
              for t in {x["task"] for x in runs if x["task"] != "fake"})
for claim, want in [
    ("README lede: models", f"{len(lb)} models from"),
    ("README lede: labs", f"from {len({r['lab'] for r in lb})} labs"),
    ("README lede: runs", f"{len(runs):,}\nagentic runs**"),
    ("README lede: tasks", f"{NT} hand-written contract tasks"),
    ("README lede: hidden tests", f"{n_tests} hidden `snforge` tests"),
    ("README data: records vs analysed", f"holds {n_lines:,} records, the {len(runs):,} analysed"),
]:
    check(claim, want in readme, want.replace("\n", " "))

# The published dataset must never carry transcripts or submitted code. Two
# merges appended sweep records verbatim instead of stripping those fields, and
# 20.8 MB of them sat in the tracked file, and then in git history, until a
# question about a sandbox rename happened to surface it. Cheap to check, and it
# would have caught it the same day.
print("\n== dataset hygiene")
_fat = [f'{r["task"]}/{r["model"]}/rep{r["rep"]}'
        for r in (_json.loads(l) for l in open("results/runs/main.jsonl"))
        if r.get("transcript") or r.get("final_code")]
check("no tracked record carries a transcript or submitted code",
      not _fat, f"{len(_fat)} records: " + ", ".join(_fat[:3]) if _fat else "0 of 7,702")
# The local archive is where that material belongs, and every merge should append
# to both files. Compared by RECORD COUNT rather than by identity tuple: the two
# files disagree on model ids for legacy records (load_runs folds llm_opts effort
# into the id, the archive stores it raw), and parsing 676 MB of transcripts on
# every audit run to normalise them would cost more than the check is worth.
# A count mismatch is exactly the failure this is for: a merge that fed one file
# and forgot the other.
#
# A public clone has neither the archive nor any way to make one, so its absence
# is not a failure: skip.
_arch = "results/runs/main.full.jsonl"
if os.path.exists(_arch):
    _n_arch = sum(1 for _ in open(_arch))
    _n_slim = sum(1 for _ in open("results/runs/main.jsonl"))
    check("the local archive holds one detailed record per published row",
          _n_arch == _n_slim, f"archive {_n_arch:,} vs tracked {_n_slim:,}")
else:
    print("  skip  archive check: main.full.jsonl not present (public clone)")

print(f"\n{'ALL CLAIMS VERIFY' if not fails else str(len(fails)) + ' FAILED: ' + '; '.join(fails)}")
sys.exit(1 if fails else 0)
