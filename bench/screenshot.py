"""One-command visual QA for the report: regenerate, screenshot every section.

  uv run python -m bench.screenshot [--no-regen]

Shots land in results/shots/NN-<slug>.png; a .fresh marker records success so
the commit-gate hook can tell whether the current report was ever looked at.
After running this, Read the PNGs and iterate until the design is right —
the screenshots are the gate, not the verdict.

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

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=LAUNCH_ARGS)
            page = browser.new_page(viewport={"width": 1100, "height": 1400})
            page.goto(f"file://{report}", wait_until="load", timeout=30000)
            shots = []
            header = page.query_selector("header")
            if header:
                path = SHOTS_DIR / "00-hero.png"
                header.screenshot(path=str(path))
                shots.append(path)
            for i, sec in enumerate(page.query_selector_all("section"), 1):
                h2 = sec.query_selector("h2")
                name = slug(h2.inner_text() if h2 else f"section-{i}")
                path = SHOTS_DIR / f"{i:02d}-{name}.png"
                sec.screenshot(path=str(path))
                shots.append(path)
            browser.close()
    except Exception as e:
        print(f"{e}\n\n{DEPS_HINT}", file=sys.stderr)
        sys.exit(1)

    (SHOTS_DIR / ".fresh").touch()
    print(f"{len(shots)} shots -> {SHOTS_DIR}")
    for s in shots:
        print(f"  {s}")
    print("Now Read them and iterate until the design is right.")


if __name__ == "__main__":
    main()
