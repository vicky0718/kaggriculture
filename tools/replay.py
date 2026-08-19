"""Analyse a downloaded Kaggle replay: who won, and where the game was decided."""
import json, sys, collections

path = sys.argv[1]
ME = int(sys.argv[2]) if len(sys.argv) > 2 else None
d = json.load(open(path))
steps = d["steps"]
cfg = d.get("configuration", {})
tpd = int(cfg.get("turnsPerDay", 24) or 24)
n = len(steps)
print(f"file={path.split('/')[-1]}  steps={n}  cfg episodeSteps={cfg.get('episodeSteps')}")

final = steps[-1]
rewards = [s.get("reward") for s in final]
print(f"final rewards: {rewards}   statuses: {[s.get('status') for s in final]}")

# identify which seat is ours by the action shape our agent emits
def seat_signature(pid):
    ops = collections.Counter(); hands = []
    for st in steps:
        a = st[pid].get("action")
        if not isinstance(a, dict): continue
        f = a.get("farmer") or ["PASS"]
        ops[f[0] if isinstance(f, list) and f else "?"] += 1
        hs = a.get("hands") or []
        hands.append(len(hs))
        for h in hs:
            ops[h[0] if isinstance(h, list) and h else "?"] += 1
    return ops, hands

for pid in (0, 1):
    ops, hands = seat_signature(pid)
    tot = sum(ops.values())
    top = ", ".join(f"{k}={100*v/max(1,tot):.0f}%" for k, v in ops.most_common(6))
    print(f"\nplayer {pid}: ${rewards[pid]:,.0f}   unit-turns={tot}  "
          f"max hands={max(hands) if hands else 0}  mean hands={sum(hands)/max(1,len(hands)):.1f}")
    print(f"   {top}")

# per-day farm + money for both players
print(f"\n{'day':>4} | {'P0 $':>10} {'P0 tiles':<34} | {'P1 $':>10} {'P1 tiles':<34}")
for day in range(0, 30):
    idx = min(day*tpd + tpd - 1, n-1)
    obs0 = steps[idx][0]["observation"]
    farms = obs0.get("farms")
    if not farms: continue
    row = f"{day:>4} |"
    for pid in (0, 1):
        f = farms[pid]
        kinds = collections.Counter()
        for r in f["tiles"]:
            for t in r:
                if t is None: kinds["empty"] += 1
                elif t == "LOCKED": pass
                elif t.get("kind") == "PLANT": kinds[t["crop"][:3]] += 1
                elif t.get("kind") == "WEED": kinds["weed"] += 1
                elif t.get("animal"): kinds[t["animal"][:3]] += 1
                else: kinds[t["kind"][:4].lower()] += 1
        s = " ".join(f"{k}:{v}" for k, v in sorted(kinds.items()) if k != "empty")
        row += f" {f['money']:>10,.0f} {s[:33]:<34} |"
    print(row)

mk = steps[-1][0]["observation"]["market"]
print("\nfinal market inventory delta from I0 (neg = starved, pos = glutted):")
print({k: v-10000 for k, v in mk["inventory"].items()})
print("final prices:", mk["prices"])
