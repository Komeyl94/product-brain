# The DESIGN.md format the brand tools read

A product-level `DESIGN.md` is Markdown with a YAML frontmatter. The prose is for people; the
frontmatter is for `brand.py`. This file documents exactly which frontmatter the tools read.
Anything else in the frontmatter (`components`, extra typography tiers, ...) is kept for
humans and design tools and ignored by the build.

PyYAML is used when installed. Without it, a small built-in reader handles **block-style**
YAML: nested maps, quoted or bare scalars, numbers, `true`/`false`, lists of scalars, and `#`
comments. Flow style (`{a: 1}`, `[a, b]`) is rejected with a message rather than misread. Quote
every colour: a bare `#4F46E5` is a YAML comment.

## Groups the build reads

| Key | Shape | Emitted as |
|---|---|---|
| `colors` | `name: 'value'` - hex, `rgb()`, `oklch()`, `color-mix(...)`, or a `{colors.x}` reference | `--ds-color-<name>` |
| `typography` | `tier: {fontFamily, fontSize, fontWeight, lineHeight, letterSpacing}` | only through the font roles |
| `rounded` | `name: '4px'` | `--ds-rounded-<name>` |
| `spacing` | `key: '4px'` (numeric keys are fine) | `--ds-space-<key>` |
| `artifact` | the role map below | `--ds-<role>` |
| `provenance` | `group: 'repo:ref:path'` strings | recorded, not emitted |

`name` and `description` are read by people and by design tooling.

## References

A value of the form `{group.key}` (or `{group.key.sub}`) is replaced by the value it points at,
recursively, anywhere inside a string - `'color-mix(in oklab, {colors.primary-600} 20%, transparent)'`
works. A reference to a typography tier resolves to that tier's `fontFamily`. An unresolved or
circular reference **fails the build** and names the key.

## The `artifact` block (required)

The contract between the design system and every generated artifact. Artifacts may use these
roles and nothing else.

```yaml
artifact:
  light:                       # all 15 colour roles are required
    canvas:         '{colors.surface-canvas}'   # page ground
    surface:        '{colors.surface-card}'     # cards, panels
    inset:          '{colors.surface-inset}'    # a group nested inside a card
    ink:            '{colors.gray-900}'         # body text
    muted:          '{colors.gray-600}'         # metadata, captions
    border:         '{colors.border}'           # hairlines
    primary:        '{colors.primary-600}'      # the one action, the main series, links
    primary-strong: '{colors.primary-900}'      # headings / brand-coloured text
    primary-soft:   '{colors.primary-50}'       # tinted ground, bar tracks
    on-primary:     '{colors.white}'            # text on a primary fill
    accent:         '{colors.accent-600}'       # the single counterweight
    success:        '{colors.success-600}'
    warning:        '{colors.warning}'
    danger:         '{colors.danger}'
    info:           '{colors.info}'
  dark:                        # the same 15 keys
    canvas:         '{colors.primary-950}'
    ...
  font-body:    '{typography.body}'             # required
  font-display: '{typography.headline}'         # required
  font-mono:    'ui-monospace, Consolas, monospace'   # required; a literal system stack is fine
  font-latin:   '{typography.latin}'            # optional: a Latin-first stack for LTR runs
  radius-sm:    '{rounded.xsmall}'              # required: chips, buttons, code
  radius-md:    '{rounded.small}'               # required: notices, insets
  radius-lg:    '{rounded.medium}'              # required: cards, panels
```

Rules the build enforces:

- Every colour role is a `{colors.x}` reference **or** a literal that already exists as a value
  in `colors`. A literal that is not in the palette fails the build - add it to `colors` with
  provenance, or reference an existing token.
- **Dark roles reference existing tokens.** If the product has no dark scheme, map the dark
  roles onto the ramp (950/900 grounds, 100/200 ink, 300/400 emphasis). Never introduce a hex
  only for dark mode.
- A role that resolves to something that is not a colour fails the build.
- Unknown role names fail the build, so a typo cannot silently become an unused variable.

### Optional roles (their variables are always emitted)

```yaml
artifact:
  light:
    warning-ink: '{colors.amber-700}'   # text-safe variant; default = the base role
    wash: 'linear-gradient(135deg, {colors.primary-50} 0%, {colors.primary-100} 100%)'
  dark: {...}                            # dark.wash absent -> var(--ds-canvas), NOT the light wash
  shadow-sm: '0 1px 3px 0 color-mix(in oklab, {colors.gray-900} 12%, transparent)'
  shadow-md: '0 8px 24px 0 color-mix(in oklab, {colors.primary-600} 20%, transparent)'
  font-latin: '{typography.latin}'
```

