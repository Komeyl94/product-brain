import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { detectStacks } from '../plugins/guardrails/engine/lib/detect.mjs';
import { buildProfile } from '../plugins/guardrails/engine/lib/profile.mjs';
import { checkBlock, dedupeByRule } from '../plugins/guardrails/engine/lib/engine.mjs';
import { parseUnifiedDiff } from '../plugins/guardrails/engine/lib/diff.mjs';
import { loadConfig } from '../plugins/guardrails/engine/lib/config.mjs';
import { rulesFor, assertUniqueIds, ALL_RULES } from '../plugins/guardrails/engine/rules/index.mjs';

/** A throwaway repository with the given manifests and source files. */
function fixture(files) {
  const root = mkdtempSync(join(tmpdir(), 'guardrail-test-'));
  for (const [path, content] of Object.entries(files)) {
    const full = join(root, path);
    mkdirSync(join(full, '..'), { recursive: true });
    writeFileSync(full, content);
  }
  return root;
}

const idsOf = (findings) => findings.map((f) => f.rule.id).sort();

function check(root, relPath, content, overrides = {}) {
  const profile = buildProfile(root);
  return checkBlock({
    content,
    filePath: join(root, relPath),
    relPath,
    profile,
    rules: rulesFor(profile.stacks),
    baseLine: 0,
    firstOnly: false,
    ...overrides,
  });
}

describe('rule registry', () => {
  test('every rule id is unique', () => {
    assert.ok(assertUniqueIds());
  });

  test('every rule declares a message and a doc reference', () => {
    for (const rule of ALL_RULES) {
      assert.ok(rule.message?.length > 20, `${rule.id} needs a message that says what to do instead`);
      assert.ok(rule.doc, `${rule.id} needs a doc reference`);
      assert.ok(rule.test || rule.custom || rule.wholeCustom, `${rule.id} has no matcher`);
    }
  });
});

describe('stack detection', () => {
  test('an Inertia monolith detects every stack it contains', () => {
    const root = fixture({
      'composer.json': JSON.stringify({
        require: { php: '^8.3', 'laravel/framework': '^13.0', 'inertiajs/inertia-laravel': '^3.0' },
      }),
      'package.json': JSON.stringify({ dependencies: { react: '^19.0' }, devDependencies: { typescript: '^5.7' } }),
    });
    const { stacks, versions } = detectStacks(root);
    assert.deepEqual([...stacks].sort(), ['core', 'inertia', 'laravel', 'php', 'react', 'typescript']);
    assert.equal(versions.laravel, 13);
  });

  test('a Laravel API repo does not pick up frontend stacks', () => {
    const root = fixture({
      'composer.json': JSON.stringify({ require: { php: '^8.3', 'laravel/framework': '^12.0' } }),
    });
    const { stacks } = detectStacks(root);
    assert.deepEqual([...stacks].sort(), ['core', 'laravel', 'php']);
  });

  test('a Dart package without the flutter sdk is not a flutter repo', () => {
    const root = fixture({ 'pubspec.yaml': 'name: pure_dart\nenvironment:\n  sdk: ">=3.0.0"\n' });
    assert.equal(detectStacks(root).stacks.has('flutter'), false);
  });

  test('a flutter app is detected', () => {
    const root = fixture({
      'pubspec.yaml': 'name: app\ndependencies:\n  flutter:\n    sdk: flutter\n',
    });
    assert.equal(detectStacks(root).stacks.has('flutter'), true);
  });

  test('an Angular workspace is detected with its major version', () => {
    const root = fixture({
      'angular.json': '{}',
      'package.json': JSON.stringify({ dependencies: { '@angular/core': '^20.1.0' } }),
    });
    const { stacks, versions } = detectStacks(root);
    assert.ok(stacks.has('angular'));
    assert.equal(versions.angular, 20);
  });
});

