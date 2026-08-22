"""Parallel multi-seed evaluation."""
import sys, os, time, argparse, importlib, statistics
from concurrent.futures import ProcessPoolExecutor
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


def _one(job):
    a0, a1, seed, steps = job
    from kaggle_environments import make
    def load(n):
        """'main' or 'main:WHEAT_CARRY=12,MIN_HANDS=8' (parameter overrides)."""
        if n in ("random", "pass", "starter"):
            return n
        mod, _, spec = n.partition(":")
        m = importlib.import_module(mod); importlib.reload(m)
        for kv in filter(None, spec.split(",")):
            k, _, v = kv.partition("=")
            cur = getattr(m.P, k)
            setattr(m.P, k, type(cur)(float(v)) if isinstance(cur, (int, float)) else v)
        return m.agent
    env = make("kaggriculture", configuration={"episodeSteps": steps, "seed": seed})
    env.run([load(a0), load(a1)])
    last = env.steps[-1]
    return seed, float(last[0]["reward"] or 0), float(last[1]["reward"] or 0), \
           last[0]["status"], last[1]["status"]


def evaluate(a0, a1, seeds, steps=720, workers=8, swap=True):
    jobs = [(a0, a1, s, steps) for s in seeds]
    if swap:
        jobs += [(a1, a0, s, steps) for s in seeds]
    res = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(_one, jobs)):
            swapped = i >= len(seeds)
            seed, r0, r1, s0, s1 = r
            mine, theirs = (r1, r0) if swapped else (r0, r1)
            st = (s1, s0) if swapped else (s0, s1)
            res.append((seed, swapped, mine, theirs, st))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("agents", nargs="*", default=["main", "starter"])
    ap.add_argument("-n", type=int, default=None)
    ap.add_argument("--seed0", type=int, default=1)
    ap.add_argument("--seeds", metavar="FILE", default=None,
                    help="file of seeds, one per line (e.g. ladder/seeds.txt -- the "
                         "seeds of real ladder episodes). Overrides -n/--seed0.")
    ap.add_argument("-w", "--workers", type=int, default=8)
    ap.add_argument("--noswap", action="store_true")
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args()
    a0, a1 = (a.agents + ["main", "starter"])[:2]
    t0 = time.time()
    if a.seeds:
        seeds = [int(x) for x in open(a.seeds)
                 if x.strip() and not x.lstrip().startswith("#")]
        if a.n:
            seeds = seeds[:a.n]          # --seeds with no -n uses every seed
    else:
        seeds = list(range(a.seed0, a.seed0 + (a.n or 8)))
    res = evaluate(a0, a1, seeds, workers=a.workers, swap=not a.noswap)
    mine = [r[2] for r in res]; theirs = [r[3] for r in res]
    w = sum(1 for r in res if r[2] > r[3]); l = sum(1 for r in res if r[2] < r[3])
    t = len(res) - w - l
    bad = [r for r in res if any(s not in ("DONE",) for s in r[4])]
    if not a.quiet:
        for seed, sw, m, th, st in sorted(res):
            print(f"  seed {seed}{' (swap)' if sw else '      '}: {m:>10,.0f} vs {th:>10,.0f}"
                  + ("  " + str(st) if any(s != "DONE" for s in st) else ""))
    q = sorted(mine)
    def pct(p):
        return q[min(len(q) - 1, int(p * len(q)))]
    print(f"{a0} vs {a1}: {w}W-{l}L-{t}T ({100.0*w/max(1,len(res)):.0f}% win)  "
          f"vs opp mean ${statistics.mean(theirs):,.0f}   [{time.time()-t0:.0f}s]")
    print(f"  own bank  p10 ${pct(.10):>9,.0f}   p25 ${pct(.25):>9,.0f}   median ${statistics.median(mine):>9,.0f}"
          f"   p75 ${pct(.75):>9,.0f}   mean ${statistics.mean(mine):>9,.0f}")
    print(f"  -- the ladder is lost in the bad games: p10/p25 move the win rate, the mean does not.")
    if bad:
        print(f"  !! {len(bad)} episodes with non-DONE status")
