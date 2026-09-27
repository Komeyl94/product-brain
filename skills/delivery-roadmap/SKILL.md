---
name: "delivery-roadmap"
description: "Use when the user mentions the roadmap, the delivery plan, what has shipped versus what is in flight, a stalled or forgotten branch, whether a feature is really merged or really live, a feature that looks shipped but may have been reverted, or asks to build, update, refresh or re-cut the roadmap — even if they never name the file. Also use for cycle, bet, appetite or hill-chart questions about delivery, and when reconciling delivery against OKRs."
argument-hint: "[refresh | full | releases] (default: refresh — re-verify git state and update the existing roadmap in place)"
compatibility: "Requires a Product Brain hub (brain.config.json with repos, releases and roadmap keys) with every app repo cloned (repos[].path, else workspace.repos_dir/<id>, else repos/<id>); git, python3 and node. Uses the brand-system skill for styling checks. Windows/Git Bash safe."
metadata:
  author: "product-brain"
user-invocable: true
---

# Delivery Roadmap

`${CLAUDE_SKILL_DIR}` is this skill's base directory (shown when the skill loads);
substitute it if your shell does not expand it.

Produce the delivery roadmap: one card per feature with expandable detail, a timeline
whose bars are computed from real dates, a two-tier release note per production release,
and a conflict panel naming what cannot fit.

**Git is the only source of truth for state.** Task lists, spec `Status:` headers and
CHANGELOG files are routinely wrong about what shipped — see
`references/git-verification-recipes.md`. Dates, appetites and hill positions are
judgment and live in the page's `DATA`; everything about *whether code exists and where
it is* comes from a command run this session.

The roadmap is an **internal planning document**. It names missed dates, stalled
branches and unresourced deadlines by name, which is right for the hub and wrong to hand
a client. Client-facing release announcements belong to the `release-notes` skill.

## Configuration

Every product fact comes from the hub's `brain.config.json`. The scripts stop with a
message naming any missing key; never fill one in from memory.

| Key | Used for |
|---|---|
| `repos[]` | the repos to read; a clone is `repos[].path` (hub-relative) if set, else `<workspace.repos_dir>/<id>`, else `repos/<id>` |
| `releases.production_branch` / `integration_branch` | what "released" and "in integration" mean |
| `releases.tag_regex` | a matching tag **is** a production release (always version-sorted) |
| `releases.version_regex` | optional; group 1 is the version label shown. Else a named group `(?P<version>…)` in `tag_regex`, else the whole tag — never an unnamed `tag_regex` group (it may be an alternation) |
| `releases.release_branch_regex` | optional, default `^(release\|hotfix)[-/._]`; classifies merges onto production |
| `releases.merge_style` | `squash` / `merge` / `rebase` — how far ancestry can be trusted |
| `releases.out` | where the `release-notes` skill writes per-release folders |
| `roadmap.out` | the page, e.g. `docs/roadmap/delivery-roadmap.html` |
| `roadmap.facts` | the derived facts file |
| `roadmap.specs_dir` | spec folders, read as *claimed* progress: checkboxes in `tasks.md` if present, else across every `*.md` in the folder |
| `roadmap.framing` | optional vocabulary: `shape-up`, `scrum`, `kanban` or `none` |
| `roadmap.okrs` | optional; reconcile against it only when set |
| `design.build` | compiled brand (`brand.css`, `tokens.json`) from the `brand-system` skill |

Sibling skills are named bare here (`release-notes`, `brand-system`, `artifact-design`); in
the plugin they are `product-brain:<name>`.

### Framing vocabulary

`roadmap.framing` changes words, never structure or checks:

| framing | window | commitment | size | progress |
|---|---|---|---|---|
| `shape-up` | cycle + cooldown | bet | appetite | hill position |
| `scrum` | sprint(s) | sprint goal | estimate | hill position or % |
| `kanban` | planning window | commitment | size class | hill position |
| `none` / unset | window | item | size | hill position |

