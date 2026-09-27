# Error handling

## Throw domain exceptions; do not return failure

`php/no-die-exit` and `php/no-debug-output` are enforced. What they cannot catch is a method that
signals failure by returning `null`, `false` or an empty collection — every caller then has to
remember to check, and one eventually will not.

```php
// Wrong — the caller gets null and carries on with a half-finished order
public function execute(Order $order): ?Allocation
{
    if ($order->isLocked()) { return null; }
}

// Right — the failure names itself and cannot be ignored
if ($order->isLocked()) {
    throw new OrderLockedException($order);
}
```

Reserve `abort(403)` / `abort(404)` for the HTTP layer. An Action that calls `abort()` cannot be
reused from a console command or a queued job, where there is no response to abort.

## Report and render in one place

Two valid shapes. Look at what the repo does and match it; do not run both.

**On the exception class** — behaviour next to the definition:

```php
class InvalidOrderException extends Exception
{
    public function render(Request $request): Response
    {
        return response()->view('errors.invalid-order', status: 422);
    }
}
```

**Centralised in `bootstrap/app.php`** — the whole picture in one file:

```php
->withExceptions(function (Exceptions $exceptions) {
    $exceptions->render(fn (InvalidOrderException $e, Request $r) => response()->view('errors.invalid-order', status: 422));
})
```

## Attach context at the throw site

```php
class InvalidOrderException extends Exception
{
    public function context(): array
    {
        return ['order_id' => $this->orderId, 'state' => $this->state->value];
    }
}
```

Laravel merges this into the log entry automatically. The alternative — reconstructing which order
failed from a stack trace — is what turns a five-minute incident into an hour.

Never put credentials, tokens or personal data in `context()`; it reaches the error tracker.

## Do not report what you do not act on

```php
class PaymentDeclinedException extends Exception implements ShouldntReport {}
```

A declined card is a business outcome, not an incident. Reporting it trains everyone to ignore the
alert channel, which is how the real failure gets missed.

For genuine errors that can spike, throttle rather than silence — one failing integration otherwise
floods the tracker and hides everything else. Enable `dontReportDuplicates()` so an exception
reported from nested catch blocks is logged once.

## Never swallow an exception

```php
// Wrong — the failure is now invisible and the caller believes it succeeded
try { $this->sync->execute($order); } catch (Throwable $e) {}
```

If a failure is genuinely tolerable, report it and continue explicitly:

```php
try {
    $this->sync->execute($order);
} catch (SyncUnavailableException $e) {
    report($e);
    Context::add('sync_skipped', true);
}
```

Catch the narrowest type that can actually be thrown. `catch (Throwable)` also catches the
`TypeError` from your own bug.

## API routes must render JSON

Laravel decides by the `Accept` header, and plenty of clients do not send one — so an API consumer
gets an HTML error page and a parse failure instead of a status code.

```php
$exceptions->shouldRenderJsonWhen(fn (Request $r, Throwable $e) => $r->is('api/*') || $r->expectsJson());
```

Keep the error body shape identical across endpoints: a code the client can branch on, a message it
can show, and field errors keyed exactly as the request keyed them.

## Failures the user causes

Validation failures, permission denials and conflicting state are expected outcomes, not errors.
Return them as a redirect with the error attached to the field it belongs to, or a 422 the frontend
can map. Do not log them at error level; the noise buries the incidents that matter.

## Transactions and partial failure

A guard that throws inside `DB::transaction()` rolls back cleanly. A guard that throws *after* the
transaction commits leaves the write in place — which is why guards belong inside the closure. Side
effects that cannot be rolled back (an email, a webhook, a payment capture) go after the commit,
never inside it: the transaction can still fail, and the email cannot be unsent.
