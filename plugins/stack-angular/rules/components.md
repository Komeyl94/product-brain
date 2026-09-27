# Components and services

Assumes you have already run `project-profile.md` and read the sibling file in the folder.

## Registration

Decided entirely by the repo's era — see `project-profile.md`. NgModule repo: declare it in the
owning module. Standalone repo: `imports: [...]` on the component itself, no new NgModule
(`angular/no-ngmodule` fires there).

Never half-migrate: a standalone component imported by an NgModule works, but a folder with both
styles is the state everybody has to reason about forever. Match the folder.

## OnPush on every new component

```ts
@Component({
  selector: 'app-order-summary',
  templateUrl: './order-summary.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
```

Most of these repos do not use OnPush yet, so nothing enforces it — new components still get it.
It is correct only when the component re-renders on reference change or signal change. With OnPush,
this silently stops updating the view:

```ts
// wrong — mutation in place, OnPush never learns anything changed
addLine(line: OrderLine): void {
  this.lines.push(line);
}
```

```ts
// right — new reference (or a signal, which notifies on its own)
addLine(line: OrderLine): void {
  this.lines = [...this.lines, line];
}
// or: this.lines.update((current) => [...current, line]);
```

If you reach for `ChangeDetectorRef.detectChanges()` or `markForCheck()` to make a view update,
the state model is wrong. The exceptions are a value arriving from outside the Angular zone
(a third-party widget callback, a raw `WebSocket` handler) — fix it by moving the value into a
signal instead.

## Dependency injection

`angular/prefer-inject` fires only where the repo already uses `inject()` (v16+, and `inject()` is
a meaningful share of DI). In those repos:

```ts
// wrong
constructor(private readonly orders: OrderService, private readonly router: Router) {}
```

```ts
// right
private readonly orders = inject(OrderService);
private readonly router = inject(Router);
```

In a constructor-DI repo, keep constructor parameter properties — the rule is silent there and
a lone `inject()` field is inconsistent, not modern.

`inject()` only works in an injection context: field initialisers, the constructor body, factory
functions, and functional guards/resolvers/interceptors. Calling it from `ngOnInit` or an event
handler throws NG0203. If you need a dependency lazily, capture the injector
(`private readonly injector = inject(Injector)`) and use `runInInjectionContext`.

## Inputs and outputs

Follow the file. In a signals repo:

```ts
readonly orderId = input.required<string>();
readonly compact = input(false, { transform: booleanAttribute });
readonly closed = output<void>();
readonly quantity = model(1);              // two-way: [(quantity)]
```

In a decorator repo `@Input()` / `@Output()` stays. Never mix both styles in one class — a signal
input read as `this.orderId` (the function, not the value) is a bug the compiler will not catch in
a template.

Signal inputs are read-only. To derive from one, use `computed()`; do not write back into it.

## Services

- `@Injectable({ providedIn: 'root' })` unless the service is genuinely per-route or per-component;
  a root service is tree-shakeable and needs no module wiring in either era.
- Provide a service on a component only when its lifetime must match that component's, and say so
  in a comment — otherwise it is an accidental singleton-per-instance.
- Services expose state as signals (signals repo) or observables (legacy repo). A service that
  exposes a raw mutable array lets every consumer break OnPush.
- Keep HTTP in a service, never in a component. See `http.md`.

## Lifecycle

- `ngOnInit` for work that needs inputs; the constructor runs before the first input is set.
- `ngOnDestroy` only for things Angular cannot clean up (timers, listeners on `window`, third-party
  instances). Subscriptions should not need it — see `rxjs.md`.
- Do not implement `ngOnChanges` in a signals component; use `computed()` or `effect()`.

## Types

No `any` — `ts/no-any` blocks it. That includes `as any` in a cast to silence a template error and
`any[]` for a list whose shape you have not modelled yet. Use the real interface, a generic, or
`unknown` plus narrowing. If a third-party type is genuinely wrong, type the boundary once in a
declaration file rather than spreading `any` through call sites.

`ts/no-ts-ignore` blocks `@ts-ignore` and `@ts-nocheck`. `@ts-expect-error` with a comment saying
why is allowed: it fails the build once the underlying problem is fixed, so it cannot rot.

`ts/no-console` blocks `console.log`/`debug`/`info`/`trace` — they reach the production browser
console. Route diagnostics through the app's logger service, or delete them.
