"""Count what the crew actually spends its turns on."""
import sys, os, collections
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from kaggle_environments import make
import importlib, main
importlib.reload(main)
SEED=int(os.environ.get("SEED","5")); POS=int(os.environ.get("POS","1"))
env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": SEED}, debug=True)
env.run([main.agent, "starter"] if POS==0 else ["starter", main.agent])

tot = collections.Counter()
per_phase = {}
for i, st in enumerate(env.steps):
    act = st[POS].get("action")
    if not isinstance(act, dict): continue
    day = i // 24
    ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
    ph = "d0-9" if day < 10 else ("d10-19" if day < 20 else "d20-29")
    c = per_phase.setdefault(ph, collections.Counter())
    for o in ops:
        k = o[0] if isinstance(o, list) and o else "PASS"
        if k in ("NORTH","SOUTH","EAST","WEST"): k = "MOVE"
        tot[k] += 1; c[k] += 1

grand = sum(tot.values())
print(f"total unit-turns: {grand}")
for k, v in tot.most_common():
    print(f"  {k:<20}{v:>7}  {100*v/grand:5.1f}%")
print()
for ph in ("d0-9","d10-19","d20-29"):
    c = per_phase.get(ph)
    if not c: continue
    n = sum(c.values())
    print(f"{ph} ({n} unit-turns): " + ", ".join(f"{k}={100*v/n:.0f}%" for k,v in c.most_common(7)))
