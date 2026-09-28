---
name: inertia-conventions
description: Inertia monolith conventions for the Laravel/React seam — page props and DTOs, generated TypeScript types, routing with Wayfinder or Ziggy, form submission and error handling, authorization across the boundary, and Playwright end-to-end tests. Use when writing or reviewing an Inertia page, a controller that calls Inertia::render, anything under resources/js/, or a form that posts to a Laravel route.
---

# Inertia Conventions

Inertia has no API layer, so the controller's prop array **is** the frontend contract. Most defects
at this seam come from treating one side as if the other were a REST API. These rules cover the
seam only; Laravel-side rules live in the `stack-laravel` plugin, React rules in the frontend
plugin.

## Match the repository before applying any rule

Inertia repos differ on things that are expensive to mix: `<Form>` component vs. `useForm` hook,
Wayfinder vs. Ziggy for route generation, `resources/js/Pages` vs. `resources/js/pages`. Open a
sibling page and follow it. Introducing the second convention costs more than using the older one.

## Rule index

| Change touches | Read |
| --- | --- |
| What a controller passes to `Inertia::render`, DTOs, generated types, deferred and partial props | [`rules/props.md`](../../rules/props.md) |
| Links, redirects, URL-driven filters and sorting, route generation | [`rules/routing.md`](../../rules/routing.md) |
| Form state, submission, validation errors, uploads, modals | [`rules/forms.md`](../../rules/forms.md) |
| Permission props, hiding vs. blocking, 403 handling | [`rules/authorization.md`](../../rules/authorization.md) |
| End-to-end tests of pages and journeys (Playwright) | [`rules/testing.md`](../../rules/testing.md) |

## Already enforced mechanically

`inertia/no-hardcoded-route` — a literal URL string in a `<Link>`, `router.visit()` or form action.
`inertia/no-raw-model-prop` — passing an Eloquent model or collection straight into
`Inertia::render`.

Both are blocked by the hook and again in CI. The rule files spend their words on what to do
instead and why the alternative is worse.

## The shape of a page

One controller, one DTO per view role, one typed page component.

```php
// Controller — every prop is a DTO or a scalar, never a model
return Inertia::render('Products/Overview', [
    'products'      => $getProducts->execute($request),          // paginator ->through(DTO)
    'statusOptions' => ProductStatusEnum::toOptionsArray(),
    'sort'          => $request->get('sort', GetProductsAction::DEFAULT_SORT),
]);
```

```tsx
// Page — props typed from generated definitions, never hand-written
export default function Overview({ products }: { products: Paginator<App.Data.Products.ProductOverviewRowData> }) { ... }
```

The page path mirrors the controller namespace and the file path: `Products/Overview` resolves to
`resources/js/Pages/Products/Overview.tsx`. A mismatch is a runtime 500 with an unhelpful message,
so keep them mechanically derivable from each other.

## After changing anything on the boundary

A DTO change that is not regenerated produces TypeScript that compiles against a type the server no
longer sends. Read the repo's `package.json` and `Makefile` for the real targets; the usual pair is:

```bash
make typescript-generate     # or: php artisan typescript:transform
make typecheck               # or: npx tsc --noEmit
php artisan wayfinder:generate --no-interaction   # after any route change, if Wayfinder is used
```

Run these before claiming a change works. `tsc` passing is the only evidence that the two sides
still agree.
