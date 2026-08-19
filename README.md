# Kaggriculture agent

An autonomous agent for the [Kaggriculture](https://www.kaggle.com/competitions/kaggriculture)
simulation competition: two farms, one shared market, 720 turns, most coins wins.

`main.py` is the submission — a single self-contained file with no dependencies
outside the standard library.

```
kaggle competitions submit kaggriculture -f main.py -m "..."
```

## How it decides things

The environment's price curve is reimplemented inside the agent, so every
decision can be priced instead of guessed.

**The market is a standing order, not a dumping ground.** The town consumes
product every turn — a shop instance eats 6 units/day of everything it wants,
the town centre 1/day of everything — and the price curve rises steeply below
the starting inventory. Anything nobody supplies drifts far above base
(strawberry and milk routinely sit above $250 all season). Egg and wheat are
the only products with a logarithmic glut curve, so they are the only ones that
absorb unlimited volume; wool, milk, melon and strawberry hit the $1 floor
within 50-150 units of oversupply.

So the agent projects, for each product, the inventory the market will actually
end the season at:

```
projected = current inventory
          - town demand still to come      (from the unlocked shop list)
          + our own pipeline                (crops in the ground, herd, shed)
          + the opponent's pipeline         (their farm is public — we read it)
```

and prices every plan at that level.

**Investments are judged on marginal revenue, not spot price.** Buying one more
sheep depresses the price of every unit of wool we were already going to sell,
so a purchase is valued as the *integral* of the price curve over our supply
with the animal minus the integral without it. This is what stops the agent
flooding its own market — an early version bought 18 sheep and 16 cows and sold
wool at $5.

**Actions, not money, are the scarce resource.** Hiring is fibonacci-priced
(1, 1, 2, 3, 5, 8, …), so a dozen hands cost $376/day while a single farm hand
is worth thousands. The agent hires a full crew and then treats the day as an
assignment problem: every pending job on the farm is scored in coins, and units
are matched to jobs greedily by coins-per-turn, `value / (1 + distance)`.

## Layout

| file | |
| --- | --- |
| `main.py` | the agent (submission) |
| `NOTES.md` | strategy notes and the mechanics that bite, derived from reading the environment source |
| `tools/econ.py` | market absorption per product |
| `tools/econ2.py` | scarcity-aware value per crop / animal, including town demand |
| `tools/eval.py` | parallel multi-seed evaluation, with `agent:PARAM=value` overrides |
| `tools/sweep.py` | compares variants with paired per-seed statistics |
| `tools/diag.py` | per-day execution trace (fed / cared / unharvested / idle land) |
| `tools/actions.py` | where the crew's turns actually go |

## Testing

```bash
python3 -m venv .venv && .venv/bin/pip install -U kaggle-environments
.venv/bin/python tools/eval.py main starter -n 8        # vs the built-in baseline
.venv/bin/python tools/sweep.py main bot_ref --opp starter -n 14
```

`tools/sweep.py` reports a paired delta against the first variant with a
standard error, because single-episode results vary by a factor of two — the
shops that unlock are drawn at random, and which products the town wants
dominates the score.
