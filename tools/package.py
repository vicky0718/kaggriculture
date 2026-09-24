"""Build a Kaggle submission archive: main.py plus the Apache-2.0 LICENSE and NOTICE.

    python tools/package.py AGENT.py [OUT.tar.gz]

The archive is byte-for-byte reproducible (fixed mtimes, owners and order), so
two builds of the same agent hash identically. The agent is checked the way
Kaggle loads it: the last top-level function must be `agent`.
"""
import ast, gzip, hashlib, io, os, sys, tarfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
agent_path = os.path.abspath(sys.argv[1])
out = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "submission.tar.gz"))

src = open(agent_path, "rb").read()
compile(src, "main.py", "exec")
defs = [n.name for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)]
assert defs and defs[-1] == "agent", f"last top-level function is {defs[-1:]}, Kaggle needs 'agent'"

files = [("main.py", src),
         ("LICENSE.txt", open(os.path.join(HERE, "third_party", "LICENSE.txt"), "rb").read()),
         ("NOTICE.txt", open(os.path.join(HERE, "third_party", "NOTICE.txt"), "rb").read())]
with open(out, "wb") as raw:
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for name, content in files:
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(content), 0o644, 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                tar.addfile(info, io.BytesIO(content))

with tarfile.open(out, "r:gz") as tar:
    assert tar.getnames() == [n for n, _ in files]
    for n, c in files:
        assert tar.extractfile(n).read() == c
print(f"{out}\n  main.py  {len(src):,} bytes  sha256 {hashlib.sha256(src).hexdigest()[:16]}")
print(f"  archive  sha256 {hashlib.sha256(open(out, 'rb').read()).hexdigest()[:16]}")
print(f"  kaggle competitions submit kaggriculture -f {os.path.basename(out)} -m \"...\"")
