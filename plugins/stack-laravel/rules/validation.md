# Validation

## Validate at the edge, in a dedicated class

Never inline `$request->validate([...])` in a controller. Two shapes are in common use across Laravel
repos — pick whichever the repo already uses and do not introduce the other:

- **Form Requests** (`app/Http/Requests/`) — the framework default.
- **`spatie/laravel-data` classes** (`app/Data/`) — where the DTO doubles as the frontend contract
  and generates TypeScript.

Both are type-hinted as a controller argument, which is what makes validation run before the method
body. A class that is constructed manually inside the method validates nothing.

```php
public function store(StoreProductRequest $request, CreateProductAction $create): RedirectResponse
{
    $create->execute($request->validated());
    // ...
}
```

## `validated()`, never `all()`

`laravel/no-unvalidated-request-all` blocks `Model::create($request->all())`. The reason is not
only mass assignment: `all()` includes query-string parameters and any field an attacker appends,
so the set of keys reaching your Action is defined by the request, not by your rules.

## Array rule syntax

Preferred for new code — it composes with `Rule::` objects without string concatenation. Match the
file you are editing if it already uses pipe strings.

```php
'email' => ['required', 'email', Rule::unique('users')],
```

## Enum fields need an explicit rule

Typing a property as a backed enum does not validate it.

```php
'status' => ['required', Rule::enum(ProductStatusEnum::class)],
```

Why this matters more here than elsewhere: migrations store enum-backed columns as plain strings
(`laravel/no-enum-column-in-migration`), so there is no database `CHECK` constraint to catch a bad
value. Validation is the only layer left. With `spatie/laravel-data`, an explicit `rules()` array
**replaces** the automatic type-based inference rather than adding to it — so a property typed
`ProductStatusEnum` in a class that defines `rules()` is unvalidated unless you list it. Consider an
architecture test that reflects every Data class and fails on a backed-enum property missing a
matching `Rule::enum(...)`.

State-machine fields that are only ever set from fixed enum constants inside an Action have no
external input to validate and should not appear in a form DTO at all.

## Conditional and cross-field rules

```php
'company_name' => [Rule::when($this->account_type === 'business', ['required', 'string', 'max:255'])],
```

Checks that span fields, or need a query, go in `after()` (Form Request) or `withValidator()`
(Data class) — not into a rule object that re-reads the request.

```php
public function after(): array
{
    return [
        function (Validator $validator) {
            if ($this->quantity > Product::find($this->product_id)?->stock) {
                $validator->errors()->add('quantity', __('orders.errors.insufficient_stock'));
            }
        },
    ];
}
```

For an error that belongs to the form rather than any single field, attach it to one agreed
pseudo-field (for example `genericFormError`) that the frontend renders as a form-level alert. An
error keyed to a field that has no input renders nowhere and the user sees a silent failure.

## Field names in messages

Supply `attributes()` so messages read in the user's language and use the label the user actually
sees, not the property name.

```php
public function attributes(): array
{
    return ['available_to' => __('products.fields.available_to')];
}
```

## File uploads

```php
'avatar' => ['required', 'image', 'mimes:jpg,jpeg,png,webp', 'max:2048'],
```

`mimes` checks the extension; `mimetypes` checks the detected MIME type — use `mimetypes` when the
file is going anywhere it might be executed or served back. Always cap `max`. Never trust the
client filename: store with a generated name.

```php
$path = $request->file('avatar')->store('avatars', 'public');
```

## Validation is not authorization

A Form Request's `authorize()` answers "may this actor perform this action at all". It does not
answer "does this record belong to them" unless you write that check explicitly. Record-scoped
checks belong in a policy — see `security.md`. Returning `true` from `authorize()` is correct when
the route already carries the permission gate; returning `true` because you did not think about it
is the bug.

## Validate external payloads too

Webhook bodies, console command input and integration callbacks do not pass through the controller
resolution that triggers automatic validation. Validate them explicitly:

```php
$data = ImportPayloadData::validateAndCreate($request->all());
```
