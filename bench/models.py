"""OpenRouter chat client with usage/cost accounting and retry."""

import json
import time

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


def chat(model, messages, tools, temperature=None, reasoning_effort=None, max_attempts=5):
    """One chat completion. Returns (message_dict, meta) where meta has
    usage tokens, OpenRouter-reported cost, latency, retries.

    temperature=None means provider default; reasoning_effort e.g. "high"
    is passed via OpenRouter's unified reasoning parameter."""
    attempt, retries, use_temperature = 0, 0, temperature is not None
    while True:
        attempt += 1
        start = time.monotonic()
        try:
            extra_body = {"usage": {"include": True}}
            if reasoning_effort:
                extra_body["reasoning"] = {"effort": reasoning_effort}
            kwargs = dict(
                model=model,
                messages=messages,
                tools=tools,
                extra_body=extra_body,
            )
            if use_temperature:
                kwargs["temperature"] = temperature
            resp = client().chat.completions.create(**kwargs)
            latency = time.monotonic() - start
            if not resp.choices:
                raise RuntimeError(f"empty choices from provider: {resp}")
            msg = resp.choices[0].message
            usage = resp.usage
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
                "finish_reason": resp.choices[0].finish_reason,
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
        except (APIConnectionError, APITimeoutError, json.JSONDecodeError):
            # JSONDecodeError: provider/proxy returned a malformed body
            if attempt < max_attempts:
                retries += 1
                time.sleep(min(60, 2 ** attempt))
                continue
            raise
