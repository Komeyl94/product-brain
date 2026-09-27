# State management

## The choice is the project's, not yours

There is no company-wide answer. Open the nearest existing feature and copy its approach — Bloc/Cubit,
Riverpod, Provider, `ChangeNotifier`, or `setState` — including how it names files, where the state class
lives, and how the widget subscribes.

If the repository genuinely has no precedent (a brand new app), say so and ask which the team wants before
adding a dependency. Do not introduce a second state library into a codebase that already has one, and do
not migrate an existing feature to a different one as part of an unrelated task.

What follows applies whichever one is in use.

## State is immutable; rebuilds come from replacement

Mutating a field on the current state object and calling `notifyListeners()`/`emit()` with the same
instance usually does nothing: equality-based consumers see no change and skip the rebuild. Emit a new
object.

```dart
// wrong — same instance; a Bloc's emit will drop it, and == comparisons see no change
state.items.add(order);
emit(state);

// right
emit(state.copyWith(items: [...state.items, order]));
```

Give state classes value equality (`==`/`hashCode`, or the project's existing codegen) so consumers can
tell a real change from a no-op.

## Model loading and failure as states, not booleans

Three booleans (`isLoading`, `hasError`, `isEmpty`) allow eight combinations, six of which are nonsense,
and the UI ends up with a spinner over an error message. Use a sealed hierarchy and switch on it:

```dart
sealed class OrdersState {}
final class OrdersLoading extends OrdersState {}
final class OrdersLoaded extends OrdersState { OrdersLoaded(this.orders); final List<Order> orders; }
final class OrdersFailed extends OrdersState { OrdersFailed(this.message); final String message; }

Widget build(BuildContext context) => switch (state) {
      OrdersLoading() => const Center(child: CircularProgressIndicator()),
      OrdersLoaded(:final orders) => OrdersList(orders: orders),
      OrdersFailed(:final message) => ErrorView(message: message),
    };
```

Dart's exhaustiveness checking on a `sealed` class means adding a fourth state produces a compile error at
every consumer, which is exactly what you want.

## Business logic lives outside the widget tree

A widget decides what to show. It does not decide what a discount is, retry a request, or parse a response.
Put that in the notifier/bloc/service so it can be tested without pumping a widget — and so the second
screen that needs it does not copy it.

The widget layer's job is: read state, render, send events. No `await` chains in `onPressed` that then
`setState` three times.

## Do not store BuildContext, and keep state out of globals

Holding a `BuildContext` in a field of a controller outlives the widget and crashes or leaks. Pass context
in at the call site, or expose a stream/callback the widget listens to.

Mutable global singletons for app state (`static User? currentUser`) are invisible to tests, survive
between tests, and cannot be scoped to a logged-out session. Inject the dependency instead, however the
project does injection.

## Scope the rebuild

Subscribing to the whole state at the top of a screen rebuilds the whole screen for a change to one field.
Subscribe as deep in the tree as possible, and select the narrowest slice the API allows (`BlocSelector`,
`context.select`, `ref.watch(provider.select(...))`, a `ValueListenableBuilder` around one widget).

## Side effects belong in a listener, not in build

Navigation, snackbars and dialogs triggered by a state change go through the library's listener hook
(`BlocListener`, `ref.listen`, an explicit listener) — never in `build()`, which may run again and fire the
effect twice. See async.md for the `mounted` rules that apply to those callbacks.
