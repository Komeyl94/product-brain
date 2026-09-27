# Types and null safety

## `dynamic` stops at the JSON boundary

`flutter/no-dynamic` blocks `dynamic` declarations. It deliberately allows a `Map<String, dynamic>`
parameter named `json` or `data`, because that is the one honest use: the shape coming off the wire really
is unknown until you parse it. Everything past that line is typed.

```dart
// wrong — dynamic spreads, and the failure surfaces three screens later as a cast error
final data = jsonDecode(response.body);
final name = data['customer']['name'];

// right — parse once, at the edge, into a real type
factory Order.fromJson(Map<String, dynamic> json) => Order(
      id: json['id'] as int,
      reference: json['reference'] as String,
      placedAt: DateTime.parse(json['placed_at'] as String),
    );
```

Cast each field explicitly at the boundary so a malformed payload fails there, with the field name in the
stack trace, instead of somewhere in the UI. Prefer whatever serialisation approach the project already
uses (hand-written `fromJson`, `json_serializable`, `freezed`) over introducing a new one.

`Object?` with an explicit narrowing check is the right type for a genuinely unknown value — it forces the
check, where `dynamic` silently permits any call.

## Nullability means something; do not erase it

- `!` asserts a value is non-null and crashes if it is not. Each one is a claim you are making about
  runtime. Use a null check, `?.`, or `??` instead; keep `!` for cases you can justify in one sentence.
- `late` defers the null check to runtime. `late final x = expr;` (lazy initialisation) is fine.
  `late Foo x;` assigned later in a lifecycle method is a `LateInitializationError` waiting for the path
  where it is not assigned.
- A nullable field that is never null in practice forces a check at every call site. Make it non-nullable
  with a required constructor argument.

## Sealed classes and exhaustive switches

Dart's pattern matching checks exhaustiveness on `sealed` hierarchies and enums, so adding a case produces
compile errors at every consumer rather than a silent fallthrough.

```dart
sealed class Result<T> {}
final class Ok<T> extends Result<T> { const Ok(this.value); final T value; }
final class Err<T> extends Result<T> { const Err(this.message); final String message; }
```

Avoid a `default:` clause in a switch over an enum or sealed type — it is what turns "the compiler will
tell me" into "nothing happened at runtime".

Enums carry data and behaviour; a bare `String` status compared with `==` across the codebase does not:

```dart
enum OrderStatus {
  draft('Draft'), paid('Paid'), shipped('Shipped');
  const OrderStatus(this.label);
  final String label;
}
```

## Analyzer and logging

`flutter/no-analyzer-ignore` blocks every `// ignore:` comment and `flutter/no-print` blocks `print()`.
Both are their own topic: see analysis.md and logging.md.

## Immutability by default

`final` on every field and local that is not reassigned. Prefer `const` constructors for models and value
objects — a const model can be a const widget argument, which is what makes the rebuild skipping in
performance.md possible. Do not expose a mutable `List` field and let callers mutate it; expose an
unmodifiable view or return a copy.
