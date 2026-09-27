---
name: "update-product-hub"
description: "Use when the user asks about the product hub or the product dashboard, its HTML page or its published artifact link; when they ask to update, refresh, re-cut or re-run the hub or dashboard; when they ask what to do today, what is most important today, what is at risk, what shipped or landed yesterday, or for a morning or start-of-day product status; and when they want a decision recorded on the dashboard or a saved hub-state file applied back to the repo."
argument-hint: "[refresh | offline | state-only] (default: refresh - fetch, re-graph, re-run producers, rebuild)"
compatibility: "Requires a Product Brain hub (brain.config.json with repos, releases.integration_branch and dashboard keys) with its app repos cloned, git and python3. Styling needs the brand-system skill installed beside this one. Windows/Git Bash safe. Publishing needs the Artifact tool."
metadata:
  author: "product-brain"
user-invocable: true
---

# Update Product Hub

`${CLAUDE_SKILL_DIR}` is this skill's base directory (shown when the skill loads);
substitute it if your shell does not expand it.

Rebuild the hub's dashboard page — the one page that answers "what do I do today, what
is at risk, what happened yesterday" — and republish it to its existing artifact URL.

Everything product-specific comes from the hub, never from this skill:

| `brain.config.json` key | Meaning |
|---|---|
| `dashboard.out` | the page (HTML) |
| `dashboard.state` | the recorded layer (JSON) |
| `dashboard.inputs[]` | `{id, path, produced_by, kind?, check?, max_age_days?}` — every file the page's figures come from (see **Inputs**) |
| `dashboard.title` (optional) | the page's stable `<title>`; otherwise it must name `hub.name` |
| `repos[]`, `releases.integration_branch` | the clones to report on and the branch to count ahead/behind against |
| `graph.out` | where the graph and `sync-report.md` live |

A missing key stops the scripts with the key's name and an example value; invalid JSON
stops them with one line naming the line and column.

### Inputs

| Field | Meaning |
|---|---|
| `id` | short name, used in gate rows and freshness chips |
| `path` | hub-relative file the figures come from |
| `produced_by` | the skill that writes it (`delivery-roadmap`, an audit skill…), or `null` when a person maintains it |
| `kind` (optional) | `"goals"` marks the input that carries dated commitments (OKRs, a plan). Only then does the page render the **Obligations at risk** tile and frame the timeline on the goals' measurement window. Without a goals input the tile is omitted (the gate fails a page that renders it) and the timeline plots the inputs' own dated items |
| `check` (optional) | hub-relative plug-in for product-specific rules (see step 3) |
| `max_age_days` (optional) | age at which the gate complains; default 0 for inputs the refresh re-runs, 7 otherwise |

### The state file

`dashboard.state` has exactly this shape (start a new hub from
`assets/hub-state.template.json`):

```json
{
  "version": 2,
  "updated": "YYYY-MM-DD",
  "focus": { "items": [ { "id": "f1", "status": "open", "closedAt": null, "closedNote": "" } ] },
  "decisions": [ { "id": "d-…", "subject": "…", "question": "…",
                   "options": [ { "id": "a", "label": "…", "body": "…" } ],
                   "choice": null, "decidedAt": null, "note": "" } ],
  "syncLog": [ { "at": "ISO time", "kind": "update-product-hub" } ]
}
```

- `status` is `"open"` or `"done"`; `closedAt` is an ISO time or `null`.
- Other top-level keys (`_readme`, `cycle`) are allowed and ignored.
- One simpler shape is also accepted: `"focus": [ …rows… ]` (a bare list) with `"schema"`
  in place of `"version"`. It carries the same rows, so refusing it would only punish a
  hub for a cosmetic difference; the page reads both and its Save always writes the
  canonical shape back.
- Anything else (focus missing or a string, a row that is not an object, a status other
  than open/done, decisions not a list) is a gate FAIL that prints the expected shape
  next to what was found.

**Two kinds of content live on that page, and they are not interchangeable.**

