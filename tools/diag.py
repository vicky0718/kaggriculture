"""Per-day execution diagnostics: are animals actually fed/cared/harvested?"""
import sys
sys.path.insert(0, "/home/user/kaggriculture/.venv/lib/python3.11/site-packages")
sys.path.insert(0, "/home/user/kaggriculture")
from kaggle_environments import make
import importlib, main, os
importlib.reload(main)
SEED=int(os.environ.get("SEED","1")); POS=int(os.environ.get("POS","0"))
OPP=os.environ.get("OPP","starter")
env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": SEED}, debug=True)
def _load(n):
    if n in ("random","pass","starter"): return n
    m = importlib.import_module(n); return m.agent
_o = _load(OPP)
env.run([main.agent, _o] if POS==0 else [_o, main.agent])

print(f"{'day':>4}{'$':>10}{'anim':>5}{'fed':>4}{'car':>4}{'unhrv':>6}{'plants':>7}"
      f"{'free':>5}{'weed':>5}{'shedN':>6}{'carry':>6}{'wheat':>6}{'hands':>6}")
for day in range(30):
    step = day*24 + 23           # last turn of the day, before end-of-day refresh
    if step >= len(env.steps): break
    st = env.steps[step]
    obs = st[0]["observation"]; farm = obs["farms"][POS]
    priv = st[POS]["observation"].get("private", {})
    fed = car = unh = anim = plants = free = weed = 0
    mix = {}
    for row in farm["tiles"]:
        for t in row:
            if t is None: free += 1
            elif t == "LOCKED": pass
            elif t.get("kind") == "PLANT": plants += 1
            elif t.get("kind") == "WEED": weed += 1
            elif t.get("animal"):
                anim += 1
                mix[t["animal"]] = mix.get(t["animal"],0)+1
                fed += bool(t["fed_today"]); car += bool(t["cared_today"])
                unh += t["yield_units"]
    shed = priv.get("shed") or {}
    carry = sum(sum(i.values()) for i in (priv.get("inventories") or []))
    print(f"{day:>4}{farm['money']:>10,.0f}{anim:>5}{fed:>4}{car:>4}{unh:>6}{plants:>7}"
          f"{free:>5}{weed:>5}{sum(shed.values()):>6}{carry:>6}{shed.get('WHEAT',0):>6}"
          f"{len(farm['hands']):>6}  {mix} q{len(farm['unlocked_quadrants'])}")

fin = env.steps[-1][0]["observation"]
print("\nmarket inv delta (negative = starved, positive = we glutted):")
print({k: v-10000 for k, v in fin["market"]["inventory"].items()})
print("prices:", fin["market"]["prices"])
