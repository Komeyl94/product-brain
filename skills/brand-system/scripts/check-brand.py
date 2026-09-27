#!/usr/bin/env python3
"""Fail any HTML artifact that styles itself outside the compiled brand.

Checks (each is reported by name, with a per-file tally):

  brand-block     the BRAND:BEGIN/END block is present exactly once and its content
                  hashes to tokens.json `brand_css_sha256` (else: missing / stale).
  colour-literal  a hex / rgb() / hsl() / oklch() / lab() / color() / named colour
                  outside the block - in <style>, style="", SVG paint attributes, or a
                  quoted string in <script>. Derive tints with
                  color-mix(in oklab, var(--ds-x) N%, var(--ds-y)) instead.
  font-family     a font-family (or `font` shorthand, or a custom property holding a
                  font stack) that is not var(--ds-font-*).
  font-weight     a weight no brand face embeds (the browser then synthesises it or
                  falls back to a system face, and a PDF shows it). When the brand embeds
                  no fonts, the weights DESIGN.md typography declares; skipped, with a
                  note, when it declares none.
  unknown-token   var(--ds-...) naming a custom property brand.css does not define.
  effect-literal  a gradient (linear-/radial-/conic-, repeating too) anywhere outside the
                  block, or a box-shadow / text-shadow / filter: drop-shadow() that is not
                  `none` or var(--ds-shadow-*). Effects are brand-owned: use
                  var(--ds-shadow-sm|md) and var(--ds-wash).

Comments are stripped before scanning, so a comment explaining a rule never trips it.

Escape hatch: --allow-literal VALUE (repeatable) accepts that exact colour literal.
Every allowed use is printed in the tally - an exception is never silent.

If you change this checker, run it on both fixtures:
    python check-brand.py ../fixtures/off-brand.html   # must FAIL every check
    python brand.py inline ../fixtures/on-brand.html --out <tmp>
    python check-brand.py <tmp>/on-brand.html          # must PASS

Usage
    python check-brand.py page.html [more.html ...] [--allow-literal '#123456'] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
sys.dont_write_bytecode = True
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _brandlib import (  # noqa: E402
    BEGIN, END, GENERIC_FAMILIES, HEX_RE, BrandError, design_config, find_hub, norm_colour,
    sha256_text, utf8_stdio,
)

CHECKS = ["brand-block", "colour-literal", "font-family", "font-weight", "unknown-token", "effect-literal"]
GRADIENT_RE = re.compile(r"\b(?:repeating-)?(?:linear|radial|conic)-gradient\(", re.I)
SHADOW_OK_RE = re.compile(r"none|var\(\s*--ds-shadow-[\w-]+\s*\)(\s*,\s*var\(\s*--ds-shadow-[\w-]+\s*\))*", re.I)

NAMED_COLOURS = set("""
aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet
brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue
darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange
darkorchid darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise
darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia
gainsboro ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo
ivory khaki lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue
lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon
mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue
mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen
paleturquoise palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red
rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue
slategray slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white
whitesmoke yellow yellowgreen
""".split())
COLOUR_FUNC_RE = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\([^()]*\)", re.I)
COLOUR_PROP_RE = re.compile(
    r"(color|background|border|outline|fill|stroke|shadow|caret|accent|text-decoration|column-rule|"
    r"stop|flood|lighting|scrollbar|^--)", re.I)
SVG_PAINT_ATTRS = ("fill", "stroke", "stop-color", "flood-color", "lighting-color", "color", "bgcolor")
KEYWORD_WEIGHTS = {"normal": 400, "bold": 700}
SAFE_FONT_VALUES = {"inherit", "initial", "unset", "revert", "revert-layer"}
DS_VAR_RE = re.compile(r"var\(\s*(--ds-[\w-]+)")
SCRIPT_COLOUR_KEY = (r"(?:colou?r|background(?:-color)?|fill|stroke|border(?:-[\w-]+)?|outline|"
                     r"shadow|stop-color|--[\w-]+)['\"]?\s*[:=]\s*[^;'\"]*?")


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def blank(text: str, start: int, end: int) -> str:
    """Replace a span with spaces, keeping newlines so offsets and line numbers hold."""
    return text[:start] + re.sub(r"[^\n]", " ", text[start:end]) + text[end:]


class Report:
    def __init__(self, path: str, text: str) -> None:
        self.path, self.text = path, text
        self.fails: dict[str, list[str]] = defaultdict(list)
        self.allowed: dict[str, int] = defaultdict(int)
        self.notes: list[str] = []

    def fail(self, check: str, offset: int, message: str) -> None:
        self.fails[check].append(f"line {line_of(self.text, offset)}: {message}")


def iter_declarations(css: str, base: int, inside: bool = False):
    """Yield (prop, value, absolute_offset) for every declaration at ANY nesting depth.

    A brace-matching scan, not a regex: text before a `{` is a selector (or at-rule prelude)
    and is skipped; text ended by `;` or `}` inside a block is a declaration. Quotes and
    parentheses are tracked so `url(data:...;base64,...)` or a `;` in a string does not split.
    Nested rules (`.card { color: red; .inner { ... } }`) are seen at every level.
    `inside=True` treats the whole text as one block (a style="" attribute).
    """
    depth = 1 if inside else 0
    start, paren, quote, i, n = 0, 0, None, 0, len(css)

    def emit(lo: int, hi: int):
        m = re.match(r"\s*([-\w]+)\s*:(.*)", css[lo:hi], re.S)
        if m:
            return m.group(1).lower(), m.group(2).strip(), base + lo + m.start(1)
        return None

    while i < n:
        ch = css[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif paren == 0:
            if ch == "{":
                depth += 1
                start = i + 1
            elif ch == ";":
                if depth > 0:
                    d = emit(start, i)
                    if d:
                        yield d
                start = i + 1
            elif ch == "}":
                if depth > 0:
                    d = emit(start, i)
                    if d:
                        yield d
                depth = max(0, depth - 1)
                start = i + 1
        i += 1
    if inside and start < n:
        d = emit(start, n)
        if d:
            yield d


class _Scan(HTMLParser):
    """Collect tags with attributes, and <style>/<script> text, with absolute offsets."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self.line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
        self.tags: list[tuple[str, list, int]] = []
        self.blocks: dict[str, list[list]] = {"style": [], "script": []}
        self._open: str | None = None

    def _off(self) -> int:
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs, self._off()))
        if tag in self.blocks:
            self._open = tag
            self.blocks[tag].append([None, ""])

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, attrs, self._off()))

    def handle_endtag(self, tag):
        if tag == self._open:
            self._open = None

    def handle_data(self, data):
        if self._open:
            block = self.blocks[self._open][-1]
            if block[0] is None:
                block[0] = self._off()
            block[1] += data