describe('core rules', () => {
  const root = fixture({ 'composer.json': JSON.stringify({ require: { php: '^8.3' } }) });

  test('a hardcoded credential is caught', () => {
    const findings = check(root, 'app/Foo.php', `<?php\n$apiKey = "sk_live_abcdefghijklmnop1234";\n`);
    assert.ok(idsOf(findings).includes('core/no-hardcoded-secret'));
  });

  test('api_token is a credential name too', () => {
    // It was not in the name list, so `let api_token = '…'` sailed past the rule while
    // the same line written as api_key was caught. Found by someone testing the gate
    // with the first credential name that came to mind.
    const findings = check(root, 'src/app/probe.ts', "let api_token = 'hdfvjhdvjdfvfdj';\n");
    assert.ok(idsOf(findings).includes('core/no-hardcoded-secret'));
  });

  test('a short value is still a credential', () => {
    const findings = check(root, 'app/Foo.php', '<?php\n$password = "hunter2hunter2";\n');
    assert.ok(idsOf(findings).includes('core/no-hardcoded-secret'));
  });

  test('an ordinary token-named variable is not a credential', () => {
    const findings = check(root, 'src/app/form.ts', "const csrfToken = document.querySelector('meta');\n");
    assert.deepEqual(idsOf(findings), []);
  });

  test('a vendor token is caught even in a file type with no other rules', () => {
    const findings = check(root, 'deploy/notes.txt', 'token glpat-abcdefghijklmnopqrst12\n');
    assert.deepEqual(idsOf(findings), ['core/no-vendor-token']);
  });

  test('a conflict marker is caught', () => {
    const findings = check(root, 'app/Foo.php', '<?php\n<<<<<<< HEAD\n');
    assert.ok(idsOf(findings).includes('core/no-conflict-marker'));
  });

  test('safety rules ignore the waiver comment', () => {
    const findings = check(
      root,
      'app/Foo.php',
      '<?php\n$apiKey = "sk_live_abcdefghijklmnop1234"; // guardrail:allow\n',
    );
    assert.ok(idsOf(findings).includes('core/no-hardcoded-secret'));
  });

  test('.env.example is exempt', () => {
    const findings = check(root, '.env.example', 'API_KEY=aaaaaaaaaaaaaaaaaaaaaaa\n');
    assert.deepEqual(idsOf(findings), []);
  });
});

describe('waivers', () => {
  const root = fixture({ 'composer.json': JSON.stringify({ require: { php: '^8.3' } }) });

  test('a waivable rule respects guardrail:allow on the line', () => {
    const findings = check(root, 'app/Foo.php', '<?php\ndd($x); // guardrail:allow\n');
    assert.deepEqual(idsOf(findings), []);
  });

  test('a waivable rule respects guardrail:allow on the preceding line', () => {
    const findings = check(root, 'app/Foo.php', '<?php\n// guardrail:allow\ndd($x);\n');
    assert.deepEqual(idsOf(findings), []);
  });

  test('guardrail:disable-file silences waivable rules but not safety rules', () => {
    const findings = check(
      root,
      'app/Foo.php',
      '<?php\n// guardrail:disable-file\ndd($x);\n$password = "hunter2hunter2hunter2";\n',
    );
    assert.deepEqual(idsOf(findings), ['core/no-hardcoded-secret']);
  });
});

describe('comment handling', () => {
  const root = fixture({ 'composer.json': JSON.stringify({ require: { php: '^8.3' } }) });

  test('a rule does not fire on prose that merely names the pattern', () => {
    const findings = check(root, 'app/Foo.php', '<?php\n// never call dd($x) in committed code\n');
    assert.deepEqual(idsOf(findings), []);
  });
});