| Role | Where | Default |
|---|---|---|
| `success-ink` `warning-ink` `danger-ink` `info-ink` | per scheme | the base role |
| `shadow-sm` `shadow-md` | per scheme or shared | `none` |
| `wash` | per scheme or shared | `var(--ds-canvas)` |
| `font-latin` | shared | the `font-body` stack |

Effect values may contain only `{colors.x}` refs or literals already in `colors`; an off-palette
literal fails the build. Resolution order for an effect: scheme block, then shared, then default.

### Always-emitted base variables

- `--ds-leading-body` - the `font-body` tier's `lineHeight` (1.6 if absent).
- `--ds-space-1` .. `--ds-space-8` - from numeric `spacing` keys. Missing steps are `n x unit`
  when the defined steps 1..8 share one px unit, else the nearest defined step; with no
  `spacing` at all, 4px multiples. Other spacing keys are emitted as `--ds-space-<key>`.
- `--ds-weight-regular|strong|bold` - 400 / 600 / 700 mapped to the nearest usable weight
  (embedded weights common to every embedded family; with no fonts, the weights typography
  declares; ties go heavier).

## The `provenance` block

Where each group was lifted from, as `repo:ref:path`, plus `source-commit` for the exact
commit `extract` read. It lets anyone re-derive a token instead of guessing, and it is how a
reviewer tells an extracted value from an invented one. Free text after the path (what was
omitted, what corroborates it) is fine.

```yaml
provenance:
  source-commit: '0123abc...'
  colors: 'web:origin/develop:apps/admin/DESIGN.md (ramp corroborated by apps/site/src/styles.css)'
  typography: 'web:origin/develop:apps/admin/DESIGN.md'
```

## Compiled output

`brand.py build` writes, under `design.build` (default `brand/`):

- **`brand.css`** - in order: `@font-face` rules (base64 woff2), `:root` light roles + base
  roles + every raw token, dark roles under both `@media (prefers-color-scheme: dark)
  { :root:not([data-theme="light"]) }` and `:root[data-theme="dark"]`, then a print block that
  restores the light roles and sets `print-color-adjust: exact`.
- **`tokens.json`** - stable keys:

| Key | Meaning |
|---|---|
| `design_md` | hub-relative path of the DESIGN.md that was compiled |
| `design_sha256` | sha256 of that DESIGN.md's bytes - compare to detect a stale build |
| `brand_css_sha256` | sha256 of `brand.css` (CRLF->LF, trimmed) - what `check-brand.py` compares each BRAND block with |
| `source` | `{repo, ref, commit}` or `null` |
| `roles` | `{light, dark, common}` resolved values, optional roles filled with their defaults |
| `colors`, `rounded`, `spacing` | resolved raw tokens |
| `fonts_embedded` | `false` when `design.fonts` is absent |
| `embedded_weights` | `{family: [weights]}` |
| `declared_weights` | every `fontWeight` in DESIGN.md typography - the font-weight check's set when nothing is embedded |
| `weights` | `{regular, strong, bold}` as emitted in `--ds-weight-*` |
| `allowed_families` | families a PDF may contain (embedded faces + the mono stack; every role family when nothing is embedded) |
| `css_vars` | every `--ds-*` name brand.css defines |

## Shape of a complete file (abridged - copy the template, not this)

```yaml
---
name: 'Example'
description: 'Calm, precise, blue.'
colors:
  blue-50: '#EFF6FF'
  blue-600: '#2563EB'
  blue-900: '#1E3A8A'
  blue-950: '#172554'
  pink-600: '#DB2777'
  green-600: '#16A34A'
  amber-500: '#F59E0B'
  red-600: '#DC2626'
  sky-600: '#0284C7'
  white: '#FFFFFF'
  slate-50: '#F8FAFC'
  slate-100: '#F1F5F9'
  slate-200: '#E2E8F0'
  slate-400: '#94A3B8'
  slate-600: '#475569'
  slate-800: '#1E293B'
  slate-900: '#0F172A'
typography:
  body: {fontFamily: ...}      # block style in real files - shown flow-style here for brevity
rounded: {sm: '4px', md: '8px', lg: '16px'}
artifact:
  light: {canvas: '{colors.slate-50}', surface: '{colors.white}', ...}
  dark:  {canvas: '{colors.slate-900}', surface: '{colors.slate-800}', ...}
  ...
---
```

The skill's `templates/DESIGN.template.md` is a complete, buildable skeleton in block style.
