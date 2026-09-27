# PHP style

## `php/require-strict-types`

Every PHP file starts with the declaration, immediately after the opening tag:

```php
<?php

declare(strict_types=1);

namespace App\Actions\Billing;
```

The rule is gated: it only fires in repositories where most PHP files already declare it,
so it never demands a sweep of a legacy codebase. It also only evaluates **whole-file**
writes — an edit that replaces part of a file has no `declare()` in it and is not
reported as missing one. If you are blocked, you are writing a new file, or replacing an
existing one and dropped the line.

## Why it belongs in every file, not most of them

`strict_types` is per-file and it governs the **call site**, not the declaration. A file
without it silently re-enables coercion for every call it makes, including calls into code
that is strict:

```php
// app/Services/Pricing.php — strict
public function charge(int $cents): void

// app/Http/Controllers/OrderController.php — no declare()
$pricing->charge('12.99');   // arrives as 12. No error. Twelve cents.
```

So a codebase that is 90% strict has no guarantee at all: the gap is wherever someone
forgot, and the failure is a wrong number rather than an exception. Coercion also runs in
both directions — `"1abc"` becomes `1` with a warning, `true` becomes `1`, `1.9` becomes
`1` — and every one of those has shipped as a data bug somewhere.

With the declaration present, the same call throws `TypeError` at the boundary, which is
the point: the caller converts deliberately.

```php
$pricing->charge((int) round((float) $request->input('amount') * 100));
```

## Placement details

- After `<?php`, before `namespace`, `use` or anything else — it must be the first
  statement or PHP fatals.
- One blank line either side. This matches PSR-12 and what the formatter will do anyway.
- Applies to test files, migrations, config files and console commands too. Anything
  with a `<?php` opening tag.
- A file that is pure HTML with no opening tag is not checked.
