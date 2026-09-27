/**
 * PHP rules shared by the Laravel and Symfony stacks.
 *
 * Deliberately narrow. Static analysis already owns the broad correctness surface —
 * PHPStan at level 9 with the custom rules in `ci/phpstan/` catches magic values,
 * `mixed`, parameter counts and naming far more reliably than a regex can. What lives
 * here is the subset worth catching *before* the write lands, either because it is a
 * security boundary or because the feedback loop of a failed pipeline is too slow.
 */

const PHP = /\.php$/;
const APP_CODE = (path) => PHP.test(path) && /[/\\](app|src)[/\\]/.test(path);

export const phpRules = [
  {
    id: 'php/no-debug-output',
    stack: 'php',
    files: PHP,
    test: /(?<![\w$>-])(var_dump|print_r|var_export|dd|dump|ray|xdebug_break)\s*\(/,
    message:
      'Debug output left in the code. Remove it, or use the logger (`Log::debug()`) if the information is worth keeping.',
    doc: 'php/debugging',
  },
  {
    id: 'php/no-eval',
    stack: 'php',
    files: PHP,
    test: /(?<![\w$>-])eval\s*\(/,
    message:
      'eval() executes arbitrary code and cannot be made safe on untrusted input. Express the logic directly.',
    doc: 'php/security',
  },
  {
    id: 'php/no-shell-execution',
    stack: 'php',
    files: PHP,
    test: /(?<![\w$>-])(shell_exec|passthru|proc_open|popen|system)\s*\(|(?<![\w$>-])exec\s*\(/,
    message:
      'Shell execution from application code is a command-injection surface. Use a library, a queued job, or Symfony Process with an argument array — never an interpolated command string.',
    doc: 'php/security',
  },
  {
    id: 'php/no-unserialize',
    stack: 'php',
    files: PHP,
    test: /(?<![\w$>-])unserialize\s*\(/,
    message:
      'unserialize() on anything externally influenced is a remote-code-execution vector. Use json_decode(), or pass `["allowed_classes" => false]` if the payload is genuinely trusted.',
    doc: 'php/security',
  },
  {
    id: 'php/no-die-exit',
    stack: 'php',
    files: APP_CODE,
    test: /(?<![\w$>-])(die|exit)\s*[(;]/,
    message:
      'die()/exit() halts the process and skips middleware, logging and the response lifecycle. Throw an exception or return a response instead.',
    doc: 'php/error-handling',
  },
  {
    id: 'php/require-strict-types',
    stack: 'php',
    files: PHP,
    gate: (gates) => gates.phpStrictTypes,
    // Only fires on a block that is a whole file — an Edit that replaces part of a file
    // has no declare() in it and must not be reported as missing one.
    wholeCustom: (text) =>
      /^<\?php/.test(text.trimStart()) && !/declare\s*\(\s*strict_types\s*=\s*1\s*\)/.test(text),
    message:
      'This project declares `strict_types=1` in its PHP files. Add `declare(strict_types=1);` directly after the opening tag.',
    doc: 'php/style',
  },
  {
    id: 'php/no-mixed-type',
    stack: 'php',
    files: PHP,
    skip: (ctx) => ctx.isTest,
    gate: (gates) => gates.phpStrictTypes,
    overridable: true,
    // Return types and properties only. A `mixed $value` *parameter* is frequently
    // mandated by an interface you do not own — Laravel's ValidationRule::validate and
    // Spatie's query filters both require it — and flagging those teaches people that
    // the rule is wrong rather than that their code is.
    test: /\)\s*:\s*\??mixed\b|\b(private|protected|public|readonly)\s+(readonly\s+)?\??mixed\s+\$/,
    message:
      '`mixed` defeats the type system and fails PHPStan level 9. Declare the real type, or a union of the types actually possible.',
    doc: 'php/types',
  },
];
