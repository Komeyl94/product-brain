"""Shared helpers for brand.py and check-brand.py.

Stdlib only. Everything product-specific is read from the hub: brain.config.json
(the `design` block) and the hub's DESIGN.md. Nothing here names a product.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
sys.dont_write_bytecode = True
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILLS = Path(__file__).resolve().parents[2]

BEGIN = "/* BRAND:BEGIN */"
END = "/* BRAND:END */"

# The roles every artifact may use. Colour roles exist in both schemes.
COLOUR_ROLES = [
    "canvas", "surface", "inset", "ink", "muted", "border",
    "primary", "primary-strong", "primary-soft", "on-primary",
    "accent", "success", "warning", "danger", "info",
]
# Optional text-safe variants of the semantic roles; default = the base role.
INK_ROLES = ["success-ink", "warning-ink", "danger-ink", "info-ink"]
# Effects: optional, per scheme or shared; defaults below. Values may only use {colors.x}
# refs (or literals already in `colors`) - never a new colour.
EFFECT_ROLES = {"shadow-sm": "none", "shadow-md": "none", "wash": "var(--ds-canvas)"}
FONT_ROLES_REQUIRED = ["font-body", "font-display", "font-mono"]
FONT_ROLES_OPTIONAL = ["font-latin"]
RADIUS_ROLES = ["radius-sm", "radius-md", "radius-lg"]

GENERIC_FAMILIES = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded", "emoji", "math",
    "fangsong", "-apple-system", "blinkmacsystemfont",
}


def utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


class BrandError(SystemExit):
    """Raised for any user-facing failure; prints the message and exits 1."""

    def __init__(self, message: str) -> None:
        super().__init__(f"brand-system: {message}")


class ConfigError(SystemExit):
    """A bad or unusable brain.config.json value: one line on stderr, exit 2."""

    def __init__(self, message: str) -> None:
        print(f"brand-system: {message}", file=sys.stderr)
        super().__init__(2)


# --------------------------------------------------------------------------- hub + config

def find_hub(explicit: str | None) -> Path:
    if explicit:
        hub = Path(explicit).resolve()
        if not (hub / "brain.config.json").is_file():
            raise BrandError(f"--hub {hub} has no brain.config.json")
        return hub
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "brain.config.json").is_file():
            return candidate
    raise BrandError(
        "no brain.config.json found walking up from the current directory. "
        "Run from inside a Product Brain hub or pass --hub <path>."
    )


def load_config(hub: Path) -> dict:
    path = hub / "brain.config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"brain.config.json: invalid JSON at line {exc.lineno} col {exc.colno}: {exc.msg}",
              file=sys.stderr)
        raise SystemExit(2)


def design_config(hub: Path, *, quiet: bool = False) -> dict:
    """The `design` block with neutral defaults for the two path keys.

    `system` defaults to DESIGN.md and `build` to brand/ - both are layout
    conventions, not product facts. `source` and `fonts` have no default: a hub
    without them has a hand-authored DESIGN.md and system font stacks.
    """
    cfg = load_config(hub)
    design = dict(cfg.get("design") or {})
    defaulted = []
    if "system" not in design:
        design["system"] = "DESIGN.md"
        defaulted.append('system: "DESIGN.md"')
    if "build" not in design:
        design["build"] = "brand"
        defaulted.append('build: "brand"')
    if defaulted and not quiet:
        print(f"note: brain.config.json design block lacks {', '.join(defaulted)} - using the default",
              file=sys.stderr)
    design["_repos"] = {r.get("id"): r for r in cfg.get("repos", []) if isinstance(r, dict)}
    design["_repos_dir"] = (cfg.get("workspace") or {}).get("repos_dir")
    return design


def need(design: dict, key: str, example: str) -> object:
    parts = key.split(".")
    node: object = design
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            raise BrandError(
                f"brain.config.json is missing `design.{key}`. Example:\n"
                f'  "design": {{ ... {example} ... }}'
            )
        node = node[part]
    return node


def repo_dir(hub: Path, design: dict, repo_id: str) -> Path:
    repo = design["_repos"].get(repo_id)
    if repo is None:
        raise BrandError(
            f"design.source.repo is {repo_id!r} but brain.config.json `repos` has no entry with that id"
        )
    # repos[].path, else <workspace.repos_dir>/<id>, else repos/<id> - all hub-relative.
    if repo.get("path"):
        path = hub / repo["path"]
    elif design.get("_repos_dir"):
        path = hub / design["_repos_dir"] / repo_id
    else:
        path = hub / "repos" / repo_id
    if not (path / ".git").exists():
        raise BrandError(f"repo {repo_id!r} is not cloned at {path}")
    return path


def check_ref(repo: Path, ref: str, key: str = "design.source.ref") -> str:
    """Validate a git ref taken from config and return the commit it names (exit 2 if not).

    A value starting with `-` would be parsed by git as an option (`--output=...`), so it is
    rejected before git sees it; every git call also passes --end-of-options.
    """
    ref = str(ref).strip()
    if not ref or ref.startswith("-") or any(c in ref for c in "\0\n\r"):
        raise ConfigError(f"brain.config.json `{key}` = {ref!r} is not a valid git ref")
    proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
                           "--end-of-options", f"{ref}^{{commit}}"], capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ConfigError(f"brain.config.json `{key}` = {ref!r} does not exist in {repo} "
                          f"(fetch first: git -C {repo} fetch)")
    return proc.stdout.strip()


def git_show(repo: Path, ref: str, path: str, *, binary: bool = False):
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", "--end-of-options", f"{ref}:{path}"],
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout if binary else proc.stdout.decode("utf-8", errors="replace")


def git_rev(repo: Path, ref: str) -> str | None:
    proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", "--end-of-options",
                           f"{ref}^{{commit}}"], capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def git_ls(repo: Path, ref: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", "--end-of-options", ref],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.stdout.splitlines() if proc.returncode == 0 else []


# --------------------------------------------------------------------------- frontmatter

def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_text, body). Empty frontmatter if the file has none."""
    text = text.lstrip("﻿")
    if not text.startswith("---"):
        return "", text
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return "".join(lines[1:i]), "".join(lines[i + 1:])
    raise BrandError("DESIGN.md frontmatter opens with --- but never closes")


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    if raw[0] == raw[-1] and raw[0] in "'\"" and len(raw) >= 2:
        inner = raw[1:-1]
        return inner.replace("''", "'") if raw[0] == "'" else inner.replace('\\"', '"')
    if raw in ("null", "~"):
        return None
    if raw in ("true", "false"):
        return raw == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d*\.\d+", raw):
        return float(raw)
    if raw.startswith("{") or raw.startswith("["):
        raise BrandError(f"flow-style YAML ({raw[:30]}...) is outside the subset this reader handles; "
                         "install PyYAML or write it in block style")
    return raw


