"""OpenRouter chat client with usage/cost accounting and retry."""

import json
import time

import httpx
from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError

from . import config

_client = None


def client():
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
            timeout=config.LLM_CALL_TIMEOUT_S,
            max_retries=0,  # we handle retries ourselves to log them
        )
    return _client


RETRIABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _stream_completion(kwargs):
    """Consume a streamed completion into (message, usage, finish_reason).

    The message mimics the SDK's non-streaming shape used by agent.py:
    .content, .tool_calls[].id/.function.name/.arguments, .reasoning_details.
    """
    from types import SimpleNamespace

    stream = client().chat.completions.create(
        **kwargs, stream=True, stream_options={"include_usage": True}
    )
    content, tool_slots, usage, finish = [], {}, None, None
    rd_by_index = {}
    for chunk in stream:
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
        if not chunk.choices:
            continue
        ch = chunk.choices[0]
        if ch.finish_reason:
            finish = ch.finish_reason
        d = ch.delta
        if d is None:
            continue
        if d.content:
            content.append(d.content)
        if d.tool_calls:
            for tc in d.tool_calls:
                slot = tool_slots.setdefault(tc.index, {"id": None, "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function.arguments:
                        slot["arguments"] += tc.function.arguments
        rds = getattr(d, "reasoning_details", None)
        if rds is None and getattr(d, "model_extra", None):
            rds = d.model_extra.get("reasoning_details")
        for rd in rds or []:
            if not isinstance(rd, dict):
                continue
            # Key by (index, id), not index alone: Gemini emits several
            # complete reasoning.encrypted blocks — one per tool call,
            # distinguished only by id — that all carry index 0. Merging
            # them by index concatenates unrelated signature blobs and the
            # provider rejects the replay ("Corrupted thought signature").
            key = (rd.get("index", 0), rd.get("id"))
            slot = rd_by_index.setdefault(key, {})
            for k, v in rd.items():
                if v is None:
                    continue
                if k in ("text", "summary", "data") and isinstance(v, str):
                    # incremental chunks — append in arrival order
                    slot[k] = slot.get(k, "") + v
                else:
                    # metadata (type, format, index) and the trailing
                    # signature delta — keep the latest value; Anthropic
                    # validates the signature over the exact assembled text
                    slot[k] = v
    msg = SimpleNamespace(
        content="".join(content) or None,
        tool_calls=[
            SimpleNamespace(
                id=slot["id"] or f"call_{i}",
                function=SimpleNamespace(name=slot["name"], arguments=slot["arguments"]),
            )
            for i, slot in sorted(tool_slots.items())
        ]
        or None,
        # insertion order = stream arrival order; sorting by the key would
        # interleave same-index blocks from different providers incorrectly
        reasoning_details=list(rd_by_index.values()) or None,
        model_extra=None,
    )
    return msg, usage, finish


def chat(model, messages, tools, temperature=None, reasoning_effort=None,
         provider_sort=None, provider_order=None, max_attempts=5):
    """One chat completion. Returns (message_dict, meta) where meta has
    usage tokens, OpenRouter-reported cost, latency, retries.

    temperature=None means provider default; reasoning_effort e.g. "high"
    is passed via OpenRouter's unified reasoning parameter; provider_sort
    e.g. "throughput" picks the fastest provider for the model.
    provider_order pins routing to the listed providers with fallbacks off —
    required for models whose thought signatures only validate on the
    provider that produced them (e.g. Gemini across AI Studio vs Vertex)."""
    attempt, retries, use_temperature = 0, 0, temperature is not None
    while True:
        attempt += 1
        start = time.monotonic()
        try:
            extra_body = {"usage": {"include": True}}
            if reasoning_effort == "disabled":
                extra_body["reasoning"] = {"enabled": False}
            elif reasoning_effort:
                extra_body["reasoning"] = {"effort": reasoning_effort}
            if provider_order:
                extra_body["provider"] = {"order": provider_order, "allow_fallbacks": False}
            elif provider_sort:
                extra_body["provider"] = {"sort": provider_sort}
            kwargs = dict(
                model=model,
                messages=messages,
                tools=tools,
                extra_body=extra_body,
            )
            if use_temperature:
                kwargs["temperature"] = temperature
            # Streaming keeps bytes flowing during long reasoning phases;
            # non-streaming requests idle for minutes and get killed by
            # network intermediaries (observed with xhigh-effort calls).
            msg, usage, finish_reason = _stream_completion(kwargs)
            latency = time.monotonic() - start
            cost = None
            if usage is not None:
                # OpenRouter returns cost when usage.include=true
                cost = getattr(usage, "cost", None)
                if cost is None and getattr(usage, "model_extra", None):
                    cost = usage.model_extra.get("cost")
            meta = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
                "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
                "cost_usd": cost,
                "latency_s": latency,
                "retries": retries,
                "finish_reason": finish_reason,
            }
            return msg, meta
        except APIStatusError as e:
            # Some providers reject temperature; retry once without it.
            if use_temperature and e.status_code == 400 and "temperature" in str(e.body).lower():
                use_temperature = False
                continue
            if e.status_code in RETRIABLE_STATUS and attempt < max_attempts:
                retries += 1
                time.sleep(min(60, 2 ** attempt))
                continue
            raise
        except (APIConnectionError, APITimeoutError, json.JSONDecodeError, httpx.HTTPError):
            # JSONDecodeError: provider/proxy returned a malformed body.
            # httpx.HTTPError covers mid-stream disconnects (RemoteProtocolError)
            # raised while iterating a streamed response, outside the SDK's
            # own exception mapping.
            if attempt < max_attempts:
                retries += 1
                time.sleep(min(60, 2 ** attempt))
                continue
            raise
