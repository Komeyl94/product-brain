# Forms

## Type the form from the generated DTO

```tsx
const form = useForm<App.Data.Products.CreateOrUpdateProductFormData>({
    name: '',
    sku: '',
    categoryId,
    ulid: null,
});
```

The point is not tidiness: the generated type is what makes a renamed or removed DTO property fail
`tsc` instead of silently posting a field the server discards. A form initialised with an untyped
object literal will keep compiling after the backend changes.

Initialise every field the DTO declares. A field left out of the initial object is absent from the
payload, so a "required" rule fires for a field the user could not see.

## `<Form>` component or `useForm` — pick the repo's

Inertia offers both. `<Form action={...} method="post">` with a render prop handles the common case
with no state wiring; `useForm` is right when submission is conditional, values are derived, or the
form is hydrated out of band. Do not mix both shapes in one directory.

Never use a bare `<form>` with a manual `fetch`. It bypasses the Inertia response protocol, so
validation errors, flash messages and redirects all stop working.

## Errors are keyed by the property name the server validated

`form.errors.<property>` is filled from the 422 response. The keys are whatever the validator used
— so a DTO mapping camelCase properties from snake_case input must be consistent about which name
the rules are written against, or the error arrives under a key the component never reads and the
field shows nothing while the submit visibly fails.

When adding a field, check the rendered error path against an actual failing submit, not against
what you expect the key to be.

For an error that belongs to no single field — a cross-field or business-rule failure — the server
attaches it to one agreed pseudo-field (for example `genericFormError`) and the form container
renders it as a top-of-form alert. Without that, the user gets a failed submit with no visible
reason.

## Submission state

Disable the submit control on `form.processing` and show progress. A form that stays enabled
invites a double submit, and a double POST to a create endpoint produces two records — the server
should be idempotent, but the button is the cheap fix.

```tsx
<button type="submit" disabled={form.processing}>
    {form.processing ? t('common.saving') : t('common.save')}
</button>
```

## Clear what should not survive

```tsx
form.post(store(), { onSuccess: () => form.reset('password') });
```

Passwords, one-time codes and card fields are reset on success *and* on failure. Everything else
should usually survive a validation failure so the user does not retype the form.

## Uploads

Any form with a file must send multipart. Inertia does this automatically when a `File` is present
in the data, but a form that conditionally attaches a file sends JSON on the runs where it is
absent — set `forceFormData: true` when the shape varies.

PUT and PATCH cannot carry multipart in browsers. Post to the update route with `_method: 'put'`,
or use `form.post()` against a route that accepts POST. Show `progress.percentage` for anything
large enough that the user would otherwise assume the page froze.

## Edit modals

Hydrating a modal from the row already in the table means the form edits whatever the list last
fetched, which may be minutes stale, and it limits the form to fields the list DTO happened to
carry. Fetch the form DTO from a JSON route when the modal opens:

```tsx
const { data } = await http.get(route('api.products.show', { product: ulid }));
form.setDefaults(data);
form.setData(data);
```

Set defaults as well as data, so `form.isDirty` and reset behave against the loaded record rather
than the empty initial state.

## Choosing store or update from one component

```tsx
const submit = () =>
    form[isEditing ? 'put' : 'post'](
        isEditing ? update(form.data.ulid!) : store(),
    );
```

Keep the branch in one place. Two nearly identical components for create and edit drift within a
sprint.

## Optimistic updates

```tsx
router.optimistic((props) => ({ post: { ...props.post, likes: props.post.likes + 1 } }))
      .post(like(post.ulid));
```

Inertia rolls back automatically on failure. Only apply it where the server is near-certain to
agree — a like, a toggle, a reorder. Never for anything the user would act on as confirmed:
payments, stock reservations, submissions.

## Client-side checks are not validation

Required attributes, `maxlength` and format masks are for the user's benefit. The server rules are
the actual constraint, and every form must render the errors that come back from them. A field
validated only in the browser is a field that is not validated.
