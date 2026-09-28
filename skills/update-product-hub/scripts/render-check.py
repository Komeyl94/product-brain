#!/usr/bin/env python3
"""Render the dashboard headless and fail on page errors or horizontal overflow.

    python render-check.py [--hub <path>] [<page.html>]

Loads the page (default: brain.config.json -> dashboard.out) at 1280 and 390 px wide,
in light and dark (both the OS colour scheme and an explicit data-theme stamp), and
prints one line per case:

    PASS|WARN|FAIL render <width> <theme> — <detail> — <remedy>

FAIL on an uncaught page error, a console error, or scrollWidth > innerWidth; an
overflow FAIL names the outermost offending elements. Exit 1 on any FAIL.

Needs the Python `playwright` package. If it is not importable, or no browser can be
launched, the script prints a WARN saying the render was NOT checked and exits 0 -
it never reports a pass it did not measure. Browser resolution: $UX_EXECUTABLE_PATH or
$PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH (an installed Chromium/headless-shell binary),
else Playwright's own browser, else the installed Edge (channel "msedge").
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WIDTHS = (1280, 390)
THEMES = ("light", "dark")

OVERFLOW_JS = """() => {
  const d = document.documentElement, W = window.innerWidth;
  if (d.scrollWidth <= W) return {sw: d.scrollWidth, w: W, culprits: []};
  const clips = el => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const o = getComputedStyle(p).overflowX; if (o === 'hidden' || o === 'auto' || o === 'scroll' || o === 'clip') return true; }
    return false; };
  const wide = [...document.body.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > W + 1 && !clips(e));
  const outer = wide.filter(e => !wide.includes(e.parentElement));
  const name = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') +
    (e.classList.length ? '.' + [...e.classList].join('.') : '');
  return {sw: d.scrollWidth, w: W, culprits: outer.slice(0, 4).map(e =>
    name(e) + ' (right ' + Math.round(e.getBoundingClientRect().right) + 'px)')};
}"""


def find_hub(explicit):
    if explicit:
        return Path(explicit).resolve()
    here = Path.cwd().resolve()
    for d in [here] + list(here.parents):
        if (d / "brain.config.json").is_file():
            return d
    return None


def line(level, name, detail, remedy=""):
    print("%s %s — %s%s" % (level, name, detail, (" — " + remedy) if remedy else ""))


def launch(pw):
    exe = os.environ.get("UX_EXECUTABLE_PATH") or os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    tries = ([{"executable_path": exe}] if exe else []) + [{}, {"channel": "msedge"}]
    errors = []
    for kw in tries:
        try:
            return pw.chromium.launch(**kw), None
        except Exception as exc:
            errors.append("%s: %s" % (kw or "default", str(exc).splitlines()[0]))
    return None, "; ".join(errors)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--hub", help="hub root (default: walk up from CWD to brain.config.json)")
    ap.add_argument("page", nargs="?", help="HTML file (default: dashboard.out)")
    args = ap.parse_args()

    if args.page:
        page = Path(args.page).resolve()
    else:
        hub = find_hub(args.hub)
        if hub is None:
            print("error: no brain.config.json at or above %s - pass --hub or a page path" % Path.cwd())
            return 2
        try:
            with open(hub / "brain.config.json", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except json.JSONDecodeError as exc:
            print("brain.config.json: invalid JSON at line %d col %d: %s" % (exc.lineno, exc.colno, exc.msg))
            return 2
        out = cfg.get("dashboard", {}).get("out")
        if not out:
            print('error: brain.config.json is missing "dashboard.out" '
                  '(example: "docs/dashboard/product-hub.html")')
            return 2
        page = (hub / out).resolve()
    if not page.is_file():
        line("FAIL", "render", "%s does not exist" % page, "build the page first")
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        line("WARN", "render", "NOT checked: the Python playwright package is not installed",
             "pip install playwright, or render it by hand at 1280 and 390 in both themes")
        return 0

    fails = 0
    with sync_playwright() as pw:
        browser, why = launch(pw)
        if browser is None:
            line("WARN", "render", "NOT checked: no browser could be launched (%s)" % why,
                 "set UX_EXECUTABLE_PATH to an installed Chromium or headless-shell binary")
            return 0
        for width in WIDTHS:
            for theme in THEMES:
                ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=theme)
                pg = ctx.new_page()
                errs = []
                pg.on("pageerror", lambda e, errs=errs: errs.append("page error: %s" % e))
                pg.on("console", lambda m, errs=errs: errs.append("console: %s" % m.text)
                      if m.type == "error" else None)
                pg.goto(page.as_uri(), wait_until="load")
                pg.evaluate("t => document.documentElement.setAttribute('data-theme', t)", theme)
                pg.wait_for_timeout(250)
                ov = pg.evaluate(OVERFLOW_JS)
                ctx.close()
                name = "render %d %s" % (width, theme)
                if errs:
                    fails += 1
                    line("FAIL", name, "; ".join(errs[:3]), "fix the script error")
                elif ov["sw"] > ov["w"]:
                    fails += 1
                    line("FAIL", name, "horizontal overflow: scrollWidth %d > %d; outermost: %s"
                         % (ov["sw"], ov["w"], ", ".join(ov["culprits"]) or "not isolated"),
                         "let the element wrap (min-width:0, overflow-wrap:anywhere) or scroll inside itself")
                else:
                    line("PASS", name, "no page errors, no horizontal overflow")
        browser.close()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
