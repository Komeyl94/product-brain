# Performance

Flutter has a 16ms budget per frame at 60Hz (8ms at 120Hz). Almost every jank report traces to one of the
items below. Measure in **profile mode** — debug mode is many times slower and its numbers mean nothing.

## Lists must be lazy

```dart
// wrong — builds and lays out every row, including the 900 off screen
ListView(children: orders.map(OrderTile.new).toList())

// right — builds only what is visible plus a small cache
ListView.builder(
  itemCount: orders.length,
  itemBuilder: (context, i) => OrderTile(order: orders[i]),
)
```

`shrinkWrap: true` defeats this: it forces the list to lay out all children to measure itself. It is the
usual "fix" for a nested-scrollable exception, and it turns a 1000-row list into a frozen screen. The right
fix is bounded constraints — `Expanded`, a fixed height — or a `CustomScrollView` with slivers when a
header and a list must scroll together.

For long lists with varying content, give `itemExtent` or `prototypeItem` when rows have a uniform height:
the scrollbar and jump-to-index then need no measurement pass.

## `const` is the cheapest optimisation you have

A `const` widget is canonicalised, so on rebuild Flutter sees the identical instance and skips the subtree
entirely. Marking constructors `const` and using `const` at call sites costs nothing at runtime. See
widgets.md.

## Rebuild the smallest possible subtree

`setState` rebuilds the whole `State`'s `build()`. If one counter changes at the bottom of a long screen,
push the state down into a small widget, or use a `ValueListenableBuilder`/selector so only that widget
rebuilds.

For animations, pass the static part as `child` so it is built once instead of every frame:

```dart
AnimatedBuilder(
  animation: _controller,
  child: const ExpensiveStaticContent(),           // built once
  builder: (context, child) => Transform.rotate(angle: _controller.value, child: child),
)
```

## Expensive work out of build

No sorting, filtering, formatting or parsing inside `build()` — it runs on every frame during an animation.
Compute when the data changes and store the result. Anything genuinely heavy (large JSON, image processing,
crypto) goes to `compute()` so the UI isolate keeps producing frames.

## Painting cliffs

- `Opacity` with a value strictly between 0 and 1 forces `saveLayer`, which is expensive. Prefer a colour
  with an alpha channel, or `FadeTransition`/`AnimatedOpacity` which are optimised for the animated case.
- Clipping and shadows are not free. `ClipRRect` over a large animated subtree, or a `BoxShadow` on every
  row of a list, shows up immediately in the raster timeline.
- `RepaintBoundary` around a small, continuously animating region stops it from repainting its neighbours.
  Do not sprinkle it everywhere — each boundary is its own layer, and too many cost more than they save.

## Images

Decoding happens at the source resolution, so a 4000px photo in a 100px avatar allocates ~64MB and is the
most common out-of-memory crash on low-end Android devices. Constrain the decode:

```dart
Image.network(url, cacheWidth: 200, cacheHeight: 200)
```

Use `cached_network_image` or whatever the project already uses for network images rather than adding a
second caching layer. Prefer the right-sized asset over scaling a large one.

## Before optimising

Confirm the problem exists: run in profile mode, open DevTools, and look at which phase is over budget —
the fix for a slow build is different from the fix for a slow raster. An optimisation added on suspicion
adds complexity and often makes things slower (`RepaintBoundary`, `AutomaticKeepAlive`, and manual caching
all have real costs). Say what you measured in the merge request.
