---
name: flutter-conventions
description: Flutter and Dart conventions for widget composition, state management, async safety, navigation, typing, integration_test end-to-end tests and rendering performance. Use when writing or reviewing Dart in a Flutter app — any repository with a pubspec.yaml that depends on the flutter SDK.
---

# Flutter conventions

## Read the neighbours first

These defaults are not calibrated against any one codebase, so nothing here encodes an
existing house style. **Before writing a screen, widget or controller, open a sibling file in the same
feature folder and match it.** Three things in particular are project decisions that this skill
deliberately does not make for you:

- **State management** — Bloc, Riverpod, Provider, `ChangeNotifier`, or plain `setState`. Whatever the
  feature next door uses, use that. Mixing two approaches in one codebase costs more than either choice.
- **Navigation** — `go_router`/declarative routing versus imperative `Navigator`. Same rule.
- **Folder layout** — feature-first or layer-first, and where models, repositories and widgets sit.

Do not introduce a new package or a new architecture as a side effect of an unrelated task. If the task
genuinely needs one, say so and ask first.

What is *not* a project decision: the async, typing, disposal and rendering rules below. Those are wrong
everywhere, and a file that already does one of them is a defect you should not copy.

## Always

- Widgets are `const` wherever their arguments allow it.
- Anything with a `dispose()` — controllers, subscriptions, timers, focus nodes — is disposed in the
  `State` that created it.
- `BuildContext` is never used after an `await` without a `mounted` check.
- No `dynamic`, no `// ignore:`, no `print()`.

## Topic files

Read the file that matches what you are about to write. They live at the plugin root under `rules/`; from
this skill the path is `../../rules/<name>.md`.

| Read | When |
|---|---|
| `../../rules/widgets.md` | Building UI: composition, `const`, keys, what belongs in `build()`, stateless vs stateful. |
| `../../rules/state-management.md` | Deciding where state lives, or touching a Bloc/Notifier/Provider. Read this before choosing anything. |
| `../../rules/async.md` | Anything with `await`, `Future`, `Stream`, `Timer`, or a `FutureBuilder`. The crash class here is the most common one in Flutter. |
| `../../rules/navigation.md` | Pushing, popping, passing arguments or returning results between screens. |
| `../../rules/types.md` | Models, JSON parsing, nullability, enums, sealed result types. |
| `../../rules/analysis.md` | A lint is in the way, or you are tempted by an `// ignore:` comment or an `analysis_options.yaml` edit. |
| `../../rules/logging.md` | Recording anything: errors, diagnostics, crash reporting, what must never be logged. |
| `../../rules/testing.md` | End-to-end tests with `integration_test`: setup, test backend, waiting without `pumpAndSettle` hangs, running on devices. |
| `../../rules/performance.md` | Lists, animations, images, or anything that janks or rebuilds more than it should. |

## What the hook blocks before the write lands

| Rule | Topic file |
|---|---|
| `flutter/no-context-across-async-gap` — `context` used after an `await` with no `mounted` check | async.md |
| `flutter/no-print` — `print(...)` outside tests | logging.md |
| `flutter/no-dynamic` — a `dynamic` declaration outside the JSON boundary | types.md |
| `flutter/no-analyzer-ignore` — any `// ignore:` or `// ignore_for_file:` comment | analysis.md |
| `core/no-hardcoded-secret` — an API key or token in source | not waivable; read it from a build-time define or secure storage |

A blocked write is not an invitation to rephrase the code until the regex stops matching. Fix the cause.
The `guardrail:allow` line comment exists for the case where the flagged line is genuinely correct — using
it obliges you to explain why in your reply.
