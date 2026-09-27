#!/usr/bin/env python3
"""Fetch every configured app clone and report what is checked out. Changes nothing.

    python fetch-and-report.py [--hub <path>] [--no-fetch]

The hub root is the first directory at or above the current one that contains
`brain.config.json` (`--hub` overrides). The repos are `brain.config.json` -> `repos[]`;
a clone is `repos[].path` if set (hub-relative), else `<workspace.repos_dir>/<id>` if
`workspace.repos_dir` is set, else `repos/<id>`. Ahead/behind is measured against
`origin/<releases.integration_branch>`, which must exist in every clone (exit 2 if not).
Exit 1 when a fetch failed (the report records `fetched: false`).

WHY THIS EXISTS
---------------
The dashboard needs accurate ahead/behind counts and branch ages, which means the
remote refs must be current. That is all it needs. An earlier version of this script
also forced every clone onto the integration branch so the graph would describe the
production track -- and that was the wrong trade. It refused to run at all while
someone was mid-test on a feature branch with dev-server proxies pointed at its
review app, which is a normal working state, not an error.

So: fetch, report, and leave the working copies exactly as they are. The graph then
describes whatever is checked out, and the DASHBOARD SAYS SO. Disclosure beats
coercion -- a reader who knows the graph covers a feature branch can weigh it; a
reader whose branches were silently moved cannot get their session back.

This script never switches branches, never stashes, never resets, never cleans. It
writes one file: `<graph.out>/.branch-report.json`. check-inputs.py reads it to warn
when a clone has left the branch the graph was built from.
"""

import argparse
import os
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def find_hub(explicit):
    if explicit:
        hub = Path(explicit).resolve()
        if not (hub / "brain.config.json").is_file():
            sys.exit("error: %s has no brain.config.json" % hub)
        return hub
    here = Path.cwd().resolve()
    for d in [here] + list(here.parents):
        if (d / "brain.config.json").is_file():
            return d
    sys.exit("error: no brain.config.json at or above %s - run from inside a Product "
             "Brain hub, or pass --hub <path>" % here)


def load_config(hub):
    """brain.config.json, or one line naming the JSON error (exit 2) - never a traceback."""
    path = hub / "brain.config.json"
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        print("brain.config.json: invalid JSON at line %d col %d: %s" % (exc.lineno, exc.colno, exc.msg))
        sys.exit(2)
    except OSError as exc:
        print("brain.config.json: unreadable: %s" % exc)
        sys.exit(2)


def need(cfg, dotted, example):
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            sys.exit('error: brain.config.json is missing "%s" (example: %s)' % (dotted, example))
        cur = cur[part]
    return cur


