---
name: review-mr
description: Collect every automated signal on the current merge request / pull request — CI pipeline, SonarQube findings and quality gate, review-bot notes — triage each finding, fix or defer, and report. Use after the pipeline passes and before marking an MR ready, or when asked to review an MR/PR's automated findings.
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# review-mr

Gather the automated signals on the current MR, triage each finding, then fix or defer. Run after
the pipeline passes and before the MR is marked ready (see the git-workflow merge-request rule).

It exists for two signals a human-thread review misses:

- **SonarQube** frequently posts no MR comments — its findings are API-only.
- **Review bots** often post a plain note, not a resolvable thread, so "unresolved threads" never
  shows them.

Works on GitLab (`glab`) and GitHub (`gh`). Detect which one from `git remote get-url origin`
and the CLI that is authenticated. Examples below show GitLab; for GitHub translate MR → PR,
`glab` → `gh`.

## Step 0: Preflight

```bash
glab auth status            # or: gh auth status
MR_IID=$(glab mr view -F json | python3 -c 'import json,sys; print(json.load(sys.stdin)["iid"])')
SOURCE_BRANCH=$(git branch --show-current)
```

If auth fails, stop and ask the user to log in (`glab auth login` / `gh auth login`). Never log in
for them.

SonarQube is optional. It applies when the repo has `sonar-project.properties` (or a Sonar step in
CI). Check credentials without printing the token:

```bash
[ -n "$SONAR_HOST_URL" ] && [ -n "$SONAR_TOKEN" ] && echo "sonar: configured" || echo "sonar: MISSING"
```

If the repo uses Sonar and the credentials are missing, do not skip silently. Tell the user:

```text
SonarQube needs a personal token before this review can include its findings.
1. Open <SONAR_HOST_URL>/account/security and generate a "User Token". Copy it — Sonar shows it once.
2. Add to <repo>/.claude/settings.local.json, inside "env" (keep existing keys):
   { "env": { "SONAR_HOST_URL": "https://<your-sonar-host>", "SONAR_TOKEN": "<token>" } }
3. Start a new session so the values load, then re-run review-mr.
```

Before ever writing a token to that file, confirm git ignores it:

```bash
git check-ignore -q .claude/settings.local.json && echo ignored || echo "NOT IGNORED"
```

If `NOT IGNORED`, stop — do not write the token. Never write a token into `.env`, `.env.example`
or any tracked file, and never echo its value. If the user declines, continue with Sonar reported
as `SKIPPED`.

## Step 1: Confirm the pipeline is green

```bash
glab ci get --merge-request "$MR_IID" -F json | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])'
# GitHub: gh pr checks
```

If it is not green, get it green first, then come back — findings from a failed or incomplete
analysis are not trustworthy. Never hardcode CI job names.

## Step 2: Fetch review-bot notes

Fetch all notes and keep the non-system ones written by a bot account (username containing `bot`,
or a known reviewer bot the repo documents):

```bash
glab api "projects/:fullpath/merge_requests/$MR_IID/notes?per_page=100" --paginate \
| python3 -c '
import json, sys
notes = [n for n in json.load(sys.stdin) if not n.get("system")
         and (n.get("author", {}).get("bot") or "bot" in n.get("author", {}).get("username", "").lower())]
if not notes: print("NO BOT REVIEW")
else:
    n = sorted(notes, key=lambda x: x.get("created_at", ""))[-1]
    print("--- {} ({})".format(n["author"]["username"], n.get("created_at"))); print(n.get("body", ""))'
# GitHub: gh pr view --json comments,reviews and filter authors whose login ends in [bot]
```

Use only the **newest** note per bot — earlier ones describe superseded commits. No bot note at all
means "the bot has not reviewed this MR", which is not the same as a clean review.

## Step 3: Fetch SonarQube issues and the quality gate

Skip when Sonar is not used or not configured (reported as `SKIPPED`).

