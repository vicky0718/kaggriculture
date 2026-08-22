"""Scarcity-aware value: the town drains inventory all season, so supplying a
product earns prices ABOVE base until our own supply catches up with demand."""
import sys
from kaggle_environments.envs.kaggriculture.kaggriculture import (
    market_price, MARKET_I0, SHOPS, PRODUCTS, CROPS, ANIMALS)

# Shop instances unlock on days 3,6,...,24 -> active for 27,24,21,18,15,12,9,6 days.
SHOP_DAYS = sum([27, 24, 21, 18, 15, 12, 9, 6])   # = 132 shop-days
NSHOPS = len(SHOPS)

demand = {p: 30.0 for p in PRODUCTS if p != "FERTILIZER"}   # town centre, 1/day
demand["FERTILIZER"] = 0.0
for name, prods in SHOPS.items():
    mult = 2 if len(prods) == 1 else 1
    for p in prods:
        # each shop-day = 6 ticks of 1 unit (x2 for single-product shops)
        demand[p] += SHOP_DAYS * 6 * mult / NSHOPS

print("=== expected season-long TOWN DEMAND per product ===")
for p in PRODUCTS:
    print(f"  {p:<12} {demand[p]:>7.0f}")

def revenue(item, n, drain):
    """Revenue for selling n units while the town removes `drain` over the season,
    interleaved evenly (sell rate and drain rate both spread across the season)."""
    inv = MARKET_I0
    tot = 0.0
    steps = max(n, 1)
    for k in range(steps):
        inv -= drain / steps            # town pulls
        p = market_price(item, int(round(inv)))
        tot += p
        if p > 1:
            inv += 1
    return tot

print()
print("=== avg $/unit when WE supply N units against expected town demand ===")
print(f"{'item':<12}" + "".join(f"{n:>8}" for n in (25,50,100,200,300,500,800)))
for it in PRODUCTS:
    row = []
    for n in (25,50,100,200,300,500,800):
        row.append(revenue(it, n, demand[it]) / n)
    print(f"{it:<12}" + "".join(f"{v:>8.0f}" for v in row))

print()
print("=== crop economics at those prices (per tile, unfertilised) ===")
print(f"{'crop':<12}{'units':>6}{'tiledays':>9}{'actions':>8}{'$/tile-day':>11}{'$/action':>9}  (price assumed)")
def crop_row(crop, price):
    cd = CROPS[crop]
    if crop == "WHEAT":   units, days, acts = 4, 5, 6
    elif crop == "CARROT":units, days, acts = 3, 4, 5
    elif crop == "MELON": units, days, acts = 6, 11, 10
    elif crop == "TOMATO":units, days, acts = 4, 13, 14
    else:                 units, days, acts = 4, 17, 16   # strawberry
    rev = units*price - cd["seed"]
    print(f"{crop:<12}{units:>6}{days:>9}{acts:>8}{rev/days:>11.0f}{rev/acts:>9.0f}  (${price})")

for crop, n in (("WHEAT",300),("CARROT",300),("MELON",100),("TOMATO",200),("STRAWBERRY",100)):
    crop_row(crop, revenue(crop, n, demand[crop])/n)

print()
print("=== fertilised variants ===")
for crop, units, days, acts, n in (("WHEAT",6,5,7,300),("CARROT",4,4,6,300),
                                   ("MELON",6,9,9,100),("STRAWBERRY",8,17,20,100),
                                   ("TOMATO",8,13,18,200)):
    price = revenue(crop, n, demand[crop])/n
    rev = units*price - CROPS[crop]["seed"] - 1*0   # fertilizer opportunity cost added later
    print(f"  {crop:<11}{units:>3}u {days:>3}d {acts:>3}a  ${rev/days:>6.0f}/tile-day  ${rev/acts:>6.0f}/action  (${price:.0f})")

print()
print("=== animals (steady state, with CARE) ===")
for a, per_day, price_n in (("GOOSE",2.0,800),("COW",1.5,150),("SHEEP",4/3,120)):
    ad = ANIMALS[a]
    price = revenue(ad["product"], price_n, demand[ad["product"]])/price_n
    fert = revenue("FERTILIZER", 300, 0)/300
    gross = per_day*price
    print(f"  {a:<7} {per_day:.2f}/day x ${price:>5.0f} = ${gross:>6.0f}/day "
          f"+1 fert(${fert:.0f})  feed -1 wheat  ~2.6 actions")
