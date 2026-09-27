# Testing

Pest 4 on PHPUnit, against PostgreSQL. If the repo's existing tests clearly follow a different
convention, match the file you are in — never mix two styles in one file.

## Layout

```
tests/
├── Pest.php          # bindings, global beforeEach, persona and fixture helpers
├── TestCase.php      # near-empty base class
├── Support/          # final helper classes: scenarios, payload builders, process racers
├── Assets/           # fixture files (CSV, XLSX, PDF, images)
├── Unit/             # one class at a time, folders mirror app/ layers (Actions/, Enums/, …)
│   └── ArchitectureTest.php
├── Feature/          # routes and commands end to end, folders mirror the product (Catalog/, Orders/, …)
├── Concurrency/      # real-process race tests (see below)
└── e2e/              # Playwright specs — see stack-inertia's testing rule
```

- **`Unit/` mirrors `app/` layers** and still hits the database — "unit" means "one class", not "no IO".
- **`Feature/` mirrors the product**: one folder per domain or area, driving real routes and commands.
- **Multi-step setup that several files share** goes in `tests/Support/` as a `final` class in the
  `Tests\Support` namespace (`OrderListScenario`, `AdjustmentPayload`), not copy-pasted arrange blocks.
- `phpunit.xml` defines one suite per top-level folder (`Unit`, `Feature`, `Concurrency`).

Generate with `php artisan make:test --pest <Name> --no-interaction`. The name must not repeat the
suite directory: `make:test --pest Feature/OrderTest` produces `tests/Feature/Feature/OrderTest.php`.

## `tests/Pest.php` is the one place for global setup

```php
pest()
    ->extend(TestCase::class)
    ->use(LazilyRefreshDatabase::class)
    ->beforeEach(function (): void {
        Http::preventStrayRequests();                     // no test may reach a real API
        app()['cache']->forget('spatie.permission.cache'); // if spatie/laravel-permission is used
    })
    ->in('Feature', 'Unit');

// Concurrency tests commit real rows, so no transaction wrapper there.
pest()->extend(TestCase::class)->in('Concurrency');
```

Global helper functions live here too, with a docblock each:

- **Persona helpers** named after the role a test acts as — `catalogAdmin()`, `tripViewer()` — each
  creating a user and granting an **explicit permission subset** through one shared
  `syncRoleAndPermissions($user, $role, [...])` helper. A test reads as "a trip viewer cannot create
  a trip", and the permission list lives in one place.
- **Request helpers** for an endpoint many tests post to (`postTrip($user, $payload)`), where keys
  left out of the payload are absent from the request, so a missing field can be tested as well as an
  invalid one.
- **Fixture builders** for third-party tables that ship no factories.

Keep `tests/TestCase.php` near-empty — at most a small helper that genuinely needs `$this`.

## Test style

```php
<?php

declare(strict_types=1);

use App\Models\Category;

uses()->group('categories.feature');

test('guests cannot create a category', function (): void {
    $this->post('/categories', ['name' => 'Dairy'])->assertRedirect('/login');
});

test('duplicate top-level category name is rejected', function (): void {
    $user = catalogAdmin();
    Category::factory()->create(['name' => 'Dairy']);

    $this->actingAs($user)->post('/categories', ['name' => 'Dairy'])
        ->assertInvalid(['name' => 'Duplicate top-level category name.']);
});
```

- **`test()`, not `it()` or `describe()`.** Names are plain sentences about behaviour. Add the
  ticket key when a test pins a specific fix: `test('an arrived line reads arrived - PROJ-926', …)`.
- **Typed closures**: `function (): void`, and `declare(strict_types=1);` in every test file.
- **One group per file**, dot-notation by area then layer: `categories.feature`,
  `orders.unit.actions`, `iam.unit`, `architecture`. Run a slice with `--group=orders.unit.actions`.
- **Unit tests resolve the class from the container** — `app(DeriveOrderLineStatusAction::class)->execute(...)`
  — and use `factory()->make()` (unsaved) when the code under test is pure.

## What every feature needs covered

Most production fixes are guards that were missing. For each route or Action assert at least:

