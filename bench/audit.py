"""Re-verify every published number in the report against the run data.

  uv run python -m bench.audit

Prints OK or FAIL per claim and exits non-zero if any fails, so it can gate a
rebuild or a release. Every figure quoted in results/report.html is checked here
against results/runs/main.jsonl: the leaderboard and its intervals, each FAQ card,
every findings claim, the methodology and caveat numbers, and the chips. If you
change the data, run this before believing the report.
"""
import math
import re
import statistics as st
import sys

from bench.report import load_runs
from bench.sci import attempts, compute_sci, index_ci, leaderboard

runs = load_runs(["results/runs/main.jsonl"])
lb = leaderboard(runs)
by = {r["label"]: r for r in lb}
mcp = {r["label"]: r for r in leaderboard(runs, condition="mcp")}
NT = len({x["task"] for x in runs if x["task"] != "fake"})

C = lambda s, c="baseline": [x for x in runs if x["model"] == s and x["condition"] == c]
one = lambda rs: 100 * sum(1 for x in rs if x["solved"] and attempts(x) == 1) / len(rs)
solve = lambda rs: 100 * sum(1 for x in rs if x["solved"]) / len(rs)
sci = lambda rs: compute_sci(rs)["sci"]
med_cost = lambda s: st.median([x["cost_usd"] for x in C(s) if x["cost_usd"] is not None])


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


pass_cost = lambda s: pass_med(s, lambda rs: sum(x["cost_usd"] or 0 for x in rs))
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
check("19 charted models", len(lb) == 19, f"{len(lb)}")

print("\n== index precision")
worst = max(((index_ci(C(r["spec"])) or 0), r["label"]) for r in lb)
check("every model within +/-5", worst[0] <= 5.0, f"widest {worst[0]:.1f} ({worst[1]})")

print("\n== FAQ cards")
o, f, g, k, mi, s5, sol = (by[n] for n in
    ["Opus 5", "Fable 5", "Grok 4.5", "Kimi K3", "MiMo-V2.5-Pro", "Sonnet 5", "GPT-5.6 Sol"])
check("Opus 100% one-shot", one(C(o["spec"])) == 100, f"{one(C(o['spec'])):.0f}%")
check("Opus has the fastest median pass",
      min((pass_time(by[r["label"]]["spec"]), r["label"]) for r in lb if not r.get("small"))[1] == "Opus 5")
check("Opus is 3.7 clear of second", abs(o["sci"] - f["sci"] - 3.7) < 0.06, f"{o['sci']-f['sci']:.2f}")
check("Fable/Grok 0.4 apart", abs(f["sci"] - g["sci"] - 0.4) < 0.06, f"{f['sci']-g['sci']:.2f}")
check("Fable 96% vs Grok 74% one-shot",
      round(one(C(f["spec"]))) == 96 and round(one(C(g["spec"]))) == 74,
      f"{one(C(f['spec'])):.0f}/{one(C(g['spec'])):.0f}")
check("Grok 9x cheaper per task than Fable", 8.5 <= med_cost(f["spec"]) / med_cost(g["spec"]) <= 9.9,
      f"{med_cost(f['spec'])/med_cost(g['spec']):.1f}x")
check("Kimi 87% vs MiMo 40% one-shot",
      round(one(C(k["spec"]))) == 87 and round(one(C(mi["spec"]))) == 40,
      f"{one(C(k['spec'])):.0f}/{one(C(mi['spec'])):.0f}")
check("Kimi beats MiMo by 4.2", abs(k["sci"] - mi["sci"] - 4.2) < 0.06, f"{k['sci']-mi['sci']:.2f}")
check("MiMo 4.5x faster, 21x cheaper per pass",
      abs(pass_time(k["spec"]) / pass_time(mi["spec"]) - 4.5) < 0.4
      and abs(pass_cost(k["spec"]) / pass_cost(mi["spec"]) - 21) < 2,
      f"{pass_time(k['spec'])/pass_time(mi['spec']):.1f}x / {pass_cost(k['spec'])/pass_cost(mi['spec']):.0f}x")
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
check("Luna stays out of the charts", all(r["label"] != "GPT-5.6 Luna" for r in lb))
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
for lab, want in (("Qwen3.6-27B", 22.0), ("Qwen3.6-35B-A3B", 15.6), ("GLM 5.2", 6.4), ("GPT-5.6 Terra", 9.1),
                  ("GPT-5.6 Sol", 7.9), ("Qwen3 Coder Next", 6.3), ("MiniMax M3", 5.2), ("Hy3", 2.3),
                  ("Opus 5", -0.1), ("Kimi K3", -0.3), ("Fable 5", -1.6),
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
check("terra-pro 51.2 below terra@max 52.6",
      abs(sci(C("openai/gpt-5.6-terra-pro")) - 51.2) < 0.06
      and abs(sci(C("openai/gpt-5.6-terra@max")) - 52.6) < 0.06)
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
check("caveats: 25 to 120 runs per variant", min(ns) == 25 and max(ns) == 120, f"{min(ns)}-{max(ns)}")
# small models pick the same tier in both conditions, and their active-param range
sm = [r for r in lb if r.get("small") and r["label"] in mcp]
check("small models: same tier in both conditions",
      all((r["variant"] or "off") == (mcp[r["label"]]["variant"] or "off") for r in sm))
import json as _json
_meta = _json.load(open("results/model_meta.json"))["models"]
acts = [_meta.get(r["spec"].split("@")[0], {}).get("params_active") for r in sm]
check("small models: 3B to 31B active", all(a for a in acts), str(sorted(set(acts))))
# head to head
closed = next(r for r in lb if not r["open_weight"]); openw = next(r for r in lb if r["open_weight"])
check("head-to-head: 26 and 63 runs",
      len(C(closed["spec"])) == 26 and len(C(openw["spec"])) == 63,
      f"{len(C(closed['spec']))} and {len(C(openw['spec']))}")
def by_tier(spec):
    out = []
    for t in ("e", "m", "h"):
        g = [x for x in C(spec) if x["task"].startswith(t)]
        out.append(round(100 * sum(1 for x in g if x["solved"] and attempts(x) == 1) / len(g)))
    return out
check("head-to-head: Opus 100/100/100, K3 90/100/67",
      by_tier(closed["spec"]) == [100, 100, 100] and by_tier(openw["spec"]) == [90, 100, 67],
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
        for r in lb if not r.get("small") and r["label"] in mcp
        and (r["variant"] or "off") != (mcp[r["label"]]["variant"] or "off")]
down = [d for d in diff if ORDER.index(d[2]) < ORDER.index(d[1])]
check("five of fourteen differ, four downward", len(diff) == 5 and len(down) == 4,
      f"{len(diff)} differ, {len(down)} down")
# chips
check("12 labs", len({r["lab"] for r in lb}) == 12, str(len({r["lab"] for r in lb})))

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

print(f"\n{'ALL CLAIMS VERIFY' if not fails else str(len(fails)) + ' FAILED: ' + '; '.join(fails)}")
sys.exit(1 if fails else 0)