def mini_yaml(text: str) -> dict:
    """Block-style YAML subset: nested maps, scalars, and lists of scalars."""
    root: dict = {}
    # (owner indent, container): children of a container are indented deeper than its owner key.
    stack: list[tuple[int, object]] = [(-1, root)]
    pending = None  # (container, key, key_indent) awaiting a nested block
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw_line)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        is_item = content.startswith("- ") or content == "-"
        if pending is not None:
            container, key, key_indent = pending
            pending = None
            if indent > key_indent or (is_item and indent == key_indent):
                new: object = [] if is_item else {}
                container[key] = new
                stack.append((key_indent if not is_item else key_indent - 1, new))
        while len(stack) > 1 and (
            indent <= stack[-1][0]
            or (not is_item and isinstance(stack[-1][1], list) and indent <= stack[-1][0] + 1)
        ):
            stack.pop()
        parent = stack[-1][1]
        if is_item:
            if not isinstance(parent, list):
                raise BrandError(f"frontmatter line {lineno}: list item where a map was expected")
            parent.append(_scalar(content[2:]))
            continue
        m = re.match(r"""^(['"]?)([^'":]+)\1\s*:(.*)$""", content)
        if not m or not isinstance(parent, dict):
            raise BrandError(f"frontmatter line {lineno}: cannot parse {raw_line.strip()!r}")
        key, rest = m.group(2).strip(), m.group(3).strip()
        if rest:
            parent[key] = _scalar(rest)
        else:
            parent[key] = None
            pending = (parent, key, indent)
    return root


