"""How much money is still on the farm when the whistle blows?

Unsold stock scores nothing. This measures the three ways value dies at the end
of a season: produce still on the plant/animal, produce sitting in the shed, and
produce still in a worker's pockets."""
import sys, statistics
sys.path.insert(0, ".venv/lib/python3.11/site-packages"); sys.path.insert(0, ".")
import importlib, main
from kaggle_environments import make

OPP = sys.argv[1] if len(sys.argv) > 1 else "main"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 6
opp = main.agent if OPP == "main" else importlib.import_module(OPP).agent

rows = []
for seed in range(1, N + 1):
    e = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed})
    e.run([main.agent, opp])
    last = e.steps[-1]
    obs = last[0]["observation"]
    prices = obs["market"]["prices"]
    farm = obs["farms"][0]
    priv = last[0]["observation"].get("private", {}) or {}

    on_tile = 0.0
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t, dict) and t.get("yield_units", 0) > 0:
                item = t["crop"] if t.get("kind") == "PLANT" else {
                    "GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}.get(t.get("animal"), None)
                if item:
                    on_tile += t["yield_units"] * prices.get(item, 0)
    shed = sum(prices.get(k, 0) * v for k, v in (priv.get("shed") or {}).items()
               if k in prices)
    pockets = sum(prices.get(k, 0) * v for inv in (priv.get("inventories") or [])
                  for k, v in inv.items() if k in prices)
    bank = farm["money"]
    rows.append((bank, on_tile, shed, pockets))
    print(f"  seed {seed}: bank ${bank:>9,.0f}   left behind: on-tile ${on_tile:>7,.0f}  "
          f"shed ${shed:>7,.0f}  pockets ${pockets:>7,.0f}   "
          f"= {100*(on_tile+shed+pockets)/max(1,bank+on_tile+shed+pockets):.1f}% of what we grew")

b = statistics.mean(r[0] for r in rows)
waste = statistics.mean(r[1] + r[2] + r[3] for r in rows)
print(f"\nmean bank ${b:,.0f}   mean value left behind ${waste:,.0f}"
      f"   ({100*waste/max(1,b+waste):.1f}% of total production)")
