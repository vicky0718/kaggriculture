"""Download every new Kaggle episode and reduce it to a committable digest.

Run this on the machine where the Kaggle CLI is authenticated. It writes one
small JSON per episode into episodes/ and deletes the multi-megabyte replay, so
the whole match history can live in git.

    python tools/harvest.py --team "Your Kaggle Team Name"
    git add episodes && git commit -m "episodes" && git push

Options:
    --episodes 94599066,94601234   skip discovery, fetch these episode ids
    --limit N                      stop after N new downloads (default 40)
    --keep-replays                 don't delete the raw replay after digesting
"""
import argparse
import csv
import glob
import io
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))
from replay import digest, render  # noqa: E402

COMP = "kaggriculture"
EPISODES = os.path.join(HERE, "episodes")
RAW = os.path.join(HERE, ".replays")


def kaggle(*args):
    """Invoke the Kaggle CLI however it is installed on this machine."""
    for base in (["kaggle"], [sys.executable, "-m", "kaggle"]):
        try:
            r = subprocess.run(base + list(args), capture_output=True, text=True)
        except FileNotFoundError:
            continue
        if r.returncode == 0:
            return r.stdout
        # a real CLI error (auth, not-found) -- report it rather than retrying
        if "usage:" not in r.stderr.lower():
            raise SystemExit(f"kaggle {' '.join(args)} failed:\n{r.stderr.strip() or r.stdout.strip()}")
    raise SystemExit("Kaggle CLI not found. pip install kaggle, then `kaggle auth login`.")


def parse_ids(csv_text, want=("episode",)):
    """Pull ids out of the CLI's CSV, tolerating column-name changes."""
    rows = list(csv.reader(io.StringIO(csv_text.strip())))
    if not rows:
        return [], []
    header = [h.strip().lower() for h in rows[0]]
    col = None
    for i, h in enumerate(header):
        if any(w in h for w in want) and "id" in h:
            col = i
            break
    if col is None:  # fall back: first column that is all digits
        for i in range(len(header)):
            vals = [r[i] for r in rows[1:] if len(r) > i]
            if vals and all(v.strip().isdigit() for v in vals):
                col = i
                break
    if col is None:
        return [], header
    return [r[col].strip() for r in rows[1:] if len(r) > col and r[col].strip().isdigit()], header


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default=os.environ.get("KAG_TEAM"),
                    help="your Kaggle team name, as it appears in the replay")
    ap.add_argument("--episodes")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--keep-replays", action="store_true")
    a = ap.parse_args()
    if not a.team:
        print("warning: no --team given; seat identification will be left blank\n")

    os.makedirs(EPISODES, exist_ok=True)
    os.makedirs(RAW, exist_ok=True)
    have = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(EPISODES, "*.json"))}

    if a.episodes:
        ids = [e.strip() for e in a.episodes.split(",") if e.strip()]
    else:
        subs, header = parse_ids(kaggle("competitions", "submissions", COMP, "-v"), ("submission", "ref"))
        if not subs:
            raise SystemExit(f"could not find submission ids in CLI output; header was {header}")
        print(f"submissions: {subs}")
        ids = []
        for s in subs:
            eps, header = parse_ids(kaggle("competitions", "episodes", s, "-v"), ("episode",))
            if not eps:
                print(f"  submission {s}: no episodes parsed (header {header})")
            ids += eps
        ids = sorted(set(ids))

    todo = [e for e in ids if e not in have][:a.limit]
    print(f"{len(ids)} episodes known, {len(have)} already digested, fetching {len(todo)}")

    for e in todo:
        kaggle("competitions", "replay", e, "-p", RAW)
        hits = glob.glob(os.path.join(RAW, f"*{e}*.json"))
        if not hits:
            print(f"  {e}: replay not found after download")
            continue
        g = digest(hits[0], a.team)
        out = os.path.join(EPISODES, f"{g['episode_id'] or e}.json")
        json.dump(g, open(out, "w"), separators=(",", ":"))
        print(f"  {e}: {g['result'] or '?':<4} {g['rewards']}  -> {os.path.getsize(out)//1024} KB")
        if not a.keep_replays:
            os.remove(hits[0])

    if not a.keep_replays:
        shutil.rmtree(RAW, ignore_errors=True)

    # A human- and model-readable index of everything harvested so far.
    rows = []
    for p in sorted(glob.glob(os.path.join(EPISODES, "*.json"))):
        g = json.load(open(p))
        rows.append(g)
    wins = sum(1 for g in rows if g["result"] == "win")
    losses = sum(1 for g in rows if g["result"] == "loss")
    with open(os.path.join(EPISODES, "INDEX.md"), "w") as f:
        selfs = sum(1 for g in rows if g["result"] == "self")
        f.write(f"# Episodes\n\n{len(rows) - selfs} ranked games — {wins}W-{losses}L"
                f"-{sum(1 for g in rows if g['result']=='tie')}T"
                f"  (+{selfs} validation self-match{'es' if selfs != 1 else ''})\n\n")
        f.write("| episode | opponent | result | ours | theirs |\n|---|---|---|---|---|\n")
        for g in rows:
            o = g["our_seat"]
            opp = "(self-match)" if g["is_validation_selfmatch"] else (
                g["teams"][1 - o] if o is not None and g["teams"] else "?")
            mine = f"{g['rewards'][o]:,.0f}" if o is not None else "?"
            theirs = f"{g['rewards'][1-o]:,.0f}" if o is not None else "?"
            f.write(f"| {g['episode_id']} | {opp} | {g['result'] or '?'} | {mine} | {theirs} |\n")
    print(f"\nwrote episodes/INDEX.md — {wins}W-{losses}L over {len(rows)} episodes")
    print("now:  git add episodes && git commit -m 'episodes' && git push")


if __name__ == "__main__":
    main()