def literals_in(value: str, prop: str | None) -> list[str]:
    scrub = re.sub(r"url\([^)]*\)", "", value)
    scrub = re.sub(r"(['\"]).*?\1", "", scrub) if prop and prop != "content" else scrub
    found = [m.group(0) for m in HEX_RE.finditer(scrub)]
    found += [m.group(0) for m in COLOUR_FUNC_RE.finditer(scrub)]
    if prop is None or COLOUR_PROP_RE.search(prop):
        found += [w for w in re.findall(r"(?<![-\w])[a-zA-Z]+(?![-\w(])", scrub) if w.lower() in NAMED_COLOURS]
    return found


def check_literal(rep: Report, lit: str, offset: int, where: str, allow: set[str]) -> None:
    key = norm_colour(lit)
    if key in allow:
        rep.allowed[lit] += 1
        return
    rep.fail("colour-literal", offset, f"{lit} in {where}")


def check_font_family(rep: Report, prop: str, value: str, offset: int, where: str) -> None:
    v = value.replace("!important", "").strip()
    if prop == "font-family":
        if v.lower() in SAFE_FONT_VALUES or re.fullmatch(r"var\(\s*--ds-font-[\w-]+\s*\)", v):
            return
        rep.fail("font-family", offset, f"font-family: {v[:60]} in {where} (use var(--ds-font-*))")
    elif prop == "font":
        if v.lower() in SAFE_FONT_VALUES or "var(--ds-font-" in v.replace(" ", ""):
            return
        rep.fail("font-family", offset, f"font: {v[:60]} in {where} (shorthand must use var(--ds-font-*))")
    elif prop.startswith("--"):
        parts = [p.strip().strip("'\"").lower() for p in v.split(",")]
        if len(parts) > 1 and any(p in GENERIC_FAMILIES for p in parts):
            rep.fail("font-family", offset, f"{prop}: {v[:60]} holds a font stack (use var(--ds-font-*))")


