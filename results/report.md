# Cairo Coder MCP benchmark — results

Runs aggregated: 76

| Model | Condition | n | Solve rate | Compile rate | Mean % tests passed | Med. wall time (s) | Med. turns | Med. tokens | Med. cost ($) | Total cost ($) | Mean assist calls |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| z-ai/glm-5.2 | baseline | 38 | 84% | 92% | 99% | 130 | 5 | 50802 | 0.0759 | 3.93 | 0.0 |
| z-ai/glm-5.2 | mcp | 38 | 97% | 97% | 100% | 96 | 4 | 28590 | 0.0502 | 2.35 | 0.6 |

## Per-task solve rate (fraction of runs solved)

| Task | z-ai/glm-5.2<br>baseline | z-ai/glm-5.2<br>mcp |
|---|--:|--:|
| e1_counter | 3/3 | 3/3 |
| e2_ownable | 3/3 | 3/3 |
| e3_registry | 3/3 | 3/3 |
| e4_structs | 3/3 | 3/3 |
| h1_component | 3/3 | 3/3 |
| h2_erc721 | 3/3 | 3/3 |
| h3_vault | 2/2 | 3/3 |
| h4_account | 1/3 | 2/3 |
| m1_erc20_capped | 2/3 | 3/3 |
| m2_voting | 3/3 | 3/3 |
| m3_escrow | 1/3 | 3/3 |
| m4_crud | 2/3 | 2/2 |
| m5_dispatcher | 3/3 | 3/3 |

## Key findings

1. **Effectiveness**: MCP lifted solve rate 84% → 97% (32/38 → 37/38). All six baseline failures trace to training-data lag on current Cairo idioms — most vividly writing pre-2024 `Map.read(key)` instead of `Map.entry(key).read()` and burning all 10 turns against the compiler. One doc lookup fixed it in the MCP condition.
2. **Efficiency**: −26% median wall time, −44% median tokens, −34% median cost. Among solved-only runs time is a wash (93s vs 96s; each Cairo Coder call costs a median 27s) — the tool pays for itself by preventing expensive 10-turn failures, not by speeding up wins.
3. **Behavior**: the model used `assist_with_cairo` selectively — 20/38 runs, 24 calls, typically after the first compiler error. No tool dependence.
4. **Caveat — confabulation**: Cairo Coder returns confident fabricated interfaces for topics outside its index (verified with an invented "STRK77" standard; real post-indexing STRK20 returned boilerplate). Agents get no out-of-coverage signal.

## Caveats

- Single model (z-ai/glm-5.2, reasoning=high, throughput routing, provider-default temperature).
- Two cells missing due to Cairo Coder token-quota exhaustion (h3_vault baseline rep2, m4_crud mcp rep2); percentages use completed runs. 36 benchmark assist calls consumed ~1.08M Cairo Coder-internal tokens.
- 3 reps: single-task deltas of one solve are noise; suite-level aggregates are the signal.
- Hosted api.cairo-coder.com sunsets 2026-07-31; later reruns require self-hosting.
