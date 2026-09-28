"""Shared plumbing for the release-notes scripts: find the hub, read its config.

Every product fact these scripts use - which repos, which tag shape, which
locale the client note is written in, where the brand toolkit's output lives -
comes from the hub's brain.config.json. A missing key is a clear error naming
the key and an example value, never a silent default borrowed from some other
product.

The hub is the first directory, walking up from the current directory, that
contains brain.config.json. `--hub <path>` overrides it. Sibling skills are found
relative to this file, so the same folder works hub-local
(.claude/skills/<x>/scripts/) and inside a plugin (skills/<x>/scripts/).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SKILLS = Path(__file__).resolve().parents[2]
BRAND_SCRIPTS = SKILLS / "brand-system" / "scripts"

_MISSING = object()

# Example values quoted in "missing key" errors, so the fix is copy-pasteable.
EXAMPLES = {
    "hub.name": '"Acme"',
    "repos": '[{"id": "acme-api", "url": "..."}]',
    "releases.tag_regex": '"^v\\\\d+\\\\.\\\\d+\\\\.\\\\d+$"',
    "releases.primary_repo": '"acme-api"',
    "releases.production_branch": '"main"',
    "releases.out": '"docs/releases"',
    "releases.client_note.locale": '"en"',
    "releases.client_note.dir": '"ltr"',
    "releases.client_note.calendar": '"gregorian"',
    "releases.internal_note.locale": '"en"',
    "releases.tests": '{"acme-api": "npm test"}',
    "releases.capture.repo": '"acme-web"',
    "releases.capture.apps": '{"web": {"serve": "npm start -- --port 4200", "base_url": "http://localhost:4200"}}',
    "design.build": '"brand"',
}


def utf8_stdio() -> None:
    """Print any script without PYTHONIOENCODING, even on a cp1252 console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def find_hub(explicit: str | None = None, also_from: Path | None = None) -> Path:
    if explicit:
        hub = Path(explicit).resolve()
        if not (hub / "brain.config.json").is_file():
            raise SystemExit(f"--hub {explicit}: no brain.config.json there")
        return hub
    starts = [Path.cwd().resolve()]
    if also_from is not None:
        starts.append(Path(also_from).resolve())
    for start in starts:
        for folder in (start, *start.parents):
            if (folder / "brain.config.json").is_file():
                return folder
    raise SystemExit(
        "No Product Brain hub found: no brain.config.json in the current directory or any "
        "parent. Run from inside the hub, or pass --hub <path>."
    )


