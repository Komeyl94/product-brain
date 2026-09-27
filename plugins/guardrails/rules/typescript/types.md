# TypeScript types

Two rules, on `.ts` and `.tsx`.

## `ts/no-any`

Blocks `: any`, `as any`, `<any>`, `any[]` and `Array<any>`. Skips test files and `.d.ts`.

`any` is not "a type I have not narrowed yet" — it switches checking **off for everything
downstream**. One assertion on an API response removes type checking from every property
read, every call, every value derived from it, and the mistake surfaces as
`undefined is not a function` in a user's browser rather than as a compile error in CI.

```ts
// wrong
const user = res.data as any;
user.profile.displayName;        // compiles even if profile does not exist

// right
interface User { id: string; profile: { displayName: string } }
const user = res.data as User;   // or, better, type the call itself
```

Type the HTTP boundary, do not assert after it:

```ts
this.http.get<Invoice[]>('/api/invoices')      // not http.get(...)
```

When the shape is genuinely unknown, `unknown` is the tool. It behaves like `any` on the
way in and forces a check on the way out, which is exactly the trade you want:

```ts
function parse(raw: unknown): Settings {
  if (typeof raw !== 'object' || raw === null) throw new Error('Malformed settings');
  // narrow, or hand it to a zod/valibot schema and use the inferred type
}
```

Other replacements, in rough order of preference: the real interface; a generic
(`<T>(items: T[]) => T`); `Record<string, unknown>` for an open bag; a union of the cases
that actually occur; `object` or `unknown[]` when you only need the container.

For a third-party library with no types, write a narrow `.d.ts` declaring the two
functions you call. `.d.ts` files are exempt, which is the supported route.

## `ts/no-ts-ignore`

Blocks `@ts-ignore` and `@ts-nocheck`. The rule reads raw text, so it fires inside
comments — which is the whole point, since that is what these are.

Use `@ts-expect-error` with a reason:

```ts
// @ts-expect-error upstream types omit the `signal` option; remove when @acme/sdk >= 4.2
client.fetch(url, { signal });
```

The difference is not style. `@ts-ignore` suppresses an error and stays forever, silently
hiding the *next* error on that line too. `@ts-expect-error` **fails the build once the
error is gone**, so it deletes itself from your attention when the library is upgraded or
the type is fixed. A codebase accumulates `@ts-ignore`; it cannot accumulate
`@ts-expect-error`.

`@ts-nocheck` disables the whole file and has no expecting equivalent. There is no
situation in application code where it is the right answer.

## Waivers

Both are waivable, neither is overridable in `.guardrails.json`. For `ts/no-ts-ignore` a
waiver is almost never right — `@ts-expect-error` with a comment already is the escape
hatch, and it is a better one. For `ts/no-any`, say in your reply which type you could not
express and why.
