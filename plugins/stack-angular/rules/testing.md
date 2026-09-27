# Testing

## Which guardrails still apply in a spec

The engine treats a path as a test when it matches `*.spec.ts`, `*.test.ts`, or lives under
`test/`, `tests/`, `spec/` or `__tests__/`. In those files `ts/no-any`, `ts/no-console`,
`angular/no-unmanaged-subscribe` and `angular/prefer-inject` are skipped — a throwaway stub typed
`any` is not worth a fight.

Still enforced, everywhere: `core/no-hardcoded-secret`, `core/no-vendor-token`,
`core/no-private-key` (all unwaivable), `angular/no-bypass-security`, `angular/no-inner-html`,
`angular/no-removed-api`, `ts/no-ts-ignore`. A real API key in a fixture is the same leak as a real
API key in production code — use an obvious fake (`'test-token'`).

Skipped does not mean encouraged: prefer a typed builder over `as any` so the spec breaks when the
model changes, which is most of the value of having it.

## Setup follows the repo's era

```ts
// NgModule repo
TestBed.configureTestingModule({
  declarations: [OrderListComponent],
  imports: [ReactiveFormsModule],
  providers: [{ provide: OrderService, useValue: orderServiceStub }],
});
```

```ts
// standalone repo
TestBed.configureTestingModule({
  imports: [OrderListComponent],
  providers: [provideHttpClientTesting(), { provide: OrderService, useValue: orderServiceStub }],
});
```

A standalone component goes in `imports`, never `declarations` — the error message for getting it
wrong is unhelpful, so check the sibling spec first. `provideHttpClient(...)` plus
`provideHttpClientTesting()` replaces `HttpClientTestingModule` in v19+ repos.

## Signal inputs need `setInput`

```ts
// wrong — assigning over an InputSignal breaks the component silently
component.orderId = 'abc';
```

```ts
fixture.componentRef.setInput('orderId', 'abc');
fixture.detectChanges();
```

With `OnPush`, `fixture.detectChanges()` only re-renders when something actually notified — set
inputs through `setInput`, update signals through `set`/`update`, and replace object references
rather than mutating them, exactly as in production code.

## Async

- `fakeAsync` + `tick(ms)` for timers and debounced streams; `flush()` to drain the queue.
  A `fakeAsync` test that ends with pending timers fails with "N timer(s) still in the queue" —
  that is a real leak in the component, not test noise to silence.
- `await fixture.whenStable()` for promises and real HTTP mocks.
- Never `setTimeout` in a spec to "wait for" something.

## HTTP

```ts
const http = TestBed.inject(HttpTestingController);
service.getOrders().subscribe((orders) => expect(orders.length).toBe(2));
http.expectOne(`${base}/orders`).flush({ data: [order1, order2] });
http.verify();           // in afterEach — fails on unexpected or outstanding requests
```

`verify()` is what catches the second request a refactor accidentally added.

## What to assert

Test behaviour through the component's public surface — rendered output and emitted outputs — not
private fields. Query by role or `data-testid`, not by CSS class: a class rename is a style change
and should not break a spec.

```ts
const rows = fixture.debugElement.queryAll(By.css('[data-testid="order-row"]'));
expect(rows).toHaveLength(2);
```

For Angular Material, use the component harnesses (`HarnessLoader` + `MatSelectHarness`) rather
than reaching into Material's DOM, which changes between versions.

## Running them

Read `package.json` before running anything: Nx repos use `nx test <project>` (add
`--watch=false`), others use `ng test`. Run the lint task too — several repos have ESLint rules
that CI enforces and the hook does not. Do not report a change as working on the basis of a build
alone.
