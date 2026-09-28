#!/usr/bin/env python3
"""Validate a rendered delivery roadmap and print the authoritative tallies.

Every count reported to the user MUST come from this script's output, never from
prose or memory. Hand-tallied counts have been wrong in this workflow before: a
previous roadmap shipped a section heading reading "4 features - two of them this
cycle" beside a list whose real membership differed.

Usage, from anywhere inside the hub:
    python verify-roadmap.py <roadmap.html>
    python verify-roadmap.py --hub <path> <roadmap.html>
    python verify-roadmap.py --self-test          # parser and check edge cases

Besides the DATA checks it runs the brand-system skill's check-brand.py on the
same file: the page may style itself only through the inlined BRAND block, and a
brand failure fails the verification. A check that cannot run (no facts file, no
specs folder) is reported as a WARN, never as a pass.

Exits non-zero if any check fails.
"""

import argparse
import json
import os
import re
import subprocess
import sys
sys.dont_write_bytecode = True
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roadmap_hub import SKILLS, find_hub, load_config, get, utf8_stdio  # noqa: E402

CHECK_BRAND = SKILLS / "brand-system" / "scripts" / "check-brand.py"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

LANES = {"shipped", "inflight", "scheduled", "deferred", "backlog"}
VERDICTS = {"not-started", "branch-only", "in-develop", "released",
            "superseded", "reverted"}
