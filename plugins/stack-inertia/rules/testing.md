# Testing

End-to-end tests of the real Laravel + React app. The general Laravel E2E setup is in
`stack-laravel`'s testing rule; this file adds what is specific to Inertia pages.

## End-to-end tests: Playwright

E2E tests use **Playwright** (`@playwright/test`) — not Laravel Dusk and not Cypress. If the repo
already has a Dusk or Cypress suite, don't start a parallel one on your own — ask whether to migrate
it; if the repo has no E2E yet, set up Playwright.

Layout: `playwright.config.ts` at the repo root with `baseURL` pointing at the app, specs in
`tests/e2e/` as `*.spec.ts`. The app must run against a **dedicated test database**, never the
developer's: reset and seed it in `globalSetup` (e.g. `php artisan migrate:fresh --seed --env=e2e`),
and let `webServer` start the app and Vite when they aren't already running.
The app is stateful, so run with `workers: 1` and `fullyParallel: false` unless every spec
creates fully isolated data.

```ts
import { test, expect } from '@playwright/test';

test('admin archives a product', async ({ page }) => {
  await page.goto('/products');
  await page.getByRole('row', { name: /Blue Chair/ }).getByRole('button', { name: 'Archive' }).click();
  await expect(page.getByRole('status')).toHaveText('Product archived');
  await expect(page.getByRole('row', { name: /Blue Chair/ })).toHaveCount(0);
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
- **Cover journeys and their failure paths** — sign-in, the flows a ticket's acceptance criteria
  describe, and what the user sees when validation or the server refuses.
- **Debug with traces, not retries** — configure `trace: 'retain-on-failure'`,
  `screenshot: 'only-on-failure'` and `forbidOnly: !!process.env.CI`, and read the trace
  (`npx playwright show-trace`) instead of raising timeouts until a flaky test passes.

Inertia-specific:

- An Inertia visit is an XHR, not a page load. Wait on the result the user sees
  (`expect(...).toBeVisible()`, `expect(page).toHaveURL(...)`), not on `load` events.
- Validation errors come back as props; assert the message next to the field
  (`getByText('The name field is required.')`), not a network response.
- Navigate with the same named routes the app uses where you can (the Wayfinder helpers resolve in
  Node), so a route change breaks the test at compile time instead of at runtime.

Run: `npx playwright test`, a single file with `npx playwright test tests/e2e/products.spec.ts`,
`--ui` to debug. First run on a machine or in CI needs `npx playwright install --with-deps`.
