# Configuration and named values

## `env()` lives only in `config/`

Enforced by `laravel/no-env-outside-config`. The failure it prevents is specific and silent: once
`php artisan config:cache` runs — which every production deploy does — the `.env` file is no longer
read, and `env('API_KEY')` outside a config file returns `null`. Not an error. A `null` that flows
into an HTTP client and produces a 401 from a third party at 3am.

```php
// config/services.php
'stripe' => ['key' => env('STRIPE_KEY')],

// anywhere else
config('services.stripe.key')
```

Every new environment variable needs three things in the same change: the `config/` entry, the
`.env.example` line, and the deployment secret. A variable that exists only in your local `.env`
works for you and nobody else.

## Environment checks

```php
// Wrong — breaks under config:cache, same as above
if (env('APP_ENV') === 'production')

// Right
if (app()->isProduction())
if (App::environment(['staging', 'production']))
```

## Domain values are named once

A string or number that carries domain meaning — a status, a role, a permission, a threshold, an
operation name — is defined once and referenced. In order of preference:

1. **A backed enum** (`app/Enums/*Enum.php`) when the value is one of a closed set. This is the
   default.
2. **A class constant** when the value belongs to exactly one class and has no siblings.
3. **`config()`** when it is deployment-dependent: a limit, a timeout, a feature flag.

```php
// Wrong — the role name is invented at the call site, and the next caller invents it again
if ($role->name !== 'admin') {

// Right
if ($role->name !== SystemRoleEnum::ADMIN->value) {
```

## Type the parameter rather than naming the literal

When the magic value is an argument, extracting a constant fixes one call site. Typing the receiving
parameter fixes every call site, including the ones written next month.

```php
// Documents the intent; the next caller can still pass 'demot'
public function execute(User $user, string $operation): void

// Enforces it; a raw string is now a type error
public function execute(User $user, GuardOperationEnum $operation): void
```

Reach for a constant only when the parameter genuinely accepts free-form text.

When the same literal appears at several call sites, change the shared signature rather than
patching the line under review — otherwise its siblings stay identical and unreviewed.

## What is not a magic value

- Identity and neutral elements: `0`, `1`, `-1`, `''`, `[]`.
- Array keys and payload field names in a DTO factory or a log array.
- A test fixture's own data: `'Old Name'`, `'new@example.com'`.
- A value used once, in the place it is defined, where a name would only restate it.

`const NAME = 'name';` is noise. Do not wrap a value in a constant to satisfy the letter of this rule.

Static analysis catches only a fraction of this — PHPStan rules of this kind typically inspect `===`
with a literal on one side, so `!==`, call arguments, array values and `match` arms all pass
unchallenged. The check is yours.

## Enum shape

Backed string enums, singular name with an `Enum` suffix, machine values lowercase. User-facing
text comes from a `label()` method, never from the case value — the moment a value is rendered
directly, renaming the case becomes a user-visible change.

```php
enum ProductStatusEnum: string
{
    case Draft = 'draft';
    case Published = 'published';

    public function label(): string
    {
        return match ($this) {
            self::Draft => __('products.status.draft'),
            self::Published => __('products.status.published'),
        };
    }
}
```

## Config file conventions

Snake_case filenames (`google_calendar.php`). Every key gets a sensible default so a missing
environment variable degrades predictably instead of returning `null`. Config files are the one
place where explanatory comments are expected — write them there rather than in application code.
