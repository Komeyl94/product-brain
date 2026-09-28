# Rebuild contract

Invariants the rebuilt dashboard page (`dashboard.out`) must satisfy. Most are enforced
by `scripts/check-inputs.py`; the rest are judgement the script cannot make. Read this
before editing the page, not after. A hub with no page yet starts from
`assets/product-hub-template.html`, which already satisfies every row below.

## Structure the checks depend on

Keep these greppable — the gate parses the page, so renaming them silently disables a
check rather than failing it.

| Must stay | Why |
|---|---|
| `<script id="hub-state" type="application/json">` | the gate compares the embed against the committed state file |
| `var FOCUS = [ { id: "f1", title:…, body:…, chips:…, due:… } ]` | focus-row content, derived; the state file supplies only status by id |
| `Obligations at risk` tile with `<span class="v">N<small> / M</small>` — **only** when an input has `"kind": "goals"` | the gate reconciles `M` against plotted obligations, and fails a page that renders the tile without a goals input |
| `{ id: "…", d: "YYYY-MM-DD", s: "…", t: "…", n: "…" }` shape in the `ROWS` array (lanes `{lane, name, sub, items}`) | how obligations are counted and plotted |
| `<meta charset="utf-8">` as the first line | the inlined brand block is ASCII; without it scripts' dashes render as mojibake |
| `var TODAY = new Date(y, m, d)` and `var T0 = …` | the timeline clock check (JS months are zero-indexed) |
| A `Known gaps` paragraph in the provenance footer | where every WARN and accepted FAIL is disclosed |
| One `data-graph-repo="<id>" data-graph-branch="<branch>" data-graph-built="YYYY-MM-DD"` element per configured repo, its text naming the branch | the `graph disclosed` FAIL — cross-checked against `sync-report.md`'s Built-from table; the contract that replaced forcing a branch switch |
| `data-date="YYYY-MM-DD"` on the Yesterday heading | the yesterday check, language-independent |
| `/* BRAND:BEGIN */ … /* BRAND:END */` inside `<style>` | the only source of colour, type and radius |
| A stable, dateless `<title>` (`dashboard.title`, or naming `hub.name`) | the artifact keeps its name across republishes |

Hub-local plug-in checks (`dashboard.inputs[].check`) may depend on more markup — a tile
label, an id shape. Read them before renaming anything on the page.

## The graph is disclosed, not controlled

The refresh graphs whatever branch each clone is on. It does not switch, stash or clean —
the working copy belongs to whoever is using it. That makes the graph's *provenance* part
of the page's content, not a precondition for building it:

- Name each graphed branch and the sync time (from `sync-report.md`) on the graph card
  **and** in Known gaps. `check-inputs.py` fails the build if a branch name is missing.
- Say when a worktree was dirty at sync time — the graph then includes uncommitted work.
- Never imply a graph answer describes the integration branch unless the report says so.

## Derived layer: re-derive, never carry forward

- Branch tips, ages, ahead/behind — from the roadmap facts plus a live re-read; the facts
  file can be hours stale relative to a fetch you just ran, and the live read wins. Say
  which one you used when they disagree.
- Task counts — from each feature's task list **as it exists now**. A missing task list
  means there is no denominator; say that rather than reusing the old one.
- Obligation dates — from the goals/plan input's own arrays. Watch for zero-indexed JS months.
- Audit counts — from the audit's own status fields.
- Every T-minus, the cycle day number, and the "yesterday" section — from today's date.

A feature withdrawn and re-scoped on purpose is progress that reads as a regression on
any board counting tasks. Say which it is.

## The timeline

- Scale starts **two days before today** so the "today" rule reads as a line rather than
  the axis edge. With a goals input it ends where the goals' measurement window opens and
  the lanes are its objectives; without one the lanes are the inputs' own dated items
  (feature targets, release dates) and it ends a few days after the last of them.
