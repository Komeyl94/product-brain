<!--
  REGRESSION FIXTURE. Not a real note. This is internal-note-template.md as
  scaffold-note.py writes it, with every remaining slot set to "none".
  The template's own bullets carry backticks, paths and example links, so an
  omission check that reads the whole section is satisfied by the template's
  prose and passes this file. It must FAIL on: technical changes, risks, the
  test-coverage Result, the untested-changes line, build and release, and
  citations - one line each.

  Run after ANY change to verify-release-notes.py:
    python "${CLAUDE_SKILL_DIR}/scripts/verify-release-notes.py" \
      "${CLAUDE_SKILL_DIR}/fixtures/hollow-internal-note.md"
  Expected: FAIL. A pass means the verifier reads the template, not the author.
-->
# Internal release note — v1.5.0

> Audience: the Example engineering team. Written in the internal-note
> locale only. This note names what broke, what is untested and what could not be
> verified. It is not client-safe and is not published as an Artifact.

- **Released:** 9 September 2026
- **Repos that shipped:** none — from `facts.reposShipping`; a repo that only re-tagged shipped nothing
- **Range:** `example-api v1.4.0..v1.5.0`, `example-web v1.4.0..v1.5.0`
- **Client note:** [client.html](client.html) · PDF `client.pdf`
- **Facts:** [facts.json](facts.json) — derived, never hand-edited

## 1. Technical changes

One row per change a maintainer would need to find later. `Evidence` is a SHA, a
path, or a path:line — a reader must be able to jump straight to it.

| Change | Area | Repo | Evidence |
|---|---|---|---|
| none | none (from `files.byArea`) | none | `none` `path/to/file` |

Uncategorised commits (conventional-commit coverage is partial — none% per repo,
from `facts.repos[].conventionalCoverage`) are listed verbatim rather than assigned
a type they never had:

- `none` none

## 2. Risks

**Required.** If a run genuinely finds none, write `None found` *and name the
check that produced that answer* — an empty Risks section is indistinguishable
from an unexamined one.

| Risk | Trigger | Blast radius | Mitigation / rollback |
|---|---|---|---|
| none | none | none | none |

Always consider, and state the verdict for each:

- **Schema migrations** — none (count from `files.byArea['schema-migration']`). A migration makes rollback non-trivial; say whether a down/rollback path exists and was run.
- **Reverts in range** — none. A reverted change is *not live* even though its `feat` commit is on the production branch.
- **Breaking changes** — none (from `facts.repos[].breaking`).
- **Config / env** — none. New keys must be set in the target environment before the build is promoted, or the release fails on start.
- **Cross-repo coupling** — none. If one repo shipped and another did not, say what the mismatch does to a live user.

## 3. Test coverage

State the command you ran and its output. A test file appearing in the diff is
evidence a test was *written*, not that it *passes*. The commands come from
`releases.tests`.

| Suite | Command | Result | Notes |
|---|---|---|---|
| example-api | `make test` | none | none |
| example-web | `npm test` | none | none |

- **Test files touched in this range:** none (from `files.byArea['tests']`).
- **Changes shipped with no accompanying test:** none — name them. This is the
  line most worth writing; it is the one nobody volunteers later.
- **Known baseline failures** (failures that predate this release and are not
  regressions): none.

## 4. Build and release process

- **Pipeline:** none — how a release tag becomes a production build, and where
  that pipeline is defined.
- **What makes it production:** a tag matching `^v\d+\.\d+\.\d+$` on
  `main`. A merge to `main` only makes the
  code reachable — it does not ship it.
- **Artifacts:** none — which images or bundles the pipeline produced, and where
  they were pushed.
- **Deploy verification:** none — a tag proves a build, not a deployment. Say
  who confirmed the running version, and how.
- **Migrations run on deploy:** none (yes/no, and by which step).

## 5. Document citations

Every claim above that came from a written source is cited here. Link, do not
summarise — a stale summary in this section is worse than no section.

| Claim | Source |
|---|---|
| none | [spec](../../../specs/NNN-slug/spec.md) |
| none | [decision record](none) |
| none | [delivery roadmap](../../../docs/roadmap/delivery-roadmap.html) |

- **Specs cited by commits in this range:** none (from `facts.specsCited`; `ticks` is the
  claimed task count - `tasks.md` if the folder has one, else every `*.md` in it. Claimed
  ticks are not a shipped verdict).
- **Specs with a shipped verdict that this release changes:** none — if a spec
  moved to released, the roadmap needs re-cutting; say so here and run the
  `delivery-roadmap` skill.
- **Unverifiable by git** — ops provisioning, env vars, webhook registration,
  staging sign-off: none.