| Layer | Lives in | Who changes it |
|---|---|---|
| Derived | the page — the `FOCUS` and `ROWS` arrays and the prose | **re-derived every run** from git, the graph and every `dashboard.inputs[]` file |
| Recorded | the `dashboard.state` file | a human, via the page's Save button |

Every defect this kind of page has shipped came from treating a derived number as
durable. A count you copy from the previous build is a lie with a timestamp on it.

**The state file holds no evidence.** Focus rows are `{id, status, closedAt, closedNote}`
and nothing more; their titles, bodies, chips and due labels live in the page's `FOCUS`
array, keyed by the same id. An earlier schema put the evidence in the state file, and
within a day it asserted "neither branch has moved in 8 days" while both had — with the
procedure forbidding anyone to edit it. `check-inputs.py` fails on any extra key.

Decision records are the exception: their prose is the record of what was considered at
the moment of the call, so figures quoted **inside a decision stay frozen on purpose**.
Never refresh them.

## Workflow

Run every command from inside the hub (the scripts walk up to `brain.config.json`;
`--hub <path>` overrides).

**No page yet?** Start from `assets/product-hub-template.html`: copy it to
`dashboard.out`, replace every fictional figure with derived ones (keep ids, class names
and the `ROWS`/`FOCUS` shapes), set the settings block at the top of its script
(`STATE_PATH`, `CALL_ID`, …), embed the state file, and run `brand.py inline`. Drop the
Obligations tile unless an input has `"kind": "goals"`, and drop the decision slab when
no decision is open. Gate the first build with `check-inputs.py --first-build` (assumed
anyway when the page file is missing and git has never tracked it): the missing page is
then a PASS with a note and the page checks are skipped, while inputs, graph and state
are still gated. Once the page exists, gate it without the flag.

### 1. Fetch, then graph whatever is checked out

```bash
python "${CLAUDE_SKILL_DIR}/scripts/fetch-and-report.py"
```

Then re-graph with **the sync command the hub's `CLAUDE.md` documents**. Add no-pull
flags (the Product Brain CLI has `--no-repo-pull --no-hub-pull`) **only if that
`CLAUDE.md` documents them** — the gate fails a page that prints an undocumented
command, and a flag the hub never mentions may not exist in its wrapper. If it documents
none, run the plain sync and say in Known gaps that it may have pulled.

**Never switch branches to make the graph "correct".** An earlier version of this step
forced every clone onto the integration branch, and the refresh then refused to run at
all while someone was mid-test on a feature branch with dev-server proxies pointed at
its review app — a normal working state. Coercion cost more than it bought.

So: fetch for accurate counts, graph the branch that is actually checked out, and
**disclose which branch that is** on the page. The no-pull flags keep the CLI from
touching the clones (it would skip a dirty one silently) and from pulling the hub out
from under uncommitted work.

`fetch-and-report.py` changes nothing — no switch, no stash, no reset, no clean. It
prints each configured clone's branch, HEAD, ahead/behind against
`origin/<releases.integration_branch>`, unpushed count and modified files, and writes
`<graph.out>/.branch-report.json`. Unpushed commits and a dirty worktree are findings to
report, not problems to fix.

### 2. Re-run the producers the page depends on

For each `dashboard.inputs[]` entry whose `produced_by` is `delivery-roadmap`, invoke
the **delivery-roadmap** skill (plugin form: `product-brain:delivery-roadmap`). It
re-fetches, re-derives every feature verdict and rewrites its facts file. Take verdicts,
branch ages and ahead/behind counts from that file — not from the previous dashboard,
and not from task lists or spec status headers, which drift from the code.

Other producers (an audit, a hand-kept goals sheet) are **not** re-run by the refresh;
the gate reports their age and the page discloses it. Run one only when the user asks.

### 3. Gate the inputs

```bash
python "${CLAUDE_SKILL_DIR}/scripts/check-inputs.py"
```

Exit 0 to proceed. Each FAIL names its remedy. If you ship with a FAIL anyway because
the user asked you to, say so in the page's **Known gaps** paragraph and in your reply —
never silently. WARN rows are accepted gaps the page must still disclose.

