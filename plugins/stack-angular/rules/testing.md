# Testing

Angular work is tested end to end with **Playwright**. This plugin does not prescribe unit or
component tests (`TestBed`, Karma, Jest); if a repo already has them, keep them passing and follow
their existing style, but don't add a unit-test setup to a repo that has none.

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
- **Cover journeys and their failure paths** — sign-in, the flows a ticket's acceptance criteria
  describe, and what the user sees when validation or the server refuses. One spec per journey,
  named for what the user does.
- **Debug with traces, not retries** — configure `trace: 'retain-on-failure'`,
  `screenshot: 'only-on-failure'` and `forbidOnly: !!process.env.CI`, and read the trace
  (`npx playwright show-trace`) instead of raising timeouts until a flaky test passes.

Run: `npx playwright test` (or `ng e2e` / `nx e2e <project>-e2e` when the repo wires it), a single
file with `npx playwright test e2e/orders.spec.ts`, and `--ui` to debug. First run on a machine
or in CI needs `npx playwright install --with-deps`.

## Which guardrails still apply in a spec

The engine treats a path as a test when it matches `*.spec.ts`, `*.test.ts`, or lives under
`test/`, `tests/`, `spec/` or `__tests__/` — Playwright specs included. In those files `ts/no-any`,
`ts/no-console`, `angular/no-unmanaged-subscribe` and `angular/prefer-inject` are skipped.

Still enforced, everywhere: `core/no-hardcoded-secret`, `core/no-vendor-token`,
`core/no-private-key` (all unwaivable), `angular/no-bypass-security`, `angular/no-inner-html`,
`angular/no-removed-api`, `ts/no-ts-ignore`. A real password or API key in an E2E fixture is the same
leak as one in production code — read credentials from the environment (`process.env.E2E_PASSWORD`)
or use an obvious fake.

## Running them

Read `package.json` before running anything and use the repo's own E2E script if it has one. Run the
lint task too — several repos have ESLint rules that CI enforces and the hook does not. Do not report
a change as working on the basis of a build alone.
