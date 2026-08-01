"""One-command visual QA for the report: regenerate, screenshot every section.

  uv run python -m bench.screenshot [--no-regen]

Every section is shot TWICE: desktop at results/shots/NN-<slug>.png and phone
at results/shots/m-NN-<slug>.png. Both are the gate. Shooting one width is how
the report shipped for weeks with no <meta name="viewport"> at all, which made
a phone lay it out at 980px and scale the whole page to ~40%, and left every
max-width media query in the stylesheet dead on arrival.

A .fresh marker records success so the commit-gate hook can tell whether the
current report was ever looked at. After running this, Read the PNGs and
iterate until the design is right — the screenshots are the gate, not the
verdict.

Chromium notes (hard-won): the sandbox proxy hangs Chromium, so proxies are
stripped from the env; /dev/shm is 64MB regardless of host RAM; full-page
screenshots crash on this report — element shots only.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from . import config

SHOTS_DIR = config.REPO_ROOT / "results" / "shots"

LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-proxy-server"]

DEPS_HINT = (
    "Chromium launch failed. Fresh sandbox? Install deps:\n"
    "  uv pip install playwright && uv run playwright install chromium\n"
    "  sudo apt-get install -y fontconfig fonts-liberation fonts-dejavu-core "
    "fonts-noto-core libnss3 libgbm1 libglib2.0-0t64 libatk1.0-0t64 libx11-6 "
    "libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libxcb1 "
    "libxkbcommon0 libasound2t64 libatspi2.0-0t64"
)


def slug(s, maxlen=40):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:maxlen] or "section"


# Full-page screenshots crash Chromium on this report, so every shot is an
# element shot: header, each section, footer.
def shoot(page, prefix=""):
    shots = []

    def snap(el, name):
        if not el:
            return
        path = SHOTS_DIR / f"{prefix}{name}.png"
        el.screenshot(path=str(path))
        shots.append(path)

    snap(page.query_selector("header"), "00-hero")
    for i, sec in enumerate(page.query_selector_all("section"), 1):
        h2 = sec.query_selector("h2")
        snap(sec, f"{i:02d}-{slug(h2.inner_text() if h2 else f'section-{i}')}")
    snap(page.query_selector("footer"), "99-footer")
    return shots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-regen", action="store_true", help="shoot the existing report.html as-is")
    args = ap.parse_args()

    if not args.no_regen:
        subprocess.run(
            [sys.executable, "-m", "bench.html_report"], check=True, cwd=config.REPO_ROOT
        )

    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(var, None)

    from playwright.sync_api import sync_playwright

    report = config.REPO_ROOT / "results" / "report.html"
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    for old in SHOTS_DIR.glob("*.png"):
        old.unlink()

    # 390x844 is an iPhone 14 in CSS pixels, the narrow end of what people
    # actually read on; 2x so an element shot comes back legible rather than
    # 390px of unreadable thumbnail. has_touch so the tap handlers are live.
    PASSES = [
        ("", {"viewport": {"width": 1100, "height": 1400}}, "desktop 1100px"),
        ("m-", {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 2,
                "has_touch": True, "is_mobile": True}, "phone 390px @2x"),
    ]
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=LAUNCH_ARGS)
            groups = []
            for prefix, opts, label in PASSES:
                page = browser.new_page(**opts)
                page.goto(f"file://{report}", wait_until="load", timeout=30000)
                groups.append((label, shoot(page, prefix)))
                page.close()
            browser.close()
    except Exception as e:
        print(f"{e}\n\n{DEPS_HINT}", file=sys.stderr)
        sys.exit(1)

    (SHOTS_DIR / ".fresh").touch()
    print(f"{sum(len(g) for _, g in groups)} shots -> {SHOTS_DIR}")
    for label, shots in groups:
        print(f"\n{label}:")
        for s in shots:
            print(f"  {s}")
    print("\nNow Read them, BOTH widths, and iterate until the design is right.")


if __name__ == "__main__":
    main()
