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

## End-to-end tests: Playwright

E2E tests use **Playwright** (`@playwright/test`). Protractor is removed from Angular, and new E2E
work does not go in Cypress. If the repo already has a Cypress or Protractor suite, don't start a
parallel one on your own — ask whether to migrate it; if the repo has no E2E yet, set up Playwright.

Layout: a `playwright.config.ts` at the workspace root (or an `<app>-e2e` project in Nx) with
`baseURL` and a `webServer` entry that starts the app (`ng serve` / `nx serve`), and specs in `e2e/`
as `*.spec.ts`.

```ts
import { test, expect } from '@playwright/test';

test('user filters the order list', async ({ page }) => {
  await page.goto('/orders');
  await page.getByLabel('Status').selectOption('shipped');
  await expect(page.getByTestId('order-row')).toHaveCount(2);
});
```

- **Locate by role, label or test id** — `getByRole('button', { name: 'Save' })`, `getByLabel`,
  `getByTestId`. Never CSS classes or XPath: a class rename is a style change and must not break a test.
- **Web-first assertions only** — `await expect(locator).toBeVisible()` / `toHaveText()` retry until
  the UI settles. Never `page.waitForTimeout()` and never assert on a one-shot `isVisible()`.
- **Every test stands alone** — no reliance on another test's data or order. Log in once in a setup
  project and reuse `storageState`; don't click through the login form in every test.
- **Own your data** — create what the test needs (seeding, factories, an API call in a fixture) and
  don't depend on whatever happens to be in a shared database.
- **Mock only what you don't own** — `page.route()` for third-party services (payments, maps);
  exercise your own backend for real, or the test proves nothing about the seam.
- **Keep E2E for journeys** — sign-in, checkout, the flows a ticket's acceptance criteria describe.
  Logic and edge cases belong in unit/component tests, which are faster and more precise.
- **Debug with traces, not retries** — configure `trace: 'on-first-retry'` and read the trace
  (`npx playwright show-trace`) instead of raising timeouts until a flaky test passes.

Run: `npx playwright test` (or `ng e2e` / `nx e2e <project>-e2e` when the repo wires it), a single
file with `npx playwright test e2e/orders.spec.ts`, and `--ui` to debug. First run on a machine
or in CI needs `npx playwright install --with-deps`.

## Running them

Read `package.json` before running anything: Nx repos use `nx test <project>` (add
`--watch=false`), others use `ng test`; E2E runs as above. Run the lint task too — several repos have ESLint rules
that CI enforces and the hook does not. Do not report a change as working on the basis of a build
alone.
