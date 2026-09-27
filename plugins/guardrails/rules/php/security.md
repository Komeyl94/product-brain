# PHP security

Three rules, on every `.php` file in the repository.

## `php/no-eval`

`eval()` is blocked outright. There is no input sanitisation that makes it safe, because
the thing you are sanitising is source code. Nearly every use of it is a dispatch table
written the hard way:

```php
// wrong
eval("\$result = \$a {$operator} \$b;");

// right
$result = match ($operator) {
    '+' => $a + $b,
    '-' => $a - $b,
    default => throw new InvalidArgumentException("Unsupported operator: {$operator}"),
};
```

If you genuinely need user-authored expressions (a rules builder, a formula field), that
is a sandboxed expression library — `symfony/expression-language` with an allow-list of
functions — and a decision to raise before writing the code, not a waiver.

## `php/no-shell-execution`

Blocks `exec`, `shell_exec`, `system`, `passthru`, `proc_open`, `popen`. The problem is
the string: PHP hands it to `/bin/sh`, so a filename containing `; rm -rf` or `$(curl …)`
is a command, and `escapeshellarg()` is one forgotten call away from being missing.

```php
// wrong — $path came from an upload
exec("convert {$path} -resize 800x600 {$out}");

// right — an argument array never reaches a shell
(new Process(['convert', $path, '-resize', '800x600', $out]))->mustRun();
```

Prefer a PHP library over a binary (Imagick, league/flysystem, a PDF package). If the work
is slow, put the Process call in a queued job — a web request waiting on a subprocess ties
up a PHP-FPM worker for the duration.

## `php/no-unserialize`

`unserialize()` on anything externally influenced is remote code execution, not just data
corruption. The attacker does not need a class of yours: the payload names any class in
`vendor/` with a `__destruct`, `__wakeup` or `__toString` that touches a file path or a
callable, and chains them. Laravel, Monolog and Doctrine have all shipped usable gadget
chains at some point, so "we do not have a vulnerable class" is a claim with a short
shelf life.

```php
// wrong
$payload = unserialize($request->input('state'));

// right
$payload = json_decode($request->input('state'), true, flags: JSON_THROW_ON_ERROR);

// acceptable only when the blob is genuinely internal, e.g. a column your app wrote
$payload = unserialize($row->blob, ['allowed_classes' => false]); // guardrail:allow
```

`allowed_classes => false` turns objects into `__PHP_Incomplete_Class` instead of
instantiating them, which removes the gadget surface — it does not make a
user-controlled blob safe, because the rest of the structure is still attacker-shaped.

## Waivers

All three are waivable, none is overridable in `.guardrails.json`. A waiver needs the
narrowest scope — the single line, not the file — and a sentence in your reply saying why
the reasoning does not apply. "Refactoring is out of scope for this ticket" is not that
sentence.
