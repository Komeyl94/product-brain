# Architecture

## The layer stack

Every request moves through the same layers. Do not merge or skip one.

| Layer | Owns | Never contains |
| --- | --- | --- |
| Route | verb, URI, model binding, permission gate | logic |
| Controller | resolve input, call one Action, respond | queries, `save()`, `update()` |
| Form Request / Data class | validation rules, field labels | record-specific authorization |
| Action | business logic, queries, writes, transactions | `redirect()`, `Inertia::render()`, HTTP status |
| Model | relationships, casts, scopes, pure accessors | writes, `config()`, notifications |
| Policy | authorization that depends on the record | bare permission lookups |

`laravel/controller-no-direct-persistence` blocks the most common violation. What it cannot judge
is everything below.

## Controllers

Resolve, delegate, respond. Under ten lines per method.

```php
public function __invoke(UpdateProductRequest $request, Product $product, UpdateProductAction $update): RedirectResponse
{
    $update->execute($product, $request->validated());

    return to_route('products.index')->with('success', __('products.updated'));
}
```

### Pass input through; do not pre-resolve it

A controller that queries in order to build an Action's arguments has taken the business rule.

```php
// Wrong — the controller now owns "how ids become models", and a console command
// calling the same Action has to duplicate it
$items = Item::whereIn('ulid', $data->itemIds)->get();
$action->execute($items);

// Right — the Action resolves what it needs; every caller gets the same behaviour
$action->execute($data->itemIds);
```

## Action classes

One discrete operation per class, `final`, one public `execute()`, collaborators
constructor-injected. Name them `VerbNounAction` and keep the suffix consistent within a repo.

```php
final class UpdateProductAction
{
    public function __construct(
        private readonly SyncProductCategoriesAction $syncCategories,
    ) {}

    public function execute(Product $product, UpdateProductData $data): Product
    {
        return DB::transaction(function () use ($product, $data) {
            $product->update(['name' => $data->name, 'sku' => $data->sku]);
            $this->syncCategories->execute($product, $data->categoryIds);

            return $product->refresh();
        });
    }
}
```

Reads belong in Actions too, not only mutations — an index controller's paginated query lives in
`GetProductsAction`, so the same listing is reachable from an export command or a test without
going through HTTP.

Omit the constructor entirely when there are no collaborators; an empty `__construct()` is noise.

## Models hold structure, not behaviour

Relationships, `casts()`, query scopes, and accessors that only read `$this->*`. Anything that
writes to the database, reads `config()`, dispatches, or notifies moves to an Action.

```php
// Belongs on the model — pure, no side effects
public function isLocked(): bool
{
    return $this->locked_until !== null && $this->locked_until->isFuture();
}

// Belongs in an Action — writes
final class ResetLoginAttemptsAction
{
    public function execute(User $user): void
    {
        $user->forceFill(['failed_login_attempts' => 0, 'locked_until' => null])->save();
    }
}
```

Why: a model method that writes cannot be exercised without the model's own persistence layer, so
it drags the database into every test that touches it. Worse, a model method calling another model
method creates coupling nothing can intercept — you cannot queue half of it, swap half of it, or
assert that only one half ran.

## Constructor injection only

Never `app()` or `resolve()` inside a class body. A service located at runtime is invisible to the
constructor signature, so nothing — not a reader, not a static analyser, not a test — can see the
dependency without reading every line of the method.

```php
// Wrong
$service = app(OrderService::class);

// Right
public function __construct(private readonly OrderService $service) {}
```

## Transactions

Wrap `execute()` in `DB::transaction()` when it writes to more than one table or composes more
than one collaborator Action. A single `create()`/`update()`/`save()` is already atomic — wrapping
it adds a transaction round-trip for nothing.

Guards belong **inside** the transaction, not before it: a check that runs before `DB::transaction()`
opens can pass, then have its premise invalidated by a concurrent write before the body commits.

## At most three parameters

When a method needs more identifying values, group the related ones into a value object.

```php
// Wrong — call sites become execute(1, 2, 'A', 60) with nothing to check the order
public function execute(int $nodeId, int $skuId, string $batchNumber, float $quantity): void

// Right — the three ids together identify one position
public function execute(InventoryPositionData $position, float $quantity): void
```

"Related" means the values together identify one thing. Do not invent a generic `options` or
`context` bag to hit the number. Constructor dependency injection is out of scope — injected
collaborators are resolved by type, not by call-site order. A Data class's own constructor is
exempt; holding many typed fields is its purpose.

## Depend on interfaces at system boundaries

Payment gateways, notification channels, third-party APIs. Bind the concrete class in a service
provider. Do not introduce an interface for a class with one implementation that lives inside the
application — that is indirection with no seam behind it.

## `defer()` versus a queued job

`defer(fn () => ...)` runs after the response is sent, in the same process. Use it for
fire-and-forget work that may be lost on a crash: analytics, page-view counters, cache warming.
Use a queued job when the work must survive a crash or needs retries.

## `Context` for request-scoped data

`Context::add('tenant_id', ...)` in middleware propagates automatically into queued jobs and log
entries, which removes a whole class of "pass the tenant down five constructors" plumbing. Use
`Context::addHidden()` for values that jobs need but logs must not show. Anything that must not
leave the process does not go in `Context` at all.
