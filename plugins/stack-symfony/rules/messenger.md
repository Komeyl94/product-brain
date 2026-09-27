# Messenger

## A message is an immutable, serialisable fact

Carry identifiers and scalars. Never an entity, an entity manager, a request, or a closure.

```php
// wrong — the entity is serialised whole, then handled hours later against stale data,
// and a mapping change makes every queued message unreadable
final readonly class OrderPlaced { public function __construct(public Order $order) {} }

// right
final readonly class OrderPlaced
{
    public function __construct(public int $orderId, public \DateTimeImmutable $placedAt) {}
}
```

The handler re-fetches by id and must cope with the row being gone — by the time it runs, the order may
have been cancelled and deleted.

## Dispatch after the transaction commits

A message dispatched before `flush()` can be consumed by a worker in another process *before* the row
exists. The handler then fails to find its own entity, and the failure looks random because it depends on
worker timing.

```php
$this->em->persist($order);
$this->em->flush();                       // commit first
$this->bus->dispatch(new OrderPlaced($order->getId(), $now));
```

Wrapping the bus in the `doctrine_transaction` middleware handles this for a handler that dispatches
further messages; for a message dispatched from inside another handler, add
`new DispatchAfterCurrentBusStamp()` so it only goes out once the current handler succeeds.

## Handlers

```php
#[AsMessageHandler]
final readonly class SendOrderConfirmation
{
    public function __construct(private OrderRepository $orders, private MailerInterface $mailer) {}

    public function __invoke(OrderPlaced $message): void { /* ... */ }
}
```

One handler, one message type, one public method. The message class in the signature is what registers it —
no configuration.

## Idempotency is not optional

Any transport worth using redelivers: a retry after a transient failure, a worker killed mid-handle, a
broker that guarantees at-least-once. The handler must therefore be safe to run twice. Check state before
acting (`if ($order->isConfirmed()) { return; }`), or key the side effect so the second run is a no-op.
"It will only run once" is not a property any queue gives you.

## Failures, retries and what not to retry

Configure `retry_strategy` (delay, multiplier, max_retries) and a `failure_transport` so a permanently
failing message lands somewhere inspectable instead of being redelivered forever.

- Throw `UnrecoverableMessageHandlingException` when the input is wrong and retrying cannot help — a
  deleted entity, a validation failure. Retrying that is pure noise.
- Let genuinely transient failures (timeouts, 503s) throw normally so the retry strategy applies.
- Never catch-and-log everything. A handler that swallows its exception is reported as successful and the
  message is acknowledged and lost.

## Workers are long-running processes

The assumptions that hold in a request do not hold here:

- Doctrine's connection goes away and the identity map grows across messages. Enable the
  `doctrine_ping_connection` and `doctrine_clear_entity_manager` middleware on the consuming bus.
- Run with `--time-limit` or `--memory-limit` under a supervisor, so a slow leak recycles the process
  instead of exhausting the host.
- A deploy leaves old workers running old code that may not understand a new message shape. Adding an
  optional field to a message is safe; renaming or removing one breaks messages already in the queue.
  Add the new field, deploy, then remove the old one in a later change.

## Sync where async buys nothing

Not everything needs a transport. Routing a message to `sync://` keeps the same code path while running
in-process — useful in tests, and for work that is fast and must be visible immediately. Choose async when
the work is slow, external, or may fail independently of the request.
