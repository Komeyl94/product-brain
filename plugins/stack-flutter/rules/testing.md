# Testing

## Pick the cheapest test that can fail for the right reason

| Test | Use when |
|---|---|
| `test()` | Logic with no widgets: parsing, a bloc/notifier, a repository against a fake client. |
| `testWidgets()` | The behaviour *is* the UI: what renders for a state, what a tap does. |
| `integration_test` | A real flow across screens on a device or emulator. Slow; keep the set small. |

Most bugs are testable without pumping a widget. If a rule can only be tested through the UI, the logic is
probably in the widget and belongs in a notifier or service instead.

## Widget tests

```dart
testWidgets('shows the empty state when there are no orders', (tester) async {
  await tester.pumpWidget(MaterialApp(home: OrdersScreen(repository: FakeOrderRepository.empty())));
  await tester.pump();

  expect(find.text('No orders yet'), findsOneWidget);
});
```

Wrap the widget under test in whatever ancestors it needs (`MaterialApp`, a theme, the project's provider
scope) — a missing `Directionality` or `MediaQuery` produces an error that looks like a bug in your widget.

`pump()` advances one frame. `pumpAndSettle()` pumps until no frames are scheduled, and **hangs until
timeout against an indefinite animation** — a spinner, a looping animation, a shimmer placeholder. Use
`pump(const Duration(milliseconds: 300))` when something on screen animates forever.

Find by semantics or by key, not by widget index. `find.byKey(const Key('submit'))` survives a layout
change; `find.byType(ElevatedButton).at(2)` does not.

## Fake the boundary, not the framework

Write a small fake implementing the repository/client interface. Mocking `http.Client` call-by-call
produces a test that asserts how the code calls the library rather than what it does, and keeps passing
when the URL is wrong.

Never hit the real network, filesystem or clock in a test. Inject a clock; pin randomness. `await
Future.delayed(...)` to "wait for" something is always wrong in a widget test — use `tester.pump` with the
duration, and `tester.runAsync` only when you genuinely need real async work to run.

## Test the states, including the unhappy ones

For each screen: loading, loaded, empty, failed. The empty and failed branches are the ones that ship
broken, because they are the ones nobody opens by hand. A sealed state hierarchy (state-management.md)
makes this a short, exhaustive list.

## Bloc / notifier tests

Test them as plain objects: construct with fakes, send an event, assert the emitted sequence. No widgets
involved, so they run in milliseconds and the failure message points at the logic.

Assert the sequence, not just the final state — `[Loading, Loaded]` and `[Loaded]` are different bugs.

## Hygiene

- Every test disposes what it creates, exactly like a widget would.
- No shared mutable state between tests; a `setUp` that builds fresh fakes beats a top-level fixture.
- `flutter/no-print` and `flutter/no-dynamic` skip test files, but a `print` in a test is still noise in
  CI output — use `expect` to say what you mean. `// ignore:` comments are blocked in tests too.

## Before claiming it works

Run the project's own commands — usually `flutter analyze` and `flutter test`, but read `pubspec.yaml`,
`Makefile` and any CI config rather than assuming. `flutter analyze` must be clean: a change that adds
warnings is not done, and silencing them is blocked. If the change touched generated code, re-run the
project's codegen (`dart run build_runner build --delete-conflicting-outputs`) and commit the result the
same way the repository already does.