Switching framing is a **`DATA` change, not a markup change**: set `DATA.framing` to the
config value and the page's label map renders the matching words (window, build/cooldown
segments, size, the bet bar, the unscheduled lane). The `DATA` field names (`cycle`,
`appetite`, `hill`, `barKind: 'bet'`) stay as they are whatever the framing. Never require
a team to adopt a method to get a roadmap.

`DATA.cycle` is **optional**. Set it only when the team really works in a fixed window
(`start`, `buildEnd`, and optionally `cooldownStart`/`cooldownEnd`). Without it the page
derives a *frame* from the earliest `start` to the latest `due` (plus today) and labels it
as a frame derived from dated items, not a commitment.

## Workflow

### 1. Gather git facts — fresh, every repo, every run

```bash
python "${CLAUDE_SKILL_DIR}/scripts/gather-git-facts.py"
```

Fetches every repo in `repos` and writes `roadmap.facts` (derived state — never hand-edit
it). It prints release tags in version order, release merges, integration-vs-production
containment, conventional-commit coverage, reverts on production, claimed task counts per
spec folder, and which active branches have not moved since the previous run. `--no-fetch`
works offline (every count may be stale); `--hub <path>` points at another hub.

The script fails loudly rather than reporting emptiness. A configured branch that does not
exist (a typo such as `mian`) stops it with exit 2 naming the key; a value starting with
`-` is rejected. A failed fetch or git command is printed as `FAIL`, recorded
(`fetched: false`, `errors[]`) and makes the exit code 1 — the facts are then incomplete
and must not be reported as current.

The facts file is what makes **staleness detectable**: it stores each branch's previous
tip. "Nothing has moved in five days" is a finding, and it only exists because the last
run recorded where things were. Stalls are measured against a **baseline** — the most
recent run from an earlier day — which the facts file carries forward, so re-running on
the same day keeps comparing against yesterday instead of against itself. Commit the facts
file alongside the roadmap. When the script says stall detection is OFF (no earlier-day
run, or a repo new to the facts file),
branch movement is *unknown* — do not report a stalled count of zero. Carry the facts'
`stallDetection` into `DATA.stallDetection`; when it is `false` (or a branch has no
previous tip) the page renders movement as unknown instead of "moved N days ago". Carry
the facts' `productionBranch` / `integrationBranch` into `DATA.branches` too: verdict labels
and notes name the configured branches ("In next"), never a hard-coded one.

### 2. Decide a shipped verdict per feature

Follow the decision procedure in `references/git-verification-recipes.md` §"The
shipped-verdict decision procedure". In short: ancestry is a valid **positive** test and,
when `releases.merge_style` is `squash`, an invalid **negative** test. If
`merge-base --is-ancestor` says no, run the content-presence check before concluding
anything, then check for a revert.

Assign exactly one `git.verdict` per feature:

| verdict | meaning |
|---|---|
| `not-started` | no branch, and the signature paths exist nowhere |
| `branch-only` | branch adds real work production lacks |
| `in-develop` | on the integration branch but not yet in a release (verify — integration is sometimes fully contained in production) |
| `released` | content is on the production branch; name the release |
| `superseded` | branch is stale or regressive; production holds the better code |
| `reverted` | merged then reverted; **not live** despite `feat` commits on production |

**When repos disagree**, there is still only one `git.verdict` field. Set it to the claim
most likely to be got wrong by a careless reader, put the other half in `git.evidence`,
and add a `warn` flag stating both states explicitly. The worked case: a feature whose
frontend half was merged and reverted inside one release while its backend half was never
merged at all. `reverted` is the right headline, because the feature's `feat` commits sit
on production and read as shipped to anyone scanning subjects.

Record `git.method` (how you decided) and `git.evidence` (SHAs and the command) for every
feature. A reader must be able to re-run your check. Put anything git cannot see — ops
provisioning, env vars, webhook registration, staging sign-off — in `git.unverifiable[]`.

### 3. Write the release notes section

A production release is a **tag matching `releases.tag_regex`** — nothing else. Merges
onto the production branch are only the route code took; the facts file classifies them
(release merges, direct feature merges, direct commits) but never counts them as releases.
Check the CI config on the production branch for what builds the production image —
commonly a tag rule — so you know whether the tag or the merge ships it. Enumerate
releases from tags; a release-branch merge subject, where one exists, can supply a
readable name. Show the version label (`tagVersion` in the facts). A release's **date is
the tag's date** (`tagDate`: tagger date, else the tagged commit's date) — never parse a
date out of the tag name. Then, per release:

