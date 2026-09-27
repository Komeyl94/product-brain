/**
 * Laravel rules.
 *
 * The architectural ones (`controller-no-direct-persistence`) are gated on adoption:
 * "controllers delegate to Actions" is only a rule in a repository that has an Actions
 * layer. In one that does not, it is an opinion, and enforcing an opinion on every
 * write is how a guardrail loses its credibility.
 */

import { hasInterpolatedSql } from './shared.mjs';

const PHP = /\.php$/;
const MIGRATION = /[/\\]database[/\\]migrations[/\\].*\.php$/;
const CONTROLLER = /[/\\]app[/\\]Http[/\\]Controllers[/\\].*\.php$/;
const CONFIG = /[/\\]config[/\\][^/\\]+\.php$/;

export const laravelRules = [
  {
    id: 'laravel/no-env-outside-config',
    stack: 'laravel',
    files: (path) => PHP.test(path) && !CONFIG.test(path),
    skip: (ctx) => ctx.isTest,
    test: /(?<![\w$>-])env\s*\(/,
    message:
      'env() returns null once the config is cached, so this breaks in production and nowhere else. Read the value in config/*.php and use config() here.',
    doc: 'laravel/config',
  },
  {
    id: 'laravel/no-raw-query-interpolation',
    stack: 'laravel',
    files: PHP,
    custom: (lines, i) =>
      hasInterpolatedSql(lines[i], /(DB::raw|whereRaw|selectRaw|orderByRaw|havingRaw|joinRaw|groupByRaw)\s*\(/),
    message:
      'A variable is being interpolated into raw SQL — this is SQL injection. Pass the value as a binding: `whereRaw("col = ?", [$value])`.',
    doc: 'laravel/security',
  },
  {
    id: 'laravel/no-unguarded-model',
    stack: 'laravel',
    files: PHP,
    test: /\$guarded\s*=\s*\[\s*\]|(?<![\w$>-])Model::unguard\s*\(/,
    message:
      'An unguarded model lets any request field reach the database, including ones the form never showed. List the assignable columns in `$fillable`.',
    doc: 'laravel/security',
  },
  {
    id: 'laravel/no-unvalidated-request-all',
    stack: 'laravel',
    files: PHP,
    skip: (ctx) => ctx.isTest,
    test: /\$request->all\s*\(\s*\)/,
    message:
      '$request->all() passes through every field the client sent. Use `$request->validated()` from a FormRequest, or `$request->safe()->only([...])`.',
    doc: 'laravel/validation',
  },
  {
    id: 'laravel/no-enum-column-in-migration',
    stack: 'laravel',
    files: MIGRATION,
    test: /->enum\s*\(/,
    message:
      'An enum column cannot be altered without a table rewrite, and its values live in the schema rather than the code. Use a string column backed by a PHP enum cast.',
    doc: 'laravel/migrations',
  },
  {
    id: 'laravel/migration-requires-down',
    stack: 'laravel',
    files: MIGRATION,
    wholeCustom: (text) =>
      /public\s+function\s+up\s*\(/.test(text) && !/public\s+function\s+down\s*\(/.test(text),
    message:
      'This migration cannot be rolled back. Add a `down()` method — a deploy that fails halfway needs a way out.',
    doc: 'laravel/migrations',
  },
  {
    id: 'laravel/controller-no-direct-persistence',
    overridable: true,
    stack: 'laravel',
    files: CONTROLLER,
    gate: (gates) => gates.laravelActions,
    test: /(::(create|updateOrCreate|firstOrCreate|insert)\s*\(|->save\s*\(\s*\)|->delete\s*\(\s*\)|DB::(table|statement|insert|update|delete)\s*\()/,
    message:
      'This project keeps write logic in app/Actions. The controller should validate, call the Action, and return — move the persistence into an Action.',
    doc: 'laravel/architecture',
  },
];