The gate does **not** fail on which branch the graph covers, how old it is, or a dirty
worktree — those are WARNs. What it *does* fail on is `graph disclosed`: for every
configured repo with a `Built from` row in `sync-report.md`, the page must carry an
element like

```html
<code data-graph-repo="my-api" data-graph-branch="develop" data-graph-built="2026-03-09">develop</code>
```

whose branch and build date match that row and whose text names the branch. A text
search could never fail (`main` is inside "remaining"), so the disclosure is structured.
Disclosure is the contract that replaced coercion, so it is the one that is enforced.
The gate also compares the graph against `fetch-and-report.py`'s snapshot and WARNs when
a clone has since moved to another branch.

Dates the gate reads are ISO: mark the Yesterday heading `data-date="YYYY-MM-DD"`
(English month names are only a fallback), so a page in any language passes.

With no `graph.json` at all it WARNs once (`no graph`) and skips the coverage checks
rather than passing them; the page must then say that no graph backs it.

It also fails when an input the refresh re-runs is not from today, when the embedded
state differs from the file, when the page prints a `pb`/`graphify` command the hub's
`CLAUDE.md` does not document, when a local link is dead, and when `check-brand.py`
reports anything.

**Product rules belong to the hub, not to this skill.** An input may name a hub-local
plug-in, `"check": "<hub-relative .py>"`, run as
`python <check.py> <hub-root> <page-path> <input-path>`; it prints
`PASS|WARN|FAIL name — detail — remedy` lines and **must exit 0** — a non-zero exit or no
result lines is a FAIL and its output is discarded. The path must be a hub-relative
`.py` file that resolves inside the hub; an absolute path or one that escapes the hub is
a FAIL and is never executed. Use one for rules
such as "every obligation date matches the goals sheet" or "the audit tile matches the
audit's own status fields".

### 4. Re-read what the numbers mean before writing any of them

Not optional, and not cacheable between runs:

- **The hub's `CLAUDE.md`** — it documents the commands the page prints. Hubs retire
  recipes mid-cycle; a page once shipped a hand-run graph build the day it was retired.
- **`<graph.out>/sync-report.md`** — which branch and HEAD the graph actually covers.
- **Every `dashboard.inputs[]` file** — dates, key results, verdicts, audit counts.
  Re-derive every date from the source's own arrays, never from the old page. Watch for
  zero-indexed JS months: `[2026, 8, 3]` is **3 September**.
- **The `dashboard.state` file** — the recorded layer. Embed it *verbatim* in the
  page's `<script id="hub-state">`; take each focus row's **status** from it and its
  **content** from the page's `FOCUS` array. Rewriting focus content is expected on
  every run; editing the state file is the human's job, not yours.

### 5. Recompute, restyle, publish

Recompute from today's date: every T-minus, the cycle day, the "yesterday" section (the
real previous day), and each freshness chip. Refresh the brand block (see **Design
system**), re-run the gate, then publish with the **Artifact** tool to the **existing
URL** so shared links keep working:

- same `file_path` (`dashboard.out`) if this conversation published it; otherwise
  recover the artifact's `url` (list or ask) and pass it
- load the **artifact-capabilities** skill before declaring any capability. The Save
  button needs the capability that hands the viewer a file to download. Do **not** add a
  shared-state or database capability: those change who can open the page and where the
  state lives — the state belongs in git.
- `icon`: `dashboard` on a first publish; omit it on a redeploy so the page keeps its icon

Verify before claiming done — render it, then look at it:

```bash
python "${CLAUDE_SKILL_DIR}/scripts/render-check.py"
```

It loads the page at 1280 and 390 px in light and dark and FAILs on page errors or
horizontal overflow, naming the outermost overflowing element. Without the Python
`playwright` package or a launchable browser it prints a WARN that the render was NOT
checked — then check it by hand; never report it as verified. See
`references/rebuild-contract.md` for the invariants that must hold in the HTML itself.

## Design system

The page styles itself **only** through the product's design system, compiled by the
**brand-system** skill into `<design.build>/brand.css`:

