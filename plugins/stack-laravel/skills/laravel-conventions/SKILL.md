---
name: laravel-conventions
description: Laravel conventions for controllers, Actions, Eloquent, migrations, validation, security, config, queues, error handling and Playwright end-to-end tests. Use when writing or reviewing PHP in a Laravel repository — anything under app/, database/, routes/, config/ or tests/ — or when a change touches models, Form Requests, Data classes, policies, jobs or schema.
---

# Laravel Conventions

Defaults for Laravel work. Each topic lives in `rules/`. Read the ones your change
touches before editing; skip the rest.

## Match the repository before applying any rule

These are defaults for when the codebase has no answer yet — not overrides. Before writing a
controller, model, Form Request or test, open a sibling file in the same folder and follow what
it does. Laravel offers several valid shapes for the same job (Form Requests vs. `spatie/laravel-data`,
`$casts` property vs. `casts()` method, `test()` vs. `it()`); a second pattern for the same job
costs more than a suboptimal one. Deviate only for a correctness or security defect, and say so.

## Rule index

| Change touches | Read |
| --- | --- |
| Controllers, Actions, service layout, where logic belongs | [`rules/architecture.md`](../../rules/architecture.md) |
| Models, relationships, scopes, casts, query performance, N+1 | [`rules/eloquent.md`](../../rules/eloquent.md) |
| Schema changes, columns, foreign keys, indexes, PostgreSQL types | [`rules/migrations.md`](../../rules/migrations.md) |
| Form Requests, Data classes, rules, enum fields, uploads | [`rules/validation.md`](../../rules/validation.md) |
| Authorization, policies, mass assignment, secrets, throttling | [`rules/security.md`](../../rules/security.md) |
| `config/`, environment values, constants, magic strings | [`rules/config.md`](../../rules/config.md) |
| Jobs, queueable Actions, retries, uniqueness, Horizon | [`rules/queues.md`](../../rules/queues.md) |
| Exceptions, reporting, rendering, failure responses | [`rules/error-handling.md`](../../rules/error-handling.md) |
| Playwright end-to-end tests (browser and API) | [`rules/testing.md`](../../rules/testing.md) |

A cross-cutting change usually needs more than one. A new CRUD feature touches architecture,
validation, security, migrations and testing.

## Already enforced mechanically

The guardrail hook blocks these before the write lands, and CI blocks them again on push. Do not
spend review comments restating them; the rule files cover the judgment *around* them instead.

`laravel/no-env-outside-config` · `laravel/no-raw-query-interpolation` · `laravel/no-unguarded-model`
· `laravel/no-unvalidated-request-all` · `laravel/no-enum-column-in-migration` ·
`laravel/migration-requires-down` · `laravel/controller-no-direct-persistence` ·
`php/no-debug-output` · `php/no-eval` · `php/no-shell-execution` · `php/no-unserialize` ·
`php/no-die-exit` · `php/require-strict-types` · `php/no-mixed-type`

If the hook blocks a write, fix the code. Never restructure the code purely to slip past the
pattern match — the CI gate runs the same engine and will catch it.

## Non-negotiable defaults for new PHP files

- `declare(strict_types=1);` at the top — enforced.
- `final class` for controllers, Actions, models and jobs unless something already extends it.
- Explicit parameter and return types on every method. No `mixed` — enforced. No untyped arrays
  where a Data object or a typed collection would do.
- Scaffold with `php artisan make:*` and always pass `--no-interaction`; an interactive prompt
  hangs an agent session with no output.

## Verify before claiming done

Read the project's `composer.json` scripts rather than assuming — the usual set is:

```bash
vendor/bin/pint --dirty          # format only what you touched
vendor/bin/phpstan analyse       # larastan; most repos here run level 9
php artisan test --compact       # the existing suite, if the repo has one
npx playwright test              # end-to-end specs
```

Architecture tests (`tests/Unit/*ArchitectureTest.php`) are where a repo encodes its own
conventions. When one fails, it is telling you about a local rule that is not in this skill —
read the test, do not delete it.
