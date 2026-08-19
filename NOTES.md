# Kaggriculture — strategy notes

Derived from the actual environment source
(`kaggle_environments/envs/kaggriculture/kaggriculture.py`), not just the README.

## Market absorption (revenue for dumping N units from I0, solo)

| item | N=50 | N=100 | N=200 | N=400 | N=2000 | price@+400 |
|---|---|---|---|---|---|---|
| EGG | 2,244 | 4,371 | 8,510 | 16,559 | **77,221** | $40 |
| WHEAT | 1,127 | 2,193 | 4,293 | 8,313 | 39,043 | $20 |
| MELON | 12,098 | **21,721** | 26,527 | 26,727 | 28,327 | $1 |
| FERTILIZER | 4,755 | 9,010 | 16,020 | 24,040 | 26,552 | $20 |
| TOMATO | 2,411 | 4,318 | 7,221 | 10,453 | 12,599 | $9 |
| CARROT | 1,482 | 2,738 | 4,832 | 7,853 | 11,838 | $12 |
| WOOL | **7,655** | 7,969 | 8,069 | 8,269 | 9,869 | $1 |
| MILK | 5,430 | 6,205 | 6,305 | 6,505 | 8,105 | $1 |
| STRAWBERRY | 3,648 | 3,847 | 3,947 | 4,147 | 5,747 | $1 |

`log`-glut resources (EGG, WHEAT) never crash — they are the only unbounded
income. Everything else saturates; `sq`/`linear` glut resources (MELON, WOOL,
MILK, STRAWBERRY) hit the $1 floor within ~50-150 units.

## Consequences

1. **Eggs are the engine.** A cared-for goose yields **2 eggs/day forever**
   (CARE banks +1, interval 1 → paid out every day) at a price that stays
   $36-44 no matter how many are sold. ~$76/day for 2.5 actions and 1 wheat.
2. **Fertilizer is the best early action.** Every surviving animal makes 1/day
   free; `COLLECT_FERTILIZER` is one action for $100 → $60 (first 200 units =
   $16k). Fertilizer is never consumed by the town, so it only saturates.
3. **Melon is the best burst**: 100 melons = $21.7k for ~17 tiles of seed
   ($1.4k). Past ~140 units it adds nothing.
4. **Wool/milk beat geese per coin but only for 2 animals each** — the first
   50 wool alone is $7.6k for a $500 sheep; unit 60 onward is worth $1.
5. **Buy wheat, don't over-grow it** — first 100 cost $31.7 avg, but 1500 cost
   $50.8 avg. Grow a base load, buy the top-up while the marginal price is sane.
6. **Hands are nearly free**: fib cost 1,1,2,3,5,8,13,21,... — 12 hands/day is
   $376. Action supply, not labour cost, is the constraint.

## Mechanics that bite

- `SELL` reads **only the shed**; harvested goods sit in unit inventories until
  a `DROP`/`PLACE` or the end-of-day auto-drop. Shed cap 100, overflow is
  **destroyed** — sell down the shed before hour 23.
- A new seed starts at `consecutive_unwatered = 1`: it **must** be watered on
  its planting day or it is a weed that night.
- Watering only adds yield inside `[ceil(max_yield_day/2), max_yield_day]`;
  outside that window water only to keep the plant alive (every other day).
- One-time crops must be harvested the same day as the last watering — decay
  starts at `(planted_day + max_yield_day + 1) * 24` and strips 1 unit every
  other *turn*.
- Melon caps at 6 units by age 10 even though `max_yield_day` is 12.
- `PLANT` is atomic per crop per turn: if requests exceed seeds held, **all**
  of that crop's plant requests that turn are dropped.
- Locked tiles are passable, and `PICKUP`/`DROP`/`PLACE`-into-shed work from a
  locked shed-access tile — which is where hired hands spawn.
- `actTimeout` is **1 second** per turn.

## What the tuning actually found

Every number below is a paired delta over 28 episodes (14 seeds, both
seatings) against the built-in `starter` agent, measured with `tools/sweep.py`.

| change | effect |
| --- | --- |
| livestock must beat the best crop on a shared capacity metric | **+$39,372 ± 4,932** |
| raise the marginal-profit bar for buying an animal ($260 → $1,500) | +$28,631 ± 2,527 |
| smaller minimum crew (the early game has little to do) | +$2,210, worst case $65k → $88k |
| keep hiring past hour 1 (sell orders share the 10-order budget) | +$593 ± 356 |
| capping the melon wave at 96 units | **−$13,952 ± 4,602** |
| stockpiling seed far ahead (ties up cash) | −$8,870 ± 3,476 |
| making livestock clear an even higher crop bar (2.2×) | −$18,846 ± 6,285 |
| buying land earlier | neutral — land is not the constraint, turns are |

The single biggest error in early versions was valuing an animal at the spot
price of its product. A sheep bought at $200/wool depresses the price of every
unit of wool the farm was already going to sell, so the agent bought 18 sheep
and 16 cows and finished the season selling wool at $5 and milk at $3. Pricing
purchases at the *integral* of the price curve — revenue with the animal minus
revenue without it — is what fixed it.

The second biggest was treating tiles as the scarce resource. They are not:
seasons routinely end with a third of the farm idle. Farm-hand turns are
scarce, and about half of them go to walking, so an option that needs 3.4
actions per tile-day (an animal) has to clear a much higher bar than one that
needs 1.2 (a crop).

## Still on the table

- Strawberry demand goes unserved almost every game (the town wants ~400 units
  and pays $250-340 for them). The crop planner ranks it correctly but rarely
  gets the farm-hand turns to plant and tend a 17-day crop.
- Roughly 50% of unit-turns are movement and another 12% are shed pickups.
  Territory-based routing — giving each hand a contiguous patch for the day
  instead of re-solving the assignment globally every turn — is the obvious
  next step.
