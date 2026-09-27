# Routing and navigation

## No URL literals in the frontend

`inertia/no-hardcoded-route` blocks them. Generate from the route definition instead — Wayfinder or
Ziggy, whichever the repo already uses.

```tsx
// Wrong — the route change that renames this path will not fail any build
<Link href={`/products/${product.ulid}/edit`}>Edit</Link>

// Right (Wayfinder)
import { edit } from '@/actions/App/Http/Controllers/ProductController'
<Link href={edit(product.ulid)}>Edit</Link>

// Right (Ziggy)
<Link href={route('products.edit', { product: product.ulid })}>Edit</Link>
```

The failure a literal causes is delayed and silent: renaming a route breaks a link that nothing
type-checks, and it is found by a user, not by CI.

With Wayfinder, import named functions rather than the module default — a default import pulls the
whole route map into the bundle and defeats tree-shaking. Regenerate after every route change
(`php artisan wayfinder:generate --no-interaction`) unless the Vite plugin is installed.

## `<Link>`, not `<a>`

An `<a>` triggers a full page load: the whole JS bundle re-downloads, layout state and scroll
position are lost, and persistent layouts remount. Use `<Link>` for anything inside the app, and a
plain `<a>` only for genuinely external destinations.

Non-GET navigation is still a `<Link>`:

```tsx
<Link href={logout()} method="post" as="button">Log out</Link>
```

## Route model binding uses the public key

Routes bind on the external identifier, so route helpers receive `product.ulid`, never an internal
id — the DTO does not carry one anyway (see `props.md`).

```php
Route::put('/products/{product}', UpdateProductController::class)->name('products.update');
```

Nested resources should chain `->scopeBindings()` so `/orders/{order}/items/{item}` cannot resolve
an item belonging to a different order. Without it, the second binding is a global lookup and the
relationship is decorative.

## Redirect after a mutation; never render

A controller handling POST/PUT/DELETE returns a redirect, and Inertia follows it as a fresh visit.
Rendering a page directly from a POST leaves the browser on a URL that re-submits on refresh.

```php
return to_route('products.index')->with('success', __('products.updated'));
```

Laravel converts the redirect to 303 for PUT/PATCH/DELETE automatically, which is what stops the
browser repeating the method on the redirect target. Do not override the status.

`return back()` is right after an action that should leave the user where they were — a modal
submit, a toggle, a bulk action on a filtered list. It preserves the query string, so filters and
the current page survive.

## URL-driven filters, sorting and pagination

Filter and sort state lives in the query string, not in component state. A user sharing a link, or
hitting refresh after an edit, then gets the same view.

```tsx
router.visit(url, { preserveState: true, preserveScroll: true, only: ['products'] });
```

Three details that are wrong more often than not:

- **Batch changes into one visit.** Setting a filter and resetting the page in two calls fires two
  requests and renders an intermediate state the user sees flicker.
- **Reset `page` whenever a filter or search changes.** Otherwise a search that returns three
  results while the user is on page 4 renders an empty table with no explanation.
- **`preserveState` keeps local component state across the visit** — correct for a filter bar, wrong
  after a mutation, where stale form state is exactly what you want cleared.

Pass the active sort back as a prop so the table header reflects the actual server-side sort rather
than what the component last requested.

## `router.visit` options that matter

| Option | Use when |
| --- | --- |
| `preserveScroll` | the interaction should not jump the page to the top |
| `preserveState` | the page's local state (filters, open panels) must survive |
| `only: [...]` | the response only needs a subset of props |
| `replace` | the visit should not add a history entry (a filter change usually should not) |

## Prefetching

`<Link href={...} prefetch>` fetches on hover. Worth it on a navigation item the user almost always
clicks; wasteful on a table where every row would prefetch a detail page. Never prefetch a route
with side effects.

## Version mismatches

Inertia compares an asset version between requests and forces a full reload when it changes. That
is what keeps a long-open tab from posting to a deploy it does not match. Do not disable it to stop
reloads during development — fix the version source instead.
