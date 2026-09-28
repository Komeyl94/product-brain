# Navigation

## The router is the project's choice

`go_router` (or another declarative router) and imperative `Navigator` calls do not mix well — a codebase
with both ends up with routes that work from one entry point and not another, and deep links that land on
a screen with no back stack. Open the nearest existing screen, see how it navigates, and do the same.

If the project uses a router package, add the route to the router's configuration rather than pushing a
`MaterialPageRoute` inline, even when the inline version is shorter.

## Navigate after an await, safely

Every navigation call needs a `BuildContext`, so every navigation after an `await` is an instance of the
crash in async.md. Capture the navigator (or router) before the await:

```dart
Future<void> _submit() async {
  final navigator = Navigator.of(context);
  final ok = await repository.submit(form);
  if (!mounted) return;
  if (ok) navigator.pop(true);
}
```

`flutter/no-context-across-async-gap` blocks the unguarded form.

## Never navigate from build

`build()` can run at any time, including during a layout pass, and pushing a route from it either asserts
or pushes twice. Navigation is a response to an event: a callback, or a state-change listener (see
state-management.md).

## Type the arguments and the result

Untyped route arguments are a runtime cast waiting to fail:

```dart
// wrong — a caller that forgets the argument crashes on cast, not on compile
final args = ModalRoute.of(context)!.settings.arguments as OrderArgs;

// right: constructor arguments, or a typed route from the router package
Navigator.of(context).push(MaterialPageRoute(builder: (_) => OrderScreen(orderId: id)));
```

`Navigator.push` returns `Future<T?>` — the `?` is real: the user can dismiss with the system back gesture
and you get `null`. Type it and handle the null case.

```dart
final Order? created = await navigator.push<Order>(...);
if (!mounted || created == null) return;
```

## Pass identifiers, not loaded objects, across screens

A pushed screen that receives a fully loaded entity renders stale data when the source changes underneath
it, and cannot be reached from a deep link or a notification tap where only an id exists. Pass the id and
let the destination load — that also makes the route restorable.

## Do not reuse the same context after a pop

After `Navigator.pop()`, the popping widget's context is on its way out. Anything the caller wants to do
next — showing a snackbar, refreshing a list — belongs on the side that stays alive, driven by the value
the `push` future returns.

## Dialogs and sheets are routes too

`showDialog`/`showModalBottomSheet` push a route and return a `Future<T?>`. The same rules apply: type the
result, check `mounted` after awaiting it, and use the dialog's own context inside the builder rather than
the outer one when popping it.

## Back behaviour

If a screen has unsaved work, intercept the back gesture (`PopScope` on recent Flutter, `WillPopScope` on
older — use whichever the project already uses) and confirm. Do not disable back without offering a way
out; on Android it is the system gesture, and a screen the user cannot leave is a bug report.
