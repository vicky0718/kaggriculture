from main import Brain, P, _step_toward


class OptimizedBrain(Brain):
    """Execution-focused variant of Brain.

    The economic planner is deliberately inherited unchanged.  The main
    difference is worker assignment: routine jobs receive a soft locality
    bonus so workers stop bouncing across the board between unrelated tiles.
    Emergency feed, harvest and shed work can still override locality.
    """

    def _locality_factor(self, u, tx, ty):
        prev = self.prev_target.get(u)
        if not prev:
            return 1.0
        px, py = prev[0], prev[1]
        d = abs(px - tx) + abs(py - ty)
        return 1.0 / (1.0 + 0.35 * d)

    def _assign(self):
        tasks = self._tasks()
        n_units = len(self.positions)
        actions = [None] * n_units
        if not n_units:
            return actions

        pairs = []
        self._errand_value = {}
        routine = {
            "WATER", "FERTILIZE", "HARVEST", "CARE", "FEED", "PLANT",
            "BUILD_COOP", "BUILD_PASTURE", "DIG", "PLACE"
        }

        for u in range(n_units):
            ux, uy = self.positions[u]
            inv = self.invs[u]
            prev = self.prev_target.get(u)

            for ti, (value, tx, ty, op, req) in enumerate(tasks):
                if req is not None and inv.get(req, 0) <= 0:
                    continue

                dist = abs(ux - tx) + abs(uy - ty)
                score = value / (1.0 + P.MOVE_PENALTY * dist)

                # Finish work already under the worker's feet before sending
                # the worker elsewhere.
                if dist == 0:
                    score *= P.HERE_BONUS

                # Keep a worker on the same target while an operation remains
                # useful.  This avoids oscillation between adjacent jobs.
                if prev is not None and prev[0] == tx and prev[1] == ty and prev[2] == op[0]:
                    score *= P.STICKY

                # Soft spatial clustering for routine work.  High-value tasks
                # remain capable of overcoming the penalty.
                if op[0] in routine:
                    score *= self._locality_factor(u, tx, ty)

                pairs.append((score, u, ti))

            errand = self._shed_errand(u)
            if errand is not None:
                pairs.append(errand)

        pairs.sort(key=lambda p: -p[0])
        used_units = set()
        used_tasks = set()
        plant_budget = dict(self.seeds)
        new_targets = {}
        errands = 0

        for score, u, ti in pairs:
            if u in used_units:
                continue

            if ti == -1:
                # Preserve the existing hard cap on simultaneous logistics
                # workers; urgent errands are exempt inside _shed_errand.
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
                crop = op[1]
                if plant_budget.get(crop, 0) <= 0:
                    continue
                plant_budget[crop] -= 1

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
