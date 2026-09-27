# Authorization across the seam

## The frontend check is UX; the server check is the control

A `can('products.edit')` helper in JSX decides what to render. It decides nothing about what is
permitted. Every route the hidden button would have called must carry its own gate, because the
route is reachable without the button — by URL, by a stale tab, by a script.

```tsx
{can('products.edit') && <Link href={edit(product.ulid)}>{t('common.edit')}</Link>}
```

If you add a permission check to a component, confirm the corresponding route has a gate before
you consider the change done. The reverse — a gated route with no UI check — is merely rude. A UI
check with no gate is a vulnerability.

## One place per ability

Bare permission checks live on the route:

```php
Route::put('/products/{product}', UpdateProductController::class)
    ->can(SystemPermissionEnum::CATALOG_PRODUCTS_EDIT);
```

Record-specific logic lives in a policy invoked from the controller. Do not write a policy method
whose body is `return $user->can(PERMISSION)` — it duplicates the route gate and adds a method with
nothing to test. See `security.md` in the `stack-laravel` plugin for the full split and the
grep-before/grep-after procedure.

## The shared permission prop

Share the permission list once, from `HandleInertiaRequests`, and read it through one helper.
Two rules about its contents:

- **Ship only what the UI branches on.** A full permission dump tells any logged-in user the exact
  shape of the admin surface, including features they have never seen. Filter to the abilities the
  application actually renders against.
- **Never ship a permission for a user who does not hold it** with a flag saying so. Absence is the
  signal; `{ 'users.delete': false }` is the same disclosure as sending the list.

The prop reflects the session at render time. After a role change the page must be reloaded for the
UI to agree with the server — which is fine, because the server was already the authority.

## Hide or disable, deliberately

Hide a control the user can never use in their role — showing it is noise about a feature they do
not have. Disable a control the user *could* use if state changed, and say why in a tooltip: "You
cannot cancel an order that has shipped." A silently missing button reads as a bug and generates
support tickets; a disabled one with a reason does not.

## 403 and 419 responses

An Inertia visit that hits a gate gets a 403. Handle it as a rendered error page rather than an
unhandled rejection, so the user sees an explanation instead of a frozen UI.

419 (expired CSRF token) is the more common one in practice — it happens to any tab left open past
the session lifetime. The default behaviour should be a clear "your session expired, sign in again"
path, not a silent failed submit that loses what the user typed.

## Partial reloads and deferred props re-enter the controller

`router.reload({ only: ['stats'] })` is a full request through the same middleware and gates, so
an authorized prop stays authorized. What changes is scoping: a prop closure that reads state
captured at first render — a filter, a selected account — must re-derive it from the request, not
assume the original context. A deferred prop that queries "the current tenant's records" needs the
tenant resolved inside the closure.

## Authorize the data, not just the route

A gate answers "may this actor use this endpoint". It does not scope rows. An index Action must
constrain its query to what the actor may see; otherwise a user with a legitimate `products.view`
permission reads every tenant's products through an endpoint they are genuinely allowed to call.

```php
QueryBuilder::for(Product::class)
    ->whereBelongsTo($request->user()->organisation)
    ->allowedFilters([...]);
```

The same applies to any identifier arriving from the client. A ULID in a form payload was chosen by
the browser: resolve it inside the Action with the actor's scope applied, never by a bare
`findOrFail()` that trusts the id.
