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

## Two hypotheses from watching real games

Both came from the user watching ladder episodes. One held up, one did not —
and the one that did not is the more instructive.

**"All the yields weren't collected and sold."** Correct, and it had a single
cause. `tools/leftovers.py` measures value stranded at the whistle, split three
ways: still on the plant or animal, still in the shed, still in a worker's
pockets. It was $1,324 a game, essentially all of it *shed wheat* — one unit per
animal, held by a feed reserve that never stood down. Feeding on the last day
produces at the end-of-day refresh, which cannot then be harvested, dropped and
sold. Zeroing the reserve on the final day took stranded value to $77 and won
**22-8 (73% ± 16%)** head to head against the version without it.

**"We need more workers initially."** Does not hold. `MIN_HANDS=12` raises our
own final bank (+$2,374) and loses anyway — 3/24 against a mirror, 9/20 against
a different agent, down from 19/20. The reason is visible in the totals: our
bank rises to $69k but the opponent's rises to $84k, and the *combined* take
goes from $133k to $153k. Hiring early shifts our production out of contention
with theirs, so both sides extract more from the town — and they extract more of
it than we do. Early wages also come out of the capital that should buy land and
seed, and the opening days are already 39-53% PASS.

The general lesson, which cost two rejected changes to learn: **mean final bank
is a misleading objective.** Territory routing and a bigger early crew both
raised our own money while losing more games. Only the win rate counts, and
`tools/eval.py` now prints it with a confidence interval and refuses to call
anything on 24 games that a coin flip could produce.

## Strategies tested and rejected

Twelve structurally different strategies, each measured on win rate against the
sitting agent over 40+ paired games. Two survived. The rejections are recorded
because they are the useful part — they say where the agent is *not* losing.

| change | result |
|---|---|
| fertilize by per-crop value, not a price gate | **REVERTED** — see below |
| drop the final-day wheat reserve | **22W-8L (73% ± 16%)** ✓ |
| filler upkeep work for idle units | 18W-22L over 40 — neutral |
| territory routing (anchors on task clusters) | 6/24 vs 14/24 baseline |
| quadrant zoning (each hand keeps to one 5×5) | 9/40, then 1/40, then 0/40 |
| season-long tile dynamic program | worse on every seed tried |
| favour crops whose planting window is closing | 0/40 at every strength |
| more livestock (`ANIMAL_MIN_PROFIT` 200, `BAR` 0.6) | −$9,577, 14/40 |
| more hands early (`MIN_HANDS` 12) | 3/24 mirror, 9/20 vs another agent |
| ignore the opponent's farm (`OPP_DISCOUNT` 0) | −$12,917, 3/40 |
| price actions or tile-days higher | −$19k and −$18k |
| buy land earlier | −$1,802, 12/40 |

### A caveat on the harness (fixed 2026-09-14)

Until `870c088`, `tools/eval.py` loaded both agents with `importlib.reload()`,
which re-executes a module into its *existing* `__dict__`. Two agents from the
same file therefore shared one `P` class, and whichever loaded second silently
overwrote the first one's overrides. Any `main:X vs main` run was really a
mirror match with `X` discarded.

Sweeps and runs against a separate opponent file (`bot_ref`, `starter`) were
never affected — a different module is already a different namespace. Same-file
A/B runs are the ones to distrust, and the first version of this note was too
generous in saying the table stood: three of the rejections were quoted as
*mirror* matches, which is exactly the corrupted case.

So they were re-run on 2026-09-17 under the fixed loader, 40 paired games each
against `bot_ref`:

| variant | mean bank | paired delta | wins |
|---|---|---|---|
| baseline | 66,723 | — | 21/40 |
| `MIN_HANDS=12` | 66,748 | +25 +/- 4,356 | 16/40 |
| `ANIMAL_MIN_PROFIT=200, ANIMAL_BAR=0.6` | 62,417 | -4,306 +/- 4,342 | 14/40 |
| `OPP_DISCOUNT=0` | 55,470 | **-11,252 +/- 3,277** | 15/40 |

Every verdict holds. Only `OPP_DISCOUNT=0` separates from noise on bank; the
other two are directionally worse at 1.5 standard errors on win rate, which 40
games cannot resolve. But both lose the argument that motivated them, because
neither buys any bank either — the original `MIN_HANDS=12` claim of +$2,374 was
itself a loader artefact and the honest figure is +$25.

A `MIN_HANDS=2` probe that returned 2W-2L under the old loader returns 1W-5L
under the new one.

### The fertilizer change was a regression (reverted 2026-09-17)

