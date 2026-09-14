"""Mine a pile of episode replays for what the strong agents actually do.

Point this at a directory of Kaggriculture replay JSONs -- e.g. the public
"kaggriculture-episodes" dataset, which carries games from across the ladder --
and it builds a strategy profile per team and ranks them by result. The point
is to answer "what do the agents that beat us do differently", from data rather
than from guesses.

    python tools/profile_agents.py <dir-of-replays> [--top 12] [--me "Team Name"]
"""
import argparse
import collections
import glob
import json
import os
import statistics
import sys

CROP3 = {"WHEAT": "wheat", "CARROT": "carrot", "TOMATO": "tomato",
         "STRAWBERRY": "straw", "MELON": "melon"}
ANIMALS = {"GOOSE": "goose", "COW": "cow", "SHEEP": "sheep"}
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def profile(path):
    """One (team, stats) pair per seat in this replay."""
    try:
        d = json.load(open(path))
    except Exception:
        return []
    steps = d.get("steps") or []
    if len(steps) < 24:
        return []
    info = d.get("info") or {}
    teams = info.get("TeamNames") or ["?", "?"]
    rewards = d.get("rewards") or [0, 0]
    tpd = int((d.get("configuration") or {}).get("turnsPerDay", 24) or 24)
    out = []
    for pid in (0, 1):
        ops = collections.Counter()
        hands, hires, land = [], 0, 0
        seeds = collections.Counter()
        animals_bought = collections.Counter()
        sold = collections.Counter()
        for i, st in enumerate(steps):
            a = st[pid].get("action")
            if not isinstance(a, dict):
                continue
            units = ([a["farmer"]] if isinstance(a.get("farmer"), list) else []) \
                + list(a.get("hands") or [])
            hands.append(len(a.get("hands") or []))
            for u in units:
                if isinstance(u, list) and u:
                    ops["MOVE" if u[0] in MOVES else u[0]] += 1
            for o in a.get("market") or []:
                if not (isinstance(o, list) and o):
                    continue
                if o[0] == "HIRE":
                    hires += 1
                elif o[0] == "BUY_LAND":
                    land += 1
                elif o[0] == "BUY_SEED" and len(o) > 2:
                    seeds[o[1]] += int(o[2])
                elif o[0] == "BUY_ANIMAL" and len(o) > 2:
                    animals_bought[o[1]] += int(o[2])
                elif o[0] == "SELL" and len(o) > 2:
                    sold[o[1]] += int(o[2])
        # peak farm composition
        peak = collections.Counter()
        for day in range(0, len(steps) // tpd):
            farms = steps[min(day * tpd + tpd - 1, len(steps) - 1)][0]["observation"].get("farms")
            if not farms:
                continue
            c = collections.Counter()
            for row in farms[pid]["tiles"]:
                for t in row:
                    if isinstance(t, dict):
                        if t.get("kind") == "PLANT":
                            c[CROP3.get(t["crop"], "?")] += 1
                        elif t.get("animal"):
                            c[ANIMALS.get(t["animal"], "?")] += 1
            for k, v in c.items():
                peak[k] = max(peak[k], v)
        total = max(1, sum(ops.values()))
        out.append((teams[pid] if pid < len(teams) else "?", {
            "bank": float(rewards[pid] or 0),
            "hires": hires,
            "mean_hands": round(sum(hands) / max(1, len(hands)), 1),
            "land": land,
            "walk_pct": round(100 * ops["MOVE"] / total),
            "peak": dict(peak),
            "seeds": dict(seeds),
            "animals": dict(animals_bought),
            "sold": dict(sold),
        }))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--me")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.directory, "**", "*.json"), recursive=True))
    if not files:
        sys.exit(f"no .json replays under {a.directory}")
    print(f"reading {len(files)} replays...")
    by_team = collections.defaultdict(list)
    for f in files:
        for team, st in profile(f):
            by_team[team].append(st)

    rows = []
    for team, games in by_team.items():
        rows.append((statistics.mean(g["bank"] for g in games), len(games), team, games))
    rows.sort(reverse=True)

    print(f"\n{'team':<26}{'games':>6}{'mean bank':>12}{'hires/day':>10}{'land':>6}"
          f"{'walk%':>7}  peak farm")
    for mean, n, team, games in rows[:a.top]:
        agg = collections.Counter()
        for g in games:
            for k, v in g["peak"].items():
                agg[k] += v
        peak = {k: round(v / n, 1) for k, v in agg.most_common(6)}
        mark = "  <- you" if a.me and team == a.me else ""
        print(f"{team[:25]:<26}{n:>6}{mean:>12,.0f}"
              f"{statistics.mean(g['hires'] for g in games)/30:>10.1f}"
              f"{statistics.mean(g['land'] for g in games):>6.1f}"
              f"{statistics.mean(g['walk_pct'] for g in games):>7.0f}  {peak}{mark}")

    if rows:
        best = rows[0]
        print(f"\nwhat {best[2]} sells (mean units per game):")
        agg = collections.Counter()
        for g in best[3]:
            for k, v in g["sold"].items():
                agg[k] += v
        print("  " + ", ".join(f"{k}={v/best[1]:.0f}" for k, v in agg.most_common()))
        if a.me and a.me in by_team:
            mine = by_team[a.me]
            agg2 = collections.Counter()
            for g in mine:
                for k, v in g["sold"].items():
                    agg2[k] += v
            print(f"what {a.me} sells:")
            print("  " + ", ".join(f"{k}={v/len(mine):.0f}" for k, v in agg2.most_common()))


if __name__ == "__main__":
    main()
