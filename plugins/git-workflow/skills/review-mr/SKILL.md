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
CI). Its verdict comes from the pipeline log (Step 3) and needs no token. A token only adds issue
details (Step 3b). Check for one without printing it:

```bash
[ -n "$SONAR_HOST_URL" ] && [ -n "$SONAR_TOKEN" ] && echo "sonar api: configured" || echo "sonar api: not configured"
```

If it is not configured and the user wants issue details, point them to the `connect-tools` skill
or tell them: generate a "User Token" at `<SONAR_HOST_URL>/account/security`, add `SONAR_HOST_URL` and
`SONAR_TOKEN` to the `env` of `.claude/settings.local.json` **themselves** (keeping existing keys),
and start a new session. Before anything touches that file, confirm git ignores it:

```bash
git check-ignore -q .claude/settings.local.json && echo ignored || echo "NOT IGNORED"
```

If `NOT IGNORED`, stop. Never write a token into `.env`, `.env.example` or any tracked file, never
echo its value, and never ask for it in the chat.

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

## Step 3: Read SonarQube from the MR pipeline

The pipeline is the source of truth and needs no token. If the hub has
`docs/runbooks/check-sonarqube-on-mr.md`, follow it — it names this repo's Sonar job. Otherwise find
the Sonar job in the MR's latest pipeline and read its log:

```bash
PIPELINE=$(glab api "projects/:id/merge_requests/$MR_IID/pipelines" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')
glab api "projects/:id/pipelines/$PIPELINE/jobs?per_page=100" \
| python3 -c 'import json,sys
for j in json.load(sys.stdin):
    if "sonar" in j["name"].lower(): print(j["id"], j["name"], j["stage"], j["status"])'
glab ci trace <job-id> | grep -iE "QUALITY GATE STATUS|ANALYSIS SUCCESSFUL|dashboard\?id=|api/ce/task"
# GitHub: gh pr checks, then gh run view <run-id> --log | grep -iE "quality gate|dashboard"
```

`QUALITY GATE STATUS: PASSED` / `FAILED` is the verdict; the `dashboard?id=` line is the link to
give the user. If the job doesn't wait for the gate (`sonar.qualitygate.wait` not `true`), the log
only shows the analysis was submitted — say the verdict is on the dashboard, not that it passed.
Never hardcode the job name; CI templates can rename it.

## Step 3b (optional): SonarQube issue details from the API

Only when `SONAR_TOKEN` and `SONAR_HOST_URL` are set **and** the server is reachable (it is often
VPN-only — test with `curl -sf "$SONAR_HOST_URL/api/server/version"`). Otherwise the Step 3 verdict
and dashboard link are the result; report issue details as `SKIPPED`, not clean.

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
  Sonar gate:   <PASSED | FAILED (conditions) | submitted, see dashboard | not used>  (source: pipeline log | API)
  Dashboard:    <url>
  Sonar issues: <n> (scope: pullRequest=<iid> | branch=<branch> | unavailable)
  Bot findings: <n> | none | bot has not reviewed this MR

  Fixed:    <list>
  Deferred: <list with ticket keys>
  Skipped:  <list with reason>
```

State plainly when a source was skipped. A partial review is never reported as clean.

## Rules

- Never report the MR as clean when neither the pipeline log nor the API gave a Sonar verdict
- Never write a token into a tracked file, and never echo its value
- Never act on a stale bot note; only the newest describes the current head
- Never edit an upstream-owned file to satisfy a finding
- Never defer a Sonar `BLOCKER`, `CRITICAL` or `SECURITY_HOTSPOT`
- Never hardcode CI job names
- User instructions override automation: if the user explicitly overrides a step, respect it