- **`headline`** — one sentence saying what a person can now do. This is the concise note;
  it is always visible. One rule decides it, in order:
  1. if the `release-notes` skill has written a folder for that tag under `releases.out`,
     use **its** headline — read it from `<meta name="release-headline" content="…">` in
     that folder's `client.html` — and point the page at the note: `notesUrl` (the
     published artifact URL, rendered as a link) if one is recorded, else `notes` (the hub
     path, shown as text, because a folder path does not resolve in a published page);
  2. else keep the headline already cached in `DATA.releases[]` — unless that release's
     commit set changed, a human edit must survive a refresh;
  3. else write one.
- **`groups`** — the commit lines, grouped by conventional type where they parse and under
  `Uncategorised` verbatim where they do not. The facts file reports coverage per repo;
  when it is partial, an `Uncategorised` group is normal. Never invent a type for a freeform
  subject.
- **`repos`** — which repos actually shipped. A repo that re-tagged the same commit shipped
  nothing in that release; list only the repos that changed, do not fabricate content.

### 4. Detect and flag conflicts — required, every run

`DATA.conflicts` is a **required slot**. If a run genuinely finds none, emit `[]` and let
the page render its "no conflicts detected" note. The verifier fails on a missing key.

Look for, at minimum:

- **Capacity collisions** — two or more items sharing a due date with one engineer.
- **Stalls** — a branch flagged stalled by step 1 while carrying a near deadline.
- **Unshaped against a hard date** — a due date with no `plan.md` in the feature's spec
  folder (the verifier warns on this). The match is by **prefix**: a feature `id` of
  `042` finds `<roadmap.specs_dir>/042` or `042-<slug>/`; an id that is not the folder's
  prefix is never matched, so name features by their spec folder's id. On the page,
  **Unshaped** counts `hill < 0.45`; the verifier prints the same count and warns when a
  dated feature has no plan but a hill that claims it is shaped.
- **Overlapping build windows** — two commitments whose `start`/`due` ranges intersect.
- **Phantom completion** — a fully ticked task list against a `not-started` or
  `branch-only` verdict. The verifier warns on this; put it on the card. Ticks are
  *claimed* everywhere they appear — the scoreboard tile reads "Tasks ticked (claimed)".
- **Shared blockers** — several features waiting on one ops action.

State the collision plainly. A shared deadline is not a resourced plan, and a roadmap
that will not say so lets dates slip silently.

### 5. OKR reconciliation — only when `roadmap.okrs` is set

Read the file it names and map each dated commitment to the key result it serves. Flag a
key result with no feature behind it and a scheduled feature with no key result. If the key
is unset, skip this step and do not mention OKRs on the page.

### 6. Render

Update `roadmap.out` in place if it exists; otherwise copy
`assets/roadmap-template.html` to `roadmap.out`, whose `DATA` is a **worked example for a
fictional product that must be regenerated, not reused**. The template ships with an
**empty** BRAND block (it carries no product's brand); run `brand.py inline` on the copy
before anything else.

Edit only `DATA` — the JS computes every bar position, tick, tile and section count from
it. Do **not** hand-write a percentage or a count anywhere; that is the bug this
architecture exists to prevent, and the verifier rejects hand-typed `left`/`width`
percentages in markup. Load the `artifact-design` skill before making design changes
beyond `DATA`.

### 7. Verify before publishing

```bash
python "${CLAUDE_SKILL_DIR}/scripts/verify-roadmap.py" <roadmap.out>
```

`--self-test` runs its parser and check edge cases against `fixtures/`. It checks enums,
ISO dates, `start`/`due` ordering, lane-vs-verdict contradictions,
required evidence, release tags against `releases.tag_regex`, unshaped dated work, and the
presence of the conflicts key — then prints the tallies — and finally runs the
`brand-system` skill's `check-brand.py` on the same file. A brand failure fails the verify.
**Take every count you report from this output, never from prose or memory.**

### 8. Publish and report

- The tracked HTML file is the source of truth.
- Publish as an Artifact. If a roadmap artifact already exists, republish to the **same
  URL** with a dated version `label`; never fork a new URL for a refresh.
- Report: the verifier's tallies, what changed since the last run (diff the previous
  `DATA` and the facts file), every conflict flagged, and any verdict that changed —
  especially a feature that turned out already shipped, or shipped-then-reverted.

