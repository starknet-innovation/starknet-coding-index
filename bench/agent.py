"""The agentic repair loop: one run of task x model x condition."""

import json
import time

from . import cairo_coder, config, models, workspace

SUBMIT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit",
        "description": (
            "Submit the complete contents of src/lib.cairo. The project is compiled "
            "with `scarb build` and tested with `snforge test` against hidden tests; "
            "the build/test output is returned to you. Submit again with a fixed "
            "version if anything fails."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Full contents of src/lib.cairo (the entire file, not a diff).",
                }
            },
            "required": ["code"],
        },
    },
}

SYSTEM_PROMPT = f"""You are an expert Starknet smart contract developer writing Cairo code.

Toolchain (fixed): Scarb {config.SCARB_VERSION} (Cairo {config.SCARB_VERSION}), Starknet Foundry (snforge) {config.SNFORGE_VERSION}.

Implement the contract described in the task as a single file, src/lib.cairo, inside an existing Scarb package. The package's Scarb.toml is fixed and shown to you; you cannot modify it or add dependencies.

Use the `submit` tool to submit the COMPLETE contents of src/lib.cairo. Hidden tests will run against your code and you will see the build/test output. Keep submitting improved versions until all tests pass. You have a limited number of turns, so make each submission count.

Follow the task's required interface exactly (names, signatures, events): the hidden tests bind to it."""

NUDGE = (
    "Reminder: you must use the `submit` tool with the complete src/lib.cairo "
    "contents. Text replies are not evaluated."
)


def build_user_message(task_id):
    task_dir = config.TASKS_DIR / task_id
    prompt = (task_dir / "prompt.md").read_text()
    scarb_toml = (task_dir / "Scarb.toml").read_text()
    stub = (task_dir / "src" / "lib.cairo").read_text()
    return f"""# Task

{prompt}

# Scarb.toml (fixed, read-only)

```toml
{scarb_toml}
```

# Current src/lib.cairo (stub to replace)

```cairo
{stub}
```"""


def _msg_to_dict(msg):
    d = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return d


def run_agent(task_id, model, condition, run_id, rep, chat_fn=None):
    """Execute one benchmark run. Returns a JSON-serializable result record."""
    chat_fn = chat_fn or models.chat
    ws = workspace.create_workspace(task_id, run_id)
    tools = [SUBMIT_TOOL] + ([cairo_coder.ASSIST_TOOL_SCHEMA] if condition == "mcp" else [])

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(task_id)},
    ]
    transcript = list(messages)

    llm_calls, assist_calls, submissions = [], [], []
    solved, final_eval, final_code, error = False, None, None, None
    start = time.monotonic()

    try:
        for turn in range(1, config.MAX_ASSISTANT_TURNS + 1):
            msg, meta = chat_fn(model, messages, tools)
            meta["turn"] = turn
            llm_calls.append(meta)
            as_dict = _msg_to_dict(msg)
            messages.append(as_dict)
            transcript.append(as_dict)

            if not msg.tool_calls:
                if turn < config.MAX_ASSISTANT_TURNS:
                    nudge = {"role": "user", "content": NUDGE}
                    messages.append(nudge)
                    transcript.append(nudge)
                continue

            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError as e:
                    result_text = f"Error: invalid JSON arguments: {e}"
                    args = None

                if args is not None and tc.function.name == "submit":
                    code = args.get("code", "")
                    ev = workspace.evaluate(ws, code)
                    submissions.append(
                        {
                            "turn": turn,
                            "compiled": ev["compiled"],
                            "tests_passed": ev["tests_passed"],
                            "tests_failed": ev["tests_failed"],
                            "all_passed": ev["all_passed"],
                            "build_time_s": ev["build_time_s"],
                            "test_time_s": ev["test_time_s"],
                        }
                    )
                    final_eval, final_code = ev, code
                    result_text = workspace.truncate_output(ev["output"])
                    if ev["all_passed"]:
                        solved = True
                elif args is not None and tc.function.name == "assist_with_cairo":
                    res = cairo_coder.assist_with_cairo(
                        args.get("query", ""),
                        args.get("codeSnippets"),
                        args.get("history"),
                    )
                    assist_calls.append(
                        {
                            "turn": turn,
                            "query": args.get("query", ""),
                            "latency_s": res["latency_s"],
                            "usage": res["usage"],
                            "error": res["error"],
                        }
                    )
                    result_text = res["text"]
                elif args is not None:
                    result_text = f"Error: unknown tool {tc.function.name}"

                tool_msg = {"role": "tool", "tool_call_id": tc.id, "content": result_text}
                messages.append(tool_msg)
                transcript.append(tool_msg)

            if solved:
                break
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    wall_time = time.monotonic() - start

    def _sum(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) if vals else None

    return {
        "run_id": run_id,
        "task": task_id,
        "model": model,
        "condition": condition,
        "rep": rep,
        "solved": solved,
        "compiled": bool(final_eval and final_eval["compiled"]),
        "tests_passed": final_eval["tests_passed"] if final_eval else 0,
        "tests_failed": final_eval["tests_failed"] if final_eval else 0,
        "turns": len(llm_calls),
        "n_submissions": len(submissions),
        "n_assist_calls": len(assist_calls),
        "wall_time_s": wall_time,
        "prompt_tokens": _sum(m["prompt_tokens"] for m in llm_calls),
        "completion_tokens": _sum(m["completion_tokens"] for m in llm_calls),
        "cost_usd": _sum(m["cost_usd"] for m in llm_calls),
        "assist_time_s": _sum(a["latency_s"] for a in assist_calls) or 0.0,
        "llm_time_s": _sum(m["latency_s"] for m in llm_calls) or 0.0,
        "error": error,
        "llm_calls": llm_calls,
        "assist_calls": assist_calls,
        "submissions": submissions,
        "final_code": final_code,
        "transcript": transcript,
    }
