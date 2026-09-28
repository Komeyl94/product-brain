# Git verification recipes and traps

Every trap below was hit in practice on a real product and produced a wrong roadmap claim
before it was caught. The recipes are the corrections.

Placeholders, all read from the hub's `brain.config.json`:

| Placeholder | Config key | Meaning |
|---|---|---|
| `<repo>` | `repos[].id` | the clone at `repos/<repo>` |
| `<production>` | `releases.production_branch` | the branch releases merge into |
| `<integration>` | `releases.integration_branch` | the branch feature work merges into first |
| `<tag>` | `releases.tag_regex` | a tag matching the regex **is** a production release |
| — | `releases.merge_style` | `squash`, `merge` or `rebase`; decides how far ancestry can be trusted |
| `<specs>` | `roadmap.specs_dir` | spec folders (`<specs>/<id>-<slug>/`) |

---

## The shipped-verdict decision procedure

Run this per feature. Do not shortcut it.

### Step 0 — establish the feature's signature

You cannot verify a feature without knowing what artefacts it introduces. Get the
signature from, in order of preference:

1. The branch diff against the integration branch:
   `git -C repos/<repo> diff origin/<integration>...origin/<branch> --stat`
2. `<specs>/<id>-*/plan.md` or `data-model.md` (named classes, actions, migrations)
3. `<specs>/<id>-*/tasks.md` task text (file paths appear inline)

A signature is 2–5 concrete paths or symbols — a new action class, a new enum, a new
migration — not topic words.

**Step 0b — MANDATORY: search by path, not by branch name.** All three sources above
presuppose a branch named for the spec. Work frequently lives on a branch named for
something else entirely, so "no `<id>-*` branch exists" proves nothing:

```bash
# Where has this path ever lived, on ANY ref?
git -C repos/<repo> log --all --oneline --diff-filter=A -- '<signature path glob>'
# Which branches contain that commit?
git -C repos/<repo> branch -r --contains <sha>
```

The pattern: a feature has no branch named for its spec or its topic in any repo, yet
dozens of its files and their tests live on a generically named `chore/<ticket>` branch,
bundled into one catch-all commit alongside unrelated changes. Skipping this step returns
`not-started` — the exact inverse of the truth.

Features with no branch and no matching paths anywhere are `not-started` — but only after
step 0b, and see the **keyword false-positive** trap before concluding that from a keyword
search alone.

### Step 1 — positive ancestry test

```bash
git -C repos/<repo> merge-base --is-ancestor <sha> origin/<production> && echo SHIPPED
```

**If this returns true, the feature shipped. This test is trustworthy in the positive
direction and you can stop.**

### Step 2 — if ancestry is false, DO NOT conclude "unshipped"

Ancestry is a **valid positive test and an invalid negative test** whenever
`releases.merge_style` is `squash` (and after any rebase or cherry-pick). A squashed commit
reaches `<production>` under a new SHA, so the original commit is correctly reported as
"not an ancestor" while its content is live. Even with `merge_style: merge`, one squashed
hotfix is enough to break the rule, so run this step whenever ancestry says no.

Run content presence instead:

```bash
# Empty output means production already has the branch's version of these files.
git -C repos/<repo> diff origin/<production> origin/<branch> -- <signature paths>
```

Interpretation:
- **Empty diff** → the content is on `<production>`. The feature shipped (squashed). Verdict `released`.
- **Diff shows the branch ADDING things production lacks** → genuinely unshipped work. Verdict `branch-only`.
- **Diff shows the branch DELETING or REVERTING things production has** → the branch is stale or
  regressive and `<production>` is ahead of it. Verdict `superseded`. Do not describe this as
  "pending merge"; merging it would regress production.

Confirm with a symbol count on production directly:

```bash
git -C repos/<repo> grep -c "<symbol>" origin/<production> -- <path>
```

### Step 3 — check for a revert before declaring victory

A feature can be merged and then reverted, with **both the merge and the revert inside the
same release**. Commit subjects then advertise a feature that never ran in production.

```bash
git -C repos/<repo> log origin/<production> -i --grep="revert" --oneline | head -20
git -C repos/<repo> log --all -i --grep="revert.*<feature-slug>" --oneline
```

If a revert exists, verdict is `reverted` and the feature is NOT live regardless of the
`feat(...)` commits sitting on `<production>`.

### Step 4 — attribute the release

Walk release tags **in version order** and find the first one containing the commit:

