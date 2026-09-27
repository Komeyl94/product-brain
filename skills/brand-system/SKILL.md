---
name: "brand-system"
description: "Use when setting up, extracting, refreshing or changing a product's design system or brand; when the user mentions DESIGN.md, brand tokens, brand colours or brand fonts, or says generated artifacts don't match the brand, look off-brand or look generic; when styling any generated report, release note, roadmap, dashboard, HTML page or PDF; when a PDF shows the wrong font; and when check-brand.py fails or a BRAND block is stale."
argument-hint: "[extract | build | inline <file.html>... | check <file.html>... | show] (default: show)"
compatibility: "Requires a Product Brain hub (brain.config.json; optional `design` block) with the frontend repo cloned when extracting. git + python3.9+. fonttools + brotli to subset and convert fonts (degrades with a warning); PyYAML optional. Windows/Git Bash safe."
metadata:
  author: "product-brain"
user-invocable: true
---

# Brand System

`${CLAUDE_SKILL_DIR}` is this skill's base directory (shown when the skill loads);
substitute it if your shell does not expand it.

One product-level design system, compiled once, inlined into every artifact:

```
<hub>/DESIGN.md            the brand: tokens (YAML frontmatter) + prose. Human-owned.
<hub>/brand/brand.css      compiled: embedded fonts + --ds-* roles. Generated.
<hub>/brand/tokens.json    compiled: resolved values, hashes, embedded weights. Generated.
```

## The rule

**Every generated artifact styles itself only from the compiled brand.** It inlines
`brand.css` between `/* BRAND:BEGIN */` and `/* BRAND:END */` inside a `<style>` (a published
artifact cannot load a local file), and every colour, font-family and radius in its own CSS is
a `var(--ds-*)`. Derived tints are `color-mix(in oklab, var(--ds-x) N%, var(--ds-y))`. Charts
use role colours and mixes of them, never a separate palette. `check-brand.py` enforces this,
and zero failures is the bar.

An artifact that invents its own palette looks fine alone and wrong next to the product, and
nobody notices until they are side by side. The compiled brand is what stops that.

## Configuration

Read from `brain.config.json` → `design`:

| Key | Required | Meaning |
|---|---|---|
| `system` | no (default `DESIGN.md`) | hub-relative path of the product-level design system |
| `build` | no (default `brand`) | hub-relative output dir for `brand.css` + `tokens.json` |
| `source` | for `extract` and fonts | `{"repo": "<repo id>", "ref": "origin/develop"}` - read with `git show <ref>:<path>`, never the checkout |
| `sources` | for `extract` | paths (at `ref`) of the design evidence: DESIGN.md files, token files, CSS variables |
| `fonts` | no | `{"Family": {"400": "<path at ref>", ...}}` - embedded for PDFs |

Without `source`, DESIGN.md is hand-authored. Without `fonts`, the brand uses the system stacks
named in DESIGN.md typography, emits no `@font-face`, the weight check is skipped, and PDF font
reports warn instead of failing.

## Commands

```bash
python "${CLAUDE_SKILL_DIR}/scripts/brand.py" extract [--source PATH ...] [--discover] [--force] [--out FILE]
python "${CLAUDE_SKILL_DIR}/scripts/brand.py" build [--text-from FILE ...] [--subset-all | --no-subset]
python "${CLAUDE_SKILL_DIR}/scripts/brand.py" inline page.html [...] [--out DIR]
python "${CLAUDE_SKILL_DIR}/scripts/brand.py" show
python "${CLAUDE_SKILL_DIR}/scripts/brand.py" pdf-fonts file.pdf
python "${CLAUDE_SKILL_DIR}/scripts/check-brand.py" page.html [...] [--allow-literal VALUE] [-v]
```

All scripts find the hub by walking up to `brain.config.json` (`--hub`, before or after the
subcommand, overrides). A repo's clone is `repos[].path` if set, else
`<workspace.repos_dir>/<id>`, else `repos/<id>`. `design.source.ref` is validated before git
sees it (a value starting with `-` is rejected, a ref that does not resolve fails with exit 2).
`extract --discover` only lists candidates - it never writes, even when DESIGN.md exists.

## Extracting a product-level DESIGN.md