`f8abb39` was adopted on a "51W-29L over 80 games" same-file A/B — exactly the
shape the loader bug corrupted. Measured against three *independent* opponents,
40 paired games each, it costs about half the win rate:

| opponent | `v_pre_fert` (`f82abd5`) | `main` (`f8abb39`) |
|---|---|---|
| `bot_ref` | **39/40** | 21/40 |
| `starter` | 116,347 mean | 110,405 mean (**-5,942 +/- 2,858**) |
| `v_pre_all` | **30/40** | 21/40 |
| head to head | 14 | 26 |

Only the head-to-head favours `f8abb39`, and that is the one test shape already
known to be unreliable here. Three independent opponents outweigh one sibling,
so `main.py` is reverted to `f82abd5`.

The likely mechanism: valuing fertilizer per crop makes the agent fertilize
*more*, which shortens cycles and raises yield — and dumping that extra yield
into `sq`-curve products (melon, wool, milk, strawberry) crashes the very price
the extra units were valued at. It optimises production against a price model
that assumes its own output away.

### Crew size is walled off by the hire curve (tested 2026-09-17)

Hands are dismissed every night (`farm["hands"] = []` in `_end_of_day`) and
re-hired each morning at `fib(k)` for the k-th hire of that day, so a crew of n
costs `fib(n+1) - 1` *per day*: $143 at 10, $609 at 13, $2,583 at 16. Against
banks of ~$66k, a crew of 16 costs more than the game is worth.

Measured against `bot_ref`, 40 paired games each, raising both the floor and the
ceiling together (the earlier `MIN_HANDS=12` probe only raised the floor under a
ceiling of 13, so it barely bound):

| crew | wins | paired delta |
|---|---|---|
| baseline (`MAX_HANDS` 13) | 21/40 | — |
| `MIN_HANDS` 13, `MAX_HANDS` 14 | 14/40 | -2,049 +/- 3,858 |
| `MIN_HANDS` 15, `MAX_HANDS` 16 | **0/40** | **-19,768 +/- 3,777** |

Zero wins in forty. There is no "hire as many as the game allows" strategy: the
game allows any number, and the curve prices them out. Note this leaves the
*placement* question untouched — hands respawn on shed tiles every morning, so
the opening walk of each day is still an unmeasured tax.

### What the rejections mean

**Walking is not waste.** Three separate attempts to keep hands near their work
all lost, monotonically harder the more they bound. Over half of unit-turns are
spent moving because the greedy correctly walks three tiles to a $300 job rather
than doing a $50 one underfoot. Constraining it forces the cheap job.

**Unserved demand is not recoverable revenue.** `tools/audit.py` reports that we
capture ~38% of what the market would pay, with $104k of strawberry and $56k of
wool apparently going begging. Both are illusions of the same kind: serving them
needs tile-days and farm-hand turns that do not exist, and the supply would
crash the price it is valued at. Pushing on either — via livestock or via a
closing-window bias — lost decisively. Read that number as a ceiling on a
different farm, not as money left on this one's table.

**Opponent-awareness earns its keep.** Reading the other farm and pricing our
plans against their visible pipeline is worth ~$13k a game; both ignoring them
and over-weighting them are worse than the current 0.7 discount.

The agent is at a genuine local optimum on every dial that exists. Further gains
need a different architecture, not a better setting.

## Scouting the public notebooks

Nothing substantive is readable from a sandbox: every Kaggle notebook, dataset
and discussion page is a JavaScript shell to an unauthenticated fetcher, and the
API returns 401 without a token. Five public Kaggriculture notebooks exist by
title — *Getting Started* (bovard), *Adaptive Replay Agent* and *Adaptive Farm
Intelligence* (flexonafft), *Observable Economic Control* (pilkwang), and
*Kaggriculture 101* — but their contents need a session to read. No competitor
agent code is on GitHub either, which is what you would expect mid-competition.

The one find that matters is a public dataset, **`georgymamarin/kaggriculture-episodes`**:
full replays from across the ladder, not just our own games. Community notebooks
describe mining it by plotting bank curves of top submissions, diffing actions
between top and mid-ladder agents, and regressing final bank on early choices.

That is worth more than any notebook write-up, because it answers the question
this project has never been able to answer: *what do the agents rated 3000
actually do?* Every strategy tested so far was measured against our own variants,
which can only find our own bugs. `tools/profile_agents.py` reads that dataset
directly — it groups replays by team, ranks by mean final bank, and reports each
team's hiring rate, land purchases, peak farm composition and what they sell.
