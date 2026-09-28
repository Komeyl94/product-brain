# Constitution

> The non-negotiable principles every spec, decision, and change in this product must respect.
> Method-agnostic: this says *what* must hold, not *how* you write specs.

**Version:** 1.0.0
**Last updated:** [DATE]

---

## Principles

### 1 — Brand design system
The product has one product-level design system — `DESIGN.md` at the hub root — lifted from the
frontend's design source (never invented, never sampled from a screenshot) and never contradicted
by an app-level design file. Every artifact the hub generates — docs pages, dashboards, roadmaps,
release notes, PDFs, decks — is styled only from the compiled brand (`brand/brand.css`, its
`--ds-*` variables, fonts embedded); no colour, font, or radius literal outside that compiled
block. The brand changes in `DESIGN.md` first, and only there; conflicts between apps over a
brand-level token are surfaced to a human to decide, never resolved silently by an extractor or an
agent. Enforced by `check-brand.py`, run in the verify step of every artifact skill — zero
failures is the bar for publishing.

*(Required by Product Brain — teams may reword this principle, not delete it.)*

### 2 — [Principle name]
[One or two sentences. A rule that would cause a change to be rejected if violated.]

### 3 — [Principle name]
[…]

### 4 — [Principle name]
[…]

---

## Per-repo notes (optional)

> Only where a repo legitimately differs (e.g. test conventions, API patterns). Keep these as
> additions to the shared principles above, not copies.

### backend-api
- [rule specific to the API]

### web-app
- [rule specific to the web app]

---

## Amendment procedure

Open a PR against this file. Bump the version on any change. Link affected specs/decisions.
