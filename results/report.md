# Cairo Coder MCP benchmark — results

Runs aggregated: 962

| Model | Condition | n | Solve rate | Compile rate | Mean % tests passed | Med. wall time (s) | Med. turns | Med. tokens | Med. cost ($) | Total cost ($) | Mean assist calls |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| moonshotai/kimi-k3 | baseline | 39 | 100% | 100% | 100% | 100 | 1 | 5578 | 0.0614 | 2.72 | 0.0 |
| moonshotai/kimi-k3 | mcp | 39 | 100% | 100% | 100% | 102 | 1 | 6096 | 0.0627 | 2.50 | 0.0 |
| z-ai/glm-5.2@disabled | baseline | 39 | 74% | 79% | 98% | 42 | 5 | 32562 | 0.0520 | 3.03 | 0.0 |
| z-ai/glm-5.2@disabled | mcp | 39 | 95% | 95% | 100% | 53 | 5 | 32984 | 0.0413 | 1.74 | 1.8 |
| z-ai/glm-5.2@high | baseline | 130 | 84% | 86% | 100% | 87 | 5 | 41802 | 0.0803 | 14.47 | 0.0 |
| z-ai/glm-5.2@high | mcp | 78 | 97% | 97% | 100% | 80 | 4 | 29064 | 0.0549 | 5.39 | 0.7 |
| z-ai/glm-5.2@low | baseline | 130 | 91% | 92% | 100% | 81 | 5 | 40776 | 0.0780 | 15.26 | 0.0 |
| z-ai/glm-5.2@low | mcp | 130 | 98% | 98% | 100% | 57 | 5 | 33200 | 0.0556 | 8.90 | 0.9 |
| z-ai/glm-5.2@medium | baseline | 130 | 90% | 91% | 100% | 75 | 5 | 35371 | 0.0831 | 12.95 | 0.0 |
| z-ai/glm-5.2@medium | mcp | 130 | 95% | 99% | 99% | 60 | 5 | 37298 | 0.0632 | 9.33 | 0.8 |
| z-ai/glm-5.2@xhigh | baseline | 39 | 95% | 97% | 99% | 194 | 3 | 46441 | 0.1473 | 7.00 | 0.0 |
| z-ai/glm-5.2@xhigh | mcp | 39 | 100% | 100% | 100% | 185 | 5 | 46346 | 0.1276 | 5.35 | 1.2 |

## Per-task solve rate (fraction of runs solved)

| Task | moonshotai/kimi-k3<br>baseline | moonshotai/kimi-k3<br>mcp | z-ai/glm-5.2@disabled<br>baseline | z-ai/glm-5.2@disabled<br>mcp | z-ai/glm-5.2@high<br>baseline | z-ai/glm-5.2@high<br>mcp | z-ai/glm-5.2@low<br>baseline | z-ai/glm-5.2@low<br>mcp | z-ai/glm-5.2@medium<br>baseline | z-ai/glm-5.2@medium<br>mcp | z-ai/glm-5.2@xhigh<br>baseline | z-ai/glm-5.2@xhigh<br>mcp |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| e1_counter | 3/3 | 3/3 | 3/3 | 3/3 | 10/10 | 6/6 | 10/10 | 10/10 | 10/10 | 9/10 | 3/3 | 3/3 |
| e2_ownable | 3/3 | 3/3 | 3/3 | 3/3 | 10/10 | 6/6 | 9/10 | 10/10 | 8/10 | 10/10 | 3/3 | 3/3 |
| e3_registry | 3/3 | 3/3 | 2/3 | 3/3 | 8/10 | 6/6 | 10/10 | 10/10 | 9/10 | 8/10 | 3/3 | 3/3 |
| e4_structs | 3/3 | 3/3 | 3/3 | 3/3 | 10/10 | 6/6 | 10/10 | 10/10 | 10/10 | 10/10 | 3/3 | 3/3 |
| h1_component | 3/3 | 3/3 | 2/3 | 3/3 | 10/10 | 5/6 | 10/10 | 10/10 | 9/10 | 10/10 | 3/3 | 3/3 |
| h2_erc721 | 3/3 | 3/3 | 2/3 | 2/3 | 9/10 | 6/6 | 9/10 | 10/10 | 8/10 | 10/10 | 3/3 | 3/3 |
| h3_vault | 3/3 | 3/3 | 2/3 | 3/3 | 9/10 | 6/6 | 9/10 | 9/10 | 10/10 | 9/10 | 3/3 | 3/3 |
| h4_account | 3/3 | 3/3 | 2/3 | 2/3 | 4/10 | 5/6 | 8/10 | 10/10 | 9/10 | 10/10 | 1/3 | 3/3 |
| m1_erc20_capped | 3/3 | 3/3 | 2/3 | 3/3 | 7/10 | 6/6 | 8/10 | 9/10 | 10/10 | 10/10 | 3/3 | 3/3 |
| m2_voting | 3/3 | 3/3 | 1/3 | 3/3 | 9/10 | 6/6 | 8/10 | 10/10 | 9/10 | 10/10 | 3/3 | 3/3 |
| m3_escrow | 3/3 | 3/3 | 2/3 | 3/3 | 4/10 | 6/6 | 9/10 | 9/10 | 7/10 | 9/10 | 3/3 | 3/3 |
| m4_crud | 3/3 | 3/3 | 2/3 | 3/3 | 9/10 | 6/6 | 9/10 | 10/10 | 10/10 | 9/10 | 3/3 | 3/3 |
| m5_dispatcher | 3/3 | 3/3 | 3/3 | 3/3 | 10/10 | 6/6 | 9/10 | 10/10 | 8/10 | 10/10 | 3/3 | 3/3 |

