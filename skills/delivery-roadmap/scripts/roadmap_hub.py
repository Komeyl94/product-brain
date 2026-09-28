"""Shared hub plumbing for the delivery-roadmap scripts.

Everything product-specific is read from the hub's brain.config.json. Nothing in
this skill may carry a default for a product fact: a missing key is an error that
names the key and shows an example value.
"""

import json
import sys
sys.dont_write_bytecode = True
from pathlib import Path

CONFIG_NAME = "brain.config.json"

# This file lives at <skills>/delivery-roadmap/scripts/, both hub-locally
# (.claude/skills/...) and in the plugin (skills/...). Sibling skills resolve from here.
SKILLS = Path(__file__).resolve().parents[2]


def utf8_stdio():
    """Windows consoles default to a legacy code page and raise on non-ASCII."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def fail(msg, code=2):
    """Stop with the reason on stderr and a non-zero exit."""
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def find_hub(explicit=None):
    """Return the hub root: --hub if given, else the first ancestor of CWD
    (inclusive) that contains brain.config.json."""
    if explicit:
        hub = Path(explicit).resolve()
        if not (hub / CONFIG_NAME).is_file():
            fail(f"FAIL: --hub {hub} has no {CONFIG_NAME}")
        return hub
    here = Path.cwd().resolve()
    for cand in (here, *here.parents):
        if (cand / CONFIG_NAME).is_file():
            return cand
    fail(f"FAIL: no {CONFIG_NAME} found in {here} or any parent. Run from inside a "
         "Product Brain hub, or pass --hub <path>.")


def load_config(hub):
    path = Path(hub) / CONFIG_NAME
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        fail(f"{CONFIG_NAME}: cannot read {path}: {exc}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"{CONFIG_NAME}: invalid JSON at line {exc.lineno} col {exc.colno}: {exc.msg}")


_MISSING = object()


def get(cfg, dotted, default=_MISSING):
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None if default is _MISSING else default
        cur = cur[part]
    return cur


def require(cfg, dotted, example):
    """Read a required config key or stop (exit 2) with a message naming it."""
    val = get(cfg, dotted)
    if val in (None, "", [], {}):
        fail(f"FAIL: {CONFIG_NAME} is missing `{dotted}`.\n  Add it, e.g.  {example}")
    return val


# Characters git forbids in ref names (git check-ref-format), plus whitespace.
BAD_REF_CHARS = set(" ~^:?*[\\\t\n")


def require_ref_name(cfg, dotted, example):
    """A branch name from config: required, and never option-shaped - a value
    starting with '-' would be read by git as a flag."""
    val = require(cfg, dotted, example)
    if (not isinstance(val, str) or val.startswith("-") or not val.strip()
            or BAD_REF_CHARS & set(val) or ".." in val):
        fail(f"FAIL: {CONFIG_NAME} `{dotted}` = {val!r} is not a valid branch name.\n"
             f"  e.g.  {example}")
    return val


def repo_path(cfg, hub, entry):
    """One rule for every skill: repos[].path (hub-relative) if set, else
    <workspace.repos_dir>/<id> if set, else repos/<id>."""
    rid = entry["id"]
    if entry.get("path"):
        return (Path(hub) / entry["path"]).resolve()
    repos_dir = get(cfg, "workspace.repos_dir")
    if repos_dir:
        return (Path(hub) / repos_dir / rid).resolve()
    return (Path(hub) / "repos" / rid).resolve()


def rel_to_hub(hub, path):
    """Hub-relative posix path when the clone is inside the hub, else absolute."""
    try:
        return Path(path).resolve().relative_to(Path(hub).resolve()).as_posix()
    except ValueError:
        return Path(path).resolve().as_posix()


def repos(cfg, hub):
    """[(id, absolute clone path)] from `repos`, resolved by repo_path()."""
    entries = require(cfg, "repos", '"repos": [{"id": "my-api", "url": "..."}]')
    out = []
    for r in entries:
        rid = r.get("id") if isinstance(r, dict) else None
        if not rid:
            fail(f"FAIL: a `repos` entry has no `id`: {r!r}")
        out.append((rid, repo_path(cfg, hub, r)))
    return out
