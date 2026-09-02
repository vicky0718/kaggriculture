"""Analyse a Kaggle replay and reduce it to a small, committable digest.

A raw replay is ~24 MB; the digest is a few KB and keeps everything needed to
reason about the game: who each seat was, per-day farm composition and bank,
the price trajectory, and where each side's turns went.

  python tools/replay.py <replay.json> [--team "Your Team Name"] [--out DIR]
"""
import argparse
import collections
import json
import os
import sys

CROP3 = {"WHEAT": "WHE", "CARROT": "CAR", "TOMATO": "TOM", "STRAWBERRY": "STR", "MELON": "MEL"}
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def _tiles(farm):
    k = collections.Counter()
    for row in farm["tiles"]:
        for t in row:
            if t is None:
                k["empty"] += 1
            elif t == "LOCKED":
                k["locked"] += 1
            elif t.get("kind") == "PLANT":
                k[CROP3.get(t["crop"], t["crop"][:3])] += 1
            elif t.get("kind") == "WEED":
                k["weed"] += 1
            elif t.get("animal"):
                k[t["animal"][:3]] += 1
            else:
                k[t["kind"].lower()] += 1
    return dict(k)


def _seat_stats(steps, pid):
    ops = collections.Counter()
    market = collections.Counter()
    hire_hours = set()
    hands = []
    for i, st in enumerate(steps):
        a = st[pid].get("action")
        if not isinstance(a, dict):
            continue
        f = a.get("farmer")
        units = ([f] if isinstance(f, list) and f else []) + list(a.get("hands") or [])
        hands.append(len(a.get("hands") or []))
        for u in units:
            if isinstance(u, list) and u:
                ops["MOVE" if u[0] in MOVES else u[0]] += 1
        for o in a.get("market") or []:
            if isinstance(o, list) and o:
                market[o[0]] += 1
                if o[0] == "HIRE":
                    hire_hours.add(i % 24)
    total = max(1, sum(ops.values()))
    return {
        "unit_turns": sum(ops.values()),
        "op_pct": {k: round(100.0 * v / total, 1) for k, v in ops.most_common()},
        "market_ops": dict(market.most_common()),
        "hire_hours": sorted(hire_hours),
        "max_hands": max(hands) if hands else 0,
        "mean_hands": round(sum(hands) / max(1, len(hands)), 1),
    }


def digest(path, team=None):
    d = json.load(open(path))
    steps = d["steps"]
    cfg = d.get("configuration", {})
    info = d.get("info", {}) or {}
    tpd = int(cfg.get("turnsPerDay", 24) or 24)
    teams = info.get("TeamNames") or []
    rewards = d.get("rewards") or [s.get("reward") for s in steps[-1]]

    # Seat identity comes from the replay metadata when we know our team name;
    # a self-match (both seats the same team) is the Validation Episode.
    ours = None
    if team and teams:
        idx = [i for i, t in enumerate(teams) if t == team]
        ours = idx[0] if len(idx) == 1 else (idx[0] if idx else None)
    mirror = len(set(teams)) == 1 and len(teams) == 2

    days, prices = [], []
    for day in range(0, (len(steps) + tpd - 1) // tpd):
        i = min(day * tpd + tpd - 1, len(steps) - 1)
        obs = steps[i][0]["observation"]
        farms = obs.get("farms")
        if not farms:
            continue
        days.append({
            "day": day,
            "money": [round(f["money"]) for f in farms],
            "tiles": [_tiles(f) for f in farms],
            "quadrants": [len(f.get("unlocked_quadrants", [])) for f in farms],
        })
        prices.append({"day": day, **obs["market"]["prices"]})

    last = steps[-1][0]["observation"]
    return {
        "episode_id": info.get("EpisodeId"),
        "teams": teams,
        "our_seat": ours,
        "is_validation_selfmatch": mirror,
        "rewards": rewards,
        # A validation self-match has our agent in both seats, so "who won" is
        # not a result -- label it rather than recording a phantom loss.
        "result": ("self" if mirror else
                   None if ours is None else
                   "win" if rewards[ours] > rewards[1 - ours] else
                   "loss" if rewards[ours] < rewards[1 - ours] else "tie"),
        "statuses": d.get("statuses"),
        "seed": info.get("seed"),
        "configuration": cfg,
        "shops": last["town"]["unlocked_shops"],
        "final_inventory_delta": {k: v - 10000 for k, v in last["market"]["inventory"].items()},
        "final_prices": last["market"]["prices"],
        "seats": [_seat_stats(steps, 0), _seat_stats(steps, 1)],
        "daily": days,
        "prices": prices,
    }


def render(g):
    out = []
    r = g["rewards"]
    tag = "  [VALIDATION self-match]" if g["is_validation_selfmatch"] else ""
    out.append(f"episode {g['episode_id']}  {g['teams']}  rewards={r}  "
               f"result={g['result']}{tag}")
    for pid in (0, 1):
        s = g["seats"][pid]
        me = " <- you" if g["our_seat"] == pid else ""
        out.append(f"  seat {pid}: ${r[pid]:>10,.0f}{me}  hands~{s['mean_hands']}"
                   f" (max {s['max_hands']})  hire_hours={s['hire_hours']}")
        out.append(f"     ops   : {dict(list(s['op_pct'].items())[:7])}")
        out.append(f"     market: {s['market_ops']}")
    out.append(f"{'day':>4} | {'p0 $':>9} {'p0 farm':<30} | {'p1 $':>9} {'p1 farm':<30}")
    for row in g["daily"]:
        cells = []
        for pid in (0, 1):
            t = {k: v for k, v in row["tiles"][pid].items() if k not in ("empty", "locked")}
            cells.append(f"{row['money'][pid]:>9,} " + " ".join(f"{k}:{v}" for k, v in sorted(t.items()))[:30].ljust(30))
        out.append(f"{row['day']:>4} | " + " | ".join(cells))
    out.append(f"final inventory delta (neg=starved): {g['final_inventory_delta']}")
    out.append(f"final prices: {g['final_prices']}")
    out.append(f"shops: {g['shops']}")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--team", default=os.environ.get("KAG_TEAM"))
    ap.add_argument("--out", help="write the digest JSON into this directory")
    a = ap.parse_args()
    g = digest(a.replay, a.team)
    print(render(g))
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        p = os.path.join(a.out, f"{g['episode_id']}.json")
        json.dump(g, open(p, "w"), separators=(",", ":"))
        print(f"\nwrote {p} ({os.path.getsize(p)/1024:.0f} KB)")
