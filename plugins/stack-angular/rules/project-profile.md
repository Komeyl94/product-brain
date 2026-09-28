# Project profile: which era is this repo in?

Read this before writing the first Angular file in a session. Everything else in these rules is
conditional on the answer.

## The version number is not the answer

`@angular/core: ^20` tells you which APIs *exist*, not which ones this codebase *uses*.
Plenty of Angular 20 repos are still deliberately NgModule-based. Adding
`standalone: true` there produces a component nothing declares, nothing imports, and no one asked
for. Measure the code instead.

## Measure it — three counts, one minute

Run from the workspace root (or the app's project root in an Nx repo):

```bash
rg -l 'standalone:\s*true' --glob '*.ts' | wc -l   # standalone components
rg -l '@NgModule\s*\(' --glob '*.ts' | wc -l       # NgModules
rg -l '=\s*inject\s*\(' --glob '*.ts' | wc -l      # inject() DI
rg -l 'constructor\(' -A3 --glob '*.ts' | rg -c 'private|protected|public'  # constructor DI
rg -l '@if\s*\(|@for\s*\(' --glob '*.html' | wc -l # built-in control flow
rg -l '\*ngIf|\*ngFor' --glob '*.html' | wc -l     # structural directives
rg '"@angular/core"' package.json                  # major version
```

Three independent axes — a repo can be modern on one and legacy on another:

| Axis | Modern when | Then |
| --- | --- | --- |
| Component style | standalone files > 2x NgModule files, **or** v19+ with zero NgModules | New components are standalone with `imports: [...]`; no new NgModule |
| DI style | v16+ and `inject()` is at least ~40% of constructor DI (~15% on v19+) | `private readonly x = inject(X)` |
| Template syntax | v17+ and 3+ files use `@if`/`@for`, **or** no `*ngIf`/`*ngFor` anywhere | `@if` / `@for (x of xs; track x.id)` / `@switch` |

Those thresholds are exactly the gates in `plugins/guardrails/engine/lib/profile.mjs`, so they
also tell you when the block layer will fire. Below the threshold the rule stays silent — which
means the repo has *not* committed to the pattern, so neither do you.

## Record the answer in the hub

Once measured, note the era in the hub (for example a line per repo in `domains.md` or the
repo's `docs/` entry) so the next session starts from the answer instead of re-measuring.
A recorded era is a hint, not a substitute: re-measure if the sibling file disagrees.

## The sibling file wins on structure

After the repo-wide measurement, read the nearest component/service in the **same folder** before
writing. Feature folders migrate one at a time, so a repo-wide "legacy" answer can be wrong for
the folder you are in — and vice versa.

The sibling file decides: module membership, standalone vs declared, DI style, input/output style,
control-flow syntax, file and selector naming, folder layout, test layout.

The sibling file decides nothing about safety. `any`, `@ts-ignore`, `console.log`, unmanaged
`.subscribe()`, `[innerHTML]`, `bypassSecurityTrust*` and hardcoded credentials are wrong in every
era, and the neighbouring file doing it is not precedent. Those rules are ungated for that reason.

## Writing into an NgModule repo

```ts
// wrong in an NgModule repo — nothing declares this, and no module imports it
@Component({ selector: 'app-invoice-row', standalone: true, imports: [CommonModule], ... })
export class InvoiceRowComponent {}
```

```ts
// right — plain component, registered in the module that owns the feature folder
@Component({
  selector: 'app-invoice-row',
  templateUrl: './invoice-row.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceRowComponent {}

// invoices.module.ts
@NgModule({
  declarations: [InvoiceListComponent, InvoiceRowComponent],
  exports: [InvoiceListComponent],
  imports: [CommonModule, RouterModule.forChild(routes)],
})
export class InvoicesModule {}
```

On Angular 19+ `standalone` defaults to `true`, so a component declared in an NgModule must say
`standalone: false` explicitly. Copy whichever form the sibling file uses — if every component in
the folder carries `standalone: false`, yours does too.

## Removed and dead APIs — wrong in every era

`angular/no-removed-api` blocks these regardless of profile, because they are broken rather than
merely old: `signal.mutate()` (removed before signals stabilised), `entryComponents`,
`@angular/flex-layout` (unmaintained, no Angular 16+ support), `ComponentFactoryResolver`,
`ModuleWithComponentFactories`. Finding one in existing code is not a reason to migrate the file;
it is a reason not to add another.

## Migration boundary

Never mix a migration into an unrelated change. A diff that both fixes a bug and converts a
component to signals cannot be reviewed or reverted independently. If the task truly requires
modernising a file, say which file and why, and ask before starting.