BAR_KINDS = {"commit", "ready", "bet", "none"}
FRAMINGS = {"shape-up", "scrum", "kanban", "none"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
UNSHAPED_HILL = 0.45   # the page's isUnshaped(): hill < 0.45

# Hand-typed horizontal positions in markup: a style attribute (either quote)
# whose left/right/width is a literal percentage. max-width / min-width are layout,
# not positions, and are not flagged.
STYLE_ATTR = re.compile(r"""\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
POS_PCT = re.compile(r"(?<![\w-])(?:left|right|width)\s*:\s*[\d.]+\s*%", re.I)
HEADLINE_META = re.compile(
    r"""<meta\s+name=["']release-headline["']\s+content=(["'])(.*?)\1""", re.I | re.S)


def find_literal_end(src, brace):
    """Index just past the object literal that opens at src[brace] == '{'.

    Understands '...' and "..." strings, `...` template literals (with ${...}
    nesting), // line comments and /* block */ comments, so an apostrophe in a
    comment or a brace inside a string or template literal cannot truncate DATA.
    Returns None when the literal never closes."""
    n = len(src)
    ctx, depth = ["code"], [0]
    i = brace
    while i < n:
        ch = src[i]
        if ctx[-1] == "tpl":
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                ctx.pop()
                depth.pop()
            elif ch == "$" and src.startswith("${", i):
                ctx.append("code")
                depth.append(1)
                i += 2
                continue
            i += 1
            continue
        if ch in "\"'":
            j = i + 1
            while j < n and src[j] != ch and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            i = j + 1
            continue
        if ch == "`":
            ctx.append("tpl")
            depth.append(0)
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j == -1 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if ch == "{":
            depth[-1] += 1
        elif ch == "}":
            depth[-1] -= 1
            if depth[-1] == 0:
                if len(ctx) == 1:
                    return i + 1
                ctx.pop()          # end of a ${...} - back inside the template literal
                depth.pop()
        i += 1
    return None


def extract_data(html):
    """Pull the DATA object literal out of the page and parse it to a dict.

    Parsing strategy: find the literal with find_literal_end(), then evaluate it
    with Node, which is the only reliable way to read a JS object literal.
    Regex-munging JS into JSON corrupts any prose containing an apostrophe, which
    every real roadmap has ("the team's first release").
    """
    start = html.find("const DATA")
    if start == -1:
        raise SystemExit("FAIL: no `const DATA` found - is this a rendered roadmap?")
    brace = html.find("{", start)
    if brace == -1:
        raise SystemExit("FAIL: `const DATA` is not followed by an object literal")
    end = find_literal_end(html, brace)
    if end is None:
        raise SystemExit("FAIL: unbalanced braces in the DATA literal")
    raw = html[brace:end]

    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as fh:
            tmp = fh.name
            fh.write("const DATA = ")
            fh.write(raw)
            fh.write(";\nprocess.stdout.write(JSON.stringify(DATA));\n")
        proc = subprocess.run(["node", tmp], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
        # Node prints the offending source line, a caret, then the error, then a
        # version banner. Surface the error line itself, not the trailing banner.
        lines = [l.rstrip() for l in (proc.stderr or "").splitlines() if l.strip()]
        detail = next(
            (l.strip() for l in lines
             if re.search(r"(SyntaxError|ReferenceError|TypeError)", l)),
            lines[0].strip() if lines else "no output",
        )
        context = "\n".join(f"    {l}" for l in lines[:6])
        raise SystemExit(
            f"FAIL: could not evaluate the DATA literal - {detail}\n"
            "DATA must be a plain object literal: no function calls, "
            f"spreads or references to other variables inside it.\n"
            f"  node said:\n{context}"
        )
    except FileNotFoundError:
        # Node absent. Fall back to a conservative JSON coercion that does NOT
        # touch quote characters, so apostrophes in prose survive. Single-quoted
        # string values cannot be read this way; the message says so plainly.
        stripped = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
        stripped = re.sub(r"(?m)^\s*//[^\n]*$", "", stripped)
        stripped = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)",
                          r'\1"\2"\3', stripped)
        stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"FAIL: node is unavailable and DATA is not JSON-parseable ({exc}).\n"
                "Install Node, or write DATA with double-quoted strings only."
            )
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def hand_typed_positions(html):
    """Style attributes in markup (after </style>) carrying a literal left/right/
    width percentage."""
    body = html[html.find("</style>"):] if "</style>" in html else html
    hits = []
    for m in STYLE_ATTR.finditer(body):
        value = m.group(1) if m.group(1) is not None else m.group(2)
        hits.extend(POS_PCT.findall(value))
    return hits


def release_tags(r, errors):
    """[(repo, tag)] from release.tags, which is {repo: tag} or a list of tags."""
    tags = r.get("tags")
    if tags is None:
        return []
    if isinstance(tags, dict):
        return [(k, v) for k, v in tags.items() if v]
    if isinstance(tags, list):
        return [(None, t) for t in tags if t]
    errors.append(f"release {r.get('name')}: tags must be {{repo: tag}} or a list, got {tags!r}")
    return []


def run_brand_check(hub, path, allow=()):
    """Run check-brand.py on the page. Returns (ok, output)."""
    if not CHECK_BRAND.is_file():
        return False, (f"brand-system toolkit not found at {CHECK_BRAND}.\n"
                       "Install the brand-system skill next to this one; the page's "
                       "styling cannot be verified without it.")
    extra = [a for v in allow for a in ("--allow-literal", v)]
    proc = subprocess.run(
        [sys.executable, str(CHECK_BRAND), "--hub", str(hub), *extra, str(Path(path).resolve())],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(hub),
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).rstrip()
    return proc.returncode == 0, out


def spec_folders(hub, specs_dir):
    root = Path(hub) / specs_dir
    if not root.is_dir():
        return None
    return {p.name: p for p in root.iterdir() if p.is_dir()}


def release_notes_folder(hub, out_dir, r, pairs):
    """The release-notes folder for this release: <releases.out>/<tag or version> - <date>."""
    root = Path(hub) / out_dir
    if not root.is_dir():
        return None
    keys = {str(t) for _, t in pairs} | ({str(r["version"])} if r.get("version") else set())
    for d in sorted(root.iterdir()):
        if d.is_dir() and any(d.name == k or d.name.startswith(k + " ") for k in keys):
            return d
    return None


def validate(data, html, cfg, hub):
    """Every DATA check. Returns (errors, warnings)."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return [f"DATA must be an object, got {type(data).__name__}"], []

    as_of = data.get("asOf")
    if not isinstance(as_of, str) or not ISO.match(as_of):
        errors.append(f"asOf must be ISO yyyy-mm-dd, got {as_of!r}")

    features = data.get("features") or []
    releases = data.get("releases") or []
    conflicts = data.get("conflicts")
    if not isinstance(features, list) or not isinstance(releases, list):
        return errors + ["features and releases must be arrays"], warnings

    if not features:
        errors.append("features[] is empty")

    seen = set()
    for f in features:
        if not isinstance(f, dict):
            errors.append(f"feature entry is not an object: {f!r}")
            continue
        fid = f.get("id", "<no id>")
        if fid in seen:
            errors.append(f"duplicate feature id {fid!r}")
        seen.add(fid)

        if f.get("lane") not in LANES:
            errors.append(f"{fid}: lane {f.get('lane')!r} not in {sorted(LANES)}")
        if f.get("barKind") not in BAR_KINDS:
            errors.append(f"{fid}: barKind {f.get('barKind')!r} not in {sorted(BAR_KINDS)}")

        hill = f.get("hill")
        if isinstance(hill, bool) or not isinstance(hill, (int, float)) or not 0 <= hill <= 1:
            errors.append(f"{fid}: hill must be a number 0..1, got {hill!r}")

        git = f.get("git") or {}
        verdict = git.get("verdict")
        if verdict not in VERDICTS:
            errors.append(f"{fid}: git.verdict {verdict!r} not in {sorted(VERDICTS)}")
        if not git.get("evidence"):
            errors.append(f"{fid}: git.evidence is required - every claim must be re-verifiable")
        if not git.get("method"):
            errors.append(f"{fid}: git.method is required - say how shipped status was decided")

        # The core cross-check: lane and git verdict must not contradict each other.
        shipped_flag = bool(git.get("shipped"))
        if (verdict == "released") != shipped_flag:
            errors.append(f"{fid}: git.shipped={shipped_flag} contradicts verdict {verdict!r}")
        if f.get("lane") == "shipped" and verdict != "released":
            errors.append(f"{fid}: lane 'shipped' requires verdict 'released', got {verdict!r}")
        if verdict == "released" and not git.get("release"):
            errors.append(f"{fid}: verdict 'released' requires a git.release name")
        if verdict == "reverted" and f.get("lane") == "shipped":
            errors.append(f"{fid}: reverted work must not sit in lane 'shipped'")

        start, due = f.get("start"), f.get("due")
        for label, val in (("start", start), ("due", due)):
            if val is not None and not ISO.match(str(val)):
                errors.append(f"{fid}: {label} must be ISO or null, got {val!r}")
        if start and due and str(due) < str(start):
            errors.append(f"{fid}: due {due} precedes start {start}")
        if f.get("barKind") != "none" and not (start and due):
            errors.append(f"{fid}: barKind {f.get('barKind')!r} needs both start and due")

        tasks = f.get("tasks") or {}
        d, t = tasks.get("done"), tasks.get("total")
        if isinstance(d, int) and isinstance(t, int):
            if d > t:
                errors.append(f"{fid}: tasks.done {d} exceeds total {t}")
            # The phantom-completion pattern: fully ticked, nothing shipped.
            if t and d == t and verdict in {"not-started", "branch-only"}:
                warnings.append(
                    f"{fid}: tasks {d}/{t} fully ticked but verdict is {verdict!r} - "
                    "state this discrepancy on the card, do not let ticks imply progress")

    tag_pairs = {}
    for r in releases:
        if not isinstance(r, dict):
            errors.append(f"release entry is not an object: {r!r}")
            continue
        nm = r.get("name", "<no name>")
        tag_pairs[id(r)] = release_tags(r, errors)
        if not ISO.match(str(r.get("date") or "")):
            errors.append(f"release {nm}: date must be ISO, got {r.get('date')!r}")
        if not r.get("headline"):
            errors.append(f"release {nm}: headline is required (the concise release note)")
        if not r.get("repos"):
            errors.append(f"release {nm}: repos[] is required - name which repos shipped")
        if not (r.get("groups") or {}):
            warnings.append(f"release {nm}: no grouped commit lines - expandable tier is empty")
    releases = [r for r in releases if isinstance(r, dict)]

    # Framing is vocabulary only, but an unknown value silently falls back to 'none'.
    framing = data.get("framing")
    if framing is not None and framing not in FRAMINGS:
        errors.append(f"framing {framing!r} not in {sorted(FRAMINGS)}")
    cfg_framing = get(cfg, "roadmap.framing")
    if framing and cfg_framing and framing != cfg_framing:
        warnings.append(f"DATA.framing {framing!r} differs from roadmap.framing {cfg_framing!r}")

    # Branch names shown on the page come from DATA.branches (copied from facts).
    br = data.get("branches")
    cfg_br = {"production": get(cfg, "releases.production_branch"),
              "integration": get(cfg, "releases.integration_branch")}
    if br is None:
        warnings.append("DATA.branches is missing - copy {production, integration} from the facts "
                        "file so verdict labels name the configured branches")
    elif isinstance(br, dict):
        for k, v in cfg_br.items():
            if v and br.get(k) and br.get(k) != v:
                warnings.append(f"DATA.branches.{k} {br.get(k)!r} differs from "
                                f"releases.{k}_branch {v!r}")
    else:
        errors.append(f"branches must be {{production, integration}}, got {br!r}")

    # Movement is only known against an earlier-day run.
    sd = data.get("stallDetection")
    if sd is None:
        warnings.append("DATA.stallDetection is missing - copy it from the facts file so the "
                        "page can render branch movement as unknown when it is")
    elif not isinstance(sd, bool):
        errors.append(f"stallDetection must be true/false, got {sd!r}")

    facts_rel = get(cfg, "roadmap.facts")
    facts = None
    if not facts_rel:
        warnings.append("roadmap.facts is not configured - stall and tag-date cross-checks did not run")
    elif not (Path(hub) / facts_rel).is_file():
        warnings.append(f"{facts_rel} does not exist - stall and tag-date cross-checks did not run")
    else:
        try:
            facts = json.loads((Path(hub) / facts_rel).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"{facts_rel} unreadable ({exc}) - cross-checks did not run")
    if isinstance(facts, dict):
        if facts.get("stallDetection") is False and facts.get("generated") == as_of:
            claimed = [f.get("id") for f in features if isinstance(f, dict)
                       for b in ((f.get("git") or {}).get("branches") or [])
                       if b.get("stalled") is True]
            if sd is True or claimed:
                warnings.append(
                    "the facts file for this date has stall detection OFF, but DATA claims "
                    + ("stallDetection: true" if sd is True else f"stalled branches on {claimed}")
                    + " - movement is unknown this run")
        # Release dates are the tag's date, never parsed from the tag name.
        for r in releases:
            for _, tag in tag_pairs.get(id(r), []):
                dates = {(blob.get("tagDate") or {}).get(tag)
                         for blob in (facts.get("repos") or {}).values()
                         if isinstance(blob, dict)} - {None}
                if dates and str(r.get("date")) not in dates:
                    warnings.append(
                        f"release {r.get('name')}: date {r.get('date')} but tag {tag!r} is dated "
                        f"{', '.join(sorted(dates))} in the facts file - use the tag's date")

    # Release tags must be production tags by the hub's own definition.
    tag_src = get(cfg, "releases.tag_regex")
    if tag_src:
        try:
            tag_re = re.compile(tag_src)
        except re.error:
            tag_re = None
            errors.append(f"releases.tag_regex {tag_src!r} in brain.config.json does not compile")
        if tag_re:
            for r in releases:
                for repo, tag in tag_pairs.get(id(r), []):
                    if not tag_re.search(str(tag)):
                        warnings.append(
                            f"release {r.get('name')}: {repo or 'a'} tag {tag!r} does not match "
                            f"releases.tag_regex /{tag_src}/ - a non-matching tag is not a "
                            "production release")

    # Headline rule 1: the release-notes skill's headline wins.
    out_dir = get(cfg, "releases.out")
    if out_dir and (Path(hub) / out_dir).is_dir():
        for r in releases:
            folder = release_notes_folder(hub, out_dir, r, tag_pairs.get(id(r), []))
            if folder is None:
                continue
            client = folder / "client.html"
            if client.is_file():
                m = HEADLINE_META.search(client.read_text(encoding="utf-8", errors="replace"))
                if m and m.group(2).strip() and m.group(2).strip() != str(r.get("headline", "")).strip():
                    warnings.append(
                        f"release {r.get('name')}: headline differs from the release-notes headline in "
                        f"{out_dir}/{folder.name}/client.html - that one wins (rule 1)")
            if not r.get("notesUrl") and not r.get("notes"):
                warnings.append(f"release {r.get('name')}: {out_dir}/{folder.name}/ exists - set notes "
                                "(hub path) or, better, notesUrl (its published URL)")
    for r in releases:
        if r.get("notes") and not (Path(hub) / str(r["notes"])).exists():
            warnings.append(f"release {r.get('name')}: notes path {r['notes']!r} does not exist in the hub")

    # Unshaped: the page counts hill < 0.45. A dated feature whose spec folder
    # (id-prefixed) has no plan.md is unshaped against a hard date.
    specs_dir = get(cfg, "roadmap.specs_dir")
    folders = spec_folders(hub, specs_dir) if specs_dir else None
    if specs_dir and folders is None:
        warnings.append(f"roadmap.specs_dir {specs_dir}/ does not exist - the plan.md check did not run")
    if folders is not None:
        for f in features:
            if not isinstance(f, dict) or not f.get("due") or f.get("lane") in {"shipped", "deferred"}:
                continue
            fid = str(f.get("id", ""))
            match = [p for n, p in folders.items() if n == fid or n.startswith(fid + "-")]
            if match and not any((p / "plan.md").is_file() for p in match):
                hill = f.get("hill")
                claim = (f" and hill {hill} claims it is shaped - lower it below {UNSHAPED_HILL} or add the plan"
                         if isinstance(hill, (int, float)) and hill >= UNSHAPED_HILL else "")
                warnings.append(
                    f"{fid}: due {f['due']} but {specs_dir}/{match[0].name}/ has no plan.md - "
                    f"unshaped against a hard date; flag it in conflicts{claim}")

    # A required-but-empty conflicts section is fine; a missing key is not.
    if conflicts is None:
        errors.append(
            "conflicts key is missing. It is a REQUIRED slot: emit [] plus the "
            "page's 'no conflicts detected' note if this run genuinely found none.")
    elif not isinstance(conflicts, list):
        errors.append(f"conflicts must be an array, got {type(conflicts).__name__}")

    # Hand-typed positions are the bug this architecture exists to prevent.
    typed = hand_typed_positions(html)
    if typed:
        errors.append(
            f"{len(typed)} hand-typed left/right/width percentage(s) found in markup - "
            "all horizontal positions must be computed in JS from dates")
    return errors, warnings


def self_test():
    """Parser and check edge cases against fixtures/data-parser-cases.html."""
    fixture = FIXTURES / "data-parser-cases.html"
    html = fixture.read_text(encoding="utf-8")
    results = []

    def check(name, ok):
        results.append((name, bool(ok)))

    data = extract_data(html)
    check("apostrophe in a // comment does not truncate DATA", data.get("afterLineComment") == "still here")
    check("brace inside a /* */ comment is ignored", data.get("afterBlockComment") == "still here")
    check("brace inside a template literal is ignored", data.get("templated") == "a } b")
    check("${...} with a brace-bearing string inside a template literal", data.get("nested") == "x}y")
    check("escaped quote and brace inside a string", data.get("quoted") == "it's {not} a brace")
    check("last key survives (DATA read to its real end)", data.get("last") is True)

    cfg = {}
    hub = Path(tempfile.gettempdir())
    base = {"asOf": None, "features": [], "releases": [], "conflicts": []}
    errs, _ = validate(dict(base), "", cfg, hub)
    check("asOf null reports an error instead of raising", any("asOf" in e for e in errs))
    rel = {"name": "r1", "date": "2026-01-01", "headline": "h", "repos": ["a"], "groups": {"x": ["y"]},
           "tags": ["v1.0.0"]}
    errs, _ = validate(dict(base, asOf="2026-01-02", releases=[rel]), "",
                       {"releases": {"tag_regex": "^v\\d"}}, hub)
    check("release.tags as a list is accepted", not any("tags must be" in e for e in errs))
    errs, _ = validate(dict(base, asOf="2026-01-02", releases=[dict(rel, tags="v1")]), "", cfg, hub)
    check("release.tags as a string is an error, not a crash", any("tags must be" in e for e in errs))
    check("max-width / min-width percentages are not positions",
          not hand_typed_positions('</style><div style="max-width:60%;min-width:10%"></div>'))
    check("single-quoted style attribute is inspected",
          hand_typed_positions("</style><div style='left:12.5%'></div>") == ["left:12.5%"])
    check("double-quoted width percentage is flagged",
          hand_typed_positions('</style><i style="width: 40%"></i>') == ["width: 40%"])

    width = max(len(n) for n, _ in results)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name.ljust(width)}")
    failed = sum(1 for _, ok in results if not ok)
    print(f"\nself-test: {len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


def main():
    utf8_stdio()
    ap = argparse.ArgumentParser(description="Validate a rendered delivery roadmap.")
    ap.add_argument("--hub", help="hub root (default: nearest ancestor with brain.config.json)")
    ap.add_argument("--allow-literal", action="append", default=[], metavar="VALUE",
                    help="passed to check-brand.py: accept this exact literal (e.g. a "
                         "'#123' issue reference in prose); always printed in its tally")
    ap.add_argument("--self-test", action="store_true", help="run the parser/check self-test")
    ap.add_argument("path", nargs="?", help="the roadmap HTML file (page or template)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("path is required (or pass --self-test)")

    hub = find_hub(args.hub)
    cfg = load_config(hub)
    path = args.path
    with open(path, encoding="utf-8") as fh:
        html = fh.read()

    data = extract_data(html)
    errors, warnings = validate(data, html, cfg, hub)
    features = [f for f in (data.get("features") or []) if isinstance(f, dict)]
    releases = data.get("releases") or []
    conflicts = data.get("conflicts")

    print(f"=== roadmap verification | {path} ===")
    print(f"as of            : {data.get('asOf')}")
    print(f"features         : {len(features)}")
    by_lane = {}
    for f in features:
        by_lane[f.get("lane")] = by_lane.get(f.get("lane"), 0) + 1
    for lane in sorted(LANES):
        print(f"  lane {lane:<10}: {by_lane.get(lane, 0)}")
    by_verdict = {}
    for f in features:
        v = (f.get("git") or {}).get("verdict")
        by_verdict[v] = by_verdict.get(v, 0) + 1
    for v in sorted(VERDICTS):
        print(f"  verdict {v:<13}: {by_verdict.get(v, 0)}")
    unshaped = sum(1 for f in features
                   if isinstance(f.get("hill"), (int, float)) and f["hill"] < UNSHAPED_HILL)
    print(f"unshaped (hill<{UNSHAPED_HILL}): {unshaped}  (the page's Unshaped tile)")
    print(f"releases         : {len(releases)}")
    print(f"conflicts flagged: {len(conflicts) if isinstance(conflicts, list) else 'MISSING'}")
    unver = sum(len((f.get('git') or {}).get('unverifiable') or []) for f in features)
    print(f"git-unverifiable : {unver} item(s) across all features")

    if warnings:
        print(f"\n--- {len(warnings)} warning(s) ---")
        for w in warnings:
            print(f"  WARN {w}")

    brand_ok, brand_out = run_brand_check(hub, path, args.allow_literal)
    print(f"\n--- brand check (check-brand.py): {'OK' if brand_ok else 'FAIL'} ---")
    for line in brand_out.splitlines():
        print(f"  {line}")
    if not brand_ok:
        errors.append("check-brand.py failed - the page must style itself only through "
                      "the inlined BRAND block; run brand.py inline, then fix what it names")

    if errors:
        print(f"\n--- {len(errors)} error(s) ---")
        for e in errors:
            print(f"  FAIL {e}")
        print("\nVERIFICATION FAILED - do not publish.")
        return 1

    shipped = by_verdict.get("released", 0)
    print(f"\nOK. Report these numbers verbatim: {len(features)} features "
          f"({shipped} released), {len(releases)} production releases, "
          f"{len(conflicts)} conflict(s) flagged; brand check clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
