# Page props

## A model is never a prop

`inertia/no-raw-model-prop` blocks it. The reason is not style: `Inertia::render('X', ['user' => $user])`
serialises the model through `toArray()`, so the page receives every column that is not in `$hidden`
— including the internal primary key, timestamps, foreign keys, soft-delete markers, and any column
added by a later migration that nobody thought about. Adding a `notes` column to `users` silently
ships it to the browser.

Pass a DTO that names exactly what the view needs.

```php
// Wrong
Inertia::render('Products/Show', ['product' => $product]);

// Right
Inertia::render('Products/Show', ['product' => ProductDetailData::fromModel($product)]);
```

The same applies to collections and paginators — map every row:

```php
$paginator->through(fn (Product $p) => ProductOverviewRowData::fromModel($p));
```

## DTO naming by role, not by model

One model usually needs several DTOs, because a list row and a detail page want different fields.

| Role | Name |
| --- | --- |
| List rows | `ProductOverviewData` / `ProductRowData` |
| Detail page | `ProductDetailData` |
| Inbound form | `CreateOrUpdateProductFormData` |
| Outbound integration payload | `ProductRequestData` |

A single `ProductData` reused everywhere grows to the union of all callers' needs, which is how a
list endpoint ends up shipping a detail page's worth of data per row.

## Expose the public identifier only

DTOs carry the external key (ULID/UUID), never the internal integer primary key. Route helpers,
form payloads and table row keys all use it. See `eloquent.md` in the Laravel plugin for the model
side.

## The generated types are the contract

Every DTO and enum that reaches the frontend is marked `#[TypeScript]` and transformed into the
`App.Data.*` / `App.Enums.*` namespaces. Consume them directly.

```tsx
// Wrong — a hand-written duplicate that silently diverges the next time the DTO changes
type Product = { ulid: string; name: string; status: 'draft' | 'published' };

// Right
App.Data.Products.ProductOverviewRowData
App.Enums.ProductStatusEnum
```

Never hand-write a union that duplicates a PHP enum. Regenerate after every DTO or enum change,
then run the type check — a stale generated file is the one failure mode that looks fine in the
editor and breaks at runtime.

## Enum labels and options come from the server

Machine values never reach the user. Pass the label map or the option list as a prop rather than
translating enum values in JSX:

```php
'statusOptions' => ProductStatusEnum::toOptionsArray(),   // [{value, label}] for selects
'statusLabels'  => ProductStatusEnum::toLabelArray(),     // [value => label] for badges
```

A `switch` in the frontend that maps `'draft'` to `"Draft"` is a second source of truth that will
not be updated when a case is added.

## Shared props are paid for by every page

Anything in `HandleInertiaRequests::share()` is serialised on every single request, including
partial reloads. Keep it to the user identity, the permission list, flash messages and locale. A
shared prop that runs a query — a notification count, a cart total — adds that query to every page
load in the application. If one page needs it, that page's controller should provide it.

## Deferred props for anything slow

```php
'stats' => Inertia::defer(fn () => $expensive->execute()),
```

The page renders immediately and the prop arrives in a follow-up request. Two obligations follow:
the component must handle the value being `undefined` on first render, and it must show a skeleton
rather than collapsing the layout — otherwise the page visibly jumps when data lands.

```tsx
{!stats ? <StatsSkeleton /> : <StatsPanel stats={stats} />}
```

`<WhenVisible data="stats">` defers until the element scrolls into view — right for below-the-fold
panels; wrong for anything the user may act on immediately.

## Partial reloads

When an interaction only changes one prop, request only that prop:

```tsx
router.reload({ only: ['products'] });
```

Without `only`, a filter change re-runs every prop callback on the page, including the expensive
ones the user cannot see. On the server side, a prop wrapped in a closure is skipped on a partial
reload that does not request it; a prop computed eagerly in the array is not — so compute expensive
props inside closures.

## Flash messages

Flash through the session and read it from a shared prop; do not invent a per-page success prop.
One toast system reading one shared key keeps success feedback consistent across the app.

```php
return to_route('products.index')->with('success', __('products.updated'));
```
