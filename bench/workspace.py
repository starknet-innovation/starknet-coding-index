"""Per-run workspace: copy a task package, apply submitted code, build and test it."""

import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import config

# Runner threads block here while their turn to compile comes up; LLM waits
# elsewhere stay fully parallel. See config.MAX_CONCURRENT_BUILDS.
_build_slots = threading.Semaphore(config.MAX_CONCURRENT_BUILDS)


def create_workspace(task_id, run_id):
    """Copy the task package (without solution/) into a fresh workspace dir."""
    src = config.TASKS_DIR / task_id
    dst = config.WORKSPACES_DIR / run_id
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    shutil.copy(src / "Scarb.toml", dst / "Scarb.toml")
    shutil.copytree(src / "src", dst / "src")
    shutil.copytree(src / "tests", dst / "tests")
    return dst


def _run(cmd, cwd, timeout):
    start = time.monotonic()
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        return p.returncode, p.stdout + p.stderr, time.monotonic() - start
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return -1, out + f"\n[harness] command timed out after {timeout}s", time.monotonic() - start


_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_SUMMARY = re.compile(r"Tests:\s*(\d+)\s+passed,\s*(\d+)\s+failed", re.IGNORECASE)


def evaluate(workspace, code):
    """Write submitted code to src/lib.cairo, then scarb build + snforge test.

    Returns dict: compiled, tests_passed, tests_failed, all_passed, output,
    build_time_s, test_time_s.
    """
    (workspace / "src" / "lib.cairo").write_text(code)

    with _build_slots:
        rc, build_out, build_t = _run(["scarb", "build"], workspace, config.BUILD_TIMEOUT_S)
        build_out = _ANSI.sub("", build_out)
        if rc != 0:
            return {
                "compiled": False, "tests_passed": 0, "tests_failed": 0, "all_passed": False,
                "output": f"BUILD FAILED (scarb build):\n{build_out}",
                "build_time_s": build_t, "test_time_s": 0.0,
            }

        rc, test_out, test_t = _run(["snforge", "test"], workspace, config.TEST_TIMEOUT_S)
    test_out = _ANSI.sub("", test_out)
    m = _SUMMARY.search(test_out)
    if m:
        passed, failed = int(m.group(1)), int(m.group(2))
    else:
        # snforge itself failed before producing a summary (e.g. test-crate compile error)
        passed, failed = 0, 0
    all_passed = rc == 0 and m is not None and failed == 0 and passed > 0
    return {
        "compiled": True, "tests_passed": passed, "tests_failed": failed,
        "all_passed": all_passed,
        "output": f"BUILD OK.\nTEST RESULTS (snforge test):\n{test_out}",
        "build_time_s": build_t, "test_time_s": test_t,
    }


def evaluate_solution(task_id):
    """Run the reference solution of a task through the same pipeline (for validation)."""
    ws = create_workspace(task_id, f"_validate_{task_id}")
    code = (config.TASKS_DIR / task_id / "solution" / "lib.cairo").read_text()
    result = evaluate(ws, code)
    return result


def evaluate_stub(task_id):
    """Run the stub through the pipeline (must NOT pass, for validation)."""
    ws = create_workspace(task_id, f"_validate_stub_{task_id}")
    code = (config.TASKS_DIR / task_id / "src" / "lib.cairo").read_text()
    return evaluate(ws, code)


def truncate_output(text, limit=config.TOOL_RESULT_MAX_CHARS):
    """Keep head and tail of long tool output; compiler errors matter at both ends."""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return head + f"\n\n[... {len(text) - limit} chars truncated by harness ...]\n\n" + tail
