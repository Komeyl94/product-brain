# Doctrine

## Never interpolate into DQL or SQL

`symfony/no-dql-interpolation` blocks a variable inside `createQuery`, `createNativeQuery`,
`executeQuery` or `executeStatement`. Bind parameters — this is injection, and DQL is not safer than SQL
because it compiles straight to it.

```php
// wrong
$em->createQuery("SELECT o FROM App\Entity\Order o WHERE o.reference = '$ref'");

// right
$em->createQuery('SELECT o FROM App\Entity\Order o WHERE o.reference = :ref')
   ->setParameter('ref', $ref);
```

The QueryBuilder has the same trap: `->where("o.status = '$status'")` is interpolation. Use
`->where('o.status = :status')->setParameter('status', $status)`. Parameters cannot bind identifiers —
if a column or sort direction comes from the request, validate it against an allowlist before it reaches
the query.

## Queries live in repositories, named after the question

```php
final class OrderRepository extends ServiceEntityRepository
{
    /** @return list<Order> */
    public function findOpenForCustomer(Customer $customer): array
    {
        return $this->createQueryBuilder('o')
            ->andWhere('o.customer = :customer')
            ->andWhere('o.status IN (:open)')
            ->setParameter('customer', $customer)
            ->setParameter('open', [OrderStatus::Draft, OrderStatus::Paid])
            ->getQuery()
            ->getResult();
    }
}
```

Annotate the return type in phpdoc — `getResult()` is `mixed` to static analysis, and without the
`list<Order>` the whole call chain downstream degrades to untyped.

## N+1 is the default unless you join

Doctrine associations are lazy. Iterating a collection and touching a relation issues one query per row;
the endpoint looks fine on ten fixtures and times out on ten thousand rows.

```php
// one query per order
foreach ($orders as $order) { $total += $order->getCustomer()->getDiscount(); }

// one query
->leftJoin('o.customer', 'c')->addSelect('c')
```

`addSelect` is the part people forget — `leftJoin` alone still leaves the relation a proxy. When you only
need a few columns, select a read model instead of hydrating entities:
`->select('NEW App\Dto\OrderSummary(o.id, o.reference, c.name)')`.

## One flush per use case

`flush()` commits the whole unit of work, so it does not need repeating per entity and must never be inside
a loop — N flushes means N transactions, and a failure halfway leaves the first half committed.

```php
// wrong
foreach ($rows as $row) { $em->persist(Order::fromRow($row)); $em->flush(); }

// right
foreach ($rows as $row) { $em->persist(Order::fromRow($row)); }
$em->flush();
```

For a genuinely large import, flush and `clear()` in batches — otherwise the identity map grows until the
process is killed by the memory limit:

```php
foreach ($repository->streamRows() as $i => $row) {
    $em->persist(Order::fromRow($row));
    if ($i % 500 === 0) { $em->flush(); $em->clear(); }
}
$em->flush();
```

After `clear()` every entity you were holding is detached — re-fetch, do not reuse the old object.

Reading a large result set: `->toIterable()` streams rows instead of hydrating all of them at once. Note
that it requires the query to select a single root entity.

## Entity mapping

- Attributes, not annotations or XML, in new code.
- Types that carry meaning: a PHP 8.1 backed enum with `#[ORM\Column(enumType: OrderStatus::class)]`
  instead of a string; `DateTimeImmutable` with `immutable_datetime` instead of `DateTime` — a mutable
  date handed to a caller can be changed behind the entity's back.
- Every column explicitly `nullable: false` unless it is genuinely optional. A nullable column that is
  never null forces `?Type` on every getter and a null check at every call site.
- `cascade: ['persist']` only where the child has no life of its own. `orphanRemoval: true` deletes rows
  when they leave the collection — correct for owned children, data loss for shared ones.
- Do not add `fetch: 'EAGER'` to fix an N+1. It makes every query touching that entity load the relation,
  including the ones that did not need it. Join at the query.

## Migrations

Generate with `doctrine:migrations:diff`, then **read the generated SQL before committing it** — the
diff reflects whatever state your local database happened to be in, and routinely includes unrelated
drops. Never run `doctrine:schema:update` against anything but a throwaway local database.

A migration that adds a non-nullable column to a populated table fails on deploy. Add it nullable,
backfill, then tighten in a second migration. Keep `down()` honest or make it throw — a `down()` that
silently does nothing is worse than none.