The brand is **what the apps share**, not any one app's design. App-level systems (shells,
layout, components, navigation, material effects) stay in each app's own DESIGN.md.

1. **Find the evidence at the configured ref.** `brand.py extract --discover` lists candidates
   at `design.source.ref`: `DESIGN.md` files, `tailwind.config.*`, token/colour/theme files,
   `styles.css` / `variables.css` with CSS custom properties, and font files. Read the likely
   ones with `git -C <repo> show <ref>:<path>`. Never read the working tree - the clone may be
   on a feature branch, and a production branch may carry a retired palette. If the ref looks
   wrong for "the current brand", ask.
2. **Configure the sources** you will extract from (`design.sources`; or pass extra ones with
   `--source` for a one-off comparison), and `design.fonts` for the faces the apps ship.
3. **Run `brand.py extract`.** It writes a DRAFT DESIGN.md from the template: token groups
   copied **verbatim** from the first source DESIGN.md frontmatter (when one exists), with its
   `name`/`description`, colours found in other sources listed as commented candidates, a
   guessed `artifact` role map, `provenance` naming `repo:ref:path` and the commit, and the
   source prose under "Source notes". Roles are guessed from the palette itself: ramps are
   clustered by name (`x-50` .. `x-950`), the most chromatic ramp is primary and the least
   chromatic the neutrals, and each text role is the step that clears 4.5:1 on its ground
   (the ratio is written beside every pick). It refuses to overwrite an existing DESIGN.md
   without `--force`; `--out FILE` writes the draft elsewhere, e.g. to compare with the current
   file. With no `design.source` it writes the blank template.
4. **Read what it prints.** "CONFLICTS" are the same token with different values in different
   sources; "Still to decide" lists every role it could not place (`{colors.TODO}`, which fails
   the build) and every pick that fails contrast, plus the judgement calls. **Surface every conflict to the
   user - do not pick silently.** A provisional choice is fine if it is written down in the
   file's "Open decisions" and in your report.
5. **Complete it by hand.** Keep only brand-level tokens (drop component states, glass, shell
   radii). Map the `artifact` roles deliberately - text roles must pass contrast, dark roles
   must reference existing tokens. Write the prose: what is brand-level vs app-level, how
   artifacts apply it, voice, Do/Don't, open decisions. Keep facts consistent with the
   product's own brand commitments (PRODUCT.md or equivalent).
6. **Build, inline, check** (below), and look at a rendered artifact in light and dark.

Format details - the frontmatter subset, the `artifact` and `provenance` blocks, the
`tokens.json` keys: [references/design-md-format.md](references/design-md-format.md).
Skeleton: [templates/DESIGN.template.md](templates/DESIGN.template.md).

## The `artifact` role block

Required, in both schemes: `canvas surface inset ink muted border primary primary-strong
primary-soft on-primary accent success warning danger info`; shared: `font-body font-display
font-mono`, `radius-sm radius-md radius-lg`. Each is a `{colors.x}` / `{typography.x}` /
`{rounded.x}` reference; a colour literal is accepted only if it already exists in `colors`.
**If the product has no dark scheme, map the dark roles onto the existing ramp** - never add a
hex that exists only for dark mode.

Optional roles - **brand.css always emits their variables**, so a template may use them for any
brand:

| Role | Default when DESIGN.md omits it |
|---|---|
| `font-latin` (shared) | same stack as `font-body` |
| `success-ink` `warning-ink` `danger-ink` `info-ink` (per scheme) | the base role |
| `shadow-sm` `shadow-md` (shared or per scheme) | `none` |
| `wash` (shared or per scheme; a colour or a gradient of `{colors.x}` refs) | `var(--ds-canvas)` |

A per-scheme effect falls back to the shared value, then the default - never to the other
scheme's value, so a light gradient wash does not leak into dark mode. Effect values may use only
`{colors.x}` refs or palette literals; express alpha as `color-mix(in oklab, {colors.x} N%,
transparent)`. A brand that forbids shadows or gradients simply leaves them out.

