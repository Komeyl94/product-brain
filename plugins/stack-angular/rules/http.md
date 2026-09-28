# HTTP

## Type every call

```ts
// wrong — returns Observable<Object>, and every consumer is untyped from here down
return this.http.get(`${this.base}/orders/${id}`);
```

```ts
// right
return this.http.get<OrderDto>(`${this.base}/orders/${id}`);
```

The generic is not a cast that makes the response safe — it is the contract you then maintain. If
the API wraps payloads (`{ data, meta }`), type the envelope and unwrap once:

```ts
interface Envelope<T> { data: T; meta?: { total: number } }

getOrders(): Observable<Order[]> {
  return this.http
    .get<Envelope<OrderDto[]>>(`${this.base}/orders`)
    .pipe(map((res) => res.data.map(toOrder)));
}
```

Keep `*Dto` types (what the server sends, snake_case and all) separate from the domain model the
app uses, and map at the service boundary. One mapping function beats a rename scattered across
twenty templates when the API changes.

## Registration

`HttpClientModule` is deprecated; `angular/no-http-client-module` blocks it from v19 upward.

```ts
// standalone repo
bootstrapApplication(AppComponent, {
  providers: [provideHttpClient(withInterceptors([authInterceptor, errorInterceptor]))],
});
```

```ts
// NgModule repo — still provideHttpClient, in the module providers
@NgModule({
  providers: [provideHttpClient(withInterceptors([authInterceptor]))],
})
export class CoreModule {}
```

Do not add `HttpClientModule` to `imports` "because the module list already has modules" — the
provider function works in both eras.

## Interceptors

Functional interceptors in v15+ repos; class interceptors with `HTTP_INTERCEPTORS` only where the
repo already has them.

```ts
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const token = inject(TokenStore).token();
  if (!token || !req.url.startsWith(environment.apiUrl)) return next(req);
  return next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};
```

The origin check is not optional — an interceptor that attaches the bearer token to every request
leaks it to every third-party URL the app ever calls. See `security.md`.

Order matters: interceptors run in array order on the way out and in reverse on the way back, so
auth goes before logging, and the error mapper goes last.

## Errors

Map transport errors to something the UI can act on, at the service or interceptor boundary:

```ts
private handle(err: HttpErrorResponse): Observable<never> {
  if (err.status === 0) return throwError(() => new AppError('offline'));
  if (err.status === 422) return throwError(() => new ValidationError(err.error?.errors ?? {}));
  return throwError(() => new AppError('unexpected', { status: err.status }));
}
```

- Never swallow an error into `of(null)` at the service level; the component cannot distinguish
  "no data" from "request failed".
- `retry` only on idempotent GETs, and only with a backoff
  (`retry({ count: 2, delay: (_, n) => timer(n * 500) })`). Retrying a POST duplicates orders.
- Do not `console.error` the response (`ts/no-console`); use the app's logger, and never log
  headers or bodies that carry tokens or personal data.

## Requests

- `HttpParams` for query strings — it encodes. String concatenation breaks on `&`, spaces and
  non-ASCII, and is how a filter value ends up splitting a URL.
- A base URL comes from `environment`, never hardcoded per service.
- Cancellation is free with `switchMap` (see `rxjs.md`); an in-flight request is aborted when the
  observable is unsubscribed, which is another reason not to convert to a promise.
- `firstValueFrom` in functional guards and resolvers, which want a promise and complete anyway.

## Caching

```ts
readonly countries$ = this.http
  .get<Country[]>(`${this.base}/countries`)
  .pipe(shareReplay({ bufferSize: 1, refCount: true }));
```

`shareReplay(1)` without `refCount` keeps the subscription alive for the life of the app. For
reference data that is deliberate; for anything user-scoped it is a leak and a stale-data bug after
logout. Clear cached per-user state on sign-out explicitly.
