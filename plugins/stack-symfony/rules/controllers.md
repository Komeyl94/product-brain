# Controllers

Routing itself — attributes, method constraints, parameter requirements, route names — is in
`routing.md`. This file is about what happens once a request has been matched.

## A controller action is glue

Map the request to a call, map the result to a response. No persistence (blocked by
`symfony/no-entity-manager-in-controller`), no query building, no more than a couple of statements.

Inject per-action, not into the constructor, when a dependency is used by one action only — the container
still resolves it and the other actions stay cheap:

```php
#[Route('/orders/{id}/cancel', methods: ['POST'])]
public function cancel(Order $order, CancelOrder $cancelOrder): Response
{
    $cancelOrder($order, $this->getUser());
    return new Response(status: 204);
}
```

## Input: a typed DTO, validated by the framework

Do not read `$request->request->get(...)` field by field and do not pass `Request` down into a service —
that makes the service impossible to call from a command or a message handler.

```php
final readonly class CreateOrderRequest
{
    public function __construct(
        #[Assert\NotBlank] public string $reference,
        #[Assert\Positive] public int $quantity,
        #[Assert\Email] public ?string $notify = null,
    ) {}
}

#[Route('/orders', methods: ['POST'])]
public function create(#[MapRequestPayload] CreateOrderRequest $payload, PlaceOrder $placeOrder): Response
{
    return $this->json($placeOrder($payload), 201);
}
```

`#[MapRequestPayload]` (6.3+) deserialises and validates, returning 422 with the violation list on failure
and 400 on malformed JSON — you do not write that branch. Use `#[MapQueryString]` for a query DTO and
`#[MapQueryParameter]` for a single scalar. On older versions, build the DTO and call
`ValidatorInterface::validate()` explicitly; never trust unvalidated input further down.

Never map a request payload onto an entity. The payload is missing every server-owned field, and the
mapper will happily write whatever the client sent into the ones it does cover.

## Entity resolution

`#[MapEntity]` (6.2+) resolves an entity from a route parameter and 404s when it is missing:

```php
public function show(#[MapEntity(mapping: ['slug' => 'slug'])] Product $product): Response
```

This is a lookup, not an authorisation check. Resolving the entity proves it exists, not that this user may
see it — see security.md.

## Output

- JSON API: return `$this->json($data, $status)`. Pass serialisation groups explicitly rather than
  serialising an entity wholesale.
- Errors: `throw $this->createNotFoundException()`, `createAccessDeniedException()`, or a
  domain exception mapped by an event listener. Never build an error body by hand in ten actions.
- Never `die()`/`exit()` (blocked by `php/no-die-exit`) — it skips kernel.terminate, so the response is
  never logged and any registered shutdown work does not run.
- Never `dd()`/`dump()` (blocked by `php/no-debug-output`) — in a JSON endpoint it produces a 200 with HTML
  in the body, which is the kind of bug that reaches production because the status code looks fine.

## Status codes

201 with a `Location` for a created resource, 204 for a command with no body, 422 for a validation failure,
409 for a state conflict. A 200 carrying `{"error": ...}` breaks every client's error handling.

## Where a listener beats a controller

Cross-cutting response shaping — exception to JSON, CORS, request id — belongs in an event subscriber, not
repeated in each action. One subscriber, registered by autoconfiguration, beats twenty try/catch blocks.
