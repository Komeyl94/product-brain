# Security

## Mass assignment

Every model declares `$fillable`. `laravel/no-unguarded-model` blocks `$guarded = []`. The judgment
it cannot make: `$fillable` must list only what a *user* may set. A column like `role_id`,
`is_admin`, `balance` or `status` is set by an Action, never by request input — leaving it in
`$fillable` means a crafted form field escalates privilege even though validation "passed",
because a rule for a field you never intended to accept is a rule nobody wrote.

## Authorize every mutating path — exactly once

Pick one place per ability and keep it there.

**Bare permission check** ("may this actor do this at all") belongs on the route:

```php
Route::put('/products/{product}', UpdateProductController::class)
    ->can(SystemPermissionEnum::CATALOG_PRODUCTS_EDIT);
```

**Record-specific logic** belongs in a policy, invoked from the controller:

```php
public function update(User $actor, User $target): bool
{
    return $actor->id !== $target->id;   // real logic: nobody edits their own role
}
```

Never write a policy method whose entire body is `return $user->can(PERMISSION)`. It duplicates the
route gate, has nothing distinct to test, and invites a matching redundant `Gate::authorize()` in
the controller. This duplication has been introduced and removed repeatedly in real repos,
almost always by copying a controller that already had it. Before adding a `Gate::authorize()` call
or a policy method, open the route file and check what gate is already declared; afterwards, grep
the ability name across `routes/`, `app/Http/Controllers/` and `app/Policies/` and delete every copy
but one.

Pass the permission enum case to `->can()`, not a raw string — a typo in a string gate fails open
in the sense that it names a permission nobody has, which is usually noticed, but the enum makes it
a compile-time error instead of a runtime 403 during QA.

## SQL injection

`laravel/no-raw-query-interpolation` blocks interpolated queries. When you genuinely need raw SQL,
bind:

```php
User::whereRaw('LOWER(name) = ?', [Str::lower($request->name)])->get();
```

Column and table names cannot be bound. If one has to be dynamic, validate it against an allowlist
of known columns — never against a regex.

## Output escaping

`{{ }}` escapes; `{!! !!}` does not. Only use the raw form on content you sanitised yourself in
this request. Storing "trusted" HTML and rendering it raw later is the standard stored-XSS shape —
the trust decision was made by whoever wrote the row, not by the renderer.

## Rate limit authentication and anything enumerable

```php
RateLimiter::for('login', fn (Request $r) => Limit::perMinute(5)->by($r->ip()));
Route::post('/login', LoginController::class)->middleware('throttle:login');
```

Also throttle password reset, email verification resend, invite acceptance and any endpoint that
answers "does this record exist" differently for hits and misses.

## Secrets

`laravel/no-env-outside-config` blocks `env()` in application code. Beyond the mechanics: never
commit a production `.env`, and never paste one into chat or a ticket. Use the platform's secret
store (or `php artisan env:encrypt`) and inject at runtime. A secret that has been in a repo's
history is compromised even after the commit is removed — rotate it, do not just delete it.

## Encrypt sensitive columns

```php
protected $hidden = ['api_key', 'api_secret'];

protected function casts(): array
{
    return ['api_key' => 'encrypted', 'api_secret' => 'encrypted'];
}
```

`$hidden` matters independently of the cast: without it, the value lands in any `toArray()` — which
includes log context, queue payloads and error-tracker breadcrumbs, not only JSON responses.

## Uploads

Store outside the public root unless the file is genuinely public. Serve private files through a
controller that authorizes the request, or a signed temporary URL — not by guessing that nobody
will find the path.

## Frontend permission flags are UX, never a boundary

A `permissions` prop that hides a button is a convenience. The server check is the security
control. Assume every route is called directly with a crafted payload, because eventually one is.

## Dependencies

Run `composer audit` in CI, not manually. A vulnerable transitive package is the one dependency
nobody remembers adding.
