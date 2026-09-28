#!/usr/bin/env python3
"""The brand toolkit: one design system, compiled once, inlined everywhere.

Subcommands
    extract   write a DRAFT product-level DESIGN.md from the configured frontend
              sources (read at `design.source.ref` with `git show`, never from the
              checkout), plus provenance, and print what is still undecided.
    build     DESIGN.md (+ fonts) -> <design.build>/brand.css and tokens.json.
    inline    refresh the BRAND:BEGIN/END block in one or more HTML files.
    show      print the resolved roles for both schemes.
    pdf-fonts list the fonts a PDF embeds and compare them with the brand's.

Why the fonts are embedded and converted, not linked - all learned from PDFs that
looked right on screen and shipped in the wrong typeface:
  * a headless browser does not fetch a linked web-font stylesheet when printing;
  * Chrome will not embed a CFF-flavoured (PostScript outline) web font in a PDF,
    so CFF faces are converted to TrueType outlines;
  * a subset silently drops any character the copy uses but the subset lacks, and
    the browser then substitutes a system face for the WHOLE run in the PDF. So
    Latin faces are subset to a generous range widened with `--text-from`, and
    faces that carry Arabic script are embedded whole unless `--subset-all`.

Everything product-specific comes from brain.config.json (`design`) and DESIGN.md.

Usage
    python brand.py extract [--force] [--source PATH ...] [--discover] [--out FILE]
    python brand.py build [--text-from FILE ...] [--subset-all] [--no-subset]
    python brand.py inline page.html [more.html ...] [--out DIR]
    python brand.py show
    python brand.py pdf-fonts file.pdf
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
sys.dont_write_bytecode = True
import zlib
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _brandlib import (  # noqa: E402
    BEGIN, COLOUR_ROLES, EFFECT_ROLES, END, FONT_ROLES_OPTIONAL, HEX_RE, INK_ROLES, FONT_ROLES_REQUIRED, RADIUS_ROLES,
    SKILL_DIR, BrandError, ConfigError, check_ref, design_config, family_names, find_hub, frontmatter_sections,
    git_ls, git_show, is_colour_literal, need, norm_colour, parse_frontmatter,
    repo_dir, sha256_file, sha256_text, split_frontmatter, utf8_stdio,
    contrast, luminance, oklch_of, to_rgb,
)

TEMPLATE = SKILL_DIR / "templates" / "DESIGN.template.md"

# Google Fonts' "latin" + "latin-ext" core: everything an English document uses,
# plus typographic punctuation, arrows and common symbols. Widen with --text-from.
LATIN_RANGES = (
    "U+0000-024F,U+0259,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0300-0301,U+0303-0304,"
    "U+0308-0309,U+0323,U+0329,U+1E00-1EFF,U+2000-206F,U+2070-209F,U+20A0-20CF,"
    "U+2100-214F,U+2150-218F,U+2190-21FF,U+2200-22FF,U+2460-24FF,U+25A0-25FF,"
    "U+2600-26FF,U+2713-2717,U+FEFF,U+FFFD"
)
ARABIC_PROBE = range(0x0600, 0x0700)


# =========================================================================== resolution

REF_RE = re.compile(r"\{([a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+)\}")


def lookup(fm: dict, dotted: str):
    node = fm
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def resolve(fm: dict, value, where: str, seen: tuple = ()) -> str:
    """Resolve every {group.key} in `value`, recursively. Typography refs yield fontFamily."""
    if isinstance(value, dict):
        if "fontFamily" in value:
            return resolve(fm, value["fontFamily"], where, seen)
        raise BrandError(f"{where}: reference points at a group, not a value")
    text = str(value)

    def sub(m: re.Match) -> str:
        ref = m.group(1)
        if ref in seen:
            raise BrandError(f"{where}: circular reference {' -> '.join(seen + (ref,))}")
        target = lookup(fm, ref)
        if target is None:
            raise BrandError(f"{where}: unresolved reference {{{ref}}} - no such token in DESIGN.md")
        return resolve(fm, target, where, seen + (ref,))

    return REF_RE.sub(sub, text)


def colour_values(fm: dict) -> set[str]:
    out = set()
    for key, raw in (fm.get("colors") or {}).items():
        try:
            out.add(norm_colour(resolve(fm, raw, f"colors.{key}")))
        except BrandError:
            out.add(norm_colour(str(raw)))
    return out


def _check_literals(fm: dict, raw: str, where: str, palette: set[str]) -> None:
    """A role value may carry colour literals only if they already exist in `colors`."""
    scrub = REF_RE.sub("", raw)
    funcs = re.finditer(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\([^()]*\)", scrub, re.I)
    for lit in [m.group(0) for m in HEX_RE.finditer(scrub)] + [m.group(0) for m in funcs]:
        if norm_colour(lit) not in palette:
            raise BrandError(
                f"{where} contains the literal {lit!r}, which is not a value in `colors`. "
                "Artifact roles may only point at existing tokens - add the colour to "
                "`colors` (with provenance) or reference an existing one "
                "(alpha: color-mix(in oklab, {colors.x} N%, transparent)).")


def resolve_roles(fm: dict) -> dict:
    """Validate the `artifact` block and return {'light', 'dark', 'common'} resolved maps.

    Every optional role is filled with its default, so brand.css always defines the full set.
    """
    art = fm.get("artifact")
    if not isinstance(art, dict):
        raise BrandError("DESIGN.md has no `artifact:` block. See references/design-md-format.md.")
    if not isinstance(fm.get("colors"), dict) or not fm["colors"]:
        raise BrandError("DESIGN.md has no `colors:` block")
    palette = colour_values(fm)
    out: dict = {"light": {}, "dark": {}, "common": {}}
    allowed = set(COLOUR_ROLES) | set(INK_ROLES) | set(EFFECT_ROLES)
    for scheme in ("light", "dark"):
        block = art.get(scheme)
        if not isinstance(block, dict):
            raise BrandError(f"artifact.{scheme} is missing")
        missing = [r for r in COLOUR_ROLES if r not in block]
        if missing:
            raise BrandError(f"artifact.{scheme} is missing roles: {', '.join(missing)}")
        extra = sorted(set(block) - allowed)
        if extra:
            raise BrandError(f"artifact.{scheme} has unknown roles: {', '.join(extra)} "
                             f"(allowed: {', '.join(sorted(allowed))})")
        for role in COLOUR_ROLES + INK_ROLES:
            if role not in block:  # optional *-ink: default to the base role
                out[scheme][role] = out[scheme][role[:-4]]
                continue
            raw = str(block[role])
            where = f"artifact.{scheme}.{role}"
            _check_literals(fm, raw, where, palette)
            value = resolve(fm, raw, where)
            if not is_colour_literal(value) and value.lower() != "transparent" \
                    and not value.lower().startswith("color-mix("):
                raise BrandError(f"{where} resolved to {value!r}, which is not a colour")
            out[scheme][role] = value
        for role, default in EFFECT_ROLES.items():
            # scheme value, else the shared value, else the default (never the other scheme's).
            raw = block.get(role, art.get(role))
            if raw is None:
                out[scheme][role] = default
                continue
            where = f"artifact.{scheme if role in block else ''}{'.' if role in block else ''}{role}"
            _check_literals(fm, str(raw), where, palette)
            out[scheme][role] = resolve(fm, raw, where)
    for role in FONT_ROLES_REQUIRED + RADIUS_ROLES:
        if role not in art:
            raise BrandError(f"artifact.{role} is missing")
    known_common = set(FONT_ROLES_REQUIRED + FONT_ROLES_OPTIONAL + RADIUS_ROLES) | set(EFFECT_ROLES) | {"light", "dark"}
    extra = sorted(set(art) - known_common)
    if extra:
        raise BrandError(f"artifact has unknown keys: {', '.join(extra)}")
    for role in FONT_ROLES_REQUIRED + FONT_ROLES_OPTIONAL + RADIUS_ROLES:
        if role in art:
            out["common"][role] = resolve(fm, art[role], f"artifact.{role}")
    out["common"].setdefault("font-latin", out["common"]["font-body"])
    return out


def load_design(hub: Path, design: dict) -> tuple[Path, str, dict]:
    path = hub / design["system"]
    if not path.is_file():
        raise BrandError(f"{path} does not exist. Run `brand.py extract` first, or author it "
                         f"from {TEMPLATE}.")
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    if not fm:
        raise BrandError(f"{path} has no YAML frontmatter")
    return path, text, fm


# =========================================================================== extract

def css_var_colours(text: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r"--([\w-]+)\s*:\s*([^;]+);", text):
        name, value = m.group(1), re.sub(r"\s+", " ", m.group(2).strip())
        if not is_colour_literal(value):
            continue
        name = re.sub(r"^(p-)?color-", "", name)
        out[name.lower()] = value
    return out


def ts_colours(text: str) -> dict[str, str]:
    out = {}
    for block in re.finditer(r"(?:export\s+)?const\s+(\w+)\s*=\s*\{(.*?)\};", text, re.S):
        group = block.group(1).lower().replace("_", "-")
        for m in re.finditer(r"""['"]?([\w-]+)['"]?\s*:\s*['"](#[0-9a-fA-F]{3,8})['"]""", block.group(2)):
            out[f"{group}-{m.group(1).lower()}"] = m.group(2)
    return out


STEP_RE = re.compile(r"^(.*?)[-_]?(\d{2,3})$")
SEMANTIC = {
    "success": (("success", "green", "emerald", "moss", "positive", "ok"), (125, 165)),
    "warning": (("warning", "warn", "amber", "yellow", "orange", "caution"), (55, 95)),
    "danger": (("danger", "error", "red", "brick", "crimson", "destructive", "negative"), (10, 40)),
    "info": (("info", "blue", "sky", "cyan", "notice"), (200, 265)),
}


class Tok:
    def __init__(self, name: str, value: str, rgb) -> None:
        self.name, self.value, self.rgb = name, value, rgb
        self.lum = luminance(rgb)
        self.L, self.C, self.H = oklch_of(rgb)
        m = STEP_RE.match(name)
        self.ramp, self.step = (m.group(1), int(m.group(2))) if m and m.group(1) else (None, None)


def _hue_dist(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


class RoleGuesser:
    """Guess artifact roles from a palette by ramp clustering, chroma and WCAG contrast.

    Most chromatic ramp -> primary; least chromatic ramp -> neutrals; text roles are the
    lightest (light scheme) / darkest (dark scheme) step that still clears 4.5:1. Every
    pick carries a note with its contrast; anything it cannot place is left as TODO.
    """

    def __init__(self, fm: dict, colors: dict) -> None:
        self.toks: list[Tok] = []
        for name, raw in colors.items():
            try:
                value = resolve(fm, raw, f"colors.{name}") if fm else str(raw)
            except BrandError:
                continue
            rgb = to_rgb(value)
            if rgb is not None and not re.search(r"(rgba|hsla)\(|/\s*0?\.\d|#[0-9a-f]{8}$|#[0-9a-f]{4}$", value.lower()):
                self.toks.append(Tok(str(name), value, rgb))
        self.by = {t.name.lower(): t for t in self.toks}
        ramps: dict[str, list[Tok]] = {}
        for t in self.toks:
            if t.ramp:
                ramps.setdefault(t.ramp, []).append(t)
        self.ramps = {k: sorted(v, key=lambda t: t.step) for k, v in ramps.items() if len(v) >= 3}

        def chroma(k: str) -> float:
            cs = sorted(t.C for t in self.ramps[k])
            return cs[len(cs) // 2]
        order = sorted(self.ramps, key=chroma)
        self.neutral = next((k for k in order if re.search(r"gr[ae]y|neutral|slate|stone|zinc|sand", k, re.I)),
                            order[0] if order else None)
        chromatic = [k for k in reversed(order) if k != self.neutral]
        self.primary = next((k for k in chromatic if re.search(r"primary|brand", k, re.I)),
                            chromatic[0] if chromatic else None)
        ph = self._ramp_hue(self.primary)
        self.accent = next((k for k in chromatic if k != self.primary and re.search(r"accent|secondary", k, re.I)), None)
        if self.accent is None and ph is not None:
            self.accent = next((k for k in chromatic if k != self.primary and not self._semantic_ramp(k)
                                and _hue_dist(self._ramp_hue(k), ph) >= 40), None)
        self.notes: dict[tuple, str] = {}
        self.problems: list[str] = []

    def _ramp_hue(self, k):
        if not k:
            return None
        mid = self.ramps[k][len(self.ramps[k]) // 2]
        return mid.H

    def _semantic_ramp(self, k: str) -> bool:
        return any(any(w in k.lower() for w in words) for words, _ in SEMANTIC.values())

    def named(self, *names: str):
        for n in names:
            if n in self.by:
                return self.by[n]
        return None

    def steps(self, k):
        return list(self.ramps.get(k, [])) if k else []

    def family(self, role: str) -> list[Tok]:
        words, (lo, hi) = SEMANTIC[role]
        for k in self.ramps:
            if any(w in k.lower() for w in words):
                return self.steps(k)
        singles = [t for t in self.toks if any(w in t.name.lower() for w in words)]
        if singles:
            return singles
        taken = {self.primary, self.neutral}
        return [t for t in self.toks if t.ramp not in taken and t.C > 0.06 and lo <= t.H <= hi]


def guess_roles(colors: dict, fm: dict | None = None) -> dict:
    g = RoleGuesser(fm or {}, colors)
    res: dict = {"light": {}, "dark": {}, "notes": {}, "unresolved": [], "problems": []}

    def put(scheme: str, role: str, tok, note: str = "", against=None, need: float = 0.0):
        if tok is None:
            res[scheme][role] = "{colors.TODO}"
            res["unresolved"].append(f"artifact.{scheme}.{role}: no candidate in the palette - pick a token")
            return
        res[scheme][role] = "{colors.%s}" % tok.name
        if against is not None:
            c = contrast(tok.rgb, against.rgb)
            note = (note + " " if note else "") + f"{c:.1f}:1 on {against.name}"
            if need and c < need:
                note += f" - FAILS {need}:1"
                res["problems"].append(f"artifact.{scheme}.{role} = {tok.name} is {c:.1f}:1 on {against.name} "
                                       f"(needs {need}:1) - no step in the palette passes")
        if note:
            res["notes"][(scheme, role)] = note

    def off(cands, *grounds):
        """Never pick a role equal to its own ground: it would be invisible."""
        gs = [g_.rgb for g_ in grounds if g_ is not None]
        return [t for t in cands if all(contrast(t.rgb, x) > 1.04 for x in gs)]

    def lightest_passing(cands, bg, need=4.5):
        ok = [t for t in off(cands, bg) if contrast(t.rgb, bg.rgb) >= need]
        return min(ok, key=lambda t: contrast(t.rgb, bg.rgb)) if ok else None

    def best(cands, bg):
        cands = off(cands, bg)
        return max(cands, key=lambda t: contrast(t.rgb, bg.rgb)) if cands else None

    def muted_for(scheme, cands, bg, ink):
        """Muted must pass 4.5:1 yet read visibly weaker than ink: aim for ~6:1."""
        ok = [t for t in off(cands, bg) if t is not ink and contrast(t.rgb, bg.rgb) >= 4.5]
        if not ok:
            return None
        pick = min(ok, key=lambda t: abs(contrast(t.rgb, bg.rgb) - 6.0))
        c, ci = contrast(pick.rgb, bg.rgb), contrast(ink.rgb, bg.rgb) if ink else 21
        if c > 8.0 and c > 0.7 * ci:
            res["problems"].append(f"artifact.{scheme}.muted = {pick.name} is {c:.1f}:1 - the ramp has no step "
                                   f"between 4.5:1 and ~8:1 on {bg.name}, so muted barely differs from ink "
                                   f"({ci:.1f}:1); add a mid step or accept it")
        return pick

    def soft_for(cands, bg):
        """A tinted ground (bar tracks, chips): distinct from the surface, far from text contrast."""
        ok = [t for t in off(cands, bg) if contrast(t.rgb, bg.rgb) < 3.0]
        if not ok:
            return None
        return min(ok, key=lambda t: abs(contrast(t.rgb, bg.rgb) - 1.25))

    neutral, primary = g.steps(g.neutral), g.steps(g.primary)
    pale = sorted([t for t in g.toks if t.C < 0.03], key=lambda t: -t.lum)
    # ------------------------------------------------------------ light
    surface = g.named("surface-card", "surface", "card", "paper", "white") or (pale[0] if pale else None)
    canvas = g.named("surface-canvas", "canvas", "background", "bg", "surface-ground") or \
        next((t for t in sorted(neutral, key=lambda t: -t.lum) if t is not surface), surface)
    inset = g.named("surface-inset", "inset", "surface-muted") or \
        next((t for t in sorted(off(neutral, surface), key=lambda t: -t.lum) if t is not canvas), canvas)
    put("light", "surface", surface)
    put("light", "canvas", canvas)
    put("light", "inset", inset)
    if surface:
        hair = [t for t in neutral if 1.1 < contrast(t.rgb, surface.rgb) < 2.0]
        border = g.named("border", "outline", "divider") or \
            (min(hair, key=lambda t: abs(contrast(t.rgb, surface.rgb) - 1.25)) if hair else None)
        put("light", "border", border)
        ink = g.named("text", "ink", "foreground") or best(neutral, canvas or surface)
        put("light", "ink", ink, against=canvas or surface, need=4.5)
        muted = g.named("text-muted", "muted") or muted_for("light", neutral, canvas or surface, ink) or ink
        put("light", "muted", muted, against=canvas or surface, need=4.5)
        p = lightest_passing(primary, surface) or best(primary, surface) or g.named("primary")
        put("light", "primary", p, against=surface, need=4.5)
        strong = [t for t in primary if contrast(t.rgb, surface.rgb) >= 7]
        ps = min(strong, key=lambda t: abs((t.step or 900) - 900)) if strong else best(primary, surface)
        put("light", "primary-strong", ps, against=surface, need=4.5)
        put("light", "primary-soft", soft_for(primary, surface), against=surface)
        if p:
            onp = next((t for t in (surface, g.named("white"), ink) if t and contrast(t.rgb, p.rgb) >= 4.5), None)
            put("light", "on-primary", onp or surface, against=p, need=4.5)
        else:
            put("light", "on-primary", None)
        acc = g.steps(g.accent)
        a = lightest_passing(acc, surface) or best(acc, surface) or g.named("accent")
        if a is None and len(neutral) >= 2:
            a = sorted(neutral, key=lambda t: t.lum)[1]
            res["problems"].append("artifact.light.accent: the palette has no second hue - accent guessed as a "
                                   f"dark neutral ({a.name}); confirm or pick a hue")
        put("light", "accent", a, against=surface)
        for role in SEMANTIC:
            fam = g.family(role)
            base = min(fam, key=lambda t: abs((t.step or 600) - 600)) if fam else None
            put("light", role, base, against=surface)
            if base is not None and contrast(base.rgb, surface.rgb) < 4.5:
                ink_tok = lightest_passing(fam, surface)
                if ink_tok:
                    put("light", f"{role}-ink", ink_tok, against=surface, need=4.5)
                else:
                    res["problems"].append(f"artifact.light.{role}: {base.name} is "
                                           f"{contrast(base.rgb, surface.rgb):.1f}:1 on {surface.name} and no step "
                                           f"passes 4.5:1 - use it for fills/marks with ink text, never small text")
    # ------------------------------------------------------------ dark
    darks = sorted(neutral + primary, key=lambda t: t.lum)
    dcanvas = min(neutral, key=lambda t: t.lum) if neutral else (darks[0] if darks else None)
    put("dark", "canvas", dcanvas)
    if dcanvas:
        lifts = [t for t in darks if t is not dcanvas and 1.03 < contrast(t.rgb, dcanvas.rgb) < 1.8]
        dsurface = min(lifts, key=lambda t: contrast(t.rgb, dcanvas.rgb)) if lifts else dcanvas
        put("dark", "surface", dsurface, against=dcanvas)
        dinset = next((t for t in off(lifts, dsurface)), dcanvas)
        put("dark", "inset", dinset)
        hair = [t for t in darks if 1.3 < contrast(t.rgb, dsurface.rgb) < 3.0 and t.lum > dsurface.lum]
        put("dark", "border", min(hair, key=lambda t: abs(contrast(t.rgb, dsurface.rgb) - 1.7)) if hair else None)
        dink = best(neutral, dsurface) or g.named("white")
        put("dark", "ink", dink, against=dsurface, need=4.5)
        put("dark", "muted", muted_for("dark", neutral, dsurface, dink) or dink, against=dsurface, need=4.5)
        dp = lightest_passing(primary, dsurface) or best(primary, dsurface)
        put("dark", "primary", dp, against=dsurface, need=4.5)
        strong = [t for t in primary if contrast(t.rgb, dsurface.rgb) >= 7]
        put("dark", "primary-strong", min(strong, key=lambda t: abs((t.step or 200) - 200)) if strong else dp,
            against=dsurface, need=4.5)
        put("dark", "primary-soft", soft_for(primary, dsurface), against=dsurface)
        if dp:
            onp = next((t for t in (dcanvas, g.named("white"), dink) if t and contrast(t.rgb, dp.rgb) >= 4.5), None)
            put("dark", "on-primary", onp or dcanvas, against=dp, need=4.5)
        else:
            put("dark", "on-primary", None)
        acc = g.steps(g.accent)
        da = lightest_passing(acc, dsurface) or best(acc, dsurface)
        if da is None and len(neutral) >= 2:
            da = sorted(neutral, key=lambda t: -t.lum)[1]
        put("dark", "accent", da, against=dsurface)
        for role in SEMANTIC:
            fam = g.family(role)
            base = lightest_passing(fam, dsurface) or best(fam, dsurface)
            put("dark", role, base, against=dsurface, need=4.5)
    res["palette"] = {"primary": g.primary, "neutral": g.neutral, "accent": g.accent}
    return res


def artifact_draft(first: dict, colors: dict, fm: dict | None = None) -> tuple[str, dict]:
    """A heuristic `artifact:` block (each pick annotated with its contrast) + the guess report."""
    g = guess_roles(colors, fm)
    out = ["artifact:   # DECIDE: every mapping below is a heuristic guess - confirm each one\n"]
    for scheme in ("light", "dark"):
        out.append(f"  {scheme}:\n")
        for role in COLOUR_ROLES + INK_ROLES:
            if role not in g[scheme]:
                continue
            note = g["notes"].get((scheme, role))
            line = f"    {role}: '{g[scheme][role]}'"
            out.append(f"{line:<44}# {note}\n" if note else line + "\n")
    typo = first.get("typography") or {}
    body_key = next((k for k in ("body", "body-md", "text") if k in typo), "body")
    disp_key = next((k for k in ("headline", "display", "title") if k in typo), "headline")
    if body_key not in typo:
        g["unresolved"].append(f"artifact.font-body: no typography tier named body/body-md/text")
    if disp_key not in typo:
        g["unresolved"].append(f"artifact.font-display: no typography tier named headline/display/title")
    out.append(f"  font-body: '{{typography.{body_key}}}'\n")
    out.append(f"  font-display: '{{typography.{disp_key}}}'\n")
    out.append("  font-mono: 'ui-monospace, Consolas, Monaco, monospace'\n")
    rk = list(first.get("rounded") or {})
    for role, idx in (("radius-sm", 0), ("radius-md", 1), ("radius-lg", 2)):
        if len(rk) <= idx:
            g["unresolved"].append(f"artifact.{role}: `rounded` has fewer than {idx + 1} steps")
        out.append(f"  {role}: '{{rounded.{rk[idx] if len(rk) > idx else 'TODO'}}}'\n")
    out.append("  # Optional, default when absent: font-latin = font-body, shadow-sm/md = none,\n"
               "  # wash = var(--ds-canvas). Add them only if the brand has them (refs to colors only).\n")
    return "".join(out), g


def cmd_discover(hub: Path, design: dict) -> int:
    """List candidate design files at the configured ref. Read-only: never writes anything."""
    if not design.get("source"):
        raise ConfigError("brain.config.json has no `design.source` {repo, ref} - nothing to discover")
    repo_id = need(design, "source.repo", '"source": {"repo": "web", "ref": "origin/main"}')
    ref = need(design, "source.ref", '"source": {"repo": "web", "ref": "origin/main"}')
    repo = repo_dir(hub, design, str(repo_id))
    commit = check_ref(repo, str(ref))
    pat = re.compile(r"(DESIGN\.md$|tailwind\.config\.|tokens?\.(ts|js|json|css)$|color|theme|"
                     r"variables\.css$|styles?\.css$|preset|\.(woff2?|ttf|otf)$)", re.I)
    hits = [f for f in git_ls(repo, str(ref)) if pat.search(f) and "node_modules" not in f]
    configured = set(design.get("sources") or [])
    print(f"Candidate design sources at {repo_id}:{ref} @ {commit[:12]} ({len(hits)}):")
    for f in hits[:200]:
        print(f"  {'*' if f in configured else ' '} {f}")
    if len(hits) > 200:
        print(f"  ... {len(hits) - 200} more")
    print("\n(* = already in design.sources.) Nothing was written.")
    return 0


def cmd_extract(args, hub: Path, design: dict) -> int:
    if args.discover:
        return cmd_discover(hub, design)
    target = Path(args.out).resolve() if args.out else hub / design["system"]
    if target.exists() and not args.force:
        raise BrandError(f"{target} already exists - refusing to overwrite it. Pass --force to "
                         "regenerate the draft (the file is replaced wholesale).")

    source = design.get("source")
    sources = list(design.get("sources") or []) + list(args.source or [])
    decisions: list[str] = []
    conflicts: list[str] = []
    provenance: dict[str, str] = {}
    fm_sections: dict[str, str] = {}
    design_mds: list[tuple[str, dict]] = []
    source_prose: list[tuple[str, str]] = []
    css_candidates: dict[str, dict[str, str]] = {}
    repo = ref = commit = None

    if not source:
        print("design.source is not configured: writing the blank template. Author the tokens by hand "
              "(or add a `design.source` {repo, ref} and `design.sources` to extract from a frontend).")
    else:
        repo_id = need(design, "source.repo", '"source": {"repo": "web", "ref": "origin/main"}')
        ref = need(design, "source.ref", '"source": {"repo": "web", "ref": "origin/main"}')
        repo = repo_dir(hub, design, str(repo_id))
        commit = check_ref(repo, str(ref))
        if not sources:
            cmd_discover(hub, design)
            print("\n`design.sources` is empty. Add the files that carry the brand to "
                  "brain.config.json and re-run.")
            return 1
        for path in sources:
            text = git_show(repo, str(ref), path)
            origin = f"{repo_id}:{ref}:{path}"
            if text is None:
                raise BrandError(f"source {origin} does not exist at that ref (check design.sources)")
            if path.endswith(".md"):
                fm_text, prose = split_frontmatter(text)
                fm = parse_frontmatter(text)
                if prose.strip():
                    source_prose.append((origin, prose))
                if fm:
                    design_mds.append((origin, fm))
                    if not fm_sections:
                        fm_sections = frontmatter_sections(fm_text)
                        for group in ("colors", "typography", "rounded", "spacing"):
                            if group in fm_sections:
                                provenance[group] = origin
                continue
            if path.endswith((".ts", ".js")):
                css_candidates[origin] = ts_colours(text)
            else:
                css_candidates[origin] = css_var_colours(text)

    # Multiple DESIGN.md files = multiple apps. The brand is what they share.
    if len(design_mds) > 1:
        base_origin, base = design_mds[0]
        for origin, other in design_mds[1:]:
            for group in ("colors", "rounded", "spacing"):
                a, b = base.get(group) or {}, other.get(group) or {}
                for key in sorted(set(a) & set(b)):
                    if norm_colour(str(a[key])) != norm_colour(str(b[key])):
                        conflicts.append(f"{group}.{key}: {a[key]} ({base_origin}) vs {b[key]} ({origin})")
                only = sorted(set(b) - set(a))
                if only:
                    decisions.append(f"{group} tokens only in {origin}: {', '.join(only[:12])}"
                                     f"{' ...' if len(only) > 12 else ''} - brand-level or app-level?")

    base_colors = (design_mds[0][1].get("colors") or {}) if design_mds else {}
    base_norm = {k.lower(): norm_colour(str(v)) for k, v in base_colors.items()}
    extra_colours: dict[str, tuple[str, str]] = {}
    for origin, found in css_candidates.items():
        for name, value in found.items():
            if name in base_norm:
                if base_norm[name] != norm_colour(value):
                    conflicts.append(f"colors.{name}: {base_colors.get(name, base_norm[name])} "
                                     f"(DESIGN.md) vs {value} ({origin})")
            elif name not in extra_colours:
                extra_colours[name] = (value, origin)

    # ---------------------------------------------------------------- assemble the draft
    template_text = TEMPLATE.read_text(encoding="utf-8")
    t_fm_text, t_body = split_frontmatter(template_text)
    t_sections = frontmatter_sections(t_fm_text)
    out = ["---\n",
           "# DRAFT written by brand.py extract on %s. Every line marked DECIDE needs a human or\n"
           "# agent decision; delete this comment when the file is complete.\n" % date.today().isoformat(),
           ]
    first_fm = design_mds[0][1] if design_mds else {}
    for key, fallback in (("name", "DECIDE: product name"),
                          ("description", "DECIDE: one sentence - what the product is and how it should feel.")):
        value = first_fm.get(key)
        if value:
            ask = "is this the product (brand) name or one app's?" if key == "name" else "brand-level or app-level?"
            quoted = str(value).replace("'", "''")
            out.append(f"{key}: '{quoted}'   # from {design_mds[0][0]} - DECIDE: {ask}\n")
            provenance.setdefault(key, design_mds[0][0])
        else:
            out.append(f"{key}: '{fallback}'\n")

    if fm_sections.get("colors"):
        out.append(fm_sections["colors"])
    elif extra_colours:
        out.append("colors:\n")
        for name, (value, origin) in sorted(extra_colours.items()):
            out.append(f"  {name}: '{value}'   # from {origin}\n")
        provenance["colors"] = "; ".join(sorted(css_candidates))
        decisions.append("No source DESIGN.md: `colors` were collected from CSS/TS variables. Prune to "
                         "the brand palette and rename to a ramp (primary-50..950, accent-*, gray-*).")
    else:
        out.append(t_sections.get("colors", "colors:\n"))
    if extra_colours and fm_sections.get("colors"):
        out.append("  # Colours found in other sources but not in the DESIGN.md above - DECIDE whether\n"
                   "  # any is brand-level (then uncomment it and add provenance):\n")
        for name, (value, origin) in sorted(extra_colours.items())[:60]:
            out.append(f"  # {name}: '{value}'   # {origin}\n")

    for group in ("typography", "rounded", "spacing"):
        out.append(fm_sections.get(group) or t_sections.get(group, f"{group}:\n"))
        if group not in fm_sections:
            decisions.append(f"`{group}` came from the template, not a source - fill it in.")

    if not design_mds and not extra_colours:
        # Nothing extracted: the template's own role map is consistent with its own tokens.
        out.append(t_sections["artifact"])
    else:
        block, guess = artifact_draft(first_fm, base_colors or {n: v for n, (v, _) in extra_colours.items()},
                                      first_fm)
        out.append(block)
        decisions += guess["unresolved"] + guess["problems"]
        pal = guess["palette"]
        print(f"palette read as: primary ramp={pal['primary']}, neutral ramp={pal['neutral']}, "
              f"accent ramp={pal['accent']}")
    out.append("provenance:\n")
    if commit:
        out.append(f"  source-commit: '{commit}'\n")
    for group, origin in provenance.items():
        out.append(f"  {group}: '{origin}'\n")
    if not provenance:
        out.append("  colors: 'DECIDE: where each token group came from (repo:ref:path)'\n")
    out.append("---\n")
    body = t_body
    if conflicts:
        body = body.replace("<!-- CONFLICTS -->",
                            "> **Unresolved source conflicts** (from `brand.py extract`):\n>\n"
                            + "".join(f"> - {c}\n" for c in conflicts))
    product = str(first_fm.get("name") or "").strip()
    if product:
        body = body.replace("# Design System: Product name", f"# Design System: {product}", 1)
    if source_prose:
        body = body.rstrip("\n") + "\n\n## Source notes\n\n" \
            "Copied verbatim from the source design files at extract time. Move what is brand-level " \
            "into the sections above, drop what is app-level, then delete this section.\n"
        for origin, prose in source_prose:
            demoted = []
            fence = False
            for line in prose.strip("\n").splitlines():
                if line.lstrip().startswith("```"):
                    fence = not fence
                demoted.append("##" + line if (not fence and re.match(r"#{1,4} ", line)) else line)
            body += f"\n### From `{origin}`\n\n" + "\n".join(demoted) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(out) + body, encoding="utf-8")

    decisions += [
        "artifact.light / artifact.dark: confirm every role mapping (dark roles must reference "
        "existing tokens; never add a hex only for dark mode).",
        "font-body / font-display: confirm the typography keys; font-mono may stay a system stack.",
        "radius-sm/md/lg: pick three rungs of the radius ladder suited to documents.",
        "name / description / prose sections: write them (brand-level only - no app layout rules).",
    ]
    if source and not design.get("fonts"):
        decisions.append("design.fonts is not configured: artifacts will use system stacks and PDFs "
                         "will not embed the brand faces. Add family -> weight -> repo path to embed them.")
    print(f"wrote DRAFT {target}")
    if commit:
        print(f"  source: {design['source']['repo']}:{ref} @ {commit[:12]}")
    print(f"  provenance: {', '.join(provenance) or 'none'}")
    if conflicts:
        print(f"\nCONFLICTS - surface these to the user; do not pick silently ({len(conflicts)}):")
        for c in conflicts:
            print(f"  - {c}")
    print(f"\nStill to decide ({len(decisions)}):")
    for d in decisions:
        print(f"  - {d}")
    print("\nThen: brand.py build")
    return 0


# =========================================================================== fonts

def sfnt_flavor(blob: bytes) -> tuple[str, str]:
    """(container, outline) from the header alone: container woff2|woff|sfnt, outline cff|glyf."""
    sig = blob[:4]
    if sig in (b"wOF2", b"wOFF"):
        container = "woff2" if sig == b"wOF2" else "woff"
        outline = "cff" if blob[4:8] == b"OTTO" else "glyf"
    else:
        container = "sfnt"
        outline = "cff" if sig == b"OTTO" else "glyf"
    return container, outline


def cff_to_glyf(font) -> None:
    """Convert PostScript (CFF) outlines to TrueType (glyf) outlines, in place.

    Chrome's PDF backend will not embed a CFF-flavoured webfont: printing falls back
    to a system face while the screen is fine.
    """
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import newTable

    glyph_order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()
    glyf = newTable("glyf")
    glyf.glyphOrder = glyph_order
    glyf.glyphs = {}
    for name in glyph_order:
        pen = TTGlyphPen(glyph_set)
        glyph_set[name].draw(Cu2QuPen(pen, max_err=1.0, reverse_direction=True))
        glyf.glyphs[name] = pen.glyph()
    font["loca"] = newTable("loca")
    font["glyf"] = glyf
    del font["CFF "]
    font["maxp"].tableVersion = 0x00010000
    for attr, value in [("maxZones", 1), ("maxTwilightPoints", 0), ("maxStorage", 0),
                        ("maxFunctionDefs", 0), ("maxInstructionDefs", 0), ("maxStackElements", 0),
                        ("maxSizeOfInstructions", 0), ("maxComponentElements", 0)]:
        setattr(font["maxp"], attr, value)
    font["head"].glyphDataFormat = 0
    font["head"].indexToLocFormat = 0
    if "post" in font:
        font["post"].formatType = 2.0
        font["post"].extraNames = []
        font["post"].mapping = {}
        font["post"].glyphOrder = glyph_order
    font.sfntVersion = "\000\001\000\000"


def process_face(blob: bytes, extra_text: str, subset_all: bool, no_subset: bool) -> dict:
    container, outline = sfnt_flavor(blob)
    info = {"container_in": container, "outline_in": outline, "bytes_in": len(blob)}
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except ImportError:
        info.update(data=blob, format=container if container != "sfnt" else "truetype",
                    subset=False, converted=False,
                    warning="fonttools not installed: embedded as shipped"
                            + (" - this face is CFF and will NOT embed in a Chrome PDF" if outline == "cff" else ""))
        return info
    # recalcTimestamp=False keeps builds byte-identical: a changed head.modified would make
    # every inlined artifact read as stale after a no-op rebuild.
    font = TTFont(io.BytesIO(blob), recalcTimestamp=False)
    cmap = font.getBestCmap() or {}
    arabic = any(cp in cmap for cp in ARABIC_PROBE)
    info["arabic_script"] = arabic
    info["glyphs_in"] = len(font.getGlyphOrder())
    do_subset = not no_subset and (subset_all or not arabic)
    if do_subset:
        unicodes = set(subset.parse_unicodes(LATIN_RANGES))
        unicodes |= {ord(c) for c in extra_text}
        options = subset.Options()
        options.layout_features = ["*"]
        options.desubroutinize = True
        options.notdef_outline = True
        options.name_IDs = ["*"]
        sub = subset.Subsetter(options=options)
        sub.populate(unicodes=unicodes)
        sub.subset(font)
    converted = False
    if "CFF " in font:
        cff_to_glyf(font)
        converted = True
    fmt = "woff2"
    try:
        import brotli  # noqa: F401
        font.flavor = "woff2"
    except ImportError:
        font.flavor = "woff"
        fmt = "woff"
        info["warning"] = "brotli not installed: emitted woff (zlib), larger than woff2"
    buf = io.BytesIO()
    font.save(buf)
    names = font["name"]
    info["postscript"] = str(names.getDebugName(6) or "") or None
    info["font_family"] = str(names.getDebugName(16) or names.getDebugName(1) or "") or None
    info.update(data=buf.getvalue(), format=fmt, subset=do_subset, converted=converted,
                glyphs_out=len(font.getGlyphOrder()), cmap=set((font.getBestCmap() or {}).keys()))
    return info


def face_rule(family: str, weight: str, data: bytes, fmt: str) -> str:
    mime = {"woff2": "font/woff2", "woff": "font/woff", "truetype": "font/ttf"}.get(fmt, "font/woff2")
    return ("@font-face {\n"
            f'  font-family: "{family}";\n'
            "  font-style: normal;\n"
            f"  font-weight: {weight};\n"
            "  font-display: block;\n"
            f'  src: url("data:{mime};base64,{base64.b64encode(data).decode("ascii")}") format("{fmt}");\n'
            "}")


# =========================================================================== build

def css_block(selector: str, decls: list[tuple[str, str]], indent: str = "") -> str:
    inner = "\n".join(f"{indent}  {k}: {v};" for k, v in decls)
    return f"{indent}{selector} {{\n{inner}\n{indent}}}"


def safe_name(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9-]", "-", str(key)).lower()


def declared_weights(typo: dict) -> list[int]:
    out = set()
    for tier in (typo or {}).values():
        if isinstance(tier, dict) and tier.get("fontWeight") is not None:
            try:
                out.add(int(str(tier["fontWeight"]).strip()))
            except ValueError:
                pass
    return sorted(out)


def nearest_weight(target: int, usable: list[int]) -> int:
    """Nearest usable weight; ties go heavier. No usable set = the target itself."""
    if not usable:
        return target
    return min(usable, key=lambda w: (abs(w - target), -w))


def space_steps(fm: dict, spacing: dict) -> dict[int, str]:
    """--ds-space-1..8, always. Missing steps: n x the scale's base unit when the defined
    numeric steps are all multiples of one px unit, else the nearest defined step."""
    defined: dict[int, str] = {}
    for key, raw in spacing.items():
        if str(key).isdigit():
            defined[int(key)] = resolve(fm, raw, f"spacing.{key}")
    if not defined:
        return {n: f"{4 * n}px" for n in range(1, 9)}
    units = set()
    for k, v in ((k, v) for k, v in defined.items() if k <= 8):
        m = re.fullmatch(r"(\d+(?:\.\d+)?)px", v.strip())
        units.add(round(float(m.group(1)) / k, 4) if m else None)
    unit = units.pop() if len(units) == 1 and None not in units else None
    out = {}
    for n in range(1, 9):
        if n in defined:
            out[n] = defined[n]
        elif unit:
            out[n] = f"{unit * n:g}px"
        else:
            out[n] = defined[min(defined, key=lambda k: (abs(k - n), k))]
    return out


def cmd_build(args, hub: Path, design: dict) -> int:
    path, text, fm = load_design(hub, design)
    roles = resolve_roles(fm)
    design_sha = sha256_file(path)

    source = design.get("source") or {}
    repo = commit = None
    if source:
        repo = repo_dir(hub, design, str(need(design, "source.repo", '"source": {"repo": "web", "ref": "origin/main"}')))
        commit = check_ref(repo, str(need(design, "source.ref", '"source": {"repo": "web", "ref": "origin/main"}')))

    extra_text = ""
    for f in args.text_from or []:
        p = Path(f)
        if not p.is_file():
            raise BrandError(f"--text-from {f}: no such file")
        extra_text += p.read_text(encoding="utf-8", errors="replace")

    fonts_cfg = design.get("fonts") or {}
    faces, report, embedded, coverage, faces_meta = [], [], {}, set(), []
    if fonts_cfg and not source:
        raise BrandError("design.fonts is set but design.source is not - fonts are read from "
                         "design.source.repo at design.source.ref")
    for family, weights in fonts_cfg.items():
        for weight, fpath in sorted(weights.items(), key=lambda kv: int(kv[0])):
            blob = git_show(repo, source["ref"], fpath, binary=True)
            if blob is None:
                raise BrandError(f"design.fonts.{family}.{weight}: {fpath} does not exist at {source['ref']}")
            info = process_face(blob, extra_text, args.subset_all, args.no_subset)
            faces.append(face_rule(family, str(weight), info["data"], info["format"]))
            embedded.setdefault(family, []).append(int(weight))
            faces_meta.append({"family": family, "weight": int(weight), "postscript": info.get("postscript"),
                               "font_family": info.get("font_family"), "path": fpath})
            coverage |= info.get("cmap", set())
            note = []
            note.append("subset" if info["subset"] else ("whole (Arabic script)" if info.get("arabic_script") else "whole"))
            if info["converted"]:
                note.append("CFF->glyf")
            report.append(f"  {family:<12} {weight}  {len(info['data']):>8,} B  {info['format']}  "
                          f"(was {info['bytes_in']:,} B {info['container_in']}/{info['outline_in']}; "
                          f"{', '.join(note)}; glyphs {info.get('glyphs_in', '?')}->{info.get('glyphs_out', '?')})")
            if info.get("warning"):
                report.append(f"    WARNING: {info['warning']}")

    uncovered = []
    if extra_text and coverage:
        uncovered = sorted({c for c in extra_text if ord(c) >= 0x20 and ord(c) not in coverage
                            and c not in "\n\r\t‌‍‎‏"})

    # ------------------------------------------------------------------ custom properties
    common = roles["common"]
    typo = fm.get("typography") or {}
    base = [
        ("--ds-font-body", common["font-body"]),
        ("--ds-font-display", common["font-display"]),
        ("--ds-font-mono", common["font-mono"]),
        ("--ds-font-latin", common["font-latin"]),
    ]
    body_typo = typo.get(str(fm["artifact"]["font-body"]).strip("{}").split(".")[-1]) if isinstance(typo, dict) else None
    leading = body_typo.get("lineHeight") if isinstance(body_typo, dict) else None
    # 1.6 when DESIGN.md is silent: loose enough for scripts with tall ascenders/descenders.
    base.append(("--ds-leading-body", str(leading if leading is not None else 1.6)))

    declared = declared_weights(typo)
    if embedded:
        sets = [set(w) for w in embedded.values()]
        usable = sorted(set.intersection(*sets)) or sorted(set().union(*sets))
    else:
        usable = declared
    weight_vars = {name: nearest_weight(target, usable) for name, target in
                   (("regular", 400), ("strong", 600), ("bold", 700))}
    base += [(f"--ds-weight-{k}", str(v)) for k, v in weight_vars.items()]
    base += [(f"--ds-{r}", common[r]) for r in RADIUS_ROLES]
    spacing = fm.get("spacing") or {}
    steps = space_steps(fm, spacing)
    base += [(f"--ds-space-{n}", steps[n]) for n in range(1, 9)]
    for key, raw in spacing.items():
        name = safe_name(key)
        if not (name.isdigit() and 1 <= int(name) <= 8):
            base.append((f"--ds-space-{name}", resolve(fm, raw, f"spacing.{key}")))
    raw_tokens = []
    for key, raw in (fm.get("colors") or {}).items():
        raw_tokens.append((f"--ds-color-{safe_name(key)}", resolve(fm, raw, f"colors.{key}")))
    for key, raw in (fm.get("rounded") or {}).items():
        raw_tokens.append((f"--ds-rounded-{safe_name(key)}", resolve(fm, raw, f"rounded.{key}")))
    scheme_roles = COLOUR_ROLES + INK_ROLES + list(EFFECT_ROLES)
    light = [(f"--ds-{r}", roles["light"][r]) for r in scheme_roles]
    dark = [(f"--ds-{r}", roles["dark"][r]) for r in scheme_roles]

    header = ("/* GENERATED by brand-system/scripts/brand.py build - do not edit by hand.\n"
              f"   design: {design['system']} sha256={design_sha}\n"
              # The ref, not the commit: a fetch that moves the ref without touching the design
              # must not make every inlined block stale. tokens.json records the commit.
              + (f"   source: {source.get('repo')}:{source.get('ref')}\n" if source else "")
              + "   Style artifacts ONLY through the --ds-* roles below. */")
    parts = [header] + faces + [
        css_block(":root", light + base + raw_tokens),
        "@media (prefers-color-scheme: dark) {\n"
        + css_block(':root:not([data-theme="light"])', dark, "  ") + "\n}",
        css_block(':root[data-theme="dark"]', dark),
        "@media print {\n" + css_block(":root, :root:not([data-theme=\"light\"]), :root[data-theme]", light, "  ")
        + "\n  * { print-color-adjust: exact; -webkit-print-color-adjust: exact; }\n}",
    ]
    css = "\n\n".join(parts) + "\n"

    out_dir = hub / design["build"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "brand.css").write_text(css, encoding="utf-8", newline="\n")

    # Embedded faces, plus the mono stack (a system face by design). With nothing embedded,
    # every family the font roles name is allowed - the PDF report then warns, not fails.
    allowed_families = sorted(set(embedded) | set(family_names(common["font-mono"]))) if embedded else sorted(
        {n for r in ("font-body", "font-display", "font-mono", "font-latin") if r in common
         for n in family_names(common[r])})
    tokens = {
        "generated_by": "brand-system/scripts/brand.py build",
        "design_md": design["system"],
        "design_sha256": design_sha,
        "brand_css_sha256": sha256_text(css),
        "source": ({"repo": source.get("repo"), "ref": source.get("ref"), "commit": commit} if source else None),
        "roles": roles,
        "colors": {k: resolve(fm, v, f"colors.{k}") for k, v in (fm.get("colors") or {}).items()},
        "rounded": {k: resolve(fm, v, f"rounded.{k}") for k, v in (fm.get("rounded") or {}).items()},
        "spacing": {k: resolve(fm, v, f"spacing.{k}") for k, v in spacing.items()},
        "fonts_embedded": bool(embedded),
        "embedded_weights": {f: sorted(w) for f, w in embedded.items()},
        # What a PDF actually records: PostScript names (name ID 6), not config family keys.
        "embedded_faces": faces_meta,
        "declared_weights": declared,
        "weights": weight_vars,
        "allowed_families": allowed_families,
        "css_vars": sorted({k for k, _ in light + base + raw_tokens}),
    }
    (out_dir / "tokens.json").write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")

    rel = out_dir.relative_to(hub)
    print(f"wrote {rel / 'brand.css'} ({len(css.encode('utf-8')):,} bytes)")
    print(f"wrote {rel / 'tokens.json'}")
    print(f"  design {design['system']} sha256 {design_sha[:12]}")
    if report:
        print("  fonts:")
        print("\n".join(report))
    else:
        print("  fonts: none embedded (no design.fonts) - artifacts use the system stacks in DESIGN.md "
              "typography, and PDF font reports will warn rather than fail")
    if uncovered:
        print(f"\nWARNING: {len(uncovered)} character(s) from --text-from are in NO embedded face and will "
              f"fall back to a system font in a PDF: {' '.join(uncovered[:40])}")
        print("  " + ", ".join(f"U+{ord(c):04X}" for c in uncovered[:40]))
    print("\nNext: brand.py inline <artifact.html> for every artifact template, then check-brand.py.")
    return 0


# =========================================================================== inline

def cmd_inline(args, hub: Path, design: dict) -> int:
    css_path = hub / design["build"] / "brand.css"
    if not css_path.is_file():
        raise BrandError(f"{css_path} does not exist - run `brand.py build` first")
    css = css_path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    status = 0
    for name in args.files:
        path = Path(name)
        if not path.is_file():
            print(f"  MISSING {name}")
            status = 1
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            html = fh.read()
        nl = "\r\n" if "\r\n" in html else "\n"
        block = f"{BEGIN}\n{css}\n{END}".replace("\n", nl)
        b, e = html.find(BEGIN), html.find(END)
        if b != -1 and e != -1 and e > b:
            new = html[:b] + block + html[e + len(END):]
            how = "refreshed"
        elif b != -1 or e != -1:
            print(f"  BROKEN  {name}: has only one of the BRAND markers - fix by hand")
            status = 1
            continue
        else:
            m = re.search(r"<style[^>]*>", html, re.I)
            if m:
                new = html[:m.end()] + nl + block + nl + html[m.end():]
                how = "inserted into first <style>"
            else:
                h = re.search(r"</head\s*>", html, re.I)
                if not h:
                    print(f"  SKIPPED {name}: no <style> and no </head> to insert into")
                    status = 1
                    continue
                new = html[:h.start()] + f"<style>{nl}{block}{nl}</style>{nl}" + html[h.start():]
                how = "inserted new <style> in <head>"
        dest = Path(args.out) / path.name if args.out else path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(new, encoding="utf-8", newline="")
        print(f"  {how:<30} {dest}")
    return status


# =========================================================================== show

def cmd_show(args, hub: Path, design: dict) -> int:
    path, _, fm = load_design(hub, design)
    roles = resolve_roles(fm)
    art = fm["artifact"]
    print(f"{design['system']}  sha256 {sha256_file(path)[:12]}")
    print(f"{'role':<16} {'light':<34} {'dark':<34}")
    for role in COLOUR_ROLES:
        lr = f"{roles['light'][role]}  {art['light'][role]}"
        dr = f"{roles['dark'][role]}  {art['dark'][role]}"
        print(f"{role:<16} {lr:<34} {dr:<34}")
    for role, value in roles["common"].items():
        print(f"{role:<16} {value}")
    tokens = hub / design["build"] / "tokens.json"
    if tokens.is_file():
        data = json.loads(tokens.read_text(encoding="utf-8"))
        fresh = data.get("design_sha256") == sha256_file(path)
        print(f"\ncompiled: {tokens.relative_to(hub)} - {'current' if fresh else 'STALE (run brand.py build)'}")
        if data.get("embedded_weights"):
            print("embedded: " + "; ".join(f"{f} {w}" for f, w in data["embedded_weights"].items()))
        else:
            print("embedded: none (system stacks)")
    else:
        print("\ncompiled: not built yet (run brand.py build)")
    return 0


# =========================================================================== pdf-fonts

def pdf_font_names(pdf: bytes) -> list[str]:
    chunks = [pdf]
    for m in re.finditer(rb"stream\r?\n", pdf):
        start = m.end()
        end = pdf.find(b"endstream", start)
        if end == -1:
            continue
        try:
            chunks.append(zlib.decompress(pdf[start:end]))
        except zlib.error:
            pass
    names = set()
    for chunk in chunks:
        for m in re.finditer(rb"/(?:BaseFont|FontName)\s*/([^\s/\[\]<>()]+)", chunk):
            names.add(m.group(1).decode("latin-1"))
    return sorted(names)


def cmd_pdf_fonts(args, hub: Path, design: dict) -> int:
    tokens_path = hub / design["build"] / "tokens.json"
    if not tokens_path.is_file():
        print(f"brand-system: {tokens_path} does not exist - run brand.py build first; "
              "cannot judge the PDF's fonts", file=sys.stderr)
        return 2
    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"brand-system: {pdf}: no such file", file=sys.stderr)
        return 2
    tokens = json.loads(tokens_path.read_text(encoding="utf-8"))

    def key(n: str) -> str:
        return re.sub(r"[\s_-]", "", n).lower()
    postscript = {key(f["postscript"]) for f in tokens.get("embedded_faces", []) if f.get("postscript")}
    families = {key(a) for a in tokens.get("allowed_families", [])}
    families |= {key(f["font_family"]) for f in tokens.get("embedded_faces", []) if f.get("font_family")}
    names = pdf_font_names(pdf.read_bytes())
    bare = sorted({re.sub(r"^[A-Z]{6}\+", "", n) for n in names})
    print(f"{pdf}: {len(bare)} font(s)")
    bad = []
    for n in bare:
        how = "face" if key(n) in postscript else \
            ("family" if any(key(n).startswith(f) for f in families if f) else None)
        print(f"  {'ok ' if how else 'OFF'}  {n}" + (f"  ({how})" if how else ""))
        if not how:
            bad.append(n)
    if not names:
        print("FAIL: no font names found in the PDF - it may be image-only or unreadable")
        return 1
    if not tokens.get("fonts_embedded", False):
        print(f"WARN: the brand embeds no fonts (no design.fonts); the PDF uses whatever the rendering "
              f"machine has. {len(bad)} face(s) outside the named stacks. Not a failure.")
        return 0
    if bad:
        print(f"FAIL: {len(bad)} non-brand font(s). A non-brand face means a character fell out of the "
              "embedded subset or a weight is not embedded - widen with build --text-from, or fix the copy.")
        return 1
    print("PASS: only brand faces embedded")
    return 0


# =========================================================================== main

def main() -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hub", help="hub root (default: walk up to brain.config.json)")
    common = argparse.ArgumentParser(add_help=False)
    # SUPPRESS keeps a --hub given before the subcommand from being reset to None.
    common.add_argument("--hub", default=argparse.SUPPRESS, help="hub root (also accepted here)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("extract", parents=[common], help="write a DRAFT DESIGN.md from the configured sources")
    p.add_argument("--force", action="store_true", help="overwrite an existing DESIGN.md")
    p.add_argument("--source", action="append", help="extra source path at design.source.ref (repeatable)")
    p.add_argument("--discover", action="store_true", help="list candidate design files at the ref")
    p.add_argument("--out", help="write the draft here instead of design.system (e.g. to compare)")
    p = sp.add_parser("build", parents=[common], help="compile brand.css + tokens.json")
    p.add_argument("--text-from", action="append", metavar="FILE",
                   help="widen Latin subsets with every character in FILE (repeatable)")
    p.add_argument("--subset-all", action="store_true", help="also subset Arabic-script faces")
    p.add_argument("--no-subset", action="store_true", help="embed every face whole")
    p = sp.add_parser("inline", parents=[common], help="refresh the BRAND block in HTML files")
    p.add_argument("files", nargs="+")
    p.add_argument("--out", help="write refreshed copies into DIR instead of in place")
    sp.add_parser("show", parents=[common], help="print resolved roles")
    p = sp.add_parser("pdf-fonts", parents=[common], help="list fonts embedded in a PDF against the brand's")
    p.add_argument("pdf")
    args = ap.parse_args()
    hub = find_hub(args.hub)
    design = design_config(hub, quiet=args.cmd in ("show", "pdf-fonts", "inline"))
    return {"extract": cmd_extract, "build": cmd_build, "inline": cmd_inline,
            "show": cmd_show, "pdf-fonts": cmd_pdf_fonts}[args.cmd](args, hub, design)


if __name__ == "__main__":
    sys.exit(main())
