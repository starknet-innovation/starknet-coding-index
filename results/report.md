# Cairo Coder MCP benchmark — results

Runs aggregated: 390

| Model | Condition | n | Solve rate | Compile rate | Mean % tests passed | Med. wall time (s) | Med. turns | Med. tokens | Med. cost ($) | Total cost ($) | Mean assist calls |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| z-ai/glm-5.2@disabled | baseline | 39 | 74% | 79% | 98% | 42 | 5 | 32562 | 0.0520 | 3.03 | 0.0 |
| z-ai/glm-5.2@disabled | mcp | 39 | 95% | 95% | 100% | 53 | 5 | 32984 | 0.0413 | 1.74 | 1.8 |
| z-ai/glm-5.2@high | baseline | 39 | 85% | 92% | 99% | 130 | 5 | 50327 | 0.0820 | 4.01 | 0.0 |
| z-ai/glm-5.2@high | mcp | 39 | 97% | 97% | 100% | 96 | 4 | 28195 | 0.0488 | 2.38 | 0.6 |
| z-ai/glm-5.2@low | baseline | 39 | 97% | 97% | 100% | 74 | 4 | 37309 | 0.0535 | 3.68 | 0.0 |
| z-ai/glm-5.2@low | mcp | 39 | 100% | 100% | 100% | 74 | 4 | 35155 | 0.0543 | 2.27 | 1.0 |
| z-ai/glm-5.2@medium | baseline | 39 | 90% | 90% | 100% | 76 | 4 | 38733 | 0.0856 | 3.23 | 0.0 |
| z-ai/glm-5.2@medium | mcp | 39 | 95% | 100% | 98% | 69 | 5 | 36937 | 0.0666 | 2.94 | 0.7 |
| z-ai/glm-5.2@xhigh | baseline | 39 | 95% | 97% | 99% | 194 | 3 | 46441 | 0.1473 | 7.00 | 0.0 |
| z-ai/glm-5.2@xhigh | mcp | 39 | 100% | 100% | 100% | 185 | 5 | 46346 | 0.1276 | 5.35 | 1.2 |

## Per-task solve rate (fraction of runs solved)

| Task | z-ai/glm-5.2@disabled<br>baseline | z-ai/glm-5.2@disabled<br>mcp | z-ai/glm-5.2@high<br>baseline | z-ai/glm-5.2@high<br>mcp | z-ai/glm-5.2@low<br>baseline | z-ai/glm-5.2@low<br>mcp | z-ai/glm-5.2@medium<br>baseline | z-ai/glm-5.2@medium<br>mcp | z-ai/glm-5.2@xhigh<br>baseline | z-ai/glm-5.2@xhigh<br>mcp |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| e1_counter | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 |
| e2_ownable | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| e3_registry | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 |
| e4_structs | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| h1_component | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| h2_erc721 | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 |
| h3_vault | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 |
| h4_account | 2/3 | 2/3 | 1/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/3 | 3/3 |
| m1_erc20_capped | 2/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| m2_voting | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 |
| m3_escrow | 2/3 | 3/3 | 1/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 |
| m4_crud | 2/3 | 3/3 | 2/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| m5_dispatcher | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

## Effort-curve findings (added after the 5-mode run, 390 runs total)

| Effort | Baseline solve | MCP solve | Lift | Med wall b->m | Med cost b->m | Assists/run |
|---|---|---|---|---|---|---|
| disabled | 74% | 95% | +21pt | 42s -> 53s | $0.052 -> $0.041 | 1.8 |
| low | 97% | 100% | +3pt | 74s -> 74s | $0.054 -> $0.054 | 1.0 |
| medium | 90% | 95% | +5pt | 76s -> 69s | $0.086 -> $0.067 | 0.7 |
| high | 85% | 97% | +12pt | 130s -> 96s | $0.082 -> $0.049 | 0.6 |
| xhigh | 95% | 100% | +5pt | 194s -> 185s | $0.147 -> $0.128 | 1.2 |

1. **Docs access substitutes for reasoning budget**: MCP lift is largest with thinking disabled (+21pt) and shrinks at higher efforts; assist usage rises as effort falls (1.8/run disabled vs 0.6 at high).
2. **More thinking is not monotonically better**: low baseline (97%) beats medium (90%) and high (85%).
3. **Efficient frontier: low + MCP** — 100% solve at ~74s / $0.054 per run, strictly dominating xhigh + MCP (100% at ~185s / $0.128).
4. Effort-tier MCP runs other than @high used the self-hosted replica (full corpus, same models); local assist calls are ~5x faster than hosted was, slightly flattering non-high MCP wall times.

New-batch spend: ~$29 OpenRouter (xhigh alone ~$12), 312 runs in 33 min at concurrency 20, zero provider errors.
