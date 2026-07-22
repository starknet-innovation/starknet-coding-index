"""Validation gate: every reference solution must pass all tests; every stub must not.

  uv run python -m bench.validate_tasks [task_id ...]
"""

import sys

from . import config, workspace


def main():
    ids = sys.argv[1:] or sorted(
        d.name for d in config.TASKS_DIR.iterdir()
        if d.is_dir() and (d / "prompt.md").exists()
    )
    failures = []
    for tid in ids:
        task_dir = config.TASKS_DIR / tid
        missing = [
            p for p in ["prompt.md", "Scarb.toml", "src/lib.cairo", "tests", "solution/lib.cairo"]
            if not (task_dir / p).exists()
        ]
        if missing:
            print(f"{tid}: MISSING {missing}")
            failures.append(tid)
            continue

        sol = workspace.evaluate_solution(tid)
        stub = workspace.evaluate_stub(tid)
        sol_ok = sol["all_passed"]
        stub_ok = not stub["all_passed"]
        n = sol["tests_passed"]
        status = "OK" if (sol_ok and stub_ok) else "FAIL"
        print(f"{tid}: {status} (solution: {n} tests pass={sol_ok}; stub fails={stub_ok})")
        if not (sol_ok and stub_ok):
            failures.append(tid)
            if not sol_ok:
                print("--- solution output (tail) ---")
                print(sol["output"][-3000:])

    if failures:
        print(f"\nVALIDATION FAILED: {failures}")
        sys.exit(1)
    print(f"\nAll {len(ids)} tasks valid.")


if __name__ == "__main__":
    main()