1. **Guests** are redirected to login (or get 401 on JSON endpoints).
2. **A user without the permission** is refused (`assertForbidden()`), and **one with it** succeeds.
3. **The happy path** — the response *and* the persisted state (`assertDatabaseHas`, `assertModelExists`).
4. **Each validation rule** — `assertInvalid(['field' => 'the exact message'])`.
5. **The refusal path** — it refuses when a precondition fails and leaves no partial write behind.
6. **Side effects the domain promises** — an audit entry, a dispatched job, a sent mail.

```php
test('allocation is refused against a locked order', function (): void {
    $order = Order::factory()->locked()->create();

    expect(fn () => app(AllocateOrderAction::class)->execute($order))
        ->toThrow(OrderLockedException::class);

    expect($order->allocations()->count())->toBe(0);
});
```

For Inertia pages, assert the component and the props that matter:

```php
$response->assertInertia(fn ($page) => $page
    ->component('orders/index')
    ->has('orders.data', 2)
    ->where('filters.status', 'open')
);
```

## Factory states, never attribute soup

```php
// Wrong — the reader has to know what these columns mean together
User::factory()->create(['email_verified_at' => null, 'locked_until' => now()->addHour()]);

// Right
User::factory()->unverified()->locked()->create();
Inventory::factory()->ofSku($sku)->holding(60)->create();
```

Check the factory for an existing state before adding one — states name a business condition once.
Use `recycle()` when nested factories must share one instance.

## Fakes, time and the network

- Build models **before** `Event::fake()` / `Queue::fake()` — factories rely on model events.
- Control time with `$this->travelTo(...)` / `$this->freezeTime()`, never `sleep()`.
- `Http::preventStrayRequests()` is global (see `Pest.php`); fake the client per test with
  `Http::fake()` (or Saloon's `MockClient`) and assert on the request you would have sent.
- `phpunit.xml` forces safe drivers: `CACHE_STORE=array`, `QUEUE_CONNECTION=sync`,
  `MAIL_MAILER=array`, `SESSION_DRIVER=array`, `BCRYPT_ROUNDS=4`, and a dedicated test database.

## Assert against models and semantics

| Use | Instead of |
| --- | --- |
| `assertModelExists($user)` | `assertDatabaseHas('users', ['id' => $user->id])` |
| `assertSuccessful()` | `assertStatus(200)` |
| `assertForbidden()` | `assertStatus(403)` |
| `assertNotFound()` | `assertStatus(404)` |
| `assertInvalid(['field' => 'message'])` | `assertSessionHasErrors('field')` |

## Datasets for matrices

Permission matrices and validation variants use `->with([...])` — one test with a dataset beats
twelve near-identical tests that drift apart.

## Architecture tests are how the repo enforces its own rules

`tests/Unit/ArchitectureTest.php` holds one Pest arch test per layer contract, plus separate
`*ArchitectureTest.php` files for cross-cutting rules (audit coverage, enum validation):

```php
uses()->group('architecture');

test('no debugging code anywhere')
    ->expect(['dd', 'dump', 'var_dump', 'ray', 'exit', 'die', 'print_r'])
    ->not->toBeUsed();

test('actions are final')->expect('App\Actions')->toBeFinal();

// ExportThingsAction streams its response, so it cannot be queued. PROJ-835.
test('actions use QueueableAction trait')
    ->expect('App\Actions')
    ->toUseTrait(QueueableAction::class)
    ->ignoring(ExportThingsAction::class);
```

Every `->ignoring()` carries a comment with the reason and the ticket. When an arch test fails it
is telling you about a local rule — read it; never delete or weaken a test to make a change pass,
and never remove one without asking.

## Concurrency tests

Races (two users allocating the same stock) can't be proven inside one transaction. Tests in
`tests/Concurrency/` commit real fixtures, race real OS processes (e.g. two `php artisan` commands
started together through a `Tests\Support\ConcurrentProcess` helper), assert exactly one wins and
the loser gets a clear message, and clean up after themselves. Under `--parallel`, hand the child
processes the **connected** worker database, not the configured base name.

## Running

Use the repo's own targets — usually a Makefile that runs inside Docker — before bare `artisan`:

```bash
make test-filter filter=CreateCategory   # while iterating (or: php artisan test --compact --filter=CreateCategory)
make test-group group=orders.unit.actions
make test                                # before handing off: full suite, --parallel
```

Run the full suite with `--parallel` (a single process can run out of memory); `--profile` only works
serially. Parallel runs create one database per worker — the repo's clean target drops leftovers.
Run the narrow filter first, and never claim a change works without running anything.
