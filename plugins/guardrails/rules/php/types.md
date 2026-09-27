# PHP types

`php/no-mixed-type` blocks `mixed` as a **return type** or a **property type**:

```php
public function resolve(): mixed          // blocked
private mixed $payload;                   // blocked
protected ?mixed $cache = null;           // blocked
```

It is gated: it only fires in repositories that have already adopted
`declare(strict_types=1)` across most of their PHP files. A legacy repo does not get
nagged. It also skips test files.

## Parameters are deliberately not flagged

`mixed $value` as a parameter passes, and that is not an oversight. Interfaces you do not
own require it:

```php
// Laravel — the signature is fixed by ValidationRule
public function validate(string $attribute, mixed $value, Closure $fail): void

// Spatie query builder filters — same situation
public function __invoke(Builder $query, mixed $value, string $property): void
```

Narrowing a parameter below the interface's type is a fatal error at class load, so a rule
that flagged these would be demanding broken code — and a guardrail that is wrong in a
common case teaches people the guardrail is wrong.

## What to write instead

Return types and properties are yours, so declare what actually comes back:

```php
// wrong
public function setting(string $key): mixed

// right — the real set
public function setting(string $key): string|int|bool|null
```

If the union is wide because the method does several jobs, split the method. If the shape
is an array, describe it for PHPStan rather than giving up:

```php
/** @return array{id: int, email: string, roles: list<string>} */
public function profile(): array
```

For a container, use a `@template` so the caller keeps its type (`@param class-string<T>`,
`@return T`). Deserialised payloads become a DTO (`spatie/laravel-data`) at the boundary,
not a `mixed` passed inward. Genuinely unknown input is `string` or `array` plus
narrowing.

## Why it is worth blocking

`mixed` is not "any type" to PHPStan at level 9 — it is a value you may do nothing with
until you narrow it, so every call site downstream either fails analysis or gets its own
ignore. One `mixed` return therefore spreads as a trail of baseline entries through code
that had nothing wrong with it. The type is also not enforced at runtime in any useful
sense, so the error you were avoiding still arrives, just later and further away.

## Overriding

This rule is `overridable`. A repository mid-migration can switch it off:

```json
{ "rules": { "php/no-mixed-type": "off" } }
```

That is repo-wide and permanent until someone removes it, which is the cost. Prefer a
line waiver (`// guardrail:allow`, with a reason) for the one method that genuinely cannot
be typed yet.
