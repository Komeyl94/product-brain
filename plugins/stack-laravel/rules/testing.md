# Testing

## Match the repo's dialect

Pest supports `test()` and `it()`. Check a sibling test file and use the same one; a file mixing
both reads as two authors arguing. Same for `describe()` blocks — some repos forbid them
outright, so look before nesting.

Generate with `php artisan make:test --pest <Name> --no-interaction`. The `{name}` must not repeat
the suite directory: `make:test --pest Feature/OrderTest` produces `tests/Feature/Feature/OrderTest.php`.

Keep `tests/TestCase.php` empty and put shared helpers, bindings and macros in `tests/Pest.php`, so
there is one place to look for global test setup.

## Cover the refusal path, not just the happy path

Most production fixes in these repos are guards that were missing: a state that should have
blocked an allocation, an owner check that was never applied. A test that only asserts the success
case cannot fail when the guard is deleted.

For every Action, assert at least: it does the thing; it refuses when the precondition fails; and
it leaves no partial write behind when it refuses.

```php
it('refuses to allocate against a locked order', function (): void {
    $order = Order::factory()->locked()->create();

    expect(fn () => app(AllocateOrderAction::class)->execute($order))
        ->toThrow(OrderLockedException::class);

    expect($order->allocations()->count())->toBe(0);
});
```

## Factory states, never attribute arrays

```php
// Wrong — the reader has to know what these columns mean together
User::factory()->create(['email_verified_at' => null, 'locked_until' => now()->addHour()]);

// Right
User::factory()->unverified()->locked()->create();
```

Check the factory for an existing state before adding one. States name a business condition once,
so when the columns behind "locked" change, one file changes instead of forty.

Use `recycle()` when several nested factories must share one instance — without it each nested
factory creates its own, and a test asserting "the airline on the ticket equals the airline on the
flight" fails for reasons that have nothing to do with the code under test.

```php
Ticket::factory()->recycle(Airline::factory()->create())->create();
```

## Fake after you build

```php
// Wrong — factories rely on model events (UUID generation, slug creation);
// faking first produces models missing those fields
Event::fake();
$user = User::factory()->create();

// Right
$user = User::factory()->create();
Event::fake();
```

## Assert against models and semantics

| Use | Instead of |
| --- | --- |
| `assertModelExists($user)` | `assertDatabaseHas('users', ['id' => $user->id])` |
| `assertSuccessful()` | `assertStatus(200)` |
| `assertForbidden()` | `assertStatus(403)` |
| `assertNotFound()` | `assertStatus(404)` |

`assertStatus(200)` passes for a page that rendered an error inside a 200 response.

## Database

Prefer `LazilyRefreshDatabase` — it skips the migration run when the schema is already current,
which is most local runs. Tests are wrapped in a transaction and rolled back, so never rely on data
left behind by another test.

## No network in tests, ever

```php
Http::preventStrayRequests();   // in tests/Pest.php, globally
```

A test that reaches a real API is not a test — it fails when the network does, passes when the
third party is broken but returns 200, and leaks credentials into CI logs. Fake the client
(`Http::fake()`, Saloon's `MockClient`) and assert on the request you would have sent.

## Architecture tests are how a repo enforces its own rules

```php
arch('controllers')->expect('App\Http\Controllers')->toHaveSuffix('Controller')->toBeFinal();
```

They are cheap and they catch the conventions no linter knows about: policies that are bare
permission proxies, Data classes with an unvalidated enum property, Actions mutating a tracked
model without writing an audit row. When one fails, read it — it is documenting a local rule. Never
delete or weaken a test to make a change pass, and never remove a test without asking.

## Datasets for repetitive cases

Validation rules and permission matrices are the usual candidates. One test with a dataset beats
twelve near-identical tests that drift apart.

```php
it('rejects an invalid status', function (string $status): void {
    $this->putJson(route('products.update', $product), ['status' => $status])
        ->assertInvalid('status');
})->with(['', 'pending', 'PUBLISHED']);
```

## Running

```bash
php artisan test --compact --filter=UpdateProduct   # while iterating
php artisan test --compact                          # before handing off
```

Run the narrow filter first. Claiming a change works without running anything is the single most
common failure in agent-written Laravel changes.
