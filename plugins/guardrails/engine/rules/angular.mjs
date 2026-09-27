/**
 * Angular rules.
 *
 * Ported from the standalone `angular-guardrail.mjs` this repository's author was
 * already running locally. The version gating is the important part and is preserved:
 * these repos sit at different points of a migration, and a v20 package.json does not
 * mean the code is modern. A deliberately NgModule-based Angular 20 app must not be
 * told to go standalone, and a repo that has never adopted `@if` must not be told to
 * stop using `*ngIf`.
 */

import { hasConstructorParamProperties } from '../lib/profile.mjs';

const TS = /\.ts$/;
const TEMPLATE = /\.(ts|html)$/;

export const angularRules = [
  {
    id: 'angular/no-unmanaged-subscribe',
    stack: 'angular',
    files: TS,
    skip: (ctx) => ctx.isTest,
    custom: (lines, i) => {
      if (!/\.subscribe\s*\(/.test(lines[i])) return false;
      const window = lines.slice(Math.max(0, i - 6), i + 1).join('\n');
      return !/takeUntilDestroyed|takeUntil\(|take\(\s*\d|first\(\)|toSignal\(|firstValueFrom|lastValueFrom|\.add\(/.test(window);
    },
    message:
      'An unmanaged subscription leaks for the lifetime of the app. Pipe through `takeUntilDestroyed()`, or prefer `toSignal()` / the `async` pipe.',
    doc: 'angular/rxjs',
  },
  {
    id: 'angular/no-bypass-security',
    stack: 'angular',
    files: TEMPLATE,
    test: /bypassSecurityTrust/,
    message:
      'bypassSecurityTrust* turns off Angular XSS protection for that value. Sanitize it, or render it without raw HTML.',
    doc: 'angular/security',
  },
  {
    id: 'angular/no-inner-html',
    stack: 'angular',
    files: TEMPLATE,
    test: /\[innerHTML\]\s*=/,
    message:
      '[innerHTML] is an XSS surface. Render through template bindings, or sanitize explicitly with DomSanitizer.',
    doc: 'angular/security',
  },
  {
    id: 'angular/no-removed-api',
    stack: 'angular',
    files: TS,
    test: /\.mutate\s*\(|\bentryComponents\b|@angular\/flex-layout|\bComponentFactoryResolver\b|ModuleWithComponentFactories/,
    message:
      'This API is removed or dead in modern Angular (signal.mutate, entryComponents, flex-layout, ComponentFactoryResolver). Use the current equivalent.',
    doc: 'angular/project-profile',
  },
  {
    id: 'angular/no-http-client-module',
    stack: 'angular',
    files: TS,
    gate: (_gates, ctx) => (ctx.versions.angular ?? 0) >= 19,
    test: /\bHttpClientModule\b/,
    message:
      'HttpClientModule is deprecated. Use `provideHttpClient(withInterceptors([...]))` in the providers array.',
    doc: 'angular/http',
  },
  {
    id: 'angular/prefer-inject',
    stack: 'angular',
    files: TS,
    skip: (ctx) => ctx.isTest,
    gate: (gates) => gates.angularInject,
    wholeCustom: (text) => hasConstructorParamProperties(text),
    message:
      'This project uses `inject()`. Declare dependencies as `private readonly x = inject(X);` rather than constructor parameter properties.',
    doc: 'angular/components',
  },
  {
    id: 'angular/no-ngmodule',
    stack: 'angular',
    files: TS,
    gate: (gates) => gates.angularStandalone,
    test: /@NgModule\s*\(/,
    message:
      'This project is standalone-based. Use a standalone component with `imports: [...]` and `provide*()` functions instead of a new NgModule.',
    doc: 'angular/components',
  },
  {
    id: 'angular/prefer-control-flow',
    stack: 'angular',
    files: TEMPLATE,
    gate: (gates) => gates.angularControlFlow,
    test: /\*ngIf|\*ngFor|\*ngSwitch/,
    message:
      'This project uses built-in control flow. Use `@if` / `@for (x of xs; track x.id)` / `@switch` instead of structural directives.',
    doc: 'angular/templates',
  },
  {
    id: 'angular/for-requires-track',
    stack: 'angular',
    files: TEMPLATE,
    gate: (_gates, ctx) => (ctx.versions.angular ?? 0) >= 17,
    test: /@for\s*\((?![^)]*\btrack\b)[^)]*\)/,
    message:
      '`@for` requires a `track` expression, e.g. `@for (item of items; track item.id)`. Without it Angular re-creates every DOM node on each change.',
    doc: 'angular/templates',
  },
];
