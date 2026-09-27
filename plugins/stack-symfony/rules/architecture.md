# Architecture

## The layers, and what each is allowed to know

```
HTTP / CLI / Message handler   → translates input, calls one service, formats output
Service (application logic)    → owns the use case and the transaction boundary
Repository                     → owns the query; returns entities or read models
Entity                         → owns its own invariants; knows nothing about HTTP
```

An entry point may know about the layer directly below it. An entity may not know about any of them. A
repository never calls a service.

## Controllers do not persist

`symfony/no-entity-manager-in-controller` blocks `persist()`, `flush()` and `remove()` in any file under a
`Controller/` directory. The reason is not style: persistence in a controller means the use case only
exists behind an HTTP request, so a console command, a message handler or a test has to re-implement it,
and the three copies drift.

```php
// wrong — the only way to register a user is now a POST
#[Route('/users', methods: ['POST'])]
public function create(Request $request, EntityManagerInterface $em): Response
{
    $user = new User($request->request->getString('email'));
    $em->persist($user);
    $em->flush();
    return $this->json($user, 201);
}

// right — the controller maps HTTP to a use case and back
#[Route('/users', methods: ['POST'])]
public function create(#[MapRequestPayload] CreateUserRequest $payload, RegisterUser $registerUser): Response
{
    return $this->json($registerUser($payload->email), 201);
}
```

## One use case per service class

Prefer a small invokable class per use case (`RegisterUser`, `CancelOrder`) over a `UserService` that
accumulates twelve unrelated methods. A class with one public method has one reason to change, one set of
dependencies, and a name that tells the next reader what it does.

```php
final readonly class RegisterUser
{
    public function __construct(
        private UserRepository $users,
        private EntityManagerInterface $em,
        private MessageBusInterface $bus,
    ) {}

    public function __invoke(string $email): User { /* ... */ }
}
```

Group them by domain concern (`src/User/`, `src/Billing/`) rather than by technical role once a repository
has more than a handful — but only if the repository already does this. Do not introduce a new top-level
layout in a codebase that is organised the other way.

## The transaction boundary is the service, not the entity

Exactly one `flush()` per use case, in the service that owns it. Entities never flush. Repositories never
flush — a repository that writes hides the boundary from the caller, so two repositories called in sequence
produce two transactions where the caller assumed one.

## Entities hold invariants, not persistence concerns

An entity method may reject an invalid state change. It may not query, dispatch, log, or read the clock or
the request. Pass the value in.

```php
// wrong — untestable, and the entity now depends on the container's clock
public function markShipped(): void { $this->shippedAt = new \DateTimeImmutable(); }

// right
public function markShipped(\DateTimeImmutable $at): void
{
    if ($this->status !== OrderStatus::Paid) {
        throw new \DomainException('Only a paid order can ship.');
    }
    $this->status = OrderStatus::Shipped;
    $this->shippedAt = $at;
}
```

## Entities are not DTOs

Do not accept an entity straight from request payload mapping, and do not serialise an entity directly into
a response unless serialisation groups are explicit. The two shapes diverge — the request is missing
server-owned fields, the response leaks them. See controllers.md and security.md.

## Naming

`RegisterUser` not `UserManager`. `OrderRepository::findOpenForCustomer()` not `findBy(['status' => ...])`
scattered across five callers. A query that appears in two places belongs in the repository with a name.
