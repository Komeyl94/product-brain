# PHP debugging output

`php/no-debug-output` blocks `var_dump`, `print_r`, `var_export`, `dd`, `dump`, `ray` and
`xdebug_break` in any `.php` file — tests included, because a `dd()` left in a test suite
truncates the run and the pipeline reports a pass on half the assertions.

## What actually goes wrong in production

These write to the output stream, which in a web request is the response body:

- A `var_dump` in an API path emits text **before** the JSON. The response is no longer
  valid JSON, and the frontend's parse error tells you nothing about where it came from.
- Output flushed early sends headers, so every `header()` call after it — content type,
  a redirect, a `Set-Cookie` for the session — is silently dropped.
- `dd()` in a queued job kills the worker process mid-job. The job is neither completed
  nor released, so it sits reserved until the visibility timeout expires and then runs
  again. Side effects that already ran, run twice.
- The dump prints whatever you handed it. `dd($user)` in Laravel renders the full model
  including `password`, `remember_token` and any API credentials on the record, into a
  page that may well be cached or captured by an error tracker.

## What to write instead

```php
// wrong
dd($order->toArray());
var_dump($response);

// right — structured, filtered by level, goes where logs go
Log::debug('Order totals recalculated', [
    'order_id' => $order->id,
    'total_cents' => $order->total_cents,
]);
```

Pass context as an array rather than interpolating it: the log handler serialises it, the
aggregator makes it searchable, and you can drop a key that should not be recorded.

For interactive debugging, use a real breakpoint from the IDE against Xdebug. `ray()` and
`dump()` are fine while you are working — they just must not survive the commit. Check
before you push:

```bash
git diff --cached | grep -nE '\b(dd|dump|var_dump|print_r|ray)\('
```

## The one legitimate waiver

`var_export($value, true)` and `print_r($value, true)` return a string instead of printing
it, so they are occasionally the right way to render a value into a message:

```php
throw new RuntimeException('Unexpected shape: ' . var_export($shape, true)); // guardrail:allow
```

Prefer `json_encode` or a log context array. If you take the waiver, say why in your
reply, and make sure the value cannot contain credentials — exception messages travel
further than logs do.
