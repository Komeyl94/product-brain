# Security

## Authentication is not authorisation

Being logged in says who the user is. It says nothing about whether they may touch *this* row. Every action
that loads a record by an id from the request needs an explicit check — otherwise changing the number in
the URL reads someone else's data. This is the most common real vulnerability in a CRUD application.

```php
// wrong — any authenticated user can read any invoice
#[Route('/invoices/{id}')]
public function show(Invoice $invoice): Response { return $this->json($invoice); }

// right
#[Route('/invoices/{id}')]
#[IsGranted('VIEW', subject: 'invoice')]
public function show(Invoice $invoice): Response { return $this->json($invoice); }
```

## Put the decision in a voter

A voter keeps the rule in one place, testable without HTTP, and reusable from a command or a Twig template.
Scattered `if ($this->getUser()->getId() === $invoice->getOwner()->getId())` checks drift apart.

```php
final class InvoiceVoter extends Voter
{
    protected function supports(string $attribute, mixed $subject): bool
    {
        return $subject instanceof Invoice && in_array($attribute, ['VIEW', 'EDIT'], true);
    }

    protected function voteOnAttribute(string $attribute, mixed $subject, TokenInterface $token): bool
    {
        $user = $token->getUser();
        if (!$user instanceof User) { return false; }
        return match ($attribute) {
            'VIEW' => $subject->getOwner() === $user || $subject->isSharedWith($user),
            'EDIT' => $subject->getOwner() === $user,
        };
    }
}
```

Check permissions (`'EDIT'`) rather than roles (`'ROLE_MANAGER'`) at the call site. Roles change; the
question "may this user edit this invoice" does not.

`access_control` in `security.yaml` is a coarse net for whole URL prefixes. It cannot see the subject, so
it never replaces a voter on a record-level action.

## Input reaching a query

`symfony/no-dql-interpolation` blocks the obvious form. The ones it cannot see:

- A sort field or direction taken from the query string and concatenated into `orderBy()`. Parameters
  cannot bind identifiers — validate against an allowlist first.
- A `LIKE` pattern built from raw input. Escape `%` and `_`, and bind the whole pattern as one parameter.
- Any `executeStatement()` assembled from a loop.

## What the response exposes

Serialising an entity directly ships every mapped field, including ones added later by someone who was not
thinking about this endpoint — password hashes, internal flags, an owner's email. Be explicit:

```php
#[Groups(['invoice:read'])] private string $reference;   // opt in per field
return $this->json($invoice, context: ['groups' => ['invoice:read']]);
```

A dedicated read DTO is stronger still: a new entity field cannot leak through a class that does not
mention it.

## Passwords, tokens, secrets

- Hash with `UserPasswordHasherInterface`. Never `md5`, `sha1`, or a hand-rolled salt.
- Compare secrets with `hash_equals()`, not `===` — a length-dependent comparison leaks the value by timing.
- Generate tokens with `random_bytes()` / `bin2hex()`, never `rand()`, `uniqid()` or `mt_rand()`.
- Secrets come from env vars or the secrets vault. `core/no-hardcoded-secret` and `core/no-vendor-token`
  cannot be waived; a committed credential must be rotated as well as removed.

## Dangerous PHP the hook already blocks

`php/no-eval`, `php/no-shell-execution`, `php/no-unserialize`. If you need to run a binary, use Symfony's
`Process` with an **argument array** — never an interpolated command string:

```php
new Process(['gs', '-sDEVICE=pdfwrite', '-sOutputFile=' . $out, $in]);  // args are not shell-parsed
```

`unserialize()` on anything a user can influence is remote code execution via magic methods. Use
`json_decode()`.

## CSRF and file uploads

Symfony forms include a CSRF token by default — do not disable it to make a test pass. A stateless
token-authenticated JSON API does not need one; a session-cookie endpoint does.

For uploads, validate with `#[Assert\File(mimeTypes: [...])]`, store outside the web root, and generate the
stored filename yourself. Trusting `getClientOriginalName()` lets a client write `../../config/x.php`.
