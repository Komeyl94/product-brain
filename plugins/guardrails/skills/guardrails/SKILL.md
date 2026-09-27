---
name: guardrails
description: How the Product Brain guardrails work — what the PreToolUse block means, when a waiver is legitimate, and how to check changes before pushing. Use when a write was blocked by a guardrail, when deciding whether to waive a rule, or when asked what the engineering standards are in this repository.
---

# Guardrails

Writes in this repository are checked against the shared engineering standards
before they land. The rules that apply are chosen from what the repository actually
contains — a Laravel API gets the PHP and Laravel rules, an Inertia monolith also gets
the React and Inertia rules, a Flutter app gets neither.

Only content being **added** is ever inspected. Existing code is never scanned, so the
standard applies from today forward rather than demanding a rewrite first.

## When a write is blocked

The block names the rule, the line, and what to do instead. **Fix the code.** Do not:

- rewrite the same content through a different tool to get past the check
- move the offending line into a file the rule does not cover
- disable, edit or uninstall the hook

If a block looks wrong, that is worth saying out loud to the user rather than working
around — a false positive is a defect in the guardrail and the Product Brain maintainers want to
hear about it.

## Waivers

Appending `guardrail:allow` to a line suppresses a waivable rule for that line:

```php
$legacyPayload = unserialize($trustedBlob); // guardrail:allow
```

A waiver is legitimate when the rule's reasoning genuinely does not apply here — not
when fixing the code is inconvenient. Two obligations come with using one:

1. **Say why in your reply to the user.** An unexplained waiver is a defect.
2. **Keep it to the narrowest scope.** `guardrail:disable-file` exists but turns off
   every waivable rule in the file; prefer the single line.

Some rules **cannot be waived at all** — hardcoded credentials, vendor tokens, private
keys and conflict markers. These have no escape hatch by design: the moment someone is
in a hurry is exactly the moment an escape hatch gets used, and a leaked credential
cannot be undone by a follow-up commit.

## Checking before you push

The plugin puts `guardrail` on PATH. Run it from inside the repository:

```bash
guardrail info                   # stacks and rules active here
guardrail staged                 # what a commit would be judged on
guardrail range origin/<target>  # everything this branch adds against its target
```

`range` is the check to run before opening a merge request.

## Repository-level configuration

An optional `.guardrails.json` at the repository root can switch off individual rules —
but only ones marked
overridable, which is the conventions and none of the safety or security rules. An
entry the policy rejects is reported by `guardrail info` rather than silently ignored,
so a repo cannot quietly opt out.

To get a rule changed, relaxed or removed for everyone, open a pull request against
the Product Brain repository (`plugins/guardrails/`). That is deliberately a visible conversation rather than a
local setting.

## What this does and does not hold

This hook blocks the agent's write and nothing else. It installs no git hooks and no CI
job, so a human editing by hand, or a commit made outside Claude, is not checked. If a
team wants the same rules to gate merges, run `guardrail range origin/<target>` as a CI
step — the engine has no dependencies beyond Node.
