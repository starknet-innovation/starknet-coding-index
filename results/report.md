# Cairo Coder MCP benchmark — results

Runs aggregated: 78

| Model | Condition | n | Solve rate | Compile rate | Mean % tests passed | Med. wall time (s) | Med. turns | Med. tokens | Med. cost ($) | Total cost ($) | Mean assist calls |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| z-ai/glm-5.2 | baseline | 39 | 85% | 92% | 99% | 130 | 5 | 50327 | 0.0820 | 4.01 | 0.0 |
| z-ai/glm-5.2 | mcp | 39 | 97% | 97% | 100% | 96 | 4 | 28195 | 0.0488 | 2.38 | 0.6 |

## Per-task solve rate (fraction of runs solved)

| Task | z-ai/glm-5.2<br>baseline | z-ai/glm-5.2<br>mcp |
|---|--:|--:|
| e1_counter | 3/3 | 3/3 |
| e2_ownable | 3/3 | 3/3 |
| e3_registry | 3/3 | 3/3 |
| e4_structs | 3/3 | 3/3 |
| h1_component | 3/3 | 3/3 |
| h2_erc721 | 3/3 | 3/3 |
| h3_vault | 3/3 | 3/3 |
| h4_account | 1/3 | 2/3 |
| m1_erc20_capped | 2/3 | 3/3 |
| m2_voting | 3/3 | 3/3 |
| m3_escrow | 1/3 | 3/3 |
| m4_crud | 2/3 | 3/3 |
| m5_dispatcher | 3/3 | 3/3 |

## Key findings

1. **Effectiveness**: MCP lifted solve rate 85% -> 97% (33/39 -> 38/39). All baseline failures trace to training-data lag on current Cairo idioms (e.g. pre-2024 `Map.read(key)` vs today's `Map.entry(key).read()`).
2. **Efficiency**: -26% median wall time, -44% median tokens, -40% median cost. Among solved-only runs time is a wash; the tool pays for itself by preventing expensive 10-turn failures, not by speeding up wins (each assist call costs a median 27s).
3. **Behavior**: assist_with_cairo used selectively (about half of MCP runs, typically after the first compiler error). No tool dependence.
4. **Caveat - confabulation**: Cairo Coder returns confident fabricated interfaces for topics outside its index (verified with an invented "STRK77" standard). Agents get no out-of-coverage signal.

## Caveats

- Single model (z-ai/glm-5.2, reasoning=high, throughput routing, provider-default temperature).
- Two cells (h3_vault baseline rep2, m4_crud mcp rep2) ran against a self-hosted Cairo Coder replica after the hosted key's quota died mid-run: same embedding + generation models, same corpus minus the starknet-blog source, routed via OpenRouter. See README "Self-hosted Cairo Coder".
- 3 reps: single-task deltas of one solve are noise; suite-level aggregates are the signal.
- Hosted api.cairo-coder.com sunsets 2026-07-31; the self-hosted deployment replaces it for future runs.
