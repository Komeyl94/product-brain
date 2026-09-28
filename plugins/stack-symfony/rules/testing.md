# Testing

Symfony work is tested end to end with **Playwright** (`@playwright/test`) — not Symfony Panther and
not Cypress. This plugin does not prescribe unit, `KernelTestCase` or `WebTestCase` tests; if a repo
already has a PHPUnit suite, keep it passing and follow its existing style. If the repo already has a
Panther or Cypress suite, don't start a parallel one on your own — ask whether to migrate it; if it
has no E2E yet, set up Playwright.

## Setup

- `playwright.config.ts` at the repo root, specs in `tests/e2e/` as `*.spec.ts`.
- `baseURL` from the app URL, and a `webServer` entry that starts the app when it isn't already
  running (`symfony server:start --no-tls --port=8000`, or `php -S 127.0.0.1:8000 -t public`).
- Run in a dedicated **`e2e` environment** (`APP_ENV=e2e`, settings in `.env.e2e`) against its own
  database, never a developer's. Reset it in `globalSetup`:

  ```bash
  php bin/console doctrine:database:drop --force --if-exists --env=e2e
  php bin/console doctrine:database:create --env=e2e
  php bin/console doctrine:migrations:migrate --no-interaction --env=e2e
  php bin/console doctrine:fixtures:load --no-interaction --env=e2e   # if the repo uses fixtures
  ```

- **Messenger**: route async transports to `sync://` in the `e2e` environment, so a message's side
  effects have happened by the time the response returns. Otherwise the spec races a worker.
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

A Symfony API with no UI (API Platform or plain controllers) is still tested end to end — through
HTTP with Playwright's `request` fixture, against the running app and its `e2e` database:

```ts
import { test, expect } from '@playwright/test';

test('another user cannot read my order', async ({ playwright }) => {
  const owner = await playwright.request.newContext({ storageState: 'e2e/.auth/owner.json' });
  const other = await playwright.request.newContext({ storageState: 'e2e/.auth/other.json' });

  const { id } = await (await owner.post('/api/orders', { data: { sku: 'SKU-1', quantity: 2 } })).json();

  expect((await owner.get(`/api/orders/${id}`)).status()).toBe(200);
  expect((await other.get(`/api/orders/${id}`)).status()).toBe(403);
});
```

Authenticate once per persona in a setup project (store the session or token and reuse it); never
hardcode a real credential — read it from the environment.

## Rules

- **Locate by role, label or test id** — never CSS classes or XPath.
- **Web-first assertions only** — `await expect(locator).toBeVisible()` retries; never
  `page.waitForTimeout()`.
- **Every test stands alone** — no reliance on another test's data or order.
- **Own your data** — create what the test needs through the app or its API; don't depend on
  whatever happens to be in the database.
- **Cover the refusal paths too** — a guest, a user without the role, another user's record (a
  missing voter check is invisible if you only ever act as the owner), invalid input.
- **Mock only what you don't own** — `page.route()` for third-party services; exercise your own
  backend for real.
- **Debug with traces, not retries** — read the trace (`npx playwright show-trace`) instead of
  raising timeouts until a flaky test passes.

## Running

Use the repo's own E2E script or Makefile target if it has one; otherwise `npx playwright test`,
one file with `npx playwright test tests/e2e/orders.spec.ts`, and `--ui` to debug. First run on a
machine or in CI needs `npx playwright install --with-deps`. Never claim a change works without
running anything.
