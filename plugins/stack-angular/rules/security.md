# Security

These rules are ungated: they apply to every repo, every era, and to `.spec.ts` files too.

## Raw HTML

`angular/no-inner-html` blocks `[innerHTML]` and `angular/no-bypass-security` blocks
`bypassSecurityTrust*`. Interpolation (`{{ value }}`) escapes; `[innerHTML]` does not, and
`bypassSecurityTrustHtml` turns Angular's sanitizer off for that value entirely — including for
the CMS field an editor pasted a `<script>` into.

```html
<!-- wrong -->
<div [innerHTML]="article.body"></div>
<div [innerHTML]="sanitizer.bypassSecurityTrustHtml(article.body)"></div>
```

In order of preference:

1. Render the structure with components and bindings; if the content is a known set of blocks,
   model it (`@for (block of article.blocks; track block.id)`) rather than shipping HTML.
2. Sanitize explicitly and keep the result a plain string:
   `this.sanitizer.sanitize(SecurityContext.HTML, article.body)` — this *cleans*, unlike
   `bypassSecurityTrust*`, which only asserts.
3. Sanitize server-side against an allow-list before the value ever reaches the browser.

An SVG or iframe URL you control (a video embed built from an id you validated) can justify
`bypassSecurityTrustResourceUrl` with `// guardrail:allow` — validate the id against a regex first,
and say in your reply why it is safe.

## URLs

Angular sanitizes `[href]` and `[src]`, so a `javascript:` URL is stripped — unless someone
bypassed it. Build external links from a validated allow-list of hosts, and add
`rel="noopener noreferrer"` to any `target="_blank"` (the opened page otherwise gets
`window.opener` and can navigate yours).

Never interpolate user input into a `window.location.href` assignment or `router.navigateByUrl()`
without validating it; an open redirect is how a phishing page acquires your domain in the
address bar.

## Secrets

`core/no-hardcoded-secret`, `core/no-vendor-token` and `core/no-private-key` are **unwaivable** —
there is no `guardrail:allow` for them, in any file, including specs and fixtures.

Everything in `environment.ts` / `environment.prod.ts` ships to the browser. A public API key
(Maps, analytics) belongs there with host restrictions configured at the provider; a secret key,
webhook signing key, database string or admin token does not, in any form. If a call needs a
secret, it needs a backend endpoint.

## Tokens

- Prefer an httpOnly, `Secure`, `SameSite` cookie set by the backend. `localStorage` is readable by
  any script on the origin, so one XSS is a permanent account takeover.
- Where the repo already uses `localStorage` (several do), do not introduce a new storage scheme in
  an unrelated ticket — but do not spread it to a new token either.
- Attach credentials only to your own API origin — see the origin check in `http.md`. A
  `withCredentials: true` or `Authorization` header applied to every URL hands the token to any
  third-party host the app calls.
- Never log a token, a full request body, or a user record (`ts/no-console` blocks the usual
  route). Logs reach browser consoles and error-reporting services.

## Authorisation is a server concern

Hiding a button with `@if (isAdmin())` is UX, not security; the endpoint must enforce it. A route
guard that only reads a role from a JWT payload decoded in the browser can be edited by the user —
it prevents accidents, not attacks. Do not describe a guard as "securing" an endpoint in comments
or MR descriptions.

## Uploads and external content

- Validate type and size client-side for feedback, and state in the MR that the server does the
  real check.
- Never render a user-supplied SVG with `[innerHTML]` — SVG carries scripts.
- Third-party scripts injected at runtime (`document.createElement('script')`) need a named reason
  and a fixed, non-interpolated URL.

## Dependencies

Do not add a package to work around one of these rules — a "safe HTML" npm package with 200 weekly
downloads is a larger attack surface than the sanitizer you were trying to avoid. If a genuine
need exists, say so and ask.
