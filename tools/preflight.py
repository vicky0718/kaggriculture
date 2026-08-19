"""Run this before every Kaggle submission.

Reproduces exactly what the competition does to your file:
  1. loads main.py the way Kaggle does -- by exec'ing it and taking the LAST
     callable defined, which must be `agent`;
  2. runs the Validation Episode (your agent against a copy of itself), which
     is what marks a submission Error if it throws;
  3. checks per-turn latency against the 1 second actTimeout;
  4. confirms the file only imports the standard library.

Usage:  .venv/bin/python tools/preflight.py [path/to/main.py]
"""
import ast
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, ".venv/lib/python3.11/site-packages"))

from kaggle_environments import make
from kaggle_environments.agent import get_last_callable

# Ask Python itself what the standard library is, rather than guessing.
STDLIB_OK = set(sys.stdlib_module_names)

path = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "main.py"))
raw = open(path).read()
fails = []

# --- 1. entry point -------------------------------------------------------
fn = get_last_callable(raw, path=path)
name = getattr(fn, "__name__", str(fn))
print(f"1. entry point            : {name}")
if name != "agent":
    fails.append(f"Kaggle would call {name!r}, not 'agent'. Nothing callable may be "
                 f"defined after the agent function.")

# --- 2. imports -----------------------------------------------------------
mods = set()
for node in ast.walk(ast.parse(raw)):
    if isinstance(node, ast.Import):
        mods.update(a.name.split(".")[0] for a in node.names)
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        mods.add(node.module.split(".")[0])
extra = sorted(mods - STDLIB_OK)
print(f"2. imports                : {sorted(mods) or 'none'}"
      + (f"   <-- non-stdlib: {extra}" if extra else ""))
if extra:
    fails.append(f"Imports outside the standard library ({extra}) must be bundled "
                 f"in a tar.gz, not submitted as a bare main.py.")

# --- 3. validation episode (agent vs a copy of itself) --------------------
t0 = time.time()
env = make("kaggriculture", configuration={"episodeSteps": 720}, debug=True)
env.run([path, path])
last = env.steps[-1]
elapsed = time.time() - t0
statuses = [s["status"] for s in last]
print(f"3. validation episode     : {elapsed:.1f}s  "
      + "  ".join(f"p{i}=${s['reward']:,.0f} [{s['status']}]" for i, s in enumerate(last)))
if any(s != "DONE" for s in statuses):
    fails.append(f"Validation episode did not finish cleanly: {statuses}. "
                 f"Kaggle would mark the submission Error.")

# --- 4. per-turn latency --------------------------------------------------
worst = 0.0
env2 = make("kaggriculture", configuration={"episodeSteps": 240, "seed": 3})
agent_fn = get_last_callable(raw, path=path)
obs_seen = 0
for step in env2.run([path, "starter"]):
    pass
# time the agent directly on real observations
env3 = make("kaggriculture", configuration={"episodeSteps": 240, "seed": 3})
env3.reset(2)
for i in range(200):
    obs = env3.state[0].observation
    t = time.perf_counter()
    agent_fn(obs, env3.configuration)
    worst = max(worst, time.perf_counter() - t)
    env3.step([{"farmer": ["PASS"], "hands": [], "market": []}] * 2)
print(f"4. worst turn latency     : {worst*1000:.1f} ms   (actTimeout is 1000 ms)")
if worst > 0.4:
    fails.append(f"Worst turn took {worst*1000:.0f} ms; the 1 s actTimeout is at risk.")

# --- verdict --------------------------------------------------------------
print()
if fails:
    print("FAILED - do not submit:")
    for f in fails:
        print(f"  * {f}")
    sys.exit(1)
print(f"READY TO SUBMIT: {path}")
print(f'  kaggle competitions submit kaggriculture -f {os.path.basename(path)} -m "your message"')
