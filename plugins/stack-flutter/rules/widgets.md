# Widgets

## Extract a widget class, not a `_buildX()` method

A method returning a `Widget` cannot be `const` and always re-runs when the enclosing `build()` runs. A
separate widget class with a `const` constructor lets Flutter compare the widget to the previous frame's,
find it identical, and skip rebuilding the whole subtree.

```dart
// wrong — the header rebuilds on every parent rebuild, forever
Widget _buildHeader() => const Padding(padding: EdgeInsets.all(16), child: Text('Orders'));

// right
class _OrdersHeader extends StatelessWidget {
  const _OrdersHeader();
  @override
  Widget build(BuildContext context) =>
      const Padding(padding: EdgeInsets.all(16), child: Text('Orders'));
}
```

The rule of thumb: if a `build()` method is longer than about 50 lines, or you are reaching for a
`_build*` helper, the piece you were about to extract is a widget.

## `const` everywhere it is accepted

`const` constructors are free at runtime and canonicalised at compile time, so the same const widget is one
object no matter how many times it appears. Make your own constructors `const` — a non-const constructor
denies `const` to every caller up the tree. That means `final` fields and no work in the constructor body.

## `build()` is pure

`build()` can run many times per second, at times you do not control (parent rebuild, media query change,
route animation). It must have no side effects:

- No network calls, no file I/O, no analytics events.
- No `setState`, no navigation, no `showDialog`.
- No object construction that is expensive or that must survive a rebuild — a `TextEditingController` or
  `AnimationController` created in `build()` is recreated every frame and leaks the old one.

One-shot work belongs in `initState`; work that needs the widget's dependencies belongs in
`didChangeDependencies`; work that must happen after the first frame goes in
`WidgetsBinding.instance.addPostFrameCallback`.

## Stateless until proven otherwise

Use `StatefulWidget` only when the widget itself owns mutable state that no one else needs (an animation
controller, a text field controller, an expansion toggle). Screen or feature state belongs in whatever the
project uses for state management — see state-management.md.

Every `State` that creates a disposable must dispose it:

```dart
@override
void dispose() {
  _controller.dispose();
  _subscription.cancel();
  _debounce?.cancel();
  super.dispose();
}
```

An undisposed `AnimationController` keeps a ticker alive and the framework asserts in debug; an undisposed
`StreamSubscription` keeps calling `setState` on a dead widget.

## Keys where identity matters

Without a key, Flutter matches children by position and type, so removing an item from a list of stateful
widgets makes the next item inherit the removed one's state — a checked checkbox appears to jump rows.
Give list items a `ValueKey` derived from the model's id whenever the list can reorder, insert or remove.

Do not scatter `GlobalKey`s to reach into another widget's state; they are expensive and usually indicate
state that should have been lifted.

## Layout

- `Expanded`/`Flexible` only inside a `Row`, `Column` or `Flex`. Anywhere else it throws at runtime.
- Do not put an unbounded-height scrollable inside another unbounded parent; give it bounded constraints
  or use slivers (see performance.md).
- Read sizes with `LayoutBuilder` rather than `MediaQuery.of(context).size` when you need the space the
  parent actually gives you — they differ inside padding, sheets and split views.
- `MediaQuery.sizeOf(context)` rebuilds only on size changes; `MediaQuery.of(context)` rebuilds on every
  media query change including the keyboard opening.

## Theme and localisation

Take colours and text styles from `Theme.of(context)`, not hardcoded `Color(0xFF...)` constants scattered
through widgets — dark mode is what breaks first. Never build a user-visible string by concatenation if
the project has a localisation setup; follow whatever the neighbouring screen does.