describe('laravel rules', () => {
  const root = fixture({
    'composer.json': JSON.stringify({ require: { php: '^8.3', 'laravel/framework': '^12.0' } }),
  });

  test('interpolated raw SQL is caught', () => {
    const findings = check(root, 'app/Repo.php', '<?php\n$q->whereRaw("id = $id");\n');
    assert.ok(idsOf(findings).includes('laravel/no-raw-query-interpolation'));
  });

  test('a variable in the bindings array is not a finding', () => {
    const findings = check(
      root,
      'app/Repo.php',
      '<?php\n$q->orderByRaw(\'(barcode ilike ?) desc\', ["{$value}%"]);\n',
    );
    assert.deepEqual(idsOf(findings), []);
  });

  test('a regex anchor inside SQL is not interpolation', () => {
    const findings = check(root, 'app/Repo.php', '<?php\n$q->whereRaw("terms !~ \'^[0-9]+$\'");\n');
    assert.deepEqual(idsOf(findings), []);
  });

  test('env() outside config is caught, inside config is not', () => {
    assert.ok(idsOf(check(root, 'app/Service.php', "<?php\n$x = env('APP_URL');\n")).includes('laravel/no-env-outside-config'));
    assert.deepEqual(idsOf(check(root, 'config/app.php', "<?php\nreturn ['url' => env('APP_URL')];\n")), []);
  });

  test('an enum column in a migration is caught', () => {
    const findings = check(root, 'database/migrations/2024_01_01_x.php', "<?php\n$t->enum('status', ['a']);\n");
    assert.ok(idsOf(findings).includes('laravel/no-enum-column-in-migration'));
  });

  test('a migration without down() is caught', () => {
    const findings = check(
      root,
      'database/migrations/2024_01_01_y.php',
      '<?php\nreturn new class extends Migration {\n  public function up(): void {}\n};\n',
    );
    assert.ok(idsOf(findings).includes('laravel/migration-requires-down'));
  });
});

describe('ratchet gating', () => {
  test('mixed return types are only flagged once the repo has adopted strict_types', () => {
    const lax = fixture({
      'composer.json': JSON.stringify({ require: { php: '^8.3' } }),
      'app/A.php': '<?php\nclass A {}\n',
    });
    assert.deepEqual(
      idsOf(check(lax, 'app/B.php', '<?php\nfunction f(): mixed {}\n')).filter((id) => id === 'php/no-mixed-type'),
      [],
    );

    const strict = Object.fromEntries(
      Array.from({ length: 10 }, (_, i) => [`app/S${i}.php`, '<?php\ndeclare(strict_types=1);\nclass S {}\n']),
    );
    const tight = fixture({ 'composer.json': JSON.stringify({ require: { php: '^8.3' } }), ...strict });
    assert.ok(idsOf(check(tight, 'app/B.php', '<?php\nfunction f(): mixed {}\n')).includes('php/no-mixed-type'));
  });

  test('a mixed parameter required by an interface is never flagged', () => {
    const strict = Object.fromEntries(
      Array.from({ length: 10 }, (_, i) => [`app/S${i}.php`, '<?php\ndeclare(strict_types=1);\nclass S {}\n']),
    );
    const root = fixture({ 'composer.json': JSON.stringify({ require: { php: '^8.3' } }), ...strict });
    const findings = check(
      root,
      'app/Rule.php',
      '<?php\ndeclare(strict_types=1);\npublic function validate(string $a, mixed $value, Closure $fail): void {}\n',
    );
    assert.deepEqual(idsOf(findings).filter((id) => id === 'php/no-mixed-type'), []);
  });
});

describe('angular ratchet', () => {
  const standalone = Object.fromEntries(
    Array.from({ length: 8 }, (_, i) => [
      `src/a${i}.component.ts`,
      'export class A { standalone: true; private readonly x = inject(X); }',
    ]),
  );

  test('NgModule is blocked in a standalone codebase', () => {
    const root = fixture({
      'angular.json': '{}',
      'package.json': JSON.stringify({ dependencies: { '@angular/core': '^20.0.0' } }),
      ...standalone,
    });
    assert.ok(idsOf(check(root, 'src/x.module.ts', '@NgModule({})\nexport class XModule {}')).includes('angular/no-ngmodule'));
  });

  test('NgModule is allowed in a deliberately NgModule-based codebase', () => {
    const modules = Object.fromEntries(
      Array.from({ length: 8 }, (_, i) => [`src/m${i}.module.ts`, '@NgModule({})\nexport class M {}']),
    );
    const root = fixture({
      'angular.json': '{}',
      'package.json': JSON.stringify({ dependencies: { '@angular/core': '^20.0.0' } }),
      ...modules,
    });
    assert.deepEqual(
      idsOf(check(root, 'src/x.module.ts', '@NgModule({})\nexport class XModule {}')).filter((id) => id === 'angular/no-ngmodule'),
      [],
    );
  });

  test('@for without track is caught', () => {
    const root = fixture({
      'angular.json': '{}',
      'package.json': JSON.stringify({ dependencies: { '@angular/core': '^18.0.0' } }),
    });
    assert.ok(idsOf(check(root, 'src/x.html', '@for (item of items) {}')).includes('angular/for-requires-track'));
  });
});