- Drop any tick within ~4% of today's position and fold it into the today label
  (`today · 3 Sep`) — otherwise the labels collide.
- Cluster markers by **proximity, not equal date**: two obligations one day apart are
  ~2% of the scale and their labels overlap. The `GAP = 4.2` cluster then distributes
  members vertically.
- Clamp marker x to 99% and flip the label leftward above 90%, or the right-edge glyph
  is clipped.
- Status is a **judgement**, applied by the rule printed in the legend — not a field any
  sheet contains. If you change the rule, change the legend.

## Colour

Colour comes from the product's design system and nothing else:

- Status text and marks are the brand's text-safe roles, used as they are:
  `var(--ds-danger-ink)` (critical), `var(--ds-warning-ink)` (at risk),
  `var(--ds-success-ink)` (on track), `var(--ds-info-ink)`. The brand always emits them.
  The page never mixes colours to reach contrast; if a role falls short (under 4.5:1 as
  text or 3:1 as a mark against `--ds-surface`), that is a design-system defect to report,
  not something to patch on the page. Soft fills are tints of the base roles:
  `color-mix(in oklab, var(--ds-danger) 12%, var(--ds-surface))`.
- The primary/accent role is **chrome only** — never a data mark. If it sits close to the
  success role it is indistinguishable from "on track".
- When the design system changes, re-validate the three status roles for colourblind
  separation and contrast in both themes with the `dataviz` palette validator, using the
  resolved values from `<design.build>/tokens.json`:

  ```bash
  node <dataviz-skill>/scripts/validate_palette.js "<danger>,<warning>,<success>" \
    --mode light --surface "<surface>" --pairs all
  ```

  If a role fails, fix it in the design system (or report it), never with a private hex.
- Marks also differ in **shape** (critical diamond, at-risk ring, on-track disc) so
  identity never rests on colour alone, and the table view carries the same data with no
  colour at all.

## Effects and weight

Shadows and washes belong to the brand: `var(--ds-shadow-sm)` on resting cards,
`var(--ds-shadow-md)` on floating things (tooltip, toast, hovered card),
`var(--ds-wash)` for the page background. A marker halo is an `outline`, not a
`box-shadow`. Weights are `var(--ds-weight-regular|strong|bold)` so a brand that embeds
no fonts, or embeds only some weights, never gets a synthesised face.

The decision slab, tooltip and toast are an **inverse panel**:
`color-mix(in oklab, var(--ds-primary-strong) 70%, var(--ds-ink))` with text in
`var(--ds-surface)` — dark on a light page, light on a dark one, from roles alone.

## Theme

The BRAND block defines light values on `:root` and dark values under both
`@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }` and
`:root[data-theme="dark"]`. The page's own CSS declares **no** theme blocks: local custom
properties are defined once on `:root` as `var(--ds-*)` / `color-mix()` expressions and
therefore follow the theme. A colour whose only definition sits behind `[data-theme]`
never applies in the default un-stamped state. `body` sets an explicit token background.

## Verify before claiming done

Run `scripts/render-check.py` (1280 and 390 px, light and dark; FAILs on page errors
and horizontal overflow). Then look at the screenshots and confirm: no page errors, the same obligation count plotted and in the
table, no horizontal overflow at desktop (1280–1440) and phone (390–420) widths, both
themes plus an explicit `data-theme="dark"` stamp, and the state layer round-tripping
(tick → dirty bar names the change → Copy JSON parses → Discard restores).

Playwright's bundled browser revision often lags the installed one, and its CDN may be
unreachable — pass `executablePath` to an installed Chromium build (under the
`ms-playwright` cache) or use `channel: "msedge"` rather than letting it resolve its own.

## Tone

This is an internal planning page. It names missed dates, stalled branches and
unresourced commitments plainly, and it distinguishes "the work is late" from "the work
was withdrawn on purpose". Do not soften a missed date into a status colour, and do not
report a decision as made when nobody recorded it.
