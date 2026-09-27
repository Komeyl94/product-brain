---
name: symfony-conventions
description: Symfony conventions for architecture, dependency injection, controllers and routing, Doctrine, security, Messenger and testing. Use when writing or reviewing PHP in a Symfony application — any repository whose composer.json requires symfony/framework-bundle.
---

# Symfony conventions

## Read the neighbours first

These defaults are not calibrated against any one codebase, so nothing here encodes an
existing house style. **Before writing a controller, service, entity or handler, open a sibling file in the
same namespace and match it** — directory layout, naming, whether services are wired by autowiring or
declared explicitly in `services.yaml`, whether the project uses `src/Controller/` flat or per-bundle
modules, whether DTOs exist.

When a local convention contradicts something below, follow the local convention for *structure and
naming* and say so in your reply. Do not follow it for the correctness and security items — parameter
binding in DQL, authorisation checks, transaction boundaries — those are wrong everywhere, and a file that
already does one of them is a defect you should not copy.

Never migrate a file to a newer Symfony idiom as a side effect of an unrelated change. If the task
genuinely requires it, say so and ask first.

## Always, in any Symfony version

- `declare(strict_types=1);` immediately after `<?php`, in every new PHP file.
- Constructor injection with promoted readonly properties. Never reach into the container.
- Typed everything: parameter types, return types, property types. No `mixed`, no untyped `array` where a
  DTO or a `list<Thing>` phpdoc would say more.
- `#[Route(...)]` PHP attributes. Doctrine-annotation `@Route` was removed in Symfony 7.
- `final class` by default for services, handlers and DTOs. Extension is a decision, not a default.

## Topic files

Read the file that matches what you are about to write. They live at the plugin root under `rules/`; from
this skill the path is `../../rules/<name>.md`.

| Read | When |
|---|---|
| `../../rules/architecture.md` | Deciding where code goes: controller vs service vs repository, what an entity is allowed to do, where a transaction begins. |
| `../../rules/dependency-injection.md` | Wiring anything: constructors, interfaces, `#[Autowire]`, tagged collections, parameters and env vars. |
| `../../rules/routing.md` | Declaring a route: attributes, names, method and parameter constraints, prefixes, collisions. |
| `../../rules/controllers.md` | Writing an HTTP entry point: request payload mapping, validation, responses, error handling. |
| `../../rules/doctrine.md` | Entities, repositories, DQL, `flush()` placement, N+1, batch processing, migrations. |
| `../../rules/security.md` | Authentication, authorisation, voters, user input reaching a query, secrets, what a response is allowed to expose. |
| `../../rules/messenger.md` | Dispatching or handling an async message, retries, transactional dispatch, worker lifetime. |
| `../../rules/testing.md` | Any test: unit, `KernelTestCase`, `WebTestCase`, database state, messenger assertions. |

## What the hook blocks before the write lands

The guardrails PreToolUse hook rejects these outright. The reasoning is in the topic files; the mechanics
are not your problem, fixing the code is.

| Rule | Topic file |
|---|---|
| `symfony/no-container-service-locator` — `$container->get(...)` outside tests | dependency-injection.md |
| `symfony/no-annotation-routes` — `* @Route(...)` in a docblock | routing.md |
| `symfony/no-dql-interpolation` — a variable interpolated into DQL or SQL | security.md, doctrine.md |
| `symfony/no-entity-manager-in-controller` — `persist()`/`flush()`/`remove()` in a controller | architecture.md |
| `php/require-strict-types`, `php/no-mixed-type` | applies once the repo already declares strict types in most files |
| `php/no-debug-output`, `php/no-die-exit` | `dd`, `dump`, `var_dump`, `die`, `exit` |
| `php/no-eval`, `php/no-shell-execution`, `php/no-unserialize` | security.md |

A blocked write is not an invitation to restructure the code until the regex stops matching. Fix the cause.
The `guardrail:allow` line comment exists for the case where the flagged line is genuinely correct — using
it obliges you to explain why in your reply.