def git(path, *args):
    proc = subprocess.run(
        ["git", "-C", str(path)] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def counts(path, left, right):
    """{'behind', 'ahead'} of `right` relative to `left`, or None when a ref is missing."""
    out = git(path, "rev-list", "--left-right", "--count", "%s...%s" % (left, right))
    parts = out.split()
    return {"behind": int(parts[0]), "ahead": int(parts[1])} if len(parts) == 2 else None


def describe(rid, path, base, do_fetch):
    info = {"repo": rid, "path": str(path)}
    if not (path / ".git").exists():
        info["missing"] = True
        print("  %s: NOT CLONED at %s - skipped" % (rid, path))
        return info
    if do_fetch:
        ok = subprocess.run(
            ["git", "-C", str(path), "fetch", "--prune", "--tags", "origin"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).returncode == 0
        info["fetched"] = ok
        print("  %s: %s" % (rid, "fetched origin" if ok else "FETCH FAILED (offline? refs are stale)"))
    else:
        info["fetched"] = False
        print("  %s: fetch skipped" % rid)

    branch = git(path, "rev-parse", "--abbrev-ref", "HEAD")
    info["branch"] = branch
    info["head"] = git(path, "rev-parse", "--short", "HEAD")
    info["headDate"] = git(path, "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d %H:%M")
    info["headSubject"] = git(path, "log", "-1", "--format=%s")

    tracked = [f for f in (git(path, "diff", "--name-only") + "\n" +
                           git(path, "diff", "--cached", "--name-only")).split("\n") if f.strip()]
    info["dirty"] = sorted(set(tracked))

    info["vsUpstream"] = counts(path, "@{upstream}", "HEAD") if branch != "HEAD" else None
    info["base"] = base
    info["baseExists"] = bool(git(path, "rev-parse", "--verify", "--quiet", "refs/remotes/" + base))
    info["vsBase"] = counts(path, base, "HEAD") if info["baseExists"] else None

    print("     on %s @ %s (%s)" % (branch, info["head"], info["headDate"]))
    if info["vsBase"]:
        print("     vs %s: %d ahead / %d behind"
              % (base, info["vsBase"]["ahead"], info["vsBase"]["behind"]))
    else:
        print("     vs %s: REF NOT FOUND in this clone" % base)
    if info["vsUpstream"] and info["vsUpstream"]["ahead"]:
        print("     %d commit(s) NOT PUSHED to its upstream" % info["vsUpstream"]["ahead"])
    if info["dirty"]:
        print("     %d tracked file(s) modified: %s"
              % (len(info["dirty"]), ", ".join(info["dirty"][:4])
                 + (" ..." if len(info["dirty"]) > 4 else "")))
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hub", help="hub root (default: walk up from CWD to brain.config.json)")
    ap.add_argument("--no-fetch", action="store_true",
                    help="skip the fetch (offline; every count may be stale)")
    args = ap.parse_args()

    hub = find_hub(args.hub)
    cfg = load_config(hub)
    repos = need(cfg, "repos", '[{"id": "my-api", "url": "git@host:org/my-api.git"}]')
    if not repos:
        sys.exit('error: brain.config.json "repos" is empty (example: [{"id": "my-api"}])')
    integration = need(cfg, "releases.integration_branch", '"develop"')
    if not isinstance(integration, str) or not integration or integration.startswith("-") \
            or any(c in integration for c in " ~^:?*[\\") or ".." in integration:
        print('brain.config.json: releases.integration_branch %r is not a valid branch name'
              % (integration,))
        return 2
    base = "origin/%s" % integration
    ws_dir = cfg.get("workspace", {}).get("repos_dir")
    graph_out = hub / cfg.get("graph", {}).get("out", "graph/")
    report_file = graph_out / ".branch-report.json"

    print("Hub: %s" % hub)
    print("Fetching and reporting. Working copies are not touched.")
    out = []
    for r in repos:
        rid = r.get("id")
        if not rid:
            sys.exit('error: every brain.config.json "repos" entry needs an "id" (example: "my-api")')
        path = hub / (r["path"] if r.get("path") else os.path.join(ws_dir or "repos", rid))
        out.append(describe(rid, path, base, not args.no_fetch))

    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as fh:
        json.dump({"base": base, "repos": out}, fh, indent=2, ensure_ascii=False)

    print("\nWritten to %s" % report_file.relative_to(hub).as_posix())
    print("The graph will describe these branches. The dashboard must say which:")
    for r in out:
        if r.get("missing"):
            print("  %-22s not cloned" % r["repo"])
            continue
        note = []
        if r["dirty"]:
            note.append("%d modified file(s)" % len(r["dirty"]))
        if r["vsUpstream"] and r["vsUpstream"]["ahead"]:
            note.append("%d unpushed" % r["vsUpstream"]["ahead"])
        print("  %-22s %s @ %s%s"
              % (r["repo"], r["branch"], r["head"],
                 (" (" + ", ".join(note) + ")") if note else ""))
    if args.no_fetch:
        print("\nOffline next steps: do NOT re-graph or re-run producers. Gate with "
              "check-inputs.py --offline and disclose every input's age on the page.")
    else:
        print("\nNext: re-graph the checkout without pulling - the sync command the hub's "
              "CLAUDE.md documents, with no-pull flags only if CLAUDE.md documents them.")
    missing = [r["repo"] for r in out if not r.get("missing") and not r.get("baseExists")]
    if missing:
        print("error: releases.integration_branch %r does not exist as %s in: %s"
              % (integration, base, ", ".join(missing)))
        return 2
    failed = [r["repo"] for r in out
              if not args.no_fetch and r.get("fetched") is False and not r.get("missing")]
    if failed:
        print("error: fetch failed for %s - counts are from stale refs" % ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
