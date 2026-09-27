#!/usr/bin/env python3
"""Gate the product-hub rebuild: are the inputs fresh, and do they agree with the page?

    python check-inputs.py [--hub <path>] [--offline] [--first-build]

--first-build: no page exists yet (also assumed when the page file is missing and git has
never tracked it). The missing page is then a PASS with a note and every page check is
skipped; the inputs, graph and state are still gated.

--offline: the refresh ran without fetching or re-running producers, so an input whose
producer the refresh normally re-runs WARNs on age instead of failing.
An input with "kind": "goals" is what allows the page's Obligations tile; without one
the tile must not be rendered. The state file's expected shape is documented in
SKILL.md and assets/hub-state.template.json.

Exit 0 = no FAIL, safe to rebuild the page. Exit 1 = at least one FAIL. Every row names
its remedy; do not rebuild around a FAIL.

Everything product-specific comes from the hub: `brain.config.json` -> `dashboard`
(`out`, `state`, `inputs[]`), `graph.out`, `repos[]`, `hub.name`, and the hub's CLAUDE.md.

Each generic check exists because a real defect shipped without it:
  graph disclosed   a graph built from stalled feature branches was quoted as current
  graph freshness   a two-week-old graph was quoted as today's
  inputs fresh      a page claimed "0 of N tasks" for a task list deleted that morning
  documented cmds   a page printed a graph recipe the hub's CLAUDE.md had retired that day
  state embed       the embedded state JSON silently drifted from the committed file
  state evidence    evidence stored in the state file aged out within a day
  brand             a page restyled by hand drifted from the product's design system

PLUG-IN CHECKS
--------------
A `dashboard.inputs[]` entry may name a hub-local check: `"check": "<hub-relative .py>"`.
It is run as

    python <check.py> <hub-root> <page-path> <input-path>

(absolute paths; cwd = hub root; 120 s timeout) and must print one line per result:

    PASS|WARN|FAIL <name> — <detail> — <remedy>

(` - ` is accepted in place of ` — `; lines not starting with a level are ignored). It
must exit 0: a non-zero exit, or zero result lines, is a FAIL and its lines are
discarded. The path must be a hub-relative .py file that resolves inside the hub; an
absolute path or one escaping the hub is a FAIL and is never executed. Product rules — "dates must match the goals sheet", "the security
tile must match the audit" — live in those hub-local files, never in this script.
"""

import argparse
import datetime as dt
import html
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SKILLS = Path(__file__).resolve().parents[2]
CHECK_BRAND = SKILLS / "brand-system" / "scripts" / "check-brand.py"

GRAPH_MAX_HOURS = 12      # a graph older than this predates today's work (WARN)
INPUT_WARN_DAYS = 7       # default age at which an input not re-run by the refresh WARNs
# Producers the refresh itself re-runs (SKILL.md step 2). Their inputs must be from today.
RERUN_EACH_REFRESH = {"delivery-roadmap"}

TODAY = dt.date.today()
rows = []                 # (name, level, detail, remedy)


def add(name, level, detail, remedy=""):
    rows.append((name, level, detail, "" if level == "PASS" else remedy))


def check(name, ok, detail, remedy=""):
    add(name, "PASS" if ok else "FAIL", detail, remedy)
    return bool(ok)


