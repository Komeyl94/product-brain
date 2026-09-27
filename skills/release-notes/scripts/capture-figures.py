#!/usr/bin/env python3
"""Capture the client note's screenshots from the real running app, then inline them.

A release that changes a screen gets a picture of that screen. The picture is a
**screenshot of the app's own code**, not a drawing: the note must not show a
control that does not exist, or a label that no i18n file contains.

    folder/figures.json                the capture spec - one entry per figure, hand-authored
    folder/figures/<id>--<locale>.png  what came out, reviewable on its own
    folder/client.html                 <img> src rewritten to a data: URI in place

Why inline rather than reference the PNG on disk: the client note is published
as an Artifact, which is one self-contained HTML file behind a CSP that blocks
every external host. A relative `src` renders locally, survives the PDF, and
then silently shows a broken image to the client. So the file always carries the
bytes, and the verifier fails any `src` that is not a data: URI.

Config (brain.config.json):
    releases.capture.repo            the clone the app is served from (and whose
                                     node_modules/playwright-core drives the browser)
    releases.capture.apps.<app>      {"serve": "<command>", "base_url": "http://localhost:NNNN",
                                      "base_path": "/optional-base-href"}
    releases.client_note.locale/dir  the default capture locale, and the dir it must render in

Prerequisites
    the app served somewhere reachable - `releases.capture.apps.<app>.serve`
    (`--serve` runs it for you and shuts it down afterwards)

Usage
    python capture-figures.py "<releases.out>/<version> - <date>"
    ... --only <figure-id>             one figure, while iterating on its clip
    ... --base-url http://localhost:NNNN   an already-running server or a preview build
    ... --serve                        start and stop the app's serve command around the run
    ... --no-inline                    write the PNGs but leave client.html alone
    ... --inline-only                  no browser: re-fill client.html from figures/

`--inline-only` exists because re-authoring the copy is far more common than
re-taking the pictures, and the empty `src=""` slots in a freshly scaffolded
note would otherwise mean booting the whole app to fill them back in.

figures.json
    {
      "app": "web",                     a key of releases.capture.apps (required)
      "basePath": "/web",               the app's base href - routes 404 without it
                                        (default: the app's base_path, else none)
      "localeKey": "locale",            OPTIONAL localStorage key the app reads its
                                        language from at boot; set before any script runs
      "figures": [
        {
          "id": "notification-settings",     must match <img data-figure="...">
          "path": "/profile/settings",
          "locales": ["<client locale>"],    default: the client locale only
          "browserLocale": "fa-IR",          OPTIONAL navigator.language (default: the locale)
          "viewport": {"width": 900, "height": 1000},
          "waitFor": "[data-testid=channel-row-sms]",
          "clip": "section:has([data-testid=channel-row-sms])",
          "padding": 14,
          "seed": {"local": {"current_user": "{...}"}, "session": {}},
          "mocks": [{"url": "**/notification-preferences", "json": {...}}],
          "prepare": [{"click": "[data-testid=telegram-activate-button]"},
                      {"fill": ["input#identifier", "09120000000"]},
                      {"wait": 400}],
          "note": "why this state - carried into the internal note, not the client one"
        }
      ]
    }

`seed` is written into localStorage/sessionStorage before the app boots. For an
auth-gated screen it is whatever the app's route guard reads - typically a
serialised current-user record carrying an allowed role. A guard that only
checks that such a record parses and has the right role is satisfied by a
synthetic session, which is what makes a capture need no backend and no
account. Read the guard before writing the seed; a capture that bounced to the
sign-in page is reported by its landing path.

Everything about a figure is declarative on purpose. A screenshot nobody can
re-take is not evidence, and the next release needs the same picture with one
toggle flipped.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True  # a skill does not litter its own folder with __pycache__

import tempfile
import time
from pathlib import Path

from _hub import (Config, find_hub, node_env, node_modules_dir, read_text_keep, shown,
                  utf8_stdio, write_text_keep)

# A figure wider than this is downscaled. 1100 CSS px is wider than the note's
# own column, so the picture is still sharp on a 2x display, and the file stays
# small enough that a dozen of them fit in one self-contained page.
MAX_WIDTH = 1100
WARN_BYTES = 400_000

NODE_DRIVER = r"""
// Generated by capture-figures.py. Runs from a temp dir; NODE_PATH points at a
// node_modules carrying playwright-core.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const outDir = process.argv[3];