## Design system

The page follows the product's design system, compiled by the `brand-system` skill into
`<design.build>/brand.css`.

- The page styles itself **only** through the inlined BRAND block: the compiled CSS sits
  between `/* BRAND:BEGIN */` and `/* BRAND:END */` inside the page's `<style>` (a
  published artifact cannot load local files). Everything outside the block uses
  `var(--ds-*)` roles; derived tints are `color-mix(in oklab, var(--ds-x) N%, var(--ds-y))`.
  No hex, `rgb()`, `hsl()` or `oklch()` literal, no named font face, no separate chart
  palette — lanes, verdicts and bars map onto the success / warning / info / danger /
  muted roles. **Text and numbers** use the text-safe `--ds-success-ink`,
  `--ds-warning-ink`, `--ds-danger-ink`, `--ds-info-ink`; the base roles are for fills,
  rails, bars and marks only. Never mix colours to reach contrast.
- Effects are brand-owned: elevation is `var(--ds-shadow-sm|md)`, the page background is
  `var(--ds-wash)`, weights are `var(--ds-weight-regular|strong|bold)`. A brand that
  forbids shadows or gradients leaves those at `none` / the canvas colour, so the page
  follows it without edits. Never write a literal shadow, gradient or numeric weight.
- Dark mode comes from the brand's dark roles, not from a second palette in the page.
- Before publishing, refresh the block from the current build:

  ```bash
  python "${CLAUDE_SKILL_DIR}/../brand-system/scripts/brand.py" inline <roadmap.out>
  ```

- `check-brand.py` runs inside step 7. If it fails on a stale block, re-run `brand.py
  inline`; if it names a literal colour or font, fix the page's CSS, never the tokens.
- Prose is scanned too: a `#123`-style issue reference in `DATA` reads as a hex colour.
  Prefer "PR 123" / "issue 123" in new prose. If an existing reference must stay verbatim,
  pass it explicitly with `verify-roadmap.py --allow-literal '#123'` (it is forwarded to
  `check-brand.py` and printed in its tally), and say so in your report.
- Never edit the template's BRAND block by hand, and never commit a filled block into the
  skill's own `assets/` — the skill folder must stay free of any one product's brand.

## Accuracy rules (learned the hard way)

- **A task list is an intention; a merge commit is a fact.** A spec has shown ~90% of its
  tasks ticked with zero code in any repo, and others 100% ticked while absent from
  production. Report ticks as *claimed*, always beside a verdict.
- **Never let ancestry alone produce a negative.** When `releases.merge_style` is
  `squash`, ancestry negatives lie. A previous roadmap wrongly reported an already-shipped
  story as pending for exactly this reason.
- **Sort tags with `--sort=v:refname`.** Default sort is alphabetic and puts `…1.0.9`
  after `…1.0.16`, which mis-attributes releases. Only tags matching
  `releases.tag_regex` are releases.
- **Every ref is `origin/<name>`.** Bare names fail with "Not a valid object name", and a
  swallowed error reads as "not merged".
- **Check for reverts before calling anything live.** A feature has been merged and
  reverted with both commits inside one release.
- **"Ahead of integration" is a size signal, not a merit signal.** Read the diff; a branch
  can be ahead and still regressive.
- **Re-measure the integration branch against production each run** rather than assuming
  a backlog exists, or that none does.
- **A tag proves a build, not a deployment.** Deployment lives outside the repo.
- **Search by signature path, not by branch name or topic word.** Work lands on
  generically named branches, and topic keywords match unrelated shipped work.
- If the hub has a knowledge graph, check its freshness per the hub's `CLAUDE.md` and
  prefer graph queries over blind grep when hunting for a feature's signature paths.
