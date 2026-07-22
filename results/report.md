# Cairo Coder MCP benchmark — results

Runs aggregated: 26

| Model | Condition | n | Solve rate | Compile rate | Mean % tests passed | Med. wall time (s) | Med. turns | Med. tokens | Med. cost ($) | Total cost ($) | Mean assist calls |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| z-ai/glm-5.2 | baseline | 13 | 92% | 92% | 100% | 250 | 4 | 35784 | 0.0421 | 0.69 | 0.0 |
| z-ai/glm-5.2 | mcp | 13 | 100% | 100% | 100% | 272 | 5 | 43068 | 0.0384 | 0.53 | 0.9 |

## Per-task solve rate (fraction of runs solved)

| Task | z-ai/glm-5.2<br>baseline | z-ai/glm-5.2<br>mcp |
|---|--:|--:|
| e1_counter | 1/1 | 1/1 |
| e2_ownable | 1/1 | 1/1 |
| e3_registry | 1/1 | 1/1 |
| e4_structs | 1/1 | 1/1 |
| h1_component | 1/1 | 1/1 |
| h2_erc721 | 1/1 | 1/1 |
| h3_vault | 1/1 | 1/1 |
| h4_account | 1/1 | 1/1 |
| m1_erc20_capped | 1/1 | 1/1 |
| m2_voting | 1/1 | 1/1 |
| m3_escrow | 1/1 | 1/1 |
| m4_crud | 1/1 | 1/1 |
| m5_dispatcher | 0/1 | 1/1 |