// Many apps read their language from storage at boot, so the locale must land
// via addInitScript - clicking an in-app switcher after load leaves half the
// screen mid-animation. `localeKey` names that storage key, when there is one.
const bootScript = ([locale, localeKey, seed]) => {
  try {
    if (localeKey) window.localStorage.setItem(localeKey, locale);
    if (seed && seed.local) {
      for (const [k, v] of Object.entries(seed.local)) window.localStorage.setItem(k, v);
    }
    if (seed && seed.session) {
      for (const [k, v] of Object.entries(seed.session)) window.sessionStorage.setItem(k, v);
    }
  } catch (e) {
    /* private mode - the capture will show the guard bounce, which is evidence too */
  }
};

(async () => {
  const launch = { args: ['--force-color-profile=srgb', '--font-render-hinting=none'] };
  if (process.env.UX_EXECUTABLE_PATH) launch.executablePath = process.env.UX_EXECUTABLE_PATH;
  if (process.env.UX_BROWSER_CHANNEL) launch.channel = process.env.UX_BROWSER_CHANNEL;
  const browser = await chromium.launch(launch);
  const results = [];

  for (const fig of spec.figures) {
    for (const locale of fig.locales) {
      const label = `${fig.id}--${locale}`;
      const context = await browser.newContext({
        viewport: fig.viewport,
        deviceScaleFactor: 2,
        locale: fig.browserLocale || locale,
        // Screenshots are the client-facing artefact: always the light theme,
        // whatever the machine taking them prefers.
        colorScheme: 'light',
        reducedMotion: 'reduce'
      });
      const page = await context.newPage();
      await page.addInitScript(bootScript, [locale, spec.localeKey || null, fig.seed || null]);

      for (const mock of fig.mocks || []) {
        await context.route(mock.url, route =>
          route.fulfill({
            status: mock.status || 200,
            contentType: 'application/json',
            body: JSON.stringify(mock.json)
          })
        );
      }

      const result = { id: fig.id, locale, errors: [] };
      page.on('pageerror', e => result.errors.push(String(e.message).slice(0, 200)));

      try {
        const url = spec.baseUrl + spec.basePath + fig.path;
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
        result.landedOn = new URL(page.url()).pathname;

        if (fig.waitFor) await page.waitForSelector(fig.waitFor, { timeout: 20000 });
        for (const step of fig.prepare || []) {
          if (step.click) await page.click(step.click, { timeout: 10000 });
          if (step.fill) await page.fill(step.fill[0], step.fill[1], { timeout: 10000 });
          if (step.press) await page.press(step.press[0], step.press[1]);
          if (step.waitFor) await page.waitForSelector(step.waitFor, { timeout: 20000 });
          if (step.wait) await page.waitForTimeout(step.wait);
        }

        // Scrollbars and carets are noise in a published picture, and a caret
        // makes two runs of the same figure differ by a few bytes forever.
        await page.addStyleTag({
          content:
            '*{caret-color:transparent!important}' +
            '::-webkit-scrollbar{display:none!important}' +
            'html{scrollbar-width:none!important}'
        });
        await page.evaluate(() => document.fonts && document.fonts.ready);
        await page.waitForTimeout(fig.settle || 500);

        const dir = await page.locator('html').getAttribute('dir');
        result.dir = dir;
        const expected = (spec.expectedDir || {})[locale];
        if (expected && (dir || 'ltr') !== expected) {
          result.errors.push(`html[dir]=${dir}, expected ${expected}`);
        }

        const file = path.join(outDir, `${label}.png`);
        if (fig.clip) {
          const box = await page.locator(fig.clip).first().boundingBox();
          if (!box) throw new Error(`clip selector matched nothing: ${fig.clip}`);
          const pad = fig.padding == null ? 12 : fig.padding;
          const vp = page.viewportSize();
          const clip = {
            x: Math.max(0, box.x - pad),
            y: Math.max(0, box.y - pad),
            width: Math.min(vp.width, box.width + pad * 2),
            height: box.height + pad * 2
          };
          await page.screenshot({ path: file, clip });
        } else {
          await page.screenshot({ path: file, fullPage: !!fig.fullPage });
        }
        result.file = file;
      } catch (e) {
        result.errors.push(String(e.message).split('\n')[0].slice(0, 300));
      }

      results.push(result);
      await context.close();
    }
  }

  await browser.close();
  fs.writeFileSync(path.join(outDir, '.capture-report.json'), JSON.stringify(results, null, 2));
})().catch(e => {
  console.error(e);
  process.exit(1);
});
"""


def optimise(png: Path) -> tuple[int, int, int]:
    """Downscale to MAX_WIDTH and re-encode. Returns (width, height, bytes)."""
    try:
        from PIL import Image
    except ImportError:
        size = png.stat().st_size
        print(f"  note: Pillow not installed, {png.name} left at capture size ({size:,} bytes)")
        return (0, 0, size)

    with Image.open(png) as img:
        img = img.convert("RGB")
        if img.width > MAX_WIDTH:
            height = round(img.height * MAX_WIDTH / img.width)
            img = img.resize((MAX_WIDTH, height), Image.LANCZOS)
        img.save(png, format="PNG", optimize=True)
        return (img.width, img.height, png.stat().st_size)


def inline(client: Path, figures: dict[tuple[str, str], Path]) -> tuple[int, list[str]]:
    """Rewrite each <img data-figure data-locale> src to the captured bytes.

    Matches on the two data attributes rather than the existing src so that
    re-running the capture is idempotent: the src may already be a 400KB data:
    URI from the last run, and a src-based match would have to parse it.
    """
    markup, newline = read_text_keep(client)
    missing, replaced = [], 0

    def swap(match: re.Match) -> str:
        nonlocal replaced
        tag = match.group(0)
        fid = re.search(r'data-figure="([^"]+)"', tag)
        loc = re.search(r'data-locale="([^"]+)"', tag)
        if not (fid and loc):
            return tag
        key = (fid.group(1), loc.group(1))
        png = figures.get(key)
        if not png or not png.is_file():
            missing.append(f"{key[0]}--{key[1]}")
            return tag
        uri = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode("ascii")
        replaced += 1
        if re.search(r'\ssrc="', tag):
            return re.sub(r'\ssrc="[^"]*"', f' src="{uri}"', tag, count=1)
        return tag[:-1].rstrip("/") + f' src="{uri}">'

    markup = re.sub(r"<img\b[^>]*>", swap, markup)
    write_text_keep(client, markup, newline)
    return replaced, missing


def answering(url: str) -> bool:
    """Does anything at all answer at url? One probe, no retries."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status < 500
    except urllib.error.HTTPError as err:
        return err.code < 500
    except Exception:
        return False


