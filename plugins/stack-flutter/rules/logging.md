# Logging

## `print` does not stay in debug

`flutter/no-print` blocks `print()` outside tests. It is not a style rule: `print` writes to the platform
log in release builds too. That output is visible to anyone with the device attached or reading a bug
report attachment, cannot be filtered or turned off per environment, carries no level or timestamp, and
never reaches crash reporting — so the one line you most want when triaging a production issue is exactly
the line you do not have.

```dart
// wrong
print('order ${order.id} failed: $e');

// right — the project's logger, with a level and the error attached
_log.warning('Order submission failed', e, stackTrace);
```

Use whatever logging the repository already has — check a neighbouring file before adding a package. If
there is genuinely none, `debugPrint` is acceptable for temporary local debugging (it is rate-limited so it
does not drop lines on Android), and it must be gone before the change is finished.

## Log levels mean something

- `severe`/`error`: the user's action failed and someone should look at it. Attach the error and the stack
  trace, not a string you built from them.
- `warning`: recovered, but unexpected — a retry succeeded, a fallback was used.
- `info`: significant state transitions (signed in, sync completed). Not per-frame, not per-item.
- `fine`/`debug`: off in release.

A log line per list item or per frame makes the log useless and costs real time on the UI isolate.

## Never log secrets or personal data

Tokens, passwords, full request and response bodies, email addresses, phone numbers, precise location. Once
a line reaches the crash reporter it has left the device and is retained by a third party, which is a data
protection problem rather than a debugging one. Log identifiers (`orderId: 41`), not payloads.

## Errors go to crash reporting, not just the console

If the project has a crash reporter (Sentry, Crashlytics, or its own endpoint), a caught error that the
user sees as a failure should be reported there as well as logged. An error that is only printed is an
error nobody will ever know about — the user is on their device, not your laptop.

Report the error object and the stack trace together; `catch (e)` without `StackTrace s` discards where it
came from:

```dart
try {
  await repository.submit(order);
} catch (e, s) {
  _log.severe('submit failed', e, s);
  await crashReporter.recordError(e, s);
  rethrow;
}
```

Do not report an error you have already handled as if it were fatal, and do not report the same error at
every layer it passes through — pick the layer that knows what it meant.
