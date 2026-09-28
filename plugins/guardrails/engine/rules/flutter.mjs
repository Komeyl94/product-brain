/**
 * Flutter / Dart rules.
 *
 * As with Symfony, there is no pilot repository calibrated against this set yet, so it
 * stays narrow. `no-context-across-async-gap` is the exception worth its weight: it is
 * the most common crash-in-production bug in Flutter code and the analyzer only warns
 * about it when `use_build_context_synchronously` is explicitly enabled.
 */

const DART = /\.dart$/;

export const flutterRules = [
  {
    id: 'flutter/no-print',
    stack: 'flutter',
    files: DART,
    skip: (ctx) => ctx.isTest,
    test: /(?<![\w.])print\s*\(/,
    message:
      'print() writes to the production console and cannot be filtered or shipped to crash reporting. Use the app logger, or `debugPrint` if it is genuinely debug-only.',
    doc: 'flutter/logging',
  },
  {
    id: 'flutter/no-dynamic',
    overridable: true,
    stack: 'flutter',
    files: DART,
    skip: (ctx) => ctx.isTest,
    test: /(?<![\w.])dynamic\s+\w+|<\s*dynamic\s*>|List<dynamic>|Map<String,\s*dynamic>\s+(?!json|data)/,
    message:
      '`dynamic` disables static checking. Declare the real type, or use `Object?` with an explicit cast where the shape is genuinely unknown.',
    doc: 'flutter/types',
  },
  {
    id: 'flutter/no-analyzer-ignore',
    stack: 'flutter',
    files: DART,
    raw: true,
    test: /\/\/\s*ignore(_for_file)?:/,
    message:
      'Silencing the analyzer hides the problem rather than fixing it. Address the diagnostic, or raise it with the team if the rule itself is wrong here.',
    doc: 'flutter/analysis',
  },
  {
    id: 'flutter/no-context-across-async-gap',
    stack: 'flutter',
    files: DART,
    skip: (ctx) => ctx.isTest,
    custom: (lines, i) => {
      if (!/\bcontext\b\s*[,)]|\bcontext\./.test(lines[i])) return false;
      const window = lines.slice(Math.max(0, i - 10), i);
      if (!window.some((l) => /\bawait\b/.test(l))) return false;
      // A mounted check between the await and the use is exactly the correct fix.
      return !window.concat(lines[i]).some((l) => /\bmounted\b/.test(l));
    },
    message:
      'Using BuildContext after an await crashes if the widget was disposed while the future ran. Guard it: `if (!context.mounted) return;` immediately after the await.',
    doc: 'flutter/async',
  },
];
