/**
 * Stack detection.
 *
 * A repository is not "a Laravel project" or "an Angular project" — it is a set of
 * stacks that happen to be present. an Inertia monolith is core + php + laravel +
 * inertia + react + typescript at once; a Laravel API is core + php + laravel; a mobile
 * app is core + flutter. Detecting a set rather than picking one label is what lets the same
 * engine serve a monolith and a split frontend/backend pair without configuration.
 */

import { readFileSync, existsSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';

export const STACKS = [
  'core',
  'php',
  'laravel',
  'symfony',
  'typescript',
  'react',
  'inertia',
  'angular',
  'flutter',
];

/** Manifests whose mtime invalidates a cached profile. */
export const MANIFESTS = [
  'composer.json',
  'package.json',
  'pubspec.yaml',
  'angular.json',
  'nx.json',
];

export const readJson = (path, fallback = null) => {
  try {
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    return fallback;
  }
};

export const mtimeOf = (path) => {
  try {
    return statSync(path).mtimeMs;
  } catch {
    return 0;
  }
};

/** First integer in a semver range: "^13.17" -> 13, ">=8.3" -> 8. */
export const majorOf = (range) => {
  const match = String(range ?? '').match(/(\d+)/);
  return match ? Number.parseInt(match[1], 10) : 0;
};

/**
 * Walk up from `startDir` to the repository root — the nearest directory holding a
 * `.git`, falling back to the nearest one holding a recognised manifest.
 */
export function findRepoRoot(startDir) {
  let dir = resolve(startDir);
  let manifestFallback = null;

  for (let depth = 0; depth < 24; depth++) {
    if (existsSync(join(dir, '.git'))) return dir;
    if (!manifestFallback && MANIFESTS.some((m) => existsSync(join(dir, m)))) {
      manifestFallback = dir;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return manifestFallback;
}

/**
 * Which stacks are present at `root`, and the version of each that has one.
 *
 * Detection reads manifests only. It never infers a stack from source files, so an
 * incidental `.tsx` under `vendor/` or a single stray `.php` script cannot switch a
 * whole rule set on.
 */
export function detectStacks(root) {
  const composer = readJson(join(root, 'composer.json')) ?? {};
  const pkg = readJson(join(root, 'package.json')) ?? {};

  const php = { ...composer.require, ...composer['require-dev'] };
  const node = { ...pkg.dependencies, ...pkg.devDependencies };

  const stacks = new Set(['core']);
  const versions = {};

  const add = (stack, version) => {
    stacks.add(stack);
    if (version) versions[stack] = majorOf(version);
  };

  if (existsSync(join(root, 'composer.json'))) add('php', php.php);
  if (php['laravel/framework']) add('laravel', php['laravel/framework']);
  if (php['symfony/framework-bundle']) add('symfony', php['symfony/framework-bundle']);

  if (node.typescript || existsSync(join(root, 'tsconfig.json'))) {
    add('typescript', node.typescript);
  }
  if (node.react) add('react', node.react);
  if (php['inertiajs/inertia-laravel'] || node['@inertiajs/react'] || node['@inertiajs/vue3']) {
    add('inertia', php['inertiajs/inertia-laravel']);
  }
  if (node['@angular/core']) add('angular', node['@angular/core']);

  if (existsSync(join(root, 'pubspec.yaml'))) {
    try {
      const pubspec = readFileSync(join(root, 'pubspec.yaml'), 'utf8');
      // The `flutter:` SDK constraint is what separates a Flutter app from a plain Dart
      // package; both carry a pubspec.yaml, and only the former gets widget rules.
      if (/^\s{2}flutter:/m.test(pubspec) || /^\s*sdk:\s*flutter\s*$/m.test(pubspec)) {
        add('flutter', (pubspec.match(/^\s*version:\s*(\S+)/m) ?? [])[1]);
      }
    } catch {
      /* unreadable pubspec: treat as absent */
    }
  }

  return { stacks, versions };
}
