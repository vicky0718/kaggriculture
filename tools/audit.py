"""Per-product audit: what the town wanted, what we sold, what we left unserved.

The point is to find markets we never serve. For each product it reports the
town's season-long demand, the units we actually sold and what they fetched,
and the revenue still sitting unclaimed at the whistle."""
import sys, collections
sys.path.insert(0, ".venv/lib/python3.11/site-packages"); sys.path.insert(0, ".")
import importlib, main
from kaggle_environments import make
from kaggle_environments.envs.kaggriculture.kaggriculture import (
    market_price, MARKET_I0, SHOPS, PRODUCTS)

OPP = sys.argv[1] if len(sys.argv) > 1 else "starter"
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1
opp = OPP if OPP in ("starter", "random", "pass") else importlib.import_module(OPP).agent

sold = collections.Counter(); revenue = collections.Counter()
raw = main.Brain.act
def spy(self, obs, config):
    r = raw(self, obs, config)
    for o in r.get("market") or []:
        if isinstance(o, list) and o and o[0] == "SELL":
            item, n = o[1], int(o[2])
            have = self.shed.get(item, 0)
            n = min(n, have)
            if n > 0:
                sold[item] += n
                inv = self.minv[item]
                for _ in range(n):
                    p = market_price(item, inv); revenue[item] += p
                    if p > 1: inv += 1
    return r
main.Brain.act = spy

env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": SEED})
env.run([main.agent, opp])
main.Brain.act = raw
last = env.steps[-1][0]["observation"]
bank = env.steps[-1][0]["reward"]
shops = last["town"]["unlocked_shops"]
prices = last["market"]["prices"]
inv_delta = {k: v - MARKET_I0 for k, v in last["market"]["inventory"].items()}

# What the town consumed this season, from the shops that actually unlocked.
demand = collections.Counter()
tpd = 24
for step in range(720):
    if step % 4 == 0:
        n_shops = min(len(shops), max(0, step // tpd // 3))
        for name in shops[:n_shops]:
            prods = SHOPS[name]; mult = 2 if len(prods) == 1 else 1
            for p in prods: demand[p] += mult
    if step % 24 == 0:
        for p in PRODUCTS:
            if p != "FERTILIZER": demand[p] += 1

print(f"opponent={OPP} seed={SEED}  final bank ${bank:,.0f}")
print(f"shops: {shops}\n")
print(f"{'product':<12}{'town wanted':>12}{'we sold':>9}{'our revenue':>13}"
      f"{'avg $':>7}{'end price':>10}{'unserved':>10}{'left on table':>15}")
tot_left = 0.0
for p in PRODUCTS:
    d = demand[p]; s = sold[p]; rev = revenue[p]
    unserved = max(0, -inv_delta.get(p, 0))
    # what those unserved units would have fetched, walking the curve back up
    left = 0.0; inv = MARKET_I0 + inv_delta.get(p, 0)
    for _ in range(int(unserved)):
        left += market_price(p, inv); inv += 1
    tot_left += left
    print(f"{p:<12}{d:>12}{s:>9}{rev:>13,.0f}{rev/max(1,s):>7.0f}"
          f"{prices[p]:>10}{unserved:>10}{left:>15,.0f}")
print(f"\ntotal earned ${sum(revenue.values()):,.0f}   "
      f"total still unserved ${tot_left:,.0f}"
      f"   -> we capture {100*sum(revenue.values())/max(1,sum(revenue.values())+tot_left):.0f}% "
      f"of what this market would pay")
