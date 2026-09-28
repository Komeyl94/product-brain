# Internal release note — REPLACE-TAG

> Audience: the REPLACE-PRODUCT engineering team. Written in the internal-note
> locale only. This note names what broke, what is untested and what could not be
> verified. It is not client-safe and is not published as an Artifact.

- **Released:** REPLACE-DATE
- **Repos that shipped:** REPLACE — from `facts.reposShipping`; a repo that only re-tagged shipped nothing
- **Range:** REPLACE-RANGES
- **Client note:** [client.html](client.html) · PDF `client.pdf`
- **Facts:** [facts.json](facts.json) — derived, never hand-edited

## 1. Technical changes

One row per change a maintainer would need to find later. `Evidence` is a SHA, a
path, or a path:line — a reader must be able to jump straight to it.

| Change | Area | Repo | Evidence |
|---|---|---|---|
| REPLACE | REPLACE (from `files.byArea`) | REPLACE | `REPLACE-sha` `path/to/file` |

Uncategorised commits (conventional-commit coverage is partial — REPLACE% per repo,
from `facts.repos[].conventionalCoverage`) are listed verbatim rather than assigned
a type they never had:

- `REPLACE-sha` REPLACE-subject

## 2. Risks

**Required.** If a run genuinely finds none, write `None found` *and name the
check that produced that answer* — an empty Risks section is indistinguishable
from an unexamined one.

| Risk | Trigger | Blast radius | Mitigation / rollback |
|---|---|---|---|
| REPLACE | REPLACE | REPLACE | REPLACE |

Always consider, and state the verdict for each:

- **Schema migrations** — REPLACE (count from `files.byArea['schema-migration']`). A migration makes rollback non-trivial; say whether a down/rollback path exists and was run.
- **Reverts in range** — REPLACE. A reverted change is *not live* even though its `feat` commit is on the production branch.
- **Breaking changes** — REPLACE (from `facts.repos[].breaking`).
- **Config / env** — REPLACE. New keys must be set in the target environment before the build is promoted, or the release fails on start.
- **Cross-repo coupling** — REPLACE. If one repo shipped and another did not, say what the mismatch does to a live user.

## 3. Test coverage

State the command you ran and its output. A test file appearing in the diff is
evidence a test was *written*, not that it *passes*. The commands come from
`releases.tests`.

| Suite | Command | Result | Notes |
|---|---|---|---|
REPLACE-TEST-ROWS

- **Test files touched in this range:** REPLACE (from `files.byArea['tests']`).
- **Changes shipped with no accompanying test:** REPLACE — name them. This is the
  line most worth writing; it is the one nobody volunteers later.
- **Known baseline failures** (failures that predate this release and are not
  regressions): REPLACE.

## 4. Build and release process

- **Pipeline:** REPLACE — how a release tag becomes a production build, and where
  that pipeline is defined.
- **What makes it production:** a tag matching `REPLACE-TAG-REGEX` on
  `REPLACE-PRODUCTION-BRANCH`. A merge to `REPLACE-PRODUCTION-BRANCH` only makes the
  code reachable — it does not ship it.
- **Artifacts:** REPLACE — which images or bundles the pipeline produced, and where
  they were pushed.
- **Deploy verification:** REPLACE — a tag proves a build, not a deployment. Say
  who confirmed the running version, and how.
- **Migrations run on deploy:** REPLACE (yes/no, and by which step).

## 5. Document citations

Every claim above that came from a written source is cited here. Link, do not
summarise — a stale summary in this section is worse than no section.

| Claim | Source |
|---|---|
| REPLACE | [spec](REPLACE-SPECS-LINK) |
| REPLACE | [decision record](REPLACE-path-to-the-decision-record) |
| REPLACE | [delivery roadmap](REPLACE-ROADMAP-LINK) |

- **Specs cited by commits in this range:** REPLACE (from `facts.specsCited`; `ticks` is the
  claimed task count - `tasks.md` if the folder has one, else every `*.md` in it. Claimed
  ticks are not a shipped verdict).
- **Specs with a shipped verdict that this release changes:** REPLACE — if a spec
  moved to released, the roadmap needs re-cutting; say so here and run the
  `delivery-roadmap` skill.
- **Unverifiable by git** — ops provisioning, env vars, webhook registration,
  staging sign-off: REPLACE.