def check_weight(rep: Report, prop: str, value: str, offset: int, where: str, weights: set[int] | None) -> None:
    if weights is None:
        return
    v = value.replace("!important", "").strip().lower()
    cands: list[str] = []
    if prop == "font-weight":
        cands = [v]
    elif prop == "font":
        cands = [t for t in v.split() if re.fullmatch(r"\d{3}|bold|bolder|lighter", t)]
    for c in cands:
        if c in SAFE_FONT_VALUES or c.startswith("var("):
            continue
        if c in ("bolder", "lighter"):
            rep.fail("font-weight", offset, f"relative weight `{c}` in {where} - name an embedded weight")
            continue
        n = KEYWORD_WEIGHTS.get(c) or (int(c) if c.isdigit() else None)
        if n is None:
            rep.fail("font-weight", offset, f"font-weight `{c}` in {where} is not a weight")
        elif n not in weights:
            rep.fail("font-weight", offset, f"font-weight {n} in {where} - allowed: {sorted(weights)} (use var(--ds-weight-*))")


def check_effect(rep: Report, prop: str, value: str, offset: int, where: str) -> None:
    v = value.replace("!important", "").strip()
    if GRADIENT_RE.search(v):
        rep.fail("effect-literal", offset, f"gradient in {where} (use var(--ds-wash))")
    elif prop in ("box-shadow", "text-shadow") and v.lower() not in SAFE_FONT_VALUES             and not SHADOW_OK_RE.fullmatch(v):
        rep.fail("effect-literal", offset, f"{prop}: {v[:50]} in {where} (use none or var(--ds-shadow-sm|md))")
    elif prop in ("filter", "-webkit-filter") and "drop-shadow(" in v.lower():
        rep.fail("effect-literal", offset, f"drop-shadow() in {where} (use var(--ds-shadow-sm|md))")


def check_file(path: Path, tokens: dict, allow: set[str]) -> Report:
    raw = path.read_text(encoding="utf-8", errors="replace")
    rep = Report(str(path), raw)
    text = raw

    # ---------------------------------------------------------------- brand block
    begins = [m.start() for m in re.finditer(re.escape(BEGIN), text)]
    ends = [m.start() for m in re.finditer(re.escape(END), text)]
    if not begins and not ends:
        rep.fail("brand-block", 0, "missing - no BRAND:BEGIN/END block (run brand.py inline)")
    elif len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        rep.fail("brand-block", (begins or ends)[0], f"malformed - {len(begins)} BEGIN / {len(ends)} END markers")
    else:
        content = text[begins[0] + len(BEGIN):ends[0]]
        if sha256_text(content) != tokens.get("brand_css_sha256"):
            rep.fail("brand-block", begins[0], "stale - content does not match the current brand.css "
                                               "(run brand.py build, then brand.py inline)")
        text = blank(text, begins[0], ends[0] + len(END))
        # The block is ~0.5 MB of ASCII. Browsers sniff the encoding from the first 1024
        # bytes, so without an early charset declaration every non-ASCII character after
        # the block (em dashes, Persian) renders as mojibake over file:// and in previews.
        charset = re.search(r"<meta[^>]+charset\s*=\s*[\"']?utf-8", raw, re.I)
        if charset is None or len(raw[:charset.start()].encode("utf-8")) > 1024:
            rep.fail("brand-block", 0, 'no <meta charset="utf-8"> in the first 1024 bytes - '
                                       "put it first in <head>, before the BRAND block")

    # ---------------------------------------------------------------- strip comments
    for m in list(re.finditer(r"<!--.*?-->", text, re.S)):
        text = blank(text, m.start(), m.end())

    known = set(tokens.get("css_vars", []))
    weights = None
    if tokens.get("fonts_embedded"):
        sets = [set(w) for w in tokens.get("embedded_weights", {}).values()]
        weights = set.intersection(*sets) if sets else set()
    elif tokens.get("declared_weights"):
        weights = set(tokens["declared_weights"])
        rep.notes.append(f"font-weight checked against DESIGN.md declared weights {sorted(weights)} "
                         "(no fonts embedded)")
    else:
        rep.notes.append("font-weight not checked: no fonts embedded and DESIGN.md declares no weights")

    scan = _Scan(text)
    scan.feed(text)
    scan.close()

    def scan_css(css: str, base: int, where_fmt: str, inside: bool) -> None:
        for prop, value, off in iter_declarations(css, base, inside):
            where = where_fmt.format(prop=prop)
            for lit in literals_in(value, prop):
                check_literal(rep, lit, off, where, allow)
            check_font_family(rep, prop, value, off, where)
            check_weight(rep, prop, value, off, where, weights)
            check_effect(rep, prop, value, off, where)
        for v in DS_VAR_RE.finditer(css):
            if v.group(1) not in known:
                rep.fail("unknown-token", base + v.start(), f"{v.group(1)} is not defined by brand.css")

    # ---------------------------------------------------------------- <style> blocks
    for base, css in scan.blocks["style"]:
        if base is None:
            continue
        css = re.sub(r"/\*.*?\*/", lambda c: re.sub(r"[^\n]", " ", c.group(0)), css, flags=re.S)
        scan_css(css, base, "<style> {prop}", inside=False)

    # ---------------------------------------------------------------- style="" and SVG attributes
    # Parsed by html.parser, so a `>` inside a quoted attribute cannot hide what follows it.
    for tag, attrs, off in scan.tags:
        for name, value in attrs:
            name, value = name.lower(), value or ""
            if name == "style":
                scan_css(value, off, f'<{tag} style="{{prop}}">', inside=True)
            elif name in SVG_PAINT_ATTRS:
                for lit in literals_in(value, None):
                    check_literal(rep, lit, off, f"<{tag} {name}>", allow)
            elif name == "font-family":
                check_font_family(rep, "font-family", value, off, f"<{tag} font-family>")
            elif name == "font-weight":
                check_weight(rep, "font-weight", value, off, f"<{tag} font-weight>", weights)

    # ---------------------------------------------------------------- <script> strings
    for base, js in scan.blocks["script"]:
        if base is None:
            continue
        js = re.sub(r"/\*.*?\*/", lambda c: re.sub(r"[^\n]", " ", c.group(0)), js, flags=re.S)
        js = re.sub(r"(?m)(^|[^:\\'\"])//[^\n]*", lambda c: c.group(1) + " " * (len(c.group(0)) - len(c.group(1))), js)
        for sm in re.finditer(r"(['\"`])((?:\\.|(?!\1).)*)\1", js, re.S):
            body = sm.group(2)
            # In script a literal is a colour only when it IS the string ('#AABBCC', "rgb(...)")
            # or follows a colour-ish property inside it ("border: 1px solid #ccc").
            # "PR #285" or "fixes #123" in a data string is prose, not a colour.
            lits = [h.group(0) for h in HEX_RE.finditer(body)] + [f.group(0) for f in COLOUR_FUNC_RE.finditer(body)]
            for lit in lits:
                if body.strip() == lit or re.search(SCRIPT_COLOUR_KEY + re.escape(lit), body, re.I):
                    check_literal(rep, lit, base + sm.start(), "<script> string", allow)
            for v in DS_VAR_RE.finditer(body):
                if v.group(1) not in known:
                    rep.fail("unknown-token", base + sm.start(), f"{v.group(1)} is not defined by brand.css")
    return rep


