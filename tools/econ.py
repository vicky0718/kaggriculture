"""Numeric analysis of Kaggriculture market absorption + per-action / per-tile-day yields."""
import sys, math
sys.path.insert(0, "/home/user/kaggriculture/.venv/lib/python3.11/site-packages")
from kaggle_environments.envs.kaggriculture.kaggriculture import (
    market_price, MARKET_PARAMS, CROPS, ANIMALS, PRODUCTS, MARKET_I0)

def cumulative_sell(item, n, start_inv=MARKET_I0):
    """Revenue from selling n units one at a time starting at start_inv."""
    inv = start_inv; total = 0
    for _ in range(n):
        p = market_price(item, inv)
        total += p
        if p > 1:
            inv += 1
    return total

print("=== SELL ABSORPTION (revenue for dumping N units from I0) ===")
print(f"{'item':<12}{'N=50':>9}{'N=100':>9}{'N=200':>9}{'N=400':>9}{'N=800':>10}{'N=2000':>10}{'p@400':>7}{'p@2000':>8}")
for it in PRODUCTS:
    row = [cumulative_sell(it, n) for n in (50,100,200,400,800,2000)]
    inv400 = MARKET_I0 + 400; inv2000 = MARKET_I0 + 2000
    print(f"{it:<12}" + "".join(f"{v:>9,}" if v<1e9 else "" for v in row[:4])
          + f"{row[4]:>10,}{row[5]:>10,}"
          + f"{market_price(it,inv400):>7}{market_price(it,inv2000):>8}")

print()
print("=== MARGINAL PRICE after selling k units ===")
print(f"{'item':<12}" + "".join(f"{k:>7}" for k in (0,25,50,100,150,200,300,500,1000,3000)))
for it in PRODUCTS:
    print(f"{it:<12}" + "".join(f"{market_price(it, MARKET_I0+k):>7}" for k in (0,25,50,100,150,200,300,500,1000,3000)))

print()
print("=== BUY WHEAT cost (draining market inventory) ===")
inv = MARKET_I0; tot = 0
for n in range(1, 3001):
    p = market_price("WHEAT", inv-1); tot += p; inv -= 1
    if n in (100,200,400,800,1500,3000):
        print(f"  buy {n:>5}: total ${tot:>8,}  avg ${tot/n:6.1f}  marginal ${p}")
