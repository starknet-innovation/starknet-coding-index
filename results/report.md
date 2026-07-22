# Cairo Coder MCP benchmark — results

Runs aggregated: 78

| Model | Condition | n | Solve rate | Compile rate | Mean % tests passed | Med. wall time (s) | Med. turns | Med. tokens | Med. cost ($) | Total cost ($) | Mean assist calls |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| z-ai/glm-5.2@high | baseline | 39 | 85% | 92% | 99% | 130 | 5 | 50327 | 0.0820 | 4.01 | 0.0 |
| z-ai/glm-5.2@high | mcp | 39 | 97% | 97% | 100% | 96 | 4 | 28195 | 0.0488 | 2.38 | 0.6 |

## Per-task solve rate (fraction of runs solved)

| Task | z-ai/glm-5.2@high<br>baseline | z-ai/glm-5.2@high<br>mcp |
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