def main() -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(description="Fail HTML artifacts that stray from the compiled brand.")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--hub", help="hub root (default: walk up to brain.config.json)")
    ap.add_argument("--tokens", help="path to tokens.json (default: <design.build>/tokens.json)")
    ap.add_argument("--allow-literal", action="append", default=[], metavar="VALUE",
                    help="accept this exact colour literal (repeatable; always printed in the tally)")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every failure, not the first 8 per check")
    args = ap.parse_args()

    if args.tokens:
        tokens_path = Path(args.tokens)
    else:
        hub = find_hub(args.hub)
        tokens_path = hub / design_config(hub, quiet=True)["build"] / "tokens.json"
    if not tokens_path.is_file():
        raise BrandError(f"{tokens_path} does not exist - run brand.py build first")
    tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
    allow = {norm_colour(a) for a in args.allow_literal}

    failed_files = 0
    for name in args.files:
        path = Path(name)
        if not path.is_file():
            print(f"FAIL {name}: no such file")
            failed_files += 1
            continue
        rep = check_file(path, tokens, allow)
        total = sum(len(v) for v in rep.fails.values())
        print(f"{'FAIL' if total else 'PASS'} {name}")
        for check in CHECKS:
            items = rep.fails.get(check, [])
            print(f"  {check:<15} {len(items)}")
            for item in items if args.verbose else items[:8]:
                print(f"      {item}")
            if not args.verbose and len(items) > 8:
                print(f"      ... {len(items) - 8} more (--verbose)")
        for lit, count in sorted(rep.allowed.items()):
            print(f"  allowed-literal {lit} x{count}  (--allow-literal)")
        for note in rep.notes:
            print(f"  note: {note}")
        failed_files += bool(total)
    print(f"\n{len(args.files) - failed_files}/{len(args.files)} file(s) on-brand")
    return 1 if failed_files else 0


if __name__ == "__main__":
    sys.exit(main())
