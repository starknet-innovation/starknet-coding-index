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
