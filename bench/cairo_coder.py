"""Bridge to the Cairo Coder API, replicating @kasarlabs/cairo-coder-mcp v0.2.5 exactly.

The MCP package is a thin stdio wrapper: it wraps the query in a fixed template,
POSTs to the public API with `x-api-key` and `mcp: true` headers, and returns the
assistant message text. We reproduce that byte-for-byte (tool name, description,
schema, request template, headers) so results generalize to the real MCP server.
"""

import json
import time
import urllib.request

from . import config

# Lifted verbatim from @kasarlabs/cairo-coder-mcp build/index.js
ASSIST_TOOL_DESCRIPTION = """Provides technical assistance with writing, refactoring, debugging, and understanding Cairo smart contracts and programs.

Call this tool when the user needs to:
- **Write or generate Cairo code** from scratch
- **Refactor or optimize** existing Cairo code
- **Debug compilation errors** or runtime issues
- **Implement specific Cairo features** (traits, storage, events, etc.)
- **Understand Cairo syntax** and best practices
- **Complete TODO sections** in Cairo smart contracts

This tool has access to Cairo documentation, code examples, corelib references, and technical guides."""

# Lifted verbatim from @kasarlabs/cairo-coder-mcp build/schemas.js
ASSIST_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "assist_with_cairo",
        "description": ASSIST_TOOL_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The user's technical question about writing, refactoring, debugging, or understanding Cairo code. Be as specific as possible for better results (e.g., 'How to implement an ERC20 transfer function with OpenZeppelin' rather than just 'ERC20').",
                },
                "codeSnippets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: Code snippets for context. This will help the tool understand the user's intent and provide more accurate answers. Provide as much relevant code as possible to fit the user's request.",
                },
                "history": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: The preceding conversation history. This can help the tool understand the context of the discussion and provide more accurate answers.",
                },
            },
            "required": ["query"],
        },
    },
}


def assist_with_cairo(query, code_snippets=None, history=None):
    """Call the Cairo Coder API the way the MCP server does.

    Returns dict: text, latency_s, usage (Cairo Coder's internal token usage), error.
    """
    # Models occasionally violate the schema and pass non-string items.
    code_snippets = [s if isinstance(s, str) else json.dumps(s) for s in code_snippets or []]
    history = [h if isinstance(h, str) else json.dumps(h) for h in history or []]
    contextual = f"As a Cairo code expert, help with the following technical question:\n\n{query}"
    if code_snippets:
        contextual += "\n\nCode snippets for context:\n" + "\n\n".join(code_snippets)
    if history:
        contextual = (
            "Previous conversation context:\n" + "\n".join(history)
            + "\n\nCurrent query: " + contextual
        )

    body = json.dumps({"messages": [{"role": "user", "content": contextual}]}).encode()
    req = urllib.request.Request(
        config.CAIRO_CODER_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "mcp": "true",
            "x-api-key": config.CAIRO_CODER_API_KEY,
        },
        method="POST",
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=config.CAIRO_CODER_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
        latency = time.monotonic() - start
        text = data["choices"][0]["message"]["content"]
        return {"text": text, "latency_s": latency, "usage": data.get("usage"), "error": None}
    except Exception as e:  # mirror the MCP server: return the error as tool text
        latency = time.monotonic() - start
        return {"text": f"Error: {e}", "latency_s": latency, "usage": None, "error": str(e)}
