# Kaggriculture agent

An autonomous agent for the [Kaggriculture](https://www.kaggle.com/competitions/kaggriculture)
simulation competition: two farms, one shared market, 720 turns, most coins wins.

`main.py` is the submission — a single self-contained file with no dependencies
outside the standard library.

```bash
.venv/bin/python tools/preflight.py          # check it the way Kaggle will
kaggle competitions submit kaggriculture -f main.py -m "..."
```

You submit the *file*; you never run it yourself. Kaggle imports it, takes the
last callable defined in it (which must be `agent`), and plays it in episodes
against other bots. A notebook that merely executes the code proves nothing and
submits nothing.

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
| `tools/preflight.py` | run before every submission — reproduces Kaggle's load path and Validation Episode |
| `tools/replay.py` | reduce a Kaggle replay (~24 MB) to a committable digest (~11 KB) |
| `tools/harvest.py` | download every new episode, digest it, and write `episodes/INDEX.md` |
| `tools/watch.py` | see an episode spatially: per-day farm map with the crew overlaid, and walking vs working |
| `episodes/` | the match history, small enough to live in git |
| `bot_ref.py` | frozen earlier agent, kept as a regression opponent |

## Results

Against the environment's built-in `starter` agent, 40 paired episodes
(20 seeds x both seatings):

| | |
| --- | --- |
| record | 40W-0L |
| mean final bank | $117,160 |
| median / worst | $118,236 / $88,343 |
| vs `random` | 20W-0L, mean $117,166 |
| vs the previous committed agent | 18W-6L head to head |

Per-turn latency is 3.8 ms mean, 11.6 ms worst — the competition's `actTimeout`
is 1 second. The agent also completes cleanly on non-default configurations
(`boardSize` 4, `turnsPerDay` 12, `shedCapacity` 20, `farmHandCostMult` 40,
48-step seasons, `marketParams` overrides) and in either seat.

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

## Keeping the match history in git

Raw replays are ~24 MB each, which is why they normally get looked at once and
thrown away. `tools/harvest.py` downloads each new episode, reduces it to an
~11 KB digest, and deletes the replay — so the whole season's games can be
committed and read later:

```bash
python tools/harvest.py --team "Your Kaggle Team Name"
git add episodes && git commit -m "episodes" && git push
```

A digest keeps per-day farm composition and bank for both players, the full
price trajectory, where each side's turns went, and the market's end state.

To see a game rather than tabulate it, `tools/watch.py` prints the farm as a
map with the crew's standing positions overlaid — the thing you would notice
watching the replay, which no aggregate shows:

```bash
python tools/watch.py <replay.json> --team "Your Team" --days 12,22
python tools/watch.py <replay.json> --html game.html   # the real Kaggle visualizer, offline
```

**Seat identity comes from `info.TeamNames` in the replay**, which is why
`--team` matters. Two traps it avoids: the seats are not otherwise labelled,
and the first episode a submission plays is the **Validation Episode** — the
agent against a copy of itself. That one is always a near-tie and says nothing
about strength; the digest labels its result `self` and leaves it out of the
win/loss record.
