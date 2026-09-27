# Routing

## Attributes only

`symfony/no-annotation-routes` blocks `* @Route(...)` in a docblock. Doctrine-annotation routes were
removed in Symfony 7: the docblock stays valid PHP, the route simply stops being registered, and the
endpoint returns 404 with nothing in the log explaining why.

```php
// wrong                              // right
/**                                   #[Route('/orders/{id}', name: 'order_show', methods: ['GET'])]
 * @Route("/orders/{id}")             public function show(int $id): Response
 */
```

## Constrain the method and the parameter

A route with no `methods` answers POST, PUT and DELETE as well — so a link prefetcher or a stray form can
reach an action that was only ever meant to be read.

```php
#[Route('/orders/{id<\d+>}', name: 'order_show', methods: ['GET'])]
```

The inline `<\d+>` requirement makes `/orders/abc` a 404 rather than letting a cast silently turn it into
`0`, which then queries for the row with id 0 and returns "not found" from a place that is harder to debug.
Use `requirements:` for anything longer than a short pattern.

## Name every route

Name it even if nothing links to it yet. Generating a URL with `generateUrl('order_show', ['id' => $id])`
survives a path change; a hardcoded `/orders/'.$id` in a template or a redirect does not, and a renamed
path leaves broken links that no test catches.

Use a consistent naming scheme within the repository — check what the neighbouring controllers do before
inventing one.

## Group with a class-level prefix

```php
#[Route('/api/orders', name: 'api_order_')]
final class OrderController extends AbstractController
{
    #[Route('', name: 'index', methods: ['GET'])]
    #[Route('/{id<\d+>}', name: 'show', methods: ['GET'])]
}
```

The class-level `name` is a prefix, so the actions above are `api_order_index` and `api_order_show`.

## Ordering and collisions

Routes match in the order they are loaded, first match wins. A generic `/orders/{slug}` declared before
`/orders/new` swallows `/orders/new` and hands `new` to the slug lookup. Declare the specific path first,
or constrain the generic one so it cannot match.

`bin/console debug:router` and `router:match /some/path` answer "which route actually handles this" — use
them rather than guessing when a request lands in the wrong action.

## Where routes are defined

Attributes on controllers for application routes. `config/routes/*.yaml` for things that have no controller
of yours — imported bundle routes, redirects, a route whose controller is a framework service. Do not split
the same resource across both; a route defined in two places is a collision waiting for a deploy.

## API versioning and locale

If the project versions its API by path prefix or serves localised URLs, follow the existing scheme
exactly. Introducing a second convention (`/v2/` alongside `/api/v1/`, or a `{_locale}` segment where
nothing else has one) makes every future route a judgement call.
