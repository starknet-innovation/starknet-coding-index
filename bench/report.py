"""The shared run loader. Every consumer of the dataset goes through here.

`sci`, `html_report`, `audit` and `status` all import `load_runs` from this
module, so the three normalisations below happen exactly once and every number
anyone publishes agrees on them.

This module used to also write a markdown report (results/report.md). That was
removed 2026-08-04: report.html is the deliverable, the audit is the gate, and
a second rendering of the same numbers was one more thing to keep in sync.
"""

import json

from . import config


def load_runs(paths):
    runs = []
    for p in paths:
        with open(p) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("error") is None:
                    # Older records carry effort only in llm_opts; fold it into
                    # the model label so groups stay distinct across runs.
                    effort = (r.get("llm_opts") or {}).get("reasoning_effort")
                    if effort and "@" not in r["model"]:
                        r["model"] = f"{r['model']}@{effort}"
                    # A run that needed more than the model-time budget is a
                    # failure, whatever its tests eventually said — applied
                    # here so every consumer (sci, charts, audit) agrees.
                    mt = (r.get("llm_time_s") or 0) + (r.get("assist_time_s") or 0)
                    r["over_time_budget"] = mt > config.MODEL_TIME_BUDGET_S
                    if r["over_time_budget"]:
                        r["solved"] = False
                    runs.append(r)
    return runs
