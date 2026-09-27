# Templates

## Control flow: match the file, not the version

`angular/prefer-control-flow` fires only in repos on v17+ that have already adopted `@if`/`@for`
(three or more files, or no structural directives left at all). Below that gate, `*ngIf` and
`*ngFor` are the house style — keep using them, and keep `CommonModule` in the imports or module
that provides them.

In an adopted repo:

```html
@if (order(); as order) {
  <app-order-summary [order]="order" />
} @else {
  <app-empty-state message="No order selected" />
}

@for (line of order().lines; track line.id) {
  <app-order-line [line]="line" />
} @empty {
  <p>This order has no lines.</p>
}
```

Do not convert a template's control flow as a side effect of another change — the diff becomes
unreviewable and the migration belongs in its own commit.

## `track` is mandatory and the expression matters

`angular/for-requires-track` fires on every v17+ repo, gated only by version, because `@for`
without `track` is a compile error in Angular and a rendering bug conceptually: the whole list of
DOM nodes is destroyed and rebuilt on each change, which loses focus, scroll position, CSS
transitions and any component state inside the row.

```html
@for (item of items(); track item.id) { ... }        <!-- right: stable identity -->
@for (name of names(); track name) { ... }           <!-- fine for unique primitives -->
@for (row of rows(); track $index) { ... }           <!-- only for append-only/immutable lists -->
```

`track $index` on a reorderable or filterable list re-binds every row to the wrong data. Duplicate
track keys produce runtime error NG0955 — if ids can repeat, track a composite
(`track item.orderId + ':' + item.lineNo`).

The same applies to `*ngFor`: `trackBy` is not optional on lists that change.

## Nothing that computes in a binding

Every binding expression re-evaluates on every change-detection cycle — dozens of times per
interaction, per row.

```html
<!-- wrong: runs on every CD pass, allocates a new array each time, and breaks OnPush
     downstream because the reference is always new -->
<app-row *ngFor="let u of users" [badges]="getBadges(u)"></app-row>
<span>{{ formatTotal(order) }}</span>
```

```html
<!-- right -->
<app-row *ngFor="let u of decoratedUsers" [badges]="u.badges"></app-row>
<span>{{ total() }}</span>          <!-- computed() in the component -->
<span>{{ order.total | currency }}</span>   <!-- pure pipe: memoised by input -->
```

Getters are function calls too. A pure pipe is the right escape hatch for formatting; an impure
pipe is not (it runs as often as the getter did).

## `async` once per value

```html
<!-- wrong: three subscriptions, three HTTP requests -->
<div *ngIf="user$ | async">{{ (user$ | async)?.name }} — {{ (user$ | async)?.email }}</div>
```

```html
<!-- right -->
@if (user$ | async; as user) {
  <div>{{ user.name }} — {{ user.email }}</div>
}
```

Signals do not have this problem: reading `user()` repeatedly is free.

## No raw HTML

`angular/no-inner-html` blocks `[innerHTML]` and `angular/no-bypass-security` blocks
`bypassSecurityTrust*`. See `security.md` for what to do instead.

## Structure

- Keep the template dumb: bindings and events, no branching business logic. Anything with an `&&`
  chain longer than two terms belongs in a `computed()`.
- `@defer (on viewport)` for heavy below-the-fold blocks in v17+ repos that already use it.
- Do not bind `[style]` / `[class]` to a freshly built object literal; it is a new reference every
  cycle. Use `[class.is-active]="isActive()"` or `ngClass` with a `computed()` value.
- Event handlers call one component method. `(click)="a(); b(); flag = true"` hides logic from
  tests.
- `<ng-container>` for grouping without a DOM node; do not add a wrapper `<div>` that CSS then has
  to undo.
