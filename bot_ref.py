"""Kaggriculture competition agent.

Strategy
--------
The town drains the shared market every single turn (a shop instance eats 6
units/day of everything it wants, the town centre 1/day of everything), and the
price curve rises steeply below the starting inventory.  So the market is not a
dumping ground -- it is a standing order worth several hundred dollars a unit
for anything nobody is supplying.  Wool, milk and strawberry sit near $200-300
all season unless somebody floods them; egg and wheat are the only products
whose glut curve is logarithmic, so they are the deep end of the pool.

The agent therefore:

  * projects, for every product, what the price will be once the town's
    remaining demand, our own crop/herd pipeline and *the opponent's visible
    pipeline* have all played out, and values every decision at that price;
  * buys whichever animal has the best marginal profit at those projected
    prices -- ruminants first (a sheep is ~$270/tile/day), geese for scale once
    wool and milk saturate;
  * runs one melon wave (~$150/tile/day, saturates near 150 units);
  * treats *actions*, not money, as the scarce resource: hands cost a
    fibonacci pittance, so it hires a full crew and assigns every unit each turn
    to the pending job with the best coins-per-turn (value / (1 + distance)).

Logistics matter as much as strategy: SELL only reaches the shed, and the
end-of-day auto-drop silently destroys anything past the 100-item cap, so the
agent keeps the shed drained and pushes carriers home before the day ends.
"""

import math

# --------------------------------------------------------------------------
# Game constants, mirrored from the environment.
# --------------------------------------------------------------------------

CROPS = {
    "WHEAT":      {"seed": 10,  "first_yield_day": 2,  "max_yield_day": 4,  "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20,  "first_yield_day": 2,  "max_yield_day": 3,  "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50,  "first_yield_day": 8,  "max_yield_day": 8,  "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80,  "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]

SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}

MARKET_I0 = 10000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0

