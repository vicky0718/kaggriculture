"""Sweep agent parameter variants against a fixed opponent, in parallel."""
import sys, argparse, statistics
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from eval import evaluate

ap = argparse.ArgumentParser()
ap.add_argument("variants", nargs="+", help="e.g. 'main' 'main:DROP_MIN=12'")
ap.add_argument("--opp", default="starter")
ap.add_argument("-n", type=int, default=None)
ap.add_argument("-w", type=int, default=4)
ap.add_argument("--seed0", type=int, default=1)
ap.add_argument("--seeds", metavar="FILE", default=None,
                help="file of seeds, one per line (e.g. ladder/seeds.txt)")
a = ap.parse_args()
if a.seeds:
    seeds = [int(x) for x in open(a.seeds)
             if x.strip() and not x.lstrip().startswith("#")]
    if a.n:
        seeds = seeds[:a.n]
else:
    seeds = list(range(a.seed0, a.seed0 + (a.n or 8)))
import math
rows = []
base_scores = None
for v in a.variants:
    res = sorted(evaluate(v, a.opp, seeds, workers=a.w, swap=True))
    mine = [r[2] for r in res]
    w = sum(1 for r in res if r[2] > r[3])
    if base_scores is None:
        base_scores = mine
        diff_txt = "(baseline)"
    else:
        d = [x - y for x, y in zip(mine, base_scores)]
        md_ = statistics.mean(d)
        se = statistics.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else 0.0
        sig = "*" if abs(md_) > 2 * se else " "
        diff_txt = f"{md_:>+9,.0f} +/-{se:>7,.0f}{sig}"
    q = sorted(mine)
    p10 = q[min(len(q) - 1, int(.10 * len(q)))]
    p25 = q[min(len(q) - 1, int(.25 * len(q)))]
    rows.append((statistics.mean(mine), statistics.median(mine), p10, p25, w, len(res), v, diff_txt))
print(f"{'mean':>10}{'median':>10}{'p10':>10}{'p25':>10}{'W/N':>8}  {'paired delta':>20}  variant")
for m, md, p10, p25, w, n, v, dt in rows:
    print(f"{m:>10,.0f}{md:>10,.0f}{p10:>10,.0f}{p25:>10,.0f}{f'{w}/{n}':>8}  {dt:>20}  {v}")