```bash
git -C repos/<repo> tag --sort=v:refname            # MANDATORY sort — see trap below
git -C repos/<repo> tag --contains <sha> --sort=v:refname | head -1
```

Keep only tags matching `releases.tag_regex`; anything else (a test tag, a marker) is not a
production release.

---

## Traps

### 1. Ancestry false negatives under squash merges

The pattern: a small feature commit is **not** an ancestor of `origin/<production>`, yet
the file it touched is byte-identical on production and on the branch, and production's
copy carries the new code. The work reached production squashed inside a later commit.
Concluding "unmerged" from ancestry alone produces a false pending item.

In the same repo, other commits **were** ancestors of production. Both behaviours coexist;
you cannot tell which applies without the content check.

### 2. Tag sorting is alphabetic by default

```
git tag                  → ... v1.0.7  v1.0.8  v1.0.9      (v1.0.9 sorts LAST)
git tag --sort=v:refname → ... v1.0.14 v1.0.15 v1.0.16
```

Reading the first line of an unsorted `git tag --contains` attributed a feature three
releases later than reality. **Always pass `--sort=v:refname`**, whatever the tag scheme.

### 3. Bare branch names do not resolve

Fresh clones have no local tracking branches. `git log my-feature-branch` fails:

```
fatal: Not a valid object name my-feature-branch
```

**Every ref must be `origin/<name>`.** The failure mode is dangerous because a script that
ignores stderr reads the error as "not merged".

### 4. Git Bash on Windows mangles `rev:path`

Git Bash (MSYS) rewrites any argument that looks like a POSIX path list before git sees
it. `origin/<production>:.ci-config.yml` has a `/` and a `:`, so it is converted to
`origin\<production>;.ci-config.yml` and git fails with
`fatal: ambiguous argument 'origin\<production>;.ci-config.yml': unknown revision`.

Read a file at a ref with either of these (both verified in Git Bash):

```bash
MSYS_NO_PATHCONV=1 git -C repos/<repo> show origin/<production>:<path>
git -C repos/<repo> show 'origin/<production>:./<path>'      # ./ stops the conversion
```

**Do not** "fix" it with `git show origin/<production> -- <path>`. That is a different
command: it prints the tip *commit* of the branch and its diff restricted to `<path>` —
usually nothing at all for a config file that did not change in that commit. Read as the
file's contents, it looks like "the CI config has no tag rule", which is exactly the wrong
conclusion. For a search, `git grep <pattern> origin/<production> -- <path>` is fine: there
the `--` separates a pathspec from a tree, and no `rev:path` argument is involved.

### 5. `tasks.md` is an intention, never evidence

Seen in practice, as dated snapshots rather than rules about any one spec:

- A spec showed roughly 90% of its tasks ticked, gate runs included, with **zero code in
  any repo** and a branch that had never held a commit. It was built for real a week later.
  The ticks were premature rather than false — but they were not evidence.
- Two other specs sat at 100% ticked while still absent from production.

Report task counts as *claimed* progress, always beside a git verdict. Never let a tick
set a lane. `gather-git-facts.py` records claimed counts per spec folder so a fully ticked
list against a `not-started`/`branch-only` verdict is easy to spot.

### 6. Spec `Status:` headers are stale

Expect most specs to read `Draft` regardless of state, including features live on
production. Ignore the field entirely.

### 7. Keyword searches produce false positives

The pattern: a large release in one topic area ships while a separate, unstarted spec in
the same topic area sits untouched. Grepping the topic word makes the unstarted spec look
started. Always confirm against the feature's *signature paths*, not its topic
vocabulary.

### 8. The same change can exist under two SHAs with different patch-ids

The pattern: one change exists once on an unmerged branch and once, re-authored, on
production. An open branch that looks like unshipped work may be entirely stale.

### 9. Single-repo releases show as duplicate tags

When a release ships from one repo only, the other repo often tags the *same commit*
again. Detect it (the facts file lists `tagsSharingACommit`) and set `repos` to the repos
that actually changed rather than inventing content for the idle one.

```bash
git -C repos/<repo> rev-list -n1 <tag-N>
git -C repos/<repo> rev-list -n1 <tag-N+1>   # same SHA → this repo shipped nothing new
```

### 10. `CHANGELOG.md` is not a release source

A hand-maintained changelog tends to carry a lone `## [Unreleased]` heading with no version
sections, still listing fixes as unreleased long after they shipped. Derive releases from
tags and merges only.