## Lab roster (2026-07-23): best open-weight coder per top Chinese lab, max thinking (78 runs each)

| Lab / model | Baseline | MCP | Lift | Med wall b/m | Med cost b/m | Assists/run |
|---|---|---|---|---|---|---|
| Moonshot Kimi K3 | 100% | 100% | 0 | 100s/102s | $0.061/$0.063 | 0.0 |
| Xiaomi MiMo-V2.5-Pro @xhigh | 100% | 97% | -3 | 23s/20s | $0.004/$0.005 | 0.0 |
| DeepSeek V4-Pro @xhigh | 95% | 100% | +5 | 225s/211s | $0.074/$0.071 | 1.3 |
| Tencent Hy3 | 95% | 95% | 0 | 148s/159s | $0.015/$0.015 | 0.5 |
| Z.ai GLM 5.2 @xhigh | 95% | 100% | +5 | 194s/185s | $0.147/$0.128 | 1.2 |
| MiniMax M3 @xhigh | 87% | 90% | +3 | 86s/104s | $0.018/$0.020 | 0.5 |
| Alibaba Qwen3.6-27B @xhigh | 28% | 49% | +21 | 852s/613s | $0.269/$0.188 | 1.3 |

Findings: (1) the knowledge-gap law holds across labs — MCP lift is zero at saturation, largest for the weakest model; (2) MiMo-V2.5-Pro is the efficiency standout (100% at ~23s/$0.004 per task, ~15x cheaper than K3); (3) Qwen3.6-27B collapses on Cairo despite strong general-coding benchmarks — language-specific knowledge is what the MCP substitutes for; (4) Hy3 (released 2026-07-06, freshest data) hits 95% without needing the tool. Notes: 5 qwen/minimax baseline cells abandoned after repeated host-sleep/network stalls, counted as failures (consistent with sibling reps); roster ran with streaming + reasoning-history passthrough. Roster spend: ~$48.

## Effort-pattern generalization (2026-07-23; +312 runs; 1664 total)

| Model / tier | Baseline | MCP | Note |
|---|---|---|---|
| DeepSeek V4-Pro @low | 94.9% | 97.4% | ~2x faster/cheaper than xhigh |
| DeepSeek V4-Pro @xhigh | 94.9% | 100% | |
| Tencent Hy3 @low | 89.7% | 94.9% | MCP repays the effort gap |
| Tencent Hy3 @high | 97.4% | 92.3% | bare default == high tier (~14k rtoks) |
| MiMo-V2.5-Pro @low | 100% | 100% | knowledge-saturated, effort irrelevant |
| MiMo-V2.5-Pro @xhigh | 100% | 97.4% | |

Verdict: GLM's "extra thinking buys nothing" holds for DeepSeek and MiMo; Hy3 is the counterexample (high tier genuinely better at baseline, +7.7pt). The substitution law is universal: MCP lift appears exactly where reasoning/knowledge falls short (hy3@low +5pt), never at saturation. Probes: deepseek low=medium=high collapse to one tier (xhigh 5-10x more reasoning); hy3 has two real tiers; mimo's ladder is cosmetic. Two harness bugs found+fixed at 50-way concurrency: non-string codeSnippets from models crash-proofed (cairo_coder.py), mid-stream disconnects now retried (models.py httpx.HTTPError). Batch: 312 runs in 42 min at concurrency 50, ~$12.

## Starknet Coding Index — SCI v1 (2026-07-23, baseline condition)

SCI = 0.50*Correctness + 0.15*OneShot + 0.15*Speed + 0.15*Cost + 0.05*TokenEfficiency (0-100).
Correctness = mean hidden-test pass fraction; resource scores use fixed log anchors
(speed 20s->1200s, cost $0.003->$0.60, tokens 1k->40k) so future models never reshuffle
existing scores. Max-thinking config, 39 baseline runs/model, 10-turn budget. All current
entrants are open-weight; the chart distinguishes open vs closed for future additions.

| # | Model | SCI | Correct | 1-shot | Speed | Cost | Tokens |
|--:|---|--:|--:|--:|--:|--:|--:|
| 1 | MiMo-V2.5-Pro | 89.1 | 100.0 | 41 | 97 | 93 | 90 |
| 2 | Kimi K3 | 82.3 | 100.0 | 90 | 61 | 43 | 65 |
| 3 | MiniMax M3 | 71.4 | 91.0 | 31 | 65 | 67 | 31 |
| 4 | Hy3 | 67.7 | 94.9 | 5 | 51 | 69 | 29 |
| 5 | DeepSeek V4-Pro | 60.7 | 94.9 | 0 | 41 | 39 | 24 |
| 6 | GLM 5.2 | 59.5 | 96.8 | 0 | 45 | 27 | 8 |
| 7 | Qwen3.6-27B | 17.6 | 28.2 | 0 | 8 | 15 | 0 |

## SCI policy update (2026-07-23): best variant per model, labeled

The leaderboard now scores each model at its best-performing benchmarked variant
(was: max thinking), with the variant labeled per bar. Changes: Hy3 default->@high
(67.7->69.1), DeepSeek @xhigh->@low (60.7->65.6), GLM @xhigh->@low (59.5->63.5).
No rank flips except DeepSeek/GLM tightening behind Hy3. MiMo's best remains @xhigh
(89.1); its @low scores 83.4. Rationale: SCI includes efficiency, and for GLM/DeepSeek
max thinking buys no correctness at 2-3x the time/cost.