```bash
SONAR_PROJECT=$(grep '^sonar.projectKey=' sonar-project.properties | cut -d= -f2)

curl -sS --fail-with-body -H "Authorization: Bearer $SONAR_TOKEN" \
  --get "$SONAR_HOST_URL/api/issues/search" \
  --data-urlencode "componentKeys=$SONAR_PROJECT" --data-urlencode "pullRequest=$MR_IID" \
  --data-urlencode "resolved=false" --data-urlencode "ps=500" \
| python3 -c 'import json,sys
for i in json.load(sys.stdin).get("issues", []):
    loc = i.get("component","").split(":",1)[-1] + ":" + str(i.get("line","?"))
    print(i.get("severity"), i.get("type"), loc, i.get("rule"), i.get("message"), sep="\t")'

curl -sS --fail-with-body -H "Authorization: Bearer $SONAR_TOKEN" \
  --get "$SONAR_HOST_URL/api/qualitygates/project_status" \
  --data-urlencode "projectKey=$SONAR_PROJECT" --data-urlencode "pullRequest=$MR_IID" \
| python3 -c 'import json,sys
s = json.load(sys.stdin)["projectStatus"]; print("gate:", s.get("status"))
for c in s.get("conditions", []):
    if c.get("status") != "OK": print("  FAILED", c.get("metricKey"), c.get("actualValue"), c.get("comparator"), c.get("errorThreshold"))'
```

If `pullRequest=` returns zero issues, confirm an MR-scoped analysis exists before calling it clean;
if none is on record, retry with `branch=$SOURCE_BRANCH`. An empty result with no analysis on record
is **unknown**, not clean. State which scope produced the findings.

## Step 4: Triage every finding

Pool bot findings and Sonar issues into one list and classify each:

| Category | Meaning | Action |
|---|---|---|
| (a) objective correctness | a bug, security issue, broken contract | fix |
| (b) convention with precedent | the repo already does it the suggested way | fix |
| (c) subjective / architectural | reasonable people disagree, or it is a design change | ask the user |
| (d) nitpick | no real impact | mention, skip unless trivial |
| (e) upstream-owned file | vendored or generated code, or a file owned by another repo | do not edit; surface it |

(e) takes precedence over (a)–(d). A Sonar `SECURITY_HOTSPOT`, `BLOCKER` or `CRITICAL` is always
(a) — fix it, never defer it.

For (a) and (b): fix, commit (following the commit-message rule), push, wait for the new
pipeline, then return to **Step 3** — a new pipeline means a new analysis, so re-fetch rather than
assume findings are unchanged. For (c)–(e): ask the user; offer to open a tech-debt ticket in the
team's tracker for anything deferred.

Bot notes are not threads, so there is nothing to resolve. Post one summary note:

```bash
glab mr note create "$MR_IID" -m "<what was fixed, what was deferred and why>"   # gh pr comment
```

Human review threads are separate: address and resolve them with the team's usual flow.

## Step 5: Report

```text
Internal review — MR !<iid>
  Pipeline:     <status>
  Sonar gate:   <OK | ERROR (conditions) | SKIPPED: <reason> | not used>
  Sonar issues: <n> (scope: pullRequest=<iid> | branch=<branch> | unavailable)
  Bot findings: <n> | none | bot has not reviewed this MR

  Fixed:    <list>
  Deferred: <list with ticket keys>
  Skipped:  <list with reason>
```

State plainly when a source was skipped. A partial review is never reported as clean.

## Rules

- Never report the MR as clean when Sonar was skipped or returned an unknown scope
- Never write a token into a tracked file, and never echo its value
- Never act on a stale bot note; only the newest describes the current head
- Never edit an upstream-owned file to satisfy a finding
- Never defer a Sonar `BLOCKER`, `CRITICAL` or `SECURITY_HOTSPOT`
- Never hardcode CI job names
- User instructions override automation: if the user explicitly overrides a step, respect it
