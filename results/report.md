# Cairo Coder MCP benchmark — results

Runs aggregated: 4005

| Model | Condition | n | Solve rate | Compile rate | Mean % tests passed | Med. model time (s) | Med. turns | Med. tokens | Med. cost ($) | Total cost ($) | Mean assist calls |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| anthropic/claude-fable-5@high | baseline | 26 | 100% | 100% | 100% | 16 | 1 | 3469 | 0.0874 | 2.41 | 0.0 |
| anthropic/claude-fable-5@max | baseline | 26 | 100% | 100% | 100% | 51 | 1 | 6986 | 0.2802 | 8.76 | 0.0 |
| anthropic/claude-fable-5@minimal | baseline | 26 | 100% | 100% | 100% | 14 | 1 | 3386 | 0.0874 | 2.40 | 0.0 |
| anthropic/claude-haiku-4.5 | baseline | 27 | 89% | 89% | 100% | 29 | 4 | 29293 | 0.0483 | 2.30 | 0.0 |
| anthropic/claude-haiku-4.5 | mcp | 26 | 100% | 100% | 100% | 41 | 4 | 28022 | 0.0484 | 1.46 | 1.7 |
| anthropic/claude-haiku-4.5@high | baseline | 32 | 66% | 69% | 98% | 102 | 5 | 95611 | 0.1688 | 7.16 | 0.0 |
| anthropic/claude-haiku-4.5@low | baseline | 29 | 90% | 90% | 100% | 44 | 4 | 40139 | 0.0685 | 2.92 | 0.0 |
| anthropic/claude-haiku-4.5@low | mcp | 28 | 93% | 93% | 100% | 48 | 3 | 32566 | 0.0618 | 2.22 | 1.5 |
| anthropic/claude-opus-4.8@disabled | baseline | 26 | 100% | 100% | 100% | 14 | 1 | 3395 | 0.0456 | 1.21 | 0.0 |
| anthropic/claude-opus-4.8@high | baseline | 26 | 100% | 100% | 100% | 16 | 1 | 3376 | 0.0442 | 1.16 | 0.0 |
| anthropic/claude-opus-4.8@low | baseline | 26 | 100% | 100% | 100% | 15 | 1 | 3324 | 0.0451 | 1.25 | 0.0 |
| anthropic/claude-sonnet-5 | baseline | 39 | 100% | 100% | 100% | 14 | 1 | 4225 | 0.0236 | 1.02 | 0.0 |
| anthropic/claude-sonnet-5 | mcp | 26 | 100% | 100% | 100% | 15 | 2 | 6636 | 0.0271 | 0.79 | 0.0 |
| anthropic/claude-sonnet-5@high | baseline | 39 | 100% | 100% | 100% | 13 | 1 | 4508 | 0.0248 | 1.06 | 0.0 |
| anthropic/claude-sonnet-5@low | baseline | 39 | 100% | 100% | 100% | 15 | 1 | 5408 | 0.0246 | 1.09 | 0.0 |
| anthropic/claude-sonnet-5@medium | baseline | 39 | 100% | 100% | 100% | 14 | 1 | 4478 | 0.0238 | 1.00 | 0.0 |
| anthropic/claude-sonnet-5@minimal | baseline | 39 | 100% | 100% | 100% | 15 | 2 | 6100 | 0.0253 | 1.15 | 0.0 |
| deepseek/deepseek-v4-pro@disabled | baseline | 39 | 97% | 97% | 100% | 49 | 3 | 18531 | 0.0210 | 1.09 | 0.0 |
| deepseek/deepseek-v4-pro@disabled | mcp | 29 | 90% | 93% | 100% | 110 | 5 | 28797 | 0.0293 | 1.39 | 1.9 |
| deepseek/deepseek-v4-pro@high | baseline | 39 | 97% | 97% | 100% | 145 | 3 | 34542 | 0.0414 | 1.90 | 0.0 |
| deepseek/deepseek-v4-pro@low | baseline | 39 | 95% | 97% | 99% | 98 | 3 | 40059 | 0.0585 | 3.43 | 0.0 |
| deepseek/deepseek-v4-pro@low | mcp | 39 | 97% | 97% | 100% | 90 | 3 | 36742 | 0.0590 | 2.51 | 0.7 |
| deepseek/deepseek-v4-pro@medium | baseline | 39 | 97% | 97% | 100% | 114 | 3 | 24799 | 0.0346 | 1.74 | 0.0 |
| deepseek/deepseek-v4-pro@minimal | baseline | 39 | 97% | 97% | 100% | 139 | 4 | 36152 | 0.0379 | 1.87 | 0.0 |
| deepseek/deepseek-v4-pro@xhigh | baseline | 39 | 95% | 95% | 100% | 214 | 3 | 52847 | 0.0744 | 5.36 | 0.0 |
| deepseek/deepseek-v4-pro@xhigh | mcp | 39 | 100% | 100% | 100% | 196 | 4 | 53324 | 0.0712 | 4.12 | 1.3 |
| fake/model | baseline | 2 | 100% | 100% | 100% | 0 | 2 | 300 | 0.0000 | 0.00 | 0.0 |
| fake/model | mcp | 2 | 100% | 100% | 100% | 35 | 3 | 450 | 0.0000 | 0.00 | 1.0 |
| google/gemini-3.6-flash@high | baseline | 39 | 100% | 100% | 100% | 30 | 2 | 12516 | 0.0651 | 3.06 | 0.0 |
| google/gemini-3.6-flash@low | baseline | 39 | 100% | 100% | 100% | 13 | 2 | 7912 | 0.0289 | 1.40 | 0.0 |
| google/gemini-3.6-flash@low | mcp | 26 | 100% | 100% | 100% | 12 | 2 | 7936 | 0.0292 | 0.90 | 0.1 |
| google/gemini-3.6-flash@max | baseline | 39 | 100% | 100% | 100% | 30 | 2 | 10262 | 0.0608 | 2.85 | 0.0 |
| google/gemini-3.6-flash@medium | baseline | 39 | 100% | 100% | 100% | 24 | 2 | 11206 | 0.0503 | 2.40 | 0.0 |
| google/gemini-3.6-flash@minimal | baseline | 39 | 97% | 97% | 100% | 8 | 2 | 7539 | 0.0231 | 1.10 | 0.0 |
| google/gemini-3.6-flash@minimal | mcp | 26 | 100% | 100% | 100% | 23 | 2 | 6056 | 0.0187 | 0.80 | 0.8 |
| google/gemini-3.6-flash@xhigh | baseline | 39 | 100% | 100% | 100% | 29 | 2 | 11659 | 0.0677 | 2.81 | 0.0 |
| minimax/minimax-m3@high | baseline | 39 | 90% | 97% | 98% | 132 | 2 | 29246 | 0.0242 | 1.82 | 0.0 |
| minimax/minimax-m3@low | baseline | 39 | 77% | 87% | 99% | 158 | 2 | 24849 | 0.0237 | 2.06 | 0.0 |
| minimax/minimax-m3@medium | baseline | 39 | 82% | 92% | 98% | 113 | 2 | 16558 | 0.0187 | 1.74 | 0.0 |
| minimax/minimax-m3@minimal | baseline | 39 | 74% | 85% | 98% | 130 | 2 | 19699 | 0.0215 | 1.93 | 0.0 |
| minimax/minimax-m3@xhigh | baseline | 39 | 87% | 92% | 99% | 81 | 2 | 20659 | 0.0170 | 2.24 | 0.0 |
| minimax/minimax-m3@xhigh | mcp | 39 | 87% | 97% | 98% | 102 | 2 | 28423 | 0.0196 | 2.96 | 0.5 |
| moonshotai/kimi-k3 | baseline | 39 | 100% | 100% | 100% | 97 | 1 | 5578 | 0.0614 | 2.72 | 0.0 |
| moonshotai/kimi-k3 | mcp | 39 | 100% | 100% | 100% | 99 | 1 | 6096 | 0.0627 | 2.50 | 0.0 |
| openai/gpt-5.6-luna-pro | baseline | 39 | 95% | 100% | 99% | 64 | 3 | 73529 | 0.1147 | 6.17 | 0.0 |
| openai/gpt-5.6-luna@disabled | baseline | 39 | 79% | 85% | 98% | 32 | 4 | 21110 | 0.0278 | 1.62 | 0.0 |
| openai/gpt-5.6-luna@disabled | mcp | 29 | 79% | 86% | 98% | 29 | 4 | 20426 | 0.0289 | 1.23 | 0.2 |
| openai/gpt-5.6-luna@high | baseline | 39 | 95% | 97% | 99% | 77 | 4 | 29225 | 0.0505 | 2.46 | 0.0 |
| openai/gpt-5.6-luna@low | baseline | 39 | 85% | 100% | 93% | 72 | 4 | 31610 | 0.0437 | 1.94 | 0.0 |
| openai/gpt-5.6-luna@max | baseline | 39 | 100% | 100% | 100% | 61 | 3 | 23408 | 0.0456 | 2.44 | 0.0 |
| openai/gpt-5.6-luna@medium | baseline | 39 | 97% | 97% | 100% | 69 | 4 | 19482 | 0.0329 | 1.73 | 0.0 |
| openai/gpt-5.6-luna@minimal | baseline | 39 | 82% | 97% | 93% | 59 | 4 | 18360 | 0.0303 | 1.71 | 0.0 |
| openai/gpt-5.6-luna@xhigh | baseline | 39 | 97% | 97% | 100% | 54 | 3 | 14887 | 0.0365 | 2.01 | 0.0 |
| openai/gpt-5.6-luna@xhigh | mcp | 27 | 93% | 96% | 97% | 56 | 3 | 21101 | 0.0403 | 1.44 | 1.0 |
| openai/gpt-5.6-sol@disabled | baseline | 26 | 100% | 100% | 100% | 43 | 2 | 5730 | 0.0723 | 2.04 | 0.0 |
| openai/gpt-5.6-sol@high | baseline | 26 | 100% | 100% | 100% | 48 | 2 | 7264 | 0.0954 | 2.63 | 0.0 |
| openai/gpt-5.6-sol@low | baseline | 26 | 100% | 100% | 100% | 44 | 2 | 6353 | 0.0807 | 2.13 | 0.0 |
| openai/gpt-5.6-terra-pro | baseline | 39 | 92% | 100% | 98% | 44 | 2 | 42094 | 0.2067 | 11.16 | 0.0 |
| openai/gpt-5.6-terra@disabled | baseline | 39 | 90% | 100% | 97% | 35 | 3 | 12503 | 0.0587 | 3.04 | 0.0 |
| openai/gpt-5.6-terra@disabled | mcp | 27 | 96% | 100% | 99% | 33 | 3 | 17489 | 0.0583 | 1.82 | 0.5 |
| openai/gpt-5.6-terra@high | baseline | 39 | 92% | 100% | 98% | 44 | 2 | 11082 | 0.0743 | 3.97 | 0.0 |
| openai/gpt-5.6-terra@low | baseline | 39 | 92% | 100% | 98% | 50 | 3 | 13900 | 0.0684 | 3.36 | 0.0 |
| openai/gpt-5.6-terra@max | baseline | 39 | 97% | 100% | 99% | 55 | 2 | 12838 | 0.0930 | 4.60 | 0.0 |
| openai/gpt-5.6-terra@medium | baseline | 39 | 100% | 100% | 100% | 53 | 3 | 15971 | 0.0734 | 3.18 | 0.0 |
| openai/gpt-5.6-terra@minimal | baseline | 39 | 95% | 97% | 99% | 46 | 3 | 11427 | 0.0638 | 3.35 | 0.0 |
| openai/gpt-5.6-terra@minimal | mcp | 27 | 96% | 100% | 99% | 39 | 3 | 11474 | 0.0572 | 2.03 | 0.6 |
| openai/gpt-5.6-terra@xhigh | baseline | 39 | 95% | 97% | 99% | 54 | 3 | 14253 | 0.0816 | 4.54 | 0.0 |
| qwen/qwen3.6-27b@xhigh | baseline | 39 | 23% | 28% | 100% | 719 | 10 | 266332 | 0.2685 | 10.36 | 0.0 |
| qwen/qwen3.6-27b@xhigh | mcp | 39 | 41% | 59% | 94% | 570 | 10 | 221453 | 0.1879 | 8.80 | 1.3 |
| tencent/hy3 | baseline | 39 | 87% | 95% | 100% | 144 | 3 | 41071 | 0.0154 | 1.01 | 0.0 |
| tencent/hy3 | mcp | 39 | 95% | 97% | 100% | 156 | 4 | 61559 | 0.0154 | 0.86 | 0.5 |
| tencent/hy3@disabled | baseline | 39 | 67% | 74% | 97% | 179 | 7 | 62672 | 0.0097 | 0.42 | 0.0 |
| tencent/hy3@high | baseline | 39 | 90% | 97% | 100% | 207 | 3 | 45641 | 0.0122 | 0.97 | 0.0 |
| tencent/hy3@high | mcp | 39 | 85% | 97% | 99% | 173 | 4 | 51563 | 0.0102 | 1.02 | 0.3 |
| tencent/hy3@low | baseline | 39 | 87% | 90% | 100% | 154 | 3 | 39109 | 0.0091 | 0.91 | 0.0 |
| tencent/hy3@low | mcp | 39 | 95% | 97% | 100% | 174 | 3 | 42702 | 0.0116 | 0.66 | 0.3 |
| tencent/hy3@medium | baseline | 39 | 72% | 77% | 99% | 242 | 4 | 54152 | 0.0111 | 0.71 | 0.0 |
| tencent/hy3@minimal | baseline | 39 | 72% | 77% | 99% | 303 | 3 | 40719 | 0.0099 | 0.67 | 0.0 |
| tencent/hy3@xhigh | baseline | 39 | 77% | 90% | 99% | 404 | 3 | 59454 | 0.0157 | 0.76 | 0.0 |
| xiaomi/mimo-v2.5-pro@disabled | baseline | 39 | 100% | 100% | 100% | 43 | 2 | 6343 | 0.0063 | 0.32 | 0.0 |
| xiaomi/mimo-v2.5-pro@high | baseline | 39 | 100% | 100% | 100% | 49 | 2 | 5424 | 0.0051 | 0.33 | 0.0 |
| xiaomi/mimo-v2.5-pro@low | baseline | 39 | 100% | 100% | 100% | 25 | 2 | 6815 | 0.0065 | 0.39 | 0.0 |
| xiaomi/mimo-v2.5-pro@low | mcp | 39 | 100% | 100% | 100% | 30 | 2 | 7672 | 0.0079 | 0.64 | 0.3 |
| xiaomi/mimo-v2.5-pro@max | baseline | 39 | 100% | 100% | 100% | 46 | 2 | 5254 | 0.0047 | 0.29 | 0.0 |
| xiaomi/mimo-v2.5-pro@medium | baseline | 39 | 100% | 100% | 100% | 47 | 2 | 5327 | 0.0059 | 0.30 | 0.0 |
| xiaomi/mimo-v2.5-pro@minimal | baseline | 39 | 100% | 100% | 100% | 44 | 2 | 6438 | 0.0060 | 0.29 | 0.0 |
| xiaomi/mimo-v2.5-pro@xhigh | baseline | 39 | 100% | 100% | 100% | 19 | 2 | 4398 | 0.0044 | 0.34 | 0.0 |
| xiaomi/mimo-v2.5-pro@xhigh | mcp | 39 | 97% | 97% | 100% | 18 | 2 | 4982 | 0.0049 | 0.29 | 0.0 |
| z-ai/glm-5.2@disabled | baseline | 39 | 74% | 79% | 98% | 39 | 5 | 32562 | 0.0520 | 3.03 | 0.0 |
| z-ai/glm-5.2@disabled | mcp | 39 | 95% | 95% | 100% | 49 | 5 | 32984 | 0.0413 | 1.74 | 1.8 |
| z-ai/glm-5.2@high | baseline | 144 | 84% | 87% | 100% | 91 | 5 | 41302 | 0.0747 | 15.19 | 0.0 |
| z-ai/glm-5.2@high | mcp | 92 | 98% | 98% | 100% | 78 | 4 | 30222 | 0.0531 | 5.93 | 0.7 |
| z-ai/glm-5.2@low | baseline | 130 | 91% | 92% | 100% | 76 | 5 | 40776 | 0.0780 | 15.26 | 0.0 |
| z-ai/glm-5.2@low | mcp | 130 | 98% | 98% | 100% | 51 | 5 | 33200 | 0.0556 | 8.90 | 0.9 |
| z-ai/glm-5.2@medium | baseline | 130 | 90% | 91% | 100% | 70 | 5 | 35371 | 0.0831 | 12.95 | 0.0 |
| z-ai/glm-5.2@medium | mcp | 130 | 95% | 99% | 99% | 55 | 5 | 37298 | 0.0632 | 9.33 | 0.8 |
| z-ai/glm-5.2@xhigh | baseline | 39 | 95% | 97% | 99% | 186 | 3 | 46441 | 0.1473 | 7.00 | 0.0 |
| z-ai/glm-5.2@xhigh | mcp | 39 | 100% | 100% | 100% | 181 | 5 | 46346 | 0.1276 | 5.35 | 1.2 |