describe('diff parsing', () => {
  test('added lines are attributed to the right line numbers', () => {
    const diff = [
      'diff --git a/app/Foo.php b/app/Foo.php',
      'index 111..222 100644',
      '--- a/app/Foo.php',
      '+++ b/app/Foo.php',
      '@@ -10,0 +11,2 @@',
      '+first',
      '+second',
      '@@ -30,1 +32,1 @@',
      '-gone',
      '+replacement',
    ].join('\n');

    const parsed = parseUnifiedDiff(diff);
    assert.deepEqual(parsed.get('app/Foo.php'), [
      { content: 'first\nsecond', baseLine: 10 },
      { content: 'replacement', baseLine: 31 },
    ]);
  });

  test('a deleted file contributes nothing', () => {
    const diff = ['diff --git a/x b/x', '--- a/x', '+++ /dev/null', '@@ -1,1 +0,0 @@', '-gone'].join('\n');
    assert.equal(parseUnifiedDiff(diff).size, 0);
  });

  test('a new file is attributed from line 1', () => {
    const diff = [
      'diff --git a/new.php b/new.php',
      'new file mode 100644',
      '--- /dev/null',
      '+++ b/new.php',
      '@@ -0,0 +1,2 @@',
      '+<?php',
      '+dd($x);',
    ].join('\n');
    assert.deepEqual(parseUnifiedDiff(diff).get('new.php'), [
      { content: '<?php\ndd($x);', baseLine: 0 },
    ]);
  });
});

describe('config policy', () => {
  const rules = rulesFor(new Set(['core', 'php', 'laravel']));

  test('a repository cannot disable a safety rule', () => {
    const root = fixture({
      '.guardrails.json': JSON.stringify({ rules: { 'core/no-hardcoded-secret': 'off' } }),
    });
    const config = loadConfig(root, rules);
    assert.deepEqual(config.rules, {});
    assert.match(config.rejected[0].reason, /cannot be disabled/);
  });

  test('a repository cannot disable a rule the platform team has not marked overridable', () => {
    const root = fixture({ '.guardrails.json': JSON.stringify({ rules: { 'php/no-debug-output': 'off' } }) });
    const config = loadConfig(root, rules);
    assert.deepEqual(config.rules, {});
    assert.match(config.rejected[0].reason, /not overridable/);
  });

  test('a repository can disable an overridable convention rule', () => {
    const root = fixture({
      '.guardrails.json': JSON.stringify({ rules: { 'laravel/controller-no-direct-persistence': 'off' } }),
    });
    const config = loadConfig(root, rules);
    assert.deepEqual(config.rules, { 'laravel/controller-no-direct-persistence': 'off' });
    assert.deepEqual(config.rejected, []);
  });

  test('a repository cannot raise a rule to a severity the engine does not have', () => {
    const root = fixture({ '.guardrails.json': JSON.stringify({ rules: { 'php/no-eval': 'warn' } }) });
    assert.match(loadConfig(root, rules).rejected[0].reason, /unsupported severity/);
  });
});

describe('deduplication', () => {
  test('one finding per rule survives', () => {
    const root = fixture({ 'composer.json': JSON.stringify({ require: { php: '^8.3' } }) });
    const findings = check(root, 'app/Foo.php', '<?php\ndd($a);\ndd($b);\ndd($c);\n');
    assert.equal(findings.filter((f) => f.rule.id === 'php/no-debug-output').length, 3);
    assert.equal(dedupeByRule(findings).filter((f) => f.rule.id === 'php/no-debug-output').length, 1);
  });
});