def warn(name, ok, detail, remedy=""):
    """A known, accepted gap. Reported every run, never blocks the rebuild."""
    add(name, "PASS" if ok else "WARN", detail, remedy)
    return bool(ok)


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


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def git_date(hub, rel):
    """Last commit date of a hub file, or None when untracked/modified (mtime then wins)."""
    proc = subprocess.run(["git", "-C", str(hub), "status", "--porcelain", "--", rel],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0 or proc.stdout.strip():
        return None
    proc = subprocess.run(["git", "-C", str(hub), "log", "-1", "--format=%cs", "--", rel],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = proc.stdout.strip()
    return dt.date.fromisoformat(out) if proc.returncode == 0 and out else None


def input_stamp(hub, rel, full):
    """(date, source) for an input: its own `generated` stamp, else git, else mtime."""
    try:
        text = read(full)
    except OSError:
        return None, "unreadable"
    if full.suffix.lower() == ".json":
        try:
            gen = json.loads(text).get("generated")
            if gen:
                return dt.date.fromisoformat(str(gen)[:10]), "generated field"
        except Exception:
            pass
    m = re.search(r'<meta\s+name="generated"\s+content="(\d{4}-\d{2}-\d{2})', text)
    if m:
        return dt.date.fromisoformat(m.group(1)), "meta generated"
    d = git_date(hub, rel)
    if d:
        return d, "last commit"
    return dt.date.fromtimestamp(full.stat().st_mtime), "file mtime"


def producer_name(p):
    return p.split(":", 1)[-1] if p else p


# ── commands: page vs the hub's CLAUDE.md ─────────────────────────────────────
CMD = re.compile(
    r"(?:python3?\s+(?:-m\s+)?)?(?:[\w.\-]*/)*(pb|graphify)(?:\.py)?\s+([^\s;|&<>`#]+)([^;|&<>`#\n]*)")


def spans(text, markdown):
    out = [m.group(2) for m in re.finditer(r"<(code|pre)\b[^>]*>(.*?)</\1>", text, re.S | re.I)]
    out += re.findall(r"`([^`\n]+)`", text)
    if markdown:
        out += re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    return [html.unescape(re.sub(r"<[^>]+>", "", s)) for s in out]


def commands(text, markdown=False):
    found = []
    for s in spans(text, markdown):
        for line in s.splitlines():
            for m in CMD.finditer(line):
                tool, sub, rest = m.group(1), m.group(2), m.group(3)
                if sub.startswith("-") and tool == "pb":
                    continue
                flags = sorted({t.split("=", 1)[0] for t in rest.split() if t.startswith("-")})
                found.append((tool, sub, tuple(flags), m.group(0).strip()))
    return found


def plugin_path(hub, script):
    """(resolved path, None) for a plug-in confined to the hub, or (None, reason).
    Nothing outside the hub is ever executed: the path comes from config, and config
    is data, not a licence to run arbitrary files."""
    raw = str(script or "")
    if not raw:
        return None, "empty path"
    if Path(raw).is_absolute() or Path(raw).drive or raw.startswith(("/", "\\")):
        return None, "absolute path %r - plug-ins are hub-relative" % raw
    root = hub.resolve()
    full = (root / raw).resolve()
    if not full.is_relative_to(root):
        return None, "%r resolves outside the hub (%s)" % (raw, full)
    if full.suffix.lower() != ".py":
        return None, "%r is not a .py file" % raw
    if not full.is_file():
        return None, "plug-in %s not found" % raw
    return full, None


def run_plugin(hub, script, page_path, input_path, label):
    name = "check: %s" % label
    full, why = plugin_path(hub, script)
    if why:
        check(name, False, "not run: %s" % why,
              "point the input's \"check\" at a .py file inside the hub")
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(full), str(hub), str(page_path), str(input_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(hub), timeout=120,
        )
    except subprocess.TimeoutExpired:
        check(name, False, "plug-in %s timed out" % script, "make it finish in 120 s")
        return
    results = []
    for line in proc.stdout.splitlines():
        m = re.match(r"\s*(PASS|WARN|FAIL)\s+(.+?)\s*$", line)
        if not m:
            continue
        rest = m.group(2).rstrip(" —-")
        parts = [p.strip() for p in rest.split(" — " if " — " in rest else " - ", 2)]
        parts += [""] * (3 - len(parts))
        results.append((parts[0], m.group(1), parts[1] or "-", parts[2]))
    tail = (proc.stderr.strip().splitlines() or ["no stderr"])[-1]
    if proc.returncode != 0:
        # A plug-in that printed PASS and then crashed has not passed anything.
        check(name, False, "plug-in %s exited %d after %d result line(s): %s"
              % (script, proc.returncode, len(results), tail),
              "fix the plug-in; its results are discarded until it exits 0")
        return
    if not results:
        check(name, False, "plug-in %s printed no result lines (%s)" % (script, tail),
              "a plug-in prints 'PASS|WARN|FAIL name — detail — remedy' lines and exits 0")
        return
    for row in results:
        add(row[0], row[1], row[2], row[3])


STATE_EXPECTED = ('{"version": 2, "focus": {"items": [{"id", "status": "open"|"done", '
                  '"closedAt", "closedNote"}]}, "decisions": [{"id", ...}], "syncLog": [...]}')


def kind(v):
    return {dict: "an object", list: "a list", str: "a string", type(None): "null",
            bool: "a boolean", int: "a number", float: "a number"}.get(type(v), type(v).__name__)


def state_shape(state):
    """-> (items, decisions, problems, shape). Accepts the canonical shape and one simpler
    one - "focus" as a bare list of rows - because both carry exactly the same rows; the
    page's Save always writes the canonical shape back."""
    problems, items, shape = [], [], "canonical shape"
    if not isinstance(state, dict):
        return [], [], ["the file is %s" % kind(state)], shape
    focus = state.get("focus")
    if isinstance(focus, dict):
        items = focus.get("items")
        if not isinstance(items, list):
            problems.append("focus.items is %s" % ("missing" if "items" not in focus else kind(items)))
            items = []
    elif isinstance(focus, list):
        items, shape = focus, "simple shape (focus is a list)"
    else:
        problems.append("focus is %s" % ("missing" if "focus" not in state else kind(focus)))
    for n, it in enumerate(items):
        if not isinstance(it, dict):
            problems.append("focus row %d is %s" % (n, kind(it)))
        elif it.get("status") not in ("open", "done"):
            problems.append("focus row %s has status %r" % (it.get("id", n), it.get("status")))
    decisions = state.get("decisions", [])
    if not isinstance(decisions, list):
        problems.append("decisions is %s" % kind(decisions))
        decisions = []
    for n, d in enumerate(decisions):
        if not isinstance(d, dict) or not d.get("id"):
            problems.append("decision %d is %s" % (n, "missing an id" if isinstance(d, dict) else kind(d)))
        elif "options" in d and not isinstance(d["options"], list):
            problems.append("decision %s options is %s" % (d["id"], kind(d["options"])))
    if "syncLog" in state and not isinstance(state["syncLog"], list):
        problems.append("syncLog is %s" % kind(state["syncLog"]))
    items = [i for i in items if isinstance(i, dict)]
    return items, decisions, problems, shape


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hub", help="hub root (default: walk up from CWD to brain.config.json)")
    ap.add_argument("--first-build", action="store_true",
                    help="no page yet: a missing page is expected and page checks are skipped")
    ap.add_argument("--offline", action="store_true",
                    help="offline mode: producers were not re-run, so a stale re-run input WARNs "
                         "instead of failing (the page must disclose its age)")
    args = ap.parse_args()

    hub = find_hub(args.hub)
    cfg = load_config(hub)
    dash = need(cfg, "dashboard", '{"out": "docs/dashboard/product-hub.html", "state": '
                '"docs/dashboard/hub-state.json", "inputs": []}')
    page_rel = need(cfg, "dashboard.out", '"docs/dashboard/product-hub.html"')
    state_rel = need(cfg, "dashboard.state", '"docs/dashboard/hub-state.json"')
    inputs = need(cfg, "dashboard.inputs",
                  '[{"id": "roadmap", "path": "docs/roadmap/.roadmap-facts.json", '
                  '"produced_by": "delivery-roadmap"}]')
    repo_ids = [r.get("id") for r in need(cfg, "repos", '[{"id": "my-api"}]') if r.get("id")]
    graph_dir = hub / cfg.get("graph", {}).get("out", "graph/")
    page_path = hub / page_rel

    # ── 1. graph: exists, age, and what it was built from ─────────────────────
    graph_json = graph_dir / "graph.json"
    report = ""
    if not graph_json.is_file():
        # No graph: coverage, freshness and doc checks would describe nothing, so they are
        # skipped rather than passed. The page must say there is no graph.
        warn("graph", False, "no graph at %s - coverage checks skipped"
             % graph_json.relative_to(hub).as_posix(),
             "build it with the sync command the hub's CLAUDE.md documents, or say on the page "
             "that no graph backs it")
    else:
        add("graph", "PASS", graph_json.relative_to(hub).as_posix())
        try:
            report = read(graph_dir / "sync-report.md")
        except OSError:
            warn("graph sync-report", False, "sync-report.md missing next to the graph",
                 "re-sync with the command the hub's CLAUDE.md documents")

    graph_built, graph_stamp = {}, None      # repo id -> (branch, head, tree)
    if report:
        m = re.search(r"\*\*Last sync:\*\*\s*([0-9]{4}-[0-9]{2}-[0-9]{2})[ T]([0-9]{2}:[0-9]{2})", report)
        if m:
            graph_stamp = dt.datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M")
            age_h = (dt.datetime.now() - graph_stamp).total_seconds() / 3600.0
            warn("graph freshness", age_h <= GRAPH_MAX_HOURS,
                 "built %s (%.1f h ago)" % (graph_stamp.strftime("%Y-%m-%d %H:%M"), age_h),
                 "re-sync without pulling the clones - or disclose the age on the page")
        else:
            warn("graph freshness", False, "no Last sync stamp in sync-report.md",
                 "re-sync with the command the hub's CLAUDE.md documents")

        # | `repo-id` | `branch` | `abc1234` | clean |
        built = {}
        for pas, branch, head, tree in re.findall(
            r"\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|\s*(\w+)\s*\|", report
        ):
            built[pas] = (branch, head, tree)

        # The graph covers whatever was checked out. That is not gated - forcing a branch
        # switch once broke a live review-app test session. What IS gated is whether the
        # page tells the reader which branch they are looking at: see 'graph disclosed'.
        for rid in repo_ids:
            if rid not in built:
                warn("graph covers: %s" % rid, False, "no Built-from row",
                     "re-sync; the report must carry one row per configured repo")
                continue
            branch, head, tree = built[rid]
            graph_built[rid] = built[rid]
            warn("graph covers: %s" % rid, tree == "clean", "`%s` @ %s (%s)" % (branch, head, tree),
                 "worktree was dirty at sync time - the page must say the graph covers "
                 "uncommitted work")
        if "hub" in built:
            warn("graph covers: hub", built["hub"][2] == "clean", "`%s` @ %s (%s)" % built["hub"],
                 "commit the hub changes, then re-sync")

        code_only = "code-only" in report
        warn("graph doc coverage", not code_only,
             "code-only (no LLM key)" if code_only else "docs included",
             "set an LLM provider key and re-sync for a doc-aware graph; until then the page "
             "must say the hub's doc files are absent from the graph")

    # ── 2. every configured input exists and is fresh enough ──────────────────
    plugins = []
    for inp in inputs:
        iid, rel = inp.get("id", "?"), inp.get("path")
        if not rel:
            check("input: %s" % iid, False, "no path", 'give it "path": "<hub-relative file>"')
            continue
        full = hub / rel
        if inp.get("check"):
            plugins.append((inp["check"], full, iid))
        if not full.is_file():
            prod = inp.get("produced_by")
            check("input: %s" % iid, False, "%s missing" % rel,
                  "run the %s skill" % prod if prod else "restore the file or drop the input")
            continue
        stamp, source = input_stamp(hub, rel, full)
        age = (TODAY - stamp).days if stamp else None
        prod = inp.get("produced_by")
        if prod and producer_name(prod) in RERUN_EACH_REFRESH:
            limit = int(inp.get("max_age_days", 0))
            gate = warn if args.offline else check
            gate("input: %s" % iid, age is not None and age <= limit,
                 "%s %s (%s d old, %s; %s)" % (rel, stamp, age, source,
                                              "offline: %s not re-run" % prod if args.offline
                                              else "refresh re-runs %s" % prod),
                 "offline: disclose its age on the page" if args.offline else
                 "run the %s skill; never carry its figures forward by hand" % prod)
        else:
            limit = int(inp.get("max_age_days", INPUT_WARN_DAYS))
            warn("input: %s" % iid, age is not None and age <= limit,
                 "%s %s (%s d old, %s)" % (rel, stamp, age, source),
                 ("run the %s skill" % prod if prod else "hand-maintained - confirm it is "
                  "current") + ", or disclose its age on the page")

    # ── 3. the recorded layer ─────────────────────────────────────────────────
    state = None
    try:
        raw_state = read(hub / state_rel)
    except OSError as exc:
        raw_state = None
        check("state file", False, "%s unreadable: %s" % (state_rel, exc.strerror or exc),
              "start from assets/hub-state.template.json")
    if raw_state is not None:
        try:
            state = json.loads(raw_state)
        except json.JSONDecodeError as exc:
            check("state file", False, "%s: invalid JSON at line %d col %d: %s"
                  % (state_rel, exc.lineno, exc.colno, exc.msg),
                  "fix the JSON, or start from assets/hub-state.template.json")
    if state is not None:
        items, decisions, problems, shape = state_shape(state)
        if problems:
            check("state file", False, "wrong shape - expected %s; found %s"
                  % (STATE_EXPECTED, "; ".join(problems)),
                  "reshape %s to the documented schema (SKILL.md, assets/hub-state.template.json)"
                  % state_rel)
            state = None
        else:
            ids = [i.get("id") for i in items]
            check("state file", len(ids) == len(set(ids)) and all(ids),
                  "%s, v%s, %d focus items, %d decisions"
                  % (shape, state.get("version", state.get("schema", "?")), len(ids), len(decisions)),
                  "give every focus item a unique non-empty id")

            # The recorded layer must hold NO derived facts. A schema that put branch ages and
            # task counts in focus-item text aged out within a day while the procedure forbade
            # editing the file. Only {id,status,closedAt,closedNote}.
            allowed = {"id", "status", "closedAt", "closedNote"}
            stray = sorted({k for i in items for k in i} - allowed)
            check("state holds no evidence", not stray,
                  "focus rows carry only id/status/closure" if not stray
                  else "focus rows also carry: %s" % ", ".join(stray),
                  "move titles, bodies, chips and due labels to the page's FOCUS array, keyed "
                  "by the same id - they are derived and go stale daily")

            derived = re.compile(r"\b\d+\s*(ahead|behind)\b|\bstalled\s+\d+\s*d\b|"
                                 r"\b\d+\s*/\s*\d+\s*tasks\b|\bT[-−]\d+\b", re.I)
            tainted = [i["id"] for i in items if derived.search(str(i.get("closedNote", "")))]
            check("closure notes stay human", not tainted,
                  "no derived figures in closure notes" if not tainted
                  else "derived figures in: %s" % ", ".join(tainted),
                  "say why it closed, not what the counts were - counts are re-derived")

    page = ""
    try:
        page = read(page_path)
    except OSError:
        tracked = subprocess.run(["git", "-C", str(hub), "log", "-1", "--format=%h", "--", page_rel],
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace").stdout.strip()
        if args.first_build or not tracked:
            add("page", "PASS", "%s does not exist yet - first build%s; page checks skipped"
                % (page_rel, "" if args.first_build else " (never tracked in git)"))
        else:
            check("page", False, "%s missing, but git has tracked it (last %s)" % (page_rel, tracked),
                  "restore it (git checkout -- %s) or pass --first-build to start over from "
                  "assets/product-hub-template.html" % page_rel)

    if page and state is not None:
        m = re.search(r'<script id="hub-state" type="application/json">(.*?)</script>', page, re.S)
        if not m:
            check("state embed", False, 'no <script id="hub-state"> block in the page',
                  "embed the state file verbatim so the page renders committed state")
        else:
            try:
                emb = json.loads(m.group(1))
                check("state embed", emb == state,
                      "embed == committed file" if emb == state else "embed DIFFERS from the file",
                      "re-embed %s verbatim; the file is the source" % state_rel)
            except Exception as exc:
                check("state embed", False, "embedded JSON does not parse: %s" % exc,
                      "re-embed the state file verbatim")

    # ── 4. page structure the rebuild contract depends on ─────────────────────
    if page:
        # Obligations exist only when an input declares "kind": "goals". Then the at-risk
        # tile denominator must equal the ROWS entries plotted; without one the tile must
        # not be rendered at all (a 0/0 tile invents a commitment the hub never made).
        goals = [i.get("id", "?") for i in inputs if i.get("kind") == "goals"]
        plotted = len(re.findall(r'\{\s*id:\s*"[^"]+",\s*d:\s*"\d{4}-\d{2}-\d{2}"', page))
        tile = re.search(r'Obligations at risk</span>\s*<span class="v">(\d+)<small>\s*/\s*(\d+)</small>',
                         page)
        if not goals:
            check("obligation counts", not tile,
                  "no goals input, no obligations tile" if not tile else
                  "page renders an obligations tile but no input declares \"kind\": \"goals\"",
                  "drop the tile and frame the timeline on the inputs' own dates, or mark the "
                  "goals input with \"kind\": \"goals\"")
        elif tile:
            at_risk, total = int(tile.group(1)), int(tile.group(2))
            check("obligation counts", total == plotted and at_risk <= total,
                  "%d plotted, tile says %d/%d" % (plotted, at_risk, total),
                  "the at-risk tile denominator must equal the number of plotted obligations")
        else:
            check("obligation counts", False, "goals input %s but no at-risk tile" % ", ".join(goals),
                  "keep the tile markup greppable (see references/rebuild-contract.md)")

        y = TODAY - dt.timedelta(days=1)
        y_iso = y.isoformat()
        y_en = "%d %s" % (y.day, y.strftime("%B"))
        if 'data-date="%s"' % y_iso in page:
            y_ok, y_how = True, 'data-date="%s"' % y_iso
        elif y_iso in page:
            y_ok, y_how = True, "ISO date %s" % y_iso
        elif y_en in page:
            y_ok, y_how = True, "'%s' (English fallback)" % y_en
        else:
            y_ok, y_how = False, 'neither data-date="%s", %s nor \'%s\'' % (y_iso, y_iso, y_en)
        check("yesterday section", y_ok, "page names %s" % y_how if y_ok else "page has %s" % y_how,
              'mark the Yesterday heading data-date="%s" - it must cover the real previous '
              "day, not the last build's" % y_iso)

        t_today = re.search(r'var TODAY = new Date\((\d{4}), (\d+), (\d+)\)', page)
        t_zero = re.search(r'var T0 = new Date\((\d{4}), (\d+), (\d+)\)', page)
        if t_today and t_zero:
            pt = dt.date(int(t_today.group(1)), int(t_today.group(2)) + 1, int(t_today.group(3)))
            p0 = dt.date(int(t_zero.group(1)), int(t_zero.group(2)) + 1, int(t_zero.group(3)))
            check("timeline clock", pt == TODAY and (pt - p0).days == 2,
                  "TODAY=%s (want %s), scale starts %s (%d d before)" % (pt, TODAY, p0, (pt - p0).days),
                  "set TODAY to today and T0 to today minus 2 days (JS months are zero-indexed)")
        else:
            check("timeline clock", False, "could not find TODAY / T0 in the page",
                  "keep the var TODAY / var T0 declarations greppable")

        # Shared-state/db capabilities change who can open a published page; state belongs in git.
        uses_db = bool(re.search(r"""use\(\s*["']db["']\s*\)""", page))
        check("no db capability", not uses_db,
              "page does not call the db capability" if not uses_db else "page calls use(\"db\")",
              "drop db; the state file + a download capability is the state path")

        check("known gaps", "Known gaps" in page, "provenance footer has a Known gaps paragraph",
              "add a Known gaps paragraph; every WARN and accepted FAIL is disclosed there")

        tm = re.search(r"<title>([^<]*)</title>", page)
        title = tm.group(1).strip() if tm else ""
        want_title = dash.get("title")
        if want_title:
            check("page title", title == want_title, "title is '%s'" % title,
                  "keep <title>%s</title> (dashboard.title) so the artifact keeps its name" % want_title)
        else:
            name = cfg.get("hub", {}).get("name", "")
            ok = bool(title) and (not name or name in title) and not re.search(r"\d{4}-\d{2}|\d{1,2} \w+ \d{4}", title)
            check("page title", ok, "title is '%s'" % title,
                  "keep a stable, dateless <title> naming the product (or set dashboard.title) so "
                  "the artifact keeps its name")

        # THE disclosure gate. The graph may cover any branch; the page may not stay quiet
        # about which. This replaced forcing a branch switch, so it is a FAIL, not a WARN.
        # A substring test cannot fail ("main" is in "remaining"), so the page carries one
        # element per configured repo:
        #   <code data-graph-repo="<id>" data-graph-branch="<branch>"
        #         data-graph-built="YYYY-MM-DD">branch</code>
        # cross-checked against sync-report's Built-from table (and the element's own text).
        if graph_json.is_file():
            if not graph_built:
                check("graph disclosed", False, "could not run: sync-report has no Built-from row "
                      "for any configured repo", "re-sync so the report names what the graph covers")
            else:
                marks = {}
                for m in re.finditer(r'<(\w+)\b([^>]*\bdata-graph-repo="([^"]+)"[^>]*)>(.*?)</\1>', page, re.S):
                    attrs, rid, text = m.group(2), m.group(3), re.sub(r"<[^>]+>", "", m.group(4))
                    br = re.search(r'\bdata-graph-branch="([^"]*)"', attrs)
                    bt = re.search(r'\bdata-graph-built="(\d{4}-\d{2}-\d{2})', attrs)
                    marks.setdefault(rid, []).append((br.group(1) if br else None,
                                                      bt.group(1) if bt else None, text.strip()))
                want_day = graph_stamp.date().isoformat() if graph_stamp else None
                bad = []
                for rid, (branch, head, tree) in sorted(graph_built.items()):
                    got = marks.get(rid, [])
                    if not got:
                        bad.append("%s: no data-graph-repo element" % rid)
                        continue
                    if not any(b == branch and branch in t and (want_day is None or d == want_day)
                               for b, d, t in got):
                        b0, d0, t0 = got[0]
                        bad.append("%s: page says %s built %s (text '%s'), report says %s built %s"
                                   % (rid, b0, d0, t0, branch, want_day))
                check("graph disclosed", not bad,
                      "%d repo(s) disclosed with branch and build date, matching sync-report"
                      % len(graph_built) if not bad else "; ".join(bad),
                      'give each repo an element data-graph-repo="<id>" data-graph-branch='
                      '"<branch>" data-graph-built="YYYY-MM-DD" whose text names the branch')

            # fetch-and-report.py's snapshot: has a clone moved since the graph was built?
            try:
                snap = json.loads(read(graph_dir / ".branch-report.json"))
            except (OSError, ValueError):
                snap = None
            if snap is None:
                warn("checkout vs graph", False, "no .branch-report.json - not compared",
                     "run fetch-and-report.py before the gate")
            else:
                now = {r.get("repo"): r.get("branch") for r in snap.get("repos", []) if r.get("branch")}
                moved = ["%s: graph %s, clone now %s" % (rid, v[0], now[rid])
                         for rid, v in sorted(graph_built.items()) if rid in now and now[rid] != v[0]]
                warn("checkout vs graph", not moved,
                     "every clone is still on the branch the graph covers" if not moved
                     else "; ".join(moved),
                     "re-sync, or say on the page that the graph describes a branch the clone "
                     "has since left")

        # Documented commands only: every pb/graphify command the page prints in code must be
        # one the hub's CLAUDE.md documents today (same subcommand, no undocumented flags).
        try:
            claude_md = read(hub / "CLAUDE.md")
        except OSError:
            claude_md = ""
        if not claude_md:
            warn("documented commands", False, "hub has no CLAUDE.md to check commands against",
                 "document the hub's sync/query commands in CLAUDE.md")
        else:
            doc = commands(claude_md, markdown=True)
            known = {(t, s) for t, s, _, _ in doc}
            flags = {}
            for t, s, f, _ in doc:
                flags.setdefault((t, s), set()).update(f)
            bad = []
            for t, s, f, raw in commands(page):
                if (t, s) not in known:
                    bad.append(raw)
                elif set(f) - flags.get((t, s), set()):
                    bad.append(raw)
            bad = sorted(set(bad))
            check("documented commands", not bad,
                  "%d printed command(s), all in CLAUDE.md" % len(commands(page)) if not bad
                  else "not in CLAUDE.md: %s" % "; ".join(bad),
                  "print only commands the hub's CLAUDE.md documents today - it retires recipes")

        # Local links must resolve from the page's own directory.
        here = page_path.parent
        rel = sorted(set(re.findall(r'href="(\.\.?/[^"#]*)', page)))
        broken = [r for r in rel if not (here / r).resolve().exists()]
        check("local links", not broken,
              "%d relative links resolve" % len(rel) if not broken else "broken: %s" % ", ".join(broken),
              "fix the path, or drop the card - a dead link on the hub page is worse than none")

        # Design system: the page styles itself only through the inlined BRAND block.
        has_block = "/* BRAND:BEGIN */" in page and "/* BRAND:END */" in page
        check("brand block", has_block,
              "BRAND block inlined" if has_block else "no /* BRAND:BEGIN */ ... /* BRAND:END */ block",
              "run brand-system/scripts/brand.py inline on the page")
        if not CHECK_BRAND.is_file():
            check("brand", False, "check-brand.py not found at %s" % CHECK_BRAND,
                  "install the brand-system skill next to this one")
        else:
            proc = subprocess.run([sys.executable, str(CHECK_BRAND), str(page_path)],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", cwd=str(hub))
            lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
            tally = ["%s %s" % m.groups() for m in
                     (re.match(r"\s+([a-z][a-z-]+)\s+(\d+)\s*$", ln) for ln in lines)
                     if m and m.group(2) != "0"]
            ok = proc.returncode == 0
            detail = (lines[-1].strip() if lines else "no output") if ok else \
                "failing checks: " + (", ".join(tally) or "; ".join(ln.strip() for ln in lines[-3:]))
            check("brand", ok, detail,
                  "restyle with var(--ds-*) only, then brand.py inline; see check-brand.py output")

    # ── 5. hub-local plug-in checks (product rules live in the hub, not here) ─
    for script, input_path, iid in plugins:
        run_plugin(hub, script, page_path, input_path, iid)

    # ── report ────────────────────────────────────────────────────────────────
    width = max(len(r[0]) for r in rows)
    print("\nproduct-hub input gate  -  %s  -  %s\n" % (TODAY, hub))
    fails = warns = 0
    for name, level, detail, remedy in rows:
        print("  [%s] %-*s  %s" % (level, width, name, detail))
        if level != "PASS" and remedy:
            print("       %s-> %s" % (" " * width, remedy))
        fails += level == "FAIL"
        warns += level == "WARN"
    print("\n%d checks, %d failed, %d warned" % (len(rows), fails, warns))
    if fails:
        print("Do not rebuild the page around a FAIL. Fix the input, or - if you are "
              "deliberately shipping with it - say so on the page in Known gaps.")
    elif warns:
        print("Safe to rebuild. Each WARN is an accepted gap the page must still disclose.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