## Per-task solve rate (fraction of runs solved)

| Task | anthropic/claude-fable-5@high<br>baseline | anthropic/claude-fable-5@max<br>baseline | anthropic/claude-fable-5@minimal<br>baseline | anthropic/claude-haiku-4.5<br>baseline | anthropic/claude-haiku-4.5<br>mcp | anthropic/claude-haiku-4.5@high<br>baseline | anthropic/claude-haiku-4.5@low<br>baseline | anthropic/claude-haiku-4.5@low<br>mcp | anthropic/claude-opus-4.8@disabled<br>baseline | anthropic/claude-opus-4.8@high<br>baseline | anthropic/claude-opus-4.8@low<br>baseline | anthropic/claude-sonnet-5<br>baseline | anthropic/claude-sonnet-5<br>mcp | anthropic/claude-sonnet-5@high<br>baseline | anthropic/claude-sonnet-5@low<br>baseline | anthropic/claude-sonnet-5@medium<br>baseline | anthropic/claude-sonnet-5@minimal<br>baseline | deepseek/deepseek-v4-pro@disabled<br>baseline | deepseek/deepseek-v4-pro@disabled<br>mcp | deepseek/deepseek-v4-pro@high<br>baseline | deepseek/deepseek-v4-pro@low<br>baseline | deepseek/deepseek-v4-pro@low<br>mcp | deepseek/deepseek-v4-pro@medium<br>baseline | deepseek/deepseek-v4-pro@minimal<br>baseline | deepseek/deepseek-v4-pro@xhigh<br>baseline | deepseek/deepseek-v4-pro@xhigh<br>mcp | fake/model<br>baseline | fake/model<br>mcp | google/gemini-3.6-flash@high<br>baseline | google/gemini-3.6-flash@low<br>baseline | google/gemini-3.6-flash@low<br>mcp | google/gemini-3.6-flash@max<br>baseline | google/gemini-3.6-flash@medium<br>baseline | google/gemini-3.6-flash@minimal<br>baseline | google/gemini-3.6-flash@minimal<br>mcp | google/gemini-3.6-flash@xhigh<br>baseline | minimax/minimax-m3@high<br>baseline | minimax/minimax-m3@low<br>baseline | minimax/minimax-m3@medium<br>baseline | minimax/minimax-m3@minimal<br>baseline | minimax/minimax-m3@xhigh<br>baseline | minimax/minimax-m3@xhigh<br>mcp | moonshotai/kimi-k3<br>baseline | moonshotai/kimi-k3<br>mcp | openai/gpt-5.6-luna-pro<br>baseline | openai/gpt-5.6-luna@disabled<br>baseline | openai/gpt-5.6-luna@disabled<br>mcp | openai/gpt-5.6-luna@high<br>baseline | openai/gpt-5.6-luna@low<br>baseline | openai/gpt-5.6-luna@max<br>baseline | openai/gpt-5.6-luna@medium<br>baseline | openai/gpt-5.6-luna@minimal<br>baseline | openai/gpt-5.6-luna@xhigh<br>baseline | openai/gpt-5.6-luna@xhigh<br>mcp | openai/gpt-5.6-sol@disabled<br>baseline | openai/gpt-5.6-sol@high<br>baseline | openai/gpt-5.6-sol@low<br>baseline | openai/gpt-5.6-terra-pro<br>baseline | openai/gpt-5.6-terra@disabled<br>baseline | openai/gpt-5.6-terra@disabled<br>mcp | openai/gpt-5.6-terra@high<br>baseline | openai/gpt-5.6-terra@low<br>baseline | openai/gpt-5.6-terra@max<br>baseline | openai/gpt-5.6-terra@medium<br>baseline | openai/gpt-5.6-terra@minimal<br>baseline | openai/gpt-5.6-terra@minimal<br>mcp | openai/gpt-5.6-terra@xhigh<br>baseline | qwen/qwen3.6-27b@xhigh<br>baseline | qwen/qwen3.6-27b@xhigh<br>mcp | tencent/hy3<br>baseline | tencent/hy3<br>mcp | tencent/hy3@disabled<br>baseline | tencent/hy3@high<br>baseline | tencent/hy3@high<br>mcp | tencent/hy3@low<br>baseline | tencent/hy3@low<br>mcp | tencent/hy3@medium<br>baseline | tencent/hy3@minimal<br>baseline | tencent/hy3@xhigh<br>baseline | xiaomi/mimo-v2.5-pro@disabled<br>baseline | xiaomi/mimo-v2.5-pro@high<br>baseline | xiaomi/mimo-v2.5-pro@low<br>baseline | xiaomi/mimo-v2.5-pro@low<br>mcp | xiaomi/mimo-v2.5-pro@max<br>baseline | xiaomi/mimo-v2.5-pro@medium<br>baseline | xiaomi/mimo-v2.5-pro@minimal<br>baseline | xiaomi/mimo-v2.5-pro@xhigh<br>baseline | xiaomi/mimo-v2.5-pro@xhigh<br>mcp | z-ai/glm-5.2@disabled<br>baseline | z-ai/glm-5.2@disabled<br>mcp | z-ai/glm-5.2@high<br>baseline | z-ai/glm-5.2@high<br>mcp | z-ai/glm-5.2@low<br>baseline | z-ai/glm-5.2@low<br>mcp | z-ai/glm-5.2@medium<br>baseline | z-ai/glm-5.2@medium<br>mcp | z-ai/glm-5.2@xhigh<br>baseline | z-ai/glm-5.2@xhigh<br>mcp |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| e1_counter | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 | 1/1 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 11/11 | 7/7 | 10/10 | 10/10 | 10/10 | 9/10 | 3/3 | 3/3 |
| e2_ownable | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 2/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 | 8/8 | 9/10 | 10/10 | 8/10 | 10/10 | 3/3 | 3/3 |
| e3_registry | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 2/3 | 2/2 | 3/3 | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 0/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 9/11 | 7/7 | 10/10 | 10/10 | 9/10 | 8/10 | 3/3 | 3/3 |
| e4_structs | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 11/11 | 7/7 | 10/10 | 10/10 | 10/10 | 10/10 | 3/3 | 3/3 |
| h1_component | 2/2 | 2/2 | 2/2 | 0/2 | 2/2 | 1/3 | 2/3 | 2/3 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 2/3 | 0/3 | 1/3 | 0/3 | 1/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 0/3 | 0/3 | 1/3 | 2/3 | 0/3 | 2/3 | 1/3 | 0/3 | 2/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 11/11 | 6/7 | 10/10 | 10/10 | 9/10 | 10/10 | 3/3 | 3/3 |
| h2_erc721 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/3 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 1/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 3/3 | 2/3 | 3/3 | 3/3 | 2/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 0/3 | 0/3 | 3/3 | 3/3 | 2/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 10/11 | 7/7 | 9/10 | 10/10 | 8/10 | 10/10 | 3/3 | 3/3 |
| h3_vault | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/3 | 2/2 | 2/3 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 9/11 | 7/7 | 9/10 | 9/10 | 10/10 | 9/10 | 3/3 | 3/3 |
| h4_account | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 1/3 | 0/3 | 2/3 | 1/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 0/3 | 0/2 | 3/3 | 1/3 | 3/3 | 3/3 | 1/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 0/3 | 0/3 | 0/3 | 3/3 | 1/3 | 2/3 | 2/3 | 3/3 | 2/3 | 0/3 | 0/3 | 0/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 5/11 | 6/7 | 8/10 | 10/10 | 9/10 | 10/10 | 1/3 | 3/3 |
| m1_erc20_capped | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 3/3 | 2/3 | 3/3 | 3/3 | 1/3 | 2/3 | 1/3 | 1/3 | 2/3 | 3/3 | 3/3 | 3/3 | 2/3 | 1/3 | 2/2 | 2/2 | 2/2 | 0/3 | 1/3 | 2/2 | 0/3 | 0/3 | 2/3 | 3/3 | 1/3 | 2/3 | 1/3 | 0/3 | 1/3 | 3/3 | 2/3 | 1/3 | 3/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 8/11 | 7/7 | 8/10 | 9/10 | 10/10 | 10/10 | 3/3 | 3/3 |
| m2_voting | 2/2 | 2/2 | 2/2 | 2/3 | 2/2 | 2/3 | 2/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/1 | 1/1 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 1/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 1/3 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 1/3 | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 1/3 | 3/3 | 10/11 | 7/7 | 8/10 | 10/10 | 9/10 | 10/10 | 3/3 | 3/3 |
| m3_escrow | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/3 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 2/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 0/3 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 3/3 | 2/3 | 3/3 | 2/3 | 0/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 3/3 | 5/11 | 7/7 | 9/10 | 9/10 | 7/10 | 9/10 | 3/3 | 3/3 |
| m4_crud | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/3 | 2/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 0/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 10/11 | 7/7 | 9/10 | 10/10 | 10/10 | 9/10 | 3/3 | 3/3 |
| m5_dispatcher | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | — | — | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 2/2 | 2/2 | 2/2 | 2/2 | 3/3 | 3/3 | 2/2 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 2/2 | 3/3 | 1/3 | 1/3 | 3/3 | 3/3 | 1/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 10/11 | 7/7 | 9/10 | 10/10 | 8/10 | 10/10 | 3/3 | 3/3 |
