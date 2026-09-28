---
name: verify-ticket-scope
description: Verify the current branch diff satisfies the scope written on its ticket (Jira, GitLab or GitHub issue) before a merge request / pull request is created. Use before any MR or PR is opened, when the user asks for an MR, or when the git-workflow hook blocked `glab mr create` / `gh pr create`.
argument-hint: "[ticket-key]"
allowed-tools: [Bash, Read, Glob, Grep]
---

# verify-ticket-scope

Check the current branch diff against the scope recorded on its ticket and report per-item
status before an MR is created. It is the gate in front of MR creation (see the git-workflow
merge-request rule); a hook denies `glab mr create` / `gh pr create` until this skill records a
result for the current HEAD.

Read-only against the tracker: never create, edit, transition or comment on a ticket. The only
write is the marker in Step 7.

## Step 1: Derive the ticket key

Use the argument if one was passed. Otherwise take it from the branch name
(`{type}-{key}-{number}-{description}`):

```bash
git branch --show-current | grep -oE '[A-Za-z][A-Za-z0-9]*-[0-9]+' | head -1 | tr '[:lower:]' '[:upper:]'
```

A bare number (`feature-123-...`) is an issue number on the code host. If nothing comes out, ask
the user for the ticket. Never proceed without one.

## Step 2: Fetch the ticket

Use the first source that is available, and name it in the report:

1. **Jira** — a connected Jira MCP tool that gets an issue (e.g. `jira_get_issue`). Fetch the
   issue and every sub-task; if the key is itself a sub-task, fetch its parent for context.
2. **GitLab issue** — `glab issue view <number> -F json`.
3. **GitHub issue** — `gh issue view <number> --json title,body`.

If none can reach the ticket, stop and report `Result: UNVERIFIED (no tracker access for <KEY>)`.
Never fall back to inferring scope from the branch name, commit messages or the diff itself.

## Step 3: Extract the scope items

Scope is a Markdown section in the ticket description. Look for the first heading named
`Acceptance criteria`, `Scope`, `Requirements` or `Definition of done` (any level, any case),
and take every list item beneath it up to the next heading of the same or higher level. Do the
same for each sub-task; a sub-task with no such section contributes its summary line as one item.

If no scope section exists anywhere, stop and report `Result: UNVERIFIED (no scope section on <KEY>)`.
Never invent scope items.

## Step 4: Collect the branch diff

Reuse the target branch of an open MR when there is one; otherwise use the remote default
branch. If two candidates are plausible, ask the user. Never default blindly to `develop` or `main`.

```bash
git fetch --quiet origin
TARGET=$(glab mr view -F json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["target_branch"])' 2>/dev/null \
  || gh pr view --json baseRefName -q .baseRefName 2>/dev/null \
  || git remote show origin | sed -n 's/.*HEAD branch: //p')
git diff --stat "origin/$TARGET...HEAD"
git diff "origin/$TARGET...HEAD"
git log --oneline "origin/$TARGET..HEAD"
```

Read the changed files when the diff alone cannot settle an item — a scope item about behaviour
usually needs the surrounding code, not just the added lines.

## Step 5: Judge each scope item

Exactly one status per item, each with one line of evidence:

| Status | Meaning | Evidence required |
|---|---|---|
| `MET` | The diff clearly implements it | The file and symbol that implements it |
| `NOT MET` | Not implemented, and not already present on the target branch | What is missing |
| `UNVERIFIABLE` | Cannot be judged from a code diff (e.g. a browser-visible assertion) | Why, and how it can be checked |

Before marking an item `NOT MET`, check whether the target branch already satisfies it — an
item delivered by an earlier branch is `MET`:

```bash
git log "origin/$TARGET" --oneline -- <path>
```

## Step 6: Report

Print one block, nothing else:

```text
Ticket scope check — <KEY> (+ N sub-tasks) via <Jira | GitLab | GitHub>
Target branch: <target>

MET            <item>
                 └ <evidence>
NOT MET        <item>
                 └ <what is missing>
UNVERIFIABLE   <item>
                 └ <why, and how to check it>

Result: PASS | BLOCKED (n not met) | UNVERIFIED (<reason>)
```

`PASS` only when zero items are `NOT MET`. `UNVERIFIABLE` items never block.

## Step 7: Record the result for the MR gate

On `PASS`, write the marker the hook reads, stamped with HEAD so a later commit invalidates it:

```bash
git rev-parse HEAD > "$(git rev-parse --absolute-git-dir)/pb-scope-ok"
```

On `BLOCKED`, do not write it. Present the `NOT MET` items and ask the user whether to waive
them. Only on an explicit waiver, record it so the MR description can note it:

```bash
printf '%s\nWAIVED: %s\n' "$(git rev-parse HEAD)" "<comma-separated waived items>" \
  > "$(git rev-parse --absolute-git-dir)/pb-scope-ok"
```

On `UNVERIFIED`, do not write it; surface the reason. If the user decides to proceed without the
check, record that as a waiver (`WAIVED: unverified — <reason>`) the same way.

The marker lives inside `.git/`, so it is never committed or shared between clones.

## Rules

- Never create, edit, transition or comment on a ticket from this skill
- Never infer scope items from the branch name, commit messages or the diff
- Never mark an item `MET` without naming the file or symbol that implements it
- Never soften a `NOT MET` into `UNVERIFIABLE` to clear the gate
- Never write the marker on `BLOCKED` or `UNVERIFIED` without an explicit user waiver
- Never create the MR from this skill — it reports; the caller decides
- User instructions override automation: if the user explicitly overrides a step, respect it