**Text-safe semantic colours.** Semantic colours are often chosen as fills and fail 4.5:1 as
text on a light surface (amber and bright green almost always do). The `*-ink` roles are the
variant an artifact uses for *text* in that state; use the base role for fills, dots, bars and
borders. Set `*-ink` to a darker **existing** step that passes 4.5:1. If the palette has none,
leave it unset (it defaults to the base role), record the contrast under Open decisions, and
design artifacts so that colour is never small text (ink text on a tinted chip). Never mix a new
colour at build time to pass - that invents a colour the brand does not have. `extract` picks
passing steps where they exist and reports the rest with their ratios.

In CSS they are `--ds-<role>`; also `--ds-space-1` .. `--ds-space-8` (always; missing steps are
filled from the scale's unit, or the nearest step), any other `--ds-space-<key>`,
`--ds-leading-body`, `--ds-weight-regular|strong|bold` (400/600/700 mapped to the nearest
embedded - or, with no fonts, declared - weight), and every raw token as `--ds-color-<name>` /
`--ds-rounded-<name>` for the rare case a role is not enough.

## Build

`brand.py build` resolves every reference recursively (an unresolved or circular reference,
or an off-palette literal in a role, **fails loudly**), then writes `brand.css` and
`tokens.json`. Builds are byte-for-byte reproducible.

**Every build that changes `brand.css` makes every inlined BRAND block stale.** After a
rebuild, re-run `inline` on the hub's **living artifacts** (the generated pages under `docs/`),
then `check-brand.py`. **Skill assets** (templates and fixtures shipped inside a skill) keep an
empty or placeholder BRAND block - the block is hub-specific, so a filled one in a skill folder
is always somebody else's brand; the generating skill inlines it when it writes the page.
The CSS header names the source ref, not its commit, so fetching the source repo does not by
itself make pages stale.

### Fonts - four traps, all silent on screen and visible only in the PDF

1. **A linked web-font stylesheet is not an option.** A headless browser does not fetch it
   when printing, so the face falls back to a system font. Faces are embedded as base64.
2. **Chrome will not embed a CFF-flavoured web font in a PDF.** Build converts CFF
   (PostScript) outlines to TrueType. Without fonttools a CFF face is embedded as shipped and
   the build warns - that PDF will ship in a system face.
3. **Chrome activates a face only when laid-out content uses it, mid-paint.** A face used by
   one short run can miss the PDF. Artifacts call `document.fonts.forEach(f => f.load())` up
   front and the renderer waits on `document.fonts.ready` before printing.
4. **A subset silently drops characters the copy uses** - and one missing glyph (an arrow, a
   check mark) puts a system face into the PDF. Latin faces are subset to a generous Latin
   range; **widen it with `--text-from <files>`** (the build then lists any character no
   embedded face covers). **Faces that carry Arabic script are embedded whole** - shaping needs
   the full set of joining forms - unless `--subset-all`.

Only the weights listed in `design.fonts` are embedded; `check-brand.py` fails any other weight,
because asking for it falls out to a synthesised or system face. With no fonts embedded it checks
against the weights DESIGN.md typography declares (`tokens.json` `declared_weights`). Templates
should say `font-weight: var(--ds-weight-strong)`, not `600`, so they fit every brand.

## Inline

```bash
python "${CLAUDE_SKILL_DIR}/scripts/brand.py" inline docs/report.html
```

Replaces the content between the markers; if there are none, inserts the block at the top of
the first `<style>` (or a new `<style>` in `<head>`). Nothing else in the file changes - the
file's own newline style is kept (a CRLF file gets a CRLF block). `--out DIR` writes refreshed
copies elsewhere (used for the fixtures).

## Check

```bash
python "${CLAUDE_SKILL_DIR}/scripts/check-brand.py" docs/report.html
```

Per-file tally of six checks: **brand-block** (missing, malformed, or stale against
`tokens.json` `brand_css_sha256`, or no `<meta charset="utf-8">` in the first 1024 bytes), **colour-literal** (hex / functional / named colour outside
the block, in `<style>`, `style=""`, SVG paint attributes, or a script string that *is* a
colour or follows a colour property - "PR #285" in data is prose), **font-family** (anything but
`var(--ds-font-*)`, including shorthands and font stacks hidden in custom properties),
**font-weight** (a weight no brand face embeds - or, with no fonts, DESIGN.md does not declare -
or `bolder`/`lighter`), **unknown-token** (`var(--ds-x)` that brand.css does not define),
**effect-literal** (any `linear-`/`radial-`/`conic-gradient(` outside the block, or a
`box-shadow`/`text-shadow`/`filter: drop-shadow()` that is not `none` or `var(--ds-shadow-*)`;
hairlines and focus rings are borders and outlines, not shadows). Comments are ignored.

`--allow-literal VALUE` is the documented escape hatch for a colour that genuinely cannot be a
role (e.g. a third-party embed's required colour). Every allowed use is printed in the tally;
say why in your report. It is never a fix for "the palette lacked a colour" - add the token to
DESIGN.md instead.

**If you change the checker, run it on both fixtures:**

```bash
python "${CLAUDE_SKILL_DIR}/scripts/check-brand.py" "${CLAUDE_SKILL_DIR}/fixtures/off-brand.html" "${CLAUDE_SKILL_DIR}/fixtures/off-brand-missing-block.html"
python "${CLAUDE_SKILL_DIR}/scripts/brand.py" inline "${CLAUDE_SKILL_DIR}/fixtures/on-brand.html" --out <tmp>
python "${CLAUDE_SKILL_DIR}/scripts/check-brand.py" <tmp>/on-brand.html
```

`off-brand.html` must fail **every applicable check** (a pass means the checker broke). The
one check that can be inapplicable is font-weight: it is skipped - with a note in the tally -
only when the brand embeds no fonts **and** DESIGN.md typography declares no weights. The
missing-block fixture must fail brand-block. The on-brand copy must pass **for any brand**: it
uses only variables brand.css always emits (roles, optional roles with defaults,
`--ds-space-1..8`, `--ds-weight-*`) and no numeric weights. The on-brand fixture ships with a
placeholder block because its real block depends on the hub's build.

## Verifying a PDF

Render with headless Chromium through Playwright (Persian and other complex scripts need real
shaping and bidi; a generic PDF writer emits broken text and reports success), then:

```bash
python "${CLAUDE_SKILL_DIR}/scripts/brand.py" pdf-fonts out.pdf
```

It lists every font in the PDF against the faces the build embedded - by their PostScript
names (`tokens.json` `embedded_faces`), which is what a PDF records, so a config family named
"Brand Sans" that ships Inter files still matches - plus the mono/system families. An `OFF`
face means a character fell out of a subset or a weight is not embedded: exit 1. With no
`design.fonts` it prints WARN and exits 0. With no `tokens.json` (brand never built) it cannot
judge and exits 2.

## Common mistakes

- **Reading design sources from the checkout.** It may be a feature branch or production's
  retired palette. Always `git show <design.source.ref>:<path>`.
- **Picking between conflicting sources silently.** Record the conflict and ask.
- **Copying an app's DESIGN.md wholesale.** Shells, component states and glass are app-level.
- **Inventing a dark palette.** Dark roles reference existing ramp tokens.
- **Hand-editing `brand.css` or the BRAND block.** Edit DESIGN.md, then build and inline.
- **No early charset.** The block is ~0.5 MB of ASCII, so a browser that sniffs the first
  1024 bytes guesses windows-1252 and every dash and non-Latin character after it is mojibake.
  Put `<meta charset="utf-8">` first; `check-brand.py` fails it otherwise.
- **Rebuilding without re-inlining.** Every artifact goes stale; `check-brand.py` says so.
- **A hex "just for this chart".** Use `color-mix` of roles; the palette is the brand.
- **A literal shadow or gradient.** Effects are brand-owned: `var(--ds-shadow-sm|md)`,
  `var(--ds-wash)`. A focus ring is an `outline`, a hairline is a `border`.
- **A semantic colour as small text.** Use the `*-ink` role for text, the base role for fills.
- **Naming a font face or a weight in the artifact's CSS.** Use `var(--ds-font-*)` and an
  embedded weight - anything else is a system face in the PDF.
- **Trusting the screen.** Every font trap renders perfectly on screen. Read the PDF font
  report.
- **Putting a customer's or tenant's identity on an artifact** when the product is
  white-label. Artifacts carry the product brand.
