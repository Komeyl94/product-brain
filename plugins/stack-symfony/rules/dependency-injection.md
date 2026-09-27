# Dependency injection

## Constructor injection, always

`symfony/no-container-service-locator` blocks `$container->get(...)` and `$this->container->get(...)`
outside tests. A service pulled from the container at runtime is invisible to the compiler, so the container
cannot tell you at build time that it is missing, cannot remove it when unused, and cannot be read by a
person to answer "what does this class need?". It also makes the class untestable without a kernel.

```php
// wrong
final class InvoiceSender
{
    public function __construct(private ContainerInterface $container) {}
    public function send(Invoice $i): void { $this->container->get('mailer')->send(/* ... */); }
}

// right
final readonly class InvoiceSender
{
    public function __construct(private MailerInterface $mailer) {}
    public function send(Invoice $i): void { $this->mailer->send(/* ... */); }
}
```

`AbstractController::$container` is the same problem wearing a framework's clothes. Inject into the action
method instead — see controllers.md.

## Promoted, private, readonly

```php
final readonly class ExportOrders
{
    public function __construct(
        private OrderRepository $orders,
        private FilesystemOperator $storage,
    ) {}
}
```

`readonly` on the class (PHP 8.2+) makes every promoted property readonly and stops a later edit from
mutating injected state. If the repository targets PHP 8.1, mark each property `private readonly`.

## Type-hint the interface the class actually needs

Inject `MailerInterface`, `LoggerInterface`, `ClockInterface` — not the concrete implementation. For your
own code, only introduce an interface when there is a real second implementation or a real need to fake it
in a test; a one-implementation interface named `FooInterface` next to `Foo` is ceremony.

When two implementations exist, alias explicitly rather than relying on autowiring guessing:

```yaml
# config/services.yaml
services:
    App\Payment\StripeGateway: ~
    App\Payment\PaymentGateway: '@App\Payment\StripeGateway'
```

## Scalars, env vars and parameters

Autowiring cannot guess a string. Bind it with `#[Autowire]` (Symfony 6.1+) rather than reading
`$_ENV` or `getenv()` inside the class — env access inside a service bypasses the container's env
processors, cannot be overridden per environment, and is invisible to `bin/console debug:container`.

```php
public function __construct(
    #[Autowire(env: 'SHIPPING_API_URL')] private string $apiUrl,
    #[Autowire(param: 'kernel.project_dir')] private string $projectDir,
    #[Autowire(service: 'monolog.logger.payment')] private LoggerInterface $logger,
) {}
```

Secrets come from the environment or the secrets vault, never from a committed parameter. See
`core/no-hardcoded-secret` — it cannot be waived.

## Collections of strategies

When a service needs "all the exporters", inject a tagged iterator instead of a match statement that has to
be edited every time someone adds one.

```php
public function __construct(
    #[AutowireIterator('app.exporter')] private iterable $exporters,  // 6.4+
) {}
```

On older versions use `!tagged_iterator app.exporter` in `services.yaml`. Either way, tag via
`#[AutoconfigureTag]` on the interface so a new implementation is wired by existing.

## Lazy services and circular dependencies

A circular dependency is a design signal, not a wiring problem. Before reaching for `#[Lazy]` or a service
locator, check whether the two classes should be one, or whether one half belongs in a third class. If a
service is genuinely expensive and rarely used on a given request, `#[Lazy]` is the right tool — say why in
the merge request.

## Do not extend framework base classes for convenience

Extending `AbstractController` is fine for a controller. Extending it — or `ServiceEntityRepository` —
from a plain service class to get helper methods drags the container in with it. Inject what you need.

## Test containers are the one exception

`static::getContainer()->get(...)` inside a test is legitimate and the rule skips test files; the test *is*
the composition root. It is still better to construct the unit directly with fakes when the test does not
need the kernel. See testing.md.
