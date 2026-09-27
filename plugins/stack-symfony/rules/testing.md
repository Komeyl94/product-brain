# Testing

## Pick the cheapest test that can fail for the right reason

| Test case | Use when |
|---|---|
| plain `TestCase` | The unit has no container and no database. Construct it with fakes. |
| `KernelTestCase` | You need real wiring or the database, but not HTTP. |
| `WebTestCase` | The thing under test *is* the HTTP behaviour: status, headers, payload shape, auth. |

A `WebTestCase` for logic that a plain `TestCase` could cover is slow, and when it fails it does not say
which layer broke.

## Unit tests construct the class directly

```php
$service = new RegisterUser(new InMemoryUserRepository(), new FakeClock($now));
```

If a service is hard to construct in a test, that is a design signal — usually too many dependencies or a
hidden container lookup. Fix the class rather than reaching for the kernel.

## The container in tests

`static::getContainer()->get(App\Service\Foo::class)` is legitimate — `symfony/no-container-service-locator`
skips test files, because the test is the composition root. The test container exposes private services, so
there is never a reason to make a service public just to test it.

```php
final class RegisterUserTest extends KernelTestCase
{
    public function testItStoresTheUser(): void
    {
        self::bootKernel();
        $register = self::getContainer()->get(RegisterUser::class);
        // ...
    }
}
```

## Database state

Each test must start from a known state and leave nothing behind. If the repository already uses
`dama/doctrine-test-bundle`, every test runs inside a transaction that is rolled back and you need no
teardown. Otherwise wrap the test yourself, or rebuild the schema per test class — never let tests depend
on rows another test left.

Build fixtures in the test, close to the assertion, rather than in a shared fixture file that every test
silently depends on. A named factory method (`anOrderWith(status: Paid)`) beats a global dataset because
the reader can see what the test needs.

Assert against the database, not only the return value, when the point of the use case is persistence —
and `clear()` the entity manager first, otherwise you are asserting against the in-memory identity map and
a broken mapping still passes.

## Functional tests

```php
$client = static::createClient();
$client->loginUser($user);                       // no login form round-trip
$client->request('POST', '/orders', server: ['CONTENT_TYPE' => 'application/json'], content: $json);

self::assertResponseStatusCodeSame(201);
self::assertJsonStringEqualsJsonString($expected, $client->getResponse()->getContent());
```

Use the `assertResponse*` / `assertBrowser*` assertions rather than poking at the response object — they
print the actual response body on failure, which turns a one-line failure into a diagnosis.

Test the authorisation path explicitly: one test for the owner getting 200, one for a different user
getting 403. A missing record-level check is invisible to a test suite that only ever logs in as the owner.

## Messenger

Route the bus to `in-memory://` in the test environment and assert on what was dispatched, rather than
running a worker:

```php
$transport = self::getContainer()->get('messenger.transport.async');
self::assertCount(1, $transport->getSent());
```

Handlers themselves are plain classes — test them by invoking them directly with a message.

## Do not mock what you do not own

Mocking `EntityManagerInterface` or `QueryBuilder` produces a test that asserts Doctrine's API was called in
a particular order, and it keeps passing when the query is wrong. Use the real thing against a test
database, or put the query behind a repository interface with an in-memory fake.

The same applies to time and randomness: inject a clock and a token generator so the test can pin them.
`sleep()` in a test is always wrong — it is slow and still flaky.

## Before claiming it works

Run the project's own commands — read `composer.json` scripts and `Makefile` rather than assuming; it is
usually `vendor/bin/phpunit` (or `bin/phpunit`) plus a static analysis step. Do not report a change as done
on the strength of having written the test.
