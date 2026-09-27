# Forms

Typed reactive forms for new code. The exception is a file that already uses template-driven forms
(`[(ngModel)]` + `#form="ngForm"`) — mixing the two in one component gives you two validation
states and two sources of truth. Follow the file.

## Type the group, do not infer it

```ts
// wrong — `any` (blocked by ts/no-any), and every consumer of .value is unchecked
form = this.fb.group({ email: [''], age: [null] });
```

```ts
// right
private readonly fb = inject(FormBuilder);

readonly form = this.fb.nonNullable.group({
  email: ['', [Validators.required, Validators.email]],
  age: this.fb.control<number | null>(null),
  newsletter: [false],
});
```

`fb.nonNullable.group` means `reset()` restores the initial value instead of `null`, and
`form.value.email` is `string`, not `string | undefined`. When a control is genuinely nullable, say
so in its type as above rather than dropping the whole group back to nullable.

Where the repo does not use `FormBuilder`, spell out the group — same guarantees:

```ts
readonly form = new FormGroup({
  email: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
});
```

## `value` silently drops disabled controls

This is the most common production bug in these repos: a field is disabled (read-only price, a
server-assigned id), and the PATCH body quietly has no such key.

```ts
// wrong when any control is disabled
this.api.save(this.form.value);
```

```ts
// right — every control, disabled included
this.api.save(this.form.getRawValue());
```

Also: `form.value` on a partially-filled group is `Partial<T>` by type. Guard on
`form.invalid` and return early, then use `getRawValue()`, so the payload type is complete.

## Disabling

Never bind `[disabled]` on a control that is also in a reactive form — Angular warns and the two
mechanisms fight. Use `control.disable({ emitEvent: false })` / `enable()`. Pass
`{ emitEvent: false }` whenever you are reacting to `valueChanges` yourself, or you get a
feedback loop.

## Validators

```ts
export function matchesControl(other: string): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null =>
    control.value === control.parent?.get(other)?.value ? null : { mismatch: true };
}
```

- Return `null` for valid, a keyed object for invalid. Never throw.
- Async validators get `{ updateOn: 'blur' }` on the control, otherwise you fire a request per
  keystroke.
- Cross-field rules go on the group, not on one control — a control validator that reads
  `control.parent` runs before the parent exists during construction.
- Reuse the shared validators in the repo before writing a new one; grep for `ValidatorFn` first.

## Reading changes

`valueChanges` and `statusChanges` outlive the component — `angular/no-unmanaged-subscribe` will
block a bare subscribe. Prefer a signal:

```ts
readonly email = toSignal(this.form.controls.email.valueChanges, { initialValue: '' });
```

or, when you must subscribe, `takeUntilDestroyed()` immediately before it (see `rxjs.md`).

## Submit

```ts
submit(): void {
  if (this.form.invalid) {
    this.form.markAllAsTouched();   // otherwise the user sees no error on an untouched field
    return;
  }
  this.saving.set(true);
  this.api.save(this.form.getRawValue()).pipe(
    finalize(() => this.saving.set(false)),
    takeUntilDestroyed(this.destroyRef),
  ).subscribe({ error: (err) => this.error.set(toMessage(err)) });
}
```

Use `exhaustMap` from a submit subject if double submission matters more than a disabled button
(see `rxjs.md`). Never rely on client validation alone — the server validates too, and its errors
must be mapped back onto controls with `setErrors`, not shown only as a toast.

## Template side

```html
<form [formGroup]="form" (ngSubmit)="submit()">
  <input formControlName="email" type="email" />
  @if (form.controls.email.touched && form.controls.email.hasError('required')) {
    <span class="error">Email is required</span>
  }
  <button type="submit" [disabled]="saving()">Save</button>
</form>
```

Keep the error conditions simple; anything longer than the above belongs in a `computed()` or a
small error-message component reused across the app.