- The compiled CSS is inlined between `/* BRAND:BEGIN */` and `/* BRAND:END */` inside
  the page's `<style>` — a published page cannot load local files. Refresh it before
  every publish:

  ```bash
  python "${CLAUDE_SKILL_DIR}/../brand-system/scripts/brand.py" inline "<dashboard.out>"
  ```

- Every colour, font-family and radius in the page's own CSS is a `var(--ds-*)` role.
  Tints are `color-mix(in oklab, var(--ds-x) N%, var(--ds-y))`. No hex/rgb/hsl/oklch
  literal outside the block — in CSS, inline `style`, JS or SVG — and no font named
  directly. Status text and marks are the brand's text-safe roles
  (`--ds-danger-ink`, `--ds-warning-ink`, `--ds-success-ink`, `--ds-info-ink`, always
  emitted), never a private palette.
- Effects are brand-owned: `box-shadow: var(--ds-shadow-sm|md)` and
  `background: var(--ds-wash)`, never a literal shadow or gradient (a brand that forbids
  them leaves those roles at `none` / the canvas). Weights are
  `var(--ds-weight-regular|strong|bold)`, never a number.
- Never mix colours on the page to reach contrast. If a `*-ink` role reads too light,
  that is a design-system defect: report it to the brand-system owner rather than
  patching the page.
- Raw `--ds-color-*` tokens differ per product; the page's own CSS uses role vars only,
  so the same page works under any brand.
- Dark mode comes from the brand block; the page adds no theme blocks of its own.
- `<meta charset="utf-8">` is the first line: the inlined brand block puts hundreds of KB
  of ASCII first, and a browser guessing the encoding from that renders every dash and
  middle dot in the page's scripts as mojibake.
- `check-brand.py` is a gate (the input gate runs it; zero failures is the bar):

  ```bash
  python "${CLAUDE_SKILL_DIR}/../brand-system/scripts/check-brand.py" "<dashboard.out>"
  ```

## Modes

| Argument | Does |
|---|---|
| `refresh` (default) | all five steps |
| `offline` | `fetch-and-report.py --no-fetch`, no graph sync, and **no producer is re-run**: the existing facts files are used as they are and their age is disclosed on the page. Gate with `check-inputs.py --offline`, which turns the stale-input FAIL for re-run producers into a WARN. Every count may be stale — say so in Known gaps |
| `state-only` | applies a state file the user pasted or saved, re-embeds it, republishes. No data refresh, so change nothing derived. |

## Common mistakes

| Mistake | What happened |
|---|---|
| Carrying a task count forward | A page claimed "0 of N tasks" for a task list deleted that morning |
| Quoting a command from the last build | A page printed a graph recipe the hub's `CLAUDE.md` had just retired |
| Trusting a fresh graph | The graph was 19 h old and built from stalled feature branches with a dirty tree |
| Forcing a branch switch | The refresh refused to run mid-review-app-test; disclose the branch instead |
| Letting the embed drift | The embedded state silently diverged from the committed file |
| Reading dates off the old page | Zero-indexed JS months put an item a month early |
| Adding a shared-state capability for ticks | It changed who could open the page; state belongs in git |
| Hand-picking colours | The page drifted from the product; style only through `var(--ds-*)` |
| Disclosing the graph in prose only | "develop" appears on every page, so a text check could not fail; use the `data-graph-*` element |
| Trusting a plug-in's PASS | A plug-in printed PASS and then crashed; only an exit-0 run counts |
| Hardcoding a product rule in the gate | Put it in a hub-local `"check"` plug-in instead |
| Rendering a 0/0 obligations tile | A hub with no goals input got a tile inventing commitments; mark the goals input with `kind` or omit the tile |
| Building a page from scratch | A new hub's first page missed half the structure the gate parses; start from the template |

## Red flags — stop and re-derive

- "The count probably has not changed since yesterday"
- "I can reuse the previous page's T-minus values"
- "The graph was rebuilt recently, so it is current"
- "I will just switch the clones to the integration branch first, it is only a checkout"
- "It is a one-day-old page, I will just bump the date"
- "This one colour is close enough to the brand"

**All of these mean: run the gate and re-derive from source.**
