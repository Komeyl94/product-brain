# TypeScript debugging output

`ts/no-console` blocks `console.log`, `console.debug`, `console.info` and `console.trace`
in `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` and `.cjs`. Test files are skipped.

`console.warn` and `console.error` are deliberately allowed — they are the two levels that
mean something in production, and stripping them would remove the only signal a browser
error reporter has.

## Why the four blocked levels matter

They reach the production bundle. Nothing strips them by default in an Angular or Vite
build, so:

- **Whatever you logged is readable by the user and by every browser extension on the
  page.** `console.log(response)` on an auth call prints the access token; on a profile
  call it prints the full user record. This is the usual way a token ends up in a support
  screenshot.
- **The console retains a live reference to every object you pass**, so a logged component
  or a logged large response cannot be garbage-collected while devtools has been opened.
  A log in a subscription or a render path turns into a real leak.
- **Logging in a hot path is slow** when devtools is open — serialising an object on every
  change-detection cycle or every scroll event is measurable.
- They are noise that trains everyone to ignore the console, which is where the actual
  errors are.

## What to write instead

Remove it. Most `console.log` calls exist to answer a question that has since been
answered.

If the information is worth keeping, route it through the application's logger so a level
and a destination apply:

```ts
// wrong
console.log('cart updated', cart);

// right
this.logger.debug('cart updated', { itemCount: cart.items.length });
```

Log identifiers and counts, not whole objects — the object is where the credentials and
the personal data are.

For a genuine unexpected failure, `console.error` passes the rule and is the right call,
usually alongside reporting it:

```ts
catch (error) {
  console.error('Failed to load invoices', error);
  this.errorReporter.capture(error);
}
```

For interactive debugging use a `debugger` statement or a source-mapped breakpoint, not a
log — neither survives into a commit by accident, because the first thing that happens is
that it stops.

## Waivers

Waivable, not overridable. A CLI script, a build tool or a seed script writing to stdout
is the realistic case; those are usually `.mjs` files outside the app, and a line waiver
with a stated reason is fine there.
