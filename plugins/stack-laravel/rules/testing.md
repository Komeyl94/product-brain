# Testing

Laravel work is tested end to end with **Playwright** (`@playwright/test`) — not Laravel Dusk and
not Cypress. This plugin does not prescribe unit or feature tests; if a repo already has a Pest or
PHPUnit suite, keep it passing and follow its existing style. If the repo already has a Dusk or
Cypress suite, don't start a parallel one on your own — ask whether to migrate it; if it has no E2E
yet, set up Playwright.

## Setup

- `playwright.config.ts` at the repo root, specs in `tests/e2e/` as `*.spec.ts`.
- `baseURL` from the app URL (e.g. `process.env.APP_URL`), and a `webServer` entry that starts the
  app (`php artisan serve`, plus Vite for a frontend) when it isn't already running.
- Run against a **dedicated E2E database**, never a developer's: reset and seed it in
  `globalSetup` (e.g. `php artisan migrate:fresh --seed --env=e2e`), with its own `.env.e2e`.
- The app is stateful, so use `workers: 1` and `fullyParallel: false` unless every spec creates fully
  isolated data.
- `trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'`, `forbidOnly: !!process.env.CI`.

## Web apps: browser specs

```ts
import { test, expect } from '@playwright/test';

test('a manager approves a pending order', async ({ page }) => {
  await page.goto('/orders?status=pending');
  await page.getByRole('row', { name: /ORD-1001/ }).getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByRole('status')).toHaveText('Order approved');
});
```

## API-only services: request specs

A Laravel API with no UI is still tested end to end — through HTTP with Playwright's `request`
fixture, against the running app and its E2E database:

```ts
import { test, expect } from '@playwright/test';

test('an order cannot be approved twice', async ({ request }) => {
  const created = await request.post('/api/orders', { data: { sku: 'SKU-1', quantity: 2 } });
  expect(created.status()).toBe(201);
  const { id } = await created.json();

  expect((await request.post(`/api/orders/${id}/approve`)).status()).toBe(200);
  expect((await request.post(`/api/orders/${id}/approve`)).status()).toBe(409);
});
```

Authenticate once in a setup project (store the session or token and reuse it); never hardcode a
real credential — read it from the environment.

## Rules

- **Locate by role, label or test id** — never CSS classes or XPath.
- **Web-first assertions only** — `await expect(locator).toBeVisible()` retries; never
  `page.waitForTimeout()`.
- **Every test stands alone** — no reliance on another test's data or order.
- **Own your data** — create what the test needs through the app or its API; don't depend on
  whatever happens to be in the database.
- **Cover the refusal paths too** — a guest, a user without the permission, invalid input, a
  precondition that fails. Most production fixes are guards that were missing.
- **Mock only what you don't own** — `page.route()` for third-party services; exercise your own
  backend for real.
- **Debug with traces, not retries** — read the trace (`npx playwright show-trace`) instead of
  raising timeouts until a flaky test passes.

## Running

Use the repo's own E2E script or Makefile target if it has one; otherwise `npx playwright test`,
one file with `npx playwright test tests/e2e/orders.spec.ts`, and `--ui` to debug. First run on a
machine or in CI needs `npx playwright install --with-deps`. Never claim a change works without
running anything.