### 11. Verify the integration→production relationship; do not assume it

At one point `git rev-list --count origin/<production>..origin/<integration>` returned 0 in
every repo — no merged-but-unreleased backlog. Weeks later the integration branch was
dozens of commits ahead. That is a property of a moment, not a law. Re-measure every run:

```bash
git -C repos/<repo> rev-list --left-right --count origin/<production>...origin/<integration>
```

### 12. "Ahead of integration" does not mean "has value to merge"

A branch read as ahead of the integration branch, but its remaining delta against
production renamed a comparison to the wrong field and deleted reset logic — production
held the better code. Ahead-count is a size signal, never a merit signal. Read the diff
before calling a branch mergeable.

### 13. Ops and infrastructure are invisible to git

Server provisioning, environment variables, registration with a third-party service,
staging sign-off. These can never be verified from a clone. Put them in
`git.unverifiable[]` and label them as such on the page. A tag proves a build was produced,
not that anything was deployed.

---

## Release extraction

### Releases are tags. Merges are only how code reached production.

A production release is a tag matching `releases.tag_regex`. Nothing else defines one — not
a release branch, not a merge, not a CHANGELOG heading. Merges into `<production>` only
describe the *route* code took, and products differ wildly here: some merge release
branches, some merge the integration branch, some merge feature branches straight into
production, some push directly.

Read the CI config on `origin/<production>` (with `MSYS_NO_PATHCONV=1 git show
origin/<production>:<path>` — see trap 4; never `show <ref> -- <path>`) to find
what builds the production image. It is commonly gated on a tag rule such as:

```yaml
  rules:
    - if: $CI_COMMIT_TAG          # GitLab; GitHub uses on: push: tags
```

If so, **a tag builds the production image; the merge does not.** Treat the tag as the
release identity, and show its version label (`releases.version_regex`, else the tag).

Release **dates** come from the tag — tagger date for an annotated tag, else the tagged
commit's date (`gather-git-facts.py` records both as `tagDate`). Never parse a date out of
a tag name, even one that looks like `release-2026.09.1`: tags get cut days after the name
was chosen, and re-cut.

Caveat that must appear on the page: a tag proves an image was **built**, not that anything
was **deployed**. Deployment state lives in the CI system and on the servers, not in the clone.

### Routes onto production — classified, not counted as releases

```bash
git -C repos/<repo> log origin/<production> --merges --first-parent     --format='%h|%ad|%s' --date=short
```

`gather-git-facts.py` sorts these first-parent commits into:

| field | what it is |
|---|---|
| `releaseMerges` | from a branch matching `releases.release_branch_regex` (default `^(release\|hotfix)[-/._]`) or from `<integration>` |
| `featureMerges` | any other branch merged straight into production — worth a look: it skipped integration |
| `fastForwardedMerges` | merges *into another branch* (subject says `into '<integration>'`) that sit on production's first-parent chain because production was fast-forwarded |
| `directCommits` | first-parent non-merge commits: direct pushes — or, when `merge_style` is `squash`, squashed merge requests, which look identical |

Match the merge subject generally (`Merge branch '<x>' into <production>`, quoted or not;
git omits `into` when merging into the default branch). When several repos use the same
release-branch names, the release-branch *name* is a convenient human label and cross-repo
join key — but tags remain the record, and a release may have no release-branch merge at
all. Tolerate a release existing in one repo only.

Contents of a release, per repo:

```bash
git -C repos/<repo> log <prev-tag>..<tag> --no-merges --format='%h|%ad|%s' --date=short
```

Validate the partition: the per-release commit counts must sum to
`git log origin/<production> --no-merges --oneline | wc -l`. A mismatch means a gap or
double-count.

### Conventional-commit coverage is partial — measure, don't assume

`gather-git-facts.py` samples the last 60 subjects on production per repo. Expect anything
from a quarter to a half of subjects to be freeform (`Show the new field in the list
view`, `Chore/ticket 671`). So:

- Group what parses by `type(scope)`.
- Put the rest under `Uncategorised` **verbatim**. Do not invent a type for them.
- The one-sentence `headline` says what a person can now do. It is decided by one rule
  (SKILL.md step 3): the `release-notes` folder's headline for that tag wins; else the
  headline cached in `DATA.releases[].headline` (kept unless the release's commit set
  changed, so a human edit survives); else you write one.
