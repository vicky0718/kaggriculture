"""Run Kaggriculture episodes and report money + diagnostics."""
import sys, os, time, json, argparse, importlib
sys.path.insert(0, "/home/user/kaggriculture/.venv/lib/python3.11/site-packages")
sys.path.insert(0, "/home/user/kaggriculture")
from kaggle_environments import make


def load(name):
    if name in ("random", "pass", "starter"):
        return name
    mod = importlib.import_module(name)
    importlib.reload(mod)
    return mod.agent


def run(a0, a1, seed=None, steps=720, verbose=False):
    cfg = {"episodeSteps": steps}
    if seed is not None:
        cfg["seed"] = seed
    env = make("kaggriculture", configuration=cfg, debug=True)
    t0 = time.time()
    env.run([load(a0), load(a1)])
    dt = time.time() - t0
    last = env.steps[-1]
    rewards = [s["reward"] for s in last]
    statuses = [s["status"] for s in last]
    return env, rewards, statuses, dt


def diagnose(env, pid=0):
    """Summarise the final farm + a few checkpoints."""
    out = []
    tpd = 24
    for step in (24, 24*5, 24*10, 24*15, 24*20, 24*25, len(env.steps)-1):
        if step >= len(env.steps):
            continue
        st = env.steps[step]
        obs = st[0]["observation"]
        farm = obs["farms"][pid]
        tiles = farm["tiles"]
        kinds = {}
        for row in tiles:
            for t in row:
                if t is None: k = "empty"
                elif t == "LOCKED": k = "locked"
                elif t.get("kind") == "PLANT": k = t["crop"]
                elif t.get("kind") == "WEED": k = "WEED"
                elif t.get("animal"): k = t["animal"]
                else: k = t.get("kind")
                kinds[k] = kinds.get(k, 0) + 1
        priv = st[pid]["observation"].get("private", {})
        shed = {k: v for k, v in (priv.get("shed") or {}).items() if v}
        out.append(f"  d{step//tpd:>2} ${farm['money']:>9,.0f} quad={len(farm['unlocked_quadrants'])} "
                   f"{ {k:v for k,v in sorted(kinds.items()) if k not in ('locked',)} } shed={shed}")
    final = env.steps[-1][0]["observation"]
    out.append("  market prices: " + str(final["market"]["prices"]))
    out.append("  market inv delta: " + str({k: v-10000 for k, v in final["market"]["inventory"].items()}))
    out.append("  shops: " + str(final["town"]["unlocked_shops"]))
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("agents", nargs="*", default=["main", "starter"])
    ap.add_argument("-n", "--games", type=int, default=1)
    ap.add_argument("-s", "--steps", type=int, default=720)
    ap.add_argument("--seed0", type=int, default=1)
    ap.add_argument("-d", "--diag", action="store_true")
    ap.add_argument("--swap", action="store_true", help="also play the mirror seating")
    args = ap.parse_args()
    a0, a1 = (args.agents + ["main", "starter"])[:2]

    wins = [0, 0, 0]
    tot = [0.0, 0.0]
    for i in range(args.games):
        seed = args.seed0 + i
        env, r, stat, dt = run(a0, a1, seed=seed, steps=args.steps)
        tot[0] += r[0]; tot[1] += r[1]
        wins[0 if r[0] > r[1] else (1 if r[1] > r[0] else 2)] += 1
        print(f"seed {seed}: {a0}=${r[0]:>10,.0f}  {a1}=${r[1]:>10,.0f}  "
              f"[{stat[0]},{stat[1]}]  {dt:.1f}s")
        if args.diag:
            print(diagnose(env, 0))
        if args.swap:
            env, r, stat, dt = run(a1, a0, seed=seed, steps=args.steps)
            tot[0] += r[1]; tot[1] += r[0]
            wins[0 if r[1] > r[0] else (1 if r[0] > r[1] else 2)] += 1
            print(f"seed {seed} (swap): {a0}=${r[1]:>10,.0f}  {a1}=${r[0]:>10,.0f}  {dt:.1f}s")
    g = args.games * (2 if args.swap else 1)
    print(f"\n{a0} vs {a1}: {wins[0]}W-{wins[1]}L-{wins[2]}T   "
          f"avg ${tot[0]/g:,.0f} vs ${tot[1]/g:,.0f}")
