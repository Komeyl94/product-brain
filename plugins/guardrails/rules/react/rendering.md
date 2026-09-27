# React rendering

`react/no-array-index-key` blocks `key={i}`, `key={idx}` and `key={index}` in `.tsx` and
`.jsx`.

## The bug it prevents

`key` is how React decides whether an element in the new render is the *same* element as
one in the previous render. With an index, "the same element" means "the same position",
so the identity is wrong the moment the list changes shape.

```tsx
// wrong
{rows.map((row, i) => <TodoRow key={i} todo={row} />)}
```

Delete the first row of five. React sees five keys become four, decides `key={0}` still
exists, and reuses that DOM node and that component instance for what is now a different
todo. Everything held in the instance rather than in props moves with it: text typed into
an uncontrolled input, a checkbox state, focus, scroll position inside the row, a running
CSS transition, the collapsed/expanded flag in `useState`. The visible symptom is "I
deleted the second item and the first item's notes are now on the wrong row", which gets
reported as a backend bug and is not one.

The same applies to sorting, filtering, prepending, and any optimistic insert.

## What to write instead

Use an identifier that belongs to the data:

```tsx
{rows.map((row) => <TodoRow key={row.id} todo={row} />)}
```

If the records have no id, build one from fields that identify the row, and make sure the
result is unique:

```tsx
{entries.map((e) => <Row key={`${e.date}:${e.accountId}`} entry={e} />)}
```

If the list is assembled client-side and genuinely has no natural identity, assign an id
when you create the item (`crypto.randomUUID()`) and keep it in state — not at render
time, or you generate a new key every render and remount the whole list.

**Renaming the variable is not a fix.** `key={rowIndex}` or `key={items.indexOf(item)}`
passes the regex and has the identical bug. Working around a guardrail rather than the
problem is worse than the original code, because the next reader assumes it was reviewed.

## When an index is actually fine

All three must hold: the list is never reordered, filtered or removed from — append-only
or fully static — and the items hold no internal state. A rendered table of read-only
cells from a fixed report qualifies. In that case take a line waiver and say so:

```tsx
{columns.map((label, i) => <th key={i}>{label}</th>)} {/* guardrail:allow static header */}
```

## Overriding

This rule is `overridable`. A repo that is almost entirely generated static tables can
switch it off:

```json
{ "rules": { "react/no-array-index-key": "off" } }
```

That turns it off for every file including the interactive ones, which is why a line
waiver is nearly always the better answer.
