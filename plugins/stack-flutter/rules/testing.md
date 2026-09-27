# Testing

Flutter work is tested end to end with Flutter's own **`integration_test`** package: the real app,
driven on a device, emulator or simulator. This plugin does not prescribe unit or widget tests; if a
repo already has them, keep them passing and follow their existing style. If flows need native OS UI
that `integration_test` can't reach (permission dialogs, notifications, the system browser), ask
whether to add **Patrol**, which builds on `integration_test` — don't bolt on a second framework
unasked. If the repo already has an E2E suite in another tool, ask before migrating it.

## Setup

```yaml
# pubspec.yaml
dev_dependencies:
  flutter_test:
    sdk: flutter
  integration_test:
    sdk: flutter
```

- Specs live in `integration_test/` as `*_test.dart`, one file per journey.
- Each file starts with `IntegrationTestWidgetsFlutterBinding.ensureInitialized();` and launches the
  **real app** through its normal entry point, not a hand-assembled widget tree.
- Point the app at a **dedicated test backend**, never production, with the project's existing
  mechanism — a flavor or `--dart-define=API_BASE_URL=...`. Hardcoding a URL in the spec defeats that.
- Reset persisted state (secure storage, shared preferences, local database) in `setUp`, so every
  test starts logged out on a fresh install.

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:my_app/main.dart' as app;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('a signed-in user places an order', (tester) async {
    app.main();
    await tester.pumpAndSettle();

    await signIn(tester, email: testUserEmail, password: testUserPassword);
    await tester.tap(find.byKey(const Key('product-tile-sku-1')));
    await tester.tap(find.bySemanticsLabel('Add to cart'));
    await tester.tap(find.byKey(const Key('checkout')));
    await pumpUntilFound(tester, find.text('Order placed'));

    expect(find.text('Order placed'), findsOneWidget);
  });
}
```

Shared steps (`signIn`, `pumpUntilFound`) go in a helper file under `integration_test/`, not
copy-pasted into every spec. Credentials come from `--dart-define`, never literals in the code.

## Rules

- **Find by key or semantics** — `find.byKey(const Key('checkout'))`, `find.bySemanticsLabel(...)`,
  `find.text` for user-visible copy. Never `find.byType(...).at(n)`: a layout change breaks it.
  Add `Key`s to the widgets a journey drives.
- **Wait for the result, not for time** — `pumpAndSettle()` **hangs until timeout** while anything
  animates forever (a spinner, a shimmer, a looping animation). Use a small `pumpUntilFound` helper
  that pumps in short steps until the finder matches or a timeout fails the test. Never
  `Future.delayed` or `sleep` to "wait for" the app.
- **Every test stands alone** — fresh state in `setUp`, no reliance on another test's data or order.
- **Own your data** — create what the test needs through the test backend's API; don't depend on
  whatever happens to be in it.
- **Cover the unhappy paths** — invalid input, a server error, no network, an expired session, a
  permission the user doesn't have. The failed and empty screens are the ones that ship broken.
- **Mock only what you don't own** — fake third-party SDKs (payments, maps, analytics) behind the
  app's own interfaces; exercise your own backend for real.
- **Screenshots on failure** — `binding.takeScreenshot('name')` (with the `flutter drive` runner)
  at the step that failed beats a bare stack trace.
- `flutter/no-print` and `flutter/no-dynamic` skip test files, but `// ignore:` comments are blocked
  in tests too, and a `print` is still noise in CI — use `expect` to say what you mean.

## Running

Use the repo's own script or Makefile target if it has one; otherwise:

```bash
flutter devices                                                 # pick a device or emulator
flutter test integration_test -d <device-id> \
  --dart-define=API_BASE_URL=https://test-api.example.com       # all journeys
flutter test integration_test/checkout_test.dart -d <device-id> # one journey
```

For screenshots, or to run on web, use `flutter drive --driver=test_driver/integration_test.dart
--target=integration_test/<name>_test.dart`. In CI the specs need an emulator/simulator or a device
farm (e.g. Firebase Test Lab). `flutter analyze` must be clean as well; if the change touched
generated code, re-run the project's codegen the way the repository already does. Never claim a
change works without running anything.
