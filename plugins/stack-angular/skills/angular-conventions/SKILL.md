---
name: angular-conventions
description: Angular conventions for components, signals, RxJS lifetime, templates, typed forms, HTTP, security, unit tests and Playwright end-to-end tests. Use when writing or reviewing TypeScript or HTML in an Angular workspace (a repo with angular.json or nx.json and @angular/core in package.json).
---

# Angular conventions

Angular repos sit at different points of the same migration. The version in `package.json` says
nothing about the style of the code: an Angular 20 repo can be deliberately NgModule-based. A standalone component added there is a defect, not an upgrade.

## Do this before writing any Angular file

1. **Establish the repo's era** — `rules/project-profile.md`. Once per session, before the first
   component, service or template you touch. It is a two-minute measurement, not a guess.
2. **Read the nearest sibling file in the same folder** and match it: module membership, DI style,
   control flow syntax, input/output style, form style, file naming.
3. Only then apply the defaults below. They are for *new* code in a project that has already
   adopted the pattern — never a licence to convert code you were not asked to convert.

Never fold a migration into an unrelated change. If the task genuinely cannot be done without
modernising a file, say so and ask first.

## Rules by topic

| Read | When |
| --- | --- |
| `rules/project-profile.md` | Always first. Which era the repo is in, how to measure it, which repo is which, and when the sibling file overrides the repo-wide answer. |
| `rules/components.md` | Creating or editing a component or service: where it gets registered, standalone vs declarations, OnPush, DI style, inputs/outputs. |
| `rules/state-and-signals.md` | Holding state: signals, computed, effects, and when `BehaviorSubject` is still the right answer. |
| `rules/rxjs.md` | Anything with `.subscribe()`, operators, or subscription lifetime. |
| `rules/templates.md` | Editing `.html` or an inline template: control flow, `track`, work done per change-detection cycle. |
| `rules/forms.md` | Reactive or template-driven forms, validators, `value` vs `getRawValue()`. |
| `rules/http.md` | `HttpClient`, interceptors, response typing, error handling. |
| `rules/security.md` | Anything touching raw HTML, URLs, tokens, or `environment.*.ts`. |
| `rules/testing.md` | `.spec.ts` files — including which guardrails stop applying there and which never do — and Playwright end-to-end tests. |

## Defaults for genuinely new code

Apply in a project that has already adopted the pattern; otherwise follow the local style.

- `changeDetection: ChangeDetectionStrategy.OnPush` on every new component. It is correct only if
  that component's state is immutable or signal-based — see `rules/components.md`.
- `signal()` / `computed()` / `input()` / `output()` over `BehaviorSubject` and the
  `@Input()` / `@Output()` decorators.
- `toSignal()` or the `async` pipe over a manual `.subscribe()`. When you must subscribe, pipe
  through `takeUntilDestroyed()`.
- No `any`. Real interfaces, generics, or `unknown` with narrowing. `http.get<Thing>(...)`, never
  bare `http.get(...)`.
- No logic in templates. No function call in a binding that re-runs every change-detection cycle.
- Typed reactive forms (`FormGroup<{ ... }>`), unless the file already uses template-driven forms.

## Already enforced mechanically

The guardrail hook blocks these on write, so do not re-derive them — the linked rules file explains
the *why* and the correct alternative:

`angular/no-unmanaged-subscribe`, `angular/no-bypass-security`, `angular/no-inner-html`,
`angular/no-removed-api`, `angular/no-http-client-module`, `angular/prefer-inject`,
`angular/no-ngmodule`, `angular/prefer-control-flow`, `angular/for-requires-track`,
`ts/no-any`, `ts/no-ts-ignore`, `ts/no-console`.

Four of them — `prefer-inject`, `no-ngmodule`, `prefer-control-flow`, and partly
`no-http-client-module` — are gated on measured adoption, so they stay silent in a legacy repo.
**Silence is not permission.** A rule that does not fire in a legacy repo means "keep doing what
this repo does", not "the modern pattern is now optional here".

When the hook blocks a write it prints `see: guardrails/<slug>`. Map the slug to a file here:

| Hook slug | File |
| --- | --- |
| `angular/standalone`, `angular/migration` | `rules/project-profile.md` |
| `angular/dependency-injection` | `rules/components.md` |
| `angular/rxjs` | `rules/rxjs.md` |
| `angular/templates` | `rules/templates.md` |
| `angular/security` | `rules/security.md` |
| `typescript/types`, `typescript/debugging` | `rules/components.md`, `rules/http.md` |

Fix the code; do not work around the hook. `// guardrail:allow` on the line is for cases that are
genuinely correct, and using it obliges you to say why in your reply. Never edit the hook, its
config, or `.guardrails.json` to get a write through.

## Verification

Do not claim a change works without running the project's own commands. Read `package.json`
scripts rather than assuming: several repos are Nx (`nx lint <project>`, `nx test <project>`),
others are plain `ng`. Commit with `git commit -m "type(scope): [KEY-123] description"` —
the format the `git-workflow` plugin enforces.
