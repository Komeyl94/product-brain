# Async

## BuildContext after an await

This is the single most common crash-in-production bug in Flutter code, and
`flutter/no-context-across-async-gap` blocks it. While the future runs the user can press back, the route
can be popped, the list item can scroll out of a `ListView.builder`'s cache. The widget is then disposed
and its context is dead — using it throws, usually far from where the mistake was made.

```dart
// wrong
Future<void> _save() async {
  await repository.save(order);
  Navigator.of(context).pop();                                   // widget may be gone
  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved')));
}

// right — check after every await, or capture before it
Future<void> _save() async {
  final navigator = Navigator.of(context);
  final messenger = ScaffoldMessenger.of(context);
  await repository.save(order);
  if (!mounted) return;                                          // State.mounted
  navigator.pop();
  messenger.showSnackBar(const SnackBar(content: Text('Saved')));
}
```

Inside a `State`, use `if (!mounted) return;`. In a non-`State` callback that holds a context, use
`if (!context.mounted) return;` (Flutter 3.7+). Check after *every* await, not just the first — two awaits
need two checks. Capturing `Navigator`/`ScaffoldMessenger` before the await is better still: it removes the
lookup from the danger zone entirely.

Enable `use_build_context_synchronously` in `analysis_options.yaml` if it is not already on. The hook
catches the common shape; the analyzer catches the rest.

## Never create a Future inside build

`FutureBuilder(future: repository.load())` starts a new request on every rebuild — and rebuilds happen for
reasons unrelated to your data, so the endpoint gets hit repeatedly and the widget flickers back to its
loading state.

```dart
// right: created once
late final Future<List<Order>> _orders = repository.load();   // in the State, not in build
```

The same applies to `StreamBuilder`. If the project has a state management library, prefer it over
`FutureBuilder` for anything that survives a rebuild.

## Every subscription and timer is cancelled

```dart
StreamSubscription<Order>? _sub;

@override
void initState() {
  super.initState();
  _sub = repository.updates().listen(_onUpdate);
}

@override
void dispose() {
  _sub?.cancel();
  super.dispose();
}
```

An uncancelled subscription calls `setState` after dispose, which throws, and keeps the whole widget
subtree alive in memory. The same holds for `Timer`, `AnimationController`, and any listener added with
`addListener`.

## Do not fire and forget

`someFuture()` without `await` or `unawaited()` discards errors: the exception surfaces as an unhandled
async error with no stack pointing at your code. Await it, or mark the intent explicitly with
`unawaited(...)` from `dart:async` and handle failure inside.

`async` in a callback that expects `void` (`onPressed: () async { ... }`) is fine, but the body must catch
its own errors — nothing upstream will.

## Handle failure where you can say something about it

```dart
try {
  await repository.save(order);
} on SocketException {
  emit(const OrdersFailed('No connection.'));
} on ApiException catch (e) {
  emit(OrdersFailed(e.userMessage));
}
```

Catch specific types. A bare `catch (e)` that shows `e.toString()` to the user leaks internals and hides
programming errors that should crash loudly in debug. Never catch and ignore.

## Keep the UI isolate free

A long loop, a large JSON parse or an image transform on the UI isolate drops frames — it does not matter
that the function is `async`, since `async` does not mean "on another thread". Move real CPU work to
`compute()` or a spawned isolate. Anything above roughly 16ms will be visible.

## Concurrency

Debounce user-driven requests (search-as-you-type) and guard against overlapping submissions — disable the
button, or track an in-flight flag — otherwise a double tap creates two orders. Responses can arrive out of
order: when a newer request has started, discard the older response rather than rendering it.
