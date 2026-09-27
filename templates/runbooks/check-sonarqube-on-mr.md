# Check SonarQube on a merge request

<!-- Template: brainify fills the <placeholders> from the apps' CI config and a real MR run.
     Delete this comment once filled. -->

Ask Claude "Check SonarQube on MR !<n>", or follow these steps yourself.

## SonarQube is read from the MR pipeline

SonarQube runs as a CI job. Its verdict is in that job's log, so no Sonar account or token is needed
to know whether an MR passes. A token only adds issue-by-issue details, and the Sonar server may
only be reachable on the VPN.

| App | Sonar job | Stage | Runs when | Waits for the gate? | Project key |
|---|---|---|---|---|---|
| `<repo-id>` | `<job-name>` (from `<include/template path, if any>`) | `<stage>` | `<rules, e.g. merge request pipelines>` | `<yes: sonar.qualitygate.wait=true / no>` | `<sonar.projectKey>` |

## Steps

1. Find the MR number (`!<iid>`) and which app repo it belongs to.
2. Get the MR's latest pipeline:
   `glab api "projects/<url-encoded-project-path>/merge_requests/<iid>/pipelines"` — take the first `id`.
3. List that pipeline's jobs and find the Sonar job above:
   `glab api "projects/<url-encoded-project-path>/pipelines/<pipeline-id>/jobs?per_page=100"`.
4. Read its log: `glab ci trace <job-id> -R <project-path>`.
5. Look for `QUALITY GATE STATUS: PASSED` or `FAILED`, and the dashboard link
   (`<sonar-host>/dashboard?id=<project-key>&pullRequest=<iid>`).
   Real example from `<repo-id>` MR !`<iid>`: `<the verdict line and link you saw>`.
6. *Optional — only when `SONAR_TOKEN` and `SONAR_HOST_URL` are set and the server is reachable:*

   ```bash
   curl -sf -u "$SONAR_TOKEN:" "$SONAR_HOST_URL/api/qualitygates/project_status?projectKey=<key>&pullRequest=<iid>"
   curl -sf -u "$SONAR_TOKEN:" "$SONAR_HOST_URL/api/issues/search?componentKeys=<key>&pullRequest=<iid>&resolved=false&ps=100"
   ```

   If either call fails (no token, off VPN), use the verdict and dashboard link from step 5.

GitHub equivalent: `gh pr checks <n>`, then `gh run view <run-id> --log | grep -i "quality gate"`.
