"""Snapshot architecture + measured GGUF sizes for the open-weight models.

Writes results/model_meta.json in place. Every number is verified before it is
kept: the GGUF repo's base_model must name the model we benchmarked, quant sizes
must increase with quant level, and stems are matched exactly (a loose regex put
Coder Next's Q8_0 below its Q6_K, which is impossible).
"""
import json
import re
import sys
import urllib.request
from collections import defaultdict

UA = {"User-Agent": "curl/8"}
QUANTS = ["IQ4_XS", "Q4_K_M", "Q6_K", "Q8_0", "BF16"]

# repo -> the base model it must declare. Deliberately explicit: the search hit
# for Inkling was thinkingmachines/Inkling-Small, a different and much smaller
# model, and it would have silently supplied ~5x-too-small numbers.
GGUF = {
    "moonshotai/kimi-k3":      ("unsloth/Kimi-K3-GGUF", "moonshotai/Kimi-K3"),
    "xiaomi/mimo-v2.5-pro":    ("unsloth/MiMo-V2.5-Pro-GGUF", "XiaomiMiMo/MiMo-V2.5-Pro"),
    "z-ai/glm-5.2":            ("unsloth/GLM-5.2-GGUF", "zai-org/GLM-5.2"),
    "minimax/minimax-m3":      ("unsloth/MiniMax-M3-GGUF", "MiniMaxAI/MiniMax-M3"),
    "openai/gpt-oss-120b":     ("unsloth/gpt-oss-120b-GGUF", "openai/gpt-oss-120b"),
    "qwen/qwen3-coder-next":   ("unsloth/Qwen3-Coder-Next-GGUF", "Qwen/Qwen3-Coder-Next"),
    "qwen/qwen3.6-35b-a3b":    ("unsloth/Qwen3.6-35B-A3B-GGUF", "Qwen/Qwen3.6-35B-A3B"),
    "google/gemma-4-31b-it":   ("unsloth/gemma-4-31B-it-GGUF", "google/gemma-4-31B-it"),
    "qwen/qwen3.6-27b":        ("unsloth/Qwen3.6-27B-GGUF", "Qwen/Qwen3.6-27B"),
    # Vision-language, so this repo ships an mmproj projector and a sharded BF16;
    # the loader already drops mmproj and collapses -00001-of-000NN shard sets.
    "qwen/qwen3.8-27b":        ("unsloth/Qwen3.8-27B-GGUF", "Qwen/Qwen3.8-27B"),
    # bartowski rather than unsloth: unsloth's Muse Glimmer repo publishes no
    # plain Q4_K_M at all (its 4-bit rung is UD-Q4_K_XL), and Q4_K_M is the
    # exact file the local-inference class rule is defined on.
    "meta/muse-glimmer-30b":   ("bartowski/Muse-Glimmer-30B-GGUF",
                                "meta-models/Muse-Glimmer-30B"),
    "deepseek/deepseek-v4-flash-0731": ("unsloth/DeepSeek-V4-Flash-0731-GGUF",
                                        "deepseek-ai/DeepSeek-V4-Flash-0731"),
    # Ladder tops out at UD-IQ4_XS: no plain Q4_K_M and no UD-Q4_K_M either, the
    # same shape as Kimi K3, so the label is in the audit's NO_PLAIN_Q4. Recorded
    # for provenance rather than for the machine table, where a 2.4T model needs
    # more than the largest budget even at one bit.
    "qwen/qwen3.8-2.4t-a95b":  ("unsloth/Qwen3.8-2.4T-A95B-GGUF",
                                "Qwen/Qwen3.8-2.4T-A95B"),
    # no usable repo: tencent/hy3 and deepseek/deepseek-v4-pro (none published),
    # thinkingmachines/inkling (only Inkling-Small, a different model)
}

# Recorded for provenance, not for display: the report dropped its experts
# column, but these are what justify calling a model MoE rather than dense.
ARCH_KEYS = {
    "experts": ("n_routed_experts", "num_experts", "num_local_experts"),
    "experts_per_tok": ("num_experts_per_tok", "num_experts_per_token"),
    "shared_experts": ("n_shared_experts", "num_shared_experts"),
    "layers": ("num_hidden_layers",),
}


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120))