class Config:
    def __init__(self, hub: Path):
        self.hub = hub
        try:
            self.data = json.loads((hub / "brain.config.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            print(f"brain.config.json: invalid JSON at line {err.lineno} col {err.colno}: {err.msg}",
                  file=sys.stderr)
            raise SystemExit(2)

    def get(self, dotted: str, default=_MISSING):
        node = self.data
        for part in dotted.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
                continue
            if default is not _MISSING:
                return default
            example = EXAMPLES.get(dotted)
            hint = f" - e.g. `\"{dotted.rsplit('.', 1)[-1]}\": {example}`" if example else ""
            raise SystemExit(f"brain.config.json is missing `{dotted}`{hint}")
        return node

    def repo_ids(self) -> list:
        repos = self.get("repos")
        return [r["id"] for r in repos if isinstance(r, dict) and r.get("id")]

    def repo_path(self, repo_id: str) -> Path:
        """A repo's clone (contract addendum 3, rule 1): `repos[].path` if set,
        else `<workspace.repos_dir>/<id>`, else `repos/<id>` - all hub-relative."""
        for repo in self.get("repos"):
            if isinstance(repo, dict) and repo.get("id") == repo_id:
                if repo.get("path"):
                    return self.hub / repo["path"]
                base = self.get("workspace.repos_dir", None) or "repos"
                return self.hub / base / repo_id
        raise SystemExit(f"repo `{repo_id}` is named in brain.config.json but is not in its `repos` list")

    @property
    def product(self) -> str:
        # `pb` and brainify write a flat `hub_name`; hand-made hubs often use `hub.name`.
        flat = self.data.get("hub_name") if isinstance(self.data, dict) else None
        return self.get("hub.name", None) or flat or self.get("hub.name")

    @property
    def client_locale(self) -> str:
        return self.get("releases.client_note.locale")

    @property
    def client_dir(self) -> str:
        value = self.get("releases.client_note.dir")
        if value not in ("ltr", "rtl"):
            raise SystemExit(f"releases.client_note.dir is {value!r} - it must be \"ltr\" or \"rtl\"")
        return value

    def releases_dir(self) -> Path:
        return self.hub / self.get("releases.out")

    def brand_build(self) -> Path:
        return self.hub / self.get("design.build")


def python_playwright() -> bool:
    """True when the Python `playwright` package is importable.

    Preferred over a Node playwright-core: no driver file, no node_modules hunt.
    The browser still has to exist - UX_EXECUTABLE_PATH / UX_BROWSER_CHANNEL
    point it at one already on disk when the download is blocked.
    """
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def launch_options() -> dict:
    """Browser choice shared by every renderer: an explicit executable or channel."""
    opts = {}
    if os.environ.get("UX_EXECUTABLE_PATH"):
        opts["executable_path"] = os.environ["UX_EXECUTABLE_PATH"]
    if os.environ.get("UX_BROWSER_CHANNEL"):
        opts["channel"] = os.environ["UX_BROWSER_CHANNEL"]
    return opts


def node_modules_dir(cfg: Config) -> Path | None:
    """A node_modules directory carrying playwright-core, for the Node drivers.

    Checked in order: every entry of NODE_PATH, then the capture repo (its
    installed browser is the one the app's own tests use), then any other
    configured repo, then the hub itself. Drivers run from a temp directory with
    NODE_PATH pointed here, so nothing is ever written into a clone.
    """
    for entry in os.environ.get("NODE_PATH", "").split(os.pathsep):
        if entry and (Path(entry) / "playwright-core").is_dir():
            return Path(entry)
    home = playwright_home(cfg)
    return home / "node_modules" if home else None


def node_env(modules: Path) -> dict:
    env = dict(os.environ)
    env["NODE_PATH"] = os.pathsep.join(p for p in (str(modules), env.get("NODE_PATH", "")) if p)
    return env


def playwright_home(cfg: Config) -> Path | None:
    """A directory whose node_modules carries playwright-core (see node_modules_dir)."""
    candidates = []
    capture = cfg.get("releases.capture.repo", None)
    if capture:
        candidates.append(cfg.repo_path(capture))
    for repo_id in cfg.repo_ids():
        path = cfg.repo_path(repo_id)
        if path not in candidates:
            candidates.append(path)
    candidates.append(cfg.hub)
    for folder in candidates:
        if (folder / "node_modules" / "playwright-core").is_dir():
            return folder
    return None


def shown(path: Path, hub: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(hub))
    except ValueError:
        return str(path)


def version_label(cfg: Config, tag: str) -> str:
    """The version as artifacts display it (contract addendum 3, rule 2).

    `releases.version_regex` group 1 when set; else the named group
    `(?P<version>...)` of `releases.tag_regex` when it has one; else the whole
    tag. Never an unnamed group of tag_regex - that may be an alternation such
    as `^(v|release-)...`, whose group 1 is the prefix, not the version.
    """
    pattern = cfg.get("releases.version_regex", None)
    if pattern:
        match = re.search(pattern, tag)
        return match.group(1) if match and match.groups() and match.group(1) else tag
    pattern = cfg.get("releases.tag_regex", None)
    if pattern:
        match = re.search(pattern, tag)
        if match and "version" in match.groupdict() and match.group("version"):
            return match.group("version")
    return tag


def safe_ref(value: str, key: str) -> str:
    """A git ref taken from config or the command line (rule 4): never an option."""
    if not isinstance(value, str) or not value or value.startswith("-"):
        print(f"{key}: {value!r} is not a usable git ref (empty, or starts with '-')", file=sys.stderr)
        raise SystemExit(2)
    return value


def read_text_keep(path: Path) -> tuple:
    """(text, newline) - read without translating newlines (rule 6)."""
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    return text, ("\r\n" if "\r\n" in text else "\n")


def write_text_keep(path: Path, text: str, newline: str | None = None) -> None:
    """Write `text` with one newline style: `newline`, else the file's existing
    style, else the style `text` already carries. Never the platform default."""
    if newline is None:
        if Path(path).is_file():
            newline = read_text_keep(path)[1]
        else:
            newline = "\r\n" if "\r\n" in text else "\n"
    body = text.replace("\r\n", "\n")
    if newline == "\r\n":
        body = body.replace("\n", "\r\n")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
