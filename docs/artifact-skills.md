# Artifact skills

Four skills that turn a hub's knowledge into generated documents: the brand design system, the
delivery roadmap, release notes, and the product dashboard. They ship in the Product Brain plugin
(`skills/<name>/`), work in **any** hub, and read every product-specific fact from
`brain.config.json` — never a hardcoded default. A missing config key is a clear error naming the
key and an example value, not a silent fallback.

| Skill | Produces | Reads (`brain.config.json` key) |
|---|---|---|
| `brand-system` | The hub's `DESIGN.md`, plus compiled `brand/brand.css` + `brand/tokens.json` | `design` |
| `delivery-roadmap` | A git-grounded delivery roadmap (HTML) and its facts JSON | `roadmap` |
| `release-notes` | Per-release client + internal notes (client HTML/PDF, internal Markdown) | `releases` |
| `update-product-hub` | The product dashboard (HTML) and its state JSON | `dashboard` |

All four are invoked as `product-brain:<name>` once the plugin is installed (see
[Migrating from hub-local copies](#migrating-from-hub-local-copies) below).

---

## The brand pipeline

Every artifact these skills generate must be styled from the **one** product-level design system,
never invented per-document. The pipeline:

1. **`DESIGN.md`** (hub root) — the brand tokens (colour ramps, semantic colours, type, shape,
   spacing), plus an `artifact` role mapping (light + dark) every generated document uses, and a
   `provenance` block recording which repo/ref/path each token group was lifted from. Written by
   `brand-system`'s `brand.py extract`, reviewed by a human, never hand-invented and never sampled
   from a screenshot. A hub with no frontend repo to extract from writes `DESIGN.md` by hand instead
   (see `examples/todo-app/DESIGN.md`).
2. **`brand.py build`** compiles `DESIGN.md` into `<design.build>/brand.css` and
   `<design.build>/tokens.json` (resolved values + a hash of `DESIGN.md` + the source ref/commit,
   so staleness is detectable).
3. **Inlining** — every artifact template inlines `brand.css` between `/* BRAND:BEGIN */` /
   `/* BRAND:END */` markers inside a `<style>` block (published artifacts can't load local files).
   Every colour, font-family and radius in the template's own CSS is `var(--ds-*)`; derived tints
   are `color-mix(in oklab, var(--ds-x) N%, var(--ds-y))`. No literal hex/rgb/hsl/oklch or named
   font-family outside that block.
4. **`check-brand.py`** fails an artifact with a missing/stale `BRAND` block, a colour literal
   outside it, a font-family that isn't a `var(--ds-font-*)`, or a font-weight that isn't embedded.
   It runs in the verify step of every artifact skill — zero failures is the bar for publishing.
   This is what the constitution's "Brand design system" principle enforces.

---

## `brain.config.json` keys

### `design` (read by `brand-system`)

| Key | Required? | Default | Example |
|---|---|---|---|
| `system` | Yes | — | `"DESIGN.md"` |
| `build` | Yes | — | `"brand"` |
| `source.repo` / `source.ref` | Only if extracting from a frontend repo (omit for a hand-authored `DESIGN.md`) | — | `{ "repo": "web-app", "ref": "origin/main" }` |
| `sources` | Only with `source` | — | `["src/styles/tokens.css", "src/design/colors.ts"]` |
| `fonts` | Optional (needed for embedded PDF fonts) | — | `{ "Inter": { "400": "src/assets/fonts/Inter-Regular.woff2" } }` |

`source` is read with `git show <ref>:<path>` — never the working checkout — so extraction is
reproducible regardless of what's checked out locally.

### `releases` (read by `release-notes`)

| Key | Required? | Default | Example |
|---|---|---|---|
| `tag_regex` | Yes | — | `"^v\\d+\\.\\d+\\.\\d+$"` — a matching tag **is** a production release |
| `primary_repo` | Yes | — | `"backend-api"` |
| `production_branch` | Yes | — | `"main"` |
| `integration_branch` | Yes | — | `"develop"` |
| `merge_style` | Yes | — | `"squash"` — `squash\|merge\|rebase`; squash makes plain ancestry checks lie, so the skill verifies content, not ancestry |
| `out` | Yes | — | `"docs/releases"` |
| `client_note.locale` / `.dir` | Yes | — | `{ "locale": "en", "dir": "ltr" }` |
| `client_note.calendar` | Optional | Gregorian | `"jalali"` |
| `client_note.i18n` / `.i18n_source` | Optional (only if client copy is translated from app i18n files) | — | `[{ "repo": "web-app", "path": "src/assets/i18n/fa.json" }]` |
| `internal_note.locale` | Yes | — | `{ "locale": "en" }` |
| `tests` | Yes (one entry per repo whose suite gates the release) | — | `{ "backend-api": "./vendor/bin/phpunit" }` |
| `capture` | Optional (only if release notes screenshot the app) | — | `{ "repo": "web-app", "apps": { "web-app": { "serve": "npm start", "base_url": "http://localhost:4200" } } }` |

### `roadmap` (read by `delivery-roadmap`)

| Key | Required? | Default | Example |
|---|---|---|---|
| `out` | Yes | — | `"docs/roadmap/delivery-roadmap.html"` |
| `facts` | Yes | — | `"docs/roadmap/.roadmap-facts.json"` |
| `specs_dir` | Yes | — | `"specs"` |
| `framing` | Optional | `"none"` | `"shape-up"` — `shape-up\|scrum\|kanban\|none`; vocabulary only, never a required methodology |
| `okrs` | Optional | — | `"docs/okrs/tracker.html"` |

### `dashboard` (read by `update-product-hub`)

| Key | Required? | Default | Example |
|---|---|---|---|
| `out` | Yes | — | `"docs/dashboard/product-hub.html"` |
| `state` | Yes | — | `"docs/dashboard/hub-state.json"` |
| `inputs` | Optional (one entry per upstream artifact the dashboard folds in) | `[]` | `[{ "id": "roadmap", "path": "docs/roadmap/.roadmap-facts.json", "produced_by": "delivery-roadmap" }]` |

Workers and the skills themselves never edit `brain.config.json` — a missing or wrong key is
reported to the user, who edits it (or asks Claude to).

---

## Migrating from hub-local copies

Development on these four skills can start as hub-local copies under
`.claude/skills/<name>/` while they're being written or customized for one team. Once the plugin
ships the same skill under `skills/<name>/`, migrate:

1. Confirm the Product Brain plugin is installed and up to date (`/plugin marketplace update
   product-brain`, `/reload-plugins`), and that `product-brain:<name>` responds for each of the
   four skills.
2. Delete the hub-local copy: `rm -rf .claude/skills/<name>` for each of `brand-system`,
   `delivery-roadmap`, `release-notes`, `update-product-hub`. The plugin version takes over —
   there is never a copy in both places, to avoid the two drifting apart.
3. Plugin skills are namespaced `product-brain:<name>` (e.g. `product-brain:brand-system`) —
   update any doc or memory that referenced the unqualified name.
4. **Hub-specific rules belong in the hub, not in a forked skill.** If the hub-local copy grew
   team-specific wording (a house style for release notes, an extra roadmap section), move that
   into the hub's `CLAUDE.md` or `constitution.md` instead of re-forking the skill — the shared
   skill stays generic and upgradeable; the hub layers its own rules on top by reading them from
   `brain.config.json` and the hub's own docs.