def _stringify_keys(node):
    if isinstance(node, dict):
        return {str(k): _stringify_keys(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_stringify_keys(v) for v in node]
    return node


def parse_frontmatter(text: str) -> dict:
    fm, _ = split_frontmatter(text)
    if not fm.strip():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        return _stringify_keys(mini_yaml(fm))
    try:
        data = yaml.safe_load(fm) or {}
    except yaml.YAMLError as exc:
        raise BrandError(f"frontmatter is not valid YAML: {exc}")
    return _stringify_keys(data)


def frontmatter_sections(fm_text: str) -> dict[str, str]:
    """Top-level key -> its verbatim text (key line included)."""
    sections: dict[str, str] = {}
    current, buf = None, []
    for line in fm_text.splitlines(keepends=True):
        m = re.match(r"^([A-Za-z0-9_-]+)\s*:", line)
        if m and not line.startswith((" ", "\t")):
            if current:
                sections[current] = "".join(buf)
            current, buf = m.group(1), [line]
        elif current:
            buf.append(line)
    if current:
        sections[current] = "".join(buf)
    return sections


# --------------------------------------------------------------------------- colours + hashing

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\b")
FUNC_COLOUR_RE = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(", re.I)


def is_colour_literal(value: str) -> bool:
    v = value.strip()
    return bool(HEX_RE.fullmatch(v) or (FUNC_COLOUR_RE.match(v) and re.fullmatch(r"[\w-]+\([^()]*\)", v)))


def norm_colour(value: str) -> str:
    v = re.sub(r"\s+", "", str(value).strip().lower())
    m = re.fullmatch(r"#([0-9a-f]{3,4})", v)
    if m:
        v = "#" + "".join(c * 2 for c in m.group(1))
    return v


def norm_css(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(norm_css(text).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def family_names(stack: str) -> list[str]:
    """Named (non-generic) families in a font-family stack, in order."""
    names = []
    for part in str(stack).split(","):
        name = part.strip().strip("'\"").strip()
        if name and name.lower() not in GENERIC_FAMILIES:
            names.append(name)
    return names


# --------------------------------------------------------------------------- colour maths
# Just enough to measure WCAG contrast and OKLCH chroma/hue for hex, rgb() and oklch() values.

def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _delin(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def to_rgb(value: str):
    """sRGB 0..1 triple for a hex / rgb() / oklch() literal, else None."""
    v = str(value).strip().lower()
    m = re.fullmatch(r"#([0-9a-f]{3,8})", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h[:3])
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+).*\)", v)
    if m:
        return tuple(float(x) / 255 for x in m.groups())
    m = re.fullmatch(r"oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+).*\)", v)
    if m:
        import math
        L = float(m.group(1)) / (100 if m.group(2) else 1)
        C, H = float(m.group(3)), math.radians(float(m.group(4)))
        a, b = C * math.cos(H), C * math.sin(H)
        l_ = L + 0.3963377774 * a + 0.2158037573 * b
        m_ = L - 0.1055613458 * a - 0.0638541728 * b
        s_ = L - 0.0894841775 * a - 1.2914855480 * b
        l3, m3, s3 = l_ ** 3, m_ ** 3, s_ ** 3
        r = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
        g = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
        bb = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3
        return tuple(_delin(x) for x in (r, g, bb))
    return None


def luminance(rgb) -> float:
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def oklch_of(rgb):
    """(L, C, H degrees) of an sRGB triple."""
    import math
    r, g, b = (_lin(c) for c in rgb)
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(a, bb), (math.degrees(math.atan2(bb, a)) + 360) % 360
