# Secrets

Three rules, in every file of every repository:

| Rule | Fires on |
|---|---|
| `core/no-hardcoded-secret` | an assignment whose name reads like a credential (`api_key`, `secret`, `password`, `auth_token`, `access_token`, `client_secret`, `bearer`) with a 16+ character string literal. Skips `*.example`, `*.template`, `*.dist`, `*.md`. |
| `core/no-vendor-token` | a token with a known vendor prefix — AWS `AKIA…`, GitLab `glpat-…`, GitHub `ghp_/gho_/ghu_/ghs_/ghr_…`, Slack `xoxb-…`, `sk-…`. Skips `*.example`, `*.template`, `*.dist` only. |
| `core/no-private-key` | a `-----BEGIN … PRIVATE KEY-----` header, in any file, including comments and fixtures. |

## There is no escape hatch, and that is the point

`guardrail:allow` does nothing on these. Neither does `guardrail:disable-file`. An
`.guardrails.json` entry switching one off is rejected by the config loader and reported
by `guardrail info`, so a repo cannot quietly opt out.

Every other rule in the set guards code quality, and a follow-up commit fixes a mistake.
A credential does not work that way. And the moment someone is in a hurry — the release
is blocked, the demo is in ten minutes — is exactly the moment an escape hatch gets used.
A check with an opt-out on that path is not a check.

If the block is a false positive, change the fixture rather than the rule: a dummy value
under 16 characters passes, and so does reading the real one from the environment.

## A committed credential is compromised, not just misplaced

Once pushed it exists in the remote's object store (rewriting your branch does not remove
objects the server already has), in every clone and fork, in CI runner caches and build
logs, in the mirror, and in whatever secret-scanning bots watch the forge. Deleting the
line, amending, and force-pushing removes it from *your* history and from nobody else's.

So, in this order:

1. **Rotate it at the provider first.** Revoke the old value before touching git.
2. Replace the code path with an environment read.
3. Tell the service owner so they can check access logs for the window it was live.

Do not reverse steps 1 and 2. Cleaning history first just means the credential is still
valid and now harder to find.

## What to write instead

PHP — read through the config layer, never `env()` in application code:

```php
// config/services.php
'stripe' => ['secret' => env('STRIPE_SECRET')],

// usage
config('services.stripe.secret');
```

TypeScript — anything reachable by the bundler ships to the browser. A publishable key
with provider-side host restrictions belongs in the environment file; a secret key does
not exist in a frontend at all, it needs a backend endpoint.

Private keys and certificates go in the platform secret store and are injected at
runtime — never a file in the repo, never base64 in a variable to get past the check.

Every new key gets an entry in `.env.example` with an **empty** value, so the next person
knows it is required without learning what it is.