def wait_for_server(url: str, timeout: int, server: subprocess.Popen | None = None) -> bool:
    """Wait for url to answer - but stop the moment our own server has exited.

    Without the poll, a serve command that died (a port clash, a build error)
    leaves this loop waiting out its whole timeout, or - worse - accepting
    whatever else happens to answer on that port.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server is not None and server.poll() is not None:
            print(f"  the serve command exited with code {server.returncode} before the app "
                  "answered", file=sys.stderr)
            return False
        if answering(url):
            return True
        time.sleep(3)
    return False


def start_server(command: str, cwd: Path) -> subprocess.Popen:
    """Run the configured serve command THROUGH A SHELL, as its own process group.

    The command is a shell string from brain.config.json (releases.capture.apps
    .<app>.serve), so it runs with the shell's full power - treat that config as
    code. Its own process group/session is what lets stop_server() kill the
    whole tree: terminating the shell alone leaves the dev server holding the
    port, and the next run silently screenshots that stale server.
    """
    if os.name == "nt":
        return subprocess.Popen(command, cwd=cwd, shell=True, stdout=subprocess.DEVNULL,
                                stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(command, cwd=cwd, shell=True, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT, start_new_session=True)


def stop_server(server: subprocess.Popen) -> None:
    """Kill the serve command and everything it started."""
    if server.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(server.pid)],
                       capture_output=True, text=True)
    else:
        import signal
        try:
            os.killpg(os.getpgid(server.pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            server.wait(timeout=20)
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(server.pid), signal.SIGKILL)
            except ProcessLookupError:
                return
    try:
        server.wait(timeout=20)
    except subprocess.TimeoutExpired:
        print(f"  WARN: the serve command (pid {server.pid}) did not exit - stop it by hand",
              file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the client note's screenshots.")
    parser.add_argument("folder", help="the release folder (contains figures.json)")
    parser.add_argument("--base-url", help="an already-running server (default: localhost + the app's port)")
    parser.add_argument("--serve", action="store_true", help="run releases.capture.apps.<app>.serve for the run and stop it after")
    parser.add_argument("--only", action="append", default=[], help="capture only these figure ids")
    parser.add_argument("--no-inline", action="store_true", help="write the PNGs, leave client.html alone")
    parser.add_argument("--inline-only", action="store_true",
                        help="skip the browser entirely and re-inline the PNGs already in figures/")
    parser.add_argument("--hub", help="hub root (default: walk up from the current directory)")
    args = parser.parse_args()
    utf8_stdio()
    if args.inline_only and args.no_inline:
        raise SystemExit("--inline-only and --no-inline ask for opposite things")

    folder = Path(args.folder)
    if not folder.is_dir():
        raise SystemExit(f"no such release folder: {folder}")
    spec_path = folder / "figures.json"
    if not spec_path.is_file():
        raise SystemExit(
            f"{spec_path} is missing. A release with no screen change needs no figures - "
            "say so in the internal note instead of writing an empty spec."
        )
    cfg = Config(find_hub(args.hub, also_from=folder))
    locale, direction = cfg.client_locale, cfg.client_dir

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    app = spec.get("app")
    apps = cfg.get("releases.capture.apps", {}) if not args.inline_only else {}
    if not args.inline_only:
        if not app:
            raise SystemExit(f"{spec_path} names no \"app\" - use a key of releases.capture.apps "
                             f"({', '.join(apps) or 'none configured'})")
        if app not in apps:
            raise SystemExit(f"figures.json app {app!r} is not in releases.capture.apps "
                             f"({', '.join(apps) or 'none configured'})")
    app_cfg = apps.get(app, {})
    base_url = args.base_url or spec.get("baseUrl") or app_cfg.get("base_url")
    if not base_url and not args.inline_only:
        raise SystemExit(f"no base URL: set releases.capture.apps.{app}.base_url, "
                         "or pass --base-url")
    spec["baseUrl"] = (base_url or "").rstrip("/")
    base_path = spec.get("basePath", app_cfg.get("base_path", ""))
    spec["basePath"] = ("/" + base_path.strip("/")) if base_path.strip("/") else ""
    spec["expectedDir"] = {locale: direction}

    figures = spec.get("figures") or []
    if args.only:
        figures = [f for f in figures if f["id"] in args.only]
        if not figures:
            raise SystemExit(f"no figure matches --only {args.only}")
    for fig in figures:
        fig.setdefault("locales", [locale])
        fig.setdefault("viewport", {"width": 900, "height": 1000})
    spec["figures"] = figures

    if args.inline_only:
        out = folder / "figures"
        captured = {}
        for fig in figures:
            for locale in fig["locales"]:
                png = out / f"{fig['id']}--{locale}.png"
                if png.is_file():
                    captured[(fig["id"], locale)] = png
                else:
                    print(f"  missing {png.name} - capture it before it can be inlined")
        if not captured:
            raise SystemExit(f"nothing to inline: no PNGs in {out}")
        client = folder / "client.html"
        if not client.is_file():
            raise SystemExit(f"{client} does not exist yet")
        replaced, missing = inline(client, captured)
        print(f"inlined {replaced} <img> src(s) into {client.name} from {len(captured)} file(s)")
        for gap in missing:
            print(f"  WARN: client.html asks for figure '{gap}' and no capture matched it")
        if replaced == 0:
            print("  WARN: no <img data-figure=... data-locale=...> in client.html")
        return 0

    repo_id = cfg.get("releases.capture.repo")
    web = cfg.repo_path(repo_id)
    if not web.is_dir():
        raise SystemExit(f"{shown(web, cfg.hub)} is missing - the capture runs against the "
                         f"releases.capture.repo clone ({repo_id})")
    modules = node_modules_dir(cfg)
    if modules is None:
        raise SystemExit("no playwright-core found - put a node_modules carrying it on NODE_PATH, "
                         f"or install dependencies in {repo_id}")

    server = None
    serve = app_cfg.get("serve")
    probe = spec["baseUrl"] + spec["basePath"] + "/"
    if args.serve:
        if not serve:
            raise SystemExit(f"--serve needs releases.capture.apps.{app}.serve - the command "
                             "that serves the app")
        # Something already on the port would be what gets screenshotted - a
        # server left over from the last run, or another app entirely.
        if answering(probe):
            print(f"FAIL: something already answers at {probe} - refusing to --serve, because "
                  "the capture would screenshot that server rather than the one it starts. "
                  "Stop it, or drop --serve and pass --base-url to capture it deliberately.",
                  file=sys.stderr)
            return 2
        print(f"starting `{serve}` in {repo_id} through a shell (a first build can take minutes)")
        server = start_server(serve, web)

    try:
        if not wait_for_server(probe, 420 if args.serve else 20, server):
            raise SystemExit(
                f"nothing answering at {probe}.\n"
                f"Serve the app first:  cd {shown(web, cfg.hub)} && {serve or '<the serve command>'}\n"
                "or pass --serve to have this script do it, or --base-url to point elsewhere."
            )

        out = folder / "figures"
        out.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            driver = Path(tmp) / "capture-figures.driver.cjs"
            payload = Path(tmp) / "spec.json"
            # The driver runs from the temp dir with NODE_PATH pointed at the
            # node_modules that carries playwright-core, so `require` resolves
            # without writing anything into a clone.
            driver.write_text(NODE_DRIVER, encoding="utf-8")
            payload.write_text(json.dumps(spec), encoding="utf-8")
            print(f"capturing {sum(len(f['locales']) for f in figures)} figure(s) from {spec['baseUrl']}")
            proc = subprocess.run(
                ["node", str(driver), str(payload), str(out.resolve())],
                cwd=tmp, env=node_env(modules), capture_output=True, text=True, errors="replace",
            )

        report_path = out / ".capture-report.json"
        if proc.returncode != 0 or not report_path.is_file():
            print(proc.stdout[-2000:])
            print(proc.stderr[-2000:], file=sys.stderr)
            raise SystemExit("FAIL: the capture driver did not finish")

        report = json.loads(report_path.read_text(encoding="utf-8"))
        failed, captured = 0, {}
        for row in report:
            label = f"{row['id']}--{row['locale']}"
            if row.get("file"):
                png = Path(row["file"])
                width, height, size = optimise(png)
                captured[(row["id"], row["locale"])] = png
                dims = f"{width}x{height}" if width else "unchanged"
                print(f"  {label}: {dims}, {size:,} bytes  [{row.get('dir')}]")
                if size > WARN_BYTES:
                    print(f"    WARN: {size:,} bytes - tighten the clip or the viewport; "
                          "every figure travels inside the published page")
            else:
                failed += 1
                print(f"  {label}: FAILED")
            for err in row.get("errors", []):
                print(f"    ! {err}")
            if row.get("landedOn") and not row["landedOn"].endswith(
                    next((f["path"] for f in figures if f["id"] == row["id"]), "").rstrip("/") or "/"):
                print(f"    note: landed on {row['landedOn']} - a guard may have redirected; "
                      "check the picture is the screen you meant")

        if not args.no_inline and captured:
            client = folder / "client.html"
            if client.is_file():
                replaced, missing = inline(client, captured)
                print(f"\ninlined {replaced} <img> src(s) into {client.name}")
                for gap in missing:
                    print(f"  WARN: client.html asks for figure '{gap}' and no capture matched it")
                orphans = {f"{k[0]}--{k[1]}" for k in captured} - set()
                if replaced == 0:
                    print("  WARN: no <img data-figure=... data-locale=...> in client.html - "
                          "the pictures were captured and nothing shows them")
                    print(f"  available: {', '.join(sorted(orphans))}")
            else:
                print(f"\nno {client} yet - scaffold and author it, then re-run to inline")

        print("\nLook at every PNG before publishing. A screenshot of a screen in the wrong "
              "state, or in the wrong language, is worse than no screenshot.")
        return 1 if failed else 0
    finally:
        if server:
            stop_server(server)


if __name__ == "__main__":
    sys.exit(main())
