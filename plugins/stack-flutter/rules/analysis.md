# Analyzer discipline

## Never silence a diagnostic

`flutter/no-analyzer-ignore` blocks every `// ignore:` and `// ignore_for_file:` comment, in test files
too. An ignore comment is permanent, invisible in review, and outlives the reason it was added — six months
later nobody knows whether the underlying problem was fixed, and the analyzer will not tell them.

```dart
// wrong — the gap is still there, it just stopped being reported
// ignore: use_build_context_synchronously
Navigator.of(context).pop();

// right
if (!mounted) return;
Navigator.of(context).pop();
```

Almost every ignore in real code is one of three things, and all three have a real fix:

| Lint | What it is actually telling you |
|---|---|
| `use_build_context_synchronously` | A real crash after an await. See async.md. |
| `avoid_dynamic_calls` / implicit dynamic | A type was lost at the JSON boundary. See types.md. |
| `unused_*` | Dead code. Delete it. |

If the lint itself is genuinely wrong for this codebase, that is a change to `analysis_options.yaml` that
the team discusses — raise it and say why, rather than ignoring it line by line where nobody will see the
decision.

## Do not weaken the configuration

Do not remove a rule from `analysis_options.yaml`, lower a severity, or add an `exclude:` entry to make a
write pass. That converts one visible problem into a silent one across the whole repository. Changing
analyzer configuration is never a side effect of an unrelated task.

Adding a rule is a different matter and usually welcome — but it belongs in its own change, since turning
one on typically produces findings across files you were not asked to touch.

## `flutter analyze` must be clean

A change that adds warnings is not finished. Run the project's own commands before reporting a change as
done — read `Makefile`, `pubspec.yaml` and any CI config rather than assuming, but it is nearly always:

```
flutter analyze
flutter test
```

Warnings the analyzer emits in code you did not touch are pre-existing; say so rather than fixing them
inside an unrelated change, and do not let them hide a warning you introduced.

## Lints worth having on, if the project does not already

`flutter_lints` is the baseline most projects start from. Beyond it, the rules that catch real bugs rather
than style are `use_build_context_synchronously`, `avoid_dynamic_calls`, `unawaited_futures`,
`cancel_subscriptions` and `close_sinks` — each maps directly to a failure class described in async.md.
Propose them; do not add them silently in the middle of a feature.
