"""Delete per-sweep run files whose records already live in the archive.

  uv run python -m bench.prune_runs            # dry run: report, change nothing
  uv run python -m bench.prune_runs --apply    # write manifest + leftovers, delete

Every sweep writes to its own `--out` file, because a sweep that goes wrong must
not touch the dataset. Once merged into `main.jsonl` (slim) and `main.full.jsonl`
(with transcripts), those files are pure duplication: 27 of them had accumulated
to 195 MB, of which 27 records existed nowhere else.

Deleting them by hand is the kind of judgement call that eventually deletes the
wrong thing, so this accounts for every record first and refuses to remove a file
it cannot explain. Two artifacts are written before anything is deleted:

  sweeps.json     which sweep produced which runs. The archive cannot answer
                  that, and it is the only information deletion destroys.
  unmerged.jsonl  records the dataset never took: transport errors (load_runs
                  drops anything with a non-null `error`) and probe runs. Kept
                  out of main.jsonl on purpose, since merging them would move the
                  published record count and the figures that quote it.
"""
import argparse
import json
import os
from collections import defaultdict

from . import config

RUNS = config.RESULTS_DIR / "runs"
SLIM, ARCHIVE = RUNS / "main.jsonl", RUNS / "main.full.jsonl"
MANIFEST, LEFTOVERS = RUNS / "sweeps.json", RUNS / "unmerged.jsonl"
KEEP = {SLIM.name, ARCHIVE.name, LEFTOVERS.name}

# Harness smoke tests against the scripted fake model. Not benchmark data, and
# regenerable with `bench.runner --models fake/model`, so they are dropped rather
# than rescued.
DROP_MODELS = {"fake/model", "fake"}

ident = lambda r: (r["task"], r["model"], r["condition"], r["rep"])


def sweep_files():
    """Every run file that is not one of the four we keep.

    Globs `*.jsonl*` rather than `*.jsonl`, so ad-hoc `.bak`/`.bak2` snapshots are
    accounted for too. Two of them (112 MB, taken before the transcript strip)
    outlived the first prune purely because they did not end in `.jsonl`.
    """
    return sorted(p for p in RUNS.glob("*.jsonl*") if p.name not in KEEP)


def load(path):
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            out.append((line, json.loads(line)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually write the manifest and leftovers, and delete")
    args = ap.parse_args()

    archive = {ident(json.loads(l)) for l in ARCHIVE.open()} if ARCHIVE.exists() else set()
    if not archive:
        raise SystemExit(f"{ARCHIVE} is missing or empty; refusing to prune anything")
    rescued_already = ({ident(r) for _, r in load(LEFTOVERS)} if LEFTOVERS.exists() else set())

    manifest, rescue, undecided, freed = {}, [], [], 0
    print(f"{'file':30} {'recs':>5} {'archived':>9} {'rescue':>7} {'drop':>5}  decision")
    for path in sweep_files():
        rows = load(path)
        covered = [r for _, r in rows if ident(r) in archive]
        dropped = [r for _, r in rows if ident(r) not in archive and r["model"] in DROP_MODELS]
        orphans = [(l, r) for l, r in rows
                   if ident(r) not in archive and r["model"] not in DROP_MODELS]
        # an orphan already sitting in unmerged.jsonl counts as accounted for
        fresh = [(l, r) for l, r in orphans if ident(r) not in rescued_already]
        ok = len(covered) + len(dropped) + len(orphans) == len(rows)
        if not ok:
            undecided.append(path.name)
        rescue += fresh
        freed += path.stat().st_size
        manifest[path.name] = {
            "records": len(rows),
            "models": sorted({r["model"] for _, r in rows}),
            "conditions": sorted({r["condition"] for _, r in rows}),
            "run_ids": [r.get("run_id") for _, r in rows],
        }
        print(f"{path.name:30} {len(rows):>5} {len(covered):>9} {len(fresh):>7} {len(dropped):>5}"
              f"  {'delete' if ok else 'KEEP: unaccounted records'}")

    print(f"\n{len(sweep_files())} files, {freed / 1e6:.1f} MB, "
          f"{len(rescue)} records to rescue, {len(undecided)} unaccounted")
    if undecided:
        raise SystemExit("refusing to delete: " + ", ".join(undecided))
    if not args.apply:
        print("\ndry run; nothing written or deleted. Re-run with --apply.")
        return

    # MERGE, never overwrite: a later prune must not erase the provenance of an
    # earlier one. Writing the fresh dict straight out would have dropped the 27
    # sweeps recorded in the first pass the moment two .bak files were pruned.
    if MANIFEST.exists():
        manifest = {**json.loads(MANIFEST.read_text()), **manifest}
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
    if rescue:
        with LEFTOVERS.open("a") as fh:
            for line, _ in rescue:
                fh.write(line + "\n")
    for path in sweep_files():
        path.unlink()
    print(f"\nwrote {MANIFEST.name} ({MANIFEST.stat().st_size / 1e6:.2f} MB) and "
          f"{LEFTOVERS.name} ({sum(1 for _ in LEFTOVERS.open())} records); "
          f"deleted {len(manifest)} files, freed {freed / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
