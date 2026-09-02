"""See an episode the way watching the replay would show it.

Aggregate stats hide the two things a human notices immediately when watching:
where the farm actually is, and how far the crew walks to reach it. This prints
a per-day map of a seat's farm with the crew overlaid, and measures how much of
the day is spent in transit.

    python tools/watch.py <replay.json> [--seat 1] [--team NAME]
                          [--days 0,6,12,18,24] [--html out.html]
"""
import argparse
import collections
import json
import sys

LEGEND = {"empty": ".", "locked": "#", "weed": "x", "coop": "o", "pasture": "p"}
CROP = {"WHEAT": "w", "CARROT": "c", "TOMATO": "t", "STRAWBERRY": "s", "MELON": "m"}
ANIMAL = {"GOOSE": "G", "COW": "C", "SHEEP": "S"}
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def glyph(t):
    if t is None:
        return LEGEND["empty"]
    if t == "LOCKED":
        return LEGEND["locked"]
    k = t.get("kind")
    if k == "PLANT":
        return CROP.get(t["crop"], "?")
    if k == "WEED":
        return LEGEND["weed"]
    if t.get("animal"):
        return ANIMAL.get(t["animal"], "A")
    return LEGEND["coop"] if k == "COOP" else LEGEND["pasture"]


def farm_map(farm, hour_positions=None):
    rows = []
    occupancy = collections.Counter(hour_positions or [])
    for y, row in enumerate(farm["tiles"]):
        line = ""
        for x, t in enumerate(row):
            g = glyph(t)
            n = occupancy.get((x, y), 0)
            # a digit marks how many units stood here during the day
            line += (str(min(n, 9)) if n and g in ".#" else g)
        rows.append(line)
    return rows


def positions_during(steps, pid, day, tpd=24):
    """Every tile a unit of `pid` occupied during `day`."""
    seen = []
    for h in range(tpd):
        i = day * tpd + h
        if i >= len(steps):
            break
        farms = steps[i][0]["observation"].get("farms")
        if not farms:
            continue
        f = farms[pid]
        seen.append(tuple(f["farmer"]))
        seen += [tuple(p) for p in f.get("hands", [])]
    return seen


def movement(steps, pid):
    walked = worked = idle = 0
    for st in steps:
        a = st[pid].get("action")
        if not isinstance(a, dict):
            continue
        units = ([a["farmer"]] if isinstance(a.get("farmer"), list) else []) + list(a.get("hands") or [])
        for u in units:
            if not (isinstance(u, list) and u):
                continue
            if u[0] in MOVES:
                walked += 1
            elif u[0] == "PASS":
                idle += 1
            else:
                worked += 1
    tot = max(1, walked + worked + idle)
    return {"walked": walked, "worked": worked, "idle": idle,
            "walk_pct": round(100 * walked / tot, 1),
            "work_pct": round(100 * worked / tot, 1),
            "idle_pct": round(100 * idle / tot, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--seat", type=int)
    ap.add_argument("--team")
    ap.add_argument("--days", default="0,6,12,18,24,29")
    ap.add_argument("--html", help="also write the interactive Kaggle visualizer to this path")
    a = ap.parse_args()

    d = json.load(open(a.replay))
    steps = d["steps"]
    cfg = d.get("configuration", {})
    tpd = int(cfg.get("turnsPerDay", 24) or 24)
    teams = (d.get("info") or {}).get("TeamNames") or []
    seat = a.seat
    if seat is None and a.team and a.team in teams:
        seat = teams.index(a.team)
    if seat is None:
        seat = 0
    print(f"episode {(d.get('info') or {}).get('EpisodeId')}  teams={teams}  "
          f"rewards={d.get('rewards')}  showing seat {seat}"
          f"{' (' + teams[seat] + ')' if seat < len(teams) else ''}\n")

    for pid in (0, 1):
        m = movement(steps, pid)
        mark = " <- shown" if pid == seat else ""
        print(f"seat {pid}: walking {m['walk_pct']}%  working {m['work_pct']}%  "
              f"idle {m['idle_pct']}%   ({m['walked']:,} moves for {m['worked']:,} "
              f"useful actions){mark}")

    print("\nlegend  . empty  # locked  x weed  o coop  p pasture   "
          "w/c/t/s/m = wheat/carrot/tomato/strawberry/melon   G/C/S = goose/cow/sheep")
    print("        digits on empty tiles = how many unit-turns were spent standing there\n")

    for day in [int(x) for x in a.days.split(",") if x.strip().isdigit()]:
        i = min(day * tpd + tpd - 1, len(steps) - 1)
        farms = steps[i][0]["observation"].get("farms")
        if not farms:
            continue
        rows = farm_map(farms[seat], positions_during(steps, seat, day, tpd))
        print(f"day {day:>2}   ${farms[seat]['money']:>10,.0f}   "
              f"quadrants={len(farms[seat].get('unlocked_quadrants', []))}")
        for r in rows:
            print("        " + " ".join(r))
        print()

    if a.html:
        sys.path.insert(0, ".venv/lib/python3.11/site-packages")
        from kaggle_environments import make
        env = make("kaggriculture", configuration=cfg, steps=steps)
        open(a.html, "w").write(env.render(mode="html", width=1000, height=800))
        print(f"wrote {a.html} — open it in a browser to watch the episode")


if __name__ == "__main__":
    main()
