# Conflict markers

`core/no-conflict-marker` blocks any line that starts with seven `<`, `=` or `>`
characters followed by whitespace or end-of-line. It applies to every file type — code,
YAML, JSON, lockfiles, Markdown — and it reads the raw text, so a marker inside a comment
or a docstring still fires.

## Not waivable

`guardrail:allow` and `guardrail:disable-file` do not suppress it, and `.guardrails.json`
cannot switch it off. A conflict marker on a shared branch is not one person's problem:
it is a parse error in most languages, so the pipeline fails for everyone on that branch
until someone notices it was not their commit. The cost of blocking a legitimate write is
seconds; the cost of letting one through is everybody's afternoon.

## Being blocked here usually means something worse than a stray line

If an agent or a script hits this, the content being written was copied out of a
conflicted working tree. Do not fix it by deleting the three marker lines — that leaves
**both** sides of the conflict in the file, concatenated. It compiles more often than you
would like, and then two competing implementations run in sequence: the migration applies
twice, the handler registers twice, the validation from one branch is silently overwritten
by the other.

Resolve the conflict properly instead: read both sides, decide which behaviour is correct,
write that.

```
  <<<<<<< HEAD          <- indented here only so this file does not trip its own rule
  $rate = $this->tax->rateFor($order);
  =======
  $rate = $order->customer->country->taxRate;
  >>>>>>> feature/tax-by-country
```

Neither half is automatically right. The branch that changed the rule most recently is a
hint, not an answer — ask if it is not obvious from the ticket.

## Before you push

```bash
git diff --check                 # flags conflict markers in the working tree
git grep -n '^<<<<<<< '          # flags ones already committed
```

Both are cheap and catch the case where a marker landed in a file you never opened —
`package-lock.json`, a `.po` file, a generated migration.

## The one false positive

A Markdown setext underline or an ASCII rule of exactly seven `=` characters at the start
of a line matches. Use a different length, or `---`. There is no waiver, so change the
text.
