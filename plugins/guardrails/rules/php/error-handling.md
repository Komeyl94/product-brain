# PHP error handling

`php/no-die-exit` blocks `die` and `exit` in application code — `.php` files under `app/`
or `src/`. Scripts elsewhere (`bin/`, a standalone deploy helper) are not covered, because
there the process ending *is* the result.

## What the process skips on the way out

`exit` unwinds nothing. It runs `__destruct` and registered shutdown functions and then
stops, which means everything the framework does after your code is simply not done:

- **Middleware never completes.** Anything wrapped around the request — the transaction
  the middleware would commit, the session write, the CORS and security headers, the
  rate-limit counter decrement — is skipped. A `die()` inside a DB transaction leaves the
  connection to be rolled back by the server on close, so the write is lost with no error
  anywhere.
- **Nothing is logged.** There is no exception, so the handler never fires, the error
  tracker records nothing, and the request shows up as a 200 with a blank or truncated
  body. This is the hardest class of production bug to find: no stack trace, no entry,
  no correlation id.
- **In a queued worker it kills the worker.** The job is neither completed nor failed, it
  stays reserved until the timeout, then retries. The supervisor restarts the process and
  you lose whatever else that worker was holding.
- **In tests it ends the suite**, and PHPUnit reports what ran before it as the result.

## What to write instead

```php
// wrong
if (! $order->isPayable()) {
    die('Order not payable');
}

// right — the exception handler decides the status code and the log entry
if (! $order->isPayable()) {
    throw new OrderNotPayableException($order->id);
}
```

By context:

- **Guard clause in a controller or action** — throw a domain exception and map it in the
  exception handler, or `abort(403)` / `abort_if()` in Laravel, which throws
  `HttpException` rather than halting.
- **Impossible state** — `throw new LogicException('…')`. It is a bug; make it loud and
  traceable rather than silent.
- **Console command** — return the exit code: `return self::FAILURE;`. The command still
  gets its teardown, its output buffer flushed, and a usable exit status.
- **Queued job** — `$this->fail($exception);` so the job lands in `failed_jobs` with its
  payload and the worker keeps running.
- **Early return of a response** — return it. A controller returning a `Response` runs the
  full middleware stack on the way out; `die(json_encode(...))` does not.

## Waivers

Waivable, but the cases are narrow. A `die()` added while debugging is not one — remove
it. If you take a waiver, name the reason in your reply.