def arch_from_config(hf_id):
    cfg = get(f"https://huggingface.co/{hf_id}/raw/main/config.json")
    flat = dict(cfg)
    flat.update(cfg.get("text_config") or {})
    out = {}
    for field, names in ARCH_KEYS.items():
        for n in names:
            if flat.get(n) is not None:
                out[field] = flat[n]
                break
    return out


def gguf_sizes(repo, expect_base):
    """Every published quantization of one repo, plus the canonical five.

    `files` is the whole ladder under the exact names the repo publishes, because
    "the best quant that fits a 64 GB machine" can only be answered from the
    ladder that exists: these repos ship 13 to 38 files each, from TQ1_0 to BF16,
    and the five-name subset we used to record made DeepSeek V4 Flash 0731 look
    like it topped out at IQ4_XS when the repo goes to UD-Q8_K_XL.

    The five canonical keys stay alongside it, derived from `files` with the same
    plain-over-UD preference as before, so the class rule and the open-weights
    ladder table read exactly what they always read.
    """
    m = get(f"https://huggingface.co/api/models/{repo}?blobs=true")
    base = (m.get("cardData") or {}).get("base_model")
    base = base[0] if isinstance(base, list) else base
    if base != expect_base:
        raise SystemExit(f"{repo}: base_model is {base!r}, expected {expect_base!r}")
    # Strip the model-name prefix off each stem rather than splitting on "-":
    # every quant name contains hyphens of its own (UD-Q4_K_XL), and splitting
    # produced names like "M3-UD-IQ1_M".
    prefix = repo.split("/")[-1].removesuffix("-GGUF")
    tot = defaultdict(int)
    for s in m.get("siblings", []):
        f = s["rfilename"]
        # mmproj is the vision projector; mtp-* is Gemma's multi-token-prediction
        # draft head, half a gigabyte of something that is not the model.
        # dflash-* is the same idea for Muse Glimmer and dspark-* for DeepSeek
        # V4 Flash (both speculative-decoding drafters), and *-imatrix.gguf is
        # the calibration matrix bartowski ships next to the quants: all .gguf,
        # none of them a quantization of the model.
        if not f.endswith(".gguf") or re.search(
                r"mmproj|imatrix|(^|/)(mtp|dflash|dspark)-", f, re.I):
            continue
        # a quant is either one file or a -00001-of-000NN shard set; strip either
        # suffix to get the stem the quant name ends with
        stem = re.sub(r"(-\d{5}-of-\d{5})?\.gguf$", "", f).split("/")[-1]
        name = re.sub(rf"^{re.escape(prefix)}[-._]?", "", stem, flags=re.I) or stem
        tot[name] += s.get("size") or 0
    files = {q: round(v / 1e9, 1) for q, v in sorted(tot.items(), key=lambda kv: kv[1]) if v}
    if not files:
        raise SystemExit(f"{repo}: no .gguf files matched the prefix {prefix!r}")

    # exact match on the canonical name, plain quant preferred over an UD-
    # variant. Matched case-insensitively because repos disagree on case
    # (bartowski publishes bf16, unsloth BF16) and a case-sensitive miss drops a
    # rung from the ladder silently instead of failing.
    lower = {q.lower(): v for q, v in files.items()}
    out = {}
    for q in QUANTS:
        v = lower.get(q.lower()) or lower.get(f"UD-{q}".lower())
        if v:
            out[q] = v
    have = [(q, out[q]) for q in QUANTS if q in out]
    for (qa, a), (qb, b) in zip(have, have[1:]):
        if b <= a:
            raise SystemExit(f"{repo}: {qb} ({b} GB) is not larger than {qa} ({a} GB); "
                             "stem matching picked up the wrong file")
    return {"repo": repo, **out, "files": files}


def main():
    path = "results/model_meta.json"
    meta = json.load(open(path))
    for mid, m in meta["models"].items():
        if not m.get("params_total"):
            continue                       # closed model, nothing to describe
        hf = m.get("hugging_face_id")
        if hf:
            try:
                m["arch"] = arch_from_config(hf)
            except Exception as e:
                print(f"  {mid}: arch unavailable ({type(e).__name__})")
        if mid in GGUF:
            repo, base = GGUF[mid]
            m["gguf"] = gguf_sizes(repo, base)
        else:
            m["gguf"] = None
        print(f"  {mid:26} arch={m.get('arch')}  gguf={m.get('gguf')}")
    json.dump(meta, open(path, "w"), indent=1)
    open(path, "a").write("\n")
    print("written")


main()
