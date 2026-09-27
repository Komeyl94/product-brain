# RxJS and subscription lifetime

## The order of preference

1. `async` pipe in the template — Angular subscribes and unsubscribes with the view.
2. `toSignal(source$, { initialValue })` — same guarantee, usable in TypeScript.
3. `firstValueFrom(source$)` in an `async` method that completes (guards, resolvers, one-shot
   submits).
4. `.subscribe()` piped through `takeUntilDestroyed()` — only when 1–3 genuinely do not fit.

An unmanaged subscription lives for the lifetime of the application: the component is destroyed,
the callback keeps running, it still touches `this`, and the whole component tree stays reachable
for the garbage collector. In a routed app that repeats on every navigation.

## What `angular/no-unmanaged-subscribe` actually checks

It looks at the `.subscribe(` line and the **6 lines above it**, and passes if that window
contains any of: `takeUntilDestroyed`, `takeUntil(`, `take(n)`, `first()`, `toSignal(`,
`firstValueFrom`, `lastValueFrom`, or `.add(`.

So a long pipe whose `takeUntilDestroyed()` sits ten lines up will be blocked even though the code
is correct. Fix it by moving the terminating operator last — which is also where it belongs, so it
cannot be bypassed by an operator that resubscribes:

```ts
// wrong — leaks, and the rule is right to block it
this.route.queryParams.subscribe((params) => this.load(params['id']));
```

```ts
// right
this.route.queryParams
  .pipe(takeUntilDestroyed(this.destroyRef))
  .subscribe((params) => this.load(params['id']));
```

```ts
// better — no subscription to manage at all
readonly id = toSignal(this.route.queryParams.pipe(map((p) => p['id'] ?? null)), {
  initialValue: null,
});
```

`takeUntilDestroyed()` with no argument only works in an injection context (a field initialiser or
the constructor). Called from `ngOnInit` it throws NG0203 — inject a `DestroyRef` and pass it:
`private readonly destroyRef = inject(DestroyRef)`.

In a repo that predates `takeUntilDestroyed`, the local `takeUntil(this.destroy$)` pattern with a
`Subject` completed in `ngOnDestroy` is correct and satisfies the rule. Follow the file.

## Operator choice that changes behaviour

- `switchMap` for reads driven by user input (search, filter, route param): it cancels the
  in-flight request, so a slow first response cannot overwrite a fast second one.
- `concatMap` for writes that must keep order.
- `exhaustMap` for submit buttons — ignores clicks while a request is in flight, which removes the
  double-submit bug without a disabled flag.
- `mergeMap` only when genuinely parallel and order-independent. It is the wrong default.

```ts
readonly results = toSignal(
  toObservable(this.query).pipe(
    debounceTime(300),
    distinctUntilChanged(),
    switchMap((q) => this.api.search(q)),
  ),
  { initialValue: [] },
);
```

## Errors terminate the stream

An error reaching the subscriber kills the subscription permanently: the search box stops working
after the first failed request and nothing in the UI says so.

```ts
// wrong — one 500 and this stream is dead
switchMap((q) => this.api.search(q))
```

```ts
// right — handle inside the inner observable so the outer stream survives
switchMap((q) => this.api.search(q).pipe(catchError(() => of([]))))
```

## Sharing and multicasting

`shareReplay(1)` never unsubscribes from its source — it keeps the HTTP request, interval or socket
alive forever. Use `shareReplay({ bufferSize: 1, refCount: true })` so it tears down when the last
subscriber leaves.

## Things that are always wrong

- Nested `subscribe()` inside a `subscribe()` — use `switchMap`/`concatMap`; nesting loses
  cancellation and error propagation.
- Calling `.subscribe()` only to assign to a field the template reads. That is `async` pipe or
  `toSignal()`.
- `.toPromise()` — removed. `firstValueFrom` / `lastValueFrom`.
- Subscribing to `valueChanges` or a router event without a terminating operator; both outlive the
  component.
- `setTimeout` to wait for a stream. Model the dependency with an operator.
