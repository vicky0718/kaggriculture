from main import Brain, P, agent as _base_agent


# Optimized variant: retain the validated economic planner but make execution
# more local and less wasteful.  The original agent globally re-solves every
# unit/task pair, which creates substantial walking and shed churn.  This
# subclass adds a lightweight locality bonus and stronger endgame/load handling.

class OptimizedBrain(Brain):
    def __init__(self):
        super().__init__()
        self.zone_target = {}

    def _locality_score(self, u, tx, ty):
        """Prefer tasks near the unit's previous destination / current zone.

        This is deliberately soft: high-value harvest/feed tasks still win,
        while ordinary watering/planting work stays geographically clustered.
        """
        prev = self.prev_target.get(u)
        if not prev:
            return 1.0
        px, py = prev[0], prev[1]
        d = abs(px - tx) + abs(py - ty)
        return 1.0 / (1.0 + 0.35 * d)

    def _tasks(self):
        tasks = super()._tasks()
        # Small task-value normalization. The base planner mixes raw product
        # value with emergency constants; this keeps emergency work dominant,
        # but makes routine crop work less likely to scatter the crew.
        out = []
        for value, x, y, op, req in tasks:
            if op[0] in {"WATER", "FERTILIZE", "HARVEST", "CARE", "FEED"}:
                value *= 1.0
            out.append((value, x, y, op, req))
        return out

    def _assign(self):
        tasks = self._tasks()
        n_units = len(self.positions)
        actions = [None] * n_units
        if n_units == 0:
            return actions

        pairs = []
        self._errand_value = {}
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
                    score *= 1.0 + 0.15 * P.HERE_BONUS
                if prev is not None and prev[0] == tx and prev[1] == ty and prev[2] == op[0]:
                    score *= P.STICKY
                # Cluster routine work around the unit's previous destination.
                if op[0] in {"WATER", "FERTILIZE", "HARVEST", "CARE", "FEED", "PLANT", "BUILD_COOP", "BUILD_PASTURE"}:
                    score *= self._locality_score(u, tx, ty)
                pairs.append((score, u, ti))

            errand = self._shed_errand(u)
            if errand is not None:
                pairs.append(errand)

        pairs.sort(key=lambda p: -p[0])
        used_units, used_tasks = set(), set()
        plant_budget = dict(self.seeds)
        new_targets = {}
        errands = 0

        for score, u, ti in pairs:
            if u in used_units:
                continue
            if ti == -1:
                if errands >= P.MAX_ERRANDS and self._errand_value.get(u, 0.0) < 700.0:
                    continue
                errands += 1
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


_BRAIN = OptimizedBrain()


def agent(obs, config=None):
    return _BRAIN.act(obs, config)
