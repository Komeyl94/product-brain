# State and signals

Signals are the default for new state **in a project that already uses them** (any repo or
folder where the sibling file uses `signal()`). In a `BehaviorSubject` repo,
keep `BehaviorSubject` — a single signal in an observable service forces every consumer to bridge
between two worlds.

## Writable, derived, and side-effecting

```ts
private readonly items = signal<CartItem[]>([]);
readonly total = computed(() => this.items().reduce((sum, i) => sum + i.price * i.qty, 0));
readonly isEmpty = computed(() => this.items().length === 0);
```

- `computed()` for anything derivable. It is lazy, cached, and cannot drift out of sync.
- `effect()` only for genuine side effects that leave the state graph: logging to analytics,
  writing `localStorage`, driving an imperative third-party widget.

```ts
// wrong — derived state in an effect: two sources of truth, an extra render, and an
// ordering bug the first time `items` is empty
effect(() => this.total.set(this.items().reduce(...)));
```

```ts
// right
readonly total = computed(() => this.items().reduce(...));
```

## Updating immutably

`signal.mutate()` was removed before signals stabilised — `angular/no-removed-api` blocks it.

```ts
// wrong
this.items.mutate((list) => list.push(item));
this.items().push(item);              // equally wrong: mutating the read value notifies nobody
```

```ts
// right
this.items.update((list) => [...list, item]);
this.items.update((list) => list.map((i) => (i.id === id ? { ...i, qty } : i)));
```

`set()` when the new value does not depend on the old one, `update()` when it does. Signals
compare by reference by default, so a mutated object re-assigned to itself does not notify.

## State shape

- One signal per independent fact, not one signal holding a big object you spread on every write —
  `computed()` consumers of the object re-run on every unrelated field change.
- Keep derived flags (`isEmpty`, `canSubmit`, `hasError`) as `computed()`, never as separate
  writable signals kept in sync by hand.
- Expose service state as `readonly` (`readonly items = this._items.asReadonly()`), so only the
  service that owns the state can write it.

## Bridging RxJS

```ts
readonly user = toSignal(this.auth.user$, { initialValue: null });
```

`toSignal()` without `initialValue` gives `T | undefined` and forces a null check everywhere —
pass an explicit initial value, or `requireSync: true` when the source is a `BehaviorSubject`
that has already emitted. `toSignal()` also manages the subscription for you, which is why
`angular/no-unmanaged-subscribe` accepts it.

`toObservable()` for the other direction, when an existing RxJS pipeline needs a signal as input.
Do not round-trip signal → observable → signal to reuse an operator; write a `computed()`.

## Query signals

In signals repos prefer `viewChild()` / `viewChildren()` / `contentChild()` over the decorator
queries: they are typed, and readable in `computed()` without lifecycle timing rules.

## Legacy state: what good looks like

In a `BehaviorSubject` service, keep the same discipline:

```ts
private readonly itemsSubject = new BehaviorSubject<CartItem[]>([]);
readonly items$ = this.itemsSubject.asObservable();
readonly total$ = this.items$.pipe(map((items) => items.reduce(...)));
```

Never expose the `BehaviorSubject` itself — a public subject lets any consumer push state into
another feature's service, and the bug surfaces far from the cause. Do not convert such a service
to signals as part of an unrelated ticket.

## Do not put component state in a service

A service field that exists only so two sibling components can talk is state with no owner and no
reset. Lift it to the shared parent, or give the service an explicit lifecycle (provided on a
routed component, reset in `ngOnDestroy`) and say which it is.
