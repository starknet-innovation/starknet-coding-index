"""Scripted fake model for harness dry-runs (no API spend).

Turn 1: submits deliberately broken code (exercises failure feedback).
Turn 2: if the mcp condition is active, calls assist_with_cairo once.
Next:   submits the task's reference solution (should pass).
"""

import json
from types import SimpleNamespace

from . import config


def _tc(name, args, i):
    return SimpleNamespace(
        id=f"fake_{i}",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def fake_chat(model, messages, tools, **kw):
    task_prompt = messages[1]["content"]
    turn = sum(1 for m in messages if m.get("role") == "assistant") + 1

    # find the task by matching the stub shown in the user message
    task_id = None
    for d in sorted(config.TASKS_DIR.iterdir()):
        if d.is_dir() and (d / "prompt.md").exists():
            if (d / "prompt.md").read_text()[:200] in task_prompt:
                task_id = d.name
                break
    assert task_id, "fake model could not identify task"

    has_mcp = any(t["function"]["name"] == "assist_with_cairo" for t in tools)

    if turn == 1:
        msg = SimpleNamespace(content="", tool_calls=[_tc("submit", {"code": "fn broken() {"}, 1)])
    elif turn == 2 and has_mcp:
        msg = SimpleNamespace(
            content="",
            tool_calls=[_tc("assist_with_cairo", {"query": "How do I define a storage struct in a Starknet contract?"}, 2)],
        )
    else:
        solution = (config.TASKS_DIR / task_id / "solution" / "lib.cairo").read_text()
        msg = SimpleNamespace(content="", tool_calls=[_tc("submit", {"code": solution}, 3)])

    meta = {
        "prompt_tokens": 100, "completion_tokens": 50, "cost_usd": 0.0,
        "latency_s": 0.01, "retries": 0, "finish_reason": "tool_calls",
    }
    return msg, meta