MARKET_PARAMS = {
    "WHEAT":      {"base":  25, "I0": MARKET_I0, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base":  35, "I0": MARKET_I0, "T": 450, "below_func": "hinge",  "below_target": 1.00, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base":  60, "I0": MARKET_I0, "T": 200, "below_func": "hinge",  "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": MARKET_I0, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "I0": MARKET_I0, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base":  50, "I0": MARKET_I0, "T": 332, "below_func": "hinge",  "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "I0": MARKET_I0, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "I0": MARKET_I0, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

LAND_PRICES = [1000, 2000, 4000]
MAX_SHOP_INSTANCES = 8

# Yield / occupancy / action cost of one crop cycle, played optimally.
# (units, days_occupied, actions) without and with a fertilizer application.
CROP_CYCLE = {
    "WHEAT":      {"plain": (4, 5, 6),  "fert": (6, 5, 7)},
    "CARROT":     {"plain": (3, 4, 5),  "fert": (4, 4, 6)},
    "MELON":      {"plain": (6, 11, 10), "fert": (6, 9, 9)},
    "TOMATO":     {"plain": (4, 13, 14), "fert": (8, 13, 18)},
    "STRAWBERRY": {"plain": (4, 17, 16), "fert": (8, 17, 20)},
}


def _shape(func, x, T=None):
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def market_price(item, inventory):
    """Exact copy of the environment's price curve, so we can plan sales."""
    p = MARKET_PARAMS[item]
    base, I0, T = p["base"], p["I0"], p["T"]
    if inventory < I0:
        f = p["below_func"]
        amp = p["below_target"] * base / _shape(f, T, T)
        price = base + amp * _shape(f, I0 - inventory, T)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / _shape(f, T, T)
        price = base - amp * _shape(f, inventory - I0, T)
    return max(PRICE_FLOOR, int(round(price)))


def animal_rate(animal):
    """Units per day in steady state when the animal is fed and CAREd daily."""
    a = ANIMALS[animal]
    return (1.0 + a["interval"]) / a["interval"]


# --------------------------------------------------------------------------
# Tunable parameters
# --------------------------------------------------------------------------

class P:
    MIN_HANDS = 7
    MAX_HANDS = 16
    HIRE_CASH_FRAC = 0.06        # marginal hand allowed while fib(k) <= this * cash
    HIRE_CASH_FLOOR = 34          # ...but always allow cheap hands

    CASH_RESERVE_BASE = 450       # never invest the farm down to nothing
    CASH_RESERVE_PER_ANIMAL = 22

    WHEAT_BUY_MAX_PRICE = 70
    WHEAT_RESERVE_DAYS = 1.35
    WHEAT_RESERVE_CAP = 70        # wheat hogging the shed is what destroys produce
    WHEAT_CARRY = 15

    LAND_RESERVE = 700
    LAND_LAST_DAY = 23

    ANIMAL_MIN_PROFIT = 500       # marginal profit needed to buy one more
    CROP_MIN_SCORE = 4.0
    TILE_WEIGHT = 1.0             # relative scarcity of a tile-day...
    ACTION_WEIGHT = 1.0           # ...versus a unit-turn
    ANIMAL_ACTIONS_PER_DAY = 3.4  # feed + care + harvest/collect amortised
    ANIMAL_BAR = 1.0              # livestock must also beat this x the best crop
    SEED_BATCH = 6                # max seeds of one crop bought per turn
    SEED_LOOKAHEAD = 12           # tiles of planting to keep seed for

    OPP_DISCOUNT = 0.7            # assume the opponent realises 70% of its pipeline
    OWN_DISCOUNT = 0.85

    SELL_FRAC = {
        "WHEAT": 0.0, "EGG": 0.0, "FERTILIZER": 0.15, "MELON": 0.10,
        "CARROT": 0.18, "TOMATO": 0.18, "MILK": 0.10, "WOOL": 0.10,
        "STRAWBERRY": 0.12,
    }
    DUMP_FROM_DAY = 28

    DROP_MIN = 5
    WALK_OVERHEAD = 0.5           # turns spent walking per turn of real work
    DROP_URGENCY = 1.0
    MOVE_PENALTY = 1.0            # score = value / (1 + MOVE_PENALTY * distance)
    HERE_BONUS = 1.0              # finish the tile you are standing on
    STICKY = 1.4
    SHED_TARGET = 55              # keep the shed this empty so drops always fit


def _g(obj, key, default=None):
    if obj is None:
        return default
    try:
        if key in obj:
            v = obj[key]
            return default if v is None else v
    except TypeError:
        pass
    return getattr(obj, key, default)


def _quadrant_of(x, y, half):
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def _step_toward(fx, fy, tx, ty):
    if fx < tx:
        return "EAST"
    if fx > tx:
        return "WEST"
    if fy < ty:
        return "SOUTH"
    if fy > ty:
        return "NORTH"
    return None


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


class Brain:
    def __init__(self):
        self.prev_target = {}
        self.melon_units_planted = 0

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    def _parse(self, obs, config):
        self.board = int(_g(config, "boardSize", 10) or 10)
        self.turns_per_day = int(_g(config, "turnsPerDay", 24) or 24)
        episode_steps = int(_g(config, "episodeSteps", 720) or 720)
        self.total_days = max(1, episode_steps // self.turns_per_day)
        self.shed_cap = int(_g(config, "shedCapacity", 100) or 100)
        self.half = self.board // 2

        self.player = int(_g(obs, "player", 0) or 0)
        self.day = int(_g(obs, "day", 0) or 0)
        self.hour = int(_g(obs, "hour", 0) or 0)
        self.step = self.day * self.turns_per_day + self.hour
        self.last_day = self.total_days - 1
        self.days_left = self.last_day - self.day
        self.endgame = self.days_left <= 0

        self.farms = _g(obs, "farms", []) or []
        self.farm = self.farms[self.player]
        self.tiles = self.farm["tiles"]
        self.money = float(self.farm["money"])
        self.quadrants = set(self.farm.get("unlocked_quadrants", ["NW"]))
        self.hires_today = int(self.farm.get("hires_today", 0))

        private = _g(obs, "private", {}) or {}
        self.shed = dict(_g(private, "shed", {}) or {})
        self.seeds = dict(_g(private, "seeds", {}) or {})
        self.invs = [dict(i) for i in (_g(private, "inventories", []) or [{}])]

        market = _g(obs, "market", {}) or {}
        self.minv = dict(_g(market, "inventory", {}) or {})
        self.prices = dict(_g(market, "prices", {}) or {})
        for it in PRODUCTS:
            self.minv.setdefault(it, MARKET_I0)
            self.prices.setdefault(it, MARKET_PARAMS[it]["base"])

        town = _g(obs, "town", {}) or {}
        self.shops = list(_g(town, "unlocked_shops", []) or [])

        self.positions = [list(self.farm["farmer"])] + [list(p) for p in self.farm.get("hands", [])]
        while len(self.invs) < len(self.positions):
            self.invs.append({})

        self.shed_tiles = [(self.half - 1, self.half - 1), (self.half, self.half - 1),
                           (self.half - 1, self.half), (self.half, self.half)]

        self._crop_seq_cache = None
        self._scan_farm()
        self._scan_opponent()
        self._price_model()

    def _scan_farm(self):
        self.animals, self.empty_structs, self.plants = [], [], []
        self.empty_tiles, self.weeds = [], []
        self.crop_counts = {c: 0 for c in CROPS}
        self.own_pipeline = {p: 0.0 for p in PRODUCTS}

        days = max(0.0, float(self.days_left))
        for y in range(self.board):
            row = self.tiles[y]
            for x in range(self.board):
                t = row[x]
                if t is None:
                    if _quadrant_of(x, y, self.half) in self.quadrants:
                        self.empty_tiles.append((x, y))
                    continue
                if t == "LOCKED" or not isinstance(t, dict):
                    continue
                kind = t.get("kind")
                if kind == "PLANT":
                    self.plants.append((x, y, t))
                    crop = t["crop"]
                    self.crop_counts[crop] = self.crop_counts.get(crop, 0) + 1
                    cd = CROPS[crop]
                    left = max(0, cd["max_yield"] - 2 - t.get("yield_units", 0))
                    self.own_pipeline[crop] += t.get("yield_units", 0) + left
                elif kind == "WEED":
                    self.weeds.append((x, y))
                elif t.get("animal"):
                    self.animals.append((x, y, t))
                    a = ANIMALS[t["animal"]]
                    first = t.get("placed_day", self.day) + a["first_yield_day"]
                    prod = max(0, self.last_day - max(self.day, first) + 1)
                    self.own_pipeline[a["product"]] += animal_rate(t["animal"]) * prod
                    self.own_pipeline["FERTILIZER"] += days
                else:
                    self.empty_structs.append((x, y, t))

        self.n_animals = len(self.animals)
        self.n_geese = sum(1 for _, _, t in self.animals if t["animal"] == "GOOSE")
        self.n_sheep = sum(1 for _, _, t in self.animals if t["animal"] == "SHEEP")
        self.n_cows = sum(1 for _, _, t in self.animals if t["animal"] == "COW")
        self.have = {"GOOSE": self.n_geese, "COW": self.n_cows, "SHEEP": self.n_sheep}
        self.empty_coops = [(x, y) for x, y, t in self.empty_structs if t["kind"] == "COOP"]
        self.empty_pastures = [(x, y) for x, y, t in self.empty_structs if t["kind"] == "PASTURE"]

        # Animals want a visit every day, so they get the ground nearest the shed.
        self.empty_tiles.sort(key=lambda p: self._shed_dist(p[0], p[1]))

        self.carried = {}
        for inv in self.invs:
            for k, v in inv.items():
                self.carried[k] = self.carried.get(k, 0) + v
        self.total_carried = sum(self.carried.values())
        self.shed_used = sum(self.shed.values())
        self.pending_animals = {a: self.shed.get(a, 0) + self.carried.get(a, 0) for a in ANIMALS}

    def _scan_opponent(self):
        """Their farm is public: read their pipeline so we don't flood a market
        they are about to flood, and do flood one they have abandoned."""
        self.opp_pipeline = {p: 0.0 for p in PRODUCTS}
        if len(self.farms) < 2:
            return
        opp = self.farms[1 - self.player]
        days = max(0.0, float(self.days_left))
        for row in opp["tiles"]:
            for t in row:
                if not isinstance(t, dict):
                    continue
                if t.get("animal"):
                    a = ANIMALS[t["animal"]]
                    self.opp_pipeline[a["product"]] += animal_rate(t["animal"]) * days
                    self.opp_pipeline["FERTILIZER"] += days
                elif t.get("kind") == "PLANT":
                    cd = CROPS[t["crop"]]
                    self.opp_pipeline[t["crop"]] += cd["max_yield"] - 2

    def _town_demand(self, item, days):
        """Units the town will consume over the next `days` days, including the
        shops we can still expect to unlock."""
        if item == "FERTILIZER" or days <= 0:
            return 0.0
        per_day = 1.0                                  # town centre
        for shop in self.shops:
            prods = SHOPS.get(shop)
            if prods and item in prods:
                per_day += 6.0 * (2 if len(prods) == 1 else 1)
        total = per_day * days

        expected = sum(6.0 * (2 if len(v) == 1 else 1)
                       for v in SHOPS.values() if item in v) / len(SHOPS)
        n, d = len(self.shops), self.day
        while n < MAX_SHOP_INSTANCES:
            nxt = (d // 3 + 1) * 3
            if nxt > self.last_day:
                break
            total += expected * max(0, min(days, self.last_day - nxt))
            n += 1
            d = nxt
        return total

    def _pipeline_of_new_animal(self, animal, place_day=None):
        """(product units, fertilizer units) one more of `animal` would add."""
        a = ANIMALS[animal]
        place_day = self.day + 1 if place_day is None else place_day
        prod = max(0, self.last_day - (place_day + a["first_yield_day"]) + 1)
        alive = max(0, self.last_day - place_day + 1)
        return animal_rate(animal) * prod, float(alive)

    def _price_model(self):
        """Projected end-of-season inventory per product, before our new plans."""
        self.proj_inv = {}
        self.own_supply = {}
        self.market_base = {}
        days = max(0.0, float(self.days_left))

        # Animals sitting in the shed or a pocket will be placed within a turn or
        # two; their whole future output is already committed.
        for animal, n in self.pending_animals.items():
            if n <= 0:
                continue
            units, fert = self._pipeline_of_new_animal(animal)
            self.own_pipeline[ANIMALS[animal]["product"]] += units * n
            self.own_pipeline["FERTILIZER"] += fert * n
        for it in PRODUCTS:
            inv = (self.minv[it]
                   - self._town_demand(it, days)
                   + P.OWN_DISCOUNT * self.own_pipeline[it]
                   + P.OPP_DISCOUNT * self.opp_pipeline[it]
                   + self.shed.get(it, 0) + self.carried.get(it, 0))
            self.proj_inv[it] = inv
            self.own_supply[it] = (P.OWN_DISCOUNT * self.own_pipeline[it]
                                   + self.shed.get(it, 0) + self.carried.get(it, 0))
            self.market_base[it] = inv - self.own_supply[it]

    def _revenue(self, item, base_inv, qty, steps=16):
        """Total proceeds from selling `qty` units into a market sitting at
        `base_inv` -- the integral of the price curve, not qty x spot price."""
        if qty <= 0:
            return 0.0
        h = qty / steps
        tot = 0.0
        for i in range(steps):
            tot += market_price(item, int(round(base_inv + i * h + h * 0.5)))
        return tot * h

    def marginal_revenue(self, item, extra, already=0.0):
        """What `extra` more units are really worth once the price they push
        down on everything we were already going to sell is paid for."""
        base = self.market_base.get(item, MARKET_I0)
        s0 = self.own_supply.get(item, 0.0) + already
        return self._revenue(item, base, s0 + extra) - self._revenue(item, base, s0)

    def proj_price(self, item, extra=0.0):
        """Price we expect to realise for a unit sold on top of `extra` more supply."""
        return market_price(item, int(round(self.proj_inv[item] + extra)))

    def _shed_dist(self, x, y):
        return min(abs(x - sx) + abs(y - sy) for sx, sy in self.shed_tiles)

    def _nearest_shed_tile(self, x, y):
        return min(self.shed_tiles, key=lambda s: abs(x - s[0]) + abs(y - s[1]))

    def _cash_reserve(self):
        return P.CASH_RESERVE_BASE + P.CASH_RESERVE_PER_ANIMAL * self.n_animals

    # ------------------------------------------------------------------
    # investment planning
    # ------------------------------------------------------------------

    def _wheat_unit_cost(self):
        return float(market_price("WHEAT", int(self.minv["WHEAT"]) - 1))

    def _animal_marginal(self, animal, extra_already):
        """Profit from buying one more of `animal`, given how many we've already
        committed to this turn."""
        a = ANIMALS[animal]
        place_day = self.day + 1
        start = place_day + a["first_yield_day"]
        prod_days = self.last_day - start + 1
        if prod_days <= 0:
            return -1e9
        rate = animal_rate(animal)
        units = rate * prod_days
        alive_days = self.last_day - place_day + 1
        fert_units = float(alive_days)

        revenue = self.marginal_revenue(a["product"], units, extra_already * units)
        revenue += 0.7 * self.marginal_revenue(
            "FERTILIZER", fert_units, extra_already * fert_units)

        feed = alive_days * self._wheat_unit_cost() * 0.95
        return revenue - a["cost"] - feed

    def _animal_capacity_score(self, animal, extra_already):
        """Animal profit per unit of scarce capacity, directly comparable with
        _crop_score, so livestock only takes a tile a crop would use better."""
        profit = self._animal_marginal(animal, extra_already)
        alive = max(1, self.last_day - (self.day + 1) + 1)
        denom = alive * P.TILE_WEIGHT + P.ANIMAL_ACTIONS_PER_DAY * alive * P.ACTION_WEIGHT
        return profit, profit / denom

    def _best_crop_score(self):
        seq = self._crop_sequence()
        if not seq:
            return 0.0
        return max(0.0, self._crop_score(seq[0]))

    def _animal_orders(self, cash):
        """Greedy marginal-profit shopping list; cheapest structure work first."""
        orders, counts = [], {a: 0 for a in ANIMALS}
        if self.endgame or self.days_left < 4:
            return orders, counts
        # An animal we cannot feed and CARE for every day is worth half as much,
        # so cap the herd at what the crew can actually service.
        crew = 1 + max(self._target_hands(), P.MIN_HANDS)
        tendable = int(crew * 20 * 0.62 / 3.4)
        headroom = tendable - self.n_animals - sum(self.pending_animals.values())
        if headroom <= 0:
            return orders, counts
        budget = cash
        crop_bar = self._best_crop_score() * P.ANIMAL_BAR
        for _ in range(min(6, headroom)):
            best, best_profit, best_score = None, P.ANIMAL_MIN_PROFIT, crop_bar
            for animal in ANIMALS:
                if ANIMALS[animal]["cost"] > budget:
                    continue
                profit, score = self._animal_capacity_score(animal, counts[animal])
                # Never buy an animal we have nowhere to put, and never take a
                # tile a crop would earn more from.
                if (profit > best_profit and score > best_score
                        and self._structure_room(animal, counts)):
                    best, best_profit, best_score = animal, profit, score
            if best is None:
                break
            counts[best] += 1
            budget -= ANIMALS[best]["cost"]
        for animal, n in counts.items():
            if n:
                orders.append(["BUY_ANIMAL", animal, n])
        return orders, counts

    def _structure_room(self, animal, counts):
        """Is there a free structure or free tile for this animal?"""
        need_coop = counts["GOOSE"] + self.pending_animals.get("GOOSE", 0)
        need_past = (counts["COW"] + counts["SHEEP"]
                     + self.pending_animals.get("COW", 0) + self.pending_animals.get("SHEEP", 0))
        free_tiles = len(self.empty_tiles)
        if animal == "GOOSE":
            spare = len(self.empty_coops) - need_coop
        else:
            spare = len(self.empty_pastures) - need_past
        if spare > 0:
            return True
        used = max(0, need_coop - len(self.empty_coops)) + max(0, need_past - len(self.empty_pastures))
        return free_tiles - used > 0

    def _crop_cycle(self, crop):
        use_fert = (self.shed.get("FERTILIZER", 0) + self.carried.get("FERTILIZER", 0) > 2
                    or self.n_animals >= 3) and self.proj_price("FERTILIZER") < 78
        return CROP_CYCLE[crop]["fert" if use_fert else "plain"], use_fert

    def _crop_score(self, crop, committed=0.0):
        """Coins per unit of scarce capacity for starting one cycle of `crop`,
        given `committed` units of that crop already planned this turn.

        Uses marginal revenue, so the tenth melon tile is priced at what the
        tenth melon tile actually fetches once the first nine have sold."""
        (units, days, acts), use_fert = self._crop_cycle(crop)
        if days > self.days_left - 1:
            return -1.0        # planted tomorrow it would not finish; don't stock it
        revenue = self.marginal_revenue(crop, units, committed)
        if crop == "WHEAT" and self.n_animals:
            # Home-grown wheat displaces a purchase at the (rising) buy price,
            # which is usually worth more than selling it.
            revenue = max(revenue, units * self._wheat_unit_cost() * 0.95)
        profit = revenue - CROPS[crop]["seed"]
        if use_fert:
            profit -= 2 * self.proj_price("FERTILIZER") if CROPS[crop]["ongoing"] \
                else self.proj_price("FERTILIZER")
        return profit / float(days * P.TILE_WEIGHT + acts * P.ACTION_WEIGHT)

    def _crop_sequence(self):
        """Which crop each free tile should get, best-first, re-pricing after
        every choice so the plan diversifies instead of flooding one market."""
        if self._crop_seq_cache is not None:
            return self._crop_seq_cache
        n = min(len(self.empty_tiles) + 6, 30)
        seq, committed = [], {c: 0.0 for c in CROPS}
        if self.endgame:
            self._crop_seq_cache = seq
            return seq
        for _ in range(n):
            best, best_s = None, P.CROP_MIN_SCORE
            for crop in CROPS:
                s = self._crop_score(crop, committed[crop])
                if s > best_s:
                    best, best_s = crop, s
            if best is None:
                break
            seq.append(best)
            committed[best] += self._crop_cycle(best)[0][0]
        self._crop_seq_cache = seq
        return seq

    def _tile_plan(self):
        """What each free tile should become, nearest-to-shed first.

        Returns a list of (x, y, action) aligned with self.empty_tiles."""
        plan = []
        free = self.empty_tiles
        if not free or self.endgame:
            return plan

        need_coop = self.pending_animals.get("GOOSE", 0) - len(self.empty_coops)
        need_past = (self.pending_animals.get("COW", 0) + self.pending_animals.get("SHEEP", 0)
                     - len(self.empty_pastures))
        # Keep a small buffer of empty structures so a purchase is never stalled.
        if self.days_left >= 6 and not self.endgame:
            need_past = max(need_past, 1 if len(self.empty_pastures) == 0 else 0)
            need_coop = max(need_coop, 1 if len(self.empty_coops) == 0 else 0)

        idx = 0
        for _ in range(max(0, min(need_past, len(free) - idx))):
            plan.append((free[idx][0], free[idx][1], ["BUILD_PASTURE"]))
            idx += 1
        for _ in range(max(0, min(need_coop, len(free) - idx))):
            plan.append((free[idx][0], free[idx][1], ["BUILD_COOP"]))
            idx += 1

        seq = list(self._crop_sequence())
        counts = {}
        while idx < len(free) and seq:
            crop = seq.pop(0)
            if self.seeds.get(crop, 0) - counts.get(crop, 0) <= 0:
                continue                       # no seed yet; the next tile tries again
            counts[crop] = counts.get(crop, 0) + 1
            plan.append((free[idx][0], free[idx][1], ["PLANT", crop]))
            idx += 1
        return plan

    def _seed_orders(self, cash):
        """Buy exactly the seeds the tile plan is about to ask for."""
        want = {}
        soon = sum(1 for _, _, t in self.plants
                   if self.day - t["planted_day"] >= CROPS[t["crop"]]["max_yield_day"])
        limit = min(len(self.empty_tiles) + soon + 2, P.SEED_LOOKAHEAD)
        for crop in self._crop_sequence()[:limit]:
            want[crop] = want.get(crop, 0) + 1
        orders, budget = [], cash
        for crop, n in sorted(want.items(), key=lambda kv: -kv[1]):
            # Buy a turn or two's worth, not the whole plan: seeds we cannot get
            # into the ground before the crop's window closes are dead money.
            n = min(n, P.SEED_BATCH)
            n = int(min(max(0, n - self.seeds.get(crop, 0)), budget // CROPS[crop]["seed"]))
            if n > 0:
                orders.append(["BUY_SEED", crop, n])
                budget -= n * CROPS[crop]["seed"]
        return orders

    # ------------------------------------------------------------------
    # market orders
    # ------------------------------------------------------------------

    def _wheat_need_total(self):
        """Wheat the farm should own, in the shed and in pockets together."""
        if self.days_left < 0 or not self.n_animals:
            return 0
        return int(min(self.n_animals * P.WHEAT_RESERVE_DAYS + 8,
                       P.WHEAT_RESERVE_CAP,
                       self.n_animals * (self.days_left + 1)))

    def _wheat_shed_target(self):
        """How much to keep loadable in the shed. The shed also has to hold a
        day's produce, so this is deliberately less than a full day's feed --
        units top up again as the morning's stock is carried out."""
        return int(min(self._wheat_need_total(), max(14, self.shed_cap - 52)))

    def _wheat_reserve(self):
        """Shed wheat that must not be sold."""
        return max(0, self._wheat_need_total() - self.carried.get("WHEAT", 0))

    def _sell_quantity(self, item, held, dump):
        if held <= 0:
            return 0
        floor = 1 if dump else max(1.0, P.SELL_FRAC.get(item, 0.2) * MARKET_PARAMS[item]["base"])
        inv = self.minv[item]
        n = 0
        while n < held:
            if market_price(item, inv) < floor:
                break
            inv += 1
            n += 1
        return n

    def _fertilizer_reserve(self):
        if self.endgame or self.proj_price("FERTILIZER") > 70:
            return 0
        return min(10, len(self.plants))

    def _target_hands(self):
        work = 3.6 * self.n_animals + 1.35 * len(self.plants)
        work += 2.2 * min(len(self.empty_tiles), 22) + 1.5 * len(self.weeds)
        work *= 1.0 + P.WALK_OVERHEAD                       # walking and shed trips
        want = int(math.ceil(work / 20.0)) - 1
        want = max(P.MIN_HANDS, min(P.MAX_HANDS, want))
        if self.endgame:
            want = min(want, 5)
        allow = max(P.HIRE_CASH_FLOOR, P.HIRE_CASH_FRAC * self.money)
        for k in range(want):
            if _fib(k) > allow:
                return k
        return want

    def _plan_market(self):
        orders = []
        dump = self.day >= P.DUMP_FROM_DAY or self.endgame
        pressure = self.shed_used + self.total_carried > self.shed_cap - 12

        # 1. Sell first: the proceeds fund everything below in the same queue.
        wheat_reserve = self._wheat_reserve()
        fert_reserve = self._fertilizer_reserve()
        sells = []
        for item in PRODUCTS:
            held = self.shed.get(item, 0)
            if held <= 0:
                continue
            if item == "WHEAT":
                held = max(0, held - wheat_reserve)
            elif item == "FERTILIZER":
                held = max(0, held - fert_reserve)
            if held <= 0:
                continue
            n = self._sell_quantity(item, held, dump or pressure)
            if n <= 0 and pressure:
                n = held                       # room matters more than price now
            if n > 0:
                sells.append((self.prices.get(item, 0) * n, ["SELL", item, n]))
        sells.sort(key=lambda s: -s[0])
        orders.extend(o for _, o in sells[:6])

        # 2. Hire early so the crew gets a full shift.
        if self.hour <= 1 and not self.endgame:
            todo = max(0, self._target_hands() - self.hires_today)
            orders.extend([["HIRE"]] * min(todo, max(0, 10 - len(orders))))
        if len(orders) >= 10:
            return orders[:10]

        orders.extend(self._plan_buys()[:10 - len(orders)])
        return orders[:10]

    def _hire_cost_today(self):
        want = self._target_hands()
        return sum(_fib(k) for k in range(self.hires_today, max(self.hires_today, want)))

    def _plan_buys(self):
        buys = []
        reserve = self._cash_reserve() + self._hire_cost_today()
        cash = self.money

        # Feed comes first: a starved animal is gone for good.
        have = self.shed.get("WHEAT", 0)
        deficit = min(self._wheat_shed_target() - have,
                      self._wheat_need_total() - have - self.carried.get("WHEAT", 0))
        if deficit > 0 and self.days_left >= 0:
            price = self._wheat_unit_cost()
            limit = P.WHEAT_BUY_MAX_PRICE
            if self.n_animals and have + self.carried.get("WHEAT", 0) < self.n_animals * 0.75:
                limit = 400                     # emergency top-up
            if price <= limit:
                room = max(0, self.shed_cap - self.shed_used - 6)
                n = int(min(deficit, room, cash // max(1.0, price)))
                if n > 0:
                    buys.append(["BUY_PRODUCT", "WHEAT", n])
                    cash -= n * price

        spare = max(0.0, cash - reserve)

        # Land: 25 more tiles is cheap next to what a tile earns, but only once
        # we are actually running out of room.
        extra = len(self.quadrants) - 1
        if (extra < len(LAND_PRICES) and self.day <= P.LAND_LAST_DAY
                and self.days_left >= 5 and len(self.empty_tiles) <= 9):
            cost = LAND_PRICES[extra]
            if spare >= cost + P.LAND_RESERVE:
                buys.append(["BUY_LAND"])
                spare -= cost

        # Land that no animal is going to occupy has to be planted, so ring-fence
        # a seed budget before the (much larger) livestock orders drain the bank.
        soon = sum(1 for _, _, t in self.plants
                   if self.day - t["planted_day"] >= CROPS[t["crop"]]["max_yield_day"])
        idle = max(0, len(self.empty_tiles) + soon - sum(self.pending_animals.values()))
        seed_budget = min(spare * 0.55, idle * 120.0)

        seed_orders = self._seed_orders(seed_budget)
        for o in seed_orders:
            spare -= o[2] * CROPS[o[1]]["seed"]

        animal_orders, _ = self._animal_orders(max(0.0, spare))
        for o in animal_orders:
            buys.append(o)
            spare -= o[2] * ANIMALS[o[1]]["cost"]
        buys.extend(seed_orders)
        return buys

    # ------------------------------------------------------------------
    # task generation
    # ------------------------------------------------------------------

    def _tasks(self):
        tasks = []
        add = tasks.append
        unfed_n = sum(1 for _, _, t in self.animals if not t.get("fed_today"))
        self._wheat_covers_herd = (
            self.shed.get("WHEAT", 0) + self.carried.get("WHEAT", 0) >= unfed_n)
        pr = self.prices
        day = self.day
        endgame = self.endgame
        fert_price = pr.get("FERTILIZER", 100)

        for x, y, t in self.animals:
            a = ANIMALS[t["animal"]]
            price = pr.get(a["product"], 0)
            rate = animal_rate(t["animal"])
            units = t.get("yield_units", 0)

            if t.get("fertilizer_available"):
                add((float(fert_price), x, y, ["COLLECT_FERTILIZER"], None))

            if not t.get("fed_today"):
                if endgame:
                    value = 3.0
                elif t.get("consecutive_unfed", 0) >= 1:
                    value = 1500.0            # feed tonight or the animal is gone
                else:
                    # Feeding is what makes CARE pay and keeps production going.
                    value = rate * price * 0.9 + 40
                add((value, x, y, ["FEED"], "WHEAT"))

            if (not t.get("cared_today") and not endgame and self.days_left >= 1
                    and (t.get("fed_today") or self._wheat_covers_herd)):
                if units + math.ceil(rate) <= a["max_held"]:
                    add((price * 1.0, x, y, ["CARE"], None))

            if units > 0:
                overflow = units + math.ceil(rate) > a["max_held"]
                value = units * price
                if overflow or endgame:
                    value += 2.0 * price
                if endgame:
                    value *= 2.0        # unsold stock scores nothing
                if units >= 1 and endgame:
                    add((value, x, y, ["HARVEST"], None))
                elif units >= 2 or overflow or self.hour >= 17:
                    add((value, x, y, ["HARVEST"], None))

        for x, y, t in self.plants:
            crop = t["crop"]
            cd = CROPS[crop]
            price = pr.get(crop, 0)
            age = day - t["planted_day"]
            units = t.get("yield_units", 0)
            watered = t.get("watered_today", False)
            unwatered = t.get("consecutive_unwatered", 0)
            mls = t.get("max_lifespan_step", -1)
            decaying = mls >= 0 and self.step >= mls - 1

            if cd["ongoing"]:
                gain = 0
                fert_on = t.get("fertilized_until_day", -1) >= day
                produces_today = (age + 1 >= cd["first_yield_day"]
                                  and (age + 1 - cd["first_yield_day"]) % cd["interval"] == 0)
                if fert_on and produces_today and not watered:
                    gain = 1                    # watering doubles today's tick
                ready = age >= cd["first_yield_day"] and units > 0
            else:
                ws = (cd["max_yield_day"] + 1) // 2
                in_window = ws <= age <= cd["max_yield_day"]
                room = cd["max_yield"] - units
                bonus = 2 if t.get("fertilized_until_day", -1) >= day else 1
                gain = min(bonus, room) if (in_window and not watered) else 0
                mature = age >= cd["max_yield_day"] or units >= cd["max_yield"]
                ready = (units > 0 and age >= cd["first_yield_day"]
                         and gain == 0 and (mature or decaying or endgame))

            if not watered:
                if gain > 0:
                    add((gain * price, x, y, ["WATER"], None))
                elif unwatered >= 1 and not ready and not endgame:
                    remaining = max(units, cd["max_yield"] - 2)
                    add((remaining * price * 0.6 + 25, x, y, ["WATER"], None))

            if ready:
                add((units * price + 15, x, y, ["HARVEST"], None))

            if (self.days_left >= 2 and not endgame
                    and t.get("fertilized_until_day", -1) < day
                    and units < cd["max_yield"]):
                extra, ok = 0, False
                if cd["ongoing"]:
                    # Ticks fire at ages first_yield-1, +interval, ... ; one
                    # application covers today..today+2, i.e. two ticks.
                    t0 = cd["first_yield_day"] - 1
                    if age >= t0 - 1:
                        k = max(0, -(-(age - t0) // cd["interval"]))
                        nxt = t0 + k * cd["interval"]
                        if nxt - age <= 2:
                            extra, ok = 2, True
                else:
                    ws = (cd["max_yield_day"] + 1) // 2
                    if ws - 1 <= age <= cd["max_yield_day"] - 1:
                        extra = min(cd["max_yield"] - units, cd["max_yield_day"] - age)
                        ok = True
                if ok:
                    value = extra * price - fert_price
                    if value > 0:
                        add((value, x, y, ["FERTILIZE"], "FERTILIZER"))

        if not endgame:
            for x, y in self.empty_coops:
                if self.shed.get("GOOSE", 0) + self.carried.get("GOOSE", 0) > 0:
                    add((self._place_value("GOOSE"), x, y, ["PLACE", "GOOSE"], "GOOSE"))
            for x, y in self.empty_pastures:
                for animal in ("SHEEP", "COW"):
                    if self.shed.get(animal, 0) + self.carried.get(animal, 0) > 0:
                        add((self._place_value(animal), x, y, ["PLACE", animal], animal))
                        break

            for x, y, op in self._tile_plan():
                if op[0] == "PLANT":
                    add((self._plant_value(op[1]), x, y, op, None))
                else:
                    pending = sum(self.pending_animals.values())
                    add((900.0 if pending else 150.0, x, y, op, None))

            if self.days_left >= 3 and self.weeds:
                # A weed only costs us anything when there is no spare land left.
                scarcity = max(0, 10 - len(self.empty_tiles)) / 10.0
                best = max([self._crop_score(c) for c in CROPS] + [0.0])
                dig = 25.0 + scarcity * best * self.days_left * 1.5
                for x, y in self.weeds:
                    add((dig, x, y, ["DIG"], None))

        return tasks

    def _place_value(self, animal):
        a = ANIMALS[animal]
        prod_days = max(0, self.last_day - (self.day + a["first_yield_day"]) + 1)
        return 200.0 + animal_rate(animal) * prod_days * self.prices.get(a["product"], 50) * 0.25

    def _plant_value(self, crop):
        units, days, acts = CROP_CYCLE[crop]["plain"]
        price = self.proj_price(crop, units * 0.5)
        if crop == "WHEAT" and self.n_animals:
            price = max(price, self._wheat_unit_cost() * 0.95)
        return max(8.0, (units * price - CROPS[crop]["seed"]) / float(acts))

    # ------------------------------------------------------------------
    # assignment
    # ------------------------------------------------------------------

    def _assign(self):
        tasks = self._tasks()
        n_units = len(self.positions)
        actions = [None] * n_units
        if n_units == 0:
            return actions

        pairs = []
        for u in range(n_units):
            ux, uy = self.positions[u]
            inv = self.invs[u]
            prev = self.prev_target.get(u)
            for ti, (value, tx, ty, op, req) in enumerate(tasks):
                if req is not None and inv.get(req, 0) <= 0:
                    continue
                dist = abs(ux - tx) + abs(uy - ty)
                score = value / (1.0 + P.MOVE_PENALTY * dist)
                if dist == 0:
                    score *= P.HERE_BONUS     # clear the tile before walking off it
                if prev is not None and prev[0] == tx and prev[1] == ty and prev[2] == op[0]:
                    score *= P.STICKY
                pairs.append((score, u, ti))
            errand = self._shed_errand(u)
            if errand is not None:
                pairs.append(errand)

        pairs.sort(key=lambda p: -p[0])
        used_units, used_tasks = set(), set()
        plant_budget = dict(self.seeds)
        new_targets = {}

        for score, u, ti in pairs:
            if u in used_units:
                continue
            if ti == -1:
                sx, sy = self._nearest_shed_tile(*self.positions[u])
                actions[u] = self._shed_action(u, sx, sy)
                used_units.add(u)
                new_targets[u] = (sx, sy, "SHED")
                continue
            if ti in used_tasks:
                continue
            value, tx, ty, op, req = tasks[ti]
            if op[0] == "PLANT":
                if plant_budget.get(op[1], 0) <= 0:
                    continue
                plant_budget[op[1]] -= 1
            used_units.add(u)
            used_tasks.add(ti)
            new_targets[u] = (tx, ty, op[0])
            ux, uy = self.positions[u]
            if (ux, uy) == (tx, ty):
                actions[u] = list(op)
            else:
                mv = _step_toward(ux, uy, tx, ty)
                actions[u] = [mv] if mv else ["PASS"]

        for u in range(n_units):
            if actions[u] is None:
                actions[u] = self._idle_action(u)
        self.prev_target = new_targets
        return actions

    def _carry_value(self, inv):
        return sum(self.prices.get(k, 20) * v for k, v in inv.items() if k in PRODUCTS)

    def _shed_errand(self, u):
        ux, uy = self.positions[u]
        inv = self.invs[u]
        sx, sy = self._nearest_shed_tile(ux, uy)
        dist = abs(ux - sx) + abs(uy - sy)
        value = 0.0

        produce = sum(v for k, v in inv.items() if k in PRODUCTS and k != "WHEAT")
        # Produce is only money once it reaches the shed: SELL cannot see a
        # pocket, and everything past the shed cap is destroyed at end of day.
        if produce >= P.DROP_MIN:
            urgency = P.DROP_URGENCY
            if self.hour >= self.turns_per_day - 7:
                urgency = 2.5
            if self.shed_used + self.total_carried > self.shed_cap - 10:
                urgency = max(urgency, 3.0)
            if self.endgame:
                urgency = max(urgency, 3.0)
            if self.shed_used >= self.shed_cap - 4:
                urgency = 0.15                  # no room; keep working instead
            value = max(value, self._carry_value(inv) * 0.45 * urgency)

        unfed = [t for _, _, t in self.animals if not t.get("fed_today")]
        stock = self.shed.get("WHEAT", 0)
        if unfed and inv.get("WHEAT", 0) == 0 and stock > 0 and not self.endgame:
            urgent = any(t.get("consecutive_unfed", 0) >= 1 for t in unfed)
            if urgent:
                value = max(value, 1400.0)
            elif stock >= 3:
                # Worth a trip only for a real load -- a one-grain round trip
                # costs more walking than the feed is worth.
                value = max(value, 55.0 * min(stock, P.WHEAT_CARRY, len(unfed)))

        if not any(inv.get(a, 0) for a in ANIMALS):
            for animal, spots in (("SHEEP", self.empty_pastures),
                                  ("COW", self.empty_pastures),
                                  ("GOOSE", self.empty_coops)):
                if spots and self.shed.get(animal, 0) > 0:
                    value = max(value, 700.0)
                    break

        if (self.shed.get("FERTILIZER", 0) > 0 and inv.get("FERTILIZER", 0) == 0
                and self._fertilizer_reserve() > 0 and self.plants):
            value = max(value, 70.0)

        if value <= 0:
            return None
        return (value / (1.0 + dist), u, -1)

    def _shed_action(self, u, sx, sy):
        ux, uy = self.positions[u]
        if (ux, uy) != (sx, sy):
            mv = _step_toward(ux, uy, sx, sy)
            return [mv] if mv else ["PASS"]

        inv = self.invs[u]
        produce = sum(v for k, v in inv.items() if k in PRODUCTS and k != "WHEAT")
        room = self.shed_cap - self.shed_used

        if produce >= P.DROP_MIN and room > 0:
            return ["DROP"]

        unfed = sum(1 for _, _, t in self.animals if not t.get("fed_today"))
        if unfed and self.shed.get("WHEAT", 0) > 0 and inv.get("WHEAT", 0) == 0 and not self.endgame:
            n = min(P.WHEAT_CARRY, self.shed["WHEAT"], max(1, unfed))
            return ["PICKUP", "WHEAT", int(n)]

        for animal, spots in (("SHEEP", self.empty_pastures),
                              ("COW", self.empty_pastures),
                              ("GOOSE", self.empty_coops)):
            if spots and self.shed.get(animal, 0) > 0:
                return ["PICKUP", animal, int(min(3, self.shed[animal], len(spots)))]

        if (self.shed.get("FERTILIZER", 0) > 0 and inv.get("FERTILIZER", 0) == 0
                and self._fertilizer_reserve() > 0):
            return ["PICKUP", "FERTILIZER", min(3, self.shed["FERTILIZER"])]

        if produce and room > 0:
            return ["DROP"]
        return ["PASS"]

    def _idle_action(self, u):
        ux, uy = self.positions[u]
        inv = self.invs[u]
        if sum(v for k, v in inv.items() if k in PRODUCTS and k != "WHEAT") > 0:
            sx, sy = self._nearest_shed_tile(ux, uy)
            if (ux, uy) == (sx, sy):
                if self.shed_used < self.shed_cap:
                    return ["DROP"]
            else:
                mv = _step_toward(ux, uy, sx, sy)
                return [mv] if mv else ["PASS"]
        return ["PASS"]

    # ------------------------------------------------------------------

    def act(self, obs, config):
        self._parse(obs, config)
        if self.step == 0:
            self.melon_units_planted = 0
            self.prev_target = {}
        market = self._plan_market()
        unit_actions = self._assign()
        for a in unit_actions:
            if a and a[0] == "PLANT" and a[1] == "MELON":
                self.melon_units_planted += CROPS["MELON"]["max_yield"]
        return {
            "farmer": unit_actions[0] if unit_actions else ["PASS"],
            "hands": unit_actions[1:],
            "market": market,
        }


_BRAIN = Brain()


def agent(obs, config=None):
    try:
        return _BRAIN.act(obs, config)
    except Exception:
        n = 0
        try:
            farms = _g(obs, "farms", []) or []
            n = len(farms[int(_g(obs, "player", 0) or 0)].get("hands", []))
        except Exception:
            n = 0
        return {"farmer": ["PASS"], "hands": [["PASS"]] * n, "market": []}
